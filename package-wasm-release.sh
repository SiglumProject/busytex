#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

commit="${1:-$(git rev-parse HEAD)}"
format_version=$(python3 -c 'import json; print(json.load(open("texlive-packages.lock.json"))["formatVersion"])')
if [[ ! "$commit" =~ ^[0-9a-f]{40}$ || ! "$format_version" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
  echo "Expected a full source commit and an ISO-format LaTeX date." >&2
  exit 1
fi

make verify-basic-formats
tag="busytex-latex-${format_version}-${commit:0:12}"
stage=$(mktemp -d "$PWD/build/.busytex-release.XXXXXX")
trap 'rm -rf "$stage"' EXIT
mkdir "$stage/$tag" "$stage/unpacked"

for asset in busytex.js busytex.wasm texlive-basic.js texlive-basic.data; do
  test -s "build/wasm/$asset"
  cp "build/wasm/$asset" "$stage/$tag/"
done
test -s build/versions.txt
cp build/versions.txt build/texlive-basic-formats.sha256 texlive-packages.lock.json smoke-release.cjs "$stage/$tag/"
cp build/texlive-basic/LICENSE.CTAN build/texlive-basic/LICENSE.TL "$stage/$tag/"
printf '%s\n' "$commit" > "$stage/$tag/source-commit.txt"

archive="$tag.tar.gz"
(
  cd "$stage"
  tar -czf "$archive" "$tag"
  sha256sum "$archive" > SHA256SUMS
  sha256sum -c SHA256SUMS
  tar -xzf "$archive" -C unpacked
  node "unpacked/$tag/smoke-release.cjs"
)

mkdir -p build/release
mv "$stage/$archive" "build/release/$archive"
mv "$stage/SHA256SUMS" build/release/SHA256SUMS
printf 'Staged build/release/%s\n' "$archive"
