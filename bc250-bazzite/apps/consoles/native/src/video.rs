// SPDX-License-Identifier: AGPL-3.0-only
//! The video receiver: video packets in, whole frames out. A frame is flushed as soon
//! as enough of its units are there, or at its last unit, or when the next frame starts. Frames that never came or
//! could not be rebuilt are reported to the console (CORRUPTFRAME, sent by the stream connection); the units per
//! frame go to the packet counts for the congestion reports.
//!
//! Recovery from lost frames, the reference's with its look into the bitstream (bitstream.rs): the last 16 frames
//! handed out are known as references. A P frame whose reference is not among them is not handed out (the decoder
//! would draw garbage from it), unless an older one it can point at instead is there (HEVC only, as in the
//! reference). After a frame FEC could not rebuild, a key frame is asked for (VideoEvent::RequestIdr, the reference's
//! "IDR on FEC failure") and the P frames until it comes are skipped. Deliberate differences: the reference's
//! setting for that is on here, without a choice; when no key frame has come after IDR_RETRY frames, it is asked
//! for again; a frame counts as a reference once handed out, where the reference waits for the decoder's answer; and a
//! fail-safe: a reference found missing while nothing was lost since the last key frame means the headers are misread,
//! and the reference check stays off for the stream (VideoStats::references_untrusted).

use std::collections::VecDeque;

use crate::bitstream::{self, Header, SliceType};
use crate::frame::{FlushResult, FrameProcessor, PacketStats};
use crate::seqnum::{gt16, lt16};
use crate::takion::AvPacket;

#[derive(Debug, PartialEq, Eq)]
pub enum VideoEvent {
    /// The stream switched to this resolution (an index into STREAMINFO's resolutions): its header goes to the
    /// decoder before the next frame.
    Profile(u8),
    /// A whole frame; fec when units came from FEC, frames_lost the frames lost since the last one delivered.
    Frame { index: u16, data: Vec<u8>, fec: bool, frames_lost: i32 },
    /// Frames start to end (inclusive) are missing or broken: the console is told.
    Corrupt { start: u16, end: u16 },
    /// A key frame is needed: the console is asked for one (IDRREQUEST).
    RequestIdr,
}

const REFERENCE_FRAMES: usize = 16;
/// Frames skipped while waiting for a key frame before it is asked for again.
const IDR_RETRY: u32 = 60;

#[derive(Clone, Copy, Debug, Default)]
pub struct VideoStats {
    pub frames: u64,
    pub bytes: u64,
    pub fec_recovered: u64,
    pub fec_failed: u64,
    pub frames_lost: i64,
    pub old_packets: u64,
    pub bad_profile: u64,
    pub bad_units: u64,
    pub idr_requests: u64,
    pub frames_skipped: u64,                  // P frames while waiting for a key frame
    pub missing_reference: u64,               // P frames whose reference was lost
    pub references_changed: u64,              // HEVC frames pointed at an older reference
    /// The look found a reference missing while nothing was lost: it misreads this stream's headers, so the
    /// reference check is off from then on (a fail-safe of our own).
    pub references_untrusted: bool,
}

pub struct VideoReceiver {
    headers: Vec<Option<Header>>,           // per resolution: its parameter sets, when they could be read
    profile_cur: Option<u8>,
    frame_index_cur: Option<u16>,           // the frame being filled
    frame_index_prev: Option<u16>,          // the last frame flushed, whole or not
    frame_index_prev_complete: u16,         // the last frame delivered
    processor: FrameProcessor,
    frames_lost: i32,
    references: VecDeque<u16>,              // the frames handed out, newest first
    waiting_for_idr: Option<u32>,           // frames skipped since the key frame was asked for
    loss_since_key: bool,                   // a frame lost or broken since the last key frame (or none came yet)
    pub stats: VideoStats,
}

impl VideoReceiver {
    /// headers: the parameter sets of each resolution in STREAMINFO (bitstream::header), None where they could not
    /// be read (that resolution's frames are passed on without a look).
    pub fn new(headers: Vec<Option<Header>>) -> Self {
        Self {
            headers,
            profile_cur: None,
            frame_index_cur: None,
            frame_index_prev: None,
            frame_index_prev_complete: 0,
            processor: FrameProcessor::new(),
            frames_lost: 0,
            references: VecDeque::with_capacity(REFERENCE_FRAMES),
            waiting_for_idr: None,
            loss_since_key: true,
            stats: VideoStats::default(),
        }
    }

