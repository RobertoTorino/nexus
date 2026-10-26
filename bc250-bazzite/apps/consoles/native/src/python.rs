// SPDX-License-Identifier: AGPL-3.0-or-later
//! The Python module bc250_console_link_core: thin wrappers over the Rust modules. Byte strings in and out; a
//! protocol error is a ValueError with the error's name.

use std::net::{SocketAddr, ToSocketAddrs};
use std::time::Duration;

use pyo3::exceptions::{PyConnectionError, PyOSError, PyTimeoutError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict, PyTuple};
use pyo3::IntoPyObjectExt;

use crate::connection::{self, ConnectError, Event, PlayerExperiment};
use crate::ecdh;
use crate::fec;
use crate::feedback;
use crate::gkcrypt;
use crate::keystate;
use crate::orientation;
use crate::takion::{self, Message, TakionError};
use crate::video::VideoEvent;

fn error(err: TakionError) -> PyErr {
    PyValueError::new_err(format!("{err:?}"))
}

fn array<const N: usize>(data: &[u8], what: &str) -> PyResult<[u8; N]> {
    data.try_into().map_err(|_| PyValueError::new_err(format!("{what} must have {N} bytes")))
}

fn bytes<'py>(py: Python<'py>, data: &[u8]) -> Bound<'py, PyBytes> {
    PyBytes::new(py, data)
}

#[pyclass(name = "GkCrypt", module = "bc250_console_link_core")]
struct GkCrypt(gkcrypt::GkCrypt);

#[pymethods]
impl GkCrypt {
    #[new]
    fn new(index: u8, handshake_key: &[u8], ecdh_secret: &[u8]) -> PyResult<Self> {
        Ok(Self(gkcrypt::GkCrypt::new(index, &array(handshake_key, "handshake_key")?, &array(ecdh_secret, "ecdh_secret")?)))
    }

    #[getter]
    fn index(&self) -> u8 {
        self.0.index
    }

    #[getter]
    fn key_base<'py>(&self, py: Python<'py>) -> Bound<'py, PyBytes> {
        bytes(py, &self.0.key_base)
    }

    #[getter]
    fn iv<'py>(&self, py: Python<'py>) -> Bound<'py, PyBytes> {
        bytes(py, &self.0.iv)
    }

    #[getter]
    fn key_gmac_base<'py>(&self, py: Python<'py>) -> Bound<'py, PyBytes> {
        bytes(py, &self.0.key_gmac_base)
    }

    fn key_stream<'py>(&self, py: Python<'py>, key_pos: u64, size: usize) -> Bound<'py, PyBytes> {
        bytes(py, &self.0.key_stream(key_pos, size))
    }

    /// Encrypts or decrypts data that sits at key_pos in the stream.
    fn crypt<'py>(&self, py: Python<'py>, key_pos: u64, data: &[u8]) -> Bound<'py, PyBytes> {
        let mut out = data.to_vec();
        self.0.crypt(key_pos, &mut out);
        bytes(py, &out)
    }

    fn gmac<'py>(&mut self, py: Python<'py>, key_pos: u64, data: &[u8]) -> Bound<'py, PyBytes> {
        bytes(py, &self.0.gmac(key_pos, data))
    }
}

#[pyclass(name = "Ecdh", module = "bc250_console_link_core")]
struct Ecdh(ecdh::Ecdh);

#[pymethods]
impl Ecdh {
    /// A new key pair, or the one of private_key (32 bytes).
    #[new]
    #[pyo3(signature = (private_key=None))]
    fn new(private_key: Option<&[u8]>) -> PyResult<Self> {
        match private_key {
            None => Ok(Self(ecdh::Ecdh::generate())),
            Some(key) => ecdh::Ecdh::from_private(key)
                .map(Self)
                .map_err(|_| PyValueError::new_err("not a secp256k1 private key")),
        }
    }

    fn public_key<'py>(&self, py: Python<'py>) -> Bound<'py, PyBytes> {
        bytes(py, &self.0.public_key())
    }

    fn signed_public_key<'py>(&self, py: Python<'py>, handshake_key: &[u8]) -> PyResult<(Bound<'py, PyBytes>, Bound<'py, PyBytes>)> {
        let (public, signature) = self.0.signed_public_key(&array(handshake_key, "handshake_key")?);
        Ok((bytes(py, &public), bytes(py, &signature)))
    }

    fn derive_secret<'py>(&self, py: Python<'py>, remote_public: &[u8]) -> PyResult<Bound<'py, PyBytes>> {
        self.0
            .derive_secret(remote_public)
            .map(|secret| bytes(py, &secret))
            .map_err(|_| PyValueError::new_err("not a secp256k1 public key"))
    }
}

