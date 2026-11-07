#!/usr/bin/env bash
set -euo pipefail
recipe_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source_dir="${SIGLUM_CHECKPOINT_SOURCE:-$(cd "$recipe_dir/../.." && pwd)}"
output_dir="${SIGLUM_CHECKPOINT_OUT:-$recipe_dir/out}"
image='emscripten/emsdk@sha256:e856cd59d54fd143366c2df314043d63a1ca23ab43521e0f30f9d9a7ce6d43e0'
mkdir -p "$output_dir"
python3 "$recipe_dir/patch-generated.py" \
    --generated "$source_dir/build/wasm/texlive/texk/web2c" --out "$output_dir"
docker_recipe_dir="$recipe_dir"
docker_output_dir="$output_dir"
# Colima shares the home directory by default, but not macOS /private/tmp.
if [[ "$recipe_dir" == /private/tmp/* || "$output_dir" == /private/tmp/* ]]; then
    stage_root="${SIGLUM_CHECKPOINT_DOCKER_STAGE_ROOT:-$source_dir/build/.checkpoint-stage}"
    mkdir -p "$stage_root"
    stage_dir="$(mktemp -d "$stage_root/checkpoint-build.XXXXXX")"
    docker_recipe_dir="$stage_dir/recipe"
    docker_output_dir="$stage_dir/out"
    mkdir -p "$docker_recipe_dir" "$docker_output_dir"
    cp "$recipe_dir/build-inside.py" "$docker_recipe_dir/"
    cp -R "$output_dir/." "$docker_output_dir/"
    printf 'Colima staging directory: %s\n' "$stage_dir"
fi
docker run --rm --network none --platform linux/amd64 \
    --mount "type=bind,src=$source_dir,dst=/work,readonly" \
    --mount "type=bind,src=$docker_recipe_dir,dst=/recipe,readonly" \
    --mount "type=bind,src=$docker_output_dir,dst=/out" \
    "$image" python3 /recipe/build-inside.py "$@"
if [[ "$docker_output_dir" != "$output_dir" ]]; then
    cp -R "$docker_output_dir/." "$output_dir/"
fi