    pub fn packet(&mut self, packet: &AvPacket, data: &[u8], packet_stats: &mut PacketStats) -> Vec<VideoEvent> {
        let mut events = Vec::new();
        let frame_index = packet.frame_index;
        if self.frame_index_cur.is_some_and(|cur| lt16(frame_index, cur)) {
            self.stats.old_packets += 1;
            return events;
        }

        if self.profile_cur != Some(packet.adaptive_stream_index) {
            if packet.adaptive_stream_index as usize >= self.headers.len() {
                self.stats.bad_profile += 1;
                return events;
            }
            self.profile_cur = Some(packet.adaptive_stream_index);
            events.push(VideoEvent::Profile(packet.adaptive_stream_index));
        }

        if self.frame_index_cur.is_none_or(|cur| gt16(frame_index, cur)) {
            let (received, lost) = self.processor.packet_counts();
            packet_stats.push_generation(received, lost);
            if self.frame_index_cur.is_some() && self.frame_index_prev != self.frame_index_cur {
                self.flush(&mut events);
            }
            let next_expected = self.frame_index_prev_complete.wrapping_add(1);
            if gt16(frame_index, next_expected) && !(frame_index == 1 && self.frame_index_cur.is_none()) {
                events.push(VideoEvent::Corrupt { start: next_expected, end: frame_index.wrapping_sub(1) });
                self.loss_since_key = true;
            }
            self.frame_index_cur = Some(frame_index);
            if self.processor.alloc_frame(packet, data).is_err() {
                self.stats.bad_units += 1;
            }
        }

        if self.processor.put_unit(packet, data).is_err() {
            self.stats.bad_units += 1;
        }

        if self.frame_index_cur != self.frame_index_prev
            && (self.processor.flush_possible() || packet.unit_index + 1 == packet.units_in_frame_total) {
            self.flush(&mut events);
        }
        events
    }

    fn flush(&mut self, events: &mut Vec<VideoEvent>) {
        let cur = self.frame_index_cur.expect("a frame to flush");
        let (result, data) = self.processor.flush();
        match result {
            FlushResult::Failed => {}
            FlushResult::FecFailed => {
                let next_expected = self.frame_index_prev_complete.wrapping_add(1);
                events.push(VideoEvent::Corrupt { start: next_expected, end: cur });
                // The reference's arithmetic: the frame numbers as plain integers, so across the wrap this is negative.
                let lost = cur as i32 - next_expected as i32 + 1;
                self.frames_lost += lost;
                self.stats.frames_lost += lost as i64;
                self.stats.fec_failed += 1;
                self.frame_index_prev = Some(cur);
                self.loss_since_key = true;
                if self.waiting_for_idr.is_none() {
                    self.request_idr(events);
                }
            }
            FlushResult::Success | FlushResult::FecSuccess => {
                self.frame_index_prev = Some(cur);
                let mut data = data;
                if !self.look(cur, &mut data, events) {
                    return;
                }
                let fec = result == FlushResult::FecSuccess;
                self.stats.frames += 1;
                self.stats.bytes += data.len() as u64;
                self.stats.fec_recovered += fec as u64;
                events.push(VideoEvent::Frame { index: cur, data, fec, frames_lost: self.frames_lost });
                self.frames_lost = 0;
                self.frame_index_prev_complete = cur;
                if self.references.len() == REFERENCE_FRAMES {
                    self.references.pop_back();
                }
                self.references.push_front(cur);
            }
        }
    }

    fn request_idr(&mut self, events: &mut Vec<VideoEvent>) {
        events.push(VideoEvent::RequestIdr);
        self.stats.idr_requests += 1;
        self.waiting_for_idr = Some(0);
    }

