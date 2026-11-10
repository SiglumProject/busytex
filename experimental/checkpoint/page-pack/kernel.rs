// Lossless block codec for retained checkpoint storage (LZ4 block format).
// Private memory only: no imports, never reads or writes compiler memory.
// The host copies one block in, calls pack/unpack, and copies the result out.
#![no_std]
#[panic_handler]
fn panic(_: &core::panic::PanicInfo<'_>) -> ! { core::arch::wasm32::unreachable() }

const BLOCK: usize = 65536;
const BOUND: usize = BLOCK + BLOCK / 255 + 16;
const HASH_BITS: u32 = 12;
const MIN_MATCH: usize = 4;
// Format rules: the last match starts at least 12 bytes before the end and the
// final 5 bytes are always literals.
const MF_LIMIT: usize = 12;
const LAST_LITERALS: usize = 5;

// Chunked copies may read or write up to SLACK bytes past a validated range.
// Those bytes stay inside these private buffers and are never reported.
const SLACK: usize = 32;
static mut INPUT: [u8; BOUND + SLACK] = [0; BOUND + SLACK];
static mut OUTPUT: [u8; BOUND + SLACK] = [0; BOUND + SLACK];
static mut TABLE: [u16; 1 << HASH_BITS] = [0; 1 << HASH_BITS];

#[no_mangle]
pub extern "C" fn input_pointer() -> *mut u8 { &raw mut INPUT as *mut u8 }
#[no_mangle]
pub extern "C" fn output_pointer() -> *mut u8 { &raw mut OUTPUT as *mut u8 }
#[no_mangle]
pub extern "C" fn block_bytes() -> usize { BLOCK }
#[no_mangle]
pub extern "C" fn buffer_bytes() -> usize { BOUND }

#[inline(always)]
fn read32(data: &[u8], at: usize) -> u32 {
    u32::from_le_bytes([data[at], data[at + 1], data[at + 2], data[at + 3]])
}
#[inline(always)]
fn read64(data: &[u8], at: usize) -> u64 {
    u64::from_le_bytes([data[at], data[at + 1], data[at + 2], data[at + 3], data[at + 4], data[at + 5], data[at + 6], data[at + 7]])
}
/// Forward copy in `step`-byte chunks; may touch up to `step - 1` bytes past
/// `len`. Callers guarantee that slack and, for overlap, a distance >= step.
#[inline(always)]
unsafe fn copy_chunks(from: *const u8, to: *mut u8, len: usize, step: usize) {
    let mut done = 0;
    while done < len {
        if step == 16 {
            (to.add(done) as *mut u128).write_unaligned((from.add(done) as *const u128).read_unaligned());
        } else {
            (to.add(done) as *mut u64).write_unaligned((from.add(done) as *const u64).read_unaligned());
        }
        done += step;
    }
}
#[inline(always)]
fn hash(value: u32) -> usize { (value.wrapping_mul(2654435761) >> (32 - HASH_BITS)) as usize }

fn put_length(out: &mut [u8], mut at: usize, mut rest: usize) -> usize {
    while rest >= 255 { out[at] = 255; at += 1; rest -= 255; }
    out[at] = rest as u8;
    at + 1
}

fn put_sequence(src: &[u8], out: &mut [u8], mut op: usize, anchor: usize, end: usize, matched: Option<(usize, usize)>) -> usize {
    let literals = end - anchor;
    let token = op;
    op += 1;
    let mut value = if literals >= 15 { op = put_length(out, op, literals - 15); 0xf0 } else { (literals as u8) << 4 };
    out[op..op + literals].copy_from_slice(&src[anchor..end]);
    op += literals;
    if let Some((offset, length)) = matched {
        out[op] = offset as u8;
        out[op + 1] = (offset >> 8) as u8;
        op += 2;
        let extra = length - MIN_MATCH;
        if extra >= 15 { value |= 15; op = put_length(out, op, extra - 15); } else { value |= extra as u8; }
    }
    out[token] = value;
    op
}

fn compress(src: &[u8], out: &mut [u8], table: &mut [u16; 1 << HASH_BITS]) -> usize {
    let len = src.len();
    let mut op = 0;
    let mut anchor = 0;
    if len > MF_LIMIT {
        table.fill(0);
        let match_limit = len - LAST_LITERALS;
        let last_start = len - MF_LIMIT;
        let mut ip = 0;
        let mut misses = 0usize;
        while ip <= last_start {
            let sequence = read32(src, ip);
            let slot = hash(sequence);
            let candidate = table[slot] as usize;
            table[slot] = ip as u16;
            // A cleared table yields candidate 0; equal bytes are still required.
            if candidate >= ip || read32(src, candidate) != sequence {
                misses += 1;
                ip += 1 + (misses >> 6);
                continue;
            }
            misses = 0;
            let mut length = MIN_MATCH;
            while ip + length + 8 <= match_limit {
                let difference = read64(src, candidate + length) ^ read64(src, ip + length);
                if difference != 0 { length += (difference.trailing_zeros() >> 3) as usize; break; }
                length += 8;
            }
            if ip + length + 8 > match_limit {
                while ip + length < match_limit && src[candidate + length] == src[ip + length] { length += 1; }
            }
            let mut start = ip;
            let mut from = candidate;
            while start > anchor && from > 0 && src[start - 1] == src[from - 1] { start -= 1; from -= 1; length += 1; }
            op = put_sequence(src, out, op, anchor, start, Some((start - from, length)));
            ip = start + length;
            anchor = ip;
            if ip >= 2 && ip <= last_start { table[hash(read32(src, ip - 2))] = (ip - 2) as u16; }
        }
    }
    put_sequence(src, out, op, anchor, len, None)
}

/// `src` and `out` are prefixes of the private buffers, so SLACK bytes follow each.
fn decompress(src: &[u8], out: &mut [u8]) -> bool {
    let (in_len, out_len) = (src.len(), out.len());
    let (mut ip, mut op) = (0usize, 0usize);
    loop {
        if ip >= in_len { return false; }
        let token = src[ip];
        ip += 1;
        let mut literals = (token >> 4) as usize;
        if literals == 15 {
            loop {
                if ip >= in_len { return false; }
                let more = src[ip];
                ip += 1;
                literals += more as usize;
                if more != 255 { break; }
                if literals > BOUND { return false; }
            }
        }
        if literals > in_len - ip || literals > out_len - op { return false; }
        unsafe { copy_chunks(src.as_ptr().add(ip), out.as_mut_ptr().add(op), literals, 16); }
        ip += literals;
        op += literals;
        if ip == in_len { return op == out_len; }
        if in_len - ip < 2 { return false; }
        let offset = src[ip] as usize | (src[ip + 1] as usize) << 8;
        ip += 2;
        if offset == 0 || offset > op { return false; }
        let mut length = (token & 15) as usize + MIN_MATCH;
        if token & 15 == 15 {
            loop {
                if ip >= in_len { return false; }
                let more = src[ip];
                ip += 1;
                length += more as usize;
                if more != 255 { break; }
                if length > BOUND { return false; }
            }
        }
        if length > out_len - op { return false; }
        if offset >= 16 {
            unsafe { copy_chunks(out.as_ptr().add(op - offset), out.as_mut_ptr().add(op), length, 16); }
        } else if offset >= 8 {
            unsafe { copy_chunks(out.as_ptr().add(op - offset), out.as_mut_ptr().add(op), length, 8); }
        } else if offset == 1 {
            let value = out[op - 1];
            out[op..op + length].fill(value);
        } else {
            // Short overlapping run: each byte may depend on one just written.
            for i in 0..length { out[op + i] = out[op + i - offset]; }
        }
        op += length;
    }
}

/// Compress INPUT[..len] into OUTPUT. Returns the packed size, or 0 for an
/// invalid length. The result never exceeds the output buffer.
#[no_mangle]
pub extern "C" fn pack(len: usize) -> usize {
    if len == 0 || len > BLOCK { return 0; }
    unsafe {
        let src = &*(&raw const INPUT);
        compress(&src[..len], &mut *(&raw mut OUTPUT), &mut *(&raw mut TABLE))
    }
}

/// Expand INPUT[..len] into OUTPUT[..expected]. Returns 1 only when the stream
/// is well formed and produces exactly `expected` bytes. Writes stay inside
/// the private output buffer; only OUTPUT[..expected] is meaningful.
#[no_mangle]
pub extern "C" fn unpack(len: usize, expected: usize) -> u32 {
    if len == 0 || len > BOUND || expected == 0 || expected > BLOCK { return 0; }
    unsafe {
        let src = &*(&raw const INPUT);
        let out = &mut *(&raw mut OUTPUT);
        decompress(&src[..len], &mut out[..expected]) as u32
    }
}
