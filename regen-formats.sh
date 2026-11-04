#!/bin/bash
# Apply the locked LaTeX package overlay and generate matching WASM formats.
#
# Run inside the emscripten container after install-tl has installed packages:
#   podman run --rm -v "$(pwd):/work" -w /work emscripten/emsdk:3.1.43 bash regen-formats.sh

set -e

TEXLIVE_DIR="build/texlive-basic"
WASM_DIR="build/wasm"
FMT_DIR="${TEXLIVE_DIR}/texmf-dist/texmf-var/web2c"
LOCK_FILE="texlive-packages.lock.json"
CHECKSUMS="build/texlive-basic-formats.sha256"
formats=(pdftex/pdflatex.fmt xetex/xelatex.fmt luahbtex/luahblatex.fmt)

test -s "${WASM_DIR}/busytex.wasm"
test -s "${WASM_DIR}/busytex.js"
settings=$(python3 -c 'import json, sys; lock = json.load(open(sys.argv[1])); print(lock["sourceDateEpoch"], lock["formatVersion"])' "$LOCK_FILE")
read -r SOURCE_DATE_EPOCH LATEX_FORMAT_VERSION <<< "$settings"
export SOURCE_DATE_EPOCH LATEX_FORMAT_VERSION TZ=UTC

# Keep the packaging guard invalid if overlay or generation fails.
rm -f "$CHECKSUMS"
python3 apply-texlive-overlay.py "${TEXLIVE_DIR}/texmf-dist"

echo "=== Regenerating format files with WASM binary ==="
echo "Node version: $(node --version)"

# Generate into a temp dir first and only swap into place once every required
# format has been produced. This prevents a failed regen from leaving FMT_DIR
# with zero (or stale/native) .fmt files while the build still reports success
# — which would surface at runtime as "could not undump format".
FMT_TMP="$(mktemp -d "${PWD}/build/.busytex-formats.XXXXXX")"
trap 'rm -rf "$FMT_TMP"' EXIT

# Create a Node.js script (CommonJS, no top-level await)
# The superproject declares type=module; preserve the glue's CommonJS mode.
cp "${WASM_DIR}/busytex.js" "${FMT_TMP}/busytex.cjs"
cat > "${FMT_TMP}/gen-format.cjs" << 'SCRIPT'
'use strict';
const fs = require('fs');
const path = require('path');

const args = process.argv.slice(2);
const engine = args[0];
const texliveDir = args[1];
const wasmDir = args[2];
const fmtOutputDir = args[3];

const engineMap = {
  'pdflatex':   { program: 'pdflatex',  iniArgs: ['-ini', '-halt-on-error', '-interaction=nonstopmode', '-jobname=pdflatex', '*pdflatex.ini'] },
  'xelatex':    { program: 'xelatex',   iniArgs: ['-ini', '-halt-on-error', '-interaction=nonstopmode', '-jobname=xelatex', '*xelatex.ini'] },
  'luahblatex': { program: 'luahblatex', iniArgs: ['-ini', '-halt-on-error', '-interaction=nonstopmode', '-jobname=lualatex', '*lualatex.ini'] },
};

const config = engineMap[engine];
if (!config) {
  console.error('Unknown engine: ' + engine);
  process.exit(1);
}

function collectFiles(dir, prefix) {
  var result = {};
  var entries = fs.readdirSync(dir, { withFileTypes: true });
  for (var i = 0; i < entries.length; i++) {
    var entry = entries[i];
    var fullPath = path.join(dir, entry.name);
    var vfsPath = prefix ? prefix + '/' + entry.name : entry.name;
    if (entry.isDirectory()) {
      Object.assign(result, collectFiles(fullPath, vfsPath));
    } else if (entry.isFile()) {
      result[vfsPath] = fs.readFileSync(fullPath);
    }
  }
  return result;
}

