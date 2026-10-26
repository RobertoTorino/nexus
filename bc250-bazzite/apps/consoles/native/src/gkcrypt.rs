// SPDX-License-Identifier: AGPL-3.0-only
//! The stream crypto. Each direction has its own instance (index 2: client to console,
//! 3: console to client), keyed from the ECDH secret and the handshake key:
//!
//! * encryption is AES-128-CTR addressed by byte position: block n of the key stream is AES(key_base, iv + n), the
//!   counter added little-endian;
//! * every packet carries a 4-byte GMAC (AES-GCM tag with the packet as additional data and no plaintext) under a
//!   key that is renewed every 45000 bytes of key position.
//!
//! The reference fills a key-stream buffer in a thread ahead of time; with AES-NI the key stream is cheap to make on
//! the spot, so it is made per call here.

use aes::cipher::{BlockEncrypt, KeyInit};
use aes::Aes128;
use aes_gcm::aead::consts::U16;
use aes_gcm::aead::AeadInPlace;
use aes_gcm::AesGcm;
use hmac::{Hmac, Mac};
use sha2::{Digest, Sha256};

pub const BLOCK_SIZE: usize = 16;
pub const GMAC_SIZE: usize = 4;
pub const HANDSHAKE_KEY_SIZE: usize = 16;
pub const ECDH_SECRET_SIZE: usize = 32;
pub const GMAC_KEY_REFRESH_KEY_POS: u64 = 45000;
pub const GMAC_KEY_REFRESH_IV_OFFSET: u64 = 44910;

type Gcm16 = AesGcm<Aes128, U16>;

/// base + v, with base read as a 128-bit little-endian number.
pub fn counter_add(base: &[u8; 16], v: u64) -> [u8; 16] {
    u128::from_le_bytes(*base).wrapping_add(v as u128).to_le_bytes()
}

pub fn gen_gmac_key(index: u64, key_base: &[u8; 16], iv: &[u8; 16]) -> [u8; 16] {
    let mut hasher = Sha256::new();
    hasher.update(key_base);
    hasher.update(counter_add(iv, index.wrapping_mul(GMAC_KEY_REFRESH_IV_OFFSET)));
    let md = hasher.finalize();
    let mut key = [0u8; 16];
    for i in 0..16 {
        key[i] = md[i] ^ md[i + 16];
    }
    key
}

pub struct GkCrypt {
    pub index: u8,
    pub key_base: [u8; 16],
    pub iv: [u8; 16],
    pub key_gmac_base: [u8; 16],
    key_gmac_current: [u8; 16],
    key_gmac_index_current: u64,
    aes: Aes128,
}

impl GkCrypt {
    pub fn new(index: u8, handshake_key: &[u8; HANDSHAKE_KEY_SIZE], ecdh_secret: &[u8; ECDH_SECRET_SIZE]) -> Self {
        let mut data = Vec::with_capacity(3 + HANDSHAKE_KEY_SIZE + 2);
        data.extend_from_slice(&[1, index, 0]);
        data.extend_from_slice(handshake_key);
        data.extend_from_slice(&[1, 0]);
        let mut mac = <Hmac<Sha256> as Mac>::new_from_slice(ecdh_secret).expect("HMAC takes any key size");
        mac.update(&data);
        let digest = mac.finalize().into_bytes();
        let key_base: [u8; 16] = digest[..16].try_into().unwrap();
        let iv: [u8; 16] = digest[16..32].try_into().unwrap();
        let key_gmac_base = gen_gmac_key(0, &key_base, &iv);
        Self {
            index,
            key_base,
            iv,
            key_gmac_base,
            key_gmac_current: key_gmac_base,
            key_gmac_index_current: 0,
            aes: Aes128::new(&key_base.into()),
        }
    }

