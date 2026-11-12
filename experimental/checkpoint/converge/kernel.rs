// Convergence check: are two images of the engine's memory the same state up
// to where its nodes happen to lie?
// The host is src/checkpoint/converge.mjs in the engine.
// Private memory only: the host copies both images and the tables in.
//
// Every failure means "not converged"; nothing is guessed.
#![no_std]
extern crate alloc;
use alloc::vec::Vec;
use core::alloc::{GlobalAlloc, Layout};
use core::arch::wasm32::{memory_grow, memory_size, unreachable};

#[panic_handler]
fn panic(_: &core::panic::PanicInfo<'_>) -> ! { unreachable() }

extern "C" { static __heap_base: u8; }
static mut NEXT: usize = 0;
struct Bump;
unsafe fn ensure(end: usize) -> bool {
    let have = memory_size(0) * 65536;
    end <= have || memory_grow(0, (end - have + 65535) / 65536) != usize::MAX
}
unsafe impl GlobalAlloc for Bump {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        if NEXT == 0 { NEXT = (&raw const __heap_base) as usize; }
        let start = (NEXT + layout.align() - 1) & !(layout.align() - 1);
        let end = match start.checked_add(layout.size()) { Some(end) => end, None => return core::ptr::null_mut() };
        if !ensure(end) { return core::ptr::null_mut(); }
        NEXT = end;
        start as *mut u8
    }
    unsafe fn dealloc(&self, _: *mut u8, _: Layout) {}
}
#[global_allocator]
static ALLOCATOR: Bump = Bump;

/// Host buffers: reserve(bytes) returns an address in this module's memory;
/// reset() gives everything back.
#[no_mangle]
pub unsafe extern "C" fn reserve(bytes: usize) -> usize {
    ALLOCATOR.alloc(Layout::from_size_align_unchecked(bytes.max(1), 8)) as usize
}
#[no_mangle]
pub unsafe extern "C" fn reset() { NEXT = (&raw const __heap_base) as usize; }

// ---- Parameter block (u32 words), filled by the host.
const P_LENGTH: usize = 0;      // bytes in each image
const P_IMAGE_A: usize = 1;
const P_IMAGE_B: usize = 2;
const P_MEM0: usize = 3;        // address of mem[memmin] in the images
const P_MEM_END: usize = 4;     // address after the last memory word
const P_MEMMIN: usize = 5;
const P_LOMEMMAX_A: usize = 6;
const P_HIMEMMIN_A: usize = 7;
const P_MEMEND_A: usize = 8;
const P_LOMEMMAX_B: usize = 9;
const P_HIMEMMIN_B: usize = 10;
const P_MEMEND_B: usize = 11;
const P_FREE_A: usize = 12;     // one byte per memory word: 0 live, 1 free single, 2 free variable
const P_FREE_B: usize = 13;
const P_BOUNDS_A: usize = 14;   // one bit per memory word: a node begins here
const P_BOUNDS_B: usize = 15;
const P_EXCLUDED: usize = 16;   // sorted, merged [from, to) byte ranges
const P_EXCLUDED_COUNT: usize = 17;
const P_NO_POINTERS: usize = 18;
const P_NO_POINTERS_COUNT: usize = 19;
const P_OBJTAB: usize = 20;
const P_OBJTAB_LENGTH: usize = 21;
const P_OBJENTRY: usize = 22;
const P_RESULT: usize = 23;     // 8 words written by check()
const P_WORDS: usize = 24;

// Result codes.
const CONVERGED: u32 = 1;
const F_KIND: u32 = 2;          // a word lies in different kinds of memory
const F_STATIC: u32 = 3;        // unexplained difference outside memory
const F_NODE: u32 = 4;          // paired nodes differ
const F_REUSED: u32 = 5;        // same address, different nodes, not accounted for
const F_DISPLACED: u32 = 6;
const F_LOST: u32 = 7;          // a live node exists in one image only
const F_HIDDEN: u32 = 8;        // an unchanged value may point into moved memory
const F_INPUT: u32 = 9;

