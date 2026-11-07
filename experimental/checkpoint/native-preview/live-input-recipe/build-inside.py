from pathlib import Path
import json,subprocess,shlex,shutil,hashlib,re
out=Path('/out'); generated=Path('/work/build/wasm/texlive/texk/kpathsea')
expr='$(DEFS) $(DEFAULT_INCLUDES) $(INCLUDES) $(libkpathsea_la_CPPFLAGS) $(CPPFLAGS) $(AM_CFLAGS) $(CFLAGS)'
flags=shlex.split(subprocess.check_output(['make','-s','--no-print-directory','-o','Makefile','-o','config.status','--eval=io-print-flags:;@echo '+expr,'io-print-flags'],cwd=generated,text=True).strip())
command=['emcc',*flags,'-c','/out/tex-file.c','-o','/out/libkpathsea_la-tex-file.o']
subprocess.run(command,cwd=generated,check=True)
shutil.copy2(generated/'.libs/libkpathsea.a',out/'libkpathsea.a')
subprocess.run(['emar','r','/out/libkpathsea.a','/out/libkpathsea_la-tex-file.o'],check=True)
web2c=Path('/work/build/wasm/texlive/texk/web2c')
expr='$(DEFS) $(DEFAULT_INCLUDES) $(INCLUDES) $(libpdftex_a_CPPFLAGS) $(CPPFLAGS) $(AM_CFLAGS) $(CFLAGS)'
map_flags=shlex.split(subprocess.check_output(['make','-s','--no-print-directory','-o','Makefile','-o','config.status','--eval=io-print-flags:;@echo '+expr,'io-print-flags'],cwd=web2c,text=True).strip())
makefile=Path('/work/Makefile').read_text()
words=lambda name: re.search(r'^'+name+r'\s*[:?]?=\s*(.+)$',makefile,re.M).group(1).split()
defines=['-D'+name+'=busypdftex_'+name for name in dict.fromkeys(words('PDFTEX_REDEFINE')+words('SYNCTEX_REDEFINE'))]
map_command=['emcc',*defines,*map_flags,'-I'+str(web2c),'-c','/out/mapfile.c','-o','/out/libpdftex_a-mapfile.o']
subprocess.run(map_command,cwd=web2c,check=True)
shutil.copy2(web2c/'busytex_libpdftex.a',out/'busytex_libpdftex.a')
subprocess.run(['emar','r','/out/busytex_libpdftex.a','/out/libpdftex_a-mapfile.o'],check=True)
link=json.loads(Path('/out/link-command.json').read_text())
subprocess.run(link,cwd='/work/build/wasm/texlive/texk/web2c',check=True)
(out/'build-commands.json').write_text(json.dumps([command,map_command,link],indent=2)+'\n')
(out/'toolchain.txt').write_text(subprocess.check_output(['emcc','--version'],text=True))
(out/'artifact-sha256.json').write_text(json.dumps({n:hashlib.sha256((out/n).read_bytes()).hexdigest() for n in ['pdftex.js','pdftex.wasm','libkpathsea.a','tex-file.c','mapfile.c','busytex_libpdftex.a']},indent=2)+'\n')
