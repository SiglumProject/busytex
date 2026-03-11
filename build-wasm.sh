#!/bin/bash
set -e

NATIVE_RELEASE="build_native_ff0318af379bd80fb72b9b928d4744b5d9c9077d_12853073565_1"
URLRELEASE="https://github.com/busytex/busytex/releases/download/${NATIVE_RELEASE}"
EMSCRIPTEN_VERSION="3.1.43"
IMAGE="emscripten/emsdk:${EMSCRIPTEN_VERSION}"

run_container() {
  podman run --rm -v "$(pwd):/work" -w /work "$IMAGE" bash -c "$1"
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
    apt-get install -y build-essential gperf p7zip-full icu-devtools file wget pkg-config python3 &&
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
  run_container "make build/wasm/texlive-basic.js"
  echo "=== Done: build/wasm/texlive-basic.data + build/wasm/texlive-basic.js ==="
}

cmd_bundles() {
  echo "=== Splitting into browser bundles ==="
  cd ../packages
  bun run split-bundle.ts ../busytex/build/wasm/texlive-basic.js ../busytex/build/wasm/texlive-basic.data ./bundles
  echo "=== Done: packages/bundles/ ==="
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
