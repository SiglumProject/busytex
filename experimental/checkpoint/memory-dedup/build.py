#!/usr/bin/env python3
"""Rebuild the no-stack, no-data Rust kernels; requires installed wasm32 target."""
from pathlib import Path
import subprocess,json,hashlib,base64
root=Path(__file__).resolve().parent
for variant in ['scalar','simd']:
    flags=['rustc',str(root/'kernel.rs'),'--crate-type','cdylib','--target','wasm32-unknown-unknown','-O','-Cpanic=abort','-C','link-arg=--import-memory','-C','link-arg=--initial-memory=0','-C','link-arg=-zstack-size=0','-C','link-arg=--export=__stack_pointer']
    if variant=='simd': flags+=['-C','target-feature=+simd128','--cfg','feature="simd"']
    subprocess.run(flags+['-o',str(root/(variant+'.wasm'))],check=True)
subprocess.run(['python3',str(root/'prepare.py')],check=True)
(root/'rustc-version.txt').write_text(subprocess.check_output(['rustc','--version'],text=True))