    /// The key stream for the bytes key_pos..key_pos + len (any alignment).
    pub fn key_stream(&self, key_pos: u64, len: usize) -> Vec<u8> {
        let pre = (key_pos % BLOCK_SIZE as u64) as usize;
        let blocks = (pre + len).div_ceil(BLOCK_SIZE);
        let first = key_pos / BLOCK_SIZE as u64;
        let mut stream = Vec::with_capacity(blocks * BLOCK_SIZE);
        for n in 0..blocks as u64 {
            let mut block = counter_add(&self.iv, first + n).into();
            self.aes.encrypt_block(&mut block);
            stream.extend_from_slice(&block);
        }
        stream.drain(..pre);
        stream.truncate(len);
        stream
    }

    /// Encrypts or decrypts (the same XOR) data that sits at key_pos in the stream.
    pub fn crypt(&self, key_pos: u64, data: &mut [u8]) {
        let stream = self.key_stream(key_pos, data.len());
        for (byte, key) in data.iter_mut().zip(stream) {
            *byte ^= key;
        }
    }

    fn gmac_key(&mut self, key_pos: u64) -> [u8; 16] {
        let index = key_pos.saturating_sub(1) / GMAC_KEY_REFRESH_KEY_POS;
        if index > self.key_gmac_index_current {
            self.key_gmac_current = gen_gmac_key(index, &self.key_gmac_base, &self.iv);
            self.key_gmac_index_current = index;
            self.key_gmac_current
        } else if index < self.key_gmac_index_current {
            // An older packet: a temporary key, the current one stays.
            if index == 0 {
                self.key_gmac_base
            } else {
                gen_gmac_key(index, &self.key_gmac_base, &self.iv)
            }
        } else {
            self.key_gmac_current
        }
    }

    pub fn gmac(&mut self, key_pos: u64, data: &[u8]) -> [u8; GMAC_SIZE] {
        let key = self.gmac_key(key_pos);
        let iv = counter_add(&self.iv, key_pos / BLOCK_SIZE as u64);
        let cipher = Gcm16::new(&key.into());
        let tag = cipher
            .encrypt_in_place_detached(&iv.into(), data, &mut [])
            .expect("GCM of an empty message does not fail");
        tag[..GMAC_SIZE].try_into().unwrap()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::vectors::{hex, load};

    fn arr<const N: usize>(value: &serde_json::Value) -> [u8; N] {
        hex(value).try_into().unwrap()
    }

    #[test]
    fn matches_reference() {
        for v in load()["gkcrypt"].as_array().unwrap() {
            let mut crypt = GkCrypt::new(v["index"].as_u64().unwrap() as u8, &arr(&v["handshake_key"]), &arr(&v["secret"]));
            assert_eq!(crypt.key_base.to_vec(), hex(&v["key_base"]));
            assert_eq!(crypt.iv.to_vec(), hex(&v["iv"]));
            assert_eq!(crypt.key_gmac_base.to_vec(), hex(&v["key_gmac_base"]));
            assert_eq!(crypt.key_stream(0, 64), hex(&v["stream_0"]));
            assert_eq!(crypt.key_stream(0xfff0, 48), hex(&v["stream_fff0"]));
            let mut data = hex(&v["plain"]);
            crypt.crypt(0x105, &mut data);
            assert_eq!(data, hex(&v["crypt_105"]));
            crypt.crypt(0x105, &mut data);
            assert_eq!(data, hex(&v["plain"]));
            let message = hex(&v["gmac_msg"]);
            for pair in v["gmacs"].as_array().unwrap() {
                let pos = pair[0].as_u64().unwrap();
                assert_eq!(crypt.gmac(pos, &message).to_vec(), hex(&pair[1]), "gmac at {pos}");
            }
        }
    }

    #[test]
    fn counter_add_carries_little_endian() {
        let mut base = [0u8; 16];
        base[0] = 0xff;
        let sum = counter_add(&base, 1);
        assert_eq!(&sum[..2], &[0, 1]);
        assert_eq!(counter_add(&[0xff; 16], 1), [0; 16]);
    }
}
