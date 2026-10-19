"""工作区文件修改→验证→提交；使用临时目录与 Git，不调用 EDA。"""
import contextlib
import gzip
import io
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'flow'))
from flow import Flow, PNR
from workspace_versions import Versions
from eco_versions import Versions as LegacyVersions
from state import files_hash, read_json, write_json


@unittest.skipUnless(shutil.which('git'), '需要 Git')
class WorkspaceVersionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root/'scripts').mkdir()
        (self.root/'scripts/example.tcl').write_text('# example')
        self.flow = Flow(self.root, dict(DESIGN_NAME='chip', TOP_MODULE='top', TECH='demo', GATE_STAGE='chipfinish'))
        for stage in ('dc',)+PNR:
            directory = self.flow.ws.stage(stage)
            directory.mkdir(parents=True)
            artifact = directory/'artifact'
            artifact.write_text(stage)
            write_json(directory/'result.json', dict(stage=stage, status='OK', artifacts=files_hash([artifact])))
        self.route = self.flow.ws.stage('route')
        self.final = self.flow.ws.stage('chipfinish')
        for directory in (self.route, self.final):
            (directory/'design.enc').write_text('restoreDesign [file dirname [info script]]/design.enc.dat top')
            (directory/'design.enc.dat').mkdir()
            (directory/'design.enc.dat/db').write_text('baseline')
        for name in ('chip.v', 'chip_lvs.v', 'chip.sdc', 'chip.sdf', 'chip.def', 'chip.lef', 'chip.gds', 'add_pg_text.tcl', 'hcell_list'):
            (self.final/name).write_text('original '+name)
        (self.final/'reports').mkdir()
        for mode, name in [('Setup', 'setup.summary.gz'), ('Hold', 'hold_hold.summary.gz')]:
            text = '| '+mode+' mode | all |\n| WNS (ns): | 0.1 |\n| All Paths: | 1 |\n'
            with gzip.open(str(self.final/'reports'/name), 'wb') as stream:
                stream.write(text.encode('utf-8'))
        self.versions = Versions(self.flow)

    def mark(self, stage):
        directory = self.flow.ws.stage(stage)
        directory.mkdir(parents=True, exist_ok=True)
        artifact = directory/'artifact'
        artifact.write_text(stage)
        write_json(directory/'result.json', dict(stage=stage, status='OK', artifacts=files_hash([artifact])))
        self.flow.memo.clear()

    def initialize(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return self.versions.initialize()

    def test_direct_lvs_edit_verify_then_accept_preserves_verification(self):
        baseline = self.initialize()
        for name in ('merge', 'hcell', 'lvs-input', 'lvs', 'rc', 'pt'):
            self.mark(name)
        (self.final/'chip_lvs.v').write_text('cleaned unused inputs')
        self.versions.before('lvs-input')
        self.assertEqual(self.flow.record('lvs-input')['status'], 'INVALIDATED')
        self.assertEqual(self.flow.record('lvs')['status'], 'INVALIDATED')
        for stage in ('merge', 'rc', 'pt'):
            self.assertEqual(self.flow.record(stage)['status'], 'OK')
        self.assertEqual(self.flow.final_directory(), self.final)
        self.mark('lvs-input')
        self.mark('lvs')
        self.flow.env['MSG'] = '清理无用输入'
        with contextlib.redirect_stdout(io.StringIO()):
            self.versions.accept()
        revision = self.versions.selected()
        self.assertNotEqual(revision, baseline)
        self.assertEqual(self.versions.metadata(revision)['parent'], baseline)
        self.assertEqual(self.flow.record('lvs-input')['status'], 'OK')
        self.assertEqual(self.flow.record('lvs')['status'], 'OK')
        self.assertEqual((self.final/'chip_lvs.v').read_text(), 'cleaned unused inputs')
        self.assertFalse((self.versions.root/'revisions').exists())
        with contextlib.redirect_stdout(io.StringIO()):
            self.versions.accept()
        self.assertEqual(self.versions.selected(), revision)

    def test_touch_is_not_a_change_but_gds_content_is(self):
        self.initialize()
        self.mark('merge')
        os.utime(str(self.final/'chip.gds'), None)
        self.assertEqual(self.versions.observe(), [])
        self.assertFalse(self.versions.dirty())
        (self.final/'chip.gds').write_text('new geometry')
        self.versions.before('merge')
        self.assertEqual(self.flow.record('merge')['status'], 'INVALIDATED')
        self.assertTrue(self.versions.dirty())

    def test_rollback_restores_workspace_and_preserves_branch(self):
        baseline = self.initialize()
        (self.final/'chip_lvs.v').write_text('second')
        with contextlib.redirect_stdout(io.StringIO()): self.versions.accept()
        second = self.versions.selected()
        (self.final/'chip_lvs.v').write_text('unsaved')
        with self.assertRaisesRegex(ValueError, '未提交'):
            self.versions.rollback()
        self.flow.env['DISCARD'] = '1'
        with contextlib.redirect_stdout(io.StringIO()): self.versions.rollback()
        self.assertEqual(self.versions.selected(), baseline)
        self.assertEqual((self.final/'chip_lvs.v').read_text(), 'original chip_lvs.v')
        self.assertFalse(self.versions.dirty())
        (self.final/'chip_lvs.v').write_text('branch')
        with contextlib.redirect_stdout(io.StringIO()): self.versions.accept()
        branch = self.versions.selected()
        self.assertEqual(self.versions.metadata(branch)['parent'], baseline)
        with contextlib.redirect_stdout(io.StringIO()): self.versions.rollback(second[:10])
        self.assertEqual((self.final/'chip_lvs.v').read_text(), 'second')
        self.assertEqual(self.flow.final_directory(), self.final)

    def test_pending_database_cannot_be_committed_or_verified_as_old_export(self):
        self.initialize()
        (self.flow.ws.stage('eco')/'draft-pending').write_text('pending')
        with self.assertRaisesRegex(ValueError, '未导出'):
            self.versions.accept()
        with self.assertRaisesRegex(ValueError, '尚未 eco_export'):
            self.versions.before('rc')

    def test_legacy_history_is_untouched_and_current_pair_seeds_new_baseline(self):
        old = LegacyVersions(self.flow)
        revision = old.snapshot(self.route/'design.enc', self.final, '旧版本')
        with contextlib.redirect_stdout(io.StringIO()): old.select(revision)
        before = old.git(['for-each-ref', '--format=%(refname) %(objectname)'])
        old_directory = old.directory(revision)
        (old_directory/'final/chip_lvs.v').write_text('old current file')
        with self.assertRaisesRegex(ValueError, 'eco-init'):
            self.versions.before('chipfinish')
        baseline = self.initialize()
        self.assertEqual((self.final/'chip_lvs.v').read_text(), 'old current file')
        self.assertNotEqual(baseline, revision)
        self.assertIsNone(self.versions.metadata(baseline)['parent'])
        self.assertEqual(old.git(['for-each-ref', '--format=%(refname) %(objectname)']), before)
        self.assertTrue(old_directory.exists())
        self.assertTrue((self.versions.root/'migration-backup').is_dir())

    def test_successful_export_is_usable_before_commit(self):
        baseline = self.initialize()
        eco = self.flow.ws.stage('eco')
        (eco/'draft-pending').write_text('pending')
        write_json(eco/'exported.json', 'session')
        (self.final/'chip.gds').write_text('uncommitted geometry')
        log = '<CMD> saveDesign '+str(eco/'editable.enc')+'\n'
        log += '<CMD> saveDesign '+str(self.final/'design.enc')+'\n'
        (eco/'gui.log').write_text(log)
        with contextlib.redirect_stdout(io.StringIO()): self.versions.publish_export('session')
        self.assertFalse(self.versions.pending())
        self.assertEqual(self.flow.final_directory(), self.final)
        self.assertEqual(self.versions.selected(), baseline)
        self.assertTrue(self.versions.dirty())
        self.versions.before('lvs-input')
        self.assertEqual(self.flow.record('chipfinish')['status'], 'OK')

    @unittest.skipIf(os.name == 'nt', 'Linux 检查点文件链接')
    def test_workspace_helper_links_materialize_without_false_dirty_after_restore(self):
        baseline = self.initialize()
        helper = self.flow.ws.stage('init')/'helper.tcl'
        helper.write_text('# helper')
        misc = self.final/'design.enc.dat/libs/misc'
        misc.mkdir(parents=True)
        (misc/'helper.tcl').symlink_to(helper)
        with contextlib.redirect_stdout(io.StringIO()): self.versions.accept()
        revision = self.versions.selected()
        with contextlib.redirect_stdout(io.StringIO()):
            self.versions.rollback(baseline)
            self.versions.rollback(revision)
        self.assertFalse(self.versions.dirty())
        self.assertEqual((self.final/'design.enc.dat/libs/misc/helper.tcl').read_text(), '# helper')
    def test_incomplete_editable_pair_cannot_be_committed(self):
        self.initialize()
        (self.flow.ws.stage('eco')/'editable.enc').unlink()
        (self.final/'chip_lvs.v').write_text('change')
        with self.assertRaisesRegex(ValueError, 'editable'):
            self.versions.accept()
    def test_restore_recovers_deleted_editable(self):
        baseline = self.initialize()
        shutil.rmtree(str(self.flow.ws.stage('eco')))
        self.flow.env['DISCARD'] = '1'
        with contextlib.redirect_stdout(io.StringIO()): self.versions.rollback(baseline)
        self.assertTrue((self.flow.ws.stage('eco')/'editable.enc').is_file())
        self.assertFalse(self.versions.dirty())
    def test_export_errors_keep_workspace_unavailable(self):
        self.initialize()
        eco = self.flow.ws.stage('eco')
        write_json(eco/'exported.json', 'session')
        (eco/'gui.log').write_text('<CMD> saveDesign '+str(eco/'editable.enc')+'\nNet broken: has routing with opens\n<CMD> saveDesign '+str(self.final/'design.enc')+'\n')
        with self.assertRaisesRegex(ValueError, '断线'):
            self.versions.publish_export('session')
        self.assertTrue(self.versions.pending())
        self.assertEqual(self.flow.record('chipfinish')['status'], 'FAILED')


if __name__ == '__main__':
    unittest.main()