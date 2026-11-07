from pathlib import Path
import base64,hashlib,json
s=Path(__file__).resolve().parent
parts=['// Embedded read-only page comparison kernels; imported engine memory only.']
meta={}
for name in ['scalar','simd']:
 data=(s/(name+'.wasm')).read_bytes();meta[name]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()};parts.append(f"export const {name}Bytes = () => Uint8Array.from(atob('{base64.b64encode(data).decode()}'), c => c.charCodeAt(0));")
(s/'embedded.mjs').write_text('\n'.join(parts)+'\n');(s/'artifacts.json').write_text(json.dumps(meta,indent=2)+'\n')
