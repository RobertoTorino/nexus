// SPDX-License-Identifier: AGPL-3.0-only
//! The controller's way to the console (the reference's feedback.c, feedbacksender.c, the controller state of
//! controller.c and the feedback packets of takion.c). Two kinds of packet, outside the DATA messages and never
//! acknowledged:
//!
//! - FEEDBACK_STATE: the sticks and the motion sensors, whenever they change and at least every 200 ms. The console
//!   expects it while the stream runs; without it a PS4 shows "Remote Play has paused".
//! - FEEDBACK_HISTORY: the buttons, triggers and touches as events, the newest first, the last eight repeated in
//!   every packet. Each new event gets a packet of its own (the console applies one new event per packet), and the
//!   newest packet goes again 20, 50, 100 and 200 ms later when nothing follows, so a lost release cannot leave a
//!   button held.
//!
//! The payload is encrypted with the local key stream 16 bytes after the packet's key position, and the whole packet
//! signed with its key position in place. One deliberate difference: a gyro or accelerometer value outside its range
//! is clamped; the reference casts it to 16 bits, which C leaves undefined.

use std::collections::VecDeque;
use std::time::{Duration, Instant};

use crate::gkcrypt::{GkCrypt, BLOCK_SIZE, GMAC_SIZE};
use crate::takion::{PACKET_FEEDBACK_HISTORY, PACKET_FEEDBACK_STATE};

pub const HEADER_SIZE: usize = 0xc;
pub const STATE_SIZE_V9: usize = 0x19;
pub const STATE_SIZE_V12: usize = 0x1c;
pub const TOUCHES_MAX: usize = 2;
const TOUCH_ID_MASK: u8 = 0x7f;
const GYRO_MIN: f32 = -30.0;
const GYRO_MAX: f32 = 30.0;
const ACCEL_MIN: f32 = -5.0;
const ACCEL_MAX: f32 = 5.0;
const KEY_POS_AT: usize = 4;
const MAC_AT: usize = 8;

const HISTORY_BUFFER_SIZE: usize = 0x10;
const HISTORY_RESEND_EVENT_COUNT: usize = 8;
const HISTORY_PACKET_QUEUE_SIZE: usize = 0x40;
pub const STATE_TIMEOUT_MAX: Duration = Duration::from_millis(200);
const HISTORY_TAIL: [Duration; 4] =
    [Duration::from_millis(20), Duration::from_millis(50), Duration::from_millis(100), Duration::from_millis(200)];

// The buttons as the reference numbers them (bit i of ControllerState::buttons); L2 and R2 are analog, bits 16 and 17
// only in a button event.
pub const BUTTON_CROSS: u32 = 1 << 0;
pub const BUTTON_MOON: u32 = 1 << 1;
pub const BUTTON_BOX: u32 = 1 << 2;
pub const BUTTON_PYRAMID: u32 = 1 << 3;
pub const BUTTON_DPAD_LEFT: u32 = 1 << 4;
pub const BUTTON_DPAD_RIGHT: u32 = 1 << 5;
pub const BUTTON_DPAD_UP: u32 = 1 << 6;
pub const BUTTON_DPAD_DOWN: u32 = 1 << 7;
pub const BUTTON_L1: u32 = 1 << 8;
pub const BUTTON_R1: u32 = 1 << 9;
pub const BUTTON_L3: u32 = 1 << 10;
pub const BUTTON_R3: u32 = 1 << 11;
pub const BUTTON_OPTIONS: u32 = 1 << 12;
pub const BUTTON_SHARE: u32 = 1 << 13;
pub const BUTTON_TOUCHPAD: u32 = 1 << 14;
pub const BUTTON_PS: u32 = 1 << 15;
pub const BUTTONS_COUNT: u32 = 16;
pub const ANALOG_L2: u32 = 1 << 16;
pub const ANALOG_R2: u32 = 1 << 17;

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Touch {
    pub x: u16,
    pub y: u16,
    pub id: i8,                                     // -1: no finger
}

