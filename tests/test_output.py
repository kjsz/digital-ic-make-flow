"""交付打包只读取当前存在文件；不调用 Make 或 EDA。"""
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'flow'))
from flow import Flow
from deliver import package
from state import read_json


class OutputTests(unittest.TestCase):
    def test_missing_files_skipped_and_zip_matches_folder(self):
        with tempfile.TemporaryDirectory() as temp:
            flow = Flow(Path(temp), dict(DESIGN_NAME='demo', TECH='demo', GATE_STAGE='dc'))
            source = flow.ws.stage('chipfinish')
            source.mkdir(parents=True)
            (source/'demo.v').write_text('module demo; endmodule')
            (source/'hcell_list').write_text('cell cell\n')
            with contextlib.redirect_stdout(io.StringIO()):
                package(flow)
                package(flow)
            root = Path(temp)/'output/demo/demo'
            directories = [path for path in root.iterdir() if path.is_dir()]
            self.assertEqual(len(directories), 2)
            for directory in directories:
                manifest = read_json(directory/'manifest.json')
                self.assertEqual(sum(item['status'] == 'copied' for item in manifest['files']), 2)
                self.assertTrue(any(item['file'] == 'demo.sdc' and item['status'] == 'skipped' for item in manifest['files']))
                with zipfile.ZipFile(str(directory.with_suffix('.zip'))) as archive:
                    self.assertEqual(archive.read(directory.name+'/demo.v'), (source/'demo.v').read_bytes())
            self.assertFalse((flow.ws.stage('dc')/'result.json').exists())


if __name__ == '__main__':
    unittest.main()