// SPDX-License-Identifier: AGPL-3.0-only
//! A video frame from its units, and the packet counts for the congestion reports
//! (packetstats.c).
//!
//! A frame comes as units of one size: the source units, then the FEC units. Each source unit starts with two
//! bytes (big-endian), the padding after its data; the first unit of a frame gives the size of all. When enough
//! units are there the frame is flushed: missing source units come from FEC (fec.rs), then the source units without
//! their first two bytes, one after another, are the frame.

use crate::fec;
use crate::seqnum::gt16;
use crate::takion::AvPacket;

pub const UNIT_SLOTS_MAX: usize = 512;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum FlushResult {
    Success,
    FecSuccess,
    FecFailed,
    Failed,
}

#[derive(Debug, Default)]
pub struct FrameProcessor {
    buf: Vec<u8>,
    unit_size: usize,
    stride: usize,
    source_expected: usize,
    fec_expected: usize,
    source_received: usize,
    fec_received: usize,
    slots: Vec<usize>,          // the size of each unit received, 0 while missing
    flushed: bool,
}

impl FrameProcessor {
    pub fn new() -> Self {
        Self { flushed: true, ..Default::default() }
    }

    /// Starts a frame from its first packet. The reference keeps the last frame's state when this fails; here the
    /// frame is empty then, so its units are refused and its flush fails.
    pub fn alloc_frame(&mut self, packet: &AvPacket, data: &[u8]) -> Result<(), &'static str> {
        *self = Self { buf: std::mem::take(&mut self.buf), flushed: true, ..Default::default() };
        if packet.units_in_frame_total < packet.units_in_frame_fec {
            return Err("the packet has fewer units in all than FEC units");
        }
        let source_expected = (packet.units_in_frame_total - packet.units_in_frame_fec) as usize;
        let fec_expected = (packet.units_in_frame_fec as usize).max(1);
        let mut unit_size = data.len();
        if packet.is_video && (packet.unit_index as usize) < source_expected {
            if data.len() < 2 {
                return Err("the packet is too small for its padding size");
            }
            unit_size += u16::from_be_bytes([data[0], data[1]]) as usize;
        }
        if unit_size == 0 {
            return Err("the frame's units are empty");
        }
        if source_expected + fec_expected > UNIT_SLOTS_MAX {
            return Err("the packet announces more than 512 units");
        }
        let stride = unit_size.div_ceil(0x10) * 0x10;
        self.buf.clear();
        self.buf.resize((source_expected + fec_expected) * stride, 0);
        self.slots = vec![0; source_expected + fec_expected];
        (self.unit_size, self.stride) = (unit_size, stride);
        (self.source_expected, self.fec_expected) = (source_expected, fec_expected);
        self.flushed = false;
        Ok(())
    }

    pub fn put_unit(&mut self, packet: &AvPacket, data: &[u8]) -> Result<(), &'static str> {
        let index = packet.unit_index as usize;
        if index >= packet.units_in_frame_total as usize || index >= self.slots.len() {
            return Err("the unit index is outside the frame");
        }
        if data.is_empty() {
            return Err("the unit is empty");
        }
        if data.len() > self.unit_size {
            return Err("the unit is larger than the frame's unit size");
        }
        if self.slots[index] != 0 {
            return Err("the unit came twice");
        }
        self.slots[index] = data.len();
        if !self.flushed {
            self.buf[index * self.stride..index * self.stride + data.len()].copy_from_slice(data);
        }
        if index < self.source_expected {
            self.source_received += 1;
        } else {
            self.fec_received += 1;
        }
        Ok(())
    }

    /// Units received and units missing, for the congestion reports. As in the reference, a frame without FEC units
    /// counts one FEC unit expected.
    pub fn packet_counts(&self) -> (u64, u64) {
        let received = self.source_received + self.fec_received;
        ((received) as u64, (self.source_expected + self.fec_expected - received) as u64)
    }

    pub fn flush_possible(&self) -> bool {
        self.source_received + self.fec_received >= self.source_expected
    }

    fn fec(&mut self) -> bool {
        let erasures: Vec<usize> = (0..self.slots.len()).filter(|&i| self.slots[i] == 0).collect();
        if fec::decode(&mut self.buf, self.unit_size, self.stride, self.source_expected, self.fec_expected, &erasures)
            .is_err() {
            return false;
        }
        for i in 0..self.source_expected {
            let at = i * self.stride;
            let padding = u16::from_be_bytes([self.buf[at], self.buf[at + 1]]) as usize;
            if padding < self.unit_size {           // else the unit stays as it was (the reference logs it)
                self.slots[i] = self.unit_size - padding;
            }
        }
        true
    }

    /// The frame: the source units without their padding size, with FEC first when units are missing.
    /// The reference's frame can be flushed once; later units only count.
    pub fn flush(&mut self) -> (FlushResult, Vec<u8>) {
        if self.source_expected == 0 || self.flushed {
            return (FlushResult::Failed, Vec::new());
        }
        let mut result = FlushResult::Success;
        if self.source_received < self.source_expected {
            result = if self.fec() { FlushResult::FecSuccess } else { FlushResult::FecFailed };
        }
        let mut frame = Vec::new();
        for i in 0..self.source_expected {
            let size = self.slots[i];
            if size < 2 {                           // missing, or too small for its padding size
                continue;
            }
            frame.extend_from_slice(&self.buf[i * self.stride + 2..i * self.stride + size]);
        }
        self.flushed = true;
        (result, frame)
    }
}

