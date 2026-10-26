// SPDX-License-Identifier: AGPL-3.0-only
//! A live Takion connection (the connection half of the reference's takion.c): the handshake, then one thread that
//! receives, checks each packet's GMAC, puts the data messages and the video in order, acknowledges data and sends
//! unacknowledged messages again. What arrives goes out as events; sending works from any thread.
//!
//! Before the key exchange (BIG/BANG, carried by this connection) there is no crypto: packets are not signed and
//! video and audio are held back (up to 32 packets) until `set_crypt`, as in the reference. The network test
//! (Senkusha, version 7) runs without crypto: there video and audio go out as they come. The reference acknowledges a
//! DATA message after its handler ran, so the BANG's acknowledgement goes out signed with the keys BANG brought;
//! here the handler is the Python side, so without keys an acknowledgement waits for `set_crypt` (up to 100 ms).
//!
//! Once the stream runs (`start_stream`, after STREAMINFO), video goes through the video receiver (video.rs) and
//! comes out as whole frames, audio through the audio receiver (audio.rs) as Opus frames in order, and a congestion
//! report goes to the console every 200 ms. The reference starts the reports right after the handshake; there is
//! nothing to count before the stream. The controller state goes out from then on too (feedback.rs), on a thread of
//! its own: at least every 200 ms, and at once when it changes.

use std::collections::VecDeque;
use std::io::ErrorKind;
use std::net::{SocketAddr, UdpSocket};
use std::sync::atomic::{AtomicBool, AtomicU32, AtomicU64, Ordering};
use std::sync::mpsc::{channel, Receiver, RecvTimeoutError, Sender};
use std::sync::{Arc, Condvar, Mutex};
use std::thread::JoinHandle;
use std::time::{Duration, Instant};

use crate::bitstream;
use crate::feedback::{self, ControllerState};
use crate::frame::{self, PacketStats};
use crate::gkcrypt::{GkCrypt, BLOCK_SIZE, ECDH_SECRET_SIZE, HANDSHAKE_KEY_SIZE};
use crate::keystate::KeyState;
use crate::reorder::{Bits, DropStrategy, ReorderQueue};
use crate::sendbuffer::{SendBuffer, SendBufferError, RESEND_WAKEUP};
use crate::takion::{
    self, AvPacket, TakionError, A_RWND, BASE_TYPE_MASK, CHUNK_COOKIE_ACK, CHUNK_DATA, CHUNK_DATA_ACK, CHUNK_INIT_ACK,
    DATA_TYPE_PAD_INFO, DATA_TYPE_PROTOBUF, DATA_TYPE_RUMBLE, DATA_TYPE_TRIGGER_EFFECTS, MESSAGE_HEADER_SIZE,
    PACKET_AUDIO, PACKET_CONTROL, PACKET_VIDEO,
};
use crate::audio::{AudioFrame, AudioReceiver, AudioStats};
use crate::video::{VideoEvent, VideoReceiver, VideoStats};

pub const PORT: u16 = 9296;
pub const EXPECT_TIMEOUT: Duration = Duration::from_millis(5000);
pub const CONNECT_TRIES: u32 = 3;
const DATA_QUEUE_SIZE_EXP: u32 = 4;
const VIDEO_QUEUE_SIZE_EXP: u32 = 6;
const VIDEO_REORDER_TIMEOUT: Duration = Duration::from_micros(16000);     // about a frame at 60 fps
const POSTPONE_MAX: usize = 32;
const RECEIVE_SIZE: usize = 1500;
const DATA_ACK_PACKET_SIZE: usize = 1 + MESSAGE_HEADER_SIZE + 0xc;
const ACK_WAIT_FOR_CRYPT: Duration = Duration::from_millis(100);
const CONGESTION_INTERVAL: Duration = Duration::from_millis(200);
const STOP_CHECK: Duration = Duration::from_millis(20);
/// The reference's default for the most loss a congestion report admits (its setting "packet_loss_max").
pub const PACKET_LOSS_MAX: f64 = 0.05;
// The data channel the reference's DATA messages go on; STREAMINFOACK uses 9, frame reports 2.
pub const CHANNEL_DEFAULT: u16 = 1;

#[derive(Debug)]
pub enum ConnectError {
    Io(std::io::Error),
    Timeout(&'static str),
    Invalid(&'static str),
}

impl std::fmt::Display for ConnectError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ConnectError::Io(error) => write!(f, "{error}"),
            ConnectError::Timeout(what) => write!(f, "no {what} from the console"),
            ConnectError::Invalid(what) => write!(f, "the console sent an invalid {what}"),
        }
    }
}

#[derive(Debug)]
pub enum SendError {
    Io(std::io::Error),
    Buffer(SendBufferError),
    Closed,
}

impl std::fmt::Display for SendError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            SendError::Io(error) => write!(f, "{error}"),
            SendError::Buffer(SendBufferError::Overflow) => write!(f, "the send buffer is full"),
            SendError::Buffer(SendBufferError::Duplicate) => write!(f, "duplicate sequence number"),
            SendError::Closed => write!(f, "the connection is closed"),
        }
    }
}

#[derive(Debug, PartialEq)]
pub enum Event {
    /// A DATA message, in order: its data type (0: protobuf) and the data.
    Data { data_type: u8, channel: u16, data: Vec<u8> },
    /// One of our DATA messages was acknowledged.
    DataAck(u32),
    /// A video or audio packet, decrypted; video in order of packet index. Only until the stream runs.
    Av { packet: AvPacket, data: Vec<u8> },
    /// Once the stream runs: a frame, a resolution switch or frames to report as corrupt.
    Video(VideoEvent),
    /// Once the stream runs: the next Opus frame of the sound, in order (no data: lost).
    Audio(AudioFrame),
    /// The receiving thread stopped: closed, or the socket failed.
    Closed(String),
}

#[derive(Debug, Default, Clone, Copy, PartialEq, Eq)]
pub struct Stats {
    pub received: u64,
    pub mac_mismatch: u64,
    pub invalid: u64,
    pub data_dropped: u64,
    pub video_dropped: u64,
    pub video_skipped: u64,
    pub video_simulated_lost: u64,          // dropped on purpose (set_simulated_loss)
    /// Video packets that came while the queue was waiting for exactly them: late, not lost. How often the wait
    /// for a missing packet (VIDEO_REORDER_TIMEOUT) pays off.
    pub video_late: u64,
    pub resent: u64,
    pub given_up: u64,
    pub congestion_reports: u64,
    pub feedback_states: u64,
    pub feedback_history: u64,
}

