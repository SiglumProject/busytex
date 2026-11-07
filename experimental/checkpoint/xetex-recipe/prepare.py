from pathlib import Path
import argparse,hashlib,json,re,shutil
p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
for f in a.base.iterdir():
 if f.suffix in ['.h','.inc']:shutil.copy2(f,a.output/f.name)
shutil.copy2(Path(__file__).parent/'siglum_xetex_checkpoint.inc',a.output/'siglum_xetex_checkpoint.inc')
records=[]
for name in ['xetex0.c','xetexini.c']:
 original=(a.base/name).read_text();text=original;include='#include "xetexd.h"';assert text.count(include)==1
 if name=='xetex0.c':
  text=text.replace(include,include+'\n#include "siglum_xetex_checkpoint.inc"',1)
  match=re.search(r'maincontrol \( void \)\s*\n\{',text);assert match
  begin=match.start();closing=re.search(r'(?m)^}[^\S\n]*\n',text[match.end():]);assert closing;end=match.end()+closing.end();original_body=text[begin:end]
  shape=re.search(r'  if \( eqtb \[\d+L \].*?\n  begintokenlist \(.*?;\n  lab60: getxtoken \(\) ;',original_body,re.S);assert shape,'maincontrol boundary changed'
  entry='  if (siglum_checkpoint_resume_enter) {\n    siglum_checkpoint_resume_enter = 0;\n    goto lab60;\n  }\n'
  # Keep the ordinary token loop unchanged. The instrumented duplicate is used
  # only while seeking a new boundary; normal continuation has no per-token poll.
  normal_body=original_body.replace(shape.group(),entry+shape.group(),1)
  assert normal_body.replace(entry,'',1)==original_body
  instrumented=normal_body.replace('maincontrol ( void )','siglum_checkpoint_maincontrol ( void )',1)
  assert instrumented != normal_body
  instrumented=instrumented.replace('  lab60: getxtoken () ;','  lab60: if (siglum_checkpoint_poll()) return;\n  getxtoken () ;',1)
  text=text[:begin]+normal_body+'\nvoid\n'+instrumented+text[end:]

 else:
  text=text.replace(include,include+'\nextern int siglum_checkpoint_is_paused;\nextern int siglum_checkpoint_resume_enter;\nextern void siglum_checkpoint_run_maincontrol(void);',1)
  point='  maincontrol () ;\n  finalcleanup () ;';assert text.count(point)==1
  text=text.replace(point,'  siglum_checkpoint_run_maincontrol() ;\n  if (siglum_checkpoint_is_paused) return;\n  finalcleanup () ;',1)
  text+='''
/* Same-instance continuation: heap, stack, native library state and JS FS must
 * be restored by the host before calling. No output conversion while paused. */
int siglum_checkpoint_resume(void) {
    if (!siglum_checkpoint_is_paused) return -1;
    siglum_checkpoint_is_paused = 0;
    siglum_checkpoint_resume_enter = 1;
    siglum_checkpoint_run_maincontrol();
    if (siglum_checkpoint_is_paused) return 1;
    finalcleanup();
    closefilesandterminate();
    fflush(stdout);
    readyalready = 0;
    return (history != 0 && history != 1) ? 2 : 0;
}
'''
 (a.output/name).write_text(text);records.append({'name':name,'baseSha256':hashlib.sha256(original.encode()).hexdigest(),'candidateSha256':hashlib.sha256(text.encode()).hexdigest()})
(a.output/'source-provenance.json').write_text(json.dumps(records,indent=2)+'\n')