/// Packets received and lost since the last congestion report: per frame the units of the video, and by sequence
/// number the audio packets.
#[derive(Debug, Default)]
pub struct PacketStats {
    gen_received: u64,
    gen_lost: u64,
    seq_min: u16,
    seq_max: u16,
    seq_received: u64,
}

impl PacketStats {
    pub fn push_generation(&mut self, received: u64, lost: u64) {
        self.gen_received += received;
        self.gen_lost += lost;
    }

    pub fn push_seq(&mut self, seq_num: u16) {
        self.seq_received += 1;
        if gt16(seq_num, self.seq_max) {
            self.seq_max = seq_num;
        }
    }

    /// Received and lost, then counting starts again. The sequence part is the reference's arithmetic as it is: the
    /// difference wraps when the maximum is below the minimum, and more packets than the difference count the
    /// difference as lost.
    pub fn take(&mut self) -> (u64, u64) {
        let seq_diff = (self.seq_max as i64 - self.seq_min as i64) as u64;
        let seq_lost = if self.seq_received > seq_diff { seq_diff } else { seq_diff - self.seq_received };
        let counts = (self.gen_received.wrapping_add(self.seq_received), self.gen_lost.wrapping_add(seq_lost));
        *self = Self { seq_min: self.seq_max, seq_max: self.seq_max, ..Default::default() };
        counts
    }
}

/// The congestion report from the counts: the loss reported is at most
/// packet_loss_max of the packets, both numbers cut to 16 bits.
pub fn congestion_report(received: u64, lost: u64, packet_loss_max: f64) -> (u16, u16) {
    let total = received.wrapping_add(lost);
    let (mut received, mut lost) = (received, lost);
    let loss = if total > 0 { lost as f64 / total as f64 } else { 0.0 };
    if loss > packet_loss_max {
        lost = (total as f64 * packet_loss_max) as u64;
        received = total - lost;
    }
    (received as u16, lost as u16)
}

#[cfg(test)]
pub(crate) mod tests {
    use super::*;

    /// The units of a frame as the console sends them: each source unit its padding size and data, padded to the
    /// unit size, then the FEC units.
    pub(crate) fn units(frame: &[u8], unit_size: usize, fec_units: usize) -> Vec<Vec<u8>> {
        let chunk = unit_size - 2;
        let k = frame.len().div_ceil(chunk);
        let mut buf = vec![0u8; unit_size * (k + fec_units)];
        for (i, part) in frame.chunks(chunk).enumerate() {
            let at = i * unit_size;
            buf[at..at + 2].copy_from_slice(&((chunk - part.len()) as u16).to_be_bytes());
            buf[at + 2..at + 2 + part.len()].copy_from_slice(part);
        }
        fec::encode(&mut buf, unit_size, unit_size, k, fec_units).unwrap();
        (0..k + fec_units).map(|i| {
            let unit = &buf[i * unit_size..(i + 1) * unit_size];
            if i < k { unit[..unit_size - u16::from_be_bytes([unit[0], unit[1]]) as usize].to_vec() }
            else { unit.to_vec() }
        }).collect()
    }

