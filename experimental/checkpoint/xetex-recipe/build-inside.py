from pathlib import Path
import json,subprocess,shlex,hashlib
out=Path('/out');g=Path('/work/build/wasm/texlive/texk/web2c');commands=[]
def run(args,cwd=g):commands.append({'argv':args,'cwd':str(cwd)});subprocess.run(args,cwd=cwd,check=True)
expr='$(DEFS) $(DEFAULT_INCLUDES) $(INCLUDES) $(xetex_CPPFLAGS) $(CPPFLAGS) $(AM_CFLAGS) $(CFLAGS)'
flags=shlex.split(subprocess.check_output(['make','-s','--no-print-directory','-o','Makefile','-o','config.status','--eval=checkpoint-flags:;@echo '+expr,'checkpoint-flags'],cwd=g,text=True).strip())
for stem in ['xetex0','xetexini']:run(['emcc','-Dbusymain=busymain_xetex','-Dprivileged=privileged',*flags,'-I'+str(g),'-I/out','-c',str(out/(stem+'.c')),'-o',str(out/('xetex-'+stem+'.o'))])
original=json.loads(Path('/control/commands.json').read_text());args=[]
exports=['_siglum_checkpoint_'+x for x in ['engine','arm','disarm','resume','paused','prepare_snapshot','refresh_inputs','line','next_line','total_pages','input_ptr','input_index','input_state','buffer_loc','buffer_limit','buffer_start','buffer','input_stack','filename','input_fd','input_offset']]
for arg in original:
 if arg in ['/packed/xetex-xetex0.o','/packed/xetex-xetexini.o']:arg='/out/'+arg.rsplit('/',1)[1]
 elif arg=='/out/native-assets.o':arg='/control/native-assets.o'
 if arg.startswith('-sEXPORTED_FUNCTIONS='):
  names=json.loads(arg.split('=',1)[1]);arg='-sEXPORTED_FUNCTIONS='+json.dumps(list(dict.fromkeys(names+exports+['_malloc','_free'])))
 if arg.startswith('-sEXPORTED_RUNTIME_METHODS='):
  names=json.loads(arg.split('=',1)[1]);arg='-sEXPORTED_RUNTIME_METHODS='+json.dumps(list(dict.fromkeys(names+['stackSave','stackRestore'])))
 args.append(arg)
run(args,Path('/work'));(out/'commands-executed.json').write_text(json.dumps(commands,indent=2)+'\n');(out/'commands.json').write_text(json.dumps(args,indent=2)+'\n');(out/'toolchain.txt').write_text(subprocess.check_output(['emcc','--version'],text=True));(out/'artifacts.json').write_text(json.dumps({f.name:{'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()}for f in out.glob('busytex.*')},indent=2)+'\n')
