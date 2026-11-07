# Experimental XeTeX continuation

A cooperative `maincontrol` boundary, not a serializable format or a new engine.
The host preserves this exact native instance: heap, stack, mutable MEMFS and
streams. XeTeX UFILE decoding state is retained in the heap. Source filename
conversion uses the engine UTF-16 string pool converter. Source shapes and entry
branches are checked before patching; generated engine offsets are not hardcoded.

Run `python3 prepare.py --base PACKED_XE_OUTPUT --output OUTPUT` on generated Xe
sources with the packed hash/growable font changes already applied. The build
recipe expects the configured native fork at `/work`, common objects at `/base`,
packed objects at `/packed`, the validated demand-ICU link recipe and object at
`/control`, and writable prepared sources at `/out`. Mount these read-only except
`/out`. Run `python3 /recipe/build-inside.py` in the pinned Emscripten image used
by the base build. The recipe recompiles the two patched Xe sources, preserves
the existing link command and explicit stack checks, and adds checkpoint/stack
exports. It records commands, toolchain and source/artifact hashes.

Boundary discovery has its own instrumented control entry. Ordinary continuation
uses a token loop without per-token checkpoint polling. The generated-source
patch verifies the ordinary loop body against its original input.

The SDK must defer xdvipdfmx until native continuation completes. A paused Xe
pass produces an incomplete XDV stream. Reuse needs unchanged consumed source,
dependencies, runtime and auxiliary state; new resource demand and unsafe edits
must use the normal full-build resolver. This saves the source prefix only; it
does not skip an arbitrary unchanged suffix.

The local desktop 1,000-page book test compares full text, selected page rasters,
normalized SyncTeX, references, dependency changes and pagination, including fresh
offline reload. Desktop and mobile WebKit offline checks passed. The paired desktop study shows
faster middle-book edits with an additional retained-snapshot memory cost; it is
not a universal lowest-memory or fastest-engine claim. A retention-policy rejection
must finish valid native work rather than restarting it. The host retains at most
one bounded snapshot; a larger candidate can be discarded without discarding its
completed replay.

The current pinned TeX configuration permits fifteen simultaneous input files.
The prototype serializer has fixed input bookkeeping capacity; custom configurations
raising the engine limit need an explicit capacity audit before enabling reuse.
This recipe is uncommitted, unpublished and not enabled in a production build.
