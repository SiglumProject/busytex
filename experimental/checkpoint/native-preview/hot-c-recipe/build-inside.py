#!/usr/bin/env python3
from pathlib import Path
import json,subprocess,hashlib
out=Path('/out')
for command in json.loads((out/'commands.json').read_text()):
    subprocess.run(command,cwd='/work/build/wasm/texlive/texk/web2c',check=True)
(out/'toolchain.txt').write_text(subprocess.check_output(['emcc','--version'],text=True))
(out/'artifact-sha256.json').write_text(json.dumps({n:hashlib.sha256((out/n).read_bytes()).hexdigest()for n in ['pdftex.js','pdftex.wasm','pdftex0.c','pdftexini.c']},indent=2)+'\n')