#[pyfunction]
fn verify_signature(handshake_key: &[u8], public_key: &[u8], signature: &[u8]) -> PyResult<bool> {
    Ok(ecdh::verify(&array(handshake_key, "handshake_key")?, public_key, signature))
}

#[pyclass(name = "KeyState", module = "bc250_console_link_core")]
#[derive(Default)]
struct KeyState(keystate::KeyState);

#[pymethods]
impl KeyState {
    #[new]
    fn new() -> Self {
        Self::default()
    }

    #[pyo3(signature = (low, commit=true))]
    fn request_pos(&mut self, low: u32, commit: bool) -> u64 {
        self.0.request_pos(low, commit)
    }

    fn commit(&mut self, pos: u64) {
        self.0.commit(pos)
    }
}

/// The packet with its GMAC filled in, the GMAC, and the MAC field as it was before.
#[pyfunction]
#[pyo3(signature = (crypt, packet, key_pos))]
fn packet_mac<'py>(
    py: Python<'py>,
    crypt: Option<&mut GkCrypt>,
    packet: &[u8],
    key_pos: u64,
) -> PyResult<(Bound<'py, PyBytes>, Bound<'py, PyBytes>, Bound<'py, PyBytes>)> {
    let mut buf = packet.to_vec();
    let (mac, old) = takion::packet_mac(crypt.map(|c| &mut c.0), &mut buf, key_pos).map_err(error)?;
    Ok((bytes(py, &buf), bytes(py, &mac), bytes(py, &old)))
}

/// The key position of a received packet whose GMAC checks out; ValueError("MacMismatch") otherwise.
#[pyfunction]
fn verify_packet(crypt: Option<&mut GkCrypt>, key_state: &mut KeyState, packet: &[u8]) -> PyResult<u64> {
    let mut buf = packet.to_vec();
    takion::verify_packet(crypt.map(|c| &mut c.0), &mut key_state.0, &mut buf).map_err(error)
}

#[pyfunction]
fn key_pos_advance(data_size: usize) -> u64 {
    takion::key_pos_advance(data_size)
}

#[pyfunction]
fn parse_message<'py>(py: Python<'py>, buf: &[u8], tag_local: u32, key_state: &mut KeyState) -> PyResult<Bound<'py, PyDict>> {
    let message = takion::parse_message(buf, tag_local, &mut key_state.0).map_err(error)?;
    let dict = PyDict::new(py);
    dict.set_item("tag", message.tag)?;
    dict.set_item("key_pos", message.key_pos)?;
    dict.set_item("chunk_type", message.chunk_type)?;
    dict.set_item("chunk_flags", message.chunk_flags)?;
    dict.set_item("payload", bytes(py, message.payload))?;
    Ok(dict)
}

fn message(chunk_type: u8, payload: &[u8]) -> Message<'_> {
    Message { tag: 0, key_pos: 0, chunk_type, chunk_flags: 0, payload }
}

/// An INIT_ACK's payload: the console's tag, window, stream counts, initial sequence number and cookie.
#[pyfunction]
fn parse_init_ack<'py>(py: Python<'py>, payload: &[u8]) -> PyResult<Bound<'py, PyDict>> {
    let init = takion::parse_init_ack(&message(takion::CHUNK_INIT_ACK, payload)).map_err(error)?;
    let dict = PyDict::new(py);
    dict.set_item("tag", init.tag)?;
    dict.set_item("a_rwnd", init.a_rwnd)?;
    dict.set_item("outbound_streams", init.outbound_streams)?;
    dict.set_item("inbound_streams", init.inbound_streams)?;
    dict.set_item("initial_seq_num", init.initial_seq_num)?;
    dict.set_item("cookie", bytes(py, &init.cookie))?;
    Ok(dict)
}

#[pyfunction]
fn parse_data<'py>(py: Python<'py>, payload: &[u8]) -> PyResult<(u32, u16, u8, Bound<'py, PyBytes>)> {
    let data = takion::parse_data(&message(takion::CHUNK_DATA, payload)).map_err(error)?;
    Ok((data.seq_num, data.channel, data.data_type, bytes(py, data.data)))
}

#[pyfunction]
fn parse_data_ack(payload: &[u8]) -> PyResult<(u32, u32)> {
    takion::parse_data_ack(&message(takion::CHUNK_DATA_ACK, payload)).map_err(error)
}

#[pyfunction]
fn init_packet<'py>(py: Python<'py>, tag_local: u32, initial_seq_num: u32) -> Bound<'py, PyBytes> {
    bytes(py, &takion::init_packet(tag_local, initial_seq_num))
}

