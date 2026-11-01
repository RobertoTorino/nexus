// SPDX-License-Identifier: AGPL-3.0-only
//! The 64-bit key position from the 32 bits a packet carries: the high
//! half follows the low half across wrap-arounds, forwards and back.

use crate::seqnum::{gt32, lt32};

#[derive(Debug, Default, Clone, Copy)]
pub struct KeyState {
    prev: u64,
}

impl KeyState {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn request_pos(&mut self, low: u32, commit: bool) -> u64 {
        let prev_low = self.prev as u32;
        let mut high = (self.prev >> 32) as u32;
        if gt32(low, prev_low) && low < prev_low {
            high = high.wrapping_add(1);
        } else if lt32(low, prev_low) && low > prev_low && high != 0 {
            high -= 1;
        }
        let pos = ((high as u64) << 32) | low as u64;
        if commit {
            self.prev = pos;
        }
        pos
    }

    pub fn commit(&mut self, pos: u64) {
        self.prev = pos;
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::vectors;

    #[test]
    fn matches_reference() {
        let mut state = KeyState::new();
        for pair in vectors::load()["key_state"].as_array().unwrap() {
            let low = pair[0].as_u64().unwrap() as u32;
            assert_eq!(state.request_pos(low, true), pair[1].as_u64().unwrap(), "low {low:#x}");
        }
    }
}