struct SendState {
    crypt: Option<GkCrypt>,
    key_pos: u64,
    seq_num: u32,
    buffer: SendBuffer,
    pending_ack: Option<(u32, Instant)>,
}

struct Shared {
    sock: UdpSocket,
    version: u8,
    crypt_expected: bool,
    tag_local: u32,
    tag_remote: u32,
    stop: AtomicBool,
    send: Mutex<SendState>,
    crypt_remote: Mutex<Option<GkCrypt>>,
    stats: Mutex<Stats>,
    packet_stats: Mutex<PacketStats>,
    /// For trying the recovery from lost packets on a network that loses none (not for users): the share of video
    /// packets dropped on arrival, in hundredths of a percent, and the state of the random numbers that pick them.
    video_loss: AtomicU32,
    loss_random: AtomicU64,
}

/// The controller state for the feedback thread; the sender exists once the stream runs.
struct Feedback {
    state: ControllerState,
    sender: Option<feedback::Sender>,
    stop: bool,
    players: PlayerExperiment,
    second: Option<feedback::Sender>,               // PlayerExperiment::Marked: the second controller's sender
}

impl Feedback {
    fn ready(&self) -> bool {
        self.sender.as_ref().is_some_and(|s| s.ready()) || self.second.as_ref().is_some_and(|s| s.ready())
    }
}

/// The several-players experiment (not for users): how a second controller's input goes to the console, to find
/// out what the console accepts. The reference knows one controller only.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PlayerExperiment {
    /// One controller, as the reference.
    Off,
    /// The second controller's input is not sent (the console is only told it connected).
    Announce,
    /// The second controller's states and events in packets of their own, mark in the first byte of each.
    Marked(u8),
    /// The second controller's state in the first one's FEEDBACK_STATE packets (two states, byte 3 = 2).
    Packed,
}

struct Stream {
    video: VideoReceiver,
    audio: AudioReceiver,
    pending: VecDeque<Event>,
}

pub struct Connection {
    shared: Arc<Shared>,
    events: Mutex<Receiver<Event>>,
    thread: Mutex<Option<JoinHandle<()>>>,
    stream: Mutex<Option<Stream>>,
    congestion: Mutex<Option<JoinHandle<()>>>,
    feedback: Arc<(Mutex<Feedback>, Condvar)>,
    feedback_thread: Mutex<Option<JoinHandle<()>>>,
}

fn is_timeout(error: &std::io::Error) -> bool {
    matches!(error.kind(), ErrorKind::WouldBlock | ErrorKind::TimedOut)
}

/// Waits for one control packet addressed to tag_local; None on timeout. Other packets are skipped.
fn expect_message(sock: &UdpSocket, tag_local: u32, deadline: Instant) -> Result<Option<Vec<u8>>, std::io::Error> {
    let mut buf = [0u8; RECEIVE_SIZE];
    loop {
        let remaining = deadline.saturating_duration_since(Instant::now());
        if remaining.is_zero() {
            return Ok(None);
        }
        sock.set_read_timeout(Some(remaining))?;
        let size = match sock.recv(&mut buf) {
            Ok(size) => size,
            Err(error) if is_timeout(&error) => return Ok(None),
            Err(error) => return Err(error),
        };
        if size > MESSAGE_HEADER_SIZE && buf[0] == PACKET_CONTROL
            && takion::parse_message(&buf[1..size], tag_local, &mut KeyState::new()).is_ok()
        {
            return Ok(Some(buf[..size].to_vec()));
        }
    }
}

fn handshake(sock: &UdpSocket, tag_local: u32, timeout: Duration, tries: u32) -> Result<u32, ConnectError> {
    // INIT -> INIT_ACK: sent again when nothing comes.
    let mut init_ack = None;
    for _ in 0..tries {
        sock.send(&takion::init_packet(tag_local, tag_local)).map_err(ConnectError::Io)?;
        if let Some(packet) = expect_message(sock, tag_local, Instant::now() + timeout).map_err(ConnectError::Io)? {
            init_ack = Some(packet);
            break;
        }
    }
    let packet = init_ack.ok_or(ConnectError::Timeout("answer to the stream connection (INIT_ACK)"))?;
    let message = takion::parse_message(&packet[1..], tag_local, &mut KeyState::new())
        .map_err(|_| ConnectError::Invalid("INIT_ACK"))?;
    let init = takion::parse_init_ack(&message).map_err(|_| ConnectError::Invalid("INIT_ACK"))?;

    // COOKIE -> COOKIE_ACK; a repeated INIT_ACK (an answer to a resent INIT) is skipped.
    for _ in 0..tries {
        sock.send(&takion::cookie_packet(init.tag, &init.cookie)).map_err(ConnectError::Io)?;
        let deadline = Instant::now() + timeout;
        while let Some(packet) = expect_message(sock, tag_local, deadline).map_err(ConnectError::Io)? {
            let message = takion::parse_message(&packet[1..], tag_local, &mut KeyState::new())
                .map_err(|_| ConnectError::Invalid("COOKIE_ACK"))?;
            match (message.chunk_type, message.chunk_flags) {
                (CHUNK_INIT_ACK, _) => continue,
                (CHUNK_COOKIE_ACK, 0) => return Ok(init.tag),
                _ => return Err(ConnectError::Invalid("COOKIE_ACK")),
            }
        }
    }
    Err(ConnectError::Timeout("COOKIE_ACK"))
}

