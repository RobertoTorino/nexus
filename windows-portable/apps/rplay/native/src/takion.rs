// SPDX-License-Identifier: AGPL-3.0-only
//! Takion packets: the transport of the stream over UDP 9296, modelled on SCTP.
//!
//! The low nibble of the first byte is the packet type. Control packets carry one message: a 16-byte header (the
//! peer's tag, the GMAC, the low 32 bits of the key position, chunk type and flags, size) and a payload. Video and
//! audio packets have their own header (three layouts: version 7 for the network test, 9 for a PS4, 12 for a PS5).
//! Every packet type with a key position carries a 4-byte GMAC at a fixed offset, computed with that field zeroed.

use crate::gkcrypt::{GkCrypt, BLOCK_SIZE, GMAC_SIZE};
use crate::keystate::KeyState;

pub const PACKET_CONTROL: u8 = 0;
pub const PACKET_FEEDBACK_HISTORY: u8 = 1;
pub const PACKET_VIDEO: u8 = 2;
pub const PACKET_AUDIO: u8 = 3;
pub const PACKET_HANDSHAKE: u8 = 4;
pub const PACKET_CONGESTION: u8 = 5;
pub const PACKET_FEEDBACK_STATE: u8 = 6;
pub const PACKET_CLIENT_INFO: u8 = 8;
pub const BASE_TYPE_MASK: u8 = 0xf;

pub const CHUNK_DATA: u8 = 0;
pub const CHUNK_INIT: u8 = 1;
pub const CHUNK_INIT_ACK: u8 = 2;
pub const CHUNK_DATA_ACK: u8 = 3;
pub const CHUNK_COOKIE: u8 = 0xa;
pub const CHUNK_COOKIE_ACK: u8 = 0xb;

pub const DATA_TYPE_PROTOBUF: u8 = 0;
pub const DATA_TYPE_RUMBLE: u8 = 7;
pub const DATA_TYPE_PAD_INFO: u8 = 9;
pub const DATA_TYPE_TRIGGER_EFFECTS: u8 = 11;

pub const MESSAGE_HEADER_SIZE: usize = 0x10;
pub const COOKIE_SIZE: usize = 0x20;
pub const A_RWND: u32 = 0x19000;
pub const OUTBOUND_STREAMS: u16 = 0x64;
pub const INBOUND_STREAMS: u16 = 0x64;
pub const CONGESTION_PACKET_SIZE: usize = 0xf;

#[derive(Debug, PartialEq, Eq, Clone, Copy)]
pub enum TakionError {
    TooSmall,
    InvalidData,
    TagMismatch,
    SizeMismatch,
    MacMismatch,
}

fn be16(buf: &[u8], at: usize) -> u16 {
    u16::from_be_bytes([buf[at], buf[at + 1]])
}

fn be32(buf: &[u8], at: usize) -> u32 {
    u32::from_be_bytes(buf[at..at + 4].try_into().unwrap())
}

pub fn mac_offset(base_type: u8) -> Option<usize> {
    match base_type {
        PACKET_CONTROL => Some(5),
        PACKET_VIDEO | PACKET_AUDIO => Some(0xa),
        PACKET_CONGESTION => Some(7),
        _ => None,
    }
}

pub fn key_pos_offset(base_type: u8) -> Option<usize> {
    match base_type {
        PACKET_CONTROL => Some(9),
        PACKET_VIDEO | PACKET_AUDIO => Some(0xe),
        PACKET_CONGESTION => Some(0xb),
        _ => None,
    }
}

/// How far the local key position moves for data_size bytes. The reference adds data_size % 16, which is not a
/// rounding up to whole blocks; the console expects these positions, so it is kept.
pub fn key_pos_advance(data_size: usize) -> u64 {
    (data_size + data_size % BLOCK_SIZE) as u64
}

