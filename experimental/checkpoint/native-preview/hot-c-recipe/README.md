# Hot generated-C optimization control

Recompile only the generated pdfTeX engine and initialization units. Keep the
source patches, growable font allocation, libraries, link flags, exports and
pinned toolchain identical. Select `--optimization=-O3` or an explicit control.

Prepare with `python3 prepare.py --base-runtime /path/to/runtime --commands
/path/to/runtime/commands.json --optimization=-O3 --output /path/to/output`.
Mount the fork read-only at `/work`, output at `/out`, recipe at `/recipe`, and
run `python3 /recipe/build-inside.py` in the exact base toolchain image. No
network or relaxed undefined-symbol linking is needed. Optimize the result with
the same recorded Binaryen version/options as the control, separately recording
that command and artifact hashes.

This is a local experiment. Compare cold loading, full and resumed compiles,
code size, sampled browser RSS, offline behavior, and output equivalence before
choosing it. Faster optimization can enlarge code and is not automatically a
better default. Nothing in this recipe changes TeX source semantics knowingly.
