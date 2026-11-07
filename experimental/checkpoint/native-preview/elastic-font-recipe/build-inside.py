#!/usr/bin/env python3
from pathlib import Path
import subprocess,json,hashlib
out=Path('/out');commands=json.loads((out/'commands.json').read_text())
for command in commands:
    subprocess.run(command,cwd='/work/build/wasm/texlive/texk/web2c',check=True)
(out/'toolchain.txt').write_text(subprocess.check_output(['emcc','--version'],text=True))
(out/'artifact-sha256.json').write_text(json.dumps({name:hashlib.sha256((out/name).read_bytes()).hexdigest() for name in ['pdftex.js','pdftex.wasm','pdftex0.c','pdftexini.c','siglum_font_memory.h','siglum_font_memory.inc']},indent=2)+'\n')
