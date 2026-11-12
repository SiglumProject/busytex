#!/usr/bin/env python3
"""Rebuild the private-memory state comparison kernel; requires installed wasm32 target."""
from pathlib import Path
import subprocess,json,hashlib,base64
root=Path(__file__).resolve().parent
subprocess.run(['rustc',str(root/'kernel.rs'),'--edition','2021','--crate-type','cdylib','--target','wasm32-unknown-unknown','-C','opt-level=3','-Cpanic=abort','-C','strip=symbols','-C','lto=fat','-C','codegen-units=1','-C','link-arg=-zstack-size=65536','-o',str(root/'converge.wasm')],check=True)
data=(root/'converge.wasm').read_bytes()
meta={'converge':{'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}}
(root/'embedded.mjs').write_text('\n'.join(['// Generated from busytex/experimental/checkpoint/converge/kernel.rs.','// Private-memory comparison of two engine states; no imports and no access to compiler memory.',f"export const convergeSha256 = '{meta['converge']['sha256']}';",f"export const convergeBytes = () => Uint8Array.from(atob('{base64.b64encode(data).decode()}'), c => c.charCodeAt(0));"])+'\n')
(root/'artifacts.json').write_text(json.dumps(meta,indent=2)+'\n')
(root/'rustc-version.txt').write_text(subprocess.check_output(['rustc','--version'],text=True))