/// Puts the GMAC into a packet (zeroes when there is no crypto yet) and returns it with the MAC that was there.
pub fn packet_mac(crypt: Option<&mut GkCrypt>, buf: &mut [u8], key_pos: u64) -> Result<([u8; GMAC_SIZE], [u8; GMAC_SIZE]), TakionError> {
    let base_type = *buf.first().ok_or(TakionError::TooSmall)? & BASE_TYPE_MASK;
    let (mac_at, key_at) = match (mac_offset(base_type), key_pos_offset(base_type)) {
        (Some(mac), Some(key)) => (mac, key),
        _ => return Err(TakionError::InvalidData),
    };
    if buf.len() < mac_at + GMAC_SIZE || buf.len() < key_at + 4 {
        return Err(TakionError::TooSmall);
    }
    let old: [u8; GMAC_SIZE] = buf[mac_at..mac_at + GMAC_SIZE].try_into().unwrap();
    buf[mac_at..mac_at + GMAC_SIZE].fill(0);
    if let Some(crypt) = crypt {
        // Control and congestion packets are signed with their key position zeroed too.
        let hide_key_pos = base_type == PACKET_CONTROL || base_type == PACKET_CONGESTION;
        let key_field: [u8; 4] = buf[key_at..key_at + 4].try_into().unwrap();
        if hide_key_pos {
            buf[key_at..key_at + 4].fill(0);
        }
        let mac = crypt.gmac(key_pos, buf);
        if hide_key_pos {
            buf[key_at..key_at + 4].copy_from_slice(&key_field);
        }
        buf[mac_at..mac_at + GMAC_SIZE].copy_from_slice(&mac);
    }
    let mac = buf[mac_at..mac_at + GMAC_SIZE].try_into().unwrap();
    Ok((mac, old))
}

/// Checks a received packet's GMAC; on success the key position is committed and returned. Without crypto (before
/// the key exchange) every packet passes, as in the reference.
pub fn verify_packet(crypt: Option<&mut GkCrypt>, key_state: &mut KeyState, buf: &mut [u8]) -> Result<u64, TakionError> {
    let Some(crypt) = crypt else { return Ok(0) };
    let base_type = *buf.first().ok_or(TakionError::TooSmall)? & BASE_TYPE_MASK;
    let key_at = key_pos_offset(base_type).ok_or(TakionError::InvalidData)?;
    if buf.len() < key_at + 4 {
        return Err(TakionError::TooSmall);
    }
    let key_pos = key_state.request_pos(be32(buf, key_at), false);
    let (expected, received) = packet_mac(Some(crypt), buf, key_pos)?;
    if expected != received {
        return Err(TakionError::MacMismatch);
    }
    key_state.commit(key_pos);
    Ok(key_pos)
}

/// A control packet with one message: the type byte, the message header and the payload.
pub fn message_packet(tag: u32, key_pos: u64, chunk_type: u8, chunk_flags: u8, payload: &[u8]) -> Vec<u8> {
    let mut buf = Vec::with_capacity(1 + MESSAGE_HEADER_SIZE + payload.len());
    buf.push(PACKET_CONTROL);
    buf.extend_from_slice(&tag.to_be_bytes());
    buf.extend_from_slice(&[0; GMAC_SIZE]);
    buf.extend_from_slice(&(key_pos as u32).to_be_bytes());
    buf.push(chunk_type);
    buf.push(chunk_flags);
    buf.extend_from_slice(&((payload.len() + 4) as u16).to_be_bytes());
    buf.extend_from_slice(payload);
    buf
}

#[derive(Debug, PartialEq, Eq)]
pub struct Message<'a> {
    pub tag: u32,
    pub key_pos: u64,
    pub chunk_type: u8,
    pub chunk_flags: u8,
    pub payload: &'a [u8],
}

/// A message (the control packet without its type byte), addressed to tag_local.
pub fn parse_message<'a>(buf: &'a [u8], tag_local: u32, key_state: &mut KeyState) -> Result<Message<'a>, TakionError> {
    if buf.len() < MESSAGE_HEADER_SIZE {
        return Err(TakionError::TooSmall);
    }
    let tag = be32(buf, 0);
    let key_pos = key_state.request_pos(be32(buf, 8), true);
    let size = be16(buf, 0xe) as usize;
    if tag != tag_local {
        return Err(TakionError::TagMismatch);
    }
    if buf.len() != size + 0xc || size < 4 {
        return Err(TakionError::SizeMismatch);
    }
    Ok(Message { tag, key_pos, chunk_type: buf[0xc], chunk_flags: buf[0xd], payload: &buf[0x10..] })
}