impl Connection {
    /// Connects to the console's Takion port (9296) and runs the handshake; version is 9 (PS4), 12 (PS5) or 7
    /// (the network test). Without crypt_expected (the network test), video and audio are not held for keys.
    pub fn connect(addr: SocketAddr, version: u8, crypt_expected: bool, timeout: Duration, tries: u32)
        -> Result<Self, ConnectError> {
        let bind: SocketAddr = if addr.is_ipv4() { "0.0.0.0:0" } else { "[::]:0" }.parse().unwrap();
        let sock = UdpSocket::bind(bind).map_err(ConnectError::Io)?;
        sock.connect(addr).map_err(ConnectError::Io)?;
        let mut tag = [0u8; 4];
        getrandom_tag(&mut tag);
        let tag_local = u32::from_be_bytes(tag).max(1);
        let tag_remote = handshake(&sock, tag_local, timeout, tries.max(1))?;

        let shared = Arc::new(Shared {
            sock,
            version,
            crypt_expected,
            tag_local,
            tag_remote,
            stop: AtomicBool::new(false),
            video_loss: AtomicU32::new(0),
            loss_random: AtomicU64::new(0x9e37_79b9_7f4a_7c15),
            send: Mutex::new(SendState {
                crypt: None,
                key_pos: 0,
                seq_num: tag_local,
                buffer: SendBuffer::new(),
                pending_ack: None,
            }),
            crypt_remote: Mutex::new(None),
            stats: Mutex::new(Stats::default()),
            packet_stats: Mutex::new(PacketStats::default()),
        });
        let (sender, receiver) = channel();
        let worker = Arc::clone(&shared);
        let thread = std::thread::Builder::new()
            .name("takion".into())
            .spawn(move || Receiving::new(worker, sender).run())
            .map_err(ConnectError::Io)?;
        Ok(Self {
            shared,
            events: Mutex::new(receiver),
            thread: Mutex::new(Some(thread)),
            stream: Mutex::new(None),
            congestion: Mutex::new(None),
            feedback: Arc::new((
                Mutex::new(Feedback { state: ControllerState::idle(), sender: None, stop: false,
                                      players: PlayerExperiment::Off, second: None }),
                Condvar::new(),
            )),
            feedback_thread: Mutex::new(None),
        })
    }

    pub fn tag_local(&self) -> u32 {
        self.shared.tag_local
    }

    pub fn tag_remote(&self) -> u32 {
        self.shared.tag_remote
    }

    pub fn version(&self) -> u8 {
        self.shared.version
    }

    pub fn stats(&self) -> Stats {
        *self.shared.stats.lock().unwrap()
    }

    /// The stream keys from the key exchange: index 2 signs what we send, index 3 what the console sends.
    /// An acknowledgement held back for the keys goes out now, signed.
    pub fn set_crypt(&self, handshake_key: &[u8; HANDSHAKE_KEY_SIZE], ecdh_secret: &[u8; ECDH_SECRET_SIZE]) {
        *self.shared.crypt_remote.lock().unwrap() = Some(GkCrypt::new(3, handshake_key, ecdh_secret));
        let mut send = self.shared.send.lock().unwrap();
        send.crypt = Some(GkCrypt::new(2, handshake_key, ecdh_secret));
        if let Some((seq_num, _)) = send.pending_ack.take() {
            send_ack(&self.shared, &mut send, seq_num);
        }
    }

    /// Sends a DATA message (data type protobuf) and keeps it for resending; returns its sequence number. With
    /// `cont`, the message continues the previous one (the BIG split over several packets) and has no data type.
    pub fn send_data(&self, chunk_flags: u8, channel: u16, data: &[u8], cont: bool) -> Result<u32, SendError> {
        if self.shared.stop.load(Ordering::Relaxed) {
            return Err(SendError::Closed);
        }
        let mut send = self.shared.send.lock().unwrap();
        let key_pos = advance(&mut send, data.len());
        let seq_num = send.seq_num;
        send.seq_num = seq_num.wrapping_add(1);
        let mut packet = if cont {
            takion::data_cont_packet(self.shared.tag_remote, key_pos, chunk_flags, seq_num, channel, data)
        } else {
            takion::data_packet(self.shared.tag_remote, key_pos, chunk_flags, seq_num, channel, data)
        };
        takion::packet_mac(send.crypt.as_mut(), &mut packet, key_pos).expect("a control packet");
        self.shared.sock.send(&packet).map_err(SendError::Io)?;
        send.buffer.push(seq_num, packet, Instant::now()).map_err(SendError::Buffer)?;
        Ok(seq_num)
    }

    /// A packet as it is, unsigned and not kept: the network test's pings.
    pub fn send_raw(&self, packet: &[u8]) -> Result<(), SendError> {
        self.shared.sock.send(packet).map(|_| ()).map_err(SendError::Io)
    }

    pub fn send_congestion(&self, word_0: u16, received: u16, lost: u16) -> Result<(), SendError> {
        send_congestion(&self.shared, word_0, received, lost)
    }

    /// The stream runs: video from now on through the video receiver (profiles: the resolutions in STREAMINFO),
    /// congestion reports every 200 ms, the loss reported at most packet_loss_max, and the controller state.
    /// The stream runs: headers are the parameter sets of each resolution in STREAMINFO (bitstream::header; the video
    /// receiver looks into the frames with them), hevc the codec.
    pub fn start_stream(&self, headers: &[Vec<u8>], hevc: bool, packet_loss_max: f64) -> Result<(), SendError> {
        let mut congestion = self.congestion.lock().unwrap();
        if congestion.is_some() {
            return Ok(());
        }
        *self.stream.lock().unwrap() =
            Some(Stream {
                video: VideoReceiver::new(headers.iter().map(|h| bitstream::header(h, hevc)).collect()),
                audio: AudioReceiver::new(),
                pending: VecDeque::new(),
            });
        let shared = Arc::clone(&self.shared);
        let thread = std::thread::Builder::new()
            .name("congestion".into())
            .spawn(move || report_congestion(shared, packet_loss_max))
            .map_err(SendError::Io)?;
        *congestion = Some(thread);
        {
            let mut feedback = self.feedback.0.lock().unwrap();
            let mut sender = feedback::Sender::new(self.shared.version, Instant::now());
            sender.set(feedback.state);
            feedback.sender = Some(sender);
            if let PlayerExperiment::Marked(mark) = feedback.players {
                feedback.second = Some(feedback::Sender::marked(self.shared.version, Instant::now(), mark));
            }
        }
        let (shared, state) = (Arc::clone(&self.shared), Arc::clone(&self.feedback));
        let thread = std::thread::Builder::new()
            .name("feedback".into())
            .spawn(move || send_feedback(shared, state))
            .map_err(SendError::Io)?;
        *self.feedback_thread.lock().unwrap() = Some(thread);
        Ok(())
    }

