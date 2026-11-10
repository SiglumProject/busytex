#!/usr/bin/env python3
"""Build the performance variants using only this tree's freshly built objects.

Run inside the pinned compiler container after make native/wasm/wasm-pdftex.
The container owns /out; no object/archive inputs from earlier experiments.
"""
import argparse, hashlib, json, os, re, shlex, shutil, subprocess
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--work', type=Path, default=Path('/work'))
parser.add_argument('--output', type=Path, default=Path('/work/build/performance'))
a = parser.parse_args()
work = a.work.resolve()
out = a.output.resolve()
recipe = work / 'experimental/checkpoint'
generated = work / 'build/wasm/texlive/texk/web2c'
commands = []

def run(argv, cwd=work):
    commands.append({'argv': [str(x) for x in argv], 'cwd': str(cwd)})
    print('+', shlex.join([str(x) for x in argv]), flush=True)
    subprocess.run([str(x) for x in argv], cwd=cwd, check=True)

def activate(path):
    path.mkdir(parents=True, exist_ok=True)
    alias = Path('/out')
    if alias.is_symlink(): alias.unlink()
    elif alias.exists(): raise RuntimeError('/out must be unused in this build container')
    alias.symlink_to(path, target_is_directory=True)

def make_flags(directory, expression):
    return shlex.split(subprocess.check_output(['make', '-s', '--no-print-directory', '-o', 'Makefile', '-o', 'config.status', '--eval=siglum-print-flags:;@echo ' + expression, 'siglum-print-flags'], cwd=directory, text=True).strip())

def link_options(args, exports=(), methods=()):
    result = []
    for arg in args:
        if arg.startswith('-sEXPORTED_FUNCTIONS='):
            arg = '-sEXPORTED_FUNCTIONS=' + json.dumps(list(dict.fromkeys(json.loads(arg.split('=', 1)[1]) + list(exports))))
        if arg.startswith('-sEXPORTED_RUNTIME_METHODS='):
            arg = '-sEXPORTED_RUNTIME_METHODS=' + json.dumps(list(dict.fromkeys(json.loads(arg.split('=', 1)[1]) + list(methods))))
        if arg.startswith('-sASSERTIONS='): arg = '-sASSERTIONS=0'
        if arg.startswith('-sERROR_ON_UNDEFINED_SYMBOLS='): arg = '-sERROR_ON_UNDEFINED_SYMBOLS=1'
        if '--unresolved-symbols=ignore-all' in arg: raise RuntimeError('Unresolved native symbols must fail the build')
        result.append(arg)
    if not any(x.startswith('-sSTACK_OVERFLOW_CHECK=') for x in result): result.append('-sSTACK_OVERFLOW_CHECK=2')
    return result

