# LaTeX Format File Regeneration

This directory contains tools and instructions for regenerating LaTeX format files (.fmt) with an updated LaTeX kernel while maintaining compatibility with the busytex WASM binary.

## Background

Format files are binary memory dumps of TeX's state after loading the LaTeX kernel. They are version-specific - a format file generated with one version of pdfTeX cannot be used with a different version. The busytex WASM binary uses TeX Live 2023 pdfTeX, so format files must be generated with TL2023 tools even when using newer LaTeX kernel sources.

## When to Regenerate

Regenerate format files when:
- Modern LaTeX packages require features not in the current kernel (e.g., `\NewStructureName` added in 2023)
- You need to update from an older `\fmtversion` to a newer one
- The current error is "Undefined control sequence" for core LaTeX3 commands

## Prerequisites

- podman (or docker) installed
- Access to the TL2024 latex-base package files (or newer)
- The siglum-engine bundles directory structure

## Step 1: Download TL2024 LaTeX Base

```bash
cd /Users/adam/code/siglum-engine/busytex/fmt-regen

# Download from TeX Live historic archive
curl -L -o latex.tar.xz \
  "https://ftp.tu-chemnitz.de/pub/tug/historic/systems/texlive/2024/tlnet-final/archive/latex.tar.xz"

# Extract
mkdir -p latex-tl2024
tar -xf latex.tar.xz -C latex-tl2024
```

The key file is `latex-tl2024/tex/latex/base/latex.ltx` which contains `\fmtversion`.

## Step 2: Regenerate Format Files

Use the TL2023-historic container to regenerate formats. This ensures binary compatibility with the busytex WASM binary.

### pdflatex.fmt

```bash
podman run --rm \
  -v "$(pwd):/work" \
  texlive/texlive:TL2023-historic sh -c "
  cp -r /work/latex-tl2024/* /usr/local/texlive/2023/texmf-dist/tex/latex/base/
  mktexlsr /usr/local/texlive/2023/texmf-dist
  fmtutil-sys --byfmt pdflatex
  cp /usr/local/texlive/2023/texmf-var/web2c/pdftex/pdflatex.fmt /work/pdflatex-new.fmt
"
```

### xelatex.fmt

```bash
podman run --rm \
  -v "$(pwd):/work" \
  texlive/texlive:TL2023-historic sh -c "
  cp -r /work/latex-tl2024/* /usr/local/texlive/2023/texmf-dist/tex/latex/base/
  mktexlsr /usr/local/texlive/2023/texmf-dist
  fmtutil-sys --byfmt xelatex
  cp /usr/local/texlive/2023/texmf-var/web2c/xetex/xelatex.fmt /work/xelatex-new.fmt
"
```

### lualatex.fmt (luahblatex)

```bash
podman run --rm \
  -v "$(pwd):/work" \
  texlive/texlive:TL2023-historic sh -c "
  cp -r /work/latex-tl2024/* /usr/local/texlive/2023/texmf-dist/tex/latex/base/
  mktexlsr /usr/local/texlive/2023/texmf-dist
  fmtutil-sys --byfmt lualatex
  cp /usr/local/texlive/2023/texmf-var/web2c/luahbtex/lualatex.fmt /work/luahblatex-new.fmt
"
```

### latex.fmt (DVI mode)

```bash
podman run --rm \
  -v "$(pwd):/work" \
  texlive/texlive:TL2023-historic sh -c "
  cp -r /work/latex-tl2024/* /usr/local/texlive/2023/texmf-dist/tex/latex/base/
  mktexlsr /usr/local/texlive/2023/texmf-dist
  fmtutil-sys --byfmt latex
  cp /usr/local/texlive/2023/texmf-var/web2c/pdftex/latex.fmt /work/latex-new.fmt
"
```

## Step 3: Verify Format Compatibility

Check that the format header matches the old format. The header contains a version checksum that must match the pdfTeX binary:

```bash
# For pdflatex (TL2023 pdfTeX uses 0817 d6e4)
xxd pdflatex-new.fmt | head -5
# Look for: W2TX....pdftex....0817 d6e4
```

If the checksum differs, the format was built with an incompatible pdfTeX version.

## Step 4: Package into Bundles