#[pyfunction]
fn cookie_packet<'py>(py: Python<'py>, tag_remote: u32, cookie: &[u8]) -> Bound<'py, PyBytes> {
    bytes(py, &takion::cookie_packet(tag_remote, cookie))
}

#[pyfunction]
fn message_packet<'py>(py: Python<'py>, tag: u32, key_pos: u64, chunk_type: u8, chunk_flags: u8, payload: &[u8]) -> Bound<'py, PyBytes> {
    bytes(py, &takion::message_packet(tag, key_pos, chunk_type, chunk_flags, payload))
}

#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn data_packet<'py>(py: Python<'py>, tag_remote: u32, key_pos: u64, chunk_flags: u8, seq_num: u32, channel: u16, data: &[u8]) -> Bound<'py, PyBytes> {
    bytes(py, &takion::data_packet(tag_remote, key_pos, chunk_flags, seq_num, channel, data))
}

#[pyfunction]
fn data_ack_packet<'py>(py: Python<'py>, tag_remote: u32, key_pos: u64, seq_num: u32, a_rwnd: u32) -> Bound<'py, PyBytes> {
    bytes(py, &takion::data_ack_packet(tag_remote, key_pos, seq_num, a_rwnd))
}

#[pyfunction]
fn congestion_packet<'py>(py: Python<'py>, word_0: u16, received: u16, lost: u16, key_pos: u64) -> Bound<'py, PyBytes> {
    bytes(py, &takion::congestion_packet(word_0, received, lost, key_pos))
}

fn av_dict<'py>(py: Python<'py>, av: &takion::AvPacket) -> PyResult<Bound<'py, PyDict>> {
    let dict = PyDict::new(py);
    dict.set_item("packet_index", av.packet_index)?;
    dict.set_item("frame_index", av.frame_index)?;
    dict.set_item("nalu", av.uses_nalu_info_structs)?;
    dict.set_item("video", av.is_video)?;
    dict.set_item("haptics", av.is_haptics)?;
    dict.set_item("unit_index", av.unit_index)?;
    dict.set_item("units_total", av.units_in_frame_total)?;
    dict.set_item("units_fec", av.units_in_frame_fec)?;
    dict.set_item("codec", av.codec)?;
    dict.set_item("word_at_0x18", av.word_at_0x18)?;
    dict.set_item("adaptive_stream_index", av.adaptive_stream_index)?;
    dict.set_item("byte_at_0x2c", av.byte_at_0x2c)?;
    dict.set_item("key_pos", av.key_pos)?;
    dict.set_item("data_offset", av.data_offset)?;
    Ok(dict)
}

/// A video or audio packet's header (Takion version 7, 9 or 12) as a dict; data_offset is where its data starts.
#[pyfunction]
fn parse_av<'py>(py: Python<'py>, version: u8, packet: &[u8], key_state: &mut KeyState) -> PyResult<Bound<'py, PyDict>> {
    let av = takion::parse_av(version, packet, &mut key_state.0).map_err(error)?;
    av_dict(py, &av)
}

/// A version 7 header (the network test's pings); the fields as parse_av names them.
#[pyfunction]
#[pyo3(signature = (*, video=false, nalu=false, packet_index=0, frame_index=0, unit_index=0, units_total=1,
                    units_fec=0, codec=0, key_pos=0, word_at_0x18=0, adaptive_stream_index=0))]
#[allow(clippy::too_many_arguments)]
fn v7_av_header<'py>(py: Python<'py>, video: bool, nalu: bool, packet_index: u16, frame_index: u16, unit_index: u16,
                     units_total: u16, units_fec: u16, codec: u8, key_pos: u64, word_at_0x18: u16,
                     adaptive_stream_index: u8) -> Bound<'py, PyBytes> {
    let packet = takion::AvPacket {
        is_video: video,
        uses_nalu_info_structs: nalu,
        packet_index,
        frame_index,
        unit_index,
        units_in_frame_total: units_total,
        units_in_frame_fec: units_fec,
        codec,
        key_pos,
        word_at_0x18,
        adaptive_stream_index,
        ..Default::default()
    };
    bytes(py, &takion::v7_av_header(&packet))
}

#[pyfunction]
fn data_cont_packet<'py>(py: Python<'py>, tag_remote: u32, key_pos: u64, chunk_flags: u8, seq_num: u32, channel: u16, data: &[u8]) -> Bound<'py, PyBytes> {
    bytes(py, &takion::data_cont_packet(tag_remote, key_pos, chunk_flags, seq_num, channel, data))
}