assert (work / 'build/wasm/busytex.wasm').is_file(), 'Build the clean combined base first'
assert (work / 'build/wasm/pdftex.wasm').is_file(), 'Build the clean pdfTeX base first'
if out.exists() and any(out.iterdir()): raise RuntimeError('Use an empty performance output directory')
out.mkdir(parents=True, exist_ok=True)
(out / 'build-provenance.json').write_text(json.dumps({'sourceCommit': os.environ.get('GITHUB_SHA'), 'toolchain': 'Emscripten 3.1.43', 'work': str(work), 'priorExperimentObjectInputs': False}, indent=2) + '\n')
try:
    # Generate native checkpoint/page/resource boundaries from the fresh Web2C output.
    packet = out / 'pdf-packet'
    activate(packet)
    run(['python3', recipe / 'native-preview/page-packet-recipe/patch-packet.py', '--generated', generated, '--base-recipe', recipe, '--out', packet])
    run(['python3', recipe / 'native-preview/page-packet-recipe/build-inside.py', '--prototype-only'])
    elastic = out / 'pdf-elastic'
    activate(elastic)
    run(['python3', recipe / 'native-preview/elastic-font-recipe/prepare.py', '--base-runtime', packet, '--base-commands', packet / 'build-commands.json', '--generated-commands', packet / 'build-commands.json', '--output', elastic])
    pdf_commands = json.loads((elastic / 'commands.json').read_text())
    for command in pdf_commands:
        if '-c' in command:
            command[:] = ['-O3' if value in ['-Oz', '-Os', '-O1', '-O2', '-O3'] else value for value in command]
        else:
            command[:] = link_options(command)
        run(command, generated)
    (elastic / 'build-commands.json').write_text(json.dumps(pdf_commands, indent=2) + '\n')
    # Preserve same-stack file resolution and demand-driven font-map parsing.
    pdf_io = out / 'pdftex-io'
    activate(pdf_io)
    run(['python3', recipe / 'native-preview/live-input-recipe/prepare.py', '--work', work, '--base-runtime', elastic, '--base-commands', elastic / 'build-commands.json', '--output', pdf_io])
    run(['python3', recipe / 'native-preview/live-input-recipe/build-inside.py'])
    # Also publish the non-I/O checkpoint variant, built from the same new objects.
    for suffix in ['js', 'wasm']:
        shutil.copy2(elastic / ('pdftex.' + suffix), out / ('pdftex.' + suffix))

    # XeTeX retains logical indices/format bytes while packing unused table gaps.
    xe_font = out / 'xe-font'
    run(['python3', recipe / 'native-preview/elastic-font-recipe/prepare-xetex.py', '--generated', generated, '--output', xe_font])
    xe_packed = out / 'xe-packed'
    run(['python3', recipe / 'native-preview/hash-memory-recipe/prepare.py', '--base-runtime', xe_font, '--output', xe_packed])
    xe = out / 'combined'
    activate(xe)
    run(['python3', recipe / 'xetex-recipe/prepare.py', '--base', xe_packed, '--output', xe])
    flags = make_flags(generated, '$(DEFS) $(DEFAULT_INCLUDES) $(INCLUDES) $(xetex_CPPFLAGS) $(CPPFLAGS) $(AM_CFLAGS) $(CFLAGS)')
    for stem in ['xetex0', 'xetexini']:
        run(['emcc', '-Dbusymain=busymain_xetex', '-Dprivileged=privileged', *flags, '-I' + str(generated), '-I' + str(xe), '-c', xe / (stem + '.c'), '-o', xe / ('xetex-' + stem + '.o')], generated)
    # ICU stub data and the full resource pack come from this exact ICU build.
    icu = work / 'build/wasm/texlive/libs/icu/icu-build'
    run(['make', '-j4', '-C', icu / 'stubdata'])
    run(['emcc', '-O3', '-I' + str(work / 'source/texlive/libs/icu/icu-src/source/common'), '-c', recipe / 'native-preview/native-data/native.c', '-o', xe / 'native-assets.o'])
    dry = subprocess.check_output(['make', '-n', '-W', 'busytex.c', 'build/wasm/busytex.js'], cwd=work, text=True)
    links = [shlex.split(line) for line in dry.splitlines() if line.startswith('em++ ') and '-o build/wasm/busytex.js ' in line]
    assert len(links) == 1, 'Cannot identify the fresh combined link command'
    link = links[0]
    replacements = {
        'build/wasm/busytex.js': str(xe / 'busytex.js'),
        'build/wasm/texlive/texk/web2c/xetex-xetex0.o': str(xe / 'xetex-xetex0.o'),
        'build/wasm/texlive/texk/web2c/xetex-xetexini.o': str(xe / 'xetex-xetexini.o'),
        'build/wasm/texlive/texk/kpathsea/.libs/libkpathsea.a': str(pdf_io / 'libkpathsea.a'),
        'build/wasm/texlive/libs/icu/icu-build/lib/libicudata.a': str(icu / 'stubdata/libicudata.a'),
    }
    for old in replacements: assert link.count(old) == 1, old
    link = [replacements.get(x, x) for x in link]
    checkpoint = ['engine', 'arm', 'disarm', 'resume', 'paused', 'prepare_snapshot', 'refresh_inputs', 'line', 'next_line', 'total_pages', 'input_ptr', 'input_index', 'input_state', 'buffer_loc', 'buffer_limit', 'buffer_start', 'buffer', 'input_stack', 'filename', 'input_fd', 'input_offset']
    exports = ['_malloc', '_free', '_siglum_io_api_version', '_siglum_io_register_file', '_siglum_icu_use_files', '_siglum_icu_probe', '_siglum_xetex_table_profile']
    exports += ['_siglum_xetex_font_memory_' + x for x in ['configure', 'capacity', 'limit', 'growth_count']]
    exports += ['_siglum_checkpoint_' + x for x in checkpoint]
    link = link_options(link, exports, ['UTF8ToString', 'stringToUTF8', 'lengthBytesUTF8', 'stackSave', 'stackRestore', 'NODEFS'])
    if '-lnodefs.js' not in link: link.append('-lnodefs.js')
    link.append(str(xe / 'native-assets.o'))
    run(link)
    packs = list((icu / 'data').rglob('icudt*l.dat'))
    packs = [p for p in packs if p.is_file()]
    assert packs, 'Missing the full data pack produced by this ICU build'
    unique = {hashlib.sha256(p.read_bytes()).hexdigest() for p in packs}
    assert len(unique) == 1, 'Ambiguous ICU resource packs'
    run(['python3', recipe / 'native-preview/native-data/extract.py', '--data', packs[0], '--output', xe])
finally:
    (out / 'commands-executed.json').write_text(json.dumps(commands, indent=2) + '\n')
    (out / 'toolchain.txt').write_text(subprocess.check_output(['emcc', '--version'], text=True))
    files = {str(p.relative_to(out)): {'size': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in out.rglob('*') if p.is_file() and p.suffix in ['.wasm', '.js', '.c', '.h', '.inc', '.dat']}
    (out / 'artifacts.json').write_text(json.dumps(files, indent=2) + '\n')