    /// The controller as it is now; it goes to the console once the stream runs.
    pub fn set_controller_state(&self, state: ControllerState) {
        let (lock, cond) = &*self.feedback;
        let mut feedback = lock.lock().unwrap();
        feedback.state = state;
        if let Some(sender) = feedback.sender.as_mut() {
            sender.set(state);
            cond.notify_one();
        }
    }

    /// For trying the recovery from lost packets (not for users): drop this share of the video packets on arrival,
    /// in percent.
    pub fn set_simulated_loss(&self, percent: f64) {
        self.shared.video_loss.store((percent.clamp(0.0, 100.0) * 100.0).round() as u32, Ordering::Relaxed);
    }

    /// The several-players experiment, chosen before the stream starts.
    pub fn set_player_experiment(&self, players: PlayerExperiment) {
        self.feedback.0.lock().unwrap().players = players;
    }

    /// The several-players experiment: the second controller as it is now (ignored when the experiment is off or
    /// only announces it).
    pub fn set_second_controller_state(&self, state: ControllerState) {
        let (lock, cond) = &*self.feedback;
        let mut feedback = lock.lock().unwrap();
        match feedback.players {
            PlayerExperiment::Marked(_) => {
                if let Some(second) = feedback.second.as_mut() {
                    second.set(state);
                }
            }
            PlayerExperiment::Packed => {
                if let Some(sender) = feedback.sender.as_mut() {
                    sender.set_extra(state);
                }
            }
            PlayerExperiment::Off | PlayerExperiment::Announce => return,
        }
        cond.notify_one();
    }

    /// The video receiver's counters, once the stream runs.
    pub fn video_stats(&self) -> Option<VideoStats> {
        self.stream.lock().unwrap().as_ref().map(|stream| stream.video.stats)
    }

    /// The audio receiver's counters, once the stream runs.
    pub fn audio_stats(&self) -> Option<AudioStats> {
        self.stream.lock().unwrap().as_ref().map(|stream| stream.audio.stats)
    }

    /// The next event, waiting up to timeout; None when there was none.
    pub fn next_event(&self, timeout: Duration) -> Option<Event> {
        let deadline = Instant::now() + timeout;
        let events = self.events.lock().unwrap();
        loop {
            if let Some(stream) = self.stream.lock().unwrap().as_mut() {
                if let Some(event) = stream.pending.pop_front() {
                    return Some(event);
                }
            }
            let event = match events.recv_timeout(deadline.saturating_duration_since(Instant::now())) {
                Ok(event) => event,
                Err(RecvTimeoutError::Timeout) | Err(RecvTimeoutError::Disconnected) => return None,
            };
            let Event::Av { packet, data } = event else { return Some(event) };
            let mut stream = self.stream.lock().unwrap();
            let Some(stream) = stream.as_mut() else { return Some(Event::Av { packet, data }) };
            let mut packet_stats = self.shared.packet_stats.lock().unwrap();
            if !packet.is_video {
                packet_stats.push_seq(packet.frame_index);
                stream.pending.extend(stream.audio.packet(&packet, &data).into_iter().map(Event::Audio));
                continue;
            }
            stream.pending.extend(stream.video.packet(&packet, &data, &mut packet_stats).into_iter().map(Event::Video));
        }
    }

    /// Stops the receiving thread, the congestion reports and the controller state; the last event is Closed.
    pub fn close(&self) {
        self.shared.stop.store(true, Ordering::Relaxed);
        self.feedback.0.lock().unwrap().stop = true;
        self.feedback.1.notify_one();
        if let Some(thread) = self.feedback_thread.lock().unwrap().take() {
            let _ = thread.join();
        }
        if let Some(thread) = self.thread.lock().unwrap().take() {
            let _ = thread.join();
        }
        if let Some(thread) = self.congestion.lock().unwrap().take() {
            let _ = thread.join();
        }
    }
}

impl Drop for Connection {
    fn drop(&mut self) {
        self.close();
    }
}

fn getrandom_tag(tag: &mut [u8; 4]) {
    use rand_core::{OsRng, RngCore};
    OsRng.fill_bytes(tag);
}

fn send_congestion(shared: &Shared, word_0: u16, received: u16, lost: u16) -> Result<(), SendError> {
    let mut send = shared.send.lock().unwrap();
    let key_pos = advance(&mut send, takion::CONGESTION_PACKET_SIZE);
    let mut packet = takion::congestion_packet(word_0, received, lost, key_pos);
    takion::packet_mac(send.crypt.as_mut(), &mut packet, key_pos).expect("a congestion packet");
    shared.sock.send(&packet).map(|_| ()).map_err(SendError::Io)
}

/// The reference's congestion control thread: every 200 ms the packets received and lost since the last report.
fn report_congestion(shared: Arc<Shared>, packet_loss_max: f64) {
    let mut next = Instant::now() + CONGESTION_INTERVAL;
    while !shared.stop.load(Ordering::Relaxed) {
        let now = Instant::now();
        if now < next {
            std::thread::sleep((next - now).min(STOP_CHECK));
            continue;
        }
        let (received, lost) = shared.packet_stats.lock().unwrap().take();
        let (received, lost) = frame::congestion_report(received, lost, packet_loss_max);
        if send_congestion(&shared, 0, received, lost).is_ok() {
            shared.stats.lock().unwrap().congestion_reports += 1;
        }
        next = Instant::now() + CONGESTION_INTERVAL;
    }
}

/// The reference's feedback sender thread: waits until the controller changes or a packet is due, then sends what
/// feedback::Sender says. Nothing goes out without the stream keys.
fn send_feedback(shared: Arc<Shared>, feedback: Arc<(Mutex<Feedback>, Condvar)>) {
    let (lock, cond) = &*feedback;
    let mut state = lock.lock().unwrap();
    while let Some(sender) = state.sender.as_ref() {
        if !state.stop && !state.ready() {
            let now = Instant::now();
            let wait = state.second.as_ref().map_or(sender.wait(now), |second| sender.wait(now).min(second.wait(now)));
            state = cond.wait_timeout_while(state, wait, |f| !f.stop && !f.ready()).unwrap().0;
        }
        if state.stop {
            break;
        }
        let now = Instant::now();
        let mut packets = state.sender.as_mut().map(|s| s.step(now)).unwrap_or_default();
        if let Some(second) = state.second.as_mut() {
            packets.extend(second.step(now));
        }
        drop(state);
        for mut packet in packets {
            let is_state = packet[0] == takion::PACKET_FEEDBACK_STATE;
            let sent = {
                let mut send = shared.send.lock().unwrap();
                if send.crypt.is_none() {
                    false
                } else {
                    let key_pos = advance(&mut send, feedback::key_pos_size(&packet));
                    feedback::seal(send.crypt.as_mut().unwrap(), &mut packet, key_pos);
                    shared.sock.send(&packet).is_ok()
                }
            };
            if sent {
                let mut stats = shared.stats.lock().unwrap();
                if is_state {
                    stats.feedback_states += 1;
                } else {
                    stats.feedback_history += 1;
                }
            }
        }
        state = lock.lock().unwrap();
    }
}

