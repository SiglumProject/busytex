# Growable font-info allocation experiment

pdfTeX's configured `font_mem_size` remains the upper bound. The font-info table
starts with one million metric words and grows geometrically as font loading
requires. Loading a format retains its existing minimum-capacity behavior.
All generated allocation checks are covered, including font loading, fontdimen
extension and expansion. The shared helper also supports XeTeX.
The generated code indexes this table through one global pointer. Its grow path
rebinds that pointer before reading the next metric. The ordinary full-allocation
control calls `_siglum_font_memory_configure(0)` before starting TeX. A positive
value selects the initial capacity. Configuration is sealed when initialization
begins; the configured upper limit is still read by TeX normally.

Prepare with an existing checkpoint/native-input runtime, its strict link
commands, and the generated-object compiler commands from the base recipe:

```sh
python3 prepare.py --base-runtime /path/to/runtime \
  --base-commands /path/to/runtime/build-commands.json \
  --generated-commands /path/to/generated/commands.json \
  --output /path/to/output
```

Mount the fork at `/work`, prepared output at `/out`, and this recipe at
`/recipe`. Run `python3 /recipe/build-inside.py` in the exact pinned toolchain
used by the base objects. Source patches, commands, and hashes accompany output.

This is a local prototype. Validate growth past the initial capacity, repeated
checkpoint restoration across a growth, full-build output equivalence, the
pinned document collection, offline behavior, and measured browser RSS before
considering it for a release. Logical WASM memory size alone is not physical RSS.

Prepare the matching XeTeX translation units without changing the source tree:

```sh
python3 prepare-xetex.py --generated /path/to/web2c/generated \
  --output /path/to/prepared-xetex
```

Compile these with the original XeTeX flags and strict-link command. The XeTeX
exports use the `_siglum_xetex_font_memory_` prefix. The shared source generator
keeps allocation policy identical across the two engines; each has independent
native state. This recipe does not activate experimental runtimes in production.
