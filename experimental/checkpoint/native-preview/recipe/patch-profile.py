#!/usr/bin/env python3
"""Generate a separate profiling variant; never edit validated generated C."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('--generated', type=Path, required=True)
parser.add_argument('--base-recipe', type=Path, required=True)
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
here = Path(__file__).resolve().parent
subprocess.run(['python3', str(args.base_recipe / 'patch-generated.py'),
                '--generated', str(args.generated), '--out', str(args.out)], check=True)


def body_extent(source, name):
    match = re.search(r'\b' + re.escape(name) + r'\s*\([^;{}]*\)\s*\n\{', source)
    if not match:
        raise RuntimeError('Missing generated definition: ' + name)
    start = source.index('{', match.start())
    depth = 0
    i = start
    while i < len(source):
        if source.startswith('//', i):
            i = source.index('\n', i)
            continue
        if source.startswith('/*', i):
            i = source.index('*/', i + 2) + 2
            continue
        if source[i] in ('"', "'"):
            delimiter = source[i]
            i += 1
            while i < len(source):
                if source[i] == '\\':
                    i += 2
                elif source[i] == delimiter:
                    i += 1
                    break
                else:
                    i += 1
            continue
        if source[i] == '{':
            depth += 1
        elif source[i] == '}':
            depth -= 1
            if depth == 0:
                return start, i
        i += 1
    raise RuntimeError('Unbalanced generated function: ' + name)


zero = (args.out / 'pdftex0.c').read_text()
zero = zero.replace('#include "pdftexd.h"',
                    '#include "pdftexd.h"\n#include "siglum_profile.h"\n#include "siglum_profile.inc"', 1)

# High-level font phases are intentionally inclusive of nested deflate/I/O.
for before, after in [
    ('dopdffont ( k , f ) ;', 'SIGLUM_PROFILE_CALL(SIGLUM_PHASE_FONT_DICTIONARIES, dopdffont(k, f));'),
    ('writefontstuff () ;', 'SIGLUM_PROFILE_CALL(SIGLUM_PHASE_FONT_STREAMS, writefontstuff());'),
]:
    assert zero.count(before) == 1, before
    zero = zero.replace(before, after)

start, end = body_extent(zero, 'zpdfshipout')
body = zero[start + 1:end]
assert not re.search(r'\breturn\b', body), 'Shipout gained an early return; audit timer exits'
assert body.count('pdfvlistout () ;') == 1
assert body.count('pdfhlistout () ;') == 1
body = body.replace('pdfvlistout () ;', 'SIGLUM_PROFILE_CALL(SIGLUM_PHASE_PAGE_LISTS, pdfvlistout());')
body = body.replace('pdfhlistout () ;', 'SIGLUM_PROFILE_CALL(SIGLUM_PHASE_PAGE_LISTS, pdfhlistout());')
zero = zero[:start + 1] + '\n  double siglum_shipout_started = siglum_profile_begin(SIGLUM_PHASE_SHIPOUT);\n' + body + \
       '\n  siglum_profile_end(SIGLUM_PHASE_SHIPOUT, siglum_shipout_started);\n' + zero[end:]

start, end = body_extent(zero, 'pdfflush')
body = zero[start + 1:end]
assert not re.search(r'\breturn\b', body)
zero = zero[:start + 1] + '\n  double siglum_flush_started = siglum_profile_begin(SIGLUM_PHASE_PDF_FLUSH);\n' + body + \
       '\n  siglum_profile_end(SIGLUM_PHASE_PDF_FLUSH, siglum_flush_started);\n' + zero[end:]
(args.out / 'pdftex0.c').write_text(zero)

ini = (args.out / 'pdftexini.c').read_text()
ini = ini.replace('#include "pdftexd.h"', '#include "pdftexd.h"\n#include "siglum_profile.h"', 1)
for function, phase in [('maincontrol', 'MAINCONTROL'), ('finalcleanup', 'FINALCLEANUP'),
                        ('closefilesandterminate', 'CLOSEFILES')]:
    pattern = r'\b' + function + r'\s*\(\s*\)\s*;'
    ini, count = re.subn(pattern, 'SIGLUM_PROFILE_CALL(SIGLUM_PHASE_' + phase + ', ' + function + '());', ini)
    assert count == 2, (function, count)

start, end = body_extent(ini, 'loadfmtfile')
ini = ini[:end + 1] + '''
static boolean siglum_profile_loadfmtfile(void)
{
    double started = siglum_profile_begin(SIGLUM_PHASE_FORMAT_LOAD);
    boolean result = loadfmtfile();
    siglum_profile_end(SIGLUM_PHASE_FORMAT_LOAD, started);
    return result;
}
''' + ini[end + 1:]
assert ini.count('if ( ! loadfmtfile () )') == 1
ini = ini.replace('if ( ! loadfmtfile () )', 'if ( ! siglum_profile_loadfmtfile() )')

needle = '    siglum_checkpoint_is_paused = 0;\n    siglum_checkpoint_resume_enter = 1;'
assert ini.count(needle) == 1
ini = ini.replace(needle, '    double siglum_resume_started;\n    siglum_profile_reset();\n    siglum_resume_started = siglum_profile_begin(SIGLUM_PHASE_RESUME_TOTAL);\n' + needle)
needle = '    if (siglum_checkpoint_is_paused) return 1;'
assert ini.count(needle) == 1
ini = ini.replace(needle, '''    if (siglum_checkpoint_is_paused) {
        siglum_profile_end(SIGLUM_PHASE_RESUME_TOTAL, siglum_resume_started);
        return 1;
    }''')
needle = '    return (history != 0 && history != 1) ? 2 : 0;'
assert ini.count(needle) == 1
ini = ini.replace(needle, '    siglum_profile_end(SIGLUM_PHASE_RESUME_TOTAL, siglum_resume_started);\n' + needle)
(args.out / 'pdftexini.c').write_text(ini)

for name in ('siglum_profile.h', 'siglum_profile.inc', 'siglum_profile_wrappers.c'):
    (args.out / name).write_bytes((here / name).read_bytes())
names = ['pdftex0.c', 'pdftexini.c', 'siglum_checkpoint.inc', 'siglum_profile.h',
         'siglum_profile.inc', 'siglum_profile_wrappers.c']
(args.out / 'profile-source-sha256.json').write_text(json.dumps({
    name: hashlib.sha256((args.out / name).read_bytes()).hexdigest() for name in names
}, indent=2) + '\n')
print('Prepared isolated native phase profiling sources')