fn send_ack(shared: &Shared, send: &mut SendState, seq_num: u32) {
    let key_pos = advance(send, DATA_ACK_PACKET_SIZE);
    let mut packet = takion::data_ack_packet(shared.tag_remote, key_pos, seq_num, A_RWND);
    takion::packet_mac(send.crypt.as_mut(), &mut packet, key_pos).expect("a control packet");
    let _ = shared.sock.send(&packet);
}

/// The local key position for data_size bytes (0 while there is no crypto).
fn advance(send: &mut SendState, data_size: usize) -> u64 {
    if send.crypt.is_none() {
        return 0;
    }
    let key_pos = send.key_pos;
    send.key_pos += takion::key_pos_advance(data_size);
    key_pos
}

struct DataEntry {
    packet: Vec<u8>,
    channel: u16,
    data_type: u8,
    data_at: usize,
}

struct VideoEntry {
    packet: AvPacket,
    data: Vec<u8>,
}

struct Receiving {
    shared: Arc<Shared>,
    events: Sender<Event>,
    key_state: KeyState,
    data_queue: ReorderQueue<DataEntry>,
    video_queue: Option<ReorderQueue<VideoEntry>>,
    video_wait: Option<(Instant, u64)>,             // when the missing head started, and its number
    postponed: Vec<Vec<u8>>,
    crypt_seen: bool,
}

impl Receiving {
    fn new(shared: Arc<Shared>, events: Sender<Event>) -> Self {
        // The reference starts the data queue at the console's tag (not its initial sequence number).
        let data_queue = ReorderQueue::new(DATA_QUEUE_SIZE_EXP, Bits::B32, shared.tag_remote as u64, DropStrategy::End);
        Self {
            shared,
            events,
            key_state: KeyState::new(),
            data_queue,
            video_queue: None,
            video_wait: None,
            postponed: Vec::new(),
            crypt_seen: false,
        }
    }

    fn stat(&self, update: impl FnOnce(&mut Stats)) {
        update(&mut self.shared.stats.lock().unwrap());
    }

    fn emit(&self, event: Event) {
        let _ = self.events.send(event);
    }

    fn run(mut self) {
        let mut buf = [0u8; RECEIVE_SIZE];
        let reason = loop {
            if self.shared.stop.load(Ordering::Relaxed) {
                break "closed".to_string();
            }
            if !self.crypt_seen && self.shared.crypt_remote.lock().unwrap().is_some() {
                self.crypt_seen = true;
                self.crypt_arrived();
            }
            let mut timeout = RESEND_WAKEUP;
            if let Some((started, _)) = self.video_wait {
                timeout = timeout.min(VIDEO_REORDER_TIMEOUT.saturating_sub(started.elapsed()));
            }
            let _ = self.shared.sock.set_read_timeout(Some(timeout.max(Duration::from_millis(1))));
            match self.shared.sock.recv(&mut buf) {
                Ok(0) => {}
                Ok(size) => self.handle_packet(buf[..size].to_vec()),
                Err(error) if is_timeout(&error) => {}
                Err(error) => break format!("the stream connection failed: {error}"),
            }
            self.flush_video();
            self.resend();
        };
        self.emit(Event::Closed(reason));
    }

    /// The crypto is there: the data messages waiting for a gap are checked now, and held video and audio go on.
    fn crypt_arrived(&mut self) {
        {
            let mut guard = self.shared.crypt_remote.lock().unwrap();
            let crypt = guard.as_mut().unwrap();
            for i in 0..self.data_queue.count() {
                let Some(entry) = self.data_queue.peek(i) else { continue };
                let mut packet = entry.packet.clone();
                if takion::verify_packet(Some(&mut *crypt), &mut self.key_state, &mut packet).is_err() {
                    self.data_queue.drop_at(i);
                    self.shared.stats.lock().unwrap().mac_mismatch += 1;
                }
            }
        }
        for packet in std::mem::take(&mut self.postponed) {
            self.handle_packet(packet);
        }
    }

    fn handle_packet(&mut self, mut packet: Vec<u8>) {
        self.stat(|s| s.received += 1);
        let base_type = packet[0] & BASE_TYPE_MASK;
        let has_crypt = {
            let mut crypt = self.shared.crypt_remote.lock().unwrap();
            match takion::verify_packet(crypt.as_mut(), &mut self.key_state, &mut packet) {
                Ok(_) => crypt.is_some(),
                Err(TakionError::MacMismatch) => return self.stat(|s| s.mac_mismatch += 1),
                Err(_) => return self.stat(|s| s.invalid += 1),
            }
        };
        match base_type {
            PACKET_CONTROL => self.handle_message(packet),
            PACKET_VIDEO | PACKET_AUDIO if !has_crypt && self.shared.crypt_expected => {
                if self.postponed.len() < POSTPONE_MAX {
                    self.postponed.push(packet);
                }
            }
            PACKET_VIDEO | PACKET_AUDIO => self.handle_av(packet),
            _ => self.stat(|s| s.invalid += 1),
        }
    }

