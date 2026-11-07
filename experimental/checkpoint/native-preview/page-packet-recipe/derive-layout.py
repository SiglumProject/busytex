#!/usr/bin/env python3
"""Resolve experimental hook constants from the exact generated engine sources.

No default engine offsets: a changed/ambiguous generation aborts before linking.
This is source generation, not a runtime dependency or parser of user documents.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re


def derive(generated):
    source = {name: (generated / name).read_text() for name in ('pdftex-pool.c', 'pdftexini.c', 'pdftex0.c')}
    pool = source['pdftex-pool.c']
    match = re.search(r'static\s+const\s+char\s*\*poolfilearr\[\]\s*=\s*\{([\s\S]*?)\bNULL\s*\}', pool)
    if not match:
        raise RuntimeError('Cannot identify generated string-pool array')
    array = match.group(1)
    # Entries are sequences of adjacent C strings. Keep escaped quotes/commas
    # inside literals, and do not depend on source line wrapping.
    entry_pattern = re.compile(r'\s*((?:"(?:\\.|[^"\\])*"\s*)+),')
    entries, position = [], 0
    while position < len(array):
        item = entry_pattern.match(array, position)
        if not item:
            if not array[position:].strip(): break
            raise RuntimeError('Unrecognized generated string-pool entry')
        tokens = re.findall(r'"(?:\\.|[^"\\])*"', item.group(1))
        # Only names queried below must decode. C unknown escapes/trigraph
        # fragments in unrelated diagnostic messages need no interpretation.
        entries.append(''.join(token[1:-1] for token in tokens))
        position = item.end()
    ini = source['pdftexini.c']
    initializer = re.search(r'getstringsstarted\s*\([^)]*\)\s*\{([\s\S]*?)loadpoolstrings\s*\(', ini)
    if not initializer:
        raise RuntimeError('Cannot identify generated string-pool initialization')
    prefix = initializer.group(1)
    loops = re.findall(r'k\s*=\s*(\d+)\s*;\s*for_end\s*=\s*(\d+)\s*;', prefix)
    if len(loops) != 1 or not re.search(r'\bstrptr\s*=\s*0\s*;', prefix) or len(re.findall(r'\bmakestring\s*\(', prefix)) != 1:
        raise RuntimeError('Ambiguous initial character-string count')
    start, end = map(int, loops[0])
    if start != 0 or end < start:
        raise RuntimeError('Unsupported generated character-string prefix')
    first_pool_id = end - start + 1
    slots, commands = {}, []
    for primitive, macro in [('pdfpageattr', 'SIGLUM_PREVIEW_EQTB_PAGE_ATTR'),
                             ('pdfpageresources', 'SIGLUM_PREVIEW_EQTB_PAGE_RESOURCES')]:
        if entries.count(primitive) != 1:
            raise RuntimeError('Missing/ambiguous pool primitive: ' + primitive)
        string_id = first_pool_id + entries.index(primitive)
        registrations = re.findall(r'\bprimitive\s*\(\s*' + str(string_id) + r'\s*,\s*(\d+)\s*,\s*(\d+)\s*\)\s*;', ini)
        if len(registrations) != 1:
            raise RuntimeError('Missing/ambiguous primitive registration: ' + primitive)
        command, slot = map(int, registrations[0])
        slots[macro] = slot
        commands.append(command)
    if len(set(commands)) != 1 or len(set(slots.values())) != 2:
        raise RuntimeError('Resource/page attribute registers have inconsistent kinds')
    primitive = 'pdfgentounicode'
    if entries.count(primitive) != 1:
        raise RuntimeError('Missing/ambiguous pool primitive: ' + primitive)
    string_id = first_pool_id + entries.index(primitive)
    registrations = re.findall(r'\bprimitive\s*\(\s*' + str(string_id) + r'\s*,\s*(\d+)\s*,\s*(\d+)\s*\)\s*;', ini)
    if len(registrations) != 1:
        raise RuntimeError('Missing/ambiguous primitive registration: ' + primitive)
    unicode_command, unicode_slot = map(int, registrations[0])
    closing_slots = set(map(int, re.findall(r'\bfixedgentounicode\s*=\s*eqtb\s*\[\s*(\d+)\s*\]\s*\.cint\s*;', source['pdftex0.c'])))
    if closing_slots != {unicode_slot}:
        raise RuntimeError('ToUnicode primitive does not match the actual finalization setting')
    slots['SIGLUM_PREVIEW_EQTB_GENERATE_UNICODE'] = unicode_slot
    nils = []
    for name in ('pdfximagelist', 'pdfxformlist', 'pdfobjlist', 'pdffontlist',
                 'pdfannotlist', 'pdflinklist', 'pdfdestlist', 'pdfbeadlist'):
        values = set(map(int, re.findall(r'\b' + name + r'\s*=\s*(-?\d+)L?\s*;', source['pdftex0.c'])))
        if len(values) != 1:
            raise RuntimeError('Missing/ambiguous generated list sentinel: ' + name)
        nils.extend(values)
    if len(set(nils)) != 1 or nils[0] >= 0:
        raise RuntimeError('Inconsistent generated list sentinels')
    slots['SIGLUM_PREVIEW_NIL'] = nils[0]
    hashes = {name: hashlib.sha256(text.encode()).hexdigest() for name, text in source.items()}
    return slots, {'slots': slots, 'firstPoolStringId': first_pool_id,
                   'primitiveCommand': commands[0], 'fontGlobalPrimitiveCommand': unicode_command,
                   'sourceSha256': hashes}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--generated', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    slots, manifest = derive(args.generated)
    args.out.mkdir(parents=True, exist_ok=True)
    header = ['/* Generated from the exact pdfTeX source files; do not edit offsets. */',
              '#ifndef SIGLUM_PREVIEW_LAYOUT_H', '#define SIGLUM_PREVIEW_LAYOUT_H']
    for name, value in slots.items(): header.append('#define ' + name + ' (' + str(value) + 'L)')
    header += ['#endif', '']
    (args.out / 'siglum_preview_layout.h').write_text('\n'.join(header))
    (args.out / 'preview-layout-source.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest))


if __name__ == '__main__': main()
