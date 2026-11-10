// Page index of a complete PDF, for changed-page updates.
// Private memory only: no imports, never reads or writes compiler memory.
// The host copies one PDF in, calls index(), and copies a compact table out:
// per page its object numbers, dictionary text and a hash of the decoded
// content stream. Anything not understood fails the call or flags the page;
// nothing is guessed.
#![no_std]
extern crate alloc;
use alloc::vec::Vec;
use core::alloc::{GlobalAlloc, Layout};
use core::arch::wasm32::{memory_grow, memory_size, unreachable};

#[panic_handler]
fn panic(_: &core::panic::PanicInfo<'_>) -> ! { unreachable() }

// ---- Private bump allocator. Reset by input_reserve(); nothing is freed in
// between, so every call works inside one bounded arena.
const MEMORY_LIMIT: usize = 1 << 30;
extern "C" { static __heap_base: u8; }
static mut NEXT: usize = 0;
static mut INPUT: (usize, usize) = (0, 0);
static mut OUTPUT: (usize, usize) = (0, 0);
struct Bump;
unsafe fn ensure(end: usize) -> bool {
    if end > MEMORY_LIMIT { return false; }
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
    unsafe fn realloc(&self, pointer: *mut u8, layout: Layout, size: usize) -> *mut u8 {
        if pointer as usize + layout.size() == NEXT {
            let end = match (pointer as usize).checked_add(size) { Some(end) => end, None => return core::ptr::null_mut() };
            if !ensure(end) { return core::ptr::null_mut(); }
            NEXT = end;
            return pointer;
        }
        if size <= layout.size() { return pointer; }
        let fresh = self.alloc(Layout::from_size_align_unchecked(size, layout.align()));
        if !fresh.is_null() { core::ptr::copy_nonoverlapping(pointer, fresh, layout.size()); }
        fresh
    }
}
#[global_allocator]
static ALLOCATOR: Bump = Bump;

type R<T> = Result<T, i32>;
const E_INPUT: i32 = -1;
const E_STARTXREF: i32 = -2;
const E_XREF: i32 = -3;
const E_UNSUPPORTED: i32 = -4;
const E_OBJECT: i32 = -5;
const E_STREAM: i32 = -6;
const E_INFLATE: i32 = -7;
const E_PAGES: i32 = -8;
const E_LIMIT: i32 = -9;

const MAX_INPUT: usize = 512 << 20;
const MAX_OBJECTS: usize = 4 << 20;
const MAX_PAGES: usize = 200_000;
const MAX_TABLE_BYTES: usize = 64 << 20;
const MAX_CACHE_BYTES: usize = 256 << 20;
const MAX_CONTENT_BYTES: usize = 4 << 20;
const MAX_DICT_BYTES: usize = 16 << 10;
const MAX_RESOURCE_BYTES: usize = 8 << 10;

// ---- Inflate (RFC 1951) inside a zlib wrapper (RFC 1950), checksum verified.
struct Bits<'a> { data: &'a [u8], at: usize, hold: u64, count: u32, padded: u32 }
impl<'a> Bits<'a> {
    #[inline(always)]
    fn fill(&mut self) {
        while self.count <= 56 {
            if self.at < self.data.len() { self.hold |= (self.data[self.at] as u64) << self.count; self.at += 1; }
            else { self.padded += 8; }
            self.count += 8;
        }
    }
    #[inline(always)]
    fn take(&mut self, bits: u32) -> u32 {
        if self.count < bits { self.fill(); }
        let value = (self.hold & ((1u64 << bits) - 1)) as u32;
        self.hold >>= bits; self.count -= bits;
        value
    }
    /// False once more bits were consumed than the input held.
    #[inline(always)]
    fn sound(&self) -> bool { self.count >= self.padded }
}
struct Huffman { fast: [u16; 1024], counts: [u16; 16], symbols: [u16; 288] }
impl Huffman {
    const fn new() -> Self { Huffman { fast: [0; 1024], counts: [0; 16], symbols: [0; 288] } }
    /// Canonical code from lengths. Returns the unused code space: 0 complete,
    /// positive incomplete, negative over-subscribed.
    fn build(&mut self, lengths: &[u8]) -> i32 {
        self.counts = [0; 16];
        self.fast = [0; 1024];
        for &length in lengths { self.counts[length as usize] += 1; }
        if self.counts[0] as usize == lengths.len() { return 0; }
        let mut left: i32 = 1;
        for length in 1..16 { left <<= 1; left -= self.counts[length] as i32; if left < 0 { return left; } }
        let mut offsets = [0u16; 16];
        let mut codes = [0u32; 16];
        let mut code = 0u32;
        for length in 1..16 {
            offsets[length] = offsets[length - 1] + if length > 1 { self.counts[length - 1] } else { 0 };
            code = (code + if length > 1 { self.counts[length - 1] as u32 } else { 0 }) << 1;
            codes[length] = code;
        }
        for (symbol, &length) in lengths.iter().enumerate() {
            let length = length as usize;
            if length == 0 { continue; }
            self.symbols[offsets[length] as usize] = symbol as u16;
            offsets[length] += 1;
            if length <= 10 {
                let mut reversed = 0usize;
                for bit in 0..length { if codes[length] >> bit & 1 != 0 { reversed |= 1 << (length - 1 - bit); } }
                let mut slot = reversed;
                while slot < 1024 { self.fast[slot] = ((symbol as u16) << 4) | length as u16; slot += 1 << length; }
            }
            codes[length] += 1;
        }
        left
    }
    #[inline(always)]
    fn decode(&self, bits: &mut Bits) -> R<usize> {
        bits.fill();
        let entry = self.fast[(bits.hold & 1023) as usize];
        if entry & 15 != 0 { bits.hold >>= entry & 15; bits.count -= (entry & 15) as u32; return Ok((entry >> 4) as usize); }
        let (mut code, mut first, mut index) = (0i32, 0i32, 0i32);
        for length in 1..16 {
            code |= (bits.hold >> (length - 1) & 1) as i32;
            let count = self.counts[length] as i32;
            if code - count < first {
                bits.hold >>= length; bits.count -= length as u32;
                return Ok(self.symbols[(index + code - first) as usize] as usize);
            }
            index += count; first += count; first <<= 1; code <<= 1;
        }
        Err(E_INFLATE)
    }
}
const LENGTH_BASE: [u16; 29] = [3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 15, 17, 19, 23, 27, 31, 35, 43, 51, 59, 67, 83, 99, 115, 131, 163, 195, 227, 258];
const LENGTH_EXTRA: [u8; 29] = [0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4, 5, 5, 5, 5, 0];
const DISTANCE_BASE: [u16; 30] = [1, 2, 3, 4, 5, 7, 9, 13, 17, 25, 33, 49, 65, 97, 129, 193, 257, 385, 513, 769, 1025, 1537, 2049, 3073, 4097, 6145, 8193, 12289, 16385, 24577];
const DISTANCE_EXTRA: [u8; 30] = [0, 0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9, 10, 10, 11, 11, 12, 12, 13, 13];
const ORDER: [usize; 19] = [16, 17, 18, 0, 8, 7, 9, 6, 10, 5, 11, 4, 12, 3, 13, 2, 14, 1, 15];