#[derive(Debug, PartialEq, Eq, Clone)]
pub struct Init {
    pub tag: u32,
    pub a_rwnd: u32,
    pub outbound_streams: u16,
    pub inbound_streams: u16,
    pub initial_seq_num: u32,
    pub cookie: Vec<u8>,                // only in INIT_ACK
}

/// INIT: sent before the peer's tag is known, so to tag 0, unsigned.
pub fn init_packet(tag_local: u32, initial_seq_num: u32) -> Vec<u8> {
    let mut payload = Vec::with_capacity(0x10);
    payload.extend_from_slice(&tag_local.to_be_bytes());
    payload.extend_from_slice(&A_RWND.to_be_bytes());
    payload.extend_from_slice(&OUTBOUND_STREAMS.to_be_bytes());
    payload.extend_from_slice(&INBOUND_STREAMS.to_be_bytes());
    payload.extend_from_slice(&initial_seq_num.to_be_bytes());
    message_packet(0, 0, CHUNK_INIT, 0, &payload)
}

pub fn parse_init_ack(message: &Message) -> Result<Init, TakionError> {
    if message.chunk_type != CHUNK_INIT_ACK || message.chunk_flags != 0 {
        return Err(TakionError::InvalidData);
    }
    let p = message.payload;
    if p.len() != 0x10 + COOKIE_SIZE {
        return Err(TakionError::SizeMismatch);
    }
    let init = Init {
        tag: be32(p, 0),
        a_rwnd: be32(p, 4),
        outbound_streams: be16(p, 8),
        inbound_streams: be16(p, 0xa),
        initial_seq_num: be32(p, 0xc),
        cookie: p[0x10..].to_vec(),
    };
    // The reference's checks: a tag, and stream counts that fit ours.
    if init.tag == 0
        || init.outbound_streams == 0
        || init.inbound_streams == 0
        || init.outbound_streams > INBOUND_STREAMS
        || init.inbound_streams < OUTBOUND_STREAMS
    {
        return Err(TakionError::InvalidData);
    }
    Ok(init)
}

pub fn cookie_packet(tag_remote: u32, cookie: &[u8]) -> Vec<u8> {
    message_packet(tag_remote, 0, CHUNK_COOKIE, 0, cookie)
}

/// A DATA message: sequence number, channel, two zero bytes, the data type (0: protobuf) and the data. The GMAC is
/// added by packet_mac when it is sent.
pub fn data_packet(tag_remote: u32, key_pos: u64, chunk_flags: u8, seq_num: u32, channel: u16, data: &[u8]) -> Vec<u8> {
    let mut payload = Vec::with_capacity(9 + data.len());
    payload.extend_from_slice(&seq_num.to_be_bytes());
    payload.extend_from_slice(&channel.to_be_bytes());
    payload.extend_from_slice(&[0, 0, DATA_TYPE_PROTOBUF]);
    payload.extend_from_slice(data);
    message_packet(tag_remote, key_pos, CHUNK_DATA, chunk_flags, &payload)
}

/// A DATA message that continues the previous one (a protobuf message split over several packets): sequence number,
/// channel, two zero bytes and the data, without a data type.
pub fn data_cont_packet(tag_remote: u32, key_pos: u64, chunk_flags: u8, seq_num: u32, channel: u16, data: &[u8]) -> Vec<u8> {
    let mut payload = Vec::with_capacity(8 + data.len());
    payload.extend_from_slice(&seq_num.to_be_bytes());
    payload.extend_from_slice(&channel.to_be_bytes());
    payload.extend_from_slice(&[0, 0]);
    payload.extend_from_slice(data);
    message_packet(tag_remote, key_pos, CHUNK_DATA, chunk_flags, &payload)
}

pub fn data_ack_packet(tag_remote: u32, key_pos: u64, seq_num: u32, a_rwnd: u32) -> Vec<u8> {
    let mut payload = Vec::with_capacity(0xc);
    payload.extend_from_slice(&seq_num.to_be_bytes());
    payload.extend_from_slice(&a_rwnd.to_be_bytes());
    payload.extend_from_slice(&[0; 4]);
    message_packet(tag_remote, key_pos, CHUNK_DATA_ACK, 0, &payload)
}

