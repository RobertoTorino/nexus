// SPDX-License-Identifier: AGPL-3.0-only
//! The key exchange of the stream: ECDH on secp256k1. Each side sends its public key
//! (uncompressed, 65 bytes) with HMAC-SHA256(handshake key, public key) as signature; the shared secret is the x
//! coordinate of the shared point.
//!
//! The reference does not check the console's signature. verify() is here so the session can; whether a console's
//! signature is computed the same way is to be seen on a real console.

use hmac::{Hmac, Mac};
use k256::ecdh::diffie_hellman;
use k256::elliptic_curve::sec1::ToEncodedPoint;
use k256::{PublicKey, SecretKey};
use rand_core::OsRng;
use sha2::Sha256;

use crate::gkcrypt::{ECDH_SECRET_SIZE, HANDSHAKE_KEY_SIZE};

#[derive(Debug, PartialEq, Eq)]
pub enum EcdhError {
    InvalidPrivateKey,
    InvalidPublicKey,
}

pub struct Ecdh {
    secret: SecretKey,
}

pub fn sign(handshake_key: &[u8; HANDSHAKE_KEY_SIZE], public_key: &[u8]) -> [u8; 32] {
    let mut mac = <Hmac<Sha256> as Mac>::new_from_slice(handshake_key).expect("HMAC takes any key size");
    mac.update(public_key);
    mac.finalize().into_bytes().into()
}

pub fn verify(handshake_key: &[u8; HANDSHAKE_KEY_SIZE], public_key: &[u8], signature: &[u8]) -> bool {
    let mut mac = <Hmac<Sha256> as Mac>::new_from_slice(handshake_key).expect("HMAC takes any key size");
    mac.update(public_key);
    mac.verify_slice(signature).is_ok()
}

impl Ecdh {
    pub fn generate() -> Self {
        Self { secret: SecretKey::random(&mut OsRng) }
    }

    pub fn from_private(private_key: &[u8]) -> Result<Self, EcdhError> {
        SecretKey::from_slice(private_key).map(|secret| Self { secret }).map_err(|_| EcdhError::InvalidPrivateKey)
    }

    pub fn public_key(&self) -> Vec<u8> {
        self.secret.public_key().to_encoded_point(false).as_bytes().to_vec()
    }

    /// The public key and its signature, as the client sends them.
    pub fn signed_public_key(&self, handshake_key: &[u8; HANDSHAKE_KEY_SIZE]) -> (Vec<u8>, [u8; 32]) {
        let public = self.public_key();
        let signature = sign(handshake_key, &public);
        (public, signature)
    }

    pub fn derive_secret(&self, remote_public: &[u8]) -> Result<[u8; ECDH_SECRET_SIZE], EcdhError> {
        let remote = PublicKey::from_sec1_bytes(remote_public).map_err(|_| EcdhError::InvalidPublicKey)?;
        let shared = diffie_hellman(self.secret.to_nonzero_scalar(), remote.as_affine());
        Ok((*shared.raw_secret_bytes()).into())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::vectors::{hex, load};

    #[test]
    fn matches_reference() {
        for v in load()["ecdh"].as_array().unwrap() {
            let ecdh = Ecdh::from_private(&hex(&v["private"])).unwrap();
            let handshake_key: [u8; 16] = hex(&v["handshake_key"]).try_into().unwrap();
            let (public, signature) = ecdh.signed_public_key(&handshake_key);
            assert_eq!(public, hex(&v["public"]));
            assert_eq!(signature.to_vec(), hex(&v["signature"]));
            assert!(verify(&handshake_key, &public, &signature));
            assert_eq!(ecdh.derive_secret(&hex(&v["remote_public"])).unwrap().to_vec(), hex(&v["secret"]));
        }
    }

    #[test]
    fn both_sides_agree() {
        let (a, b) = (Ecdh::generate(), Ecdh::generate());
        assert_eq!(a.derive_secret(&b.public_key()).unwrap(), b.derive_secret(&a.public_key()).unwrap());
        assert_eq!(a.derive_secret(&[4; 65]), Err(EcdhError::InvalidPublicKey));
    }
}