fn inflate(data: &[u8], out: &mut Vec<u8>, limit: usize) -> R<()> {
    out.clear();
    if data.len() < 6 || data[0] & 15 != 8 || data[0] >> 4 > 7 || data[1] & 32 != 0
        || ((data[0] as u32) << 8 | data[1] as u32) % 31 != 0 { return Err(E_INFLATE); }
    let mut bits = Bits { data: &data[2..], at: 0, hold: 0, count: 0, padded: 0 };
    let mut literal = Huffman::new();
    let mut distance = Huffman::new();
    loop {
        let last = bits.take(1);
        match bits.take(2) {
            0 => {
                let drop = bits.count & 7;
                bits.take(drop);
                let length = bits.take(16);
                if bits.take(16) != length ^ 0xffff || !bits.sound() { return Err(E_INFLATE); }
                if out.len() + length as usize > limit { return Err(E_LIMIT); }
                for _ in 0..length { let byte = bits.take(8) as u8; out.push(byte); }
            }
            1 => {
                let mut lengths = [8u8; 288];
                for symbol in 144..256 { lengths[symbol] = 9; }
                for symbol in 256..280 { lengths[symbol] = 7; }
                literal.build(&lengths);
                distance.build(&[5u8; 30]);
                codes(&mut bits, &literal, &distance, out, limit)?;
            }
            2 => {
                let literals = bits.take(5) as usize + 257;
                let distances = bits.take(5) as usize + 1;
                let lengths_count = bits.take(4) as usize + 4;
                if literals > 286 || distances > 30 { return Err(E_INFLATE); }
                let mut lengths = [0u8; 320];
                for index in 0..lengths_count { lengths[ORDER[index]] = bits.take(3) as u8; }
                if literal.build(&lengths[..19]) != 0 { return Err(E_INFLATE); }
                let mut index = 0;
                while index < literals + distances {
                    let symbol = literal.decode(&mut bits)?;
                    if symbol < 16 { lengths[index] = symbol as u8; index += 1; continue; }
                    let (value, repeat) = match symbol {
                        16 => { if index == 0 { return Err(E_INFLATE); } (lengths[index - 1], 3 + bits.take(2) as usize) }
                        17 => (0, 3 + bits.take(3) as usize),
                        _ => (0, 11 + bits.take(7) as usize),
                    };
                    if index + repeat > literals + distances { return Err(E_INFLATE); }
                    for _ in 0..repeat { lengths[index] = value; index += 1; }
                }
                if !bits.sound() || lengths[256] == 0 { return Err(E_INFLATE); }
                let mut distance_lengths = [0u8; 30];
                distance_lengths[..distances].copy_from_slice(&lengths[literals..literals + distances]);
                let left = literal.build(&lengths[..literals]);
                if left < 0 || (left > 0 && literals - literal.counts[0] as usize != 1) { return Err(E_INFLATE); }
                let left = distance.build(&distance_lengths[..distances]);
                if left < 0 || (left > 0 && distances - distance.counts[0] as usize != 1) { return Err(E_INFLATE); }
                codes(&mut bits, &literal, &distance, out, limit)?;
            }
            _ => return Err(E_INFLATE),
        }
        if !bits.sound() { return Err(E_INFLATE); }
        if last == 1 { break; }
    }
    let drop = bits.count & 7;
    bits.take(drop);
    let unread = ((bits.count - bits.padded) / 8) as usize;
    let at = bits.at - unread;
    let tail = bits.data;
    if at + 4 > tail.len() { return Err(E_INFLATE); }
    let (mut a, mut b) = (1u32, 0u32);
    for chunk in out.chunks(5552) {
        for &byte in chunk { a += byte as u32; b += a; }
        a %= 65521; b %= 65521;
    }
    if u32::from_be_bytes([tail[at], tail[at + 1], tail[at + 2], tail[at + 3]]) != (b << 16 | a) { return Err(E_INFLATE); }
    Ok(())
}
fn codes(bits: &mut Bits, literal: &Huffman, distance: &Huffman, out: &mut Vec<u8>, limit: usize) -> R<()> {
    loop {
        let symbol = literal.decode(bits)?;
        if symbol < 256 {
            if out.len() >= limit { return Err(E_LIMIT); }
            out.push(symbol as u8);
            continue;
        }
        if symbol == 256 { return Ok(()); }
        let symbol = symbol - 257;
        if symbol >= 29 { return Err(E_INFLATE); }
        let length = LENGTH_BASE[symbol] as usize + bits.take(LENGTH_EXTRA[symbol] as u32) as usize;
        let symbol = distance.decode(bits)?;
        if symbol >= 30 { return Err(E_INFLATE); }
        let back = DISTANCE_BASE[symbol] as usize + bits.take(DISTANCE_EXTRA[symbol] as u32) as usize;
        if !bits.sound() || back > out.len() { return Err(E_INFLATE); }
        if out.len() + length > limit { return Err(E_LIMIT); }
        let from = out.len() - back;
        if back >= length { out.extend_from_within(from..from + length); }
        else { for index in 0..length { let byte = out[from + index]; out.push(byte); } }
    }
}