#[derive(Debug, PartialEq, Eq)]
pub struct Data<'a> {
    pub seq_num: u32,
    pub channel: u16,
    pub data_type: u8,
    pub data: &'a [u8],
}

pub fn parse_data<'a>(message: &Message<'a>) -> Result<Data<'a>, TakionError> {
    let p = message.payload;
    if message.chunk_type != CHUNK_DATA {
        return Err(TakionError::InvalidData);
    }
    if p.len() < 9 {
        return Err(TakionError::TooSmall);
    }
    Ok(Data { seq_num: be32(p, 0), channel: be16(p, 4), data_type: p[8], data: &p[9..] })
}

/// A DATA_ACK: the cumulative sequence number and the peer's window; gap blocks are not used by the consoles.
pub fn parse_data_ack(message: &Message) -> Result<(u32, u32), TakionError> {
    let p = message.payload;
    if message.chunk_type != CHUNK_DATA_ACK {
        return Err(TakionError::InvalidData);
    }
    if p.len() != 0xc || be16(p, 8) != 0 {
        return Err(TakionError::SizeMismatch);
    }
    Ok((be32(p, 0), be32(p, 4)))
}

pub fn congestion_packet(word_0: u16, received: u16, lost: u16, key_pos: u64) -> [u8; CONGESTION_PACKET_SIZE] {
    let mut buf = [0u8; CONGESTION_PACKET_SIZE];
    buf[0] = PACKET_CONGESTION;
    buf[1..3].copy_from_slice(&word_0.to_be_bytes());
    buf[3..5].copy_from_slice(&received.to_be_bytes());
    buf[5..7].copy_from_slice(&lost.to_be_bytes());
    buf[0xb..0xf].copy_from_slice(&(key_pos as u32).to_be_bytes());
    buf
}

#[derive(Debug, Default, PartialEq, Eq, Clone)]
pub struct AvPacket {
    pub packet_index: u16,
    pub frame_index: u16,
    pub uses_nalu_info_structs: bool,
    pub is_video: bool,
    pub is_haptics: bool,
    pub unit_index: u16,
    pub units_in_frame_total: u16,       // source units + FEC units
    pub units_in_frame_fec: u16,
    pub codec: u8,
    pub word_at_0x18: u16,
    pub adaptive_stream_index: u8,
    pub byte_at_0x2c: u8,
    pub key_pos: u64,
    pub data_offset: usize,              // where the unit's data starts in the packet
}

pub const V7_AV_HEADER_SIZE: usize = 0x12;

/// A version 7 video or audio header: what the network test
/// sends as its pings. As there, the unit fields use the video layout for audio too, and the key position is
/// written in the machine's byte order (little-endian here) where every other field is big-endian.
pub fn v7_av_header(packet: &AvPacket) -> Vec<u8> {
    let mut buf = vec![0u8; V7_AV_HEADER_SIZE];
    buf[0] = if packet.is_video { PACKET_VIDEO } else { PACKET_AUDIO };
    if packet.uses_nalu_info_structs {
        buf[0] |= 0x10;
    }
    buf[1..3].copy_from_slice(&packet.packet_index.to_be_bytes());
    buf[3..5].copy_from_slice(&packet.frame_index.to_be_bytes());
    let dword_2 = (packet.units_in_frame_fec as u32 & 0x3ff)
        | ((packet.units_in_frame_total as u32).wrapping_sub(1) & 0x7ff) << 0xa
        | (packet.unit_index as u32) << 0x15;
    buf[5..9].copy_from_slice(&dword_2.to_be_bytes());
    buf[9] = packet.codec;
    buf[0xe..0x12].copy_from_slice(&(packet.key_pos as u32).to_le_bytes());
    if packet.is_video {
        buf.extend_from_slice(&packet.word_at_0x18.to_be_bytes());
        buf.push(packet.adaptive_stream_index << 5);
    }
    if packet.uses_nalu_info_structs {
        buf.extend_from_slice(&[0, 0, 0]);
    }
    buf
}

