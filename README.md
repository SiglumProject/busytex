# busytex — TeX Live 2026 → WebAssembly

This fork builds on [BusyTeX](https://github.com/busytex/busytex), which combines
TeX Live programs into one native binary and one WebAssembly module. The Siglum
build produces a multi-engine **WebAssembly** module via Emscripten and a static
**x86_64-linux** binary used as the build-time `install-tl` helper.

The binary includes `xetex`, `pdftex`, `luahbtex`, `bibtex8`, `xdvipdfmx`,
`makeindex`, and the kpathsea tools (`kpsewhich`, `kpsestat`, `kpseaccess`,
`kpsereadlink`).

## How this fork differs from upstream

- **TeX Live 2026 build.** The fork pins the 2026 compiler source and installs
  from the March 1, 2026 ISO after verifying its SHA-512. Upstream main at
  `2beec8b` lists the same ISO URL, but its active extraction rule uses the 2023
  ISO cache and its compiler source pin is TeX Live 2023.
  [Upstream Makefile](https://github.com/busytex/busytex/blob/2beec8babad2f00b0429b548f51afcbcd8a53eb4/Makefile#L6-L10)
- **June LaTeX formats.** The [package lock](texlive-packages.lock.json) pins
  13 packages from the June 5 snapshot. The build verifies their size and
  SHA-512, applies them to the March tree, and generates LaTeX2e `2026-06-01`
  formats for pdfLaTeX, XeLaTeX, and LuaHBLaTeX. It fixes the generation clock
  and uses the same combined WASM that will load the formats.
- **WASM heap and toolchain.** The combined module starts with a 64 MiB heap
  and can grow to 512 MiB. The upstream target at that revision sets 512 MiB.
  This fork uses a digest-pinned Emscripten 3.1.43 image. The heap figures are
  build settings. Actual browser memory use depends on the workload.
  [Upstream link settings](https://github.com/busytex/busytex/blob/2beec8babad2f00b0429b548f51afcbcd8a53eb4/Makefile#L205-L211)

[`@siglum/engine`](https://github.com/SiglumProject/siglum) pins this repo as
its `busytex` submodule. The fork produces the WASM, JavaScript glue, and
`texlive-basic.data`. Siglum splits that data into browser bundles and
handles on-demand loading, package fetching, and caching in its own runtime.
The editor exposes pdfLaTeX and XeLaTeX.

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

To reuse a package cache, set `BUSYTEX_TEXLIVE_ARCHIVES` to a directory inside
the checkout. Use a path relative to the checkout root with the container
wrapper. The default cache is `build/texlive-package-cache`.

Packaging verifies `build/texlive-basic-formats.sha256`, which records the
lock, WASM, JavaScript glue, and three format hashes. Run the formats step
again after replacing the WASM or refreshing the TeX Live installation.
The manual GitHub workflow can stage the matched WASM and TeX Live data as a
draft release.

To update the engine source or base ISO, edit the pins at the top of the
`Makefile` and use a fresh source and build tree. For a LaTeX format update,
revise the package lock and repeat the build and browser checks. [Siglum build
guide](https://github.com/SiglumProject/siglum/blob/main/docs/building.md) ·
[TeX Live upgrade guide](https://github.com/SiglumProject/siglum/blob/main/docs/upgrading-texlive.md)

## License

MIT