// ---- PDF syntax, only as far as locating objects and dictionary entries.
#[inline(always)]
fn is_space(byte: u8) -> bool { matches!(byte, 0 | 9 | 10 | 12 | 13 | 32) }
#[inline(always)]
fn is_delimiter(byte: u8) -> bool { matches!(byte, b'(' | b')' | b'<' | b'>' | b'[' | b']' | b'{' | b'}' | b'/' | b'%') }
fn skip_space(data: &[u8], mut at: usize) -> usize {
    loop {
        while at < data.len() && is_space(data[at]) { at += 1; }
        if at < data.len() && data[at] == b'%' { while at < data.len() && data[at] != 10 && data[at] != 13 { at += 1; } }
        else { return at; }
    }
}
fn token_end(data: &[u8], mut at: usize) -> usize {
    while at < data.len() && !is_space(data[at]) && !is_delimiter(data[at]) { at += 1; }
    at
}
fn starts(data: &[u8], at: usize, text: &[u8]) -> bool { data.len() >= at + text.len() && &data[at..at + text.len()] == text }
fn keyword(data: &[u8], at: usize, text: &[u8]) -> bool {
    starts(data, at, text) && (at + text.len() == data.len() || is_space(data[at + text.len()]) || is_delimiter(data[at + text.len()]))
}
fn number(data: &[u8], at: usize) -> R<(usize, usize)> {
    let (mut value, mut end) = (0u64, at);
    while end < data.len() && data[end].is_ascii_digit() {
        value = value * 10 + (data[end] - b'0') as u64;
        if value > u32::MAX as u64 { return Err(E_OBJECT); }
        end += 1;
    }
    if end == at { Err(E_OBJECT) } else { Ok((value as usize, end)) }
}
/// `N G R` starting at `at`; returns the object, generation and end.
fn reference(data: &[u8], at: usize) -> R<(usize, usize, usize)> {
    let (object, end) = number(data, at)?;
    if end >= data.len() || !is_space(data[end]) { return Err(E_OBJECT); }
    let (generation, end) = number(data, skip_space(data, end))?;
    if end >= data.len() || !is_space(data[end]) { return Err(E_OBJECT); }
    let end = skip_space(data, end);
    if keyword(data, end, b"R") { Ok((object, generation, end + 1)) } else { Err(E_OBJECT) }
}
fn skip_value(data: &[u8], at: usize, depth: u32) -> R<usize> {
    if depth > 64 { return Err(E_LIMIT); }
    let at = skip_space(data, at);
    if at >= data.len() { return Err(E_OBJECT); }
    match data[at] {
        b'<' if starts(data, at, b"<<") => {
            let mut next = at + 2;
            loop {
                next = skip_space(data, next);
                if starts(data, next, b">>") { return Ok(next + 2); }
                if next >= data.len() || data[next] != b'/' { return Err(E_OBJECT); }
                next = skip_value(data, token_end(data, next + 1), depth + 1)?;
            }
        }
        b'<' => {
            let mut next = at + 1;
            while next < data.len() && data[next] != b'>' { next += 1; }
            if next < data.len() { Ok(next + 1) } else { Err(E_OBJECT) }
        }
        b'[' => {
            let mut next = at + 1;
            loop {
                next = skip_space(data, next);
                if next >= data.len() { return Err(E_OBJECT); }
                if data[next] == b']' { return Ok(next + 1); }
                next = skip_value(data, next, depth + 1)?;
            }
        }
        b'(' => {
            let (mut next, mut open) = (at + 1, 1u32);
            while next < data.len() {
                match data[next] {
                    b'\\' => next += 1,
                    b'(' => open += 1,
                    b')' => { open -= 1; if open == 0 { return Ok(next + 1); } }
                    _ => {}
                }
                next += 1;
            }
            Err(E_OBJECT)
        }
        b'/' => Ok(token_end(data, at + 1)),
        b')' | b'>' | b']' | b'{' | b'}' => Err(E_OBJECT),
        _ => {
            let end = token_end(data, at);
            if end == at { return Err(E_OBJECT); }
            match reference(data, at) { Ok((_, _, end)) => Ok(end), Err(_) => Ok(end) }
        }
    }
}
/// Entries of the dictionary at `at`, in order: (key start, key end, value start, value end).
struct Entries<'a> { data: &'a [u8], at: usize, done: bool }
fn entries(data: &[u8], at: usize) -> R<Entries<'_>> {
    let at = skip_space(data, at);
    if starts(data, at, b"<<") { Ok(Entries { data, at: at + 2, done: false }) } else { Err(E_OBJECT) }
}
impl<'a> Entries<'a> {
    fn next(&mut self) -> R<Option<(usize, usize, usize, usize)>> {
        if self.done { return Ok(None); }
        let key = skip_space(self.data, self.at);
        if starts(self.data, key, b">>") { self.done = true; self.at = key + 2; return Ok(None); }
        if key >= self.data.len() || self.data[key] != b'/' { return Err(E_OBJECT); }
        let key_end = token_end(self.data, key + 1);
        let value = skip_space(self.data, key_end);
        let value_end = skip_value(self.data, value, 1)?;
        self.at = value_end;
        Ok(Some((key + 1, key_end, value, value_end)))
    }
}
fn lookup(data: &[u8], at: usize, name: &[u8]) -> R<Option<(usize, usize)>> {
    let mut all = entries(data, at)?;
    while let Some((key, key_end, value, value_end)) = all.next()? {
        if &data[key..key_end] == name { return Ok(Some((value, value_end))); }
    }
    Ok(None)
}
fn is_name(data: &[u8], span: (usize, usize), name: &[u8]) -> bool {
    span.1 > span.0 && data[span.0] == b'/' && &data[span.0 + 1..span.1] == name
}

