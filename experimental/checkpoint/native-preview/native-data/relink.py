"""Relink the recorded packed native build with matching ICU stubdata."""
from pathlib import Path
import argparse,subprocess,json,hashlib
p=argparse.ArgumentParser();p.add_argument('--commands',required=True,type=Path);p.add_argument('--objects',required=True,type=Path);p.add_argument('--icu-common',required=True,type=Path);p.add_argument('--output',required=True,type=Path);p.add_argument('--compiler',default='emcc');p.add_argument('--runtime-assertions',type=int,choices=[0,1,2],default=1);p.add_argument('--stack-check',type=int,choices=[1,2],default=2);a=p.parse_args()
source=Path(__file__).resolve().parent/'native.c';a.output.mkdir(parents=True,exist_ok=True)
subprocess.run([a.compiler,'-O3','-I'+str(a.icu_common),'-c',str(source),'-o',str(a.output/'native-assets.o')],check=True)
recorded=json.loads(a.commands.read_text());original=recorded[-1]['argv']if isinstance(recorded[-1],dict)else recorded
command=[];replaced=0
for arg in original:
 if arg==original[0]:arg=a.compiler
 if arg.startswith('/out/'):
  arg=str(a.output/'busytex.js')if arg=='/out/busytex.js'else str(a.objects/arg.removeprefix('/out/'))
 if arg.endswith('/lib/libicudata.a'):
  arg=arg.replace('/lib/libicudata.a','/stubdata/libicudata.a');assert Path(arg).is_file(),arg;replaced+=1
 if arg.startswith('-sASSERTIONS='):arg='-sASSERTIONS='+str(a.runtime_assertions)
 if arg.startswith('-sEXPORTED_FUNCTIONS='):
  names=json.loads(arg.split('=',1)[1]);names=list(dict.fromkeys(names+['_siglum_icu_use_files','_siglum_icu_probe']));arg='-sEXPORTED_FUNCTIONS='+json.dumps(names)
 command.append(arg)
assert replaced==1,'Expected exactly one ICU data archive'
# Keep explicit stack checks in optimized browser release variants.
if a.runtime_assertions==0:command.append('-sSTACK_OVERFLOW_CHECK='+str(a.stack_check))
command.append(str(a.output/'native-assets.o'));subprocess.run(command,check=True)
(a.output/'commands.json').write_text(json.dumps(command,indent=2)+'\n')
(a.output/'artifacts.json').write_text(json.dumps({f.name:{'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()}for f in a.output.glob('busytex.*')},indent=2)+'\n')
(a.output/'compiler-version.txt').write_text(subprocess.check_output([a.compiler,'--version'],text=True))
