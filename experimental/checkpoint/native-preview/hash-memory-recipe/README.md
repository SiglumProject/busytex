# Packed XeTeX hash storage experiment

XeTeX identifiers and format files use logical table indices. The generated
allocation also reserves the large unused intervals between real entries.
This recipe derives the live intervals from the pinned format loader and packs
only physical storage. Unicode character tables, control-sequence identifiers,
configured hash capacity and format serialization remain unchanged.

```sh
python3 prepare.py --base-runtime /path/to/generated-xetex-runtime \
  --output /path/to/prepared-runtime
```

The input must contain the matching `xetex0.c`, `xetexini.c` and their helper
sources. Compile both prepared translation units with the original generated
XeTeX flags and relink with the exact original native objects/toolchain. Export
`_siglum_xetex_table_profile` for the optional read-only diagnostics. The output
records source hashes, patches and extracted format-layout boundaries.

Every generated `hash[index]` becomes a checked C lvalue. Initialization skips
unused gaps, and format I/O still sees contiguous storage for each serialized
interval. An unexpected access into a gap aborts instead of aliasing a real entry.
No document, font or package names participate in this optimization.

This remains experimental. Validate source-equivalent full builds, Unicode names,
group restoration, many extra definitions, native-font math, format loading,
repeated edits, the large-book workload, isolated tools, and fresh offline desktop
and mobile browsers before selecting a runtime. Compare process RSS separately
from logical WASM allocation and retain the ordinary full-build control.