#[derive(Clone, Copy)]
struct Entry { kind: u8, first: u32, second: u32 }
struct Container { object: usize, data: Vec<u8>, table: Vec<(u32, u32)>, first: usize }
/// Where an object's value lives: source 0 is the file, source n is container n - 1.
#[derive(Clone, Copy)]
struct Span { source: usize, start: usize, end: usize }
struct Pdf<'a> { data: &'a [u8], table: Vec<Entry>, containers: Vec<Container>, cached: usize }

impl<'a> Pdf<'a> {
    fn bytes(&self, source: usize) -> &[u8] { if source == 0 { self.data } else { &self.containers[source - 1].data } }
    /// Value start and generation of the object stored directly at `offset`.
    fn direct(&self, offset: usize, expected: Option<usize>) -> R<(usize, usize)> {
        let data = self.data;
        if offset >= data.len() { return Err(E_OBJECT); }
        let (object, end) = number(data, skip_space(data, offset))?;
        let (generation, end) = number(data, skip_space(data, end))?;
        let end = skip_space(data, end);
        if !keyword(data, end, b"obj") || expected.is_some_and(|value| value != object) { return Err(E_OBJECT); }
        Ok((end + 3, generation))
    }
    /// Raw stream bytes following the dictionary that ends at `end`.
    fn stream(&mut self, start: usize, end: usize, resolve: bool) -> R<(usize, usize)> {
        let data = self.data;
        let mut at = skip_space(data, end);
        if !starts(data, at, b"stream") { return Err(E_STREAM); }
        at += 6;
        if starts(data, at, b"\r\n") { at += 2; } else if at < data.len() && (data[at] == 10 || data[at] == 13) { at += 1; } else { return Err(E_STREAM); }
        let length = lookup(data, start, b"Length")?.ok_or(E_STREAM)?;
        let length = match reference(data, length.0) {
            Ok((object, _, _)) if resolve => {
                let span = self.locate(object)?;
                number(self.bytes(span.source), skip_space(self.bytes(span.source), span.start))?.0
            }
            Ok(_) => return Err(E_STREAM),
            Err(_) => number(data, length.0)?.0,
        };
        let stop = at.checked_add(length).filter(|&stop| stop <= data.len()).ok_or(E_STREAM)?;
        if !starts(data, skip_space(data, stop), b"endstream") { return Err(E_STREAM); }
        Ok((at, stop))
    }
    /// Decode the stream of the dictionary at `start..end` (file only).
    /// Only an absent filter or one FlateDecode without parameters is accepted
    /// unless `predictor` is set, which also admits PNG row prediction.
    fn decode(&mut self, start: usize, end: usize, out: &mut Vec<u8>, limit: usize, resolve: bool, predictor: bool) -> R<()> {
        let data = self.data;
        let (from, to) = self.stream(start, end, resolve)?;
        let filter = match lookup(data, start, b"Filter")? {
            None => None,
            Some(span) if is_name(data, span, b"FlateDecode") => Some(()),
            Some((value, value_end)) if data[value] == b'[' => {
                let name = skip_space(data, value + 1);
                if name < value_end && data[name] == b']' { None } else {
                    let name_end = token_end(data, name + 1);
                    if !is_name(data, (name, name_end), b"FlateDecode") || skip_space(data, name_end) + 1 != value_end { return Err(E_STREAM); }
                    Some(())
                }
            }
            Some(_) => return Err(E_STREAM),
        };
        let parameters = lookup(data, start, b"DecodeParms")?;
        if filter.is_none() {
            if parameters.is_some() || to - from > limit { return Err(E_STREAM); }
            out.clear();
            out.extend_from_slice(&data[from..to]);
            return Ok(());
        }
        inflate(&data[from..to], out, limit)?;
        let Some((parameters, _)) = parameters else { return Ok(()) };
        if !predictor || !starts(data, parameters, b"<<") { return Err(E_STREAM); }
        let read = |name: &[u8], default: usize| -> R<usize> {
            match lookup(data, parameters, name)? { Some((value, _)) => Ok(number(data, value)?.0), None => Ok(default) }
        };
        let kind = read(b"Predictor", 1)?;
        if kind == 1 { return Ok(()); }
        let columns = read(b"Columns", 1)?;
        if kind < 10 || read(b"Colors", 1)? != 1 || read(b"BitsPerComponent", 8)? != 8 || columns == 0 || columns > 64
            || out.len() % (columns + 1) != 0 { return Err(E_STREAM); }
        let rows = out.len() / (columns + 1);
        for row in 0..rows {
            let (source, target) = (row * (columns + 1), row * columns);
            let filter = out[source];
            for column in 0..columns {
                let raw = out[source + 1 + column];
                let left = if column > 0 { out[target + column - 1] } else { 0 };
                let up = if row > 0 { out[target - columns + column] } else { 0 };
                out[target + column] = match filter { 0 => raw, 1 => raw.wrapping_add(left), 2 => raw.wrapping_add(up), _ => return Err(E_STREAM) };
            }
        }
        out.truncate(rows * columns);
        Ok(())
    }
    fn container(&mut self, object: usize) -> R<usize> {
        if let Some(index) = self.containers.iter().position(|item| item.object == object) { return Ok(index); }
        let entry = *self.table.get(object).ok_or(E_OBJECT)?;
        if entry.kind != 1 { return Err(E_OBJECT); }
        let data = self.data;
        let (start, _) = self.direct(entry.first as usize, Some(object))?;
        let start = skip_space(data, start);
        let end = skip_value(data, start, 0)?;
        if !lookup(data, start, b"Type")?.is_some_and(|span| is_name(data, span, b"ObjStm")) || lookup(data, start, b"Extends")?.is_some() { return Err(E_OBJECT); }
        let count = number(data, lookup(data, start, b"N")?.ok_or(E_OBJECT)?.0)?.0;
        let first = number(data, lookup(data, start, b"First")?.ok_or(E_OBJECT)?.0)?.0;
        let mut decoded = Vec::new();
        self.decode(start, end, &mut decoded, MAX_TABLE_BYTES, false, false)?;
        self.cached += decoded.len();
        if self.cached > MAX_CACHE_BYTES || count > MAX_OBJECTS || first > decoded.len() { return Err(E_LIMIT); }
        let mut table = Vec::with_capacity(count);
        let mut at = 0;
        for _ in 0..count {
            let (number_value, end) = number(&decoded[..first], skip_space(&decoded[..first], at))?;
            let (offset, end) = number(&decoded[..first], skip_space(&decoded[..first], end))?;
            if first + offset > decoded.len() { return Err(E_OBJECT); }
            table.push((number_value as u32, offset as u32));
            at = end;
        }
        self.containers.push(Container { object, data: decoded, table, first });
        Ok(self.containers.len() - 1)
    }
    fn locate(&mut self, object: usize) -> R<Span> {
        let entry = *self.table.get(object).ok_or(E_OBJECT)?;
        match entry.kind {
            1 => {
                let (start, _) = self.direct(entry.first as usize, Some(object))?;
                let start = skip_space(self.data, start);
                Ok(Span { source: 0, start, end: skip_value(self.data, start, 0)? })
            }
            2 => {
                let index = self.container(entry.first as usize)?;
                let container = &self.containers[index];
                let slot = entry.second as usize;
                let &(stored, offset) = container.table.get(slot).ok_or(E_OBJECT)?;
                if stored as usize != object { return Err(E_OBJECT); }
                let start = skip_space(&container.data, container.first + offset as usize);
                let end = skip_value(&container.data, start, 0)?;
                Ok(Span { source: index + 1, start, end })
            }
            _ => Err(E_OBJECT),
        }
    }
}

