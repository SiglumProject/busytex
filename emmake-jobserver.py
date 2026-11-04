#!/usr/bin/env python3
"""Run make with Emscripten's environment and inherited GNU Make job slots."""

from pathlib import Path
from shutil import which
import os
import sys


emmake = which('emmake')
if not emmake:
    sys.exit('emmake is required to build WASM')
sys.path.insert(0, str(Path(emmake).resolve().parent))
from tools import building

# Emscripten 3.1.43 starts make via subprocess, which closes the jobserver FDs.
os.execvpe(sys.argv[1], sys.argv[1:], building.get_building_env())
