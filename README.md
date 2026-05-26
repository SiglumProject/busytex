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

Future work:
- mf-nowin
- LuaMetaTex / LMTX (lua)
- tlmgr (perl, web requests)
- Biber (perl)
- mktexlsr, fmtutil, updmap (perl)

### License
MIT

### Usage

This is the **SiglumProject fork** of busytex ([SiglumProject/busytex](https://github.com/SiglumProject/busytex)),
used as the engine build for the `@siglum/engine` superproject
([SiglumProject/siglum](https://github.com/SiglumProject/siglum)), where it lives as
the `busytex` submodule. This repo produces the `busytex.wasm` engine and the
packaged `texlive-basic.data`; the superproject then splits that into the browser
bundles and serves them to the siglum runtime — see the superproject's
`docs/building.md` for the full packaging/distribution flow. This fork does not
publish prebuilt release artifacts; build them with `./build-wasm.sh` (below).

### Help needed
- single page HTML5 webapp: https://diveinto.html5doctor.com/offline.html
- refactor data packages subsystem in Emscripten: https://github.com/emscripten-core/emscripten/issues/14385
- LLVM's support for localizing global system in WASM object files: https://bugs.llvm.org/show_bug.cgi?id=51279
- upstream build sequence to TexLive: https://tug.org/pipermail/tlbuild/2021q1/004806.html
- various Emscripten improvements: https://github.com/emscripten-core/emscripten/issues/12093, https://github.com/emscripten-core/emscripten/issues/12256, https://github.com/emscripten-core/emscripten/issues/13466, https://github.com/emscripten-core/emscripten/issues/13219
- better error catching at all stages including WASM module initialization: https://github.com/emscripten-core/emscripten/issues/14777
- explore defining DLLPROC instead of redefining main functions
- complete investigation of feasibility of porting Biber to WASM/browser: https://github.com/plk/biber/issues/338, https://github.com/busytex/buildbiber
- review shipped TexLive packages in order to review useless files to save space
- review fonts / fontmaps / hyphenation shipped in TexLive packages
- optimizing binary size. any stripping possible?
- compile for x86_64-linux-glibc with clang (to match WASM toolchain)
- set up x86_64-linux binaries Github Actions test for WSLv1
- minimize build sequence in Makefile as much as possible
- test of WASM binaries using node.js, test preloading of data packages
- preloaded minimal single-file, single-engine versions (both WASM and x86_64-linux) with just TexLive Basic and latex-base
- explore creating virtual and LD_PRELOAD-based file systems: to avoid unpacking the ISO files or ZIP files (to be used even outside BusyTeX context); to embed Tex packages / Perl scripts in the native build 
- figure out how to embed static perl with Perl scripts (fmtutil.pl, updmap.pl, https://perldoc.perl.org/perlembed#Using-embedded-Perl-with-POSIX-locales, https://www.cs.ait.ac.th/~on/O/oreilly/perl/advprog/ch19_02.htm, https://www.foo.be/docs/tpj/issues/vol1_4/tpj0104-0009.html, http://www.kaiyuanba.cn/content/develop/Perl/Extending_And_Embedding_Perl.pdf)
- pre-parse ProvidesPackage meta for data packages

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
