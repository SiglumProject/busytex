#!/usr/bin/env python3
"""Compile two patched generated-C objects, then strictly relink existing libs."""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys

work = Path('/work')
out = Path('/out')
generated = work / 'build/wasm/texlive/texk/web2c'
makefile = (work / 'Makefile').read_text()
def make_words(name):
    match = re.search(r'^' + re.escape(name) + r'\s*[:?]?=\s*(.+)$', makefile, re.M)
    if not match:
        raise RuntimeError('Missing ' + name)
    return match.group(1).split()

flags_expr = '$(DEFS) $(DEFAULT_INCLUDES) $(INCLUDES) $(pdftex_CPPFLAGS) $(CPPFLAGS) $(AM_CFLAGS) $(CFLAGS)'
flags = subprocess.check_output([
    'make', '-s', '--no-print-directory', '-o', 'Makefile', '-o', 'config.status',
    '--eval=checkpoint-print-flags:;@echo ' + flags_expr,
    'checkpoint-print-flags',
], cwd=generated, text=True)
flags = shlex.split(flags.strip())
defines = ['-Dmain=busymain_pdftex'] + [
    '-D' + symbol + '=busypdftex_' + symbol
    for symbol in dict.fromkeys(make_words('PDFTEX_REDEFINE') + make_words('SYNCTEX_REDEFINE'))
]
commands = []
control_only = '--control-only' in sys.argv
prototype_only = '--prototype-only' in sys.argv
if control_only and prototype_only:
    raise RuntimeError('Choose one build variant')
for stem in (() if control_only else ('pdftex0', 'pdftexini')):
    command = ['emcc', *defines, *flags, '-I' + str(generated), '-I/out',
               '-c', str(out / (stem + '.c')), '-o', str(out / ('pdftex-' + stem + '.o'))]
    commands.append(command)
    print('Compiling ' + stem, flush=True)
    subprocess.run(command, cwd=generated, check=True)

command = ['emcc', '-Oz', '-DBUSYTEX_PDFTEX', '-c', '/work/busytex.c', '-o', '/out/busytex-pdftex.o']
commands.append(command)
subprocess.run(command, check=True)

command = ['emcc', '-O2', '-I/out', '-c', '/out/siglum_profile_wrappers.c', '-o', '/out/siglum_profile_wrappers.o']
commands.append(command)
subprocess.run(command, check=True)

# Native entrypoint names follow the exact BusyTeX symbol-renaming list rather
# than assuming combined/split builds use the same external names.
renamed = set(make_words('PDFTEX_REDEFINE') + make_words('SYNCTEX_REDEFINE'))
setter_signatures = [
    ('pdfmapfile', 'integer value', 'value', 1),
    ('pdfmapline', 'integer value', 'value', 1),
    ('pdfmaplinesp', 'void', '', 1),
    ('deftounicode', 'strnumber glyph, strnumber unicode', 'glyph, unicode', 2),
]
setter_symbols = []
wrapper_source = ['#define EXTERN extern', '#include "pdftexd.h"', '#include "siglum_preview.h"']
for name, declaration, arguments, event in setter_signatures:
    symbol = 'busypdftex_' + name if name in renamed else name
    setter_symbols.append(symbol)
    wrapper_source += ['extern void __real_' + symbol + '(' + declaration + ');',
        'void __wrap_' + symbol + '(' + declaration + ') {',
        '    siglum_preview_resource_event(' + str(event) + ');',
        '    __real_' + symbol + '(' + arguments + ');', '}']
(out / 'siglum_preview_setter_wrappers.c').write_text('\n'.join(wrapper_source) + '\n')
command = ['emcc', *defines, *flags, '-I' + str(generated), '-I/out', '-c',
           '/out/siglum_preview_setter_wrappers.c', '-o', '/out/siglum_preview_setter_wrappers.o']
commands.append(command)
subprocess.run(command, cwd=generated, check=True)
objects = []
control_objects = []
for name in make_words('OBJ_PDFTEX'):
    control_objects.append(str(generated / name))
    if name in ('pdftex-pdftex0.o', 'pdftex-pdftexini.o'):
        objects.append(str(out / name))
    else:
        objects.append(str(generated / name))
objects += [str(out / 'siglum_profile_wrappers.o')]
objects += [str(out / 'siglum_preview_setter_wrappers.o')]
objects += [str(work / 'build/wasm' / name) for name in (
    'texlive/libs/libpng/libpng.a', 'texlive/libs/pplib/libpplib.a',
    'texlive/libs/zlib/libz.a', 'texlive/libs/zziplib/libzzip.a',
    'texlive/libs/xpdf/libxpdf.a', 'texlive/texk/kpathsea/.libs/libkpathsea.a',
)]
objects += [str(work / 'build/wasm/texlive/texk/kpathsea' / name)
            for name in make_words('OBJ_KPATHSEA')]
