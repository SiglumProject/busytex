#!/usr/bin/env python3
"""Compiles the literal grammar of siglum_preview.inc on its own and checks
which PDF literals the page handoff accepts."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ACCEPTED = [
    '',
    '0 g 0 G',
    '1 0 0 rg 0.5 0.5 0.5 RG',
    '0 0 0 1 k 0 0 0 1 K',
    'q',
    'Q',
    'q 1 0 0 1 72 786.999 cm',
    '[]0 d 0 J 0.398 w 0 0 m 451.276 0 l S',
    '[3 1.5] 0 d',
    '[ 3 1.5 ]2 d 1 j 10 M',
    '45.83205 14.17339 m -45.83205 14.17339 l -48.03299 14.17339 -49.81717 12.38921 -49.81717 10.18828 c h B',
    '0 0 10 20 re W n',
    '0 0 10 20 re f* 1 2 3 4 v 1 2 3 4 y b* s F',
    '/pgf@ca1.0 gs',
    '0.375 g\n/pgf@ca1.0 gs\n0.0 4.25198 m\n0.0 160.63058 l S',
    '1 i',
]
REFUSED = [
    'BT /F1 10 Tf (x) Tj ET',
    '(x) Tj',
    '<41> Tj',
    '/F1 10 Tf',
    'BT',
    '/Im1 Do',
    '/Sh1 sh',
    '/Cs1 cs',
    '/P1 scn',
    '1 0 0 scn',
    '/pgf@ca1.0 gs gs',
    '/a /b gs',
    '1 /a gs',
    '/a',
    '0 g 0',
    '1 2 rg',
    '1 2 3 4 rg',
    '1 2 m 3',
    '[1 2 d',
    '1 2] 0 d',
    '[[1] 2] 0 d',
    '[1 2] d',
    '[1 2] 0 w',
    '[1 (x)] 0 d',
    '% comment\n0 g',
    '<< /a 1 >> gs',
    'BI /W 1 ID x EI',
    '1 0 0 1 0 0 cm (',
    '0g',
    '1 0 0 1 0 0 cmx',
    '1..2 w',
    '- w',
    'q q Tj',
    '0 Tc',
    '0 Tr',
    "(x) '",
    '{ }',
]


class LiteralGrammarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which('cc') or shutil.which('gcc') or shutil.which('clang')
        if not compiler:
            raise unittest.SkipTest('no C compiler')
        source = Path(__file__).with_name('siglum_preview.inc').read_text()
        begin, end = source.index('/* BEGIN literal grammar */'), source.index('/* END literal grammar */')
        cls.directory = tempfile.TemporaryDirectory()
        path = Path(cls.directory.name)
        (path / 'test.c').write_text('#include <stdio.h>\n#include <string.h>\n' + source[begin:end] + '''
int main(int argc, char **argv) {
    static unsigned char buffer[1 << 17];
    size_t length = fread(buffer, 1, sizeof(buffer), stdin);
    (void)argc; (void)argv;
    return siglum_preview_is_drawing_literal_bytes(buffer, buffer + length) ? 0 : 1;
}
''')
        subprocess.run([compiler, '-std=c99', '-Wall', '-Wextra', '-Werror', '-o', str(path / 'test'), str(path / 'test.c')], check=True)
        cls.binary = str(path / 'test')

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def accepts(self, literal):
        return subprocess.run([self.binary], input=literal.encode('latin-1')).returncode == 0

    def test_accepts_drawing_and_graphics_state(self):
        for literal in ACCEPTED:
            self.assertTrue(self.accepts(literal), literal)

    def test_refuses_everything_else(self):
        for literal in REFUSED:
            self.assertFalse(self.accepts(literal), literal)

    def test_refuses_oversized(self):
        self.assertFalse(self.accepts('q ' * 40000))


if __name__ == '__main__':
    unittest.main()
