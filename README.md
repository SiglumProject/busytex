# busytex — TeX Live 2026 → WebAssembly

SiglumProject fork of [busytex](https://github.com/busytex/busytex). Compiles TeX
Live 2026 into a single multi-engine **WebAssembly** module (via Emscripten), plus a
static **x86_64-linux** binary (via glibc) used as the build-time `install-tl` helper.

Engines compiled into the binary: `xetex`, `pdftex`, `luahbtex`, `bibtex8`,
`xdvipdfmx`, `makeindex`, and the kpathsea tools (`kpsewhich`, `kpsestat`,
`kpseaccess`, `kpsereadlink`).

This repo is the engine build for the
[`@siglum/engine`](https://github.com/SiglumProject/siglum) superproject, where it
lives as the `busytex` submodule. It produces `busytex.wasm` and the packaged
`texlive-basic.data`; the superproject splits those into browser bundles and serves
them to the siglum runtime (see the superproject's `docs/building.md`). No prebuilt
release artifacts are published here — build them with `./build-wasm.sh`.

## Building

The build is driven by `./build-wasm.sh`, which runs each stage in a container. The
pipeline (`wasm`/`all`) builds the native helper and the WASM binary inside
`emscripten/emsdk:3.1.43`; the standalone `native` command uses `ubuntu:22.04`.

**Prerequisites:** Podman, Bun (for bundle splitting), and ~10 GB free disk for the
TeX Live ISO.

```shell
./build-wasm.sh all      # full pipeline: wasm → texlive → formats → package → bundles
```

Individual stages (`./build-wasm.sh` with no args lists them all):

```shell
./build-wasm.sh wasm     # native + WASM binaries → build/wasm/busytex.{wasm,js}
./build-wasm.sh texlive  # install TeX Live packages via install-tl
./build-wasm.sh formats  # regenerate .fmt files with the WASM binary
./build-wasm.sh package  # create build/wasm/texlive-basic.data
./build-wasm.sh bundles  # split into browser bundles (in the superproject)
```

To bump the TeX Live version, edit the URLs at the top of the `Makefile`. The full
procedure is documented in the superproject's `docs/building.md` and
`docs/upgrading-texlive.md`.

## Upstream

Forked from [busytex/busytex](https://github.com/busytex/busytex) — see upstream for
the general roadmap and contribution ideas.

## License

MIT