/// The m FEC units for k source units of unit_size bytes each, one after another in buf: buf with them added.
#[pyfunction]
fn fec_encode<'py>(py: Python<'py>, buf: &[u8], unit_size: usize, k: usize, m: usize) -> PyResult<Bound<'py, PyBytes>> {
    let mut units = buf.to_vec();
    units.resize(unit_size * (k + m), 0);
    fec::encode(&mut units, unit_size, unit_size, k, m).map_err(|e| PyValueError::new_err(format!("{e:?}")))?;
    Ok(bytes(py, &units))
}

/// The k source units rebuilt from k + m units of unit_size bytes, those at the indexes in erasures missing.
#[pyfunction]
fn fec_decode<'py>(py: Python<'py>, buf: &[u8], unit_size: usize, k: usize, m: usize, erasures: Vec<usize>)
    -> PyResult<Bound<'py, PyBytes>> {
    let mut units = buf.to_vec();
    fec::decode(&mut units, unit_size, unit_size, k, m, &erasures).map_err(|e| PyValueError::new_err(format!("{e:?}")))?;
    Ok(bytes(py, &units[..unit_size * k]))
}

fn resolve(host: &str, port: u16) -> PyResult<SocketAddr> {
    (host, port)
        .to_socket_addrs()
        .map_err(|e| PyOSError::new_err(format!("{host}: {e}")))?
        .next()
        .ok_or_else(|| PyOSError::new_err(format!("{host}: no address")))
}

/// One controller's motion (orientation.rs): update() with each gyro or accelerometer sample (rad/s, g, a 32-bit
/// microsecond clock); gyro, accel and orientation (x, y, z, w) are what set_controller_state takes.
#[pyclass(name = "OrientationTracker", module = "bc250_console_link_core")]
#[derive(Default)]
struct OrientationTracker(orientation::Tracker);

#[pymethods]
impl OrientationTracker {
    #[new]
    fn new() -> Self {
        Self::default()
    }

    #[pyo3(signature = (gyro, accel, timestamp_us, accel_zero=(0.0, 0.0, 0.0), accel_zero_applied=false))]
    fn update(&mut self, gyro: (f32, f32, f32), accel: (f32, f32, f32), timestamp_us: u32,
              accel_zero: (f32, f32, f32), accel_zero_applied: bool) {
        self.0.update([gyro.0, gyro.1, gyro.2], [accel.0, accel.1, accel.2],
                      [accel_zero.0, accel_zero.1, accel_zero.2], accel_zero_applied, timestamp_us);
    }

    #[getter]
    fn gyro(&self) -> (f32, f32, f32) {
        (self.0.gyro[0], self.0.gyro[1], self.0.gyro[2])
    }

    #[getter]
    fn accel(&self) -> (f32, f32, f32) {
        (self.0.accel[0], self.0.accel[1], self.0.accel[2])
    }

    #[getter]
    fn orientation(&self) -> (f32, f32, f32, f32) {
        let [x, y, z, w] = self.0.console_orientation();
        (x, y, z, w)
    }
}

/// A controller state from Python's arguments (Takion.set_controller_state).
#[allow(clippy::too_many_arguments)]
fn controller_state(buttons: u32, l2: u8, r2: u8, left: (i16, i16), right: (i16, i16), touches: Vec<(u8, u16, u16)>,
                    gyro: (f32, f32, f32), accel: (f32, f32, f32), orient: (f32, f32, f32, f32))
                    -> PyResult<feedback::ControllerState> {
    if touches.len() > feedback::TOUCHES_MAX {
        return Err(PyValueError::new_err("at most two touches"));
    }
    let mut state = feedback::ControllerState::idle();
    state.buttons = buttons & 0xffff;
    (state.l2, state.r2) = (l2, r2);
    (state.left_x, state.left_y, state.right_x, state.right_y) = (left.0, left.1, right.0, right.1);
    for (slot, (id, x, y)) in state.touches.iter_mut().zip(touches) {
        *slot = feedback::Touch { id: (id & 0x7f) as i8, x, y };
    }
    state.gyro = [gyro.0, gyro.1, gyro.2];
    state.accel = [accel.0, accel.1, accel.2];
    state.orient = [orient.0, orient.1, orient.2, orient.3];
    Ok(state)
}

/// A live Takion connection (connection.rs). The constructor connects and runs the handshake, without the GIL;
/// TimeoutError when the console does not answer, ConnectionError when it answers wrongly.
#[pyclass(name = "Takion", module = "bc250_console_link_core", frozen)]
struct Takion(connection::Connection);