control_objects += objects[len(make_words('OBJ_PDFTEX')):]
exports = [
    '_main', '_flush_streams', '_malloc', '_free',
    '_siglum_checkpoint_arm', '_siglum_checkpoint_disarm', '_siglum_checkpoint_resume',
    '_siglum_checkpoint_paused', '_siglum_checkpoint_prepare_snapshot',
    '_siglum_checkpoint_refresh_inputs', '_siglum_checkpoint_line',
    '_siglum_checkpoint_next_line', '_siglum_checkpoint_total_pages',
    '_siglum_checkpoint_input_ptr', '_siglum_checkpoint_input_index',
    '_siglum_checkpoint_input_state', '_siglum_checkpoint_buffer_loc',
    '_siglum_checkpoint_buffer_limit', '_siglum_checkpoint_buffer_start',
    '_siglum_checkpoint_buffer', '_siglum_checkpoint_input_stack',
    '_siglum_checkpoint_filename', '_siglum_checkpoint_input_fd',
    '_siglum_checkpoint_input_offset',
    '_siglum_preview_api_version', '_siglum_preview_arm', '_siglum_preview_disarm', '_siglum_preview_paused',
    '_siglum_preview_continue', '_siglum_preview_page', '_siglum_preview_width_sp',
    '_siglum_preview_continue_until_page',
    '_siglum_preview_height_sp', '_siglum_preview_guard_flags',
    '_siglum_preview_content_length', '_siglum_preview_content_data',
    '_siglum_preview_resources_length', '_siglum_preview_resources_data',
    '_siglum_preview_font_count', '_siglum_preview_font_index',
    '_siglum_preview_font_max_index', '_siglum_preview_font_info',
    '_siglum_preview_font_string', '_siglum_preview_font_bits',
    '_siglum_preview_font_attr_length', '_siglum_preview_font_attr_data',
    '_siglum_preview_resource_guard_api_version', '_siglum_preview_guard_object',
    '_siglum_preview_guard_object_status', '_siglum_preview_resource_events',
    '_siglum_preview_font_global',
    '_siglum_finalize_api_version', '_siglum_finalize_enable', '_siglum_finalize_paused',
    '_siglum_finalize_request_count', '_siglum_finalize_request_name',
    '_siglum_finalize_request_kind', '_siglum_finalize_request_overflow',
    '_siglum_finalize_unsupported_count', '_siglum_finalize_resume', '_siglum_checkpoint_finish',
    '_siglum_profile_enable', '_siglum_profile_reset', '_siglum_profile_get_time',
    '_siglum_profile_get_count', '_siglum_profile_get_bytes', '_siglum_profile_phase_count',
]
exports.append('_siglum_configure_default_map')
runtime = ['callMain', 'FS', 'ENV', 'LZ4', 'PATH', 'UTF8ToString', 'stringToUTF8',
           'lengthBytesUTF8', 'stackSave', 'stackRestore', 'NODEFS']
link_flags = [
    '--static', '-static', '-static-libstdc++', '-static-libgcc',
    '-Wl,--wrap=deflate', '-Wl,--wrap=fwrite',
    *['-Wl,--wrap=' + symbol for symbol in setter_symbols],
    '-Wl,-error-limit=0', '-sINITIAL_MEMORY=16777216', '-sMAXIMUM_MEMORY=268435456',
    '-sSTACK_SIZE=5242880', '-sALLOW_MEMORY_GROWTH=1', '-sEXIT_RUNTIME=0',
    '-sINVOKE_RUN=0', '-sASSERTIONS=0', '-sFORCE_FILESYSTEM=1', '-sLZ4=1',
    '-sMODULARIZE=1', '-sEXPORT_NAME=pdftex', '-lnodefs.js',
    '-sEXPORTED_RUNTIME_METHODS=' + json.dumps(runtime),
]
if not control_only:
    command = ['em++', '-o', '/out/pdftex.js', '/out/busytex-pdftex.o', *objects,
               *link_flags, '-sEXPORTED_FUNCTIONS=' + json.dumps(exports)]
    commands.append(command)
    print('Strictly linking checkpoint pdfTeX', flush=True)
    subprocess.run(command, cwd=generated, check=True)
control_out = out / 'control'
if not prototype_only:
    control_out.mkdir(exist_ok=True)
    command = ['em++', '-o', '/out/control/pdftex.js', '/out/busytex-pdftex.o', *control_objects,
               *link_flags, '-sEXPORTED_FUNCTIONS=' + json.dumps(['_main', '_flush_streams', '_malloc', '_free'])]
    commands.append(command)
    print('Strictly linking unmodified-object control pdfTeX', flush=True)
    subprocess.run(command, cwd=generated, check=True)
version = subprocess.check_output(['emcc', '--version'], text=True)
if not control_only:
    (out / 'build-commands.json').write_text(json.dumps(commands, indent=2) + '\n')
    (out / 'toolchain.txt').write_text(version)
    (out / 'artifact-sha256.json').write_text(json.dumps({
        name: hashlib.sha256((out / name).read_bytes()).hexdigest()
        for name in ('pdftex.js', 'pdftex.wasm')
    }, indent=2) + '\n')
    (out / 'patched-source-sha256.json').write_text(json.dumps({
        name: hashlib.sha256((out / name).read_bytes()).hexdigest()
        for name in ('pdftex0.c', 'pdftexini.c', 'siglum_checkpoint.inc',
                     'siglum_preview.inc', 'siglum_preview_layout.h', 'siglum_preview_setter_wrappers.c')
    }, indent=2) + '\n')
if not prototype_only:
    (control_out / 'build-command.json').write_text(json.dumps(command, indent=2) + '\n')
    (control_out / 'toolchain.txt').write_text(version)
    (control_out / 'artifact-sha256.json').write_text(json.dumps({
        name: hashlib.sha256((control_out / name).read_bytes()).hexdigest()
        for name in ('pdftex.js', 'pdftex.wasm')
    }, indent=2) + '\n')
    (control_out / 'original-object-sha256.json').write_text(json.dumps({
        str(Path(path).relative_to(work)): hashlib.sha256(Path(path).read_bytes()).hexdigest()
        for path in control_objects
    }, indent=2) + '\n')
print('Build complete', flush=True)
