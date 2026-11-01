// SPDX-License-Identifier: AGPL-3.0-only
//! The audio receiver (the reference's audioreceiver.c): audio packets in, Opus frames out in order, one per 10 ms.
//!
//! An audio packet carries a few units of one size, each an Opus frame: its source units are the frames from the
//! packet's frame index on, its FEC units copies of the frames just before it, so a lost packet's frames come with
//! the next one. The frames wait in a jitter buffer (8 slots); playback starts with 3 in it, then takes them in
//! order. A frame that never comes is given up once newer ones are buffered: the event has no data then, and the
//! decoder fills the gap. Haptics (the PS5's controller rumble, sent as audio packets) are only counted here.
//!
//! One difference: the reference takes a packet's source units before its FEC units. With the jitter buffer nearly
//! empty, as it is while playing, it then gives a lost frame up before it sees the FEC copy in the same packet, so
//! the copies hardly ever help. Here the FEC units, the older frames, come first.

use crate::seqnum::{gt16, lt16};
use crate::takion::AvPacket;

pub const CODEC_OPUS: u8 = 5;
pub const JITTER_PREFILL: usize = 3;
pub const JITTER_SIZE: usize = 8;

#[derive(Debug, PartialEq, Eq)]
pub struct AudioFrame {
    pub index: u16,
    /// The Opus frame; None for a frame that is lost.
    pub data: Option<Vec<u8>>,
}

#[derive(Clone, Copy, Debug, Default)]
pub struct AudioStats {
    pub packets: u64,
    pub frames: u64,
    pub lost: u64,
    pub refused: u64,
    pub haptics: u64,                   // packets
}

#[derive(Default)]
pub struct AudioReceiver {
    next: Option<u16>,                  // the frame to play next, once playback started
    startup: bool,
    slots: Vec<Option<(u16, Vec<u8>)>>,
    pub stats: AudioStats,
}

impl AudioReceiver {
    pub fn new() -> Self {
        Self { startup: true, slots: (0..JITTER_SIZE).map(|_| None).collect(), ..Default::default() }
    }

    fn count(&self) -> usize {
        self.slots.iter().flatten().count()
    }

    fn find(&self, index: u16) -> Option<usize> {
        self.slots.iter().position(|slot| matches!(slot, Some((i, _)) if *i == index))
    }

    fn oldest(&self) -> Option<usize> {
        let mut found: Option<usize> = None;
        for (i, slot) in self.slots.iter().enumerate() {
            if let Some((index, _)) = slot {
                if found.is_none_or(|f| lt16(*index, self.slots[f].as_ref().unwrap().0)) {
                    found = Some(i);
                }
            }
        }
        found
    }

    fn newest(&self) -> Option<usize> {
        let mut found: Option<usize> = None;
        for (i, slot) in self.slots.iter().enumerate() {
            if let Some((index, _)) = slot {
                if found.is_none_or(|f| gt16(*index, self.slots[f].as_ref().unwrap().0)) {
                    found = Some(i);
                }
            }
        }
        found
    }

    /// Into the jitter buffer; when it is full, a frame older than the newest takes that one's slot.
    fn store(&mut self, index: u16, data: &[u8]) -> bool {
        if self.find(index).is_some() {
            return false;
        }
        let slot = match self.slots.iter().position(Option::is_none) {
            Some(free) => free,
            None => {
                let Some(newest) = self.newest() else { return false };
                if !lt16(index, self.slots[newest].as_ref().unwrap().0) {
                    return false;
                }
                newest
            }
        };
        self.slots[slot] = Some((index, data.to_vec()));
        true
    }

    /// The frames that are due, in order, after this packet.
    pub fn packet(&mut self, packet: &AvPacket, data: &[u8]) -> Vec<AudioFrame> {
        let mut out = Vec::new();
        if packet.is_haptics {
            self.stats.haptics += 1;
            return out;
        }
        self.stats.packets += 1;
        let source = (packet.units_in_frame_fec & 0xf) as usize;
        let fec = ((packet.units_in_frame_fec >> 4) & 0xf) as usize;
        let unit_size = (packet.units_in_frame_fec >> 8) as usize;
        if packet.codec != CODEC_OPUS || data.is_empty() || source + fec != packet.units_in_frame_total as usize
            || data.len() != unit_size * (source + fec) {
            self.stats.refused += 1;
            return out;
        }
        if packet.frame_index > 1 << 15 {
            self.startup = false;
        }
        for i in (source..source + fec).chain(0..source) {
            let index = if i < source {
                packet.frame_index.wrapping_add(i as u16)
            } else {
                let fec_index = i - source;
                // At the start of the stream the FEC units would be frames from before it.
                if self.startup && packet.frame_index as usize + fec_index < fec + 1 {
                    continue;
                }
                packet.frame_index.wrapping_sub(fec as u16).wrapping_add(fec_index as u16)
            };
            self.frame(index, &data[unit_size * i..unit_size * (i + 1)], &mut out);
        }
        out
    }