#[pymethods]
impl Takion {
    #[new]
    #[pyo3(signature = (host, port=connection::PORT, version=12, timeout=5.0, tries=connection::CONNECT_TRIES, crypt=true))]
    fn new(py: Python<'_>, host: &str, port: u16, version: u8, timeout: f64, tries: u32, crypt: bool) -> PyResult<Self> {
        if ![7, 9, 12].contains(&version) {
            return Err(PyValueError::new_err("version is 7, 9 or 12"));
        }
        let addr = resolve(host, port)?;
        let timeout = Duration::from_secs_f64(timeout.max(0.001));
        py.detach(|| connection::Connection::connect(addr, version, crypt, timeout, tries))
            .map(Self)
            .map_err(|e| match e {
                ConnectError::Timeout(_) => PyTimeoutError::new_err(e.to_string()),
                ConnectError::Invalid(_) => PyConnectionError::new_err(e.to_string()),
                ConnectError::Io(_) => PyOSError::new_err(e.to_string()),
            })
    }

    #[getter]
    fn tag_local(&self) -> u32 {
        self.0.tag_local()
    }

    #[getter]
    fn tag_remote(&self) -> u32 {
        self.0.tag_remote()
    }

    #[getter]
    fn version(&self) -> u8 {
        self.0.version()
    }

    fn set_crypt(&self, handshake_key: &[u8], ecdh_secret: &[u8]) -> PyResult<()> {
        self.0.set_crypt(&array(handshake_key, "handshake_key")?, &array(ecdh_secret, "ecdh_secret")?);
        Ok(())
    }

    /// Sends a DATA message and returns its sequence number; cont=True continues the previous message.
    #[pyo3(signature = (data, channel=connection::CHANNEL_DEFAULT, flags=1, cont=false))]
    fn send_data(&self, data: &[u8], channel: u16, flags: u8, cont: bool) -> PyResult<u32> {
        self.0.send_data(flags, channel, data, cont).map_err(|e| PyOSError::new_err(e.to_string()))
    }

    /// A packet as it is, unsigned and not resent (the network test's pings).
    fn send_raw(&self, packet: &[u8]) -> PyResult<()> {
        self.0.send_raw(packet).map_err(|e| PyOSError::new_err(e.to_string()))
    }

    fn send_congestion(&self, word_0: u16, received: u16, lost: u16) -> PyResult<()> {
        self.0.send_congestion(word_0, received, lost).map_err(|e| PyOSError::new_err(e.to_string()))
    }

    /// The stream runs (after STREAMINFO, with each resolution's video header and whether the codec is HEVC): video
    /// comes as frames from now on, and congestion reports go every 200 ms.
    #[pyo3(signature = (headers, hevc=false, packet_loss_max=connection::PACKET_LOSS_MAX))]
    fn start_stream(&self, headers: Vec<Vec<u8>>, hevc: bool, packet_loss_max: f64) -> PyResult<()> {
        self.0.start_stream(&headers, hevc, packet_loss_max).map_err(|e| PyOSError::new_err(e.to_string()))
    }