/// Open-addressing map from node address to node address.
struct Map { keys: Vec<i32>, values: Vec<i32>, used: usize }
const EMPTY: i32 = i32::MIN;
impl Map {
    fn new() -> Map { Map { keys: alloc::vec![EMPTY; 1 << 12], values: alloc::vec![0; 1 << 12], used: 0 } }
    fn slot(&self, key: i32) -> usize {
        let mask = self.keys.len() - 1;
        let mut at = (key as u32).wrapping_mul(0x9E37_79B1) as usize >> 7 & mask;
        while self.keys[at] != EMPTY && self.keys[at] != key { at = (at + 1) & mask; }
        at
    }
    fn get(&self, key: i32) -> Option<i32> { let at = self.slot(key); if self.keys[at] == key { Some(self.values[at]) } else { None } }
    fn has(&self, key: i32) -> bool { self.keys[self.slot(key)] == key }
    fn set(&mut self, key: i32, value: i32) {
        if (self.used + 1) * 2 > self.keys.len() { self.grow(); }
        let at = self.slot(key);
        if self.keys[at] != key { self.keys[at] = key; self.used += 1; }
        self.values[at] = value;
    }
    fn grow(&mut self) {
        let (keys, values) = (core::mem::take(&mut self.keys), core::mem::take(&mut self.values));
        self.keys = alloc::vec![EMPTY; keys.len() * 2]; self.values = alloc::vec![0; keys.len() * 2]; self.used = 0;
        for (index, key) in keys.iter().enumerate() { if *key != EMPTY { self.set(*key, values[index]); } }
    }
    /// Deleting leaves a tombstone-free table by rebuilding; removals are rare (withdrawn assumptions).
    fn remove_all(&mut self, gone: &[i32]) {
        if gone.is_empty() { return; }
        let (keys, values) = (core::mem::take(&mut self.keys), core::mem::take(&mut self.values));
        self.keys = alloc::vec![EMPTY; keys.len()]; self.values = alloc::vec![0; keys.len()]; self.used = 0;
        for (index, key) in keys.iter().enumerate() { if *key != EMPTY && !gone.contains(key) { self.set(*key, values[index]); } }
    }
}

struct Image { words: *const u32, free: *const u8, bounds: *const u8, lomemmax: i32, himemmin: i32, memend: i32 }
struct State<'a> {
    p: &'a [u32], a: Image, b: Image, memmin: i32, mem0: usize,
    phi: Map, inverse: Map, sizes: Map, queue: Vec<i32>, added: Vec<i32>,
    fail: [u32; 4],
}
impl Image {
    #[inline] unsafe fn free_of(&self, p: i32, memmin: i32) -> u8 { *self.free.add((p - memmin) as usize) }
    #[inline] fn is_single(&self, p: i32) -> bool { p >= self.himemmin && p <= self.memend }
    #[inline] fn is_variable(&self, p: i32, memmin: i32) -> bool { p >= memmin && p <= self.lomemmax }
    #[inline] unsafe fn marked(&self, p: i32, memmin: i32) -> bool { let at = (p - memmin) as usize; (*self.bounds.add(at >> 3) >> (at & 7)) & 1 == 1 }
    #[inline] unsafe fn boundary(&self, p: i32, memmin: i32) -> bool {
        p <= memmin || p > self.lomemmax || self.marked(p, memmin) || self.free_of(p, memmin) != self.free_of(p - 1, memmin)
    }
    unsafe fn segment_start(&self, p: i32, memmin: i32) -> i32 { let mut s = p; while !self.boundary(s, memmin) { s -= 1; } s }
    unsafe fn segment_size(&self, s: i32, memmin: i32) -> i32 { let mut e = s + 1; while e <= self.lomemmax && !self.boundary(e, memmin) { e += 1; } e - s }
    /// Size of the live node that starts at p, or 0.
    unsafe fn node_at(&self, p: i32, memmin: i32) -> i32 {
        if self.is_single(p) { return if self.free_of(p, memmin) != 0 { 0 } else { 1 }; }
        if self.is_variable(p, memmin) && self.free_of(p, memmin) == 0 && self.boundary(p, memmin) { self.segment_size(p, memmin) } else { 0 }
    }
    #[inline] unsafe fn half(&self, mem0: usize, memmin: i32, p: i32, half: usize) -> i32 { *self.words.add(((mem0 + (p - memmin) as usize * 8) >> 2) + half) as i32 }
}
impl<'a> State<'a> {
    unsafe fn pair(&mut self, p: i32, q: i32) -> bool {
        if let Some(have) = self.phi.get(p) { return have == q; }
        if self.inverse.has(q) { return false; }
        let n = self.a.node_at(p, self.memmin);
        if n == 0 || n != self.b.node_at(q, self.memmin) || self.a.is_single(p) != self.b.is_single(q) { return false; }
        self.phi.set(p, q); self.inverse.set(q, p); self.sizes.set(p, n); self.queue.push(p); self.added.push(p);
        true
    }
    /// Related nodes are equal up to phi. False on the first contradiction.
    unsafe fn close(&mut self) -> bool {
        while let Some(p) = self.queue.pop() {
            let (q, n) = (self.phi.get(p).unwrap(), self.sizes.get(p).unwrap());
            for w in 0..n { for half in 0..2 {
                let (x, y) = (self.a.half(self.mem0, self.memmin, p + w, half), self.b.half(self.mem0, self.memmin, q + w, half));
                if x != y && !self.pair(x, y) { self.fail = [F_NODE, p as u32, x as u32, y as u32]; return false; }
            } }
        }
        true
    }
    unsafe fn dangling(&self, p: i32, q: i32) -> bool {
        let last = self.memmin + ((self.p[P_MEM_END] as usize - self.mem0) / 8) as i32 - 1;
        p >= self.memmin && p <= last && q >= self.memmin && q <= last && self.a.free_of(p, self.memmin) > 0 && self.b.free_of(q, self.memmin) > 0
    }
}
fn in_ranges(ranges: &[u32], at: u32) -> bool {
    // Sorted [from, to) pairs: binary search on the starts.
    let (mut low, mut high) = (0usize, ranges.len() / 2);
    while low < high { let middle = (low + high) / 2; if ranges[middle * 2] <= at { low = middle + 1 } else { high = middle } }
    low > 0 && at < ranges[(low - 1) * 2 + 1]
}