/// What the controller does now (the reference's controller state, controller.h).
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct ControllerState {
    pub buttons: u32,
    pub l2: u8,
    pub r2: u8,
    pub left_x: i16,
    pub left_y: i16,
    pub right_x: i16,
    pub right_y: i16,
    pub touch_id_next: u8,
    pub touches: [Touch; TOUCHES_MAX],
    pub gyro: [f32; 3],
    pub accel: [f32; 3],
    pub orient: [f32; 4],                           // x, y, z, w
}

impl ControllerState {
    /// Nothing pressed, sticks centred, the controller lying still (gravity on y, no rotation).
    pub fn idle() -> Self {
        ControllerState {
            buttons: 0,
            l2: 0,
            r2: 0,
            left_x: 0,
            left_y: 0,
            right_x: 0,
            right_y: 0,
            touch_id_next: 0,
            touches: [Touch { x: 0, y: 0, id: -1 }; TOUCHES_MAX],
            gyro: [0.0; 3],
            accel: [0.0, 1.0, 0.0],
            orient: [0.0, 0.0, 0.0, 1.0],
        }
    }

    /// A new finger on the touchpad; its id, or None when both slots are taken.
    pub fn start_touch(&mut self, x: u16, y: u16) -> Option<u8> {
        let touch = self.touches.iter_mut().find(|touch| touch.id < 0)?;
        touch.id = self.touch_id_next as i8;
        touch.x = x;
        touch.y = y;
        self.touch_id_next = (self.touch_id_next + 1) & TOUCH_ID_MASK;
        Some(touch.id as u8)
    }

    pub fn stop_touch(&mut self, id: u8) {
        if let Some(touch) = self.touches.iter_mut().find(|touch| touch.id == id as i8) {
            touch.id = -1;
        }
    }

    pub fn set_touch_pos(&mut self, id: u8, x: u16, y: u16) {
        let id = (id & TOUCH_ID_MASK) as i8;
        if let Some(touch) = self.touches.iter_mut().find(|touch| touch.id == id) {
            touch.x = x;
            touch.y = y;
        }
    }

    /// The reference's state comparison (controller.c): a lifted finger's position does not count.
    pub fn equals(&self, other: &Self) -> bool {
        (self.buttons, self.l2, self.r2) == (other.buttons, other.l2, other.r2)
            && self.touches.iter().zip(&other.touches).all(|(a, b)| {
                a.id == b.id && (a.id < 0 || (a.x, a.y) == (b.x, b.y))
            })
            && self.same_feedback_state(other)
    }

    /// What a FEEDBACK_STATE carries: the sticks and the motion sensors.
    fn same_feedback_state(&self, other: &Self) -> bool {
        let close = |a: &[f32], b: &[f32]| a.iter().zip(b).all(|(a, b)| !(*a < b - 0.0000001 || *a > b + 0.0000001));
        (self.left_x, self.left_y, self.right_x, self.right_y)
            == (other.left_x, other.left_y, other.right_x, other.right_y)
            && close(&self.gyro, &other.gyro)
            && close(&self.accel, &other.accel)
            && close(&self.orient, &other.orient)
    }
}

/// A value in min..max as 16 bits, clamped (Rust's cast saturates).
fn scale(value: f32, min: f32, max: f32) -> u16 {
    (65535.0f32 * (value - min) / (max - min)) as u16
}

/// The orientation in 32 bits: which component is largest and its sign, the other three in 9 bits each. The
/// arithmetic mixes float and double as the reference's C does, so the bits are the same.
fn compress_quat(q: &[f32; 4]) -> u32 {
    use std::f64::consts::FRAC_1_SQRT_2;
    let mut largest = 0;
    for i in 1..4 {
        if q[i].abs() > q[largest].abs() {
            largest = i;
        }
    }
    let mut r = (q[largest] < 0.0) as u32 | (largest as u32) << 1;
    let factor = 0x1ff as f32 as f64 / (2.0f32 as f64 * FRAC_1_SQRT_2);
    for i in 0..3 {
        let mut v = q[if i < largest { i } else { i + 1 }];
        if (v as f64) < -FRAC_1_SQRT_2 {
            v = -FRAC_1_SQRT_2 as f32;
        }
        if (v as f64) > FRAC_1_SQRT_2 {
            v = FRAC_1_SQRT_2 as f32;
        }
        v = (v as f64 + FRAC_1_SQRT_2) as f32;
        v = (v as f64 * factor) as f32;
        r |= (v as u32) << (3 + i * 9);
    }
    r
}

