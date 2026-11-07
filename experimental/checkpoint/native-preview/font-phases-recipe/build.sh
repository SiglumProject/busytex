#!/usr/bin/env bash
set -euo pipefail
recipe_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source_dir="${SIGLUM_NATIVE_SOURCE:-$(cd "$recipe_dir/../../../.." && pwd)}"
base_recipe="${SIGLUM_NATIVE_BASE_RECIPE:-$(cd "$recipe_dir/../.." && pwd)}"
font_optimization="${SIGLUM_FONT_OPT:--Oz}"
case "$font_optimization" in -Oz|-O3) ;; *) exit 2 ;; esac
output_dir="${SIGLUM_NATIVE_OUT:-$recipe_dir/../out/font-phases-${font_optimization#-}}"
image='emscripten/emsdk@sha256:e856cd59d54fd143366c2df314043d63a1ca23ab43521e0f30f9d9a7ce6d43e0'
mkdir -p "$output_dir"
python3 "$recipe_dir/patch-font.py" --source "$source_dir" \
  --base-recipe "$base_recipe" --out "$output_dir"
docker run --rm --network none --platform linux/amd64 \
  --env "SIGLUM_FONT_OPT=$font_optimization" \
  --mount "type=bind,src=$source_dir,dst=/work,readonly" \
  --mount "type=bind,src=$recipe_dir,dst=/recipe,readonly" \
  --mount "type=bind,src=$output_dir,dst=/out" \
  "$image" python3 /recipe/build-inside.py --prototype-only
