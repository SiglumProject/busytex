#![no_std]
#[panic_handler]
fn panic(_: &core::panic::PanicInfo<'_>) -> ! { core::arch::wasm32::unreachable() }
fn valid(start: usize, len: usize) -> bool {
    let size = core::arch::wasm32::memory_size(0) * 65536;
    start <= size && len <= size - start
}
#[no_mangle]
pub extern "C" fn page_fingerprint(start: usize, len: usize) -> u32 {
    if !valid(start, len) || start % 4 != 0 { return 0; }
    let mut hash = 2166136261u32;
    if len < 4 {
        for i in 0..len { hash = (hash ^ unsafe { core::ptr::read_volatile((start+i) as *const u8) } as u32).wrapping_mul(16777619); }
    } else {
        for i in 0..16 {
            let at = start + ((i * (len - 4) / 15) & !3);
            hash = (hash ^ unsafe { core::ptr::read_volatile(at as *const u32) }).wrapping_mul(16777619);
        }
    }
    hash
}
#[no_mangle]
pub extern "C" fn equal_pages(a: usize, b: usize, len: usize) -> u32 {
    if !valid(a,len) || !valid(b,len) { return 0; }
    let mut i = 0;
    #[cfg(feature="simd")]
    unsafe {
        use core::arch::wasm32::*;
        while i + 16 <= len {
            if !i8x16_all_true(i8x16_eq(v128_load((a+i) as *const v128),v128_load((b+i) as *const v128))) { return 0; }
            i += 16;
        }
    }
    while i < len {
        if unsafe { core::ptr::read_volatile((a+i) as *const u8) != core::ptr::read_volatile((b+i) as *const u8) } { return 0; }
        i += 1;
    }
    1
}