/// A video or audio packet's header, for Takion version 7, 9 or 12.
pub fn parse_av(version: u8, buf: &[u8], key_state: &mut KeyState) -> Result<AvPacket, TakionError> {
    match version {
        7 => parse_av_v7(buf),
        9 => parse_av_v9_v12(false, buf, key_state),
        12 => parse_av_v9_v12(true, buf, key_state),
        _ => Err(TakionError::InvalidData),
    }
}

fn av_base(buf: &[u8]) -> Result<AvPacket, TakionError> {
    let base_type = *buf.first().ok_or(TakionError::TooSmall)? & BASE_TYPE_MASK;
    if base_type != PACKET_VIDEO && base_type != PACKET_AUDIO {
        return Err(TakionError::InvalidData);
    }
    Ok(AvPacket { is_video: base_type == PACKET_VIDEO, uses_nalu_info_structs: (buf[0] >> 4) & 1 != 0, ..Default::default() })
}

fn parse_av_v9_v12(v12: bool, buf: &[u8], key_state: &mut KeyState) -> Result<AvPacket, TakionError> {
    let mut packet = av_base(buf)?;
    let header = match (v12, packet.is_video) {
        (_, true) => 0x17,
        (true, false) => 0x13,
        (false, false) => 0x12,
    };
    // The reference checks only this size; its audio path then reads past it when the nalu bit is set. Here the whole
    // header, nalu bytes and haptics marker included, must be inside the packet.
    let mut needed = 1 + 0x11 + if packet.is_video { 3 } else { 1 };
    needed += if packet.uses_nalu_info_structs { 3 } else { 0 };
    needed += if v12 && !packet.is_video { 1 } else { 0 };
    if buf.len() < 1 + header + 1 || buf.len() < needed {
        return Err(TakionError::TooSmall);
    }
    let av = &buf[1..];
    packet.packet_index = be16(av, 0);
    packet.frame_index = be16(av, 2);
    let dword_2 = be32(av, 4);
    if packet.is_video {
        packet.unit_index = ((dword_2 >> 0x15) & 0x7ff) as u16;
        packet.units_in_frame_total = (((dword_2 >> 0xa) & 0x7ff) + 1) as u16;
        packet.units_in_frame_fec = (dword_2 & 0x3ff) as u16;
    } else {
        packet.unit_index = ((dword_2 >> 0x18) & 0xff) as u16;
        packet.units_in_frame_total = (((dword_2 >> 0x10) & 0xff) + 1) as u16;
        packet.units_in_frame_fec = (dword_2 & 0xffff) as u16;
    }
    packet.codec = av[8];
    packet.key_pos = key_state.request_pos(be32(av, 0xd), true);
    let mut at = 1 + 0x11;
    if packet.is_video {
        packet.word_at_0x18 = be16(buf, at);
        packet.adaptive_stream_index = buf[at + 2] >> 5;
        at += 3;
        packet.byte_at_0x2c = buf[at];
    } else {
        at += 1;
    }
    if packet.uses_nalu_info_structs {
        at += 3;
    }
    if v12 && !packet.is_video {
        packet.is_haptics = buf[at] == 0x02;
        at += 1;
    }
    packet.data_offset = at;
    Ok(packet)
}