    /// The controller as it is now: buttons as the reference numbers them (bit 0 cross ... bit 15 PS), L2 and R2 from
    /// 0 to 255, the sticks as (x, y) from -32768 to 32767, up to two fingers on the touchpad as (id, x, y), the gyro
    /// in rad/s, the accelerometer in g and the orientation as a quaternion (x, y, z, w). It goes to the console
    /// once the stream runs, at once when it changes and at least every 200 ms.
    #[pyo3(signature = (buttons=0, l2=0, r2=0, left=(0, 0), right=(0, 0), touches=Vec::new(), gyro=(0.0, 0.0, 0.0),
                        accel=(0.0, 1.0, 0.0), orient=(0.0, 0.0, 0.0, 1.0)))]
    #[allow(clippy::too_many_arguments)]
    fn set_controller_state(&self, buttons: u32, l2: u8, r2: u8, left: (i16, i16), right: (i16, i16),
                            touches: Vec<(u8, u16, u16)>, gyro: (f32, f32, f32), accel: (f32, f32, f32),
                            orient: (f32, f32, f32, f32)) -> PyResult<()> {
        let state = controller_state(buttons, l2, r2, left, right, touches, gyro, accel, orient)?;
        self.0.set_controller_state(state);
        Ok(())
    }

    /// For trying the recovery from lost packets (not for users): this share of the video packets, in percent, is
    /// dropped on arrival.
    fn set_simulated_loss(&self, percent: f64) {
        self.0.set_simulated_loss(percent);
    }

    /// The several-players experiment (not for users), before start_stream: "off", "announce", "marked" (the second
    /// controller in packets of its own, mark in the first byte) or "packed" (both states in one packet).
    #[pyo3(signature = (mode, mark=1))]
    fn set_player_experiment(&self, mode: &str, mark: u8) -> PyResult<()> {
        let players = match mode {
            "off" => PlayerExperiment::Off,
            "announce" => PlayerExperiment::Announce,
            "marked" => PlayerExperiment::Marked(mark),
            "packed" => PlayerExperiment::Packed,
            _ => return Err(PyValueError::new_err("mode is off, announce, marked or packed")),
        };
        self.0.set_player_experiment(players);
        Ok(())
    }

    /// The several-players experiment: the second controller, with set_controller_state's arguments.
    #[pyo3(signature = (buttons=0, l2=0, r2=0, left=(0, 0), right=(0, 0), touches=Vec::new(), gyro=(0.0, 0.0, 0.0),
                        accel=(0.0, 1.0, 0.0), orient=(0.0, 0.0, 0.0, 1.0)))]
    #[allow(clippy::too_many_arguments)]
    fn set_second_controller_state(&self, buttons: u32, l2: u8, r2: u8, left: (i16, i16), right: (i16, i16),
                                   touches: Vec<(u8, u16, u16)>, gyro: (f32, f32, f32), accel: (f32, f32, f32),
                                   orient: (f32, f32, f32, f32)) -> PyResult<()> {
        let state = controller_state(buttons, l2, r2, left, right, touches, gyro, accel, orient)?;
        self.0.set_second_controller_state(state);
        Ok(())
    }

    /// The audio receiver's counters once the stream runs, else None.
    fn audio_stats<'py>(&self, py: Python<'py>) -> PyResult<Option<Bound<'py, PyDict>>> {
        let Some(s) = self.0.audio_stats() else { return Ok(None) };
        let dict = PyDict::new(py);
        for (name, value) in [("packets", s.packets), ("frames", s.frames), ("lost", s.lost), ("refused", s.refused),
                              ("haptics", s.haptics)] {
            dict.set_item(name, value)?;
        }
        Ok(Some(dict))
    }

    /// The video receiver's counters once the stream runs, else None.
    fn video_stats<'py>(&self, py: Python<'py>) -> PyResult<Option<Bound<'py, PyDict>>> {
        let Some(s) = self.0.video_stats() else { return Ok(None) };
        let dict = PyDict::new(py);
        for (name, value) in [
            ("frames", s.frames), ("bytes", s.bytes), ("fec_recovered", s.fec_recovered), ("fec_failed", s.fec_failed),
            ("old_packets", s.old_packets), ("bad_profile", s.bad_profile), ("bad_units", s.bad_units),
            ("idr_requests", s.idr_requests), ("frames_skipped", s.frames_skipped),
            ("missing_reference", s.missing_reference), ("references_changed", s.references_changed),
        ] {
            dict.set_item(name, value)?;
        }
        dict.set_item("frames_lost", s.frames_lost)?;
        dict.set_item("references_untrusted", s.references_untrusted)?;
        Ok(Some(dict))
    }

    /// The next event or None after timeout seconds: ("data", data_type, channel, bytes), ("data_ack", seq_num),
    /// ("av", header dict, decrypted bytes) or ("closed", reason). Once the stream runs, "av" is audio only and
    /// video comes as ("frame", {"index", "fec", "frames_lost"}, bytes), ("profile", resolution index) and
    /// ("corrupt", first frame, last frame), the frames to report to the console, and ("idr",) when a key frame is to
    /// be asked for; audio comes as ("audio", index,
    /// Opus frame or None for a lost one).
    #[pyo3(signature = (timeout=0.0))]
    fn next_event<'py>(&self, py: Python<'py>, timeout: f64) -> PyResult<Option<Bound<'py, PyTuple>>> {
        let timeout = Duration::from_secs_f64(timeout.max(0.0));
        let Some(event) = py.detach(|| self.0.next_event(timeout)) else { return Ok(None) };
        let items: Vec<Py<PyAny>> = match event {
            Event::Data { data_type, channel, data } => vec![
                "data".into_py_any(py)?, data_type.into_py_any(py)?, channel.into_py_any(py)?, bytes(py, &data).into_py_any(py)?,
            ],
            Event::DataAck(seq_num) => vec!["data_ack".into_py_any(py)?, seq_num.into_py_any(py)?],
            Event::Av { packet, data } => vec!["av".into_py_any(py)?, av_dict(py, &packet)?.into_py_any(py)?, bytes(py, &data).into_py_any(py)?],
            Event::Closed(reason) => vec!["closed".into_py_any(py)?, reason.into_py_any(py)?],
            Event::Video(VideoEvent::Frame { index, data, fec, frames_lost }) => {
                let info = PyDict::new(py);
                info.set_item("index", index)?;
                info.set_item("fec", fec)?;
                info.set_item("frames_lost", frames_lost)?;
                vec!["frame".into_py_any(py)?, info.into_py_any(py)?, bytes(py, &data).into_py_any(py)?]
            }
            Event::Video(VideoEvent::Profile(index)) => vec!["profile".into_py_any(py)?, index.into_py_any(py)?],
            Event::Video(VideoEvent::Corrupt { start, end }) => {
                vec!["corrupt".into_py_any(py)?, start.into_py_any(py)?, end.into_py_any(py)?]
            }
            Event::Video(VideoEvent::RequestIdr) => vec!["idr".into_py_any(py)?],
            Event::Audio(frame) => vec![
                "audio".into_py_any(py)?, frame.index.into_py_any(py)?,
                frame.data.map(|data| bytes(py, &data)).into_py_any(py)?,
            ],
        };
        Ok(Some(PyTuple::new(py, items)?))
    }

    /// Counters: packets received, MAC mismatches, invalid packets, data and video dropped, video skipped after
    /// the reorder timeout, messages resent and given up, congestion reports, controller states and history packets
    /// sent.
    fn stats<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        let s = self.0.stats();
        let dict = PyDict::new(py);
        for (name, value) in [
            ("received", s.received), ("mac_mismatch", s.mac_mismatch), ("invalid", s.invalid),
            ("data_dropped", s.data_dropped), ("video_dropped", s.video_dropped), ("video_skipped", s.video_skipped),
            ("video_simulated_lost", s.video_simulated_lost), ("video_late", s.video_late),
            ("resent", s.resent), ("given_up", s.given_up), ("congestion_reports", s.congestion_reports),
            ("feedback_states", s.feedback_states), ("feedback_history", s.feedback_history),
        ] {
            dict.set_item(name, value)?;
        }
        Ok(dict)
    }

    fn close(&self, py: Python<'_>) {
        py.detach(|| self.0.close());
    }
}

