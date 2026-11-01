// SPDX-License-Identifier: AGPL-3.0-only
//! A reorder queue for 16- or 32-bit sequence numbers: items go in by sequence
//! number, in any order, and come out in order once there is no gap before them. The queue holds 2^size_exp
//! numbers from `begin`; what does not fit is dropped from the end (the newest, for the data messages) or from the
//! begin (the oldest, for video, which moves on rather than wait).

use crate::seqnum::{gt16, gt32, lt16, lt32};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DropStrategy {
    Begin,
    End,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Bits {
    B16,
    B32,
}

impl Bits {
    pub fn lt(self, a: u64, b: u64) -> bool {
        match self {
            Bits::B16 => lt16(a as u16, b as u16),
            Bits::B32 => lt32(a as u32, b as u32),
        }
    }

    pub fn gt(self, a: u64, b: u64) -> bool {
        match self {
            Bits::B16 => gt16(a as u16, b as u16),
            Bits::B32 => gt32(a as u32, b as u32),
        }
    }

    pub fn add(self, a: u64, b: u64) -> u64 {
        match self {
            Bits::B16 => (a as u16).wrapping_add(b as u16) as u64,
            Bits::B32 => (a as u32).wrapping_add(b as u32) as u64,
        }
    }

    fn ge(self, a: u64, b: u64) -> bool {
        a == b || self.gt(a, b)
    }
}

pub struct ReorderQueue<T> {
    bits: Bits,
    begin: u64,
    count: u64,
    slots: Vec<Option<T>>,
    drop_strategy: DropStrategy,
    dropped: u64,
}

impl<T> ReorderQueue<T> {
    pub fn new(size_exp: u32, bits: Bits, begin: u64, drop_strategy: DropStrategy) -> Self {
        Self { bits, begin, count: 0, slots: (0..1usize << size_exp).map(|_| None).collect(), drop_strategy, dropped: 0 }
    }

    fn size(&self) -> u64 {
        self.slots.len() as u64
    }

    fn idx(&self, seq_num: u64) -> usize {
        (seq_num % self.size()) as usize
    }

    pub fn begin(&self) -> u64 {
        self.begin
    }

    /// The span from begin to the newest number, gaps included.
    pub fn count(&self) -> u64 {
        self.count
    }

    /// Items dropped so far: duplicates, numbers already passed, and what did not fit.
    pub fn dropped(&self) -> u64 {
        self.dropped
    }

    pub fn push(&mut self, seq_num: u64, item: T) {
        let b = self.bits;
        let mut end = b.add(self.begin, self.count);
        if b.ge(seq_num, self.begin) && b.lt(seq_num, end) {
            let i = self.idx(seq_num);
            if self.slots[i].is_some() {
                self.dropped += 1;                       // received twice
            } else {
                self.slots[i] = Some(item);
            }
            return;
        }
        if b.lt(seq_num, self.begin) {
            self.dropped += 1;
            return;
        }
        if !b.ge(seq_num, end) {
            // Half the number space away: neither before nor after. An empty video queue starts over there.
            if self.count == 0 && self.drop_strategy == DropStrategy::Begin {
                self.begin = seq_num;
                end = seq_num;
            } else {
                self.dropped += 1;
                return;
            }
        }
        let new_end = b.add(seq_num, 1);
        let mut total_end = b.add(end, self.size() - self.count);
        if b.lt(total_end, new_end) {
            if self.drop_strategy == DropStrategy::End {
                self.dropped += 1;
                return;
            }
            while self.count > 0 && b.lt(total_end, new_end) {
                let i = self.idx(self.begin);
                if self.slots[i].take().is_some() {
                    self.dropped += 1;
                }
                self.begin = b.add(self.begin, 1);
                self.count -= 1;
                total_end = b.add(end, self.size() - self.count);
            }
            if self.count == 0 {
                self.begin = seq_num;
            }
        }
        end = b.add(self.begin, self.count);
        while b.lt(end, new_end) {
            let i = self.idx(end);
            self.slots[i] = None;
            self.count += 1;
            end = b.add(self.begin, self.count);
        }
        let i = self.idx(seq_num);
        self.slots[i] = Some(item);
    }

    /// The item at begin, when it is there.
    pub fn pull(&mut self) -> Option<(u64, T)> {
        if self.count == 0 {
            return None;
        }
        let i = self.idx(self.begin);
        let item = self.slots[i].take()?;
        let seq_num = self.begin;
        self.begin = self.bits.add(self.begin, 1);
        self.count -= 1;
        Some((seq_num, item))
    }

    pub fn peek(&self, index: u64) -> Option<&T> {
        if index >= self.count {
            return None;
        }
        self.slots[self.idx(self.bits.add(self.begin, index))].as_ref()
    }

    /// Removes the item at begin + index. The reference's version calls the drop callback but leaves the slot set,
    /// so the freed item could still be pulled; here the slot is emptied.
    pub fn drop_at(&mut self, index: u64) {
        if index >= self.count {
            return;
        }
        let i = self.idx(self.bits.add(self.begin, index));
        if self.slots[i].take().is_none() {
            return;
        }
        self.dropped += 1;
        while self.count > 0 && self.slots[self.idx(self.bits.add(self.begin, self.count - 1))].is_none() {
            self.count -= 1;
        }
    }

    /// Skips the missing numbers before the first item that is there (the video queue's timeout). Returns how
    /// many were skipped.
    pub fn skip_to_first(&mut self) -> u64 {
        let mut skipped = 0;
        while skipped < self.count && self.peek(skipped).is_none() {
            skipped += 1;
        }
        if skipped >= self.count {
            return 0;
        }
        self.begin = self.bits.add(self.begin, skipped);
        self.count -= skipped;
        skipped
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn in_order_after_gaps_and_duplicates() {
        let mut q = ReorderQueue::new(4, Bits::B32, 10, DropStrategy::End);
        q.push(12, "c");
        q.push(11, "b");
        assert_eq!(q.pull(), None);                       // 10 missing
        q.push(10, "a");
        q.push(10, "a again");
        q.push(9, "old");
        assert_eq!([q.pull(), q.pull(), q.pull(), q.pull()], [Some((10, "a")), Some((11, "b")), Some((12, "c")), None]);
        assert_eq!(q.dropped(), 2);
    }

    #[test]
    fn full_queue_drops_new_or_old() {
        let mut end = ReorderQueue::new(2, Bits::B32, 0, DropStrategy::End);   // 4 slots
        for n in 1..4 {
            end.push(n, n);
        }
        end.push(4, 4);                                   // 0..3 spans the queue: 4 does not fit
        assert_eq!((end.count(), end.dropped()), (4, 1));

        let mut begin = ReorderQueue::new(2, Bits::B16, 0, DropStrategy::Begin);
        for n in 1..4 {
            begin.push(n, n);
        }
        begin.push(5, 5);                                 // 0 and 1 make room
        assert_eq!(begin.begin(), 2);
        assert_eq!([begin.pull(), begin.pull()], [Some((2, 2)), Some((3, 3))]);
        assert_eq!(begin.pull(), None);
        assert_eq!(begin.skip_to_first(), 1);
        assert_eq!(begin.pull(), Some((5, 5)));
    }

    #[test]
    fn wraps_around_and_drops_items() {
        let mut q = ReorderQueue::new(4, Bits::B16, 0xfffe, DropStrategy::Begin);
        q.push(0x0001, 'c');
        q.push(0xfffe, 'a');
        q.push(0xffff, 'b');
        q.drop_at(2);                                     // 0x0000: not there
        q.drop_at(3);                                     // 0x0001
        assert_eq!(q.count(), 2);
        assert_eq!([q.pull(), q.pull(), q.pull()], [Some((0xfffe, 'a')), Some((0xffff, 'b')), None]);
        // Empty, half the number space away: a video queue starts over there.
        q.push(0x8000, 'x');
        assert_eq!(q.pull(), Some((0x8000, 'x')));
    }
}