    fn handle_message(&mut self, packet: Vec<u8>) {
        let Ok(message) = takion::parse_message(&packet[1..], self.shared.tag_local, &mut self.key_state) else {
            return self.stat(|s| s.invalid += 1);
        };
        match message.chunk_type {
            CHUNK_DATA => {
                let Ok(data) = takion::parse_data(&message) else { return self.stat(|s| s.invalid += 1) };
                let (seq_num, channel, data_type) = (data.seq_num, data.channel, data.data_type);
                let data_at = 1 + MESSAGE_HEADER_SIZE + 9;
                let before = self.data_queue.dropped();
                self.data_queue.push(seq_num as u64, DataEntry { packet, channel, data_type, data_at });
                let dropped = self.data_queue.dropped() - before;
                self.stat(|s| s.data_dropped += dropped);
                self.flush_data();
            }
            CHUNK_DATA_ACK => {
                let Ok((seq_num, _a_rwnd)) = takion::parse_data_ack(&message) else {
                    return self.stat(|s| s.invalid += 1);
                };
                let acked = self.shared.send.lock().unwrap().buffer.ack(seq_num);
                for seq_num in acked {
                    self.emit(Event::DataAck(seq_num));
                }
            }
            _ => self.stat(|s| s.invalid += 1),
        }
    }

    /// Hands out the data messages that are in order and acknowledges the last one.
    fn flush_data(&mut self) {
        let mut last = None;
        while let Some((seq_num, entry)) = self.data_queue.pull() {
            last = Some(seq_num as u32);
            if matches!(entry.data_type, DATA_TYPE_PROTOBUF | DATA_TYPE_RUMBLE | DATA_TYPE_PAD_INFO | DATA_TYPE_TRIGGER_EFFECTS) {
                let data = entry.packet[entry.data_at..].to_vec();
                self.emit(Event::Data { data_type: entry.data_type, channel: entry.channel, data });
            }
        }
        if let Some(seq_num) = last {
            let mut send = self.shared.send.lock().unwrap();
            if send.crypt.is_some() {
                send_ack(&self.shared, &mut send, seq_num);
            } else {
                let since = send.pending_ack.map_or_else(Instant::now, |(_, since)| since);
                send.pending_ack = Some((seq_num, since));
            }
        }
    }

    fn handle_av(&mut self, packet: Vec<u8>) {
        let Ok(av) = takion::parse_av(self.shared.version, &packet, &mut self.key_state) else {
            return self.stat(|s| s.invalid += 1);
        };
        let mut data = packet[av.data_offset..].to_vec();
        if let Some(crypt) = self.shared.crypt_remote.lock().unwrap().as_ref() {
            crypt.crypt(av.key_pos + BLOCK_SIZE as u64, &mut data);
        }
        if !av.is_video {
            return self.emit(Event::Av { packet: av, data });
        }
        if self.simulated_loss() {
            return self.stat(|s| s.video_simulated_lost += 1);
        }
        self.video_queue.get_or_insert_with(|| {
            let begin = av.packet_index.wrapping_sub(av.unit_index);
            ReorderQueue::new(VIDEO_QUEUE_SIZE_EXP, Bits::B16, begin as u64, DropStrategy::Begin)
        });
        let index = av.packet_index as u64;
        if self.video_wait.is_some_and(|(_, head)| head == index) {
            self.stat(|s| s.video_late += 1);
        }
        let queue = self.video_queue.as_mut().expect("made just above");
        let before = queue.dropped();
        queue.push(index, VideoEntry { packet: av, data });
        let dropped = queue.dropped() - before;
        self.stat(|s| s.video_dropped += dropped);
        self.flush_video();
    }

    /// Whether the simulated loss drops this video packet (xorshift64 random numbers).
    fn simulated_loss(&self) -> bool {
        let share = self.shared.video_loss.load(Ordering::Relaxed);
        if share == 0 {
            return false;
        }
        let mut x = self.shared.loss_random.load(Ordering::Relaxed);
        x ^= x << 13;
        x ^= x >> 7;
        x ^= x << 17;
        self.shared.loss_random.store(x, Ordering::Relaxed);
        (x % 10000) < share as u64
    }

    /// Hands out the video packets in order. A missing packet is waited for up to about a frame; then the queue
    /// skips to the next packet it has.
    fn flush_video(&mut self) {
        let Some(queue) = self.video_queue.as_mut() else { return };
        let mut out = Vec::new();
        let mut skipped_total = 0;
        loop {
            let mut progress = false;
            while let Some((_, entry)) = queue.pull() {
                out.push(entry);
                progress = true;
            }
            if progress {
                self.video_wait = None;
            }
            if queue.count() == 0 {
                break;
            }
            let now = Instant::now();
            match self.video_wait {
                Some((started, head)) if queue.begin() != head => {
                    if Bits::B16.gt(queue.begin(), head) {
                        self.video_wait = Some((started, queue.begin()));      // the same loss burst
                    } else {
                        self.video_wait = Some((now, queue.begin()));
                        break;
                    }
                }
                None => {
                    self.video_wait = Some((now, queue.begin()));
                    break;
                }
                _ => {}
            }
            let (started, _) = self.video_wait.unwrap();
            if now.duration_since(started) <= VIDEO_REORDER_TIMEOUT {
                break;
            }
            let skipped = queue.skip_to_first();
            if skipped == 0 {
                break;
            }
            skipped_total += skipped;
            self.video_wait = None;
        }
        if skipped_total > 0 {
            self.stat(|s| s.video_skipped += skipped_total);
        }
        for entry in out {
            self.emit(Event::Av { packet: entry.packet, data: entry.data });
        }
    }

    fn resend(&self) {
        let due = {
            let mut send = self.shared.send.lock().unwrap();
            if let Some((seq_num, since)) = send.pending_ack {
                if since.elapsed() >= ACK_WAIT_FOR_CRYPT {
                    send.pending_ack = None;
                    send_ack(&self.shared, &mut send, seq_num);       // no keys came: unsigned, as before BANG
                }
            }
            if send.buffer.is_empty() {
                return;
            }
            send.buffer.due(Instant::now())
        };
        for packet in &due.resend {
            let _ = self.shared.sock.send(packet);
        }
        let (resent, given_up) = (due.resend.len() as u64, due.given_up.len() as u64);
        if resent + given_up > 0 {
            self.stat(|s| {
                s.resent += resent;
                s.given_up += given_up;
            });
        }
    }
}

#[cfg(test)]
mod tests {
    //! Against a fake console on localhost that speaks Takion with the packet functions of takion.rs.
    use super::*;
    use crate::ecdh::Ecdh;
    use crate::takion::{message_packet, parse_message, CHUNK_COOKIE, CHUNK_INIT};

    const TAG_CONSOLE: u32 = 0xc0ffee;