/// The video decoder (decoder.rs): Decoder(codec="h264" or "hevc", hw=True, low_delay=False). decode(sample) gives the frames it
/// completed as dicts (width, height, hw); image() the last one's picture.
/// hw tells whether VA-API runs, hw_error why not when it was asked for.
#[cfg(feature = "decoder")]
#[pyclass(name = "Decoder", module = "bc250_console_link_core", unsendable)]
struct Decoder(crate::decoder::Decoder);

#[cfg(feature = "decoder")]
fn decode_error(e: crate::decoder::DecodeError) -> PyErr {
    PyValueError::new_err(e.message)
}

#[cfg(feature = "decoder")]
#[pymethods]
impl Decoder {
    #[new]
    #[pyo3(signature = (codec="h264", hw=true, low_delay=false))]
    fn new(codec: &str, hw: bool, low_delay: bool) -> PyResult<Self> {
        let hevc = match codec {
            "h264" => false,
            "h265" | "hevc" => true,
            _ => return Err(PyValueError::new_err("codec is h264 or hevc")),
        };
        crate::decoder::Decoder::new(hevc, hw, low_delay).map(Self).map_err(decode_error)
    }

    #[getter]
    fn hw(&self) -> bool {
        self.0.hw()
    }

    #[getter]
    fn hw_error(&self) -> Option<String> {
        self.0.hw_error.as_ref().map(|e| e.message.clone())
    }

    /// Decoding lets go of the GIL (a 1080p frame takes about 5 ms in software): the window, the sound output and
    /// the controller reader run meanwhile.
    fn decode<'py>(&mut self, py: Python<'py>, sample: &[u8]) -> PyResult<Vec<Bound<'py, PyDict>>> {
        let decoder = &mut self.0;
        let frames = py.detach(|| decoder.decode(sample)).map_err(decode_error)?;
        frames.into_iter().map(|frame| {
            let dict = PyDict::new(py);
            dict.set_item("width", frame.width)?;
            dict.set_item("height", frame.height)?;
            dict.set_item("hw", frame.hw)?;
            Ok(dict)
        }).collect()
    }

    /// The last frame's picture: a dict with format, width, height, colorspace (FFmpeg's numbers), full_range and
    /// data (the planes one after another).
    fn image<'py>(&mut self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        let decoder = &mut self.0;
        let image = py.detach(|| decoder.image()).map_err(decode_error)?;
        let dict = PyDict::new(py);
        dict.set_item("format", image.format)?;
        dict.set_item("width", image.width)?;
        dict.set_item("height", image.height)?;
        dict.set_item("colorspace", image.colorspace)?;
        dict.set_item("full_range", image.full_range)?;
        dict.set_item("data", bytes(py, &image.data))?;
        Ok(dict)
    }
}