async function main() {
  console.log('Generating format: ' + engine);

  var wasmBinary = fs.readFileSync(path.join(wasmDir, 'busytex.wasm'));

  console.log('Collecting texmf-dist files...');
  var texmfFiles = collectFiles(path.join(texliveDir, 'texmf-dist'), '/texlive/texmf-dist');
  console.log('Collected ' + Object.keys(texmfFiles).length + ' files');

  // Pin Emscripten's wall clock for format generation, including Lua's hash seed.
  const epochSeconds = Number(process.env.SOURCE_DATE_EPOCH);
  if (!Number.isSafeInteger(epochSeconds) || epochSeconds <= 0) throw new Error('Expected SOURCE_DATE_EPOCH');
  Date.now = () => epochSeconds * 1000;
  var busytexFactory = require('./busytex.cjs');

  const expectedBanner = 'LaTeX2e <' + process.env.LATEX_FORMAT_VERSION + '>';
  let foundVersion = false;
  var Module = await busytexFactory({
    wasmBinary: wasmBinary,
    noInitialRun: true,
    thisProgram: '/texlive/texmf-dist/bin/busytex',
    arguments: [config.program].concat(config.iniArgs),
    preRun: [function(mod) {
      // Create a dummy binary so kpathsea can lstat it for $SELFAUTODIR
      mod.FS.mkdirTree('/texlive/texmf-dist/bin');
      mod.FS.writeFile('/texlive/texmf-dist/bin/busytex', '');
      var paths = Object.keys(texmfFiles);
      for (var i = 0; i < paths.length; i++) {
        var p = paths[i];
        var dir = path.dirname(p);
        try { mod.FS.mkdirTree(dir); } catch(e) {}
        mod.FS.writeFile(p, texmfFiles[p]);
      }
      mod.ENV['TEXMFCNF'] = '/texlive/texmf-dist/web2c';
      mod.ENV['TZ'] = 'UTC';
      mod.ENV['SOURCE_DATE_EPOCH'] = process.env.SOURCE_DATE_EPOCH;
      mod.ENV['FORCE_SOURCE_DATE'] = '1';
    }],
    print: function(text) {
      if (text.startsWith(expectedBanner)) foundVersion = true;
      console.log('[TeX] ' + text);
    },
    printErr: function(text) { console.error('[TeX ERR] ' + text); }
  });

  await Module.ready;

  try {
    const status = Module.callMain([config.program].concat(config.iniArgs));
    if (status !== 0) throw new Error('Engine exited with status ' + status);
  } catch (e) {
    if (e.name !== 'ExitStatus' || e.status !== 0) throw e;
  }

  if (!foundVersion) throw new Error('Expected ' + expectedBanner + ' from ' + engine);
  var fmtName = (engine === 'luahblatex' ? 'lualatex' : engine) + '.fmt';
  try {
    var fmtData = Module.FS.readFile(fmtName);
    fs.mkdirSync(fmtOutputDir, { recursive: true });
    var outputPath = path.join(fmtOutputDir, fmtName);
    fs.writeFileSync(outputPath, fmtData);
    console.log('Written: ' + outputPath + ' (' + fmtData.length + ' bytes)');
  } catch (e) {
    console.error('Failed to extract ' + fmtName + ': ' + e.message);
    try {
      console.log('CWD files:', Module.FS.readdir('.'));
    } catch(e2) {}
    process.exit(1);
  }
}

main().catch(function(e) { console.error(e); process.exit(1); });
SCRIPT

# Generate each format into the temp dir. Failures are fatal: with `set -e` a
# non-zero gen-format.js (it exits 1 if the .fmt can't be extracted) aborts here.
for engine in pdflatex xelatex; do
  subdir=$(echo $engine | sed 's/pdflatex/pdftex/;s/xelatex/xetex/')
  mkdir -p "${FMT_TMP}/${subdir}"
  echo "--- Generating ${engine}.fmt ---"
  node "${FMT_TMP}/gen-format.cjs" "$engine" "$TEXLIVE_DIR" "$WASM_DIR" "${FMT_TMP}/${subdir}"
done

# Handle luahblatex separately (renamed from lualatex)
mkdir -p "${FMT_TMP}/luahbtex"
echo "--- Generating lualatex.fmt (for luahblatex) ---"
node "${FMT_TMP}/gen-format.cjs" "luahblatex" "$TEXLIVE_DIR" "$WASM_DIR" "${FMT_TMP}/luahbtex"

# Rename lualatex.fmt to luahblatex.fmt
mv "${FMT_TMP}/luahbtex/lualatex.fmt" "${FMT_TMP}/luahbtex/luahblatex.fmt"

# Assert every expected format was produced and is non-empty before swapping in.
echo ""
echo "=== Verifying generated formats ==="
for f in "${formats[@]}"; do
  if [ ! -s "${FMT_TMP}/$f" ]; then
    echo "FATAL: missing or empty format $f — refusing to swap in incomplete formats"
    exit 1
  fi
  echo "  ok: $f ($(wc -c < "${FMT_TMP}/$f") bytes)"
done

# All required formats are ready. Replace the install-time formats and record their inputs.
echo "=== Installing format files into ${FMT_DIR} ==="
for subdir in pdftex xetex luahbtex; do
  mkdir -p "${FMT_DIR}/${subdir}"
  rm -f "${FMT_DIR}/${subdir}"/*.fmt
  mv "${FMT_TMP}/${subdir}"/*.fmt "${FMT_DIR}/${subdir}/"
done

sha256sum "$LOCK_FILE" "${WASM_DIR}/busytex.wasm" "${WASM_DIR}/busytex.js" \
  "${formats[@]/#/$FMT_DIR/}" > "${FMT_TMP}/formats.sha256"
mv "${FMT_TMP}/formats.sha256" "$CHECKSUMS"

echo ""
echo "=== Format checksums ==="
cat "$CHECKSUMS"
echo "=== Done ==="