    pub(crate) fn packet(frame_index: u16, unit_index: usize, total: usize, fec: usize) -> AvPacket {
        AvPacket {
            is_video: true, frame_index, unit_index: unit_index as u16, units_in_frame_total: total as u16,
            units_in_frame_fec: fec as u16, ..Default::default()
        }
    }

    fn frame_bytes() -> Vec<u8> {
        (0..3000u32).map(|i| (i * 7 + 3) as u8).collect()
    }

    #[test]
    fn whole_frame() {
        let frame = frame_bytes();
        let units = units(&frame, 1000, 2);
        let mut processor = FrameProcessor::new();
        processor.alloc_frame(&packet(1, 0, 6, 2), &units[0]).unwrap();
        for (i, unit) in units.iter().enumerate().take(4) {
            processor.put_unit(&packet(1, i, 6, 2), unit).unwrap();
        }
        assert!(processor.flush_possible());
        assert_eq!(processor.flush(), (FlushResult::Success, frame));
        assert_eq!(processor.flush().0, FlushResult::Failed);
        assert_eq!(processor.packet_counts(), (4, 2));
    }

    #[test]
    fn missing_units_from_fec() {
        let frame = frame_bytes();
        let units = units(&frame, 1000, 2);
        let mut processor = FrameProcessor::new();
        processor.alloc_frame(&packet(1, 1, 6, 2), &units[1]).unwrap();
        for i in [1, 3, 4, 5] {
            processor.put_unit(&packet(1, i, 6, 2), &units[i]).unwrap();
        }
        assert_eq!(processor.flush(), (FlushResult::FecSuccess, frame));
    }

    #[test]
    fn too_many_missing() {
        let units = units(&frame_bytes(), 1000, 1);
        let mut processor = FrameProcessor::new();
        processor.alloc_frame(&packet(1, 0, 5, 1), &units[0]).unwrap();
        processor.put_unit(&packet(1, 0, 5, 1), &units[0]).unwrap();
        processor.put_unit(&packet(1, 4, 5, 1), &units[4]).unwrap();
        assert_eq!(processor.flush().0, FlushResult::FecFailed);
        assert_eq!(processor.packet_counts(), (2, 3));
    }

    #[test]
    fn bad_units_are_refused() {
        let units = units(&frame_bytes(), 1000, 1);
        let mut processor = FrameProcessor::new();
        assert!(processor.alloc_frame(&packet(1, 0, 1, 2), &units[0]).is_err());
        assert!(processor.put_unit(&packet(1, 0, 5, 1), &units[0]).is_err());
        assert_eq!(processor.flush().0, FlushResult::Failed);
        assert!(processor.alloc_frame(&packet(1, 0, 600, 1), &units[0]).is_err());
        processor.alloc_frame(&packet(1, 0, 5, 1), &units[0]).unwrap();
        processor.put_unit(&packet(1, 0, 5, 1), &units[0]).unwrap();
        assert_eq!(processor.put_unit(&packet(1, 0, 5, 1), &units[0]), Err("the unit came twice"));
        assert!(processor.put_unit(&packet(1, 1, 5, 1), &[0; 1001]).is_err());
        assert!(processor.put_unit(&packet(1, 5, 5, 1), &units[1]).is_err());
    }

    #[test]
    fn packet_stats_and_reports() {
        let mut stats = PacketStats::default();
        stats.push_generation(10, 2);
        for seq in 1..=5 {
            stats.push_seq(seq);
        }
        assert_eq!(stats.take(), (15, 2));
        assert_eq!(stats.take(), (0, 0));
        stats.push_seq(8);
        assert_eq!(stats.take(), (1, 2));
        for _ in 0..3 {
            stats.push_seq(9);
        }
        assert_eq!(stats.take(), (3, 1));           // more packets than the difference: the reference counts it lost
        assert_eq!(congestion_report(90, 10, 0.05), (95, 5));
        assert_eq!(congestion_report(99, 1, 0.05), (99, 1));
        assert_eq!(congestion_report(0, 0, 0.05), (0, 0));
    }
}
