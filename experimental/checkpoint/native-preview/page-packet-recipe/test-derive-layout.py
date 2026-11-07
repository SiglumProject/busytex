#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('derive_layout', Path(__file__).with_name('derive-layout.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class GeneratedLayoutTests(unittest.TestCase):
    def sources(self, directory):
        (directory / 'pdftex-pool.c').write_text('static const char *poolfilearr[] = {\n'
            '"unrelated, diagnostic", "pdfpageattr", "pdfpageresources", "pdfgentounicode", NULL };\n')
        (directory / 'pdftexini.c').write_text('getstringsstarted(void) { strptr = 0;\n'
            'k = 0;for_end = 4; g = makestring(); g = loadpoolstrings(8); }\n'
            'primitive(6, 9, 101); primitive(7, 9, 202); primitive(8, 10, 303);\n')
        (directory / 'pdftex0.c').write_text('fixedgentounicode = eqtb[303].cint;\n' + '\n'.join(name + ' = -7L;' for name in
            ('pdfximagelist', 'pdfxformlist', 'pdfobjlist', 'pdffontlist',
             'pdfannotlist', 'pdflinklist', 'pdfdestlist', 'pdfbeadlist')))

    def test_derives_changed_generated_layout(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary); self.sources(path)
            slots, manifest = module.derive(path)
            self.assertEqual(slots, {'SIGLUM_PREVIEW_EQTB_PAGE_ATTR': 101,
                'SIGLUM_PREVIEW_EQTB_PAGE_RESOURCES': 202, 'SIGLUM_PREVIEW_EQTB_GENERATE_UNICODE': 303,
                'SIGLUM_PREVIEW_NIL': -7})
            self.assertEqual(manifest['firstPoolStringId'], 5)

    def rejects(self, file, before, after):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary); self.sources(path)
            source = (path / file).read_text(); self.assertIn(before, source)
            (path / file).write_text(source.replace(before, after, 1))
            with self.assertRaises(RuntimeError): module.derive(path)

    def test_rejects_duplicate_pool_primitive(self):
        self.rejects('pdftex-pool.c', '"unrelated, diagnostic"', '"pdfpageattr"')

    def test_rejects_duplicate_primitive_registration(self):
        self.rejects('pdftexini.c', 'primitive(6, 9, 101);', 'primitive(6, 9, 101); primitive(6, 9, 303);')

    def test_rejects_missing_primitive_registration(self):
        self.rejects('pdftexini.c', 'primitive(6, 9, 101);', '')

    def test_rejects_changed_sentinel_kind(self):
        self.rejects('pdftex0.c', 'pdfobjlist = -7L;', 'pdfobjlist = -9L;')

    def test_rejects_ambiguous_initial_string_count(self):
        self.rejects('pdftexini.c', 'g = makestring();', 'g = makestring(); g = makestring();')

    def test_rejects_different_register_command(self):
        self.rejects('pdftexini.c', 'primitive(7, 9, 202)', 'primitive(7, 10, 202)')

    def test_rejects_mismatched_finalization_setting(self):
        self.rejects('pdftex0.c', 'fixedgentounicode = eqtb[303].cint;', 'fixedgentounicode = eqtb[304].cint;')


if __name__ == '__main__': unittest.main()