    fn frame(&mut self, index: u16, unit: &[u8], out: &mut Vec<AudioFrame>) {
        if self.next.is_some_and(|next| lt16(index, next)) || !self.store(index, unit) {
            return;
        }
        loop {
            if self.next.is_none() && self.count() >= JITTER_PREFILL {
                self.next = self.oldest().map(|slot| self.slots[slot].as_ref().unwrap().0);
            }
            let Some(next) = self.next else { return };
            if let Some(slot) = self.find(next) {
                let (_, data) = self.slots[slot].take().unwrap();
                out.push(AudioFrame { index: next, data: Some(data) });
                self.stats.frames += 1;
            } else {
                let (Some(oldest), Some(newest)) = (self.oldest(), self.newest()) else { return };
                let newer_buffered = gt16(self.slots[oldest].as_ref().unwrap().0, next);
                let conceal = newer_buffered && (self.count() < JITTER_PREFILL
                    || gt16(self.slots[newest].as_ref().unwrap().0,
                            next.wrapping_add(JITTER_PREFILL as u16).wrapping_sub(1)));
                if !conceal {
                    return;
                }
                out.push(AudioFrame { index: next, data: None });
                self.stats.lost += 1;
            }
            self.next = Some(next.wrapping_add(1));
        }
    }
}

#[cfg(test)]
pub(crate) mod tests {
    use super::*;

    /// An audio packet as the console sends it: source frames from index on, then fec copies of those before.
    pub(crate) fn packet(index: u16, source: usize, fec: usize, unit: usize) -> (AvPacket, Vec<u8>) {
        let header = AvPacket {
            frame_index: index, codec: CODEC_OPUS, units_in_frame_total: (source + fec) as u16,
            units_in_frame_fec: ((unit << 8) | (fec << 4) | source) as u16, ..Default::default()
        };
        let mut data = Vec::new();
        for i in 0..source {
            data.extend(vec![index.wrapping_add(i as u16) as u8; unit]);
        }
        for f in 0..fec {
            data.extend(vec![index.wrapping_sub(fec as u16).wrapping_add(f as u16) as u8; unit]);
        }
        (header, data)
    }

    fn feed(receiver: &mut AudioReceiver, index: u16) -> Vec<(u16, Option<u8>)> {
        let (header, data) = packet(index, 1, 1, 4);
        receiver.packet(&header, &data).into_iter().map(|f| (f.index, f.data.map(|d| d[0]))).collect()
    }

    #[test]
    fn plays_in_order_after_the_prefill() {
        let mut receiver = AudioReceiver::new();
        assert!(feed(&mut receiver, 1).is_empty());            // frame 1 (its FEC copy of 0 is from before the start)
        assert!(feed(&mut receiver, 2).is_empty());            // 2, and 1 again: a duplicate
        assert_eq!(feed(&mut receiver, 3), [(1, Some(1)), (2, Some(2)), (3, Some(3))]);
        assert_eq!(feed(&mut receiver, 4), [(4, Some(4))]);
        assert_eq!(receiver.stats.frames, 4);
    }

    #[test]
    fn a_lost_packet_comes_back_from_the_next_ones_fec() {
        let mut receiver = AudioReceiver::new();
        for i in 1..=3 {
            feed(&mut receiver, i);
        }
        assert!(feed(&mut receiver, 5).len() == 2);            // 4 from 5's FEC copy, then 5
        assert_eq!(receiver.stats.lost, 0);
    }

    #[test]
    fn a_frame_that_never_comes_is_given_up() {
        let mut receiver = AudioReceiver::new();
        for i in 1..=3 {
            feed(&mut receiver, i);
        }
        // 4 and 5 lost, no FEC to bring them back: with less than the prefill buffered, given up right away.
        let (header, data) = packet(6, 1, 0, 4);
        let frames: Vec<_> = receiver.packet(&header, &data).into_iter().map(|f| (f.index, f.data.is_some())).collect();
        assert_eq!(frames, [(4, false), (5, false), (6, true)]);
        assert_eq!(receiver.stats.lost, 2);
    }

    #[test]
    fn bad_packets_and_haptics() {
        let mut receiver = AudioReceiver::new();
        let (mut header, data) = packet(1, 2, 1, 4);
        header.codec = 0xff;
        assert!(receiver.packet(&header, &data).is_empty());
        let (header, _) = packet(1, 2, 1, 4);
        assert!(receiver.packet(&header, &[0; 5]).is_empty());
        assert_eq!(receiver.stats.refused, 2);
        let (mut header, data) = packet(9, 1, 0, 4);
        header.is_haptics = true;
        assert!(receiver.packet(&header, &data).is_empty());
        assert_eq!((receiver.stats.haptics, receiver.stats.frames), (1, 0));
    }
}