fn find_last(data: &[u8], text: &[u8]) -> Option<usize> {
    let from = data.len().saturating_sub(2048);
    (from..data.len().saturating_sub(text.len()) + 1).rev().find(|&at| starts(data, at, text))
}
/// Fill the table from the cross-reference section at `offset`; returns the
/// trailer dictionary position and whether the section is a stream.
fn cross_reference(pdf: &mut Pdf, offset: usize) -> R<(usize, bool)> {
    let data = pdf.data;
    let free = Entry { kind: 0, first: 0, second: 0 };
    if keyword(data, offset, b"xref") {
        let mut at = offset + 4;
        loop {
            at = skip_space(data, at);
            if keyword(data, at, b"trailer") { return Ok((skip_space(data, at + 7), false)); }
            let (first, end) = number(data, at).map_err(|_| E_XREF)?;
            let (count, end) = number(data, skip_space(data, end)).map_err(|_| E_XREF)?;
            if first + count > MAX_OBJECTS { return Err(E_LIMIT); }
            if pdf.table.len() < first + count { pdf.table.resize(first + count, free); }
            at = end;
            for index in 0..count {
                let (position, end) = number(data, skip_space(data, at)).map_err(|_| E_XREF)?;
                let (generation, end) = number(data, skip_space(data, end)).map_err(|_| E_XREF)?;
                let flag = skip_space(data, end);
                if flag >= data.len() || position > u32::MAX as usize { return Err(E_XREF); }
                pdf.table[first + index] = match data[flag] {
                    b'n' => Entry { kind: 1, first: position as u32, second: generation as u32 },
                    b'f' => free,
                    _ => return Err(E_XREF),
                };
                at = flag + 1;
            }
        }
    }
    let (start, _) = pdf.direct(offset, None).map_err(|_| E_XREF)?;
    let start = skip_space(data, start);
    let end = skip_value(data, start, 0).map_err(|_| E_XREF)?;
    if !lookup(data, start, b"Type")?.is_some_and(|span| is_name(data, span, b"XRef")) { return Err(E_XREF); }
    let size = number(data, lookup(data, start, b"Size")?.ok_or(E_XREF)?.0)?.0;
    if size > MAX_OBJECTS { return Err(E_LIMIT); }
    let (widths, _) = lookup(data, start, b"W")?.ok_or(E_XREF)?;
    if data[widths] != b'[' { return Err(E_XREF); }
    let mut width = [0usize; 3];
    let mut at = widths + 1;
    for item in width.iter_mut() { let (value, end) = number(data, skip_space(data, at))?; *item = value; at = end; }
    if width.iter().any(|&value| value > 8) || width[1] == 0 { return Err(E_XREF); }
    let mut decoded = Vec::new();
    pdf.decode(start, end, &mut decoded, MAX_TABLE_BYTES, false, true)?;
    pdf.table.resize(size, free);
    let row = width[0] + width[1] + width[2];
    let mut cursor = 0;
    let mut fill = |pdf: &mut Pdf, first: usize, count: usize| -> R<()> {
        if first + count > size || cursor + count * row > decoded.len() { return Err(E_XREF); }
        for index in 0..count {
            let mut field = [1u64, 0, 0];
            for part in 0..3 {
                if width[part] > 0 { field[part] = 0; }
                for _ in 0..width[part] { field[part] = field[part] << 8 | decoded[cursor] as u64; cursor += 1; }
            }
            if field[1] > u32::MAX as u64 || field[2] > u32::MAX as u64 { return Err(E_XREF); }
            pdf.table[first + index] = match field[0] {
                0 => free,
                1 | 2 => Entry { kind: field[0] as u8, first: field[1] as u32, second: field[2] as u32 },
                _ => return Err(E_XREF),
            };
        }
        Ok(())
    };
    match lookup(data, start, b"Index")? {
        None => fill(pdf, 0, size)?,
        Some((value, _)) => {
            if data[value] != b'[' { return Err(E_XREF); }
            let mut at = skip_space(data, value + 1);
            while at < data.len() && data[at] != b']' {
                let (first, end) = number(data, at)?;
                let (count, end) = number(data, skip_space(data, end))?;
                fill(pdf, first, count)?;
                at = skip_space(data, end);
            }
        }
    }
    Ok((start, true))
}

