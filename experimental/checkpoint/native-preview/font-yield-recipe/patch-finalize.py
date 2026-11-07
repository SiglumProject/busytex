#!/usr/bin/env python3
"""Add an opt-in post-layout handoff to an isolated profiling source copy."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('--generated', type=Path, required=True)
parser.add_argument('--base-recipe', type=Path, required=True)
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
here = Path(__file__).resolve().parent
subprocess.run(['python3', str(here.parent / 'recipe/patch-profile.py'),
                '--generated', str(args.generated), '--base-recipe', str(args.base_recipe),
                '--out', str(args.out)], check=True)
zero = (args.out / 'pdftex0.c').read_text()
needle = '#include "siglum_profile.inc"'
assert zero.count(needle) == 1
zero = zero.replace(needle, needle + '\n#include "siglum_finalize.h"\n#include "siglum_finalize.inc"', 1)
(args.out / 'pdftex0.c').write_text(zero)

ini = (args.out / 'pdftexini.c').read_text()
ini = ini.replace('#include "siglum_profile.h"', '#include "siglum_profile.h"\n#include "siglum_finalize.h"', 1)
needle = '  if (siglum_checkpoint_is_paused) return;'
assert ini.count(needle) == 1
ini = ini.replace(needle, needle + '\n  if (siglum_finalize_prepare()) return;', 1)
needle = '    SIGLUM_PROFILE_CALL(SIGLUM_PHASE_FINALCLEANUP, finalcleanup());'
assert ini.count(needle) == 1
ini = ini.replace(needle, '''    if (siglum_finalize_prepare()) {
        siglum_profile_end(SIGLUM_PHASE_RESUME_TOTAL, siglum_resume_started);
        return 3;
    }
''' + needle, 1)
ini += '''
/* Only a post-maincontrol handoff may enter here. Input processing has ended;
 * the host may add files, but must not replace source or restore a heap before
 * finishing. Any thrown compiler error poisons this instance for further use.
 */
int siglum_finalize_resume(void)
{
    if (!siglum_finalize_is_paused) return -1;
    siglum_finalize_is_paused = 0;
    SIGLUM_PROFILE_CALL(SIGLUM_PHASE_FINALCLEANUP, finalcleanup());
    SIGLUM_PROFILE_CALL(SIGLUM_PHASE_CLOSEFILES, closefilesandterminate());
    fflush(stdout);
    readyalready = 0;
    return (history != 0 && history != 1) ? 2 : 0;
}
'''
(args.out / 'pdftexini.c').write_text(ini)
for name in ('siglum_finalize.h', 'siglum_finalize.inc'):
    (args.out / name).write_bytes((here / name).read_bytes())
names = ['pdftex0.c', 'pdftexini.c', 'siglum_checkpoint.inc', 'siglum_finalize.h',
         'siglum_finalize.inc', 'siglum_profile.h', 'siglum_profile.inc', 'siglum_profile_wrappers.c']
(args.out / 'finalize-source-sha256.json').write_text(json.dumps({
    name: hashlib.sha256((args.out / name).read_bytes()).hexdigest() for name in names
}, indent=2) + '\n')
print('Prepared isolated post-layout font-finalization handoff')