/// Returns 1 when the images are the same state, else 0; details in the result words:
/// [code, where, old value, new value, moved nodes, moved variable-size nodes, nodes checked, withdrawn].
#[no_mangle]
pub unsafe extern "C" fn check(parameters: *const u32) -> u32 {
    let p = core::slice::from_raw_parts(parameters, P_WORDS);
    let result = core::slice::from_raw_parts_mut(p[P_RESULT] as usize as *mut u32, 8);
    result.fill(0);
    let length = p[P_LENGTH] as usize / 4;
    let (words_a, words_b) = (p[P_IMAGE_A] as usize as *const u32, p[P_IMAGE_B] as usize as *const u32);
    let (mem0, mem_end, memmin) = (p[P_MEM0] as usize, p[P_MEM_END] as usize, p[P_MEMMIN] as i32);
    if mem0 & 7 != 0 || mem_end <= mem0 || mem_end > length * 4 { result[0] = F_INPUT; return 0; }
    let excluded = core::slice::from_raw_parts(p[P_EXCLUDED] as usize as *const u32, p[P_EXCLUDED_COUNT] as usize * 2);
    let no_pointers = core::slice::from_raw_parts(p[P_NO_POINTERS] as usize as *const u32, p[P_NO_POINTERS_COUNT] as usize * 2);
    let (objtab, objtab_end, objentry) = (p[P_OBJTAB], p[P_OBJTAB] + p[P_OBJTAB_LENGTH], p[P_OBJENTRY].max(1));
    let is_excluded = |at: u32| in_ranges(excluded, at) || (at >= objtab && at < objtab_end && { let within = (at - objtab) % objentry; within >= 8 && within < 16 });
    let mut s = State {
        p, memmin, mem0,
        a: Image { words: words_a, free: p[P_FREE_A] as usize as *const u8, bounds: p[P_BOUNDS_A] as usize as *const u8, lomemmax: p[P_LOMEMMAX_A] as i32, himemmin: p[P_HIMEMMIN_A] as i32, memend: p[P_MEMEND_A] as i32 },
        b: Image { words: words_b, free: p[P_FREE_B] as usize as *const u8, bounds: p[P_BOUNDS_B] as usize as *const u8, lomemmax: p[P_LOMEMMAX_B] as i32, himemmin: p[P_HIMEMMIN_B] as i32, memend: p[P_MEMEND_B] as i32 },
        phi: Map::new(), inverse: Map::new(), sizes: Map::new(), queue: Vec::new(), added: Vec::new(), fail: [0; 4],
    };
    let word_of = |at: usize| ((at - mem0) >> 3) as i32 + memmin;
    macro_rules! fail { ($code:expr, $at:expr, $x:expr, $y:expr) => {{ result[0] = $code; result[1] = $at as u32; result[2] = $x as u32; result[3] = $y as u32; return 0; }} }

    // 1: every differing half. Inside memory: by the node it lies in. Outside: a root of phi or a stale temporary.
    let mut in_place: Vec<(i32, i32)> = Vec::new();
    let mut displaced: Vec<(i32, bool)> = Vec::new();
    let mut statics: Vec<u32> = Vec::new();
    let (mut i, mut last_in_place, mut range) = (0usize, i32::MIN, 0usize);
    while i < length {
        // Excluded ranges are skipped whole: the unused middle of memory alone is tens of megabytes.
        while range * 2 < excluded.len() && (excluded[range * 2 + 1] as usize) <= i * 4 { range += 1; }
        if range * 2 < excluded.len() && (excluded[range * 2] as usize) <= i * 4 { i = (excluded[range * 2 + 1] as usize + 3) / 4; continue; }
        if *words_a.add(i) == *words_b.add(i) { i += 1; continue; }
        let at = i * 4;
        if is_excluded(at as u32) { i += 1; continue; }
        if at < mem0 || at >= mem_end { statics.push(i as u32); i += 1; continue; }
        let w = word_of(at);
        let (fa, fb) = (s.a.free_of(w, memmin), s.b.free_of(w, memmin));
        if fa != 0 || fb != 0 { i += 1; continue; }             // dead in both, or live in one only (step 5)
        if s.a.is_single(w) && s.b.is_single(w) {
            if last_in_place != w { in_place.push((w, 1)); last_in_place = w; }
        } else if s.a.is_variable(w, memmin) && s.b.is_variable(w, memmin) {
            let (sa, sb) = (s.a.segment_start(w, memmin), s.b.segment_start(w, memmin));
            let na = s.a.segment_size(sa, memmin);
            if sa == sb && na == s.b.segment_size(sb, memmin) { if last_in_place != sa { in_place.push((sa, na)); last_in_place = sa; } }
            else { displaced.push((sa, true)); displaced.push((sb, false)); }
        } else { fail!(F_KIND, at, w, 0) }
        i += 1;
    }
    let mut stale = 0u32;
    for index in statics.iter() {
        let (x, y) = (*words_a.add(*index as usize) as i32, *words_b.add(*index as usize) as i32);
        if s.pair(x, y) { continue; }
        if s.dangling(x, y) { stale += 1; continue; }
        fail!(F_STATIC, *index * 4, x, y)
    }
    if !s.close() { let f = s.fail; fail!(f[0], f[1], f[2], f[3]) }
    // TeX's fixed list heads at the top of memory are set before each use; one is scratch.
    let memtop = s.a.memend;
    if s.a.memend == s.b.memend {
        let mut kept: Vec<(i32, i32)> = Vec::with_capacity(in_place.len());
        for (p0, n) in in_place.iter().copied() {
            if p0 < memtop - 14 || p0 > memtop { kept.push((p0, n)); continue; }
            let mut explained = true;
            for half in 0..2 {
                let (x, y) = (s.a.half(mem0, memmin, p0, half), s.b.half(mem0, memmin, p0, half));
                if x == y || p0 == memtop - 12 { continue; }
                if s.pair(x, y) { continue; }
                if s.dangling(x, y) { stale += 1; continue; }
                explained = false; break;
            }
            if !explained { kept.push((p0, n)); }
        }
        in_place = kept;
    }
    if !s.close() { let f = s.fail; fail!(f[0], f[1], f[2], f[3]) }
    // 4: a node at the same address in both images that differs: first assumed the same node.
    let mut reused: Vec<i32> = Vec::new();
    let mut withdrawn = 0u32;
    for (p0, _) in in_place.iter().copied() {
        if s.phi.has(p0) || s.inverse.has(p0) { if s.phi.get(p0) != Some(p0) { reused.push(p0); } continue; }
        s.added.clear();
        let ok = s.pair(p0, p0) && s.close();
        if !ok {
            let added = core::mem::take(&mut s.added);
            let images: Vec<i32> = added.iter().map(|k| s.phi.get(*k).unwrap()).collect();
            s.phi.remove_all(&added); s.sizes.remove_all(&added); s.inverse.remove_all(&images);
            s.queue.clear(); withdrawn += 1; reused.push(p0);
        }
    }
    for p0 in reused.iter().copied() { if !(s.phi.has(p0) && s.inverse.has(p0)) { fail!(F_REUSED, p0, 0, 0) } }
    for (start, old) in displaced.iter().copied() { if if old { !s.phi.has(start) } else { !s.inverse.has(start) } { fail!(F_DISPLACED, start, old as u32, 0) } }
    // 5: every live node without an identical counterpart at the same address was reached.
    for side in 0..2 {
        let (image, other, known) = if side == 0 { (&s.a, &s.b, &s.phi) } else { (&s.b, &s.a, &s.inverse) };
        let (from, to) = (image.himemmin.min(other.himemmin), image.memend.max(other.memend));
        let mut q = from;
        while q <= to {
            if image.is_single(q) && image.free_of(q, memmin) == 0 && !(other.is_single(q) && other.free_of(q, memmin) == 0) && !known.has(q) { fail!(F_LOST, q, side, 1) }
            q += 1;
        }
        let mut start = memmin;
        while start <= image.lomemmax {
            let n = image.segment_size(start, memmin);
            if image.free_of(start, memmin) == 0 {
                let mirrored = other.is_variable(start, memmin) && other.free_of(start, memmin) == 0 && other.boundary(start, memmin) && other.segment_size(start, memmin) == n;
                if !mirrored && !known.has(start) { fail!(F_LOST, start, side, n) }
            }
            start += n;
        }
    }
    // 6: no unchanged value may be a pointer into moved memory.
    let mut moved_variable = 0u32;
    if s.phi.used > 0 {
        // Candidate values are node addresses: a cheap range test rejects almost every word.
        let (low_from, low_to) = (memmin, s.a.lomemmax.max(s.b.lomemmax));
        let (high_from, high_to) = (s.a.himemmin.min(s.b.himemmin), s.a.memend.max(s.b.memend));
        // One bit per address in the two ranges: set where a node moved away or moved in.
        // Small integers are everywhere, so this test must cost a few instructions.
        let (low_bits, high_bits) = ((low_to - low_from + 1).max(0) as usize, (high_to - high_from + 1).max(0) as usize);
        let mut moved: Vec<u64> = alloc::vec![0u64; (low_bits + high_bits + 63) / 64 + 1];
        let bit_of = |v: i32| -> usize { if v <= low_to { (v - low_from) as usize } else { low_bits + (v - high_from) as usize } };
        for index in 0..s.phi.keys.len() {
            let key = s.phi.keys[index];
            if key == EMPTY || s.phi.values[index] == key { continue; }
            for v in [key, s.phi.values[index]] {
                if (v >= low_from && v <= low_to) || (v >= high_from && v <= high_to) { let bit = bit_of(v); moved[bit >> 6] |= 1u64 << (bit & 63); }
            }
        }
        let suspicious = |s: &State, v: i32| -> bool {
            if !((v >= low_from && v <= low_to) || (v >= high_from && v <= high_to)) { return false; }
            let bit = bit_of(v);
            if moved[bit >> 6] >> (bit & 63) & 1 == 0 { return false; }
            s.a.node_at(v, memmin) != 0 && s.b.node_at(v, memmin) != 0
        };
        let (mut i, mut range) = (0usize, 0usize);
        while i < length {
            while range * 2 < excluded.len() && (excluded[range * 2 + 1] as usize) <= i * 4 { range += 1; }
            if range * 2 < excluded.len() && (excluded[range * 2] as usize) <= i * 4 { i = (excluded[range * 2 + 1] as usize + 3) / 4; continue; }
            let v = *words_a.add(i) as i32;
            if v != *words_b.add(i) as i32 || !suspicious(&s, v) { i += 1; continue; }
            let at = i * 4;
            if is_excluded(at as u32) || in_ranges(no_pointers, at as u32) { i += 1; continue; }
            if at >= mem0 && at < mem_end {
                let w = word_of(at);
                if s.a.free_of(w, memmin) != 0 && s.b.free_of(w, memmin) != 0 { i += 1; continue; }
                let single = s.a.is_single(w) && s.b.is_single(w);
                if single && (at - mem0) & 4 == 0 && (v & 0xffff) <= 255 { i += 1; continue; }   // font and character
                let sa = if s.a.is_single(w) { w } else if s.a.is_variable(w, memmin) { s.a.segment_start(w, memmin) } else { w };
                let sb = if s.b.is_single(w) { w } else if s.b.is_variable(w, memmin) { s.b.segment_start(w, memmin) } else { w };
                if s.phi.get(sa).is_some_and(|q| q != sa) || s.inverse.get(sb).is_some_and(|q| q != sb) { i += 1; continue; }
            }
            fail!(F_HIDDEN, at, v, 0)
        }
        // The words of moved nodes, each against its counterpart.
        let keys: Vec<i32> = s.phi.keys.iter().copied().filter(|k| *k != EMPTY).collect();
        for p0 in keys {
            let q0 = s.phi.get(p0).unwrap();
            if p0 == q0 { continue; }
            let (n, single) = (s.sizes.get(p0).unwrap(), s.a.is_single(p0));
            if !single { moved_variable += 1; }
            for w in 0..n { for half in 0..2usize {
                let x = s.a.half(mem0, memmin, p0 + w, half);
                if x != s.b.half(mem0, memmin, q0 + w, half) || !suspicious(&s, x) { continue; }
                if single && half == 0 && (x & 0xffff) <= 255 { continue; }
                fail!(F_HIDDEN, p0, x, 1)
            } }
        }
    }
    result[0] = CONVERGED; result[1] = stale; result[4] = s.phi.used as u32; result[5] = moved_variable; result[7] = withdrawn;
    1
}
