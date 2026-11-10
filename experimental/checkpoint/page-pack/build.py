#!/usr/bin/env python3
"""Rebuild the private-memory block codec; requires installed wasm32 target."""
from pathlib import Path
import subprocess,json,hashlib,base64
root=Path(__file__).resolve().parent
subprocess.run(['rustc',str(root/'kernel.rs'),'--crate-type','cdylib','--target','wasm32-unknown-unknown','-C','opt-level=3','-Cpanic=abort','-C','strip=symbols','-C','lto=fat','-C','codegen-units=1','-C','link-arg=-zstack-size=16384','-o',str(root/'pack.wasm')],check=True)
data=(root/'pack.wasm').read_bytes()
meta={'pack':{'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}}
(root/'embedded.mjs').write_text('\n'.join(['// Generated from busytex/experimental/checkpoint/page-pack/kernel.rs.','// Private-memory lossless block codec; no imports and no access to compiler memory.',f"export const packSha256 = '{meta['pack']['sha256']}';",f"export const packBytes = () => Uint8Array.from(atob('{base64.b64encode(data).decode()}'), c => c.charCodeAt(0));"])+'\n')
(root/'artifacts.json').write_text(json.dumps(meta,indent=2)+'\n')
(root/'rustc-version.txt').write_text(subprocess.check_output(['rustc','--version'],text=True))
