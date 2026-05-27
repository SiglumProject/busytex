#!/bin/bash
set -e

EMSCRIPTEN_VERSION="3.1.43"
IMAGE="emscripten/emsdk:${EMSCRIPTEN_VERSION}"

run_container() {
  podman run --rm -v "$(pwd):/work" -w /work "$IMAGE" bash -c "$1"
}

# Extract the embedded "TeX Live <year>" banner from a busytex binary.
tl_version() {
  command -v strings >/dev/null 2>&1 || return 0
  strings "$1" 2>/dev/null | grep -oE 'TeX Live 20[0-9][0-9]' | head -1
}

# Guard against a stale native binary: install-tl uses build/native/busytex as
# its --custom-bin, so a leftover from a previous TeX Live would install the new
# packages with an old engine (silent version mismatch). Require it to match the
# freshly built WASM binary. Year is derived, not hardcoded, so this survives the
# next TL bump. Skips quietly if either binary or `strings` is unavailable.
assert_native_matches_wasm() {
  local native="build/native/busytex" wasm="build/wasm/busytex.wasm" nv wv
  [ -f "$native" ] && [ -f "$wasm" ] || return 0
  nv="$(tl_version "$native")"; wv="$(tl_version "$wasm")"
  [ -n "$nv" ] && [ -n "$wv" ] || return 0
  if [ "$nv" != "$wv" ]; then
    echo "FATAL: native busytex is '$nv' but WASM busytex is '$wv' — the native binary is stale." >&2
    echo "       install-tl would install '$wv' packages with a '$nv' engine. Rebuild: ./build-wasm.sh wasm" >&2
    exit 1
  fi
  echo "native/WASM engine versions match: $nv"
}

usage() {
  cat <<'EOF'
Usage: ./build-wasm.sh <command>

Commands:
  native        Build native busytex binary (for install-tl)
  wasm          Build native + WASM binaries (busytex.wasm + busytex.js)
  relink        Relink WASM binary only (fast — reuses .o files)
  texlive       Run install-tl to install TeX Live packages
  formats       Regenerate format files using WASM binary (ensures match)
  package       Run file_packager to create texlive-basic.data
  bundles       Split texlive-basic.data into browser-loadable bundles (runs on host)
  all           Run full pipeline: wasm → texlive → formats → package → bundles
  clean         Remove build/ and source/ directories

Upgrade workflow (TeX Live version bump):
  1. Update Makefile URLs for new TeX Live version
  2. Download ISO:  make source/texmfrepo.txt
  3. ./build-wasm.sh wasm        # Rebuild native + WASM engines
  4. ./build-wasm.sh texlive     # Install packages via install-tl
  5. ./build-wasm.sh formats     # Regenerate .fmt files with WASM binary
  6. ./build-wasm.sh package     # Create texlive-basic.data
  7. ./build-wasm.sh bundles     # Split into browser bundles

Prerequisites:
  - Podman (podman machine start)
  - Bun runtime (for bundle splitting)
  - ~10GB disk for TeX Live ISO
EOF
}

cmd_native() {
  echo "=== Building native busytex binary ==="
  # Use Ubuntu container — native static linking needs full glibc dev libs
  podman run --rm -v "$(pwd):/work" -w /work ubuntu:22.04 bash -c "
    apt-get update &&
    apt-get install -y build-essential cmake gperf p7zip-full icu-devtools file wget pkg-config python3 &&
    make source/texlive.txt &&
    make native
  "
  echo "=== Done: build/native/busytex ==="
}

cmd_wasm() {
  echo "=== Building native + WASM binaries ==="
  run_container "
    sudo apt-get update &&
    sudo apt-get install -y gperf p7zip-full icu-devtools file &&
    make source/texlive.txt &&
    make native &&
    make wasm-all
  "
  echo "=== Done: build/native/busytex + build/wasm/busytex.wasm + build/wasm/busytex.js ==="
}

cmd_relink() {
  echo "=== Relinking WASM binary (fast — reuses existing .o files) ==="
  run_container "
    rm -f build/wasm/busytex.js build/wasm/busytex.wasm &&
    make build/wasm/busytex.js
  "
  echo "=== Done: build/wasm/busytex.wasm + build/wasm/busytex.js ==="
}

cmd_texlive() {
  echo "=== Running install-tl in container ==="
  assert_native_matches_wasm
  run_container "
    sudo apt-get update -qq && sudo apt-get install -yqq perl >/dev/null 2>&1 &&
    make build/texlive-basic.txt
  "
  echo "=== Done: build/texlive-basic/ ==="
}

cmd_formats() {
  echo "=== Regenerating format files with WASM binary ==="
  run_container "bash regen-formats.sh"
  echo "=== Done: format files regenerated ==="
}

cmd_package() {
  echo "=== Packaging texlive-basic.data ==="
  # Force a repackage. The Makefile target depends on the texmf-dist *directory*,
  # whose mtime doesn't change when files deep inside it (e.g. regenerated .fmt)
  # are updated, so make would otherwise report "up to date" and ship a stale
  # .data missing the new formats. Removing the outputs guarantees correctness;
  # file_packager is cheap relative to shipping a stale tree.
  run_container "rm -f build/wasm/texlive-basic.js build/wasm/texlive-basic.data && make build/wasm/texlive-basic.js"
  echo "=== Done: build/wasm/texlive-basic.data + build/wasm/texlive-basic.js ==="
}

cmd_bundles() {
  echo "=== Splitting into browser bundles ==="
  # Bundle splitting is a siglum-superproject concern: it lives in ../packages
  # in the submodule layout. A standalone busytex checkout has no ../packages,
  # so make the location overridable and fail with a clear message if absent
  # rather than emitting a confusing `cd: no such file or directory`.
  PACKAGES_DIR="${SIGLUM_PACKAGES_DIR:-../packages}"
  if [ ! -f "$PACKAGES_DIR/split-bundle.ts" ]; then
    echo "split-bundle.ts not found at $PACKAGES_DIR — set SIGLUM_PACKAGES_DIR (the bundles step is siglum-only and needs the superproject's packages/)" >&2
    exit 1
  fi
  local data_dir
  data_dir="$(pwd)/build/wasm"
  # split-bundle.ts OVERWRITES file-manifest.json from the texlive-basic tree only.
  # cm-super is built/served as a separate bundle (too big to fetch at runtime) and
  # its entries are merged back into file-manifest.json by bundle-cm-super.ts. That
  # merge MUST run after the split, or the manifest loses every cm-super font and
  # compiles fail with "Font <tc/ec font> not found".
  ( cd "$PACKAGES_DIR" \
      && bun run split-bundle.ts "$data_dir/texlive-basic.js" "$data_dir/texlive-basic.data" ./bundles \
      && bun run bundle-cm-super.ts )
  echo "=== Done: $PACKAGES_DIR/bundles/ (incl. re-merged cm-super) ==="
}

cmd_clean() {
  echo "=== Cleaning build artifacts ==="
  rm -rf build source
  echo "=== Done ==="
}

cmd_all() {
  cmd_wasm
  cmd_texlive
  cmd_formats
  cmd_package
  cmd_bundles
}

case "${1:-help}" in
  native)   cmd_native ;;
  wasm)     cmd_wasm ;;
  relink)   cmd_relink ;;
  texlive)  cmd_texlive ;;
  formats)  cmd_formats ;;
  package)  cmd_package ;;
  bundles)  cmd_bundles ;;
  all)      cmd_all ;;
  clean)    cmd_clean ;;
  help|*)   usage ;;
esac