    struct Console {
        sock: UdpSocket,
        peer: Option<SocketAddr>,
        tag_client: u32,
        key_state: KeyState,
    }

    impl Console {
        fn new() -> Self {
            let sock = UdpSocket::bind("127.0.0.1:0").unwrap();
            sock.set_read_timeout(Some(Duration::from_secs(2))).unwrap();
            Self { sock, peer: None, tag_client: 0, key_state: KeyState::new() }
        }

        fn addr(&self) -> SocketAddr {
            self.sock.local_addr().unwrap()
        }

        fn recv(&mut self) -> Vec<u8> {
            let mut buf = [0u8; 2048];
            let (size, peer) = self.sock.recv_from(&mut buf).unwrap();
            self.peer = Some(peer);
            buf[..size].to_vec()
        }

        fn send(&self, packet: &[u8]) {
            self.sock.send_to(packet, self.peer.unwrap()).unwrap();
        }

        fn init_ack(&self) -> Vec<u8> {
            let mut payload = TAG_CONSOLE.to_be_bytes().to_vec();
            payload.extend_from_slice(&A_RWND.to_be_bytes());
            payload.extend_from_slice(&[0, 0x64, 0, 0x64]);
            payload.extend_from_slice(&TAG_CONSOLE.to_be_bytes());
            payload.extend_from_slice(&[0xab; 32]);
            message_packet(self.tag_client, 0, CHUNK_INIT_ACK, 0, &payload)
        }

        /// Answers INIT (after ignoring `lose_inits` of them) and COOKIE.
        fn accept(&mut self, lose_inits: usize) {
            for _ in 0..=lose_inits {
                let init = self.recv();
                let message = parse_message(&init[1..], 0, &mut KeyState::new()).unwrap();
                assert_eq!(message.chunk_type, CHUNK_INIT);
                self.tag_client = u32::from_be_bytes(message.payload[..4].try_into().unwrap());
            }
            self.send(&self.init_ack());
            let cookie = self.recv();
            let message = parse_message(&cookie[1..], TAG_CONSOLE, &mut KeyState::new()).unwrap();
            assert_eq!((message.chunk_type, message.payload), (CHUNK_COOKIE, &[0xab; 32][..]));
            self.send(&self.init_ack());                    // a repeated INIT_ACK first: skipped
            self.send(&message_packet(self.tag_client, 0, CHUNK_COOKIE_ACK, 0, &[]));
        }

        fn data(&self, seq_num: u32, data: &[u8], crypt: Option<&mut GkCrypt>, key_pos: u64) -> Vec<u8> {
            let mut packet = takion::data_packet(self.tag_client, key_pos, 1, seq_num, 1, data);
            takion::packet_mac(crypt, &mut packet, key_pos).unwrap();
            packet
        }

        fn recv_message(&mut self) -> (u8, Vec<u8>) {
            let packet = self.recv();
            let message = parse_message(&packet[1..], TAG_CONSOLE, &mut self.key_state).unwrap();
            (message.chunk_type, message.payload.to_vec())
        }
    }

    fn connect(console: &mut Console, lose_inits: usize) -> Connection {
        connect_version(console, lose_inits, 12, true)
    }

    fn connect_version(console: &mut Console, lose_inits: usize, version: u8, crypt: bool) -> Connection {
        let addr = console.addr();
        let connecting =
            std::thread::spawn(move || Connection::connect(addr, version, crypt, Duration::from_millis(300), 3));
        console.accept(lose_inits);
        connecting.join().unwrap().unwrap()
    }

    fn next(connection: &Connection) -> Event {
        connection.next_event(Duration::from_secs(2)).expect("an event")
    }

    #[test]
    fn handshake_with_a_lost_init_then_data_in_order() {
        let mut console = Console::new();
        let connection = connect(&mut console, 1);
        assert_eq!((connection.tag_remote(), connection.tag_local()), (TAG_CONSOLE, console.tag_client));

        // Out of order: the second message waits for the first, then both come and one ack covers them.
        console.send(&console.data(TAG_CONSOLE + 1, b"second", None, 0));
        console.send(&console.data(TAG_CONSOLE, b"first", None, 0));
        assert_eq!(next(&connection), Event::Data { data_type: 0, channel: 1, data: b"first".to_vec() });
        assert_eq!(next(&connection), Event::Data { data_type: 0, channel: 1, data: b"second".to_vec() });
        let (chunk, payload) = console.recv_message();
        assert_eq!((chunk, &payload[..4]), (CHUNK_DATA_ACK, &(TAG_CONSOLE + 1).to_be_bytes()[..]));

        // Ours: resent until acknowledged, then a DataAck event.
        let seq = connection.send_data(1, 1, b"hello", false).unwrap();
        assert_eq!(seq, console.tag_client);
        let (first, resent) = (console.recv(), console.recv());
        assert_eq!(first, resent);
        console.send(&message_packet(console.tag_client, 0, CHUNK_DATA_ACK, 0,
                                     &[&seq.to_be_bytes()[..], &A_RWND.to_be_bytes(), &[0; 4]].concat()));
        assert_eq!(next(&connection), Event::DataAck(seq));
        assert!(connection.stats().resent >= 1);
        connection.close();
        assert_eq!(next(&connection), Event::Closed("closed".into()));
    }

    #[test]
    fn network_test_gets_av_without_keys() {
        let mut console = Console::new();
        let connection = connect_version(&mut console, 0, 7, false);
        let pong = AvPacket { codec: 0xff, unit_index: 2, units_in_frame_total: 0x800, ..Default::default() };
        let mut packet = takion::v7_av_header(&pong);
        packet.extend_from_slice(&[0, 0, 0, 0, 0xde, 0xad, 0xbe, 0xef]);
        console.send(&packet);
        match next(&connection) {
            Event::Av { packet, data } => {
                assert_eq!((packet.is_video, packet.unit_index, packet.codec), (false, 2, 0xff));
                assert_eq!(data, [0, 0, 0, 0, 0xde, 0xad, 0xbe, 0xef]);
            }
            other => panic!("{other:?}"),
        }
        connection.send_raw(&packet).unwrap();
        assert_eq!(console.recv(), packet);
    }

