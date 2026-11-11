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
if not control_only:
    # The synchronization unit, with one function added that says where its state is.
    # Printing the flags through the shell loses the quotes of the one header name.
    synctex_flags = ['-DSYNCTEX_ENGINE_H="synctex-pdftex.h"' if flag.startswith('-DSYNCTEX_ENGINE_H=') else flag
                     for flag in flags]
    assert synctex_flags != flags
    command = ['emcc', *defines, *synctex_flags, '-I' + str(generated), '-I/out',
               '-I' + str(work / 'source/texlive/texk/web2c/synctexdir'),
               '-c', str(out / 'synctex.c'), '-o', str(out / 'pdftex-synctex.o')]
    commands.append(command)
    print('Compiling synctex', flush=True)
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
# State comparison (see siglum_state_* in siglum_preview.inc): memory given back
# to the allocator is cleared, so that dead bytes never differ between two runs,
# and the compressor's blocks are known, since they hold only output state.
wrapper_source += [r'''
#include <stdlib.h>
#include <string.h>
#include <malloc.h>
/* The C library's free and realloc are weak: these take their place and reach
 * the allocator through its builtin names. */
extern void emscripten_builtin_free(void *);
extern void *emscripten_builtin_malloc(size_t);
void free(void *pointer)
{
    if (pointer) memset(pointer, 0, malloc_usable_size(pointer));
    emscripten_builtin_free(pointer);
}
void *realloc(void *pointer, size_t size)
{
    void *moved; size_t old;
    if (!pointer) return emscripten_builtin_malloc(size);
    if (!size) { free(pointer); return NULL; }
    old = malloc_usable_size(pointer);
    moved = emscripten_builtin_malloc(size);
    if (!moved) return NULL;
    memcpy(moved, pointer, old < size ? old : size);
    free(pointer);
    return moved;
}
#define SIGLUM_ZLIB_BLOCKS 32
static struct { void *pointer; size_t size; } siglum_zlib_blocks[SIGLUM_ZLIB_BLOCKS];
extern void *__real_zcalloc(void *, unsigned, unsigned);
extern void __real_zcfree(void *, void *);
void *__wrap_zcalloc(void *opaque, unsigned items, unsigned size)
{
    void *pointer = __real_zcalloc(opaque, items, size); int i;
    if (pointer) for (i = 0; i < SIGLUM_ZLIB_BLOCKS; i++) if (!siglum_zlib_blocks[i].pointer) {
        siglum_zlib_blocks[i].pointer = pointer; siglum_zlib_blocks[i].size = (size_t)items * size; break;
    }
    return pointer;
}
void __wrap_zcfree(void *opaque, void *pointer)
{
    int i;
    for (i = 0; i < SIGLUM_ZLIB_BLOCKS; i++) if (siglum_zlib_blocks[i].pointer == pointer) { siglum_zlib_blocks[i].pointer = NULL; siglum_zlib_blocks[i].size = 0; }
    __real_zcfree(opaque, pointer);
}
int siglum_state_zlib_block(int index, int which)
{
    if (index < 0 || index >= SIGLUM_ZLIB_BLOCKS) return -1;
    return which ? (int)siglum_zlib_blocks[index].size : (int)(size_t)siglum_zlib_blocks[index].pointer;
}
/* The PDF writer's compression stream is the one deflate stream that lives in
 * static data; its output buffer is private to that unit and is found through
 * the stream (the writer points it at the start of a 32768-byte buffer). */
#include <zlib.h>
#define SIGLUM_ZIP_BUFFER 32768
extern unsigned char __heap_base;
static z_streamp siglum_zip_stream = NULL;
extern int __real_deflateInit_(z_streamp, int, const char *, int);
int __wrap_deflateInit_(z_streamp stream, int level, const char *version, int size)
{
    if (!siglum_zip_stream && (unsigned char *)stream < &__heap_base) siglum_zip_stream = stream;
    return __real_deflateInit_(stream, level, version, size);
}
int siglum_state_zlib_output(int which)
{
    z_streamp stream = siglum_zip_stream;
    if (!stream) return 0;
    switch (which) {
    case 0: return (int)(size_t)stream;
    case 1: return (int)sizeof(*stream);
    case 2: return stream->next_out && stream->avail_out <= SIGLUM_ZIP_BUFFER
        ? (int)(size_t)(stream->next_out + stream->avail_out - SIGLUM_ZIP_BUFFER) : 0;
    case 3: return SIGLUM_ZIP_BUFFER;
    default: return -1;
    }
}
''']
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
    elif name == 'synctexdir/pdftex-synctex.o':
        objects.append(str(out / 'pdftex-synctex.o'))
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
    '_siglum_state_region', '_siglum_state_region_name', '_siglum_state_region_address', '_siglum_state_region_length',
    '_siglum_state_zlib_block', '_siglum_state_zlib_output', '_siglum_state_api_version', '_siglum_state_objentry_size', '_siglum_state_free_single_count', '_siglum_state_mark_free', '_siglum_state_memmin', '_siglum_state_memmax',
    '_siglum_state_node_bounds', '_siglum_state_node_bounds_bits', '_siglum_state_lomemmax', '_siglum_state_himemmin', '_siglum_state_rover', '_siglum_state_mem',
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
    '-Wl,--wrap=zcalloc', '-Wl,--wrap=zcfree', '-Wl,--wrap=deflateInit_',
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
    # For local study only: where every data symbol ends up.
    if os.environ.get('SIGLUM_LINK_MAP'): command.append('-Wl,--Map=/out/pdftex.map')
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
        for name in ('pdftex0.c', 'pdftexini.c', 'synctex.c', 'siglum_checkpoint.inc',
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
