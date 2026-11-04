#!/usr/bin/env python3
"""Stream the pinned TeX Live ISO into a temporary extraction directory."""

from contextlib import suppress
from hashlib import sha512
from pathlib import Path
from subprocess import PIPE, Popen
from tempfile import TemporaryDirectory
from urllib.request import urlopen
import sys


def extract(url, expected, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = sha512()
    with TemporaryDirectory(prefix=destination.name + '.', dir=destination.parent) as work:
        extracted = Path(work) / 'tree'
        extracted.mkdir()
        with urlopen(url, timeout=120) as archive, Popen(
            ['bsdtar', '-xf', '-', '-C', str(extracted)], stdin=PIPE
        ) as unpack:
            chunks = iter(lambda: archive.read(1024 * 1024), b'')
            try:
                for chunk in chunks:
                    digest.update(chunk)
                    unpack.stdin.write(chunk)
            except BrokenPipeError:
                # bsdtar can finish before trailing ISO bytes have been read.
                for chunk in chunks:
                    digest.update(chunk)
            finally:
                with suppress(BrokenPipeError):
                    unpack.stdin.close()
            if unpack.wait():
                raise ValueError('bsdtar could not extract the ISO')
        if digest.hexdigest() != expected:
            raise ValueError('ISO SHA-512 mismatch')
        extracted.rename(destination)


if __name__ == '__main__':
    try:
        extract(sys.argv[1], sys.argv[2], Path(sys.argv[3]))
    except (OSError, ValueError) as error:
        sys.exit(f'TeX Live ISO extraction failed: {error}')
