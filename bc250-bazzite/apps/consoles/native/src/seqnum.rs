// SPDX-License-Identifier: AGPL-3.0-only
//! Serial number arithmetic (RFC 1982) for the 16- and 32-bit sequence numbers.

macro_rules! seqnum {
    ($lt:ident, $gt:ident, $t:ty, $wide:ty, $bits:expr) => {
        pub fn $lt(a: $t, b: $t) -> bool {
            if a == b {
                return false;
            }
            let d = b as $wide - a as $wide;
            let half = (1 as $wide) << ($bits - 1);
            (a < b && d < half) || (a > b && -d > half)
        }

        pub fn $gt(a: $t, b: $t) -> bool {
            if a == b {
                return false;
            }
            let d = b as $wide - a as $wide;
            let half = (1 as $wide) << ($bits - 1);
            (a < b && d > half) || (a > b && -d < half)
        }
    };
}

seqnum!(lt16, gt16, u16, i32, 16);
seqnum!(lt32, gt32, u32, i64, 32);

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn wraps_around() {
        assert!(lt16(0xfff0, 0x0010) && gt16(0x0010, 0xfff0));
        assert!(lt32(0xffff_fff0, 0x10) && gt32(0x10, 0xffff_fff0));
        assert!(!lt32(5, 5) && !gt32(5, 5));
        assert!(lt32(1, 2) && gt32(2, 1));
    }
}
