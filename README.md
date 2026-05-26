# TeX Live 2026 compiled into a single multi-engine binary — WebAssembly (via Emscripten) and static x86_64-linux (via glibc)

Compiles into a **WebAssembly module** (via Emscripten) and a **static x86_64-linux binary** (via glibc, used as the build-time `install-tl` helper):
- xetex
- pdftex
- luahbtex
- bibtex8
- xdvipdfmx
- kpsewhich, kpsestat, kpseaccess, kpsereadlink
- makeindex

Supported architecture targets:
- x86_64-linux
- WASM32

### License
MIT

### Usage

This is the **SiglumProject fork** of [busytex](https://github.com/busytex/busytex)
(this repo: [SiglumProject/busytex](https://github.com/SiglumProject/busytex)),
used as the engine build for the `@siglum/engine` superproject
([SiglumProject/siglum](https://github.com/SiglumProject/siglum)), where it lives as
the `busytex` submodule. This repo produces the `busytex.wasm` engine and the
packaged `texlive-basic.data`; the superproject then splits that into the browser
bundles and serves them to the siglum runtime — see the superproject's
`docs/building.md` for the full packaging/distribution flow. This fork does not
publish prebuilt release artifacts; build them with `./build-wasm.sh` (below).

For the general busytex roadmap and contribution ideas, see the upstream project:
https://github.com/busytex/busytex

### Building from source

The build is driven by `./build-wasm.sh`, which runs each stage in a container.
The pipeline (`wasm`/`all`) builds both the native helper and the WASM binary inside
`emscripten/emsdk:3.1.43`; the standalone `native` command uses `ubuntu:22.04`.

Prerequisites: **Podman**, **Bun** (for bundle splitting), and ~10 GB free disk for
the TeX Live ISO.

```shell
./build-wasm.sh all      # full pipeline: wasm → texlive → formats → package → bundles
```

Or run a single stage (`./build-wasm.sh` with no args lists them all):

```shell
./build-wasm.sh wasm     # build native + WASM binaries (build/wasm/busytex.{wasm,js})
./build-wasm.sh texlive  # install TeX Live packages via install-tl
./build-wasm.sh formats  # regenerate .fmt files with the WASM binary
./build-wasm.sh package  # create build/wasm/texlive-basic.data
./build-wasm.sh bundles  # split into browser bundles (siglum superproject)
```

To bump the TeX Live version, update the URLs at the top of the `Makefile`. The full
procedure, including downstream packaging and deployment, is documented in the siglum
superproject's `docs/building.md` and `docs/upgrading-texlive.md`.

### References
- [pdftex.js](https://github.com/dmonad/pdftex.js)
- [xetex.js](https://github.com/lyze/xetex-js)
- [texlive.js](https://github.com/manuels/texlive.js/)
- [latexjs](https://github.com/latexjs/latexjs)
- [dvi2html](https://github.com/kisonecat/dvi2html), [web2js](https://github.com/kisonecat/web2js)
- [SwiftLaTeX](https://github.com/SwiftLaTeX/SwiftLaTeX)
- [JavascriptSubtitlesOctopus](https://github.com/Dador/JavascriptSubtitlesOctopus)
- [js-sha1](https://raw.githubusercontent.com/emn178/js-sha1)
- [BLFS](http://www.linuxfromscratch.org/blfs/view/svn/pst/texlive.html)
- https://github.com/schlamar/latexmk.py/pull/11
- https://github.com/schlamar/latexmk.py
- https://github.com/JanKanis/latexmk.py
- https://mg.readthedocs.io/latexmk.html
- https://ctan.org/tex-archive/support/latexmk
- https://metacpan.org/release/TSCHWAND/TeX-AutoTeX-v0.906.0/view/lib/TeX/AutoTeX/File.pm
