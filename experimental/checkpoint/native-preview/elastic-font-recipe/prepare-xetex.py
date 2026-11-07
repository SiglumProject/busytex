#!/usr/bin/env python3
"""Prepare XeTeX font storage from an existing pinned generated native tree."""
from pathlib import Path
import argparse,re,hashlib,json,difflib
from font_memory import font_memory_source
p=argparse.ArgumentParser();p.add_argument('--generated',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
prefix='siglum_xetex_font';stem=prefix+'_memory';header,implementation=font_memory_source(prefix)
(out/(stem+'.h')).write_text(header);(out/(stem+'.inc')).write_text(implementation);provenance=[]
for name in ['xetex0.c','xetexini.c']:
 source=a.generated/name;before=source.read_text();text=before;needle='#include "xetexd.h"';assert text.count(needle)==1;text=text.replace(needle,needle+'\n#include "'+stem+'.h"'+('\n#include "'+stem+'.inc"'if name=='xetex0.c'else''),1)
 if name=='xetex0.c':
  pattern=re.compile(r'\(\s*(fmemptr(?:\s*\+\s*[a-zA-Z_][a-zA-Z_0-9]*)*)\s*(==|>=|>)\s*fontmemsize\s*\)')
  def guard(match):
   expression,operator=match.groups();extra=' + 1'if operator in ['==','>=']else''
   return '( !'+stem+'_reserve((long long)'+expression+extra+') )'
  text,count=pattern.subn(guard,text);assert count==3,(count,'Unreviewed generated font-table guards')
  text=re.sub(r'(overflow\s*\(\s*\d+L?\s*,\s*)fontmemsize(\s*\))',r'\1'+stem+'_limit()'+r'\2',text)
 else:
  needle='    else if ( fontmemsize > supfontmemsize ) \n    fontmemsize = supfontmemsize ;\n  }';assert text.count(needle)==1;text=text.replace(needle,needle+'\n  '+stem+'_begin();',1)
 (out/name).write_text(text);(out/(name+'.patch')).write_text(''.join(difflib.unified_diff(before.splitlines(True),text.splitlines(True),'a/'+name,'b/'+name)));provenance.append({'source':str(source),'baseSha256':hashlib.sha256(before.encode()).hexdigest(),'candidateSha256':hashlib.sha256(text.encode()).hexdigest()})
(out/'source-provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
