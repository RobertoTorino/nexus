// SPDX-License-Identifier: AGPL-3.0-only
//! The stream layer of Remote Play, ported from the reference (AGPL-3.0): Takion, the SCTP-like transport over UDP
//! 9296, its crypto, and the video frames with their FEC. Each module names the reference file it comes from; the
//! tests compare every function with vectors printed by the reference's own C code (tests/takion_vectors.json of the
//! app) and the FEC with frames recorded by the reference (tests/fec_vectors.json).

pub mod audio;
pub mod bitstream;
pub mod connection;
#[cfg(feature = "decoder")]
pub mod decoder;
pub mod ecdh;
pub mod fec;
pub mod feedback;
pub mod frame;
pub mod gkcrypt;
pub mod keystate;
pub mod orientation;
pub mod reorder;
pub mod sendbuffer;
pub mod seqnum;
pub mod takion;
pub mod video;

#[cfg(feature = "python")]
mod python;

#[cfg(test)]
pub(crate) mod vectors {
    //! The vectors from the reference's C code, shared with the Python tests.
    pub fn load() -> serde_json::Value {
        serde_json::from_str(include_str!("../../tests/takion_vectors.json")).expect("valid vectors")
    }

    pub fn hex(value: &serde_json::Value) -> Vec<u8> {
        let text = value.as_str().expect("a hex string");
        (0..text.len()).step_by(2).map(|i| u8::from_str_radix(&text[i..i + 2], 16).unwrap()).collect()
    }

    pub fn base64(text: &str) -> Vec<u8> {
        let value = |c: u8| match c {
            b'A'..=b'Z' => c - b'A',
            b'a'..=b'z' => c - b'a' + 26,
            b'0'..=b'9' => c - b'0' + 52,
            b'+' => 62,
            b'/' => 63,
            _ => panic!("not base64"),
        };
        let digits: Vec<u8> = text.bytes().filter(|&c| c != b'=').map(value).collect();
        let mut out = Vec::new();
        for chunk in digits.chunks(4) {
            let n = chunk.iter().enumerate().fold(0u32, |n, (i, &d)| n | (d as u32) << (18 - 6 * i));
            out.extend_from_slice(&n.to_be_bytes()[1..chunk.len()]);
        }
        out
    }
}
