"""Rule overlay regression cases; filesystem only, no EDA invocation."""
from pathlib import Path
import os
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'flow'))
from flow import copy_overlay


@unittest.skipIf(os.name == 'nt', 'Linux Calibre database symlinks')
class CalibreOverlayTests(unittest.TestCase):
    def test_database_link_is_preserved_but_copy_target_link_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, destination = root/'rules', root/'drc'
            source.mkdir()
            destination.mkdir()
            (source/'rules.cal.in').write_text('rules')
            (destination/'drc_run').mkdir()
            database = destination/'.cgidrcdb'
            database.symlink_to('drc_run', target_is_directory=True)
            copy_overlay(source, destination)
            self.assertTrue(database.is_symlink())
            self.assertEqual((destination/'rules.cal.in').read_text(), 'rules')
            (destination/'rules.cal.in').unlink()
            external = root/'external'
            external.write_text('untouched')
            (destination/'rules.cal.in').symlink_to(external)
            with self.assertRaises(ValueError):
                copy_overlay(source, destination)
            self.assertEqual(external.read_text(), 'untouched')


if __name__ == '__main__':
    unittest.main()