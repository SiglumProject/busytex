from pathlib import Path
import re,json,hashlib,difflib,shutil
import argparse
parser=argparse.ArgumentParser(description='Prepare checked packed XeTeX hash storage from a pinned generated runtime')
parser.add_argument('--base-runtime',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args();base=args.base_runtime.resolve();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
for p in base.iterdir():
 if p.suffix in ['.c','.h','.inc']:shutil.copy2(p,out/p.name)
# These indices are extracted from the pinned generated program's own format
# loader and font-id interval. Refuse an unfamiliar layout before patching.
ini=(base/'xetexini.c').read_text()
bases=set(map(int,re.findall(r'hash \[(\d+)L \]\.v\.LH = 0',ini)))
assert len(bases)==1,bases
base_index=bases.pop()
low_ends=set(map(int,re.findall(r'if \( hashextra == 0 \) \n  hashtop = (\d+)L',ini)))
assert len(low_ends)==1,low_ends
low_end=low_ends.pop()
eqtb_bases=set(map(int,re.findall(r'eqtbtop = (\d+)L \+ hashextra',ini)))
assert len(eqtb_bases)==1,eqtb_bases
high_base=eqtb_bases.pop()+1
assert base_index<low_end<high_base
assert f'dumpthings ( hash [{high_base}L ], hashhigh )'in ini
assert f'dumpthings ( hash [hashused + 1 ], {low_end-1}L - hashused )'in ini
header=f'''#ifndef SIGLUM_XETEX_HASH_MEMORY_H
#define SIGLUM_XETEX_HASH_MEMORY_H
#include <stdlib.h>
#define SIGLUM_XETEX_HASH_BASE {base_index}L
#define SIGLUM_XETEX_HASH_LOW_END {low_end}L
#define SIGLUM_XETEX_HASH_HIGH_BASE {high_base}L
/* Logical TeX identifiers and format bytes remain unchanged. Only the host
 * storage for the disjoint hash-table intervals is packed. */
static inline long siglum_xetex_hash_slots(void) {{
    return SIGLUM_XETEX_HASH_LOW_END - SIGLUM_XETEX_HASH_BASE + 1
        + (hashtop >= SIGLUM_XETEX_HASH_HIGH_BASE ? hashtop - SIGLUM_XETEX_HASH_HIGH_BASE + 1 : 0);
}}
static inline twohalves *siglum_xetex_hash_at(halfword index) {{
    if (index >= SIGLUM_XETEX_HASH_BASE && index <= SIGLUM_XETEX_HASH_LOW_END)
        return yhash + (index - SIGLUM_XETEX_HASH_BASE);
    if (index >= SIGLUM_XETEX_HASH_HIGH_BASE && index <= hashtop)
        return yhash + (SIGLUM_XETEX_HASH_LOW_END - SIGLUM_XETEX_HASH_BASE + 1)
            + (index - SIGLUM_XETEX_HASH_HIGH_BASE);
    /* A new native access into a previously unused gap is an ABI mismatch,
       never a reason to alias unrelated slots or silently drop a definition. */
    abort();
}}
#define SIGLUM_XETEX_HASH(index) (*siglum_xetex_hash_at((index)))
#endif
'''
(out/'siglum_xetex_hash_memory.h').write_text(header)
(out/'siglum_xetex_hash_memory.inc').write_text('''/* Read-only allocation diagnostics, outside the measured execution path. */
unsigned int siglum_xetex_table_profile(int field) {
    switch (field) {
    case 1: return siglum_xetex_hash_slots() * sizeof(*yhash);
    case 2: return (1 + hashtop - hashoffset) * sizeof(*yhash);
    case 3: return (eqtbtop + 1) * sizeof(*zeqtb);
    case 4: return (memmax - memmin + 1) * sizeof(*zmem);
    case 5: return poolsize * sizeof(*strpool);
    case 6: return maxstrings * sizeof(*strstart);
    case 7: return fontmemsize * sizeof(*fontinfo);
    case 8: return hashextra;
    case 9: return hashhigh;
    case 10: return hashtop;
    default: return 0;
    }
}
''')
# A lexical, balanced-bracket transformation. It skips strings, chars and both
# comment forms and recursively handles nested hash reads. C lvalue semantics
# and address-taking for the unchanged format I/O macros are preserved.
def replace_hash(text):
 result=[];count=0;i=0;pattern=re.compile(r'\bhash\s*\[')
 while i<len(text):
  if text.startswith('//',i):
   j=text.find('\n',i);j=len(text)if j<0 else j;result.append(text[i:j]);i=j;continue
  if text.startswith('/*',i):
   j=text.index('*/',i+2)+2;result.append(text[i:j]);i=j;continue
  if text[i]in '\"\'':
   quote=text[i];j=i+1
   while j<len(text):
    if text[j]=='\\':j+=2;continue
    if text[j]==quote:j+=1;break
    j+=1
   result.append(text[i:j]);i=j;continue
  m=pattern.match(text,i)if(i==0 or not(text[i-1].isalnum()or text[i-1]=='_'))else None
  if m:
   start=m.end();j=start;depth=1
   while depth:
    if text[j]=='[':depth+=1
    elif text[j]==']':depth-=1
    j+=1
   inside,nested=replace_hash(text[start:j-1]);result.append('SIGLUM_XETEX_HASH('+inside+')');count+=nested+1;i=j
  else:result.append(text[i]);i+=1
 return ''.join(result),count
records=[]
for name in ['xetex0.c','xetexini.c']:
 p=out/name;old=p.read_text();text=old.replace('#include "xetexd.h"','#include "xetexd.h"\n#include "siglum_xetex_hash_memory.h"'+ ('\n#include "siglum_xetex_hash_memory.inc"'if name=='xetex0.c'else''),1)
 if name=='xetexini.c':
  assert text.count('yhash = xmallocarray ( twohalves , 1 + hashtop - hashoffset ) ;')==2
  text=text.replace('yhash = xmallocarray ( twohalves , 1 + hashtop - hashoffset ) ;','yhash = xmallocarray ( twohalves , siglum_xetex_hash_slots() ) ;')
  assert text.count('hash = yhash - hashoffset ;')==2;text=text.replace('hash = yhash - hashoffset ;','hash = NULL; /* Direct logical indexing is forbidden in the packed layout. */')
  for index in ['x','hashused']:
   needle=f'hash [{index} ]= hash [{base_index}L ];';assert text.count(needle)==1
   text=text.replace(needle,f'''{{ if ({index} == SIGLUM_XETEX_HASH_LOW_END + 1) {index} = SIGLUM_XETEX_HASH_HIGH_BASE;
    if ({index} <= for_end) hash [{index} ]= hash [{base_index}L ]; }}''',1)
 text,count=replace_hash(text);assert count>20,(name,count)
 assert replace_hash(text)[1]==0
 p.write_text(text);(out/(name+'.patch')).write_text(''.join(difflib.unified_diff(old.splitlines(True),text.splitlines(True),'a/'+name,'b/'+name)))
 records.append({'name':name,'baseSha256':hashlib.sha256(old.encode()).hexdigest(),'candidateSha256':hashlib.sha256(text.encode()).hexdigest(),'rewrittenHashReferences':count})
manifest={'layout':{'base':base_index,'lowEndInclusive':low_end,'extraBase':high_base,'formatIdentifiersUnchanged':True,'hashExtraCapacityPreserved':True},'sources':records}
(out/'source-provenance.json').write_text(json.dumps(manifest,indent=2)+'\n');print(manifest)
