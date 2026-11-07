"""Index every resource in the exact little-endian ICU CmnD package."""
from pathlib import Path
import argparse,hashlib,json,struct,shutil
parser=argparse.ArgumentParser();parser.add_argument('--data',required=True,type=Path);parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
data=args.data.read_bytes()
assert data[2:4]==bytes([0xda,0x27]) and data[8:11]==bytes([0,0,2]) and data[12:20]==b'CmnD\x01\0\0\0','Unsupported ICU package format'
header=struct.unpack_from('<H',data)[0];count=struct.unpack_from('<I',data,header)[0];entries=[]
assert 0<count<=8192
for i in range(count):
 name_at,offset=struct.unpack_from('<II',data,header+4+i*8);name_at+=header
 name=data[name_at:data.index(0,name_at)].decode('ascii')
 assert not name.startswith('/') and all(p not in ('','.','..')for p in name.split('/'))
 entries.append((name,header+offset))
assert len({name for name,_ in entries})==count and all(a[1]<b[1]for a,b in zip(entries,entries[1:]))
files=[]
for i,(name,start)in enumerate(entries):
 end=entries[i+1][1]if i+1<count else len(data);payload=data[start:end]
 assert payload[2:4]==bytes([0xda,0x27]),name
 files.append({'name':name,'offset':start,'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest()})
native=args.output/'native';native.mkdir(parents=True,exist_ok=True)
shutil.copyfile(args.data,native/'icu.dat')
index={'version':1,'pack':'native/icu.dat','packageSha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'files':files}
(native/'icu-index.json').write_text(json.dumps(index,separators=(',',':'))+'\n')
(args.output/'native-resources.json').write_text(json.dumps([{'version':1,'runtime':'combined','directory':'/icu','initialize':'_siglum_icu_use_files','index':'native/icu-index.json'}],indent=2)+'\n')
print(json.dumps({'resources':len(files),'packageBytes':len(data),'sha256':index['packageSha256']}))
