#!/usr/bin/env python3
"""Prepare a bounded growable font-info table against a pinned generated build."""
from pathlib import Path
import argparse, shutil, json, hashlib, difflib, re
p=argparse.ArgumentParser()
p.add_argument('--base-runtime',type=Path,required=True)
p.add_argument('--base-commands',type=Path,required=True)
p.add_argument('--generated-commands',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
for source in a.base_runtime.iterdir():
    if source.suffix in ['.o','.a','.c','.h','.inc']:
        shutil.copy2(source,out/source.name)
from font_memory import font_memory_source
header,implementation=font_memory_source()
(out/'siglum_font_memory.h').write_text(header)
(out/'siglum_font_memory.inc').write_text(implementation)
provenance={}
for name in ['pdftex0.c','pdftexini.c']:
    path=out/name;before=path.read_text();s=before
    needle='#include "pdftexd.h"'
    assert s.count(needle)==1
    s=s.replace(needle,needle+'\n#include "siglum_font_memory.h"',1)
    if name=='pdftex0.c':
        s=s.replace('#include "siglum_checkpoint.inc"','#include "siglum_checkpoint.inc"\n#include "siglum_font_memory.inc"',1)
        pattern=re.compile(r'\(\s*(fmemptr(?:\s*\+\s*[a-zA-Z_][a-zA-Z_0-9]*)*)\s*(==|>=|>)\s*fontmemsize\s*\)')
        def guard(match):
            expression,operator=match.groups()
            extra=' + 1' if operator in ['==','>='] else ''
            return '( !siglum_font_memory_reserve((long long)'+expression+extra+') )'
        s,count=pattern.subn(guard,s)
        # TFM loading, fontdimen extension, and both expansion allocations.
        assert count==4,(count,'Unreviewed generated font-table guards')
        s=re.sub(r'(overflow\s*\(\s*\d+L?\s*,\s*)fontmemsize(\s*\))',r'\1siglum_font_memory_limit()\2',s)
    else:
        needle='''    else if ( fontmemsize > supfontmemsize ) 
    fontmemsize = supfontmemsize ;
  }'''
        assert s.count(needle)==1
        s=s.replace(needle,needle+'\n  siglum_font_memory_begin();',1)
    path.write_text(s)
    (out/(name+'.patch')).write_text(''.join(difflib.unified_diff(before.splitlines(True),s.splitlines(True),fromfile='a/'+name,tofile='b/'+name)))
    provenance[name]={'base':hashlib.sha256(before.encode()).hexdigest(),'patched':hashlib.sha256(s.encode()).hexdigest()}
commands=json.loads(a.generated_commands.read_text())
compile_commands=[c for c in commands if '-c' in c and any(x.endswith('/pdftex0.c') or x.endswith('/pdftexini.c') for x in c)]
# A relink-only base may have rebuilt just the initialization object. The
# generated engine and initialization units use the same pinned PDFTEX flags.
if len(compile_commands)==1:
    template=compile_commands[0]
    missing='pdftex0' if '/out/pdftexini.c' in template else 'pdftexini'
    clone=list(template)
    clone[clone.index('-c')+1]='/out/'+missing+'.c'
    clone[clone.index('-o')+1]='/out/pdftex-'+missing+'.o'
    compile_commands.append(clone)
assert len(compile_commands)==2
link=json.loads(a.base_commands.read_text())[-1]
for i,arg in enumerate(link):
    if arg.startswith('-sEXPORTED_FUNCTIONS='):
        names=json.loads(arg.split('=',1)[1]);names += ['_siglum_font_memory_configure','_siglum_font_memory_capacity','_siglum_font_memory_limit','_siglum_font_memory_growth_count'];link[i]='-sEXPORTED_FUNCTIONS='+json.dumps(names)
(out/'commands.json').write_text(json.dumps(compile_commands+[link],indent=2)+'\n')
(out/'source-provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
