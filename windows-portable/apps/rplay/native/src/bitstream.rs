// SPDX-License-Identifier: AGPL-3.0-only
//! A look into the video bitstream (the reference's bitstream.c): from the stream's header (the parameter sets of
//! STREAMINFO) and each frame's first slice header, whether a frame is a key frame (I) or depends on an earlier one
//! (P), and which earlier frame. With that the video receiver skips frames whose reference never arrived, and for
//! HEVC points a frame at an older reference it does have.
//!
//! Deliberate differences: H.264 slice headers are read as the standard writes them, with the parameter sets'
//! fields that decide which fields come (picture order count type, frame-only coding, the PPS's flags), where the
//! reference assumes the console's usual values and reads the reference count override with an extra bit; scaling
//! matrices in the SPS are skipped instead of refused. HEVC is the reference's, with every key frame type (BLA, IDR,
//! CRA) taken as a key frame, where the reference knows IDR_N_LP only.

/// What a frame's first slice says.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SliceType {
    I,
    P,
    Unknown,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Slice {
    pub slice_type: SliceType,
    /// For a P frame: how many frames back its reference is, less one (0: the frame before). None when the header
    /// does not say (the frame is not checked).
    pub reference_frame: Option<u32>,
}

/// Reads an RBSP (a NAL unit's payload without the emulation prevention bytes 00 00 03), and knows each bit's place
/// in the original data, so a bit can be changed in place.
pub struct Reader<'a> {
    data: &'a [u8],
    byte: usize,
    bit: u8,             // 0..8, from the most significant
    zeros: u8,           // zero bytes in a row just before `byte`
}

impl<'a> Reader<'a> {
    /// From the NAL unit's first byte after its header, at data[start].
    pub fn new(data: &'a [u8], start: usize) -> Self {
        let mut reader = Reader { data, byte: start, bit: 0, zeros: 0 };
        reader.skip_emulation();
        reader
    }

    fn skip_emulation(&mut self) {
        if self.zeros >= 2 && self.data.get(self.byte) == Some(&3) {
            self.byte += 1;
            self.zeros = 0;
        }
    }

    /// Where the next bit is in the data: (byte, bit from the most significant).
    pub fn position(&self) -> (usize, u8) {
        (self.byte, self.bit)
    }

    pub fn u1(&mut self) -> Option<u32> {
        let byte = *self.data.get(self.byte)?;
        let value = (byte >> (7 - self.bit)) & 1;
        self.bit += 1;
        if self.bit == 8 {
            self.bit = 0;
            self.zeros = if byte == 0 { self.zeros.saturating_add(1) } else { 0 };
            self.byte += 1;
            self.skip_emulation();
        }
        Some(value as u32)
    }

    pub fn u(&mut self, bits: u32) -> Option<u32> {
        (0..bits).try_fold(0u32, |value, _| Some((value << 1) | self.u1()?))
    }

    /// An unsigned Exp-Golomb number.
    pub fn ue(&mut self) -> Option<u32> {
        let mut zeros = 0;
        while self.u1()? == 0 {
            zeros += 1;
            if zeros > 31 {
                return None;
            }
        }
        Some(((1u64 << zeros) - 1 + self.u(zeros)? as u64) as u32)
    }

    /// A signed Exp-Golomb number.
    pub fn se(&mut self) -> Option<i32> {
        let k = self.ue()? as i64;
        Some(if k % 2 == 1 { (k + 1) / 2 } else { -(k / 2) } as i32)
    }
}