/// The FEEDBACK_STATE payload: 0x19 bytes up to version 9 (PS4), 0x1c from version 12 (PS5).
pub fn state_format(version: u8, state: &ControllerState) -> Vec<u8> {
    let mut buf = Vec::with_capacity(STATE_SIZE_V12);
    buf.push(0xa0);
    for value in &state.gyro {
        buf.extend_from_slice(&scale(*value, GYRO_MIN, GYRO_MAX).to_le_bytes());
    }
    for value in &state.accel {
        buf.extend_from_slice(&scale(*value, ACCEL_MIN, ACCEL_MAX).to_le_bytes());
    }
    buf.extend_from_slice(&compress_quat(&state.orient).to_le_bytes());
    for stick in [state.left_x, state.left_y, state.right_x, state.right_y] {
        buf.extend_from_slice(&stick.to_be_bytes());
    }
    if version > 9 {
        buf.extend_from_slice(&[0, 0, 1]);
    }
    buf
}

/// A button event: 0 released, 0xff pressed, in between for L2 and R2. Some buttons carry their state in the code.
pub fn button_event(button: u32, value: u8) -> Option<Vec<u8>> {
    let code = match button {
        BUTTON_CROSS => 0x88,
        BUTTON_MOON => 0x89,
        BUTTON_BOX => 0x8a,
        BUTTON_PYRAMID => 0x8b,
        BUTTON_DPAD_LEFT => 0x82,
        BUTTON_DPAD_RIGHT => 0x83,
        BUTTON_DPAD_UP => 0x80,
        BUTTON_DPAD_DOWN => 0x81,
        BUTTON_L1 => 0x84,
        BUTTON_R1 => 0x85,
        ANALOG_L2 => 0x86,
        ANALOG_R2 => 0x87,
        BUTTON_L3 => return Some(vec![0x80, if value != 0 { 0xaf } else { 0x8f }]),
        BUTTON_R3 => return Some(vec![0x80, if value != 0 { 0xb0 } else { 0x90 }]),
        BUTTON_OPTIONS => return Some(vec![0x80, if value != 0 { 0xac } else { 0x8c }]),
        BUTTON_SHARE => return Some(vec![0x80, if value != 0 { 0xad } else { 0x8d }]),
        BUTTON_TOUCHPAD => return Some(vec![0x80, if value != 0 { 0xb1 } else { 0x91 }]),
        BUTTON_PS => return Some(vec![0x80, if value != 0 { 0xae } else { 0x8e }]),
        _ => return None,
    };
    Some(vec![0x80, code, value])
}

/// A finger down (or moved) or lifted; x up to 1919, y up to 941.
pub fn touch_event(down: bool, id: u8, x: u16, y: u16) -> Vec<u8> {
    vec![if down { 0xd0 } else { 0xc0 }, id & 0x7f, (x >> 4) as u8, ((x & 0xf) << 4) as u8 | (y >> 8) as u8, y as u8]
}

/// The last events, newest first (the reference's ring buffer of 16).
#[derive(Debug, Default)]
pub struct HistoryBuffer {
    events: VecDeque<Vec<u8>>,
    /// The several-players experiment: OR-ed into each event's first byte (0 for the reference's one controller).
    pub mark: u8,
}

impl HistoryBuffer {
    pub fn len(&self) -> usize {
        self.events.len()
    }

    pub fn is_empty(&self) -> bool {
        self.events.is_empty()
    }

