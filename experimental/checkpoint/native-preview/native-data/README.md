# External native ICU data

This optional recipe keeps ICU's complete data package outside the combined
WebAssembly binary. It links ICU's matching stubdata archive and configures file
access through `/icu`. No locale or character repertoire is removed. The default
embedded-data build remains the compatibility control.

Use the same pinned source, generated native objects and Emscripten toolchain as
the packed-hash build. Build the matching ICU stubdata target first. Then, inside
that build environment:

```sh
python3 relink.py --commands /path/to/commands-executed.json \
  --objects /path/to/packed-native-objects \
  --icu-common /path/to/icu/source/common --output /path/to/output
python3 extract.py --data /path/to/exact-built-icu-package.dat \
  --output /path/to/output
```

The relinker preserves the recorded flags and native objects. It replaces exactly
one data archive, exports the initializer and diagnostic probes, and records its
command, compiler version and artifact hashes. It fails if the expected archive
layout changes. `extract.py` indexes and hashes every resource directly from that
build's little-endian CmnD package; it does not download a replacement package.

The output includes a byte-identical data pack, a resource range index and a native
resource descriptor. Pair these with the compatible Siglum SDK/worker loader and
include the ICU license from its source tree. Do not replace a public runtime
alias used by older clients without a compatible runtime-selection/fallback plan.
Keep the embedded combined build available at its immutable URL.

The optional probe checks normalization, locale-sensitive casing, a legacy
converter and dictionary line-breaking. It does not establish full language/font
coverage. Validate real XeLaTeX PDF text, rasters, SyncTeX, native-font math,
Unicode identifiers, fresh offline workers, and desktop/mobile browsers. Compare
actual process memory separately from logical WASM size.

ICU already supports file-backed data. See its [data documentation](https://unicode-org.github.io/icu/userguide/icu_data/).
The work here is the immutable browser resource index, lazy filesystem integration
and verified persistent reuse; it is not a claim of inventing ICU demand loading.

For a production-style memory experiment, pass `--runtime-assertions 0`. This
removes Emscripten JavaScript diagnostic getters that can retain the first
modularized heap through `globalThis` on the pinned toolchain. It keeps explicit
`STACK_OVERFLOW_CHECK=2`; native TeX object files and assertions are unchanged.
The default remains the assertion-enabled diagnostic control. Test invalid
input recovery, module retirement and full output equivalence before selecting
this variant. See Emscripten issue
[#22588](https://github.com/emscripten-core/emscripten/issues/22588).
