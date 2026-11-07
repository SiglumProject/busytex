#!/usr/bin/env python3
"""Recompile hot generated TeX units with one explicit optimization change."""
from pathlib import Path
import argparse,json,shutil,hashlib
p=argparse.ArgumentParser()
p.add_argument('--base-runtime',type=Path,required=True)
p.add_argument('--commands',type=Path,required=True)
p.add_argument('--optimization',choices=['-Oz','-O2','-O3'],required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
for path in a.base_runtime.iterdir():
    if path.suffix in ['.o','.a','.c','.h','.inc']:shutil.copy2(path,out/path.name)
original=json.loads(a.commands.read_text());commands=[]
for c in original:
    if '-c' in c and any(x.endswith('/pdftex0.c') or x.endswith('/pdftexini.c') for x in c):
        c=[a.optimization if x in ['-Oz','-Os','-O1','-O2','-O3'] else x for x in c]
    commands.append(c)
assert len([c for c in commands if '-c' in c])==2
assert not any(x=='-sERROR_ON_UNDEFINED_SYMBOLS=0' for x in commands[-1])
(out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
(out/'base-identity.json').write_text(json.dumps({'optimization':a.optimization,'baseWasmSha256':hashlib.sha256((a.base_runtime/'pdftex-o3.wasm').read_bytes()).hexdigest(),'baseCommandsSha256':hashlib.sha256(a.commands.read_bytes()).hexdigest(),'sourceSha256':{n:hashlib.sha256((out/n).read_bytes()).hexdigest()for n in ['pdftex0.c','pdftexini.c']}},indent=2)+'\n')