fn parse_av_v7(buf: &[u8]) -> Result<AvPacket, TakionError> {
    let mut packet = av_base(buf)?;
    let header = 0x12 + if packet.is_video { 3 } else { 0 } + if packet.uses_nalu_info_structs { 3 } else { 0 };
    if buf.len() < header {
        return Err(TakionError::TooSmall);
    }
    packet.packet_index = be16(buf, 1);
    packet.frame_index = be16(buf, 3);
    let dword_2 = be32(buf, 5);
    packet.unit_index = ((dword_2 >> 0x15) & 0x7ff) as u16;
    packet.units_in_frame_total = (((dword_2 >> 0xa) & 0x7ff) + 1) as u16;
    packet.units_in_frame_fec = (dword_2 & 0x3ff) as u16;
    packet.codec = buf[9];
    packet.key_pos = be32(buf, 0xe) as u64;            // version 7 has no key state
    if packet.is_video {
        packet.word_at_0x18 = be16(buf, 0x12);
        packet.adaptive_stream_index = buf[0x14] >> 5;
    }
    packet.data_offset = header;
    Ok(packet)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::vectors::{hex, load};

    #[test]
    fn v7_header_matches_reference() {
        for (name, v) in load()["v7_header"].as_object().unwrap() {
            let n = |key: &str| v[key].as_u64().unwrap();
            let packet = AvPacket {
                is_video: n("video") == 1,
                uses_nalu_info_structs: n("nalu") == 1,
                packet_index: n("packet_index") as u16,
                frame_index: n("frame_index") as u16,
                unit_index: n("unit_index") as u16,
                units_in_frame_total: n("units_total") as u16,
                units_in_frame_fec: n("units_fec") as u16,
                codec: n("codec") as u8,
                key_pos: n("key_pos"),
                word_at_0x18: n("word_at_0x18") as u16,
                adaptive_stream_index: n("adaptive_stream_index") as u8,
                ..Default::default()
            };
            assert_eq!(v7_av_header(&packet), hex(&v["header"]), "{name}");
        }
    }

    #[test]
    fn packet_mac_matches_reference() {
        let v = &load()["packet_mac"];
        let key: [u8; 16] = hex(&v["handshake_key"]).try_into().unwrap();
        let secret: [u8; 32] = hex(&v["secret"]).try_into().unwrap();
        let mut crypt = GkCrypt::new(v["index"].as_u64().unwrap() as u8, &key, &secret);
        for case in v["packets"].as_array().unwrap() {
            let mut packet = hex(&case["packet"]);
            let key_pos = case["key_pos"].as_u64().unwrap();
            let (mac, _old) = packet_mac(Some(&mut crypt), &mut packet, key_pos).unwrap();
            assert_eq!(packet, hex(&case["with_mac"]));
            assert_eq!(mac.to_vec(), hex(&case["mac"]));
            // The receiving side accepts it, and rejects it with one bit changed.
            let mut state = KeyState::new();
            assert_eq!(verify_packet(Some(&mut crypt), &mut state, &mut packet.clone()), Ok(key_pos));
            packet[1] ^= 1;                                      // signed in every packet type
            assert_eq!(verify_packet(Some(&mut crypt), &mut KeyState::new(), &mut packet), Err(TakionError::MacMismatch));
        }
    }

    #[test]
    fn av_parse_matches_reference() {
        for case in load()["av"].as_array().unwrap() {
            let packet = hex(&case["packet"]);
            let version = match case["parser"].as_str().unwrap() {
                "v7" => 7,
                "v9" => 9,
                _ => 12,
            };
            let parsed = parse_av(version, &packet, &mut KeyState::new()).unwrap();
            let n = |k: &str| case[k].as_u64().unwrap();
            let b = |k: &str| case[k].as_bool().unwrap();
            assert_eq!(parsed.packet_index as u64, n("packet_index"));
            assert_eq!(parsed.frame_index as u64, n("frame_index"));
            assert_eq!(parsed.uses_nalu_info_structs, b("nalu"));
            assert_eq!(parsed.is_video, b("video"));
            assert_eq!(parsed.is_haptics, b("haptics"));
            assert_eq!(parsed.unit_index as u64, n("unit_index"));
            assert_eq!(parsed.units_in_frame_total as u64, n("units_total"));
            assert_eq!(parsed.units_in_frame_fec as u64, n("units_fec"));
            assert_eq!(parsed.codec as u64, n("codec"));
            assert_eq!(parsed.word_at_0x18 as u64, n("word_at_0x18"));
            assert_eq!(parsed.adaptive_stream_index as u64, n("adaptive_stream_index"));
            assert_eq!(parsed.byte_at_0x2c as u64, n("byte_at_0x2c"));
            assert_eq!(parsed.key_pos, n("key_pos"));
            assert_eq!(parsed.data_offset as u64, n("data_offset"));
            assert_eq!((packet.len() - parsed.data_offset) as u64, n("data_size"));
        }
    }

    #[test]
    fn short_av_packets_are_refused() {
        let mut packet = vec![0x13u8; 0x14];                 // audio, nalu bit: the reference would read past the end
        assert_eq!(parse_av(12, &packet, &mut KeyState::new()), Err(TakionError::TooSmall));
        packet[0] = 0x02;
        assert_eq!(parse_av(9, &packet[..0x10], &mut KeyState::new()), Err(TakionError::TooSmall));
        assert_eq!(parse_av(7, &[0x02; 4], &mut KeyState::new()), Err(TakionError::TooSmall));
        assert_eq!(parse_av(12, &[0x00; 0x40], &mut KeyState::new()), Err(TakionError::InvalidData));
    }

    #[test]
    fn congestion_matches_reference() {
        let v = &load()["congestion"];
        let n = |k: &str| v[k].as_u64().unwrap();
        let packet = congestion_packet(n("word_0") as u16, n("received") as u16, n("lost") as u16, n("key_pos"));
        assert_eq!(packet.to_vec(), hex(&v["packet"]));
    }

    #[test]
    fn messages_round_trip() {
        let packet = data_packet(0xdeadbeef, 0x1234, 1, 7, 2, b"hello");
        let mut state = KeyState::new();
        let message = parse_message(&packet[1..], 0xdeadbeef, &mut state).unwrap();
        assert_eq!((message.key_pos, message.chunk_type, message.chunk_flags), (0x1234, CHUNK_DATA, 1));
        let data = parse_data(&message).unwrap();
        assert_eq!((data.seq_num, data.channel, data.data_type, data.data), (7, 2, DATA_TYPE_PROTOBUF, &b"hello"[..]));
        assert_eq!(parse_message(&packet[1..], 1, &mut state), Err(TakionError::TagMismatch));
        assert_eq!(parse_message(&packet[1..packet.len() - 1], 0xdeadbeef, &mut state), Err(TakionError::SizeMismatch));
        let ack = data_ack_packet(5, 0x40, 7, A_RWND);
        let message = parse_message(&ack[1..], 5, &mut KeyState::new()).unwrap();
        assert_eq!(parse_data_ack(&message), Ok((7, A_RWND)));
    }

    #[test]
    fn init_handshake_layout() {
        let init = init_packet(0x11223344, 0x11223344);
        assert_eq!(init.len(), 1 + 0x10 + 0x10);
        assert_eq!(&init[1..5], &[0, 0, 0, 0]);                           // to tag 0
        assert_eq!(init[0xd], CHUNK_INIT);
        // The console's INIT_ACK, as the reference expects it: its tag, window, stream counts, sequence number, cookie.
        let mut payload = Vec::new();
        payload.extend_from_slice(&0xcafe_u32.to_be_bytes());
        payload.extend_from_slice(&A_RWND.to_be_bytes());
        payload.extend_from_slice(&0x64_u16.to_be_bytes());
        payload.extend_from_slice(&0x64_u16.to_be_bytes());
        payload.extend_from_slice(&0x99_u32.to_be_bytes());
        payload.extend_from_slice(&[0xab; COOKIE_SIZE]);
        let ack = message_packet(0x11223344, 0, CHUNK_INIT_ACK, 0, &payload);
        let message = parse_message(&ack[1..], 0x11223344, &mut KeyState::new()).unwrap();
        let parsed = parse_init_ack(&message).unwrap();
        assert_eq!((parsed.tag, parsed.cookie.as_slice()), (0xcafe, &[0xab; COOKIE_SIZE][..]));
        let cookie = cookie_packet(parsed.tag, &parsed.cookie);
        assert_eq!((&cookie[1..5], cookie[0xd], cookie.len()), (&0xcafe_u32.to_be_bytes()[..], CHUNK_COOKIE, 1 + 0x10 + COOKIE_SIZE));
    }

    #[test]
    fn key_pos_advance_is_the_references() {
        assert_eq!(key_pos_advance(16), 16);
        assert_eq!(key_pos_advance(20), 24);                               // 20 + 20 % 16, not 32
        assert_eq!(key_pos_advance(0x1d), 0x1d + 0xd);
    }
}