/// The sound's decoder (decoder.rs): AudioDecoder(rate, channels, frame_size) from the stream's audio header;
/// decode(frame) gives 16-bit PCM, interleaved, as bytes (a frame of silence for None, a lost frame).
#[cfg(feature = "decoder")]
#[pyclass(name = "AudioDecoder", module = "bc250_console_link_core", unsendable)]
struct AudioDecoder(crate::decoder::AudioDecoder);

#[cfg(feature = "decoder")]
#[pymethods]
impl AudioDecoder {
    #[new]
    fn new(rate: u32, channels: u32, frame_size: u32) -> PyResult<Self> {
        crate::decoder::AudioDecoder::new(rate, channels, frame_size).map(Self).map_err(decode_error)
    }

    #[pyo3(signature = (frame=None))]
    fn decode<'py>(&mut self, py: Python<'py>, frame: Option<&[u8]>) -> PyResult<Bound<'py, PyBytes>> {
        let decoder = &mut self.0;
        let pcm = py.detach(|| decoder.decode(frame)).map_err(decode_error)?;
        let raw: Vec<u8> = pcm.iter().flat_map(|sample| sample.to_le_bytes()).collect();
        Ok(bytes(py, &raw))
    }
}

#[pymodule]
fn bc250_console_link_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add("DECODER", cfg!(feature = "decoder"))?;
    #[cfg(feature = "decoder")]
    {
        m.add_class::<Decoder>()?;
        m.add_class::<AudioDecoder>()?;
        m.add("FFMPEG_VERSION", crate::decoder::ffmpeg_version())?;
    }
    m.add_class::<GkCrypt>()?;
    m.add_class::<Ecdh>()?;
    m.add_class::<KeyState>()?;
    m.add_class::<OrientationTracker>()?;
    m.add_function(wrap_pyfunction!(verify_signature, m)?)?;
    m.add_function(wrap_pyfunction!(packet_mac, m)?)?;
    m.add_function(wrap_pyfunction!(verify_packet, m)?)?;
    m.add_function(wrap_pyfunction!(key_pos_advance, m)?)?;
    m.add_function(wrap_pyfunction!(parse_message, m)?)?;
    m.add_function(wrap_pyfunction!(parse_init_ack, m)?)?;
    m.add_function(wrap_pyfunction!(parse_data, m)?)?;
    m.add_function(wrap_pyfunction!(parse_data_ack, m)?)?;
    m.add_function(wrap_pyfunction!(init_packet, m)?)?;
    m.add_function(wrap_pyfunction!(cookie_packet, m)?)?;
    m.add_function(wrap_pyfunction!(message_packet, m)?)?;
    m.add_function(wrap_pyfunction!(data_packet, m)?)?;
    m.add_function(wrap_pyfunction!(data_ack_packet, m)?)?;
    m.add_function(wrap_pyfunction!(congestion_packet, m)?)?;
    m.add_function(wrap_pyfunction!(parse_av, m)?)?;
    m.add_function(wrap_pyfunction!(data_cont_packet, m)?)?;
    m.add_function(wrap_pyfunction!(v7_av_header, m)?)?;
    m.add_function(wrap_pyfunction!(fec_encode, m)?)?;
    m.add_function(wrap_pyfunction!(fec_decode, m)?)?;
    m.add_class::<Takion>()?;
    for (name, value) in [
        ("PACKET_CONTROL", takion::PACKET_CONTROL),
        ("PACKET_VIDEO", takion::PACKET_VIDEO),
        ("PACKET_AUDIO", takion::PACKET_AUDIO),
        ("PACKET_CONGESTION", takion::PACKET_CONGESTION),
        ("PACKET_FEEDBACK_HISTORY", takion::PACKET_FEEDBACK_HISTORY),
        ("PACKET_FEEDBACK_STATE", takion::PACKET_FEEDBACK_STATE),
        ("CHUNK_DATA", takion::CHUNK_DATA),
        ("CHUNK_INIT", takion::CHUNK_INIT),
        ("CHUNK_INIT_ACK", takion::CHUNK_INIT_ACK),
        ("CHUNK_DATA_ACK", takion::CHUNK_DATA_ACK),
        ("CHUNK_COOKIE", takion::CHUNK_COOKIE),
        ("CHUNK_COOKIE_ACK", takion::CHUNK_COOKIE_ACK),
    ] {
        m.add(name, value)?;
    }
    m.add("A_RWND", takion::A_RWND)?;
    m.add("PORT", connection::PORT)?;
    Ok(())
}