    pub fn push(&mut self, mut event: Vec<u8>) {
        event[0] |= self.mark;
        self.events.push_front(event);
        self.events.truncate(HISTORY_BUFFER_SIZE);
    }

    pub fn format(&self) -> Vec<u8> {
        self.events.iter().flatten().copied().collect()
    }

    /// The history packets (event count, payload) for the change from prev to now, one per event, in the order a
    /// real controller makes them: releases, touches, presses, then L2 and R2. After each packet the buffer keeps the
    /// newest eight, which the next packet repeats.
    pub fn record(&mut self, prev: &ControllerState, now: &ControllerState) -> Vec<(u8, Vec<u8>)> {
        let mut packets = Vec::new();
        let mut push = |buffer: &mut Self, event: Vec<u8>| {
            buffer.push(event);
            packets.push((buffer.len() as u8, buffer.format()));
            buffer.events.truncate(HISTORY_RESEND_EVENT_COUNT);
        };
        let buttons = |buffer: &mut Self, push: &mut dyn FnMut(&mut Self, Vec<u8>), pressed: bool| {
            for i in 0..BUTTONS_COUNT {
                let button = 1 << i;
                let (was, is) = (prev.buttons & button != 0, now.buttons & button != 0);
                if was != is && is == pressed {
                    push(buffer, button_event(button, if is { 0xff } else { 0 }).expect("a known button"));
                }
            }
        };
        buttons(self, &mut push, false);
        for (was, is) in prev.touches.iter().zip(&now.touches) {
            if was.id != is.id && was.id >= 0 {
                push(self, touch_event(false, was.id as u8, was.x, was.y));
            } else if is.id >= 0 && (was.id != is.id || (was.x, was.y) != (is.x, is.y)) {
                push(self, touch_event(true, is.id as u8, is.x, is.y));
            }
        }
        buttons(self, &mut push, true);
        if prev.l2 != now.l2 {
            push(self, button_event(ANALOG_L2, now.l2).unwrap());
        }
        if prev.r2 != now.r2 {
            push(self, button_event(ANALOG_R2, now.r2).unwrap());
        }
        packets
    }
}

/// A FEEDBACK_STATE packet, not yet sealed.
pub fn state_packet(version: u8, seq_num: u16, state: &ControllerState) -> Vec<u8> {
    states_packet(version, seq_num, &[*state], 0)
}

/// A FEEDBACK_STATE packet with several states (byte 3 counts them; the reference always sends one), the first
/// byte of each OR-ed with mark: for the several-players experiment.
pub fn states_packet(version: u8, seq_num: u16, states: &[ControllerState], mark: u8) -> Vec<u8> {
    let mut buf = vec![PACKET_FEEDBACK_STATE];
    buf.extend_from_slice(&seq_num.to_be_bytes());
    buf.push(states.len() as u8);
    buf.extend_from_slice(&[0; 8]);                 // key position and GMAC
    for state in states {
        let mut formatted = state_format(version, state);
        formatted[0] |= mark;
        buf.extend_from_slice(&formatted);
    }
    buf
}

/// A FEEDBACK_HISTORY packet, not yet sealed.
pub fn history_packet(seq_num: u16, event_count: u8, payload: &[u8]) -> Vec<u8> {
    let mut buf = vec![PACKET_FEEDBACK_HISTORY];
    buf.extend_from_slice(&seq_num.to_be_bytes());
    buf.push(event_count);
    buf.extend_from_slice(&[0; 8]);
    buf.extend_from_slice(payload);
    buf
}

/// How far a feedback packet moves the local key position: its payload and one block.
pub fn key_pos_size(packet: &[u8]) -> usize {
    packet.len() - HEADER_SIZE + BLOCK_SIZE
}

/// Encrypts the payload (at key_pos + 16), writes the key position and signs the packet.
pub fn seal(crypt: &mut GkCrypt, packet: &mut [u8], key_pos: u64) {
    crypt.crypt(key_pos + BLOCK_SIZE as u64, &mut packet[HEADER_SIZE..]);
    packet[KEY_POS_AT..KEY_POS_AT + 4].copy_from_slice(&(key_pos as u32).to_be_bytes());
    packet[MAC_AT..MAC_AT + GMAC_SIZE].fill(0);
    let mac = crypt.gmac(key_pos, packet);
    packet[MAC_AT..MAC_AT + GMAC_SIZE].copy_from_slice(&mac);
}

