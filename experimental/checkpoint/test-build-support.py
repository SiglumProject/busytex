import unittest
from build_support import replace_link_inputs


class LinkInputs(unittest.TestCase):
    def test_repeated_static_archive_preserves_resolution_order(self):
        command = ['em++', 'main.o', 'libpaths.a', 'libother.a', 'libpaths.a', '-o', 'old.js']
        result, counts = replace_link_inputs(command, {'libpaths.a': 'patched.a', 'old.js': 'new.js'})
        self.assertEqual(result, ['em++', 'main.o', 'patched.a', 'libother.a', 'patched.a', '-o', 'new.js'])
        self.assertEqual(counts, {'libpaths.a': 2, 'old.js': 1})
        self.assertEqual(command[2], 'libpaths.a')

    def test_missing_archive_is_rejected(self):
        with self.assertRaises(ValueError):
            replace_link_inputs(['em++', 'main.o'], {'missing.a': 'patched.a'})

    def test_duplicate_object_is_rejected(self):
        with self.assertRaises(ValueError):
            replace_link_inputs(['em++', 'main.o', 'main.o'], {'main.o': 'patched.o'})

    def test_duplicate_output_is_rejected(self):
        with self.assertRaises(ValueError):
            replace_link_inputs(['em++', '-o', 'old.js', 'old.js'], {'old.js': 'new.js'})

    def test_multiple_archive_repetitions_are_not_deduplicated(self):
        result, counts = replace_link_inputs(['a.a', 'b.a', 'a.a', 'a.a'], {'a.a': 'new.a'})
        self.assertEqual(result, ['new.a', 'b.a', 'new.a', 'new.a'])
        self.assertEqual(counts['a.a'], 3)


if __name__ == '__main__':
    unittest.main()