Each bundle concatenates multiple format files with a JSON metadata file describing offsets.

### Extract base formats from old bundles

The plain TeX formats (pdfetex.fmt, pdftex.fmt, etex.fmt, xetex.fmt, luahbtex.fmt) don't need regeneration - only the LaTeX formats do.

```bash
BUNDLES=/Users/adam/code/siglum-engine/packages/bundles

# Extract pdfetex.fmt and pdftex.fmt from fmt-pdflatex bundle
gunzip -c $BUNDLES/fmt-pdflatex.data.gz > fmt-pdflatex-old.data
dd if=fmt-pdflatex-old.data of=pdfetex.fmt bs=1 count=127495
dd if=fmt-pdflatex-old.data of=pdftex.fmt bs=1 skip=6605059 count=127504

# Extract xetex.fmt from fmt-xelatex bundle
gunzip -c $BUNDLES/fmt-xelatex.data.gz > fmt-xelatex-old.data
dd if=fmt-xelatex-old.data of=xetex.fmt bs=1 skip=8714726 count=2290522

# Extract luahbtex.fmt from fmt-lualatex bundle
gunzip -c $BUNDLES/fmt-lualatex.data.gz > fmt-lualatex-old.data
dd if=fmt-lualatex-old.data of=luahbtex.fmt bs=1 skip=11875783 count=1212397

# Extract etex.fmt from fmt-latex bundle
gunzip -c $BUNDLES/fmt-latex.data.gz > fmt-latex-old.data
dd if=fmt-latex-old.data of=etex.fmt bs=1 count=127325
```

### Create new bundles

```bash
# fmt-pdflatex: pdfetex.fmt + pdflatex.fmt + pdftex.fmt
cat pdfetex.fmt pdflatex-new.fmt pdftex.fmt > fmt-pdflatex-new.data
gzip -c fmt-pdflatex-new.data > $BUNDLES/fmt-pdflatex.data.gz

# fmt-xelatex: xelatex.fmt + xetex.fmt
cat xelatex-new.fmt xetex.fmt > fmt-xelatex-new.data
gzip -c fmt-xelatex-new.data > $BUNDLES/fmt-xelatex.data.gz

# fmt-lualatex: luahblatex.fmt + luahbtex.fmt
cat luahblatex-new.fmt luahbtex.fmt > fmt-lualatex-new.data
gzip -c fmt-lualatex-new.data > $BUNDLES/fmt-lualatex.data.gz

# fmt-latex: etex.fmt + latex.fmt
cat etex.fmt latex-new.fmt > fmt-latex-new.data
gzip -c fmt-latex-new.data > $BUNDLES/fmt-latex.data.gz
```

### Update metadata JSON files

Update each `.meta.json` file with new byte offsets. Calculate offsets as:
- First file: start=0, end=filesize
- Second file: start=previous_end, end=start+filesize
- etc.

Example for fmt-pdflatex.meta.json:
```json
{
  "name": "fmt-pdflatex",
  "files": [
    {"path": "/texlive/texmf-dist/texmf-var/web2c/pdftex", "name": "pdfetex.fmt", "start": 0, "end": 127495},
    {"path": "/texlive/texmf-dist/texmf-var/web2c/pdftex", "name": "pdflatex.fmt", "start": 127495, "end": 8364167},
    {"path": "/texlive/texmf-dist/texmf-var/web2c/pdftex", "name": "pdftex.fmt", "start": 8364167, "end": 8491671}
  ],
  "totalSize": 8491671
}
```

## Step 5: Deploy

Upload updated bundles to R2 using the cloudflare upload script, or deploy via the normal siglum-engine deployment process.

## File Locations

- Source bundles: `/Users/adam/code/siglum-engine/packages/bundles/`
- Working directory: `/Users/adam/code/siglum-engine/busytex/fmt-regen/`
- TL2024 latex sources: `./latex-tl2024/tex/latex/base/`

## Notes

- The `WARNING: image platform (linux/amd64) does not match...` message on Apple Silicon is expected and can be ignored - the container runs via emulation.
- Format files grow larger with newer LaTeX kernels due to additional features.
- The plain TeX formats (pdftex.fmt, xetex.fmt, etc.) rarely need updating - they don't include LaTeX code.
