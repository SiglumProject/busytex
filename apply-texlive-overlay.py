#!/usr/bin/env python3
"""Apply the locked TeX Live runtime package overlay to an installed tree."""

from hashlib import sha512
from io import BytesIO
from pathlib import Path, PurePosixPath
from subprocess import PIPE, Popen
from tempfile import NamedTemporaryFile
import json
import os
import sys
import tarfile


def write_file(path, contents):
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
        staged = Path(temporary.name)
        try:
            temporary.write(contents)
            temporary.close()
            staged.chmod(0o644)
            staged.replace(path)
        finally:
            staged.unlink(missing_ok=True)


def read_package(cache, name, pin):
    path = cache / f"{name}.r{pin['revision']}.tar.xz"
    size = int(pin['containersize'])
    cached = path.is_file()
    if cached:
        contents = path.read_bytes()
    else:
        # The TeX Live archive serves its package files to curl.
        with Popen([
            'curl', '--fail', '--silent', '--show-error', '--location',
            '--max-time', '30', '--', pin['url'],
        ], stdout=PIPE) as download:
            contents = download.stdout.read(size + 1)
            if len(contents) > size:
                download.terminate()
            elif download.wait():
                raise ValueError(f"download failed for {path.name}")
    if len(contents) != size or sha512(contents).hexdigest() != pin['containerchecksum']:
        raise ValueError(f"size or SHA-512 mismatch for {path.name}")
    if not cached:
        write_file(path, contents)
    return contents


def tds_path(name):
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or not path.parts:
        raise ValueError(f"invalid archive path {name!r}")
    return path


def apply_overlay(tree, cache, pins):
    files = {}
    for name, pin in pins['packages'].items():
        contents = read_package(cache, name, pin)
        with tarfile.open(fileobj=BytesIO(contents), mode='r:xz') as archive:
            for member in archive:
                path = tds_path(member.name)
                if path.parts[0] not in ('tex', 'fonts') or member.isdir():
                    continue
                if not member.isfile() or path in files:
                    raise ValueError(f"unexpected archive entry {name}/{path}")
                files[path] = archive.extractfile(member).read()

    retired = {tds_path(path) for path in pins['retiredFiles']}
    if retired & files.keys():
        raise ValueError("a retired path is also in the overlay")
    for path in retired | files.keys():
        target = tree / path
        if target.resolve() != target or (target.exists() and not target.is_file()):
            raise ValueError(f"unexpected path in TeX Live installation: {target}")

    for path in sorted(retired):
        (tree / path).unlink(missing_ok=True)
    for path, contents in sorted(files.items()):
        write_file(tree / path, contents)

    # kpathsea uses this filename database for lookups inside the WASM tree.
    database = ['% ls-R -- filename database for kpathsea\n']
    for folder, dirs, names in os.walk(tree):
        dirs.sort()
        relative = Path(folder).relative_to(tree).as_posix()
        directory = '.' if relative == '.' else './' + relative
        database.extend([f'\n{directory}:\n', '\n'.join(sorted(names + dirs)) + '\n'])
    write_file(tree / 'ls-R', ''.join(database).encode())
    print(f"Applied {len(pins['packages'])} verified packages from {pins['snapshot']}")


if __name__ == '__main__':
    installed_tree = Path(sys.argv[1]).resolve()
    cache = Path(os.environ.get('BUSYTEX_TEXLIVE_ARCHIVES') or 'build/texlive-package-cache')
    lock = Path(__file__).with_name('texlive-packages.lock.json')
    try:
        if not (installed_tree / 'web2c/texmf.cnf').is_file():
            raise ValueError(f"install the base TeX Live tree first: {installed_tree}")
        apply_overlay(installed_tree, cache, json.loads(lock.read_text()))
    except (OSError, ValueError, tarfile.TarError) as error:
        sys.exit(f"TeX Live package overlay failed: {error}")
