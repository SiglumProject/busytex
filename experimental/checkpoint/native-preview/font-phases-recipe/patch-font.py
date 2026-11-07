#!/usr/bin/env python3
"""Prepare an isolated font/map profiling and optimization comparison."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('--source', type=Path, required=True)
parser.add_argument('--base-recipe', type=Path, required=True)
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
here = Path(__file__).resolve().parent
generated = args.source / 'build/wasm/texlive/texk/web2c'
subprocess.run(['python3', str(here.parent / 'recipe/patch-profile.py'), '--generated', str(generated),
                '--base-recipe', str(args.base_recipe), '--out', str(args.out)], check=True)
originals = {}
for name in ('writet1.c', 'mapfile.c'):
    path = args.source / 'source/texlive/texk/web2c/pdftexdir' / name
    source = path.read_text(); originals[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    assert source.count('#include "ptexlib.h"') == 1
    source = source.replace('#include "ptexlib.h"', '#include "ptexlib.h"\n#include "siglum_font_profile.h"', 1)
    if name == 'writet1.c':
        source = source.replace('#include "siglum_font_profile.h"',
            '#include "siglum_font_profile.h"\n#include "siglum_font_profile.inc"', 1)
        needle = 'static boolean t1_open_fontfile(const char *open_name_prefix)\n{'
        assert source.count(needle) == 1
        source = source.replace(needle, needle + '\n    double siglum_font_open_started = siglum_font_profile_begin();', 1)
        needle = '    return true;                /* font file found */'
        assert source.count(needle) == 1
        source = source.replace(needle, '    siglum_font_profile_end(SIGLUM_FONT_OPEN, siglum_font_open_started);\n' + needle, 1)
        start = source.index('void writet1(fd_entry *fd)')
        end = source.index('\nvoid t1_free(void)', start)
        body = source[start:end]
        calls = [('t1_include', 'FULL_INCLUDE'), ('t1_subset_ascii_part', 'ASCII'),
                 ('t1_start_eexec', 'EEXEC_START'), ('t1_read_subrs', 'SUBRS'),
                 ('t1_subset_charstrings', 'CHARSTRINGS'), ('t1_subset_end', 'SUBSET_END')]
        for function, phase in calls:
            needle = function + '();'
            assert body.count(needle) == 1
            body = body.replace(needle, 'SIGLUM_FONT_PROFILE_CALL(SIGLUM_FONT_' + phase + ', ' + needle[:-1] + ');')
        body, count = re.subn(r't1_close_font_file\(([^;]*)\);',
            r'SIGLUM_FONT_PROFILE_CALL(SIGLUM_FONT_CLOSE, t1_close_font_file(\1));', body)
        assert count == 2
        source = source[:start] + body + source[end:]
    else:
        start = source.index('void fm_read_info(void)\n{')
        end = source.index('\nstatic fmentryptr fmlookup(', start)
        body = source[start:end]
        assert body.count('return;') == 2
        body = body.replace('void fm_read_info(void)\n{',
            'void fm_read_info(void)\n{\n    double siglum_map_started = siglum_font_profile_begin();', 1)
        body = body.replace('return;', '{ siglum_font_profile_end(SIGLUM_FONT_MAP_READ, siglum_map_started); return; }')
        source = source[:start] + body + source[end:]
    (args.out / name).write_text(source)

zero = (args.out / 'pdftex0.c').read_text()
zero = zero.replace('#include "siglum_profile.h"', '#include "siglum_profile.h"\n#include "siglum_font_profile.h"', 1)
(args.out / 'pdftex0.c').write_text(zero)
profile = (args.out / 'siglum_profile.inc').read_text()
needle = 'void siglum_profile_reset(void)\n{'
assert profile.count(needle) == 1
profile = profile.replace(needle, needle + '\n    siglum_font_profile_reset();', 1)
(args.out / 'siglum_profile.inc').write_text(profile)
for name in ('siglum_font_profile.h', 'siglum_font_profile.inc'):
    (args.out / name).write_bytes((here / name).read_bytes())
(args.out / 'font-original-source-sha256.json').write_text(json.dumps(originals, indent=2) + '\n')
print('Prepared isolated Type1/map phases; original archive and sources untouched')
