"""用户运行的回归测试：临时文件/Git/Tcl 桩，不调用任何 EDA 工具。"""
import contextlib
import gzip
import io
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import zipfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'flow'))
from flow import Flow, PNR
from eco_versions import Versions, export_log
from report_store import unpack, collect
from state import files_hash, write_json, read_json
import readiness

ROOT = Path(__file__).resolve().parents[1]


class SourceTests(unittest.TestCase):
    def test_python_sources_parse(self):
        for path in (ROOT/'flow').glob('*.py'):
            compile(path.read_text(encoding='utf-8'), str(path), 'exec')


class ExportLogTests(unittest.TestCase):
    def test_old_interactive_errors_excluded_but_export_errors_retained(self):
        import reports
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            log = directory/'gui.log'
            prefix = '**ERROR: No more action to undo.\ninvalid command name "eco_expot"\n'
            export = '<CMD> saveDesign '+str(directory/'editable.enc')+'\n'
            export += 'verifyConnectivity complete\n<CMD> saveDesign '+str(directory/'design.enc')+'\n'
            log.write_text(prefix+export)
            self.assertEqual(reports.messages([export_log(directory)])['errors'], [])
            self.assertEqual(log.read_text(), prefix+export)
            log.write_text(prefix+export+'**ERROR: export failed\n')
            self.assertTrue(reports.messages([export_log(directory)])['errors'])
            log.write_text(prefix+export+'Net signal: has regular routing with opens, dangling Wire.\n')
            with self.assertRaisesRegex(ValueError, '断线'):
                export_log(directory)

class ReportTests(unittest.TestCase):
    def test_refresh_text_and_reject_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root/'setup.summary.gz'
            with gzip.open(str(path), 'wb') as output:
                output.write(b'new report')
            path.with_suffix('').write_text('old report')
            unpack(path)
            self.assertEqual(path.with_suffix('').read_text(), 'new report')
            self.assertTrue(path.exists())
            archive = root/'bad.zip'
            with zipfile.ZipFile(str(archive), 'w') as output:
                output.writestr('../escape', 'bad')
            with self.assertRaises(ValueError):
                unpack(archive)
            self.assertFalse((root/'escape').exists())


@unittest.skipUnless(shutil.which('git'), '需要 Git')
class VersionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root/'scripts').mkdir()
        (self.root/'scripts/example.tcl').write_text('# test')
        self.flow = Flow(self.root, dict(DESIGN_NAME='chip', TOP_MODULE='top', TECH='demo', GATE_STAGE='chipfinish'))
        for stage in ('dc',)+PNR:
            directory = self.flow.ws.stage(stage)
            directory.mkdir(parents=True)
            artifact = directory/'artifact'
            artifact.write_text(stage)
            write_json(directory/'result.json', dict(status='OK', artifacts=files_hash([artifact])))
        self.route = self.flow.ws.stage('route')
        self.final = self.flow.ws.stage('chipfinish')
        for directory in (self.route, self.final):
            (directory/'design.enc').write_text('restoreDesign [file dirname [info script]]/design.enc.dat top')
            (directory/'design.enc.dat').mkdir()
            (directory/'design.enc.dat/db').write_text('baseline')
        for name in ('chip.v', 'chip_lvs.v', 'chip.sdc', 'chip.sdf', 'chip.def', 'chip.gds', 'chip.lef', 'add_pg_text.tcl', 'hcell_list'):
            (self.final/name).write_text(name)
        (self.final/'reports').mkdir()
        # 自建最小报告，公开仓库不包含真实项目日志或供应商报告。
        for mode, name in [('Setup', 'setup.summary.gz'), ('Hold', 'hold_hold.summary.gz')]:
            text = '| '+mode+' mode | all |\n| WNS (ns): | 0.1 |\n| TNS (ns): | 0.0 |\n| All Paths: | 1 |\n'
            with gzip.open(str(self.final/'reports'/name), 'wb') as stream:
                stream.write(text.encode('utf-8'))
        self.versions = Versions(self.flow)

    def test_parent_rollback_branch_and_git_recovery(self):
        base = self.versions.baseline()
        (self.route/'design.enc.dat/db').write_text('second')
        second = self.versions.snapshot(self.route/'design.enc', self.final, '第二版', base)
        with contextlib.redirect_stdout(io.StringIO()):
            self.versions.select(second)
            self.assertTrue(self.flow.valid('eco'))
            self.assertEqual(self.versions.directory(second).joinpath('editable/design.enc.dat/db').read_text(), 'second')
            self.versions.rollback()
            self.assertEqual(self.versions.selected(), base)
            third = self.versions.snapshot(self.route/'design.enc', self.final, '从基线分支', base)
            self.versions.select(third)
            self.versions.rollback(second[:10])
        self.assertEqual(self.versions.selected(), second)
        self.assertEqual(self.versions.metadata(third)['parent'], base)
        # 缓存丢失后应从 Git 内容恢复，而不是依赖可变工作目录。
        directory = self.versions.directory(second)
        shutil.rmtree(str(directory))
        self.assertEqual(self.versions.directory(second).joinpath('editable/design.enc.dat/db').read_text(), 'second')
        self.assertEqual((self.final/'chip.gds').read_text(), 'chip.gds')

    def test_report_collection_excludes_database(self):
        (self.final/'design.enc.dat/private.rpt').write_text('database internals')
        collect(self.flow, 'chipfinish')
        destination = self.root/'reports/chip/demo/innovus/chipfinish'
        self.assertTrue((destination/'setup.summary').is_file())
        self.assertFalse((destination/'design.enc.dat').exists())


@unittest.skipUnless(shutil.which('tclsh'), '需要 Tcl 解释器')
class DrcPolicyTests(unittest.TestCase):
    def test_remaining_drc_continues_after_one_repair(self):
        import subprocess
        with tempfile.TemporaryDirectory() as temp:
            source = (ROOT/'flow/route_drc.tcl').as_posix()
            script = '''source {%s}
file mkdir reports
set checks 0
set repairs 0
proc flow_drc_count {path} {global checks; incr checks; return 2}
proc saveDesign {args} {}
proc ecoRoute {args} {global repairs; incr repairs}
set passes [flow_route_drc_gate]
flow_chipfinish_drc_gate
puts "RESULT:$passes:$repairs:$checks"
''' % source
            proc = subprocess.Popen(['tclsh'], cwd=temp, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            out, err = proc.communicate(script.encode('utf-8'))
            self.assertEqual(proc.returncode, 0, err.decode('utf-8', 'replace'))
            self.assertIn(b'RESULT:1:1:3', out)

class ReadinessTests(unittest.TestCase):
    def test_blank_template_not_ready_and_power_not_a_selector(self):
        flow = Flow(ROOT, dict(TECH='demo'))
        self.assertTrue(readiness.configuration_issues(flow, 'floorplan'))
        issues = readiness.configuration_issues(flow, 'powerplan')
        self.assertFalse(any('POWER' in issue or 'one / two' in issue for issue in issues))


if __name__ == '__main__':
    unittest.main()