    #[test]
    fn stream_assembles_frames_and_reports_congestion() {
        let mut console = Console::new();
        let connection = connect_version(&mut console, 0, 7, false);
        connection.start_stream(&[Vec::new()], false, PACKET_LOSS_MAX).unwrap();
        let frame: Vec<u8> = (0..2500u32).map(|i| (i * 13) as u8).collect();
        let units = crate::frame::tests::units(&frame, 1000, 1);
        for (i, unit) in units.iter().enumerate().filter(|(i, _)| *i != 1) {     // unit 1 lost: FEC rebuilds it
            let header = AvPacket {
                is_video: true, packet_index: i as u16, frame_index: 1, unit_index: i as u16,
                units_in_frame_total: units.len() as u16, units_in_frame_fec: 1, ..Default::default()
            };
            console.send(&[takion::v7_av_header(&header), unit.clone()].concat());
        }
        // Audio: Opus frames of 3 bytes, one per packet (version 7 has 10 bits for the units: 3 << 8 | 1 fits).
        for index in 1..=3u16 {
            let audio = AvPacket {
                frame_index: index, codec: crate::audio::CODEC_OPUS, units_in_frame_total: 1,
                units_in_frame_fec: 3 << 8 | 1, ..Default::default()
            };
            console.send(&[takion::v7_av_header(&audio), vec![index as u8; 3]].concat());
        }

        let mut events: Vec<Event> = (0..5).map(|_| next(&connection)).collect();
        events.sort_by_key(|e| !matches!(e, Event::Video(_)));
        assert_eq!(events[0], Event::Video(VideoEvent::Profile(0)));
        assert_eq!(events[1], Event::Video(VideoEvent::Frame { index: 1, data: frame, fec: true, frames_lost: 0 }));
        let audio: Vec<_> = events[2..].iter().map(|e| match e {
            Event::Audio(frame) => (frame.index, frame.data.clone()),
            other => panic!("{other:?}"),
        }).collect();
        assert_eq!(audio, [(1, Some(vec![1; 3])), (2, Some(vec![2; 3])), (3, Some(vec![3; 3]))]);
        assert_eq!(connection.audio_stats().unwrap().frames, 3);
        assert_eq!(connection.video_stats().unwrap().fec_recovered, 1);

        let report = console.recv();
        assert_eq!((report[0], report.len()), (takion::PACKET_CONGESTION, takion::CONGESTION_PACKET_SIZE));
        connection.close();
        assert!(connection.stats().congestion_reports >= 1);
    }

    #[test]
    fn no_console_times_out() {
        let silent = UdpSocket::bind("127.0.0.1:0").unwrap();
        let error = Connection::connect(silent.local_addr().unwrap(), 12, true, Duration::from_millis(50), 2).err().unwrap();
        assert!(matches!(error, ConnectError::Timeout(_)), "{error}");
    }

    #[test]
    fn crypto_signs_checks_and_releases_held_video() {
        let mut console = Console::new();
        let connection = connect(&mut console, 0);
        let key = [7u8; 16];
        let secret = Ecdh::generate().derive_secret(&Ecdh::generate().public_key()).unwrap();
        let mut console_crypt = GkCrypt::new(3, &key, &secret);         // the console's sending side
        let mut client_crypt = GkCrypt::new(2, &key, &secret);

        // A video packet before the key exchange is held back.
        let mut video = vec![0u8; 0x20];
        video[0] = PACKET_VIDEO;
        video[1..3].copy_from_slice(&5u16.to_be_bytes());
        let key_pos = 0x40u64;
        video[0xe..0x12].copy_from_slice(&(key_pos as u32).to_be_bytes());
        let offset = takion::parse_av(12, &video, &mut KeyState::new()).unwrap().data_offset;
        let plain: Vec<u8> = (0..video.len() - offset).map(|i| i as u8).collect();
        let mut encrypted = plain.clone();
        console_crypt.crypt(key_pos + 16, &mut encrypted);
        video[offset..].copy_from_slice(&encrypted);
        takion::packet_mac(Some(&mut console_crypt), &mut video, key_pos).unwrap();
        console.send(&video);
        // BANG: unsigned, and its acknowledgement waits for the keys.
        console.send(&console.data(TAG_CONSOLE, b"bang", None, 0));
        assert_eq!(next(&connection), Event::Data { data_type: 0, channel: 1, data: b"bang".to_vec() });
        assert_eq!(connection.next_event(Duration::from_millis(50)), None);

        connection.set_crypt(&key, &secret);
        // The acknowledgement goes out signed with index 2, as the first packet at key position 0.
        let mut ack = console.recv();
        assert_eq!(takion::verify_packet(Some(&mut client_crypt), &mut KeyState::new(), &mut ack), Ok(0));
        let (chunk, payload) = (ack[0xd], &ack[0x11..0x15]);
        assert_eq!((chunk, payload), (CHUNK_DATA_ACK, &TAG_CONSOLE.to_be_bytes()[..]));

        // A signed DATA message passes; one with a wrong MAC is dropped. The video comes out decrypted.
        let mut bad = console.data(TAG_CONSOLE + 1, b"forged", Some(&mut console_crypt), 0x100);
        bad[1] ^= 1;
        console.send(&bad);
        console.send(&console.data(TAG_CONSOLE + 1, b"signed", Some(&mut console_crypt), 0x100));
        let mut events = [next(&connection), next(&connection)];
        events.sort_by_key(|e| matches!(e, Event::Data { .. }));
        match &events[0] {
            Event::Av { packet, data } => assert_eq!((packet.packet_index, data), (5, &plain)),
            other => panic!("{other:?}"),
        }
        assert_eq!(events[1], Event::Data { data_type: 0, channel: 1, data: b"signed".to_vec() });
        assert_eq!(connection.stats().mac_mismatch, 1);

        // Each acknowledgement moves the key position by its packet size (29) plus 29 % 16, as in the reference.
        console.recv();                                     // the DATA_ACK, at 42
        let seq = connection.send_data(1, 1, b"big", false).unwrap();
        let mut packet = console.recv();
        assert_eq!(takion::verify_packet(Some(&mut client_crypt), &mut KeyState::new(), &mut packet), Ok(84));
        let message = parse_message(&packet[1..], TAG_CONSOLE, &mut KeyState::new()).unwrap();
        assert_eq!(takion::parse_data(&message).unwrap().seq_num, seq);
    }
}
