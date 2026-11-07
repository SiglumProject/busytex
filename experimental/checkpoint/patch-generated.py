#!/usr/bin/env python3
"""Patch existing generated pdfTeX C into an isolated output directory."""
import argparse
import hashlib
import json
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--generated', type=Path, required=True)
p.add_argument('--out', type=Path, required=True)
args = p.parse_args()
args.out.mkdir(parents=True, exist_ok=True)
here = Path(__file__).resolve().parent
hashes = {}
for name in ('pdftex0.c', 'pdftexini.c'):
    raw = (args.generated / name).read_bytes()
    hashes[name] = hashlib.sha256(raw).hexdigest()
    text = raw.decode()
    if name == 'pdftex0.c':
        needle = '#include "pdftexd.h"'
        assert text.count(needle) == 1
        text = text.replace(needle, needle + '\n#include "siglum_checkpoint.inc"', 1)
        needle = ('  if ( eqtb [27165 ].hh .v.RH != -268435455L ) \n'
                  '  begintokenlist ( eqtb [27165 ].hh .v.RH , 12 ) ;\n'
                  '  lab60: getxtoken () ;')
        assert text.count(needle) == 1, 'maincontrol entry shape changed'
        replacement = ("  if ( siglum_checkpoint_resume_enter ) {\n"
                       "    siglum_checkpoint_resume_enter = 0;\n"
                       "    goto lab60;\n"
                       "  }\n" + needle.replace('  lab60: getxtoken () ;',
                       '  lab60: if (siglum_checkpoint_poll()) return;\n  getxtoken () ;'))
        text = text.replace(needle, replacement, 1)
    else:
        needle = '  maincontrol () ;\n  finalcleanup () ;'
        assert text.count(needle) == 1, 'mainbody completion shape changed'
        text = text.replace(needle, '  maincontrol () ;\n  if (siglum_checkpoint_is_paused) return;\n  finalcleanup () ;', 1)
        needle = '#include "pdftexd.h"'
        assert text.count(needle) == 1
        text = text.replace(needle, needle + '\nextern int siglum_checkpoint_is_paused;\nextern int siglum_checkpoint_resume_enter;\n', 1)
        text += '''
/* Only call for a paused instance with its complete heap and JS FS intact. */
int siglum_checkpoint_resume(void)
{
    if (!siglum_checkpoint_is_paused) return -1;
    siglum_checkpoint_is_paused = 0;
    siglum_checkpoint_resume_enter = 1;
    maincontrol();
    if (siglum_checkpoint_is_paused) return 1;
    finalcleanup();
    closefilesandterminate();
    fflush(stdout);
    readyalready = 0;
    return (history != 0 && history != 1) ? 2 : 0;
}
'''
    (args.out / name).write_text(text)
(args.out / 'siglum_checkpoint.inc').write_text((here / 'siglum_checkpoint.inc').read_text())
(args.out / 'source-sha256.json').write_text(json.dumps(hashes, indent=2) + '\n')
print(json.dumps(hashes))