/// The NAL units of an Annex B stream: (offset of the NAL header, end), each after a 00 00 01 start code.
pub fn nal_units(data: &[u8]) -> Vec<(usize, usize)> {
    let mut starts = Vec::new();
    let mut i = 0;
    while i + 3 <= data.len() {
        if data[i] == 0 && data[i + 1] == 0 && data[i + 2] == 1 {
            starts.push(i + 3);
            i += 3;
        } else {
            i += 1;
        }
    }
    starts.iter().enumerate().map(|(n, &start)| {
        let mut end = starts.get(n + 1).map_or(data.len(), |next| next - 3);
        while end > start && data[end - 1] == 0 {
            end -= 1;                                   // the next start code's leading zero, or trailing zeros
        }
        (start, end)
    }).collect()
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct H264Sps {
    pub separate_colour_plane: bool,
    pub log2_max_frame_num: u32,
    pub poc_type: u32,
    pub log2_max_poc_lsb: u32,
    pub delta_pic_order_always_zero: bool,
    pub frame_mbs_only: bool,
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct H264Pps {
    pub bottom_field_pic_order_in_frame_present: bool,
    pub redundant_pic_cnt_present: bool,
}

fn skip_scaling_list(r: &mut Reader, size: usize) -> Option<()> {
    let (mut last, mut next) = (8i32, 8i32);
    for _ in 0..size {
        if next != 0 {
            next = (last + r.se()? + 256) % 256;
        }
        last = if next == 0 { last } else { next };
    }
    Some(())
}

const HIGH_PROFILES: [u32; 13] = [100, 110, 122, 244, 44, 83, 86, 118, 128, 138, 139, 134, 135];

pub fn h264_sps(r: &mut Reader) -> Option<H264Sps> {
    let profile_idc = r.u(8)?;
    r.u(8)?;                                            // constraint flags and reserved bits
    r.u(8)?;                                            // level_idc
    r.ue()?;                                            // seq_parameter_set_id
    let mut sps = H264Sps::default();
    if HIGH_PROFILES.contains(&profile_idc) {
        let chroma_format_idc = r.ue()?;
        if chroma_format_idc == 3 {
            sps.separate_colour_plane = r.u1()? == 1;
        }
        r.ue()?;                                        // bit_depth_luma_minus8
        r.ue()?;                                        // bit_depth_chroma_minus8
        r.u1()?;                                        // qpprime_y_zero_transform_bypass_flag
        if r.u1()? == 1 {                               // seq_scaling_matrix_present_flag
            for i in 0..if chroma_format_idc == 3 { 12 } else { 8 } {
                if r.u1()? == 1 {
                    skip_scaling_list(r, if i < 6 { 16 } else { 64 })?;
                }
            }
        }
    }
    sps.log2_max_frame_num = r.ue()? + 4;
    if sps.log2_max_frame_num > 16 {
        return None;
    }
    sps.poc_type = r.ue()?;
    match sps.poc_type {
        0 => {
            sps.log2_max_poc_lsb = r.ue()? + 4;
            if sps.log2_max_poc_lsb > 16 {
                return None;
            }
        }
        1 => {
            sps.delta_pic_order_always_zero = r.u1()? == 1;
            r.se()?;                                    // offset_for_non_ref_pic
            r.se()?;                                    // offset_for_top_to_bottom_field
            for _ in 0..r.ue()? {                       // num_ref_frames_in_pic_order_cnt_cycle
                r.se()?;
            }
        }
        2 => {}
        _ => return None,
    }
    r.ue()?;                                            // max_num_ref_frames
    r.u1()?;                                            // gaps_in_frame_num_value_allowed_flag
    r.ue()?;                                            // pic_width_in_mbs_minus1
    r.ue()?;                                            // pic_height_in_map_units_minus1
    sps.frame_mbs_only = r.u1()? == 1;
    Some(sps)
}

pub fn h264_pps(r: &mut Reader) -> Option<H264Pps> {
    r.ue()?;                                            // pic_parameter_set_id
    r.ue()?;                                            // seq_parameter_set_id
    r.u1()?;                                            // entropy_coding_mode_flag
    let bottom_field_pic_order_in_frame_present = r.u1()? == 1;
    if r.ue()? != 0 {                                   // num_slice_groups_minus1: slice groups are not followed
        return None;
    }
    r.ue()?;                                            // num_ref_idx_l0_default_active_minus1
    r.ue()?;                                            // num_ref_idx_l1_default_active_minus1
    r.u1()?;                                            // weighted_pred_flag
    r.u(2)?;                                            // weighted_bipred_idc
    r.se()?;                                            // pic_init_qp_minus26
    r.se()?;                                            // pic_init_qs_minus26
    r.se()?;                                            // chroma_qp_index_offset
    r.u1()?;                                            // deblocking_filter_control_present_flag
    r.u1()?;                                            // constrained_intra_pred_flag
    let redundant_pic_cnt_present = r.u1()? == 1;
    Some(H264Pps { bottom_field_pic_order_in_frame_present, redundant_pic_cnt_present })
}

pub fn h264_slice(r: &mut Reader, nal_type: u8, sps: &H264Sps, pps: &H264Pps) -> Option<Slice> {
    r.ue()?;                                            // first_mb_in_slice
    let raw_type = r.ue()? % 5;
    let slice_type = match raw_type {
        0 => SliceType::P,
        2 => SliceType::I,
        _ => SliceType::Unknown,                        // B, SP, SI: the console sends none
    };
    if slice_type != SliceType::P {
        return Some(Slice { slice_type, reference_frame: None });
    }
    r.ue()?;                                            // pic_parameter_set_id
    if sps.separate_colour_plane {
        r.u(2)?;                                        // colour_plane_id
    }
    r.u(sps.log2_max_frame_num)?;                       // frame_num
    let mut field_pic = false;
    if !sps.frame_mbs_only {
        field_pic = r.u1()? == 1;
        if field_pic {
            r.u1()?;                                    // bottom_field_flag
        }
    }
    if nal_type == 5 {
        r.ue()?;                                        // idr_pic_id
    }
    if sps.poc_type == 0 {
        r.u(sps.log2_max_poc_lsb)?;                     // pic_order_cnt_lsb
        if pps.bottom_field_pic_order_in_frame_present && !field_pic {
            r.se()?;                                    // delta_pic_order_cnt_bottom
        }
    }
    if sps.poc_type == 1 && !sps.delta_pic_order_always_zero {
        r.se()?;                                        // delta_pic_order_cnt[0]
        if pps.bottom_field_pic_order_in_frame_present && !field_pic {
            r.se()?;                                    // delta_pic_order_cnt[1]
        }
    }
    if pps.redundant_pic_cnt_present {
        r.ue()?;                                        // redundant_pic_cnt
    }
    if r.u1()? == 1 {                                   // num_ref_idx_active_override_flag
        r.ue()?;                                        // num_ref_idx_l0_active_minus1
    }
    let mut reference_frame = Some(0);                  // without a modification: the frame before
    if r.u1()? == 1 {                                   // ref_pic_list_modification_flag_l0
        // The first entry says which picture comes first: subtracting abs_diff_pic_num_minus1 + 1 from this frame's
        // number (idc 0) is the frame that many back; any other first entry is not followed.
        reference_frame = match r.ue()? {
            0 => Some(r.ue()?),
            _ => None,
        };
    }
    Some(Slice { slice_type, reference_frame })
}

/// The stream's parameter sets: H.264's SPS and PPS, or HEVC's SPS field the slices need.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Header {
    H264(H264Sps, H264Pps),
    Hevc { log2_max_poc_lsb: u32 },
}

/// The parameter sets of a stream header (STREAMINFO's): None when they cannot be read, and the frames are then
/// passed on without a look.
pub fn header(data: &[u8], hevc: bool) -> Option<Header> {
    if hevc {
        return hevc_header(data);
    }
    let (mut sps, mut pps) = (None, None);
    for (start, end) in nal_units(data) {
        let unit = &data[..end];
        match unit.get(start)? & 0x1f {
            7 => sps = h264_sps(&mut Reader::new(unit, start + 1)),
            8 => pps = h264_pps(&mut Reader::new(unit, start + 1)),
            _ => {}
        }
    }
    Some(Header::H264(sps?, pps?))
}

fn hevc_header(data: &[u8]) -> Option<Header> {
    for (start, end) in nal_units(data) {
        let unit = &data[..end];
        if (unit.get(start)? >> 1) & 0x3f != 33 {       // not the SPS (the VPS comes first)
            continue;
        }
        let r = &mut Reader::new(unit, start + 2);
        r.u(4)?;                                        // sps_video_parameter_set_id
        if r.u(3)? != 0 {                               // sps_max_sub_layers_minus1: sub-layers are not followed
            return None;
        }
        r.u1()?;                                        // sps_temporal_id_nesting_flag
        r.u(8)?;                                        // general_profile_space, tier and profile_idc
        r.u(32)?;                                       // general_profile_compatibility_flags
        r.u(4)?;                                        // progressive, interlaced, non-packed, frame-only
        r.u(32)?;
        r.u(11)?;                                       // general_reserved_zero_43bits
        r.u1()?;                                        // general_inbld_flag
        r.u(8)?;                                        // general_level_idc
        r.ue()?;                                        // sps_seq_parameter_set_id
        if r.ue()? == 3 {                               // chroma_format_idc
            r.u1()?;                                    // separate_colour_plane_flag
        }
        r.ue()?;                                        // pic_width_in_luma_samples
        r.ue()?;                                        // pic_height_in_luma_samples
        if r.u1()? == 1 {                               // conformance_window_flag
            for _ in 0..4 {
                r.ue()?;
            }
        }
        r.ue()?;                                        // bit_depth_luma_minus8
        r.ue()?;                                        // bit_depth_chroma_minus8
        let log2_max_poc_lsb = r.ue()? + 4;
        return (log2_max_poc_lsb <= 16).then_some(Header::Hevc { log2_max_poc_lsb });
    }
    None
}

/// HEVC's key frame NAL unit types (BLA, IDR, CRA); the reference knows IDR_N_LP (20) only.
const IRAP: std::ops::RangeInclusive<u8> = 16..=21;

/// The first slice of a frame: None when the frame has none that can be read.
pub fn slice(frame: &[u8], header: &Header) -> Option<Slice> {
    for (start, end) in nal_units(frame) {
        let unit = &frame[..end];
        match header {
            Header::H264(sps, pps) => {
                let nal_type = unit.get(start)? & 0x1f;
                if nal_type == 1 || nal_type == 5 {
                    return h264_slice(&mut Reader::new(unit, start + 1), nal_type, sps, pps);
                }
            }
            Header::Hevc { log2_max_poc_lsb } => {
                let nal_type = (unit.get(start)? >> 1) & 0x3f;
                if nal_type == 1 || IRAP.contains(&nal_type) {
                    return hevc_slice(&mut Reader::new(unit, start + 2), nal_type, *log2_max_poc_lsb).map(|(s, _)| s);
                }
            }
        }
    }
    None
}

/// The reference's HEVC slice header up to the short-term reference picture set; also where each
/// used_by_curr_pic_s0_flag is, for set_reference_frame.
fn hevc_slice(r: &mut Reader, nal_type: u8, log2_max_poc_lsb: u32) -> Option<(Slice, Vec<(usize, u8)>)> {
    let first_slice_segment_in_pic = r.u1()? == 1;
    if IRAP.contains(&nal_type) {
        r.u1()?;                                        // no_output_of_prior_pics_flag
    }
    r.ue()?;                                            // slice_pic_parameter_set_id
    if !first_slice_segment_in_pic {
        r.ue()?;                                        // slice_segment_address
    }
    let slice_type = match r.ue()? {
        1 => SliceType::P,
        2 => SliceType::I,
        _ => SliceType::Unknown,
    };
    let mut flags = Vec::new();
    let mut reference_frame = None;
    if nal_type == 1 {
        r.u(log2_max_poc_lsb)?;                         // slice_pic_order_cnt_lsb
        if r.u1()? == 0 {                               // short_term_ref_pic_set_sps_flag
            let negative = r.ue()?;
            if negative > 16 {
                return None;
            }
            r.ue()?;                                    // num_positive_pics
            for i in 0..negative {
                r.ue()?;                                // delta_poc_s0_minus1
                flags.push(r.position());
                if r.u1()? == 1 && reference_frame.is_none() {
                    reference_frame = Some(i);
                }
            }
        }
    }
    Some((Slice { slice_type, reference_frame }, flags))
}

/// HEVC: points a P frame's first slice at the reference *reference_frame* frames back, by setting that one's
/// used_by_curr_pic_s0_flag and clearing those before it, in place. False when the frame cannot be changed (H.264
/// has no such change, as in the reference).
pub fn set_reference_frame(frame: &mut [u8], header: &Header, reference_frame: u32) -> bool {
    let Header::Hevc { log2_max_poc_lsb } = header else { return false };
    for (start, end) in nal_units(frame) {
        let nal_type = (frame[start] >> 1) & 0x3f;
        if nal_type != 1 {
            continue;
        }
        let Some((slice, flags)) = hevc_slice(&mut Reader::new(&frame[..end], start + 2), nal_type, *log2_max_poc_lsb)
        else {
            return false;
        };
        if slice.slice_type != SliceType::P || reference_frame as usize >= flags.len() {
            return false;
        }
        for (i, (byte, bit)) in flags.iter().enumerate().take(reference_frame as usize + 1) {
            let mask = 0x80 >> bit;
            if i == reference_frame as usize {
                frame[*byte] |= mask;
            } else {
                frame[*byte] &= !mask;
            }
        }
        return true;
    }
    false
}

#[cfg(test)]
pub(crate) mod tests {
    use super::*;

    /// Writes bits, Exp-Golomb numbers and emulation prevention, to make headers for the tests.
    #[derive(Default)]
    pub struct Writer {
        bits: Vec<u8>,
    }

    impl Writer {
        pub fn u(&mut self, bits: u32, value: u32) -> &mut Self {
            for i in (0..bits).rev() {
                self.bits.push(((value >> i) & 1) as u8);
            }
            self
        }

        pub fn ue(&mut self, value: u32) -> &mut Self {
            let code = value as u64 + 1;
            let len = 64 - code.leading_zeros();
            self.u(len - 1, 0);
            for i in (0..len).rev() {
                self.bits.push(((code >> i) & 1) as u8);
            }
            self
        }

        pub fn se(&mut self, value: i32) -> &mut Self {
            self.ue(if value > 0 { 2 * value as u32 - 1 } else { (-2 * value) as u32 })
        }

        /// A NAL unit: start code, header byte(s), the bits with a stop bit, emulation prevention.
        pub fn nal(&mut self, header: &[u8]) -> Vec<u8> {
            self.bits.push(1);
            while !self.bits.len().is_multiple_of(8) {
                self.bits.push(0);
            }
            let payload: Vec<u8> = self.bits.chunks(8).map(|c| c.iter().fold(0, |b, bit| (b << 1) | bit)).collect();
            let mut out = vec![0, 0, 0, 1];
            out.extend_from_slice(header);
            let mut zeros = 0;
            for byte in payload {
                if zeros >= 2 && byte <= 3 {
                    out.push(3);
                    zeros = 0;
                }
                zeros = if byte == 0 { zeros + 1 } else { 0 };
                out.push(byte);
            }
            out
        }
    }

    /// An H.264 SPS and PPS: baseline-like, frame_num 8 bits, POC type 2, frames only (as consoles send).
    pub fn h264_header(poc_type: u32) -> Vec<u8> {
        let mut sps = Writer::default();
        sps.u(8, 77).u(8, 0).u(8, 42).ue(0).ue(4).ue(poc_type);
        if poc_type == 0 {
            sps.ue(2);                                  // log2_max_poc_lsb 6
        }
        sps.ue(4).u(1, 0).ue(119).ue(67).u(1, 1);
        let mut pps = Writer::default();
        pps.ue(0).ue(0).u(1, 1).u(1, 0).ue(0).ue(0).ue(0).u(1, 0).u(2, 0).se(0).se(0).se(0).u(1, 1).u(1, 0).u(1, 0);
        [sps.nal(&[0x67]), pps.nal(&[0x68])].concat()
    }

    pub fn h264_frame(i_frame: bool, frame_num: u32, modification: Option<(u32, u32)>) -> Vec<u8> {
        let mut w = Writer::default();
        w.ue(0).ue(if i_frame { 7 } else { 5 }).ue(0).u(8, frame_num);
        if i_frame {
            w.ue(0);                                    // idr_pic_id
        } else {
            w.u(1, 0);                                  // num_ref_idx_active_override_flag
            match modification {
                None => {
                    w.u(1, 0);
                }
                Some((idc, value)) => {
                    w.u(1, 1).ue(idc).ue(value).ue(3);
                }
            }
        }
        w.ue(5);                                        // the rest of the slice, as far as the look goes
        let mut frame = vec![0, 0, 0, 1, 0x09, 0xf0];   // an access unit delimiter first
        frame.extend(w.nal(&[if i_frame { 0x65 } else { 0x41 }]));
        frame
    }

    #[test]
    fn exp_golomb_and_emulation_prevention() {
        let mut w = Writer::default();
        w.ue(0).ue(1).ue(7).se(-3).se(4).u(16, 0).u(8, 0x01).ue(300);
        let nal = w.nal(&[0x41]);
        assert!(nal.windows(3).any(|b| b == [0, 0, 3]));               // 00 00 01 inside got its 03
        let mut r = Reader::new(&nal, 5);
        assert_eq!((r.ue(), r.ue(), r.ue(), r.se(), r.se()), (Some(0), Some(1), Some(7), Some(-3), Some(4)));
        assert_eq!((r.u(16), r.u(8), r.ue()), (Some(0), Some(1), Some(300)));
    }

    #[test]
    fn h264_frames_by_type_and_reference() {
        for poc_type in [0, 2] {
            let header = header(&h264_header(poc_type), false).expect("SPS and PPS");
            let Header::H264(sps, _) = header else { panic!() };
            assert_eq!((sps.log2_max_frame_num, sps.poc_type, sps.frame_mbs_only), (8, poc_type, true));
            let mut frame = Writer::default();
            frame.ue(0).ue(5).ue(0).u(8, 3);
            if poc_type == 0 {
                frame.u(6, 6);
            }
            frame.u(1, 0).u(1, 1).ue(0).ue(2).ue(3).ue(5);
            let mut data = vec![0, 0, 0, 1, 0x09, 0xf0];
            data.extend(frame.nal(&[0x41]));
            assert_eq!(slice(&data, &header), Some(Slice { slice_type: SliceType::P, reference_frame: Some(2) }));
        }
        let header = header(&h264_header(2), false).unwrap();
        assert_eq!(slice(&h264_frame(true, 0, None), &header).unwrap().slice_type, SliceType::I);
        assert_eq!(slice(&h264_frame(false, 1, None), &header).unwrap().reference_frame, Some(0));
        assert_eq!(slice(&h264_frame(false, 1, Some((0, 4))), &header).unwrap().reference_frame, Some(4));
        assert_eq!(slice(&h264_frame(false, 1, Some((1, 4))), &header).unwrap().reference_frame, None);
        assert_eq!(slice(&[1, 2, 3], &header), None);
        assert!(!set_reference_frame(&mut h264_frame(false, 1, None), &header, 1));
    }

    #[test]
    fn console_frames_are_p_frames() {
        // Frames recorded from a console (the FEC vectors): each begins with the unit header, then an H.264 slice
        // NAL unit (41 9a ...: a P slice). Without the console's SPS only the slice type can be read.
        let v: serde_json::Value =
            serde_json::from_str(include_str!("../../tests/fec_vectors.json")).expect("valid vectors");
        for case in v["cases"].as_array().unwrap() {
            let frame = crate::vectors::base64(case["frame"].as_str().unwrap());
            let (start, _) = nal_units(&frame)[0];
            assert_eq!(frame[start] & 0x1f, 1, "a non-IDR slice");
            let r = &mut Reader::new(&frame, start + 1);
            assert_eq!((r.ue(), r.ue().map(|t| t % 5)), (Some(0), Some(0)), "first_mb 0, a P slice");
        }
    }

    #[test]
    fn encoded_clips_have_a_key_frame_every_six() {
        // The decoder's clips (x264 and x265, a key frame every 6, no B-frames): the parameter sets come with the
        // first sample.
        let v: serde_json::Value =
            serde_json::from_str(include_str!("../../tests/video_vectors.json")).expect("valid vectors");
        for (name, clip) in v["clips"].as_object().unwrap() {
            let samples: Vec<Vec<u8>> =
                clip["samples"].as_array().unwrap().iter().map(|s| crate::vectors::base64(s.as_str().unwrap())).collect();
            let header = header(&samples[0], name == "hevc").unwrap_or_else(|| panic!("{name}: parameter sets"));
            let types: Vec<SliceType> = samples.iter().map(|s| slice(s, &header).expect("a slice").slice_type).collect();
            let expected: Vec<SliceType> =
                (0..samples.len()).map(|i| if i % 6 == 0 { SliceType::I } else { SliceType::P }).collect();
            assert_eq!(types, expected, "{name}");
            if name == "h264" {
                assert!(samples[1..6].iter().all(|s| slice(s, &header).unwrap().reference_frame == Some(0)));
            }
        }
    }

    #[test]
    fn hevc_reference_frame_changed_in_place() {
        let mut sps = Writer::default();
        sps.u(4, 0).u(3, 0).u(1, 1).u(8, 1).u(32, 0x6000_0000).u(4, 0b1001).u(32, 0).u(11, 0).u(1, 0).u(8, 120)
            .ue(0).ue(1).ue(1920).ue(1080).u(1, 0).ue(0).ue(0).ue(4);
        let header_data = [Writer::default().u(8, 0).nal(&[0x40, 0x01]), sps.nal(&[0x42, 0x01])].concat();
        let header = header(&header_data, true).unwrap();
        assert_eq!(header, Header::Hevc { log2_max_poc_lsb: 8 });
        let mut w = Writer::default();
        w.u(1, 1).ue(0).ue(1).u(8, 9).u(1, 0).ue(3).ue(0);
        for flag in [1, 0, 0] {
            w.ue(0).u(1, flag);                         // delta_poc_s0_minus1, used_by_curr_pic_s0_flag
        }
        w.ue(4);
        let mut frame = w.nal(&[0x02, 0x01]);
        assert_eq!(slice(&frame, &header), Some(Slice { slice_type: SliceType::P, reference_frame: Some(0) }));
        assert!(set_reference_frame(&mut frame, &header, 2));
        assert_eq!(slice(&frame, &header), Some(Slice { slice_type: SliceType::P, reference_frame: Some(2) }));
        assert!(!set_reference_frame(&mut frame, &header, 3));                    // only three are listed
    }
}