// Page flags reported to the host.
const HAS_ANNOTATIONS: u32 = 1;
const HAS_BEADS: u32 = 2;
const HAS_OTHER_KEYS: u32 = 4;
const NO_MEDIA_BOX: u32 = 8;
const NO_RESOURCES: u32 = 16;
const CONTENT_UNREADABLE: u32 = 32;
const DICTIONARY_UNUSABLE: u32 = 64;
const CONTENT_SHARED: u32 = 128;
const RECORD_WORDS: usize = 12;
const HEADER_WORDS: usize = 16;

fn content_hash(data: &[u8]) -> (u32, u32) {
    let (mut low, mut high) = (0x811c9dc5u32, 0x9e3779b9u32);
    for &byte in data {
        low = (low ^ byte as u32).wrapping_mul(0x01000193);
        high = (high.rotate_left(5) ^ byte as u32).wrapping_mul(0x9e3779b1);
    }
    (low, high)
}

fn build(data: &[u8]) -> R<Vec<u8>> {
    let start = find_last(data, b"startxref").ok_or(E_STARTXREF)?;
    let (offset, _) = number(data, skip_space(data, start + 9)).map_err(|_| E_STARTXREF)?;
    let mut pdf = Pdf { data, table: Vec::new(), containers: Vec::new(), cached: 0 };
    let (trailer, is_stream) = cross_reference(&mut pdf, offset)?;
    for name in [&b"Prev"[..], b"Encrypt", b"XRefStm"] { if lookup(data, trailer, name)?.is_some() { return Err(E_UNSUPPORTED); } }
    let size = number(data, lookup(data, trailer, b"Size")?.ok_or(E_XREF)?.0)?.0;
    if size != pdf.table.len() { return Err(E_XREF); }
    let (root, root_generation, _) = reference(data, lookup(data, trailer, b"Root")?.ok_or(E_XREF)?.0)?;
    let info = match lookup(data, trailer, b"Info")? { Some((value, _)) => { let (object, generation, _) = reference(data, value)?; (object, generation) } None => (0, 0) };
    let identifier = lookup(data, trailer, b"ID")?;

    let mut records: Vec<[u32; RECORD_WORDS]> = Vec::new();
    let mut blob: Vec<u8> = Vec::new();
    if let Some((value, end)) = identifier { blob.extend_from_slice(&data[value..end]); }
    let identifier_length = blob.len();
    let mut scratch: Vec<u8> = Vec::new();
    let mut used = alloc::vec![0u8; size / 8 + 1];
    let mut shared = alloc::vec![0u8; size / 8 + 1];

    let catalog = pdf.locate(root)?;
    let (pages, _, _) = {
        let source = pdf.bytes(catalog.source);
        reference(source, lookup(source, catalog.start, b"Pages")?.ok_or(E_PAGES)?.0).map_err(|_| E_PAGES)?
    };
    let mut pending: Vec<usize> = Vec::new();
    pending.push(pages);
    let mut visited = 0usize;
    while let Some(object) = pending.pop() {
        visited += 1;
        if visited > size + 1 || records.len() >= MAX_PAGES { return Err(E_PAGES); }
        let span = pdf.locate(object).map_err(|_| E_PAGES)?;
        let kids = { let source = pdf.bytes(span.source); lookup(source, span.start, b"Kids").map_err(|_| E_PAGES)? };
        if let Some((value, value_end)) = kids {
            let source = pdf.bytes(span.source);
            if source[value] != b'[' { return Err(E_PAGES); }
            let first = pending.len();
            let mut at = skip_space(source, value + 1);
            while at + 1 < value_end {
                let (kid, _, end) = reference(source, at).map_err(|_| E_PAGES)?;
                pending.push(kid);
                at = skip_space(source, end);
            }
            pending[first..].reverse();
            continue;
        }
        let mut record = [0u32; RECORD_WORDS];
        record[0] = object as u32;
        let mut flags = 0u32;
        let (mut contents, mut resources) = (None, None);
        {
            let source = pdf.bytes(span.source);
            if !lookup(source, span.start, b"Type").map_err(|_| E_PAGES)?.is_some_and(|value| is_name(source, value, b"Page")) { return Err(E_PAGES); }
            let mut has_box = false;
            let mut all = entries(source, span.start)?;
            while let Some((key, key_end, value, value_end)) = all.next()? {
                match &source[key..key_end] {
                    b"Type" | b"Parent" => {}
                    b"MediaBox" => has_box = true,
                    b"Contents" => contents = Some((value, value_end)),
                    b"Resources" => resources = Some((value, value_end)),
                    b"Annots" => flags |= HAS_ANNOTATIONS | HAS_OTHER_KEYS,
                    b"B" => flags |= HAS_BEADS | HAS_OTHER_KEYS,
                    _ => flags |= HAS_OTHER_KEYS,
                }
            }
            if !has_box { flags |= NO_MEDIA_BOX; }
            if pdf.table[object].kind == 1 && pdf.table[object].second != 0 { flags |= DICTIONARY_UNUSABLE; }
            if span.end - span.start > MAX_DICT_BYTES { flags |= DICTIONARY_UNUSABLE; }
            else {
                record[6] = blob.len() as u32;
                record[7] = (span.end - span.start) as u32;
                blob.extend_from_slice(&source[span.start..span.end]);
            }
        }
        // Resources: where the value sits in the page dictionary, and its resolved text.
        match resources {
            None => flags |= NO_RESOURCES,
            Some((value, value_end)) => {
                record[8] = (value - span.start) as u32;
                record[9] = (value_end - span.start) as u32;
                let target = { let source = pdf.bytes(span.source); reference(source, value).ok() };
                let resolved = match target { Some((target, _, _)) => pdf.locate(target).ok(), None => Some(Span { source: span.source, start: value, end: value_end }) };
                match resolved {
                    Some(found) if found.end - found.start <= MAX_RESOURCE_BYTES && starts(pdf.bytes(found.source), found.start, b"<<") => {
                        record[10] = blob.len() as u32;
                        record[11] = (found.end - found.start) as u32;
                        blob.extend_from_slice(&pdf.bytes(found.source)[found.start..found.end]);
                    }
                    _ => flags |= NO_RESOURCES,
                }
            }
        }
        // Content: one direct, generation-zero stream object, decoded and hashed.
        let target = contents.and_then(|(value, value_end)| {
            let source = pdf.bytes(span.source);
            // xdvipdfmx writes a one-element array.
            let (value, value_end) = if source[value] == b'[' && source[value_end - 1] == b']' {
                let mut last = value_end - 1;
                while last > value + 1 && is_space(source[last - 1]) { last -= 1; }
                (skip_space(source, value + 1), last)
            } else { (value, value_end) };
            reference(source, value).ok().filter(|&(_, generation, end)| generation == 0 && end == value_end).map(|(target, _, _)| target)
        });
        let mut readable = false;
        if let Some(target) = target {
            if target < size {
                let entry = pdf.table[target];
                if entry.kind == 1 && entry.second == 0 {
                    if let Ok((start, _)) = pdf.direct(entry.first as usize, Some(target)) {
                        let start = skip_space(data, start);
                        if let Ok(end) = skip_value(data, start, 0) {
                            if starts(data, start, b"<<") && pdf.decode(start, end, &mut scratch, MAX_CONTENT_BYTES, true, false).is_ok() {
                                let (low, high) = content_hash(&scratch);
                                record[1] = target as u32;
                                record[3] = scratch.len() as u32;
                                record[4] = low;
                                record[5] = high;
                                readable = true;
                                if used[target / 8] >> (target % 8) & 1 != 0 { shared[target / 8] |= 1 << (target % 8); }
                                used[target / 8] |= 1 << (target % 8);
                            }
                        }
                    }
                }
            }
        }
        if !readable { flags |= CONTENT_UNREADABLE; }
        record[2] = flags;
        records.push(record);
    }
    for record in records.iter_mut() {
        let target = record[1] as usize;
        if target != 0 && shared[target / 8] >> (target % 8) & 1 != 0 { record[2] |= CONTENT_SHARED; }
    }

    let records_offset = HEADER_WORDS * 4;
    let data_offset = records_offset + records.len() * RECORD_WORDS * 4;
    let total = data_offset + blob.len();
    if data.len() > u32::MAX as usize || total > u32::MAX as usize { return Err(E_LIMIT); }
    let header: [u32; HEADER_WORDS] = [0x31495053, 1, is_stream as u32, size as u32, root as u32, root_generation as u32,
        info.0 as u32, info.1 as u32, offset as u32, data.len() as u32, records.len() as u32, 0, identifier_length as u32,
        records_offset as u32, data_offset as u32, total as u32];
    let mut out = Vec::with_capacity(total);
    for word in header { out.extend_from_slice(&word.to_le_bytes()); }
    for record in &records { for word in record { out.extend_from_slice(&word.to_le_bytes()); } }
    out.extend_from_slice(&blob);
    Ok(out)
}