/// The reference's feedback sender without its thread: set() takes the controller state, step() says what to send
/// now, wait() how long until the next step. The connection runs it on a thread of its own.
#[derive(Debug)]
pub struct Sender {
    version: u8,
    state: ControllerState,
    state_sent: ControllerState,                    // the last FEEDBACK_STATE's
    history_prev: ControllerState,
    history: HistoryBuffer,
    changed: bool,
    last_state: Instant,
    state_seq_num: u16,
    history_seq_num: u16,
    queue: VecDeque<(u8, Vec<u8>)>,
    last_history: Option<(u8, Vec<u8>, Instant)>,
    tail_resends: usize,
    pub overflows: u64,
    /// The several-players experiment: OR-ed into the first byte of each state and event this sender sends.
    mark: u8,
    /// The several-players experiment: a second controller's state, sent in the same FEEDBACK_STATE packets.
    extra: Option<ControllerState>,
    extra_changed: bool,
}

impl Sender {
    pub fn new(version: u8, now: Instant) -> Self {
        Sender {
            version,
            state: ControllerState::idle(),
            state_sent: ControllerState::idle(),
            history_prev: ControllerState::idle(),
            history: HistoryBuffer::default(),
            changed: false,
            last_state: now,
            state_seq_num: 0,
            history_seq_num: 0,
            queue: VecDeque::new(),
            last_history: None,
            tail_resends: HISTORY_TAIL.len(),
            overflows: 0,
            mark: 0,
            extra: None,
            extra_changed: false,
        }
    }

    /// A sender for another controller in the several-players experiment: mark goes into the first byte of its
    /// states and events.
    pub fn marked(version: u8, now: Instant, mark: u8) -> Self {
        let mut sender = Sender::new(version, now);
        sender.mark = mark;
        sender.history.mark = mark;
        sender
    }

    /// The several-players experiment: a second controller's state, sent beside this one in each FEEDBACK_STATE.
    pub fn set_extra(&mut self, state: ControllerState) {
        if self.extra.is_some_and(|extra| extra.same_feedback_state(&state)) {
            return;
        }
        self.extra = Some(state);
        self.extra_changed = true;
        self.changed = true;
    }

    /// A new controller state; the same input as before changes nothing.
    pub fn set(&mut self, state: ControllerState) {
        if self.state.equals(&state) {
            return;
        }
        self.state = state;
        for packet in self.history.record(&self.history_prev, &state) {
            if self.queue.len() == HISTORY_PACKET_QUEUE_SIZE {
                self.queue.pop_front();
                self.overflows += 1;
            }
            self.queue.push_back(packet);
        }
        self.history_prev = state;
        self.changed = true;
    }

    /// Whether step() has something to do before wait() runs out.
    pub fn ready(&self) -> bool {
        self.changed || !self.queue.is_empty()
    }

    /// How long until the next FEEDBACK_STATE or tail resend is due.
    pub fn wait(&self, now: Instant) -> Duration {
        let elapsed = now.saturating_duration_since(self.last_state);
        let mut timeout = if elapsed < STATE_TIMEOUT_MAX { STATE_TIMEOUT_MAX - elapsed } else { STATE_TIMEOUT_MAX };
        if let (Some((_, _, sent)), Some(offset)) = (&self.last_history, HISTORY_TAIL.get(self.tail_resends)) {
            timeout = timeout.min((*sent + *offset).saturating_duration_since(now));
        }
        timeout
    }