    /// The look into a whole frame: whether it is handed out. A key frame ends the wait for one; while waiting, P
    /// frames are skipped; a P frame without its reference is dropped, or (HEVC) pointed at an older one.
    fn look(&mut self, cur: u16, data: &mut [u8], events: &mut Vec<VideoEvent>) -> bool {
        let header = self.profile_cur.and_then(|p| self.headers.get(p as usize).copied().flatten());
        let Some(header) = header else { return true };
        let Some(slice) = bitstream::slice(data, &header) else { return true };
        if slice.slice_type == SliceType::I {
            self.loss_since_key = false;
        }
        if let Some(skipped) = self.waiting_for_idr {
            if slice.slice_type == SliceType::I {
                self.waiting_for_idr = None;
            } else {
                self.stats.frames_skipped += 1;
                self.waiting_for_idr = Some(skipped + 1);
                if skipped + 1 >= IDR_RETRY {
                    self.request_idr(events);
                }
                return false;
            }
        }
        if self.stats.references_untrusted {
            return true;
        }
        let Some(reference) = slice.reference_frame.filter(|_| slice.slice_type == SliceType::P) else { return true };
        let have = |back: u32| self.references.contains(&cur.wrapping_sub(back as u16).wrapping_sub(1));
        if have(reference) {
            return true;
        }
        if !self.loss_since_key {
            self.stats.references_untrusted = true;           // nothing was lost: the headers were misread
            return true;
        }
        let older = (reference + 1..REFERENCE_FRAMES as u32).find(|&back| have(back));
        if older.is_some_and(|back| bitstream::set_reference_frame(data, &header, back)) {
            self.stats.references_changed += 1;
            return true;
        }
        self.frames_lost += 1;
        self.stats.frames_lost += 1;
        self.stats.missing_reference += 1;
        false
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::bitstream;
    use crate::frame::tests::{packet, units};

    struct Console {
        receiver: VideoReceiver,
        stats: PacketStats,
    }

    impl Console {
        fn new() -> Self {
            Self { receiver: VideoReceiver::new(vec![None]), stats: PacketStats::default() }
        }

        /// Sends a frame's units, leaving out those in skip.
        fn frame(&mut self, index: u16, frame: &[u8], skip: &[usize]) -> Vec<VideoEvent> {
            let units = units(frame, 500, 2);
            let mut events = Vec::new();
            for (i, unit) in units.iter().enumerate().filter(|(i, _)| !skip.contains(i)) {
                events.extend(self.receiver.packet(&packet(index, i, units.len(), 2), unit, &mut self.stats));
            }
            events
        }
    }

    fn frame(seed: u8) -> Vec<u8> {
        (0..1200u32).map(|i| (i as u8).wrapping_mul(seed)).collect()
    }

    fn frames(events: &[VideoEvent]) -> Vec<(u16, bool, i32)> {
        events.iter().filter_map(|e| match e {
            VideoEvent::Frame { index, fec, frames_lost, .. } => Some((*index, *fec, *frames_lost)),
            _ => None,
        }).collect()
    }

    #[test]
    fn frames_in_order() {
        let mut console = Console::new();
        let events = console.frame(1, &frame(3), &[]);
        assert_eq!(events[0], VideoEvent::Profile(0));
        assert_eq!(events[1], VideoEvent::Frame { index: 1, data: frame(3), fec: false, frames_lost: 0 });
        assert_eq!(events.len(), 2);         // flushed once the source units were there; the FEC units only count
        assert_eq!(frames(&console.frame(2, &frame(5), &[])), [(2, false, 0)]);
        assert_eq!(console.stats.take(), (5, 0));
    }

    #[test]
    fn lost_unit_from_fec() {
        let mut console = Console::new();
        let events = console.frame(1, &frame(3), &[1]);
        assert_eq!(events[1], VideoEvent::Frame { index: 1, data: frame(3), fec: true, frames_lost: 0 });
        assert_eq!(console.receiver.stats.fec_recovered, 1);
    }

    #[test]
    fn lost_frames_are_reported() {
        let mut console = Console::new();
        console.frame(1, &frame(3), &[]);
        let events = console.frame(4, &frame(3), &[]);
        assert_eq!(events[0], VideoEvent::Corrupt { start: 2, end: 3 });
        assert_eq!(frames(&events), [(4, false, 0)]);

        // Too many units missing: the frame is reported and counted lost.
        let events = console.frame(5, &frame(3), &[0, 1, 2]);
        assert_eq!(events, [VideoEvent::Corrupt { start: 5, end: 5 }, VideoEvent::RequestIdr]);
        assert_eq!(frames(&console.frame(6, &frame(3), &[])), [(6, false, 1)]);
        assert_eq!((console.receiver.stats.fec_failed, console.receiver.stats.frames_lost), (1, 1));
    }

    #[test]
    fn old_packets_and_unknown_profiles_are_dropped() {
        let mut console = Console::new();
        console.frame(2, &frame(3), &[]);
        assert!(console.frame(1, &frame(3), &[]).is_empty());
        assert_eq!(console.receiver.stats.old_packets, 5);
        let mut other = packet(3, 0, 4, 2);
        other.adaptive_stream_index = 1;
        assert!(console.receiver.packet(&other, &[0, 0, 1], &mut console.stats).is_empty());
        assert_eq!(console.receiver.stats.bad_profile, 1);
    }

    // Recovery, with H.264 frames whose slice headers the look can read.

    fn h264(i_frame: bool, frame_num: u32, modification: Option<(u32, u32)>) -> Vec<u8> {
        let mut data = bitstream::tests::h264_frame(i_frame, frame_num, modification);
        data.resize(1200, 0xab);                    // three units of 500, so losing three is beyond FEC
        data
    }

    fn recovering() -> Console {
        let header = bitstream::header(&bitstream::tests::h264_header(2), false);
        assert!(header.is_some());
        Console { receiver: VideoReceiver::new(vec![header]), stats: PacketStats::default() }
    }

    #[test]
    fn a_frame_without_its_reference_is_not_handed_out() {
        let mut console = recovering();
        for (index, i_frame) in [(1, true), (2, false), (3, false)] {
            assert_eq!(frames(&console.frame(index, &h264(i_frame, index as u32, None), &[])).len(), 1);
        }
        // Frame 4 never comes: 5 and 6 refer to the frame before theirs, which is not there; 7 points back to 3.
        let events = console.frame(5, &h264(false, 5, None), &[]);
        assert_eq!(events, [VideoEvent::Corrupt { start: 4, end: 4 }]);
        assert!(frames(&console.frame(6, &h264(false, 6, None), &[])).is_empty());
        assert_eq!(frames(&console.frame(7, &h264(false, 7, Some((0, 3))), &[])), [(7, false, 2)]);
        assert_eq!(console.receiver.stats.missing_reference, 2);
        assert_eq!(console.receiver.stats.idr_requests, 0);             // missing frames ask for none
    }

    #[test]
    fn after_a_failed_fec_a_key_frame_is_asked_for_and_waited_for() {
        let mut console = recovering();
        console.frame(1, &h264(true, 1, None), &[]);
        console.frame(2, &h264(false, 2, None), &[]);
        let events = console.frame(3, &h264(false, 3, None), &[0, 1, 2]);   // three of five units: beyond FEC
        assert_eq!(events, [VideoEvent::Corrupt { start: 3, end: 3 }, VideoEvent::RequestIdr]);
        // P frames are skipped until the key frame; it is asked for once.
        for index in 4..8 {
            let events = console.frame(index, &h264(false, index as u32, None), &[]);
            assert!(frames(&events).is_empty() && !events.contains(&VideoEvent::RequestIdr), "{index}");
        }
        assert_eq!(frames(&console.frame(8, &h264(true, 8, None), &[])).len(), 1);
        assert_eq!(frames(&console.frame(9, &h264(false, 9, None), &[])), [(9, false, 0)]);
        let stats = console.receiver.stats;
        assert_eq!((stats.idr_requests, stats.frames_skipped, stats.fec_failed), (1, 4, 1));
    }

    #[test]
    fn a_key_frame_that_does_not_come_is_asked_for_again() {
        let mut console = recovering();
        console.frame(1, &h264(true, 1, None), &[]);
        console.frame(2, &h264(false, 2, None), &[0, 1, 2]);
        let requests = (3..3 + IDR_RETRY as u16 + 1)
            .map(|index| console.frame(index, &h264(false, index as u32, None), &[]))
            .filter(|events| events.contains(&VideoEvent::RequestIdr))
            .count();
        assert_eq!((requests, console.receiver.stats.idr_requests), (1, 2));
    }

    #[test]
    fn a_missing_reference_without_any_loss_turns_the_check_off() {
        let mut console = recovering();
        console.frame(1, &h264(true, 1, None), &[]);
        console.frame(2, &h264(false, 2, None), &[]);
        // Frame 3 says it refers to 5 frames back, which was never there, though nothing was lost: misread.
        assert_eq!(frames(&console.frame(3, &h264(false, 3, Some((0, 4))), &[])).len(), 1);
        assert!(console.receiver.stats.references_untrusted);
        assert_eq!(frames(&console.frame(4, &h264(false, 4, Some((0, 9))), &[])).len(), 1);
        assert_eq!(console.receiver.stats.missing_reference, 0);
    }
}