/// Discard everything from earlier calls and return room for `length` input bytes (0 on failure).
#[no_mangle]
pub extern "C" fn input_reserve(length: usize) -> *mut u8 {
    unsafe {
        NEXT = (&raw const __heap_base) as usize;
        INPUT = (0, 0);
        OUTPUT = (0, 0);
        if length == 0 || length > MAX_INPUT { return core::ptr::null_mut(); }
        let pointer = ALLOCATOR.alloc(Layout::from_size_align_unchecked(length, 16));
        if !pointer.is_null() { INPUT = (pointer as usize, length); }
        pointer
    }
}
/// Index the reserved input. 0 on success, a negative code otherwise.
#[no_mangle]
pub extern "C" fn index() -> i32 {
    unsafe {
        OUTPUT = (0, 0);
        if INPUT.1 == 0 { return E_INPUT; }
        let data = core::slice::from_raw_parts(INPUT.0 as *const u8, INPUT.1);
        match build(data) {
            Ok(out) => { OUTPUT = (out.as_ptr() as usize, out.len()); core::mem::forget(out); 0 }
            Err(code) => code,
        }
    }
}
/// Hash of the first `length` reserved input bytes, as the index computes it
/// for page content: low word returned, high word via hash_high().
static mut HASH_HIGH: u32 = 0;
#[no_mangle]
pub extern "C" fn hash(length: usize) -> u32 {
    unsafe {
        if length > INPUT.1 { HASH_HIGH = 0; return 0; }
        let (low, high) = content_hash(core::slice::from_raw_parts(INPUT.0 as *const u8, length));
        HASH_HIGH = high;
        low
    }
}
#[no_mangle]
pub extern "C" fn hash_high() -> u32 { unsafe { HASH_HIGH } }
#[no_mangle]
pub extern "C" fn output_pointer() -> *const u8 { unsafe { OUTPUT.0 as *const u8 } }
#[no_mangle]
pub extern "C" fn output_length() -> usize { unsafe { OUTPUT.1 } }