    /// The packets to send now, unsealed: a FEEDBACK_STATE when the sticks or motion changed or 200 ms passed, and
    /// the next history packet (or the last one again, when its tail resend is due).
    pub fn step(&mut self, now: Instant) -> Vec<Vec<u8>> {
        let mut send_state = now.saturating_duration_since(self.last_state) >= STATE_TIMEOUT_MAX;
        if self.changed {
            self.changed = false;
            // Only the buttons changed: no state packet, as in the reference, even when one is due.
            send_state = !self.state.same_feedback_state(&self.state_sent) || self.extra_changed;
            self.extra_changed = false;
        }
        let mut packets = Vec::new();
        if send_state {
            let states: Vec<ControllerState> = std::iter::once(self.state).chain(self.extra).collect();
            packets.push(states_packet(self.version, self.state_seq_num, &states, self.mark));
            self.state_seq_num = self.state_seq_num.wrapping_add(1);
            self.state_sent = self.state;
            self.last_state = now;
        }
        let history = if let Some((count, payload)) = self.queue.pop_front() {
            self.last_history = Some((count, payload.clone(), now));
            self.tail_resends = 0;
            Some((count, payload))
        } else {
            match (&self.last_history, HISTORY_TAIL.get(self.tail_resends)) {
                (Some((count, payload, sent)), Some(offset)) if now >= *sent + *offset => {
                    self.tail_resends += 1;
                    Some((*count, payload.clone()))
                }
                _ => None,
            }
        };
        if let Some((count, payload)) = history {
            packets.push(history_packet(self.history_seq_num, count, &payload));
            self.history_seq_num = self.history_seq_num.wrapping_add(1);
        }
        packets
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::vectors::hex;

    fn load() -> serde_json::Value {
        serde_json::from_str(include_str!("../../tests/feedback_vectors.json")).expect("valid vectors")
    }

    fn state(v: &serde_json::Value) -> ControllerState {
        let n = |name: &str| v[name].as_i64().unwrap();
        let floats = |name: &str| v[name].as_array().unwrap().iter().map(|x| x.as_f64().unwrap() as f32).collect::<Vec<_>>();
        let mut state = ControllerState::idle();
        state.buttons = n("buttons") as u32;
        (state.l2, state.r2) = (n("l2") as u8, n("r2") as u8);
        (state.left_x, state.left_y, state.right_x, state.right_y) =
            (n("left_x") as i16, n("left_y") as i16, n("right_x") as i16, n("right_y") as i16);
        for (touch, t) in state.touches.iter_mut().zip(v["touches"].as_array().unwrap()) {
            let t: Vec<i64> = t.as_array().unwrap().iter().map(|x| x.as_i64().unwrap()).collect();
            *touch = Touch { id: t[0] as i8, x: t[1] as u16, y: t[2] as u16 };
        }
        state.gyro.copy_from_slice(&floats("gyro"));
        state.accel.copy_from_slice(&floats("accel"));
        state.orient.copy_from_slice(&floats("orient"));
        state
    }

    #[test]
    fn state_matches_reference() {
        for case in load()["state"].as_array().unwrap() {
            let s = state(&case["state"]);
            assert_eq!(state_format(9, &s), hex(&case["v9"]));
            assert_eq!(state_format(12, &s), hex(&case["v12"]));
        }
    }

    #[test]
    fn events_match_reference() {
        let v = load();
        for case in v["button_events"].as_array().unwrap() {
            let event = button_event(case["button"].as_u64().unwrap() as u32, case["value"].as_u64().unwrap() as u8);
            assert_eq!(event, Some(hex(&case["event"])), "{case}");
        }
        for case in v["touch_events"].as_array().unwrap() {
            let n = |name: &str| case[name].as_u64().unwrap();
            let event = touch_event(case["down"].as_bool().unwrap(), n("id") as u8, n("x") as u16, n("y") as u16);
            assert_eq!(event, hex(&case["event"]));
        }
        assert_eq!(button_event(1 << 18, 0xff), None);
    }

    #[test]
    fn history_matches_reference() {
        let mut buffer = HistoryBuffer::default();
        let mut prev = ControllerState::idle();
        for case in load()["history"].as_array().unwrap() {
            let now = state(&case["state"]);
            let expected: Vec<(u8, Vec<u8>)> = case["packets"].as_array().unwrap().iter()
                .map(|p| (p["event_count"].as_u64().unwrap() as u8, hex(&p["payload"])))
                .collect();
            assert_eq!(buffer.record(&prev, &now), expected);
            prev = now;
        }
    }

    #[test]
    fn packets_match_reference() {
        let vectors = load();
        let v = &vectors["packets"];
        let key: [u8; 16] = hex(&v["handshake_key"]).try_into().unwrap();
        let secret: [u8; 32] = hex(&v["secret"]).try_into().unwrap();
        for case in v["cases"].as_array().unwrap() {
            let n = |name: &str| case[name].as_u64().unwrap();
            let plain = hex(&case["plain"]);
            let mut packet = if case["history"].as_bool().unwrap() {
                history_packet(n("seq_num") as u16, plain[3], &plain[HEADER_SIZE..])
            } else {
                let s = state(&vectors["state"][n("state") as usize]["state"]);
                state_packet(n("version") as u8, n("seq_num") as u16, &s)
            };
            assert_eq!(packet, plain);
            let mut crypt = GkCrypt::new(2, &key, &secret);
            seal(&mut crypt, &mut packet, n("key_pos"));
            assert_eq!(packet, hex(&case["packet"]));
        }
    }

    #[test]
    fn motion_out_of_range_is_clamped() {
        let mut s = ControllerState::idle();
        s.gyro = [40.0, -31.0, f32::NAN];
        s.accel = [5.5, -100.0, 0.0];
        let buf = state_format(9, &s);
        assert_eq!(&buf[1..7], &[0xff, 0xff, 0, 0, 0, 0]);
        assert_eq!(&buf[7..11], &[0xff, 0xff, 0, 0]);
    }

    #[test]
    fn touches() {
        let mut s = ControllerState::idle();
        assert_eq!((s.start_touch(1, 2), s.start_touch(3, 4), s.start_touch(5, 6)), (Some(0), Some(1), None));
        s.set_touch_pos(1 | 0x80, 7, 8);
        assert_eq!((s.touches[1].x, s.touches[1].y), (7, 8));
        s.stop_touch(0);
        assert_eq!(s.start_touch(9, 9), Some(2));
        s.touch_id_next = 0x7f;
        s.stop_touch(2);
        assert_eq!((s.start_touch(0, 0), s.touch_id_next), (Some(0x7f), 0));
    }

    #[test]
    fn idle_state_every_200_ms() {
        let start = Instant::now();
        let mut sender = Sender::new(9, start);
        assert!(!sender.ready());
        assert_eq!(sender.wait(start), STATE_TIMEOUT_MAX);
        assert!(sender.step(start + Duration::from_millis(100)).is_empty());
        let packets = sender.step(start + STATE_TIMEOUT_MAX);
        assert_eq!(packets, vec![state_packet(9, 0, &ControllerState::idle())]);
        assert_eq!(sender.wait(start + STATE_TIMEOUT_MAX + Duration::from_millis(50)), Duration::from_millis(150));
        assert_eq!(sender.step(start + 2 * STATE_TIMEOUT_MAX)[0][1..3], [0, 1]);
    }

    #[test]
    fn sticks_send_a_state_at_once() {
        let start = Instant::now();
        let mut sender = Sender::new(12, start);
        let mut s = ControllerState::idle();
        s.left_x = 1000;
        sender.set(s);
        sender.set(s);                                      // the same again: nothing new
        assert!(sender.ready());
        assert_eq!(sender.step(start + Duration::from_millis(1)), vec![state_packet(12, 0, &s)]);
        assert!(!sender.ready());
    }

    #[test]
    fn a_button_goes_as_history_with_its_tail() {
        let start = Instant::now();
        let ms = |n: u64| start + Duration::from_millis(n);
        let mut sender = Sender::new(9, start);
        let mut s = ControllerState::idle();
        s.buttons = BUTTON_CROSS;
        sender.set(s);
        sender.set(ControllerState::idle());
        // The press, no state packet (sticks and motion unchanged), then the release.
        assert_eq!(sender.step(ms(1)), vec![history_packet(0, 1, &[0x80, 0x88, 0xff])]);
        assert!(sender.ready());
        let release = history_packet(1, 2, &[0x80, 0x88, 0x00, 0x80, 0x88, 0xff]);
        assert_eq!(sender.step(ms(2)), vec![release.clone()]);
        assert!(!sender.ready());
        // The release again after 20, 50, 100 and 200 ms, each with a new sequence number; the state packet when
        // 200 ms passed.
        assert_eq!(sender.wait(ms(2)), Duration::from_millis(20));
        let again = |seq: u16| history_packet(seq, 2, &release[HEADER_SIZE..]);
        assert_eq!(sender.step(ms(22)), vec![again(2)]);
        assert_eq!(sender.wait(ms(22)), Duration::from_millis(30));
        assert_eq!(sender.step(ms(52)), vec![again(3)]);
        assert_eq!(sender.step(ms(102)), vec![again(4)]);
        assert_eq!(sender.step(ms(202)), vec![state_packet(9, 0, &ControllerState::idle()), again(5)]);
        assert!(sender.step(ms(300)).is_empty());
        assert_eq!(sender.wait(ms(300)), Duration::from_millis(102));
    }

    #[test]
    fn a_full_queue_drops_the_oldest() {
        let start = Instant::now();
        let mut sender = Sender::new(9, start);
        let mut s = ControllerState::idle();
        for i in 0..HISTORY_PACKET_QUEUE_SIZE + 3 {
            s.l2 = (i + 1) as u8;
            sender.set(s);
        }
        assert_eq!((sender.queue.len(), sender.overflows), (HISTORY_PACKET_QUEUE_SIZE, 3));
        assert_eq!(sender.queue[0].1[..3], [0x80, 0x86, 4]);
    }

    // The several-players experiment.

    #[test]
    fn two_states_in_one_packet_and_marked_first_bytes() {
        let mut second = ControllerState::idle();
        second.left_x = 0x1234;
        let packet = states_packet(9, 7, &[ControllerState::idle(), second], 1);
        assert_eq!(packet.len(), HEADER_SIZE + 2 * STATE_SIZE_V9);
        assert_eq!(packet[..4], [PACKET_FEEDBACK_STATE, 0, 7, 2]);
        assert_eq!((packet[HEADER_SIZE], packet[HEADER_SIZE + STATE_SIZE_V9]), (0xa1, 0xa1));
        assert_eq!(packet[HEADER_SIZE + STATE_SIZE_V9 + 0x11..][..2], [0x12, 0x34]);
        assert_eq!(state_packet(9, 7, &second), states_packet(9, 7, &[second], 0));    // the reference's packet
    }

    #[test]
    fn a_marked_sender_marks_its_states_and_events() {
        let now = Instant::now();
        let mut sender = Sender::marked(9, now, 2);
        let mut state = ControllerState::idle();
        state.buttons = BUTTON_CROSS;
        state.left_x = 100;
        sender.set(state);
        let packets = sender.step(now);
        assert_eq!(packets.len(), 2);
        assert_eq!(packets[0][HEADER_SIZE], 0xa2);                                // the state
        assert_eq!(packets[1][HEADER_SIZE..HEADER_SIZE + 3], [0x82, 0x88, 0xff]);  // cross pressed
    }

    #[test]
    fn a_second_state_goes_out_with_the_first() {
        let now = Instant::now();
        let mut sender = Sender::new(9, now);
        assert!(sender.step(now).is_empty());
        let mut second = ControllerState::idle();
        second.right_y = -5;
        sender.set_extra(second);
        assert!(sender.ready());
        let packets = sender.step(now);
        assert_eq!(packets.len(), 1);
        assert_eq!((packets[0][3], packets[0].len()), (2, HEADER_SIZE + 2 * STATE_SIZE_V9));
        sender.set_extra(second);                                                 // the same: nothing new
        assert!(!sender.ready());
    }
}
