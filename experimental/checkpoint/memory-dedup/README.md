# Exact repeated-page checkpoint storage

Local experimental helper. This does not replace TeX or approximate compiler
state. A nonzero-page snapshot may store identical pages once and restore them
to every original address. A sampled fingerprint selects at most eight candidate
pages; full Rust byte equality is required before sharing storage. Collisions
always preserve unequal pages verbatim. Zero pages retain the existing scanner
policy. Native memory growth is scanned and zeroed/restored as before.

The scalar and SIMD128 kernels import the exact compiler memory, use no stack,
allocate no private memory, initialize no data, and only read engine bytes. SIMD
selection uses the existing feature probe. `python3 build.py` rebuilds both
variants with the installed Rust wasm32 target and embeds their bytes. The
artifacts file records exact hashes. Original build: rustc 1.92.0.

The SDK loader verifies imports, absence of start/data initialization and a zero
linear-memory stack pointer. Unit tests verify full restore equality, deliberate
fingerprint collisions, read-only kernels, bounds, memory growth and sole-snapshot
ownership transfer. Xe-only activation leaves the existing pdfTeX snapshot policy
unchanged. Retained bytes include payload, page indices, per-page payload offsets
and bitmap. Temporary candidate tables are released after capture.

This remains under browser/native/output/offline/RSS validation. Do not infer a
speed or memory benefit for arbitrary documents from unit tests alone.
