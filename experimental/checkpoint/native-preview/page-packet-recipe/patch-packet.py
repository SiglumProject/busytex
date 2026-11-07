#!/usr/bin/env python3
"""Capture exact page operators in another isolated native variant."""
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
subprocess.run(['python3', str(here / 'derive-layout.py'), '--generated', str(args.generated),
                '--out', str(args.out)], check=True)
subprocess.run(['python3', str(here.parent / 'font-yield-recipe/patch-finalize.py'),
                '--generated', str(args.generated), '--base-recipe', str(args.base_recipe),
                '--out', str(args.out)], check=True)

def body_extent(source, name):
    match = re.search(r'\b' + re.escape(name) + r'\s*\([^;{}]*\)\s*\n\{', source)
    assert match, 'Missing generated definition: ' + name
    start = source.index('{', match.start())
    depth, i = 0, start
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
        if source[i] == '{': depth += 1
        elif source[i] == '}':
            depth -= 1
            if depth == 0: return start, i
        i += 1
    raise RuntimeError('Unbalanced function: ' + name)

zero = (args.out / 'pdftex0.c').read_text()
zero = zero.replace('#include "siglum_finalize.inc"',
    '#include "siglum_finalize.inc"\n#include "siglum_preview.h"\n#include "siglum_preview.inc"', 1)
needle = '  lab60: if (siglum_checkpoint_poll()) return;'
assert zero.count(needle) == 1
zero = zero.replace(needle, '  lab60: if (siglum_preview_poll()) return;\n  if (siglum_checkpoint_poll()) return;', 1)

start, end = body_extent(zero, 'pdfflush')
zero = zero[:start + 1] + '\n  siglum_preview_before_flush();\n' + zero[start + 1:]

start, end = body_extent(zero, 'zpdfosprepareobj')
zero = zero[:start + 1] + '\n  siglum_preview_before_object_write(i);\n' + zero[start + 1:]

start, end = body_extent(zero, 'zliteral')
zero = zero[:start + 1] + '\n  siglum_preview_literal_event(s);\n' + zero[start + 1:]

start, end = body_extent(zero, 'zpdfshipout')
body = zero[start + 1:end]
body = '\n  int siglum_capture_this_page = siglum_preview_should_capture(shippingpage);\n' + body
needle = '  pdfbeginstream () ;'
assert body.count(needle) == 1
body = body.replace(needle, needle + '\n  if (siglum_capture_this_page) siglum_preview_begin(&siglum_preview_content);', 1)
needle = '  pdfendstream () ;'
assert body.count(needle) == 1
body = body.replace(needle, '  if (siglum_capture_this_page) siglum_preview_end(&siglum_preview_content, SIGLUM_PREVIEW_CONTENT_MAX);\n' + needle, 1)
needle = '  pdfbegindict ( pdflastresources , 1 ) ;'
assert body.count(needle) == 1
body = body.replace(needle, needle + '\n  if (siglum_capture_this_page) siglum_preview_begin(&siglum_preview_resources);', 1)
needle = '  pdfenddict () ;\n  flushlist ( pdffontlist ) ;'
assert body.count(needle) == 1
body = body.replace(needle, '''  if (siglum_capture_this_page) {
    siglum_preview_end(&siglum_preview_resources, SIGLUM_PREVIEW_RESOURCES_MAX);
    siglum_preview_page_metadata();
  }
''' + needle, 1)
body += '\n  if (siglum_capture_this_page) siglum_preview_shipout_done();\n'
zero = zero[:start + 1] + body + zero[end:]
(args.out / 'pdftex0.c').write_text(zero)

ini = (args.out / 'pdftexini.c').read_text()
ini = ini.replace('#include "siglum_finalize.h"', '#include "siglum_finalize.h"\n#include "siglum_preview.h"', 1)
needle = '  if (siglum_finalize_prepare()) return;'
assert ini.count(needle) == 1
ini = ini.replace(needle, '  if (siglum_preview_after_maincontrol()) return;\n' + needle, 1)
needle = '    if (siglum_finalize_prepare()) {'
assert ini.count(needle) == 1
ini = ini.replace(needle, '''    if (siglum_preview_after_maincontrol()) {
        siglum_profile_end(SIGLUM_PHASE_RESUME_TOTAL, siglum_resume_started);
        return 4;
    }
''' + needle, 1)
ini += '''
/* Continue a page handoff without changing source, input positions or heap. */
int siglum_preview_continue(void)
{
    int done = siglum_preview_enter_continue();
    if (done < 0) return -1;
    if (!done) {
        siglum_checkpoint_resume_enter = 1;
        SIGLUM_PROFILE_CALL(SIGLUM_PHASE_MAINCONTROL, maincontrol());
        if (siglum_checkpoint_is_paused) return 1;
    }
    if (siglum_finalize_prepare()) return 3;
    SIGLUM_PROFILE_CALL(SIGLUM_PHASE_FINALCLEANUP, finalcleanup());
    SIGLUM_PROFILE_CALL(SIGLUM_PHASE_CLOSEFILES, closefilesandterminate());
    fflush(stdout);
    readyalready = 0;
    return (history != 0 && history != 1) ? 2 : 0;
}

/* Yield after another completed page so the worker can service a new revision
 * between chunks. The same engine and original hot checkpoint remain in use.
 */
int siglum_preview_continue_until_page(int page)
{
    int done = siglum_preview_enter_next(page);
    if (done < 0) return -1;
    if (!done) {
        siglum_checkpoint_resume_enter = 1;
        SIGLUM_PROFILE_CALL(SIGLUM_PHASE_MAINCONTROL, maincontrol());
        if (siglum_checkpoint_is_paused) return 1;
        if (siglum_preview_after_maincontrol()) return 4;
    }
    if (siglum_finalize_prepare()) return 3;
    SIGLUM_PROFILE_CALL(SIGLUM_PHASE_FINALCLEANUP, finalcleanup());
    SIGLUM_PROFILE_CALL(SIGLUM_PHASE_CLOSEFILES, closefilesandterminate());
    fflush(stdout);
    readyalready = 0;
    return (history != 0 && history != 1) ? 2 : 0;
}
'''
ini = ini.replace('extern int siglum_checkpoint_is_paused;',
    (here / 'siglum_default_map.inc').read_text() + '\nextern int siglum_checkpoint_is_paused;', 1)
needle = '    pdfinitmapfile ( "pdftex.map" ) ;'
assert ini.count(needle) == 1
ini = ini.replace(needle, '    pdfinitmapfile ( siglum_default_map_name("pdftex.map") ) ;', 1)
(args.out / 'pdftexini.c').write_text(ini)
for name in ('siglum_preview.h', 'siglum_preview.inc'):
    (args.out / name).write_bytes((here / name).read_bytes())
names = ['pdftex0.c', 'pdftexini.c', 'siglum_checkpoint.inc', 'siglum_finalize.h',
         'siglum_finalize.inc', 'siglum_preview.h', 'siglum_preview.inc', 'siglum_preview_layout.h']
(args.out / 'packet-source-sha256.json').write_text(json.dumps({
    name: hashlib.sha256((args.out / name).read_bytes()).hexdigest() for name in names
}, indent=2) + '\n')
print('Prepared isolated exact-page content capture and forward continuation')
