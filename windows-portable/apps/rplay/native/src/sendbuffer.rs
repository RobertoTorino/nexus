// SPDX-License-Identifier: AGPL-3.0-only
//! The data messages sent and not yet acknowledged. A message is sent again when
//! no DATA_ACK came within 200 ms, up to 25 times; then it is given up. An acknowledgement covers its sequence
//! number and every earlier one.

use std::time::{Duration, Instant};

use crate::seqnum::lt32;

pub const SIZE: usize = 16;
pub const RESEND_TIMEOUT: Duration = Duration::from_millis(200);
pub const RESEND_WAKEUP: Duration = Duration::from_millis(100);
pub const RESEND_TRIES_MAX: u32 = 25;

#[derive(Debug, PartialEq, Eq)]
pub enum SendBufferError {
    Overflow,
    Duplicate,
}

struct Entry {
    seq_num: u32,
    tries: u32,
    last_send: Instant,
    packet: Vec<u8>,
}

#[derive(Default)]
pub struct SendBuffer {
    entries: Vec<Entry>,
}

#[derive(Debug, Default, PartialEq, Eq)]
pub struct Due {
    pub resend: Vec<Vec<u8>>,
    pub given_up: Vec<u32>,
}

impl SendBuffer {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn len(&self) -> usize {
        self.entries.len()
    }

    pub fn is_empty(&self) -> bool {
        self.entries.is_empty()
    }

    /// A message that was just sent.
    pub fn push(&mut self, seq_num: u32, packet: Vec<u8>, now: Instant) -> Result<(), SendBufferError> {
        if self.entries.len() >= SIZE {
            return Err(SendBufferError::Overflow);
        }
        if self.entries.iter().any(|e| e.seq_num == seq_num) {
            return Err(SendBufferError::Duplicate);
        }
        self.entries.push(Entry { seq_num, tries: 0, last_send: now, packet });
        Ok(())
    }

    /// Removes seq_num and everything before it; returns the removed sequence numbers in buffer order.
    pub fn ack(&mut self, seq_num: u32) -> Vec<u32> {
        let mut acked = Vec::new();
        self.entries.retain(|e| {
            let covered = e.seq_num == seq_num || lt32(e.seq_num, seq_num);
            if covered {
                acked.push(e.seq_num);
            }
            !covered
        });
        acked
    }

    /// What to send again now, and what is given up after the last try (acknowledged locally, as the reference does).
    pub fn due(&mut self, now: Instant) -> Due {
        let mut due = Due::default();
        let mut i = 0;
        while i < self.entries.len() {
            let entry = &mut self.entries[i];
            if now.duration_since(entry.last_send) > RESEND_TIMEOUT {
                if entry.tries >= RESEND_TRIES_MAX {
                    let seq_num = entry.seq_num;
                    due.given_up.extend(self.ack(seq_num));
                    i = 0;
                    continue;
                }
                entry.last_send = now;
                entry.tries += 1;
                due.resend.push(entry.packet.clone());
            }
            i += 1;
        }
        due
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ack_covers_earlier_and_wraps() {
        let now = Instant::now();
        let mut buffer = SendBuffer::new();
        for seq in [0xffff_fffe, 0xffff_ffff, 0, 1] {
            buffer.push(seq, vec![seq as u8], now).unwrap();
        }
        assert_eq!(buffer.push(1, vec![], now), Err(SendBufferError::Duplicate));
        assert_eq!(buffer.ack(0), vec![0xffff_fffe, 0xffff_ffff, 0]);
        assert_eq!(buffer.len(), 1);
        for seq in 2..2 + SIZE as u32 - 1 {
            buffer.push(seq, vec![], now).unwrap();
        }
        assert_eq!(buffer.push(100, vec![], now), Err(SendBufferError::Overflow));
    }

    #[test]
    fn resends_then_gives_up() {
        let start = Instant::now();
        let mut buffer = SendBuffer::new();
        buffer.push(7, vec![7], start).unwrap();
        assert_eq!(buffer.due(start + RESEND_TIMEOUT), Due::default());          // not later than the timeout
        let mut now = start;
        for _ in 0..RESEND_TRIES_MAX {
            now += RESEND_TIMEOUT + Duration::from_millis(1);
            assert_eq!(buffer.due(now), Due { resend: vec![vec![7]], given_up: vec![] });
        }
        now += RESEND_TIMEOUT + Duration::from_millis(1);
        assert_eq!(buffer.due(now), Due { resend: vec![], given_up: vec![7] });
        assert!(buffer.is_empty());
    }
}
