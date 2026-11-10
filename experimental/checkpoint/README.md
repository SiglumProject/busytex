# Experimental native checkpoints

Local opt-in prototype. The normal compiler build remains unchanged. One
same-instance snapshot preserves TeX linear memory, native globals, MEMFS files
and stream positions at a guarded input boundary. The host must validate source
prefixes, consumed dependencies and auxiliary state before reuse. Native page
packets are a separate provisional ABI; the regular editor currently returns a
complete PDF and does not claim arbitrary realtime page patching.

Build the base prototype with `bash experimental/checkpoint/build.sh`. Build the
current page/font handoff variant with
`bash experimental/checkpoint/native-preview/page-packet-recipe/build.sh`.
The existing generated TeX sources and object libraries must have been built
with the pinned Emscripten toolchain. The scripts use that cached Docker image,
no network, source-only patching in a separate output directory and strict
linking. They derive generated engine offsets from source rather than guessing.

`siglum_configure_default_map(path)` optionally selects the initial map before
startup and rejects later changes. A private host-generated map can omit exact
duplicate default rows while original maps remain intact for explicit TeX map
operations. The host must protect its private file and use the ordinary runtime
if a document needs to write protected assets.

The tested editor uses bounded Rust SIMD compact snapshots, the existing SDK
resolver and a full-build fallback. Native correctness and browser/offline
artifacts are recorded locally under the Siglum test workspace checkpoint
prototype. These sources are experimental and have not been released.

## pdfTeX and XeTeX integration

The split pdfTeX runtime and the combined XeTeX runtime use the same guarded host
checkpoint system. XeTeX continuation and XDV conversion are separate phases;
conversion runs only after a native pass completes. `combined` names the binary,
not a request to bypass checkpointing.

The [XeTeX recipe](xetex-recipe/README.md) includes packed tables, growable font
storage and native continuation. The [snapshot helper](memory-dedup/README.md)
provides exact repeated-page comparison for the bounded host snapshot. The
[ICU recipe](native-preview/native-data/README.md) retains the complete matching
resource package and loads data on demand. Matching engine, host SDK and immutable
resource assets are required; unsupported native capabilities use a full build
with an explicit reason. The ordinary embedded-data build remains available.


## Rebuild from fresh objects

Use the pinned Emscripten image from `build-wasm.sh` on a Linux filesystem. Start
with an empty build tree, fetch the pinned source archives, then run `make native`,
`make wasm` and `make wasm-pdftex`. Run
`python3 experimental/checkpoint/build-performance.py --work "$PWD" --output "$PWD/build/performance"`
in the same container. The output directory must be empty and `/out` must be free
for the recipe's temporary stage alias. The script records commands, toolchain,
source hashes and output hashes. It does not read old experiment directories.

The manual **Build performance compiler** workflow performs that sequence without
publishing a release or deploying anything. Its compiler outputs still need
matching generated formats, package indexes, SDK integration and browser tests
before use as a complete runtime. macOS shared mounts may reject archived Unix
permissions; use a fresh Linux volume for the source and build directories.
