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
them to the Siglum runtime. The fork's manual GitHub workflow can build and stage
the matched WASM and TeX Live data as a draft release.

## Building

The build is driven by `./build-wasm.sh`, which runs each stage in a container. The
pipeline (`wasm`/`all`) builds the native helper and the WASM binary inside
`emscripten/emsdk:3.1.43`; the standalone `native` command uses `ubuntu:22.04`.

You need Podman, Bun for the Siglum bundle split, and about 10 GB of free space
for the TeX Live ISO and build inputs. The Makefile pins the TeX Live engine
source and verifies the March 2026 ISO with SHA-512 while extracting it.

```shell
./build-wasm.sh all      # full pipeline: wasm → texlive → formats → package → bundles
```

Individual stages (`./build-wasm.sh` with no args lists them all):

```shell
./build-wasm.sh wasm     # native + WASM binaries → build/wasm/busytex.{wasm,js}
./build-wasm.sh texlive  # install TeX Live packages via install-tl
./build-wasm.sh formats  # apply pinned June packages and generate .fmt files
./build-wasm.sh package  # create build/wasm/texlive-basic.data
./build-wasm.sh bundles  # split into browser bundles (in the superproject)
```

The engine uses TeX Live 2026 with the LaTeX2e 2026-06-01 format. The
[package lock](texlive-packages.lock.json) records the 13 packages from the
June 5 TeX Live snapshot that update the March ISO tree. The formats step
checks each archive’s size and SHA-512 before applying the overlay. To reuse
a cache, set `BUSYTEX_TEXLIVE_ARCHIVES` to a directory inside the checkout,
relative to the checkout root when using the container wrapper. The default
cache is `build/texlive-package-cache`.

The generator uses the combined BusyTeX WASM to create pdfLaTeX, XeLaTeX and
LuaHBLaTeX formats. It fixes the generation clock and checks the LaTeX version
in each format dump. Packaging requires `build/texlive-basic-formats.sha256`,
which records the lock, WASM, JavaScript glue and three format hashes.
Run the formats step again after replacing the WASM or refreshing the
TeX Live installation.

To update the engine source or base ISO, edit the pins at the top of the
`Makefile` and use a fresh source and build tree. For a LaTeX format update,
revise the package lock and repeat the build and browser checks. [Siglum build
guide](https://github.com/SiglumProject/siglum/blob/main/docs/building.md) ·
[TeX Live upgrade guide](https://github.com/SiglumProject/siglum/blob/main/docs/upgrading-texlive.md)

## Upstream

Forked from [busytex/busytex](https://github.com/busytex/busytex) — see upstream for
the general roadmap and contribution ideas.

## License

MIT
