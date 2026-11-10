# Lossless packed checkpoint storage

Local experimental helper. It changes how a retained checkpoint is stored, not
what is stored: every restore reproduces the captured bytes exactly or fails.

`kernel.rs` is a small LZ4 block-format codec in `no_std` Rust. Unlike the
scanner and comparison kernels it imports nothing and owns a private memory of
fixed size (two static 64 KiB block buffers, a 4,096-entry match table and a
16 KiB stack). It has no allocator and never grows. The host copies one block
in, calls `pack` or `unpack`, and copies the result out, so the codec never
reads or writes compiler memory and cannot cause linear-memory growth there.

`python3 build.py` rebuilds `pack.wasm` with the installed Rust wasm32 target,
embeds its bytes and records the exact hash in `artifacts.json`. Original
build: rustc 1.92.0. The module uses bulk-memory operations.

## Storage

Heap snapshots keep the existing policy: nonzero 16 KiB pages only, with exact
repeated-page sharing where it is enabled. Each unique page is then packed on
its own, so a page can later be restored without touching its neighbours.
Mutable file copies of 4 KiB or more are packed in 64 KiB blocks. A block or
page that does not shrink is kept verbatim. Packed bytes live in 2 MiB
host-owned chunks, avoiding a worst-case contiguous allocation during capture.

Retained bytes count packed payload, placement tables, page indices and the
bitmap. The configured checkpoint cap applies to that total, unchanged.

## Failure handling

`unpack` validates every literal and match against both buffers and the
expected block size. A truncated, altered or wrong-length stream returns
failure; the host throws before copying anything to its target. A failed heap
restore releases the snapshot and marks the engine instance unusable, which
the driver already answers with a full build on a fresh instance.

Unit tests cover exact round trips across size classes, verbatim storage of
incompressible data, truncation at every seventh byte, 2,000 random damage
trials with guard bands, repeated restore after memory growth, scratch
transfer to a forward capture, and packed MEMFS file restore.

## Measured so far

Saved pdfTeX heaps (Node, 16 KiB pages): 2.2–2.3x on unique nonzero pages,
exact reconstruction. Real browser run, 1,000-page XeLaTeX book: the
last-chapter checkpoint that requested 59.5 MB verbatim is retained in
18.7 MiB, and the first-chapter checkpoint drops from 31.7 MB to 13.2 MiB.
Restore of the packed late checkpoint takes roughly 40–50 ms against 8–20 ms
verbatim; this is the cost paid for the storage reduction.

Do not infer results for arbitrary documents from these fixtures.
