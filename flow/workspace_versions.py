"""工作区优先的 ECO：验证未提交修改，Git 只存历史，不作为当前工具输入。"""
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import time
import uuid

from eco_versions import Versions as LegacyVersions
from eco_versions import export_log
from state import digest, files_hash, no_links, read_json, write_json
import reports
import report_store

CONSUMERS = ('merge', 'hcell', 'lvs-input', 'rc', 'pt', 'postsim', 'postsim_sdf', 'drc', 'lvs')
EXCLUDED = ('reports', 'timingReports', 'record-history', '__pycache__')
EPHEMERAL = ('result.json', 'tool.done', 'run.tcl', 'open.tcl', 'edit.tcl', 'exported.json', 'message.txt', 'accept-export.log')


class Versions(LegacyVersions):
    def __init__(self, flow):
        self.flow = flow
        self.root = no_links(flow.require_workspace().base/'versions-v2')
        self.repo = no_links(self.root/'repository.git')
        self.state = self.root/'state.json'

    def ready(self):
        return read_json(self.state).get('format') == 2

    def selected(self):
        return read_json(self.state).get('revision')

    def legacy_selected(self):
        info = read_json(self.flow.ws.base/'active-final.json')
        return info.get('git_version') and info.get('workspace_format') != 2

    def metadata(self, revision):
        revision = self.resolve(revision)
        meta = json.loads(self.git(['show', revision+':version.json']))
        if meta.get('format') != 2:
            raise ValueError('不是新版工作区提交；旧历史可用 make eco-history LEGACY=1 查看')
        return meta

    def handoff(self):
        f = self.flow
        directory = f.ws.stage('chipfinish')
        names = [f.cfg['DESIGN_NAME']+suffix for suffix in ('.v', '_lvs.v', '.sdc', '.sdf', '.def', '.lef', '.gds')]
        names += ['hcell_list', 'add_pg_text.tcl']
        return {name: digest(directory/name) if (directory/name).is_file() else None for name in names}

    def fingerprint(self, path):
        # 工作目录中的辅助文件链接归档时会实体化，因此按内容比较；工艺库链接保留。
        if path.is_symlink() and self.flow.tech.resolve() in path.resolve().parents:
            return 'link:'+str(path.resolve())
        return digest(path)
    def payload(self):
        """当前可提交内容；不将验证报告/日志写入 dirty 判断。"""
        f = self.flow
        result = {}
        final = f.ws.stage('chipfinish')
        if final.exists():
            for current, directories, files in os.walk(str(final), followlinks=False):
                directories[:] = [name for name in directories if name not in EXCLUDED]
                for name in files:
                    path = Path(current)/name
                    if name in EPHEMERAL or name.endswith(('.log', '.logv', '.rpt', '.summary')):
                        continue
                    relative = path.relative_to(f.ws.base).as_posix()
                    if path.is_file():
                        result[relative] = self.fingerprint(path)
        eco = f.ws.stage('eco')
        for source in (eco/'editable.enc', eco/'editable.enc.dat'):
            if not source.exists():
                continue
            paths = source.rglob('*') if source.is_dir() else [source]
            for path in paths:
                if path.is_file():
                    result[path.relative_to(f.ws.base).as_posix()] = self.fingerprint(path)
        return result

    def dirty(self):
        if not self.ready():
            return False
        return self.payload() != read_json(self.state).get('payload', {}) or self.pending()

    def pending(self):
        return (self.flow.ws.stage('eco')/'draft-pending').exists()

    def observe(self):
        """只按最终交付内容判定下游缓存，touch 不影响结果，提交本身不使结果失效。"""
        if not self.ready():
            return []
        info = read_json(self.root/'observed.json')
        current = self.handoff()
        previous = info.get('files', {})
        changed = [name for name in current if current[name] != previous.get(name)]
        targets = set()
        design = self.flow.cfg['DESIGN_NAME']
        mapping = {
            design+'.gds': ('merge', 'drc', 'lvs-input', 'lvs'),
            design+'_lvs.v': ('lvs-input', 'lvs'),
            design+'.v': ('pt', 'postsim_sdf'),
            design+'.sdc': ('pt',),
            design+'.sdf': ('postsim_sdf',),
            design+'.def': ('rc', 'pt'),
            'hcell_list': ('hcell', 'lvs-input', 'lvs'),
            'add_pg_text.tcl': ('lvs-input', 'lvs'),
        }
        for name in changed:
            targets.update(mapping.get(name, ()))
        if design+'.v' in changed and self.flow.cfg['GATE_STAGE'] == 'chipfinish':
            targets.add('postsim')
        self.invalidate(targets, '工作区文件内容变化：'+', '.join(changed))
        if changed or not info:
            write_json(self.root/'observed.json', dict(files=current, changed=changed, time=time.time()))
        return changed

    def invalidate(self, names, reason):
        token = uuid.uuid4().hex
        for name in sorted(names):
            record = self.flow.record(name)
            if record and record.get('status') != 'INVALIDATED':
                directory = self.flow.ws.require_record_directory(name)
                history = directory/'record-history'
                history.mkdir(exist_ok=True)
                write_json(history/(token+'.json'), record)
                record.update(status='INVALIDATED', reason=reason)
                write_json(directory/'result.json', record)
        self.flow.memo.clear()

    def before(self, stage):
        if self.legacy_selected() and (stage == 'chipfinish' or stage in CONSUMERS):
            raise ValueError('当前仍指向旧版本；请先 make eco-init 将当前成套文件复制到工作区，旧历史保持原样')
        if not self.ready():
            return
        self.observe()
        if stage in CONSUMERS and not (stage == 'postsim' and self.flow.cfg['GATE_STAGE'] == 'dc') and self.pending():
            raise ValueError('存在尚未 eco_export 的数据库草稿；请先导出再验证，避免检查旧版最终文件')

    def inputs(self, stage):
        """只记录对应检查使用的内容，不宣称 GUI 已执行签核。"""
        values = self.handoff()
        return dict(workspace=values, base_revision=self.selected(), dirty=self.dirty())

    def _copy_payload(self, staging):
        f = self.flow
        f.ws.require_checkpoint_tree('chipfinish', f.tech)
        f.ws.require_checkpoint_tree('eco', f.tech)
        for relative in self.payload():
            self.copy_tree(f.ws.base/relative, staging/relative)
        source = f.root/'scripts'
        if source.is_dir():
            self.copy_tree(source, staging/'source-scripts')
        # 将当时的检查记录及报告一同留档，但它们不决定是否允许提交。
        evidence = staging/'verification'
        for stage in ('chipfinish',) + CONSUMERS:
            directory = f.ws.stage(stage)
            if not directory.exists():
                continue
            for current, directories, files in os.walk(str(directory), followlinks=False):
                directories[:] = [name for name in directories if name not in EXCLUDED and not name.endswith('.enc.dat') and not (Path(current)/name).is_symlink()]
                for name in files:
                    path = Path(current)/name
                    if path.is_symlink():
                        continue
                    if name == 'result.json' or name.endswith(('.rep', '.report', '.summary', '.summary.gz')):
                        self.copy_tree(path, evidence/stage/path.relative_to(directory))
            for name in ('reports', 'timingReports'):
                if (directory/name).is_dir():
                    self.copy_tree(directory/name, evidence/stage/name)

    def commit(self, message, parent=None):
        editable = self.flow.ws.stage('eco')/'editable.enc'
        if not editable.is_file() or not editable.stat().st_size or not Path(str(editable)+'.dat').is_dir():
            raise ValueError('缺少完整 editable 检查点，不能创建可恢复的版本')
        self.flow.outputs('chipfinish', self.flow.ws.stage('chipfinish'))
        self.init()
        token = uuid.uuid4().hex
        staging = no_links(self.root/'staging'/token)
        staging.mkdir(parents=True)
        payload = self.payload()
        self._copy_payload(staging)
        if payload != self.payload():
            raise ValueError('工作区在快照过程中发生变化，请停止编辑后重新提交')
        meta = dict(format=2, token=token, parent=parent, message=message, created=time.time(),
                    payload=payload, handoff=self.handoff(), design=self.flow.cfg['DESIGN_NAME'],
                    tech=self.flow.cfg['TECH'], note='文件快照，不证明数据库/网表一致或签核通过')
        write_json(staging/'version.json', meta)
        index = self.root/('index-'+token)
        try:
            self.git(['read-tree', '--empty'], staging, index)
            self.git(['add', '-f', '--', '.'], staging, index)
            tree = self.git(['write-tree'], staging, index)
            revision = self.git(['commit-tree', tree]+(['-p', parent] if parent else []), data=(message+'\n').encode('utf-8'))
            self.git(['update-ref', 'refs/heads/version-'+token, revision])
        finally:
            if index.exists(): index.unlink()
        # 只有持久化提交成功后才更新指针。
        state = read_json(self.state)
        state.update(format=2, revision=revision, baseline=state.get('baseline') or revision, payload=payload)
        write_json(self.state, state)
        self.pointer(revision)
        shutil.rmtree(str(staging))
        return revision

    def pointer(self, revision):
        write_json(self.flow.ws.base/'active-final.json', dict(stage='chipfinish', workspace_format=2, revision=revision))
        self.flow.memo.clear()

    def initialize(self):
        if self.ready():
            print('工作区版本管理已初始化：'+str(self.selected())); return self.selected()
        f = self.flow
        selection = read_json(f.ws.base/'active-final.json')
        final = f.ws.stage('chipfinish')
        editable = f.checkpoint('route')
        source = final
        if self.legacy_selected():
            old = LegacyVersions(f)
            # 只取当前旧版本作为新基线；不迁移/改写旧提交父关系。
            metadata = old.metadata(selection['revision'])
            old_directory = no_links(old.root/'revisions'/metadata['token'])
            source = old_directory/'final'
            editable = old_directory/'editable/design.enc'
            if not source.is_dir() or not editable.is_file():
                raise ValueError('当前旧版本缓存缺失。旧历史已保留；请先恢复成套工作文件后再初始化')
        f.outputs('chipfinish', source)
        if not editable.is_file() or not Path(str(editable)+'.dat').is_dir():
            raise ValueError('缺少 finish 前检查点，不能建立成对基线')
        self.init()
        backup = no_links(self.root/'migration-backup'/uuid.uuid4().hex)
        backup.mkdir(parents=True)
        write_json(backup/'active-final.json', selection)
        if source != final:
            # 使用完整临时副本后再替换，旧 chipfinish 保存为迁移备份。
            prepared = backup/'prepared-chipfinish'
            self.copy_tree(source, prepared)
            if final.exists(): final.rename(backup/'chipfinish')
            prepared.rename(final)
        eco = f.ws.stage('eco')
        eco.mkdir(parents=True, exist_ok=True)
        for name in ('editable.enc', 'editable.enc.dat'):
            if (eco/name).exists(): (eco/name).rename(backup/name)
        self.copy_tree(Path(str(editable)+'.dat'), eco/'editable.enc.dat')
        text = editable.read_text(encoding='utf-8').replace(editable.name+'.dat', 'editable.enc.dat')
        (eco/'editable.enc').write_text(text, encoding='utf-8')
        # 写入工作区的完成记录引用工作文件，绝不继续引用旧快照路径。
        record = dict(stage='chipfinish', status='OK', artifacts=f.outputs('chipfinish', final),
                      summaries=[reports.collect('chipfinish', final)], finished=time.time())
        write_json(final/'result.json', record)
        revision = self.commit('基线：当前工作区')
        write_json(self.root/'observed.json', dict(files=self.handoff(), changed=[]))
        # 旧缓存结果的来源路径不同，重新验证当前工作区。
        f.invalidate_final_consumers('初始化新版工作区；旧版本和迁移备份保持原样')
        self.accept_record(revision)
        print('新基线：'+revision[:12]+'；最终文件在 '+str(final))
        print('旧 versions/ 历史保持原样；新历史位于 versions-v2/。')
        return revision

    def accept_record(self, revision):
        directory = self.flow.ws.stage('eco')
        directory.mkdir(parents=True, exist_ok=True)
        write_json(directory/'result.json', dict(stage='eco', status='OK', revision=revision,
                   artifacts=files_hash([self.state]), finished=time.time(), note='工作区文件提交，不等于签核通过'))
        write_json(self.flow.ws.base/'latest.json', dict(stage='eco'))

    def accept(self):
        if not self.ready():
            self.initialize()
            print('首次提交仅建立基线；请在修改前初始化，以保留可回退的修改前状态。')
            return
        if self.pending():
            raise ValueError('存在未导出的数据库草稿，请先 eco_export；纯文件编辑无需启动 Innovus')
        self.observe()
        self.flow.outputs('chipfinish', self.flow.ws.stage('chipfinish'))
        if not self.dirty():
            print('工作区内容未变化，无需新建提交。'); return
        message = self.flow.env.get('MSG', '').strip()
        message_file = self.flow.ws.stage('eco')/'message.txt'
        if not message and message_file.exists(): message = message_file.read_text(encoding='utf-8').strip()
        revision = self.commit(message or '工作区修改', self.selected())
        # 提交不改变内容，不让刚完成的验证再次失效。
        self.accept_record(revision)
        print('已提交工作区：'+revision[:12]+'；已完成且输入未变的验证结果保留。')
        print('直接编辑网表不会同步修改 Innovus 数据库；需要自行确认成套一致性。')

    def start(self):
        f = self.flow
        if not self.ready(): self.initialize()
        self.observe()
        if self.dirty(): print('提示：工作区已有未提交修改；eco_export 会重新生成文本导出，请先提交或另存需保留的文件修改。')
        directory = f.ws.require_checkpoint_tree('eco', f.tech)
        checkpoint = directory/'editable.enc'
        if not checkpoint.is_file(): raise ValueError('缺少工作区 editable.enc，请恢复版本')
        token = uuid.uuid4().hex
        (directory/'reports').mkdir(exist_ok=True)
        f.config_tcl(directory, 'chipfinish')
        f.mmmc(directory)
        from flow import put, tcl
        final = f.ws.stage('chipfinish')
        final.mkdir(exist_ok=True)
        (final/'reports').mkdir(exist_ok=True)
        with (directory/'config.tcl').open('a', encoding='utf-8') as stream:
            for key, value in dict(FINAL_DIR=final, CHECKPOINT_OUT=final/'design.enc',
                                   NETLIST_OUT=final/(f.cfg['DESIGN_NAME']+'.v'),
                                   SDC_OUT=final/(f.cfg['DESIGN_NAME']+'.sdc'),
                                   SDF_OUT=final/(f.cfg['DESIGN_NAME']+'.sdf')).items():
                stream.write('set '+key+' '+tcl(value)+'\n')
        write_json(directory/'workspace-session.json', dict(token=token, parent=self.selected()))
        script = ('source config.tcl\nsource [file join $FLOW_DIR common.tcl]\nsource '+tcl(checkpoint)+'\n'
                  'set ECO_DIR '+tcl(directory)+'\nset ECO_TOKEN '+tcl(token)+'\n'
                  'source [file join $FLOW_DIR eco.tcl]\neco_save\n'
                  'if {$CALIBRE_INNOVUS_TCL ne ""} {source $CALIBRE_INNOVUS_TCL}\nwin on\n')
        put(directory/'edit.tcl', script)
        print('编辑工作区：'+str(directory)+'；eco_export 写入 '+str(final), flush=True)
        print('export 后可直接 make drc/lvs/pt；验证后再 make eco-accept MSG="备注"。', flush=True)
        failure = None
        try:
            f.command('INNOVUS', ['-log', 'gui', '-overwrite', '-files', 'edit.tcl'], directory, 'gui.log', interactive=True)
        except (OSError, RuntimeError, ValueError) as exc:
            failure = exc
        # 即使 GUI 返回非零也检查是否存在本次完整导出；真实导出错误仍保留。
        self.publish_export(token)
        report_store.collect(f, 'eco', directory, 'working')
        report_store.collect(f, 'chipfinish')
        if failure: raise failure

    def publish_export(self, token):
        f = self.flow
        directory = f.ws.stage('eco')
        if read_json(directory/'exported.json') != token:
            return
        final = f.ws.stage('chipfinish')
        result = reports.collect('chipfinish', final)
        # 精确识别本次导出两类检查点的路径，忽略导出前交互错误。
        try:
            messages = reports.messages([export_log(directory, final)] + list((final/'reports').glob('*.rpt')))
        except (ValueError, OSError) as exc:
            (directory/'draft-pending').write_text('导出核验失败，请修复后重新导出', encoding='utf-8')
            write_json(final/'result.json', dict(stage='chipfinish', status='FAILED', error=str(exc)))
            raise
        result.update(messages)
        artifacts = f.outputs('chipfinish', final)
        failed = bool(result['errors']) or result['timing_status'] == 'INCOMPLETE'
        write_json(final/'result.json', dict(stage='chipfinish', status='FAILED' if failed else 'OK',
                   artifacts=artifacts, summaries=[result], finished=time.time()))
        self.observe()
        if failed:
            (directory/'draft-pending').write_text('导出有错误或缺少时序报告', encoding='utf-8')
            raise ValueError('本次工作区导出有错误或缺少时序报告，请检查 chipfinish/reports 和 eco/gui.log')
        pending = no_links(directory/'draft-pending')
        if pending.exists(): pending.unlink()
        print('工作区导出完成，尚未提交；可以先运行下游验证。')

    def _extract(self, revision, destination):
        data = subprocess.check_output(['git', '--git-dir='+str(self.repo), 'archive', self.resolve(revision)])
        with tarfile.open(fileobj=io.BytesIO(data), mode='r:') as archive:
            for entry in archive:
                relative = Path(entry.name)
                if relative.is_absolute() or '..' in relative.parts or ':' in entry.name:
                    raise ValueError('版本归档路径无效')
                target = no_links(destination/relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                if entry.isdir(): target.mkdir(exist_ok=True)
                elif entry.issym():
                    link = Path(entry.linkname)
                    if not link.is_absolute() or self.flow.tech.resolve() not in link.resolve().parents:
                        raise ValueError('版本库链接不属于当前工艺库')
                    target.symlink_to(link)
                elif entry.isfile():
                    with archive.extractfile(entry) as inp, target.open('wb') as out: shutil.copyfileobj(inp, out)
                else: raise ValueError('版本库包含特殊文件')

    def rollback(self, revision=None, original=False):
        if not self.ready(): raise ValueError('请先 make eco-init；旧历史不会被改写')
        if self.dirty() and self.flow.env.get('DISCARD', '0') != '1':
            raise ValueError('工作区有未提交修改，请先 accept；确认放弃时使用 make eco-rollback DISCARD=1')
        state = read_json(self.state)
        revision = state['baseline'] if original else revision or self.metadata(state['revision']).get('parent')
        if not revision: raise ValueError('已是新版基线，没有上一版')
        revision = self.resolve(revision)
        meta = self.metadata(revision)
        staging = no_links(self.root/'restore'/uuid.uuid4().hex)
        staging.mkdir(parents=True)
        self._extract(revision, staging)
        final = self.flow.ws.stage('chipfinish')
        eco = self.flow.ws.stage('eco')
        eco.mkdir(parents=True, exist_ok=True)
        self.flow.outputs('chipfinish', staging/'chipfinish')
        # 先完整解包，旧工作区移入恢复备份，绝不直接覆盖半个版本。
        backup = no_links(self.root/'restore-backup'/uuid.uuid4().hex)
        backup.mkdir(parents=True)
        if final.exists(): final.rename(backup/'chipfinish')
        try:
            (staging/'chipfinish').rename(final)
            for name in ('editable.enc', 'editable.enc.dat'):
                path = eco/name
                if path.exists(): path.rename(backup/name)
                (staging/'eco'/name).rename(path)
        except BaseException:
            # 尽力回滚替换操作；中间产物也留在暂存中，不删除用户内容。
            try:
                if (backup/'chipfinish').exists():
                    if final.exists(): final.rename(staging/'interrupted-chipfinish')
                    (backup/'chipfinish').rename(final)
                for name in ('editable.enc', 'editable.enc.dat'):
                    if (backup/name).exists():
                        if (eco/name).exists(): (eco/name).rename(staging/('interrupted-'+name))
                        (backup/name).rename(eco/name)
            except OSError:
                pass
            raise ValueError('恢复中断，旧文件保留/恢复于工作区或 '+str(backup)+'；请检查后再继续')
        for name in ('draft-pending', 'exported.json', 'workspace-session.json', 'message.txt'):
            path = no_links(eco/name)
            if path.exists(): path.unlink()
        evidence = staging/'verification/chipfinish'
        for name in ('reports', 'timingReports'):
            if (evidence/name).is_dir(): self.copy_tree(evidence/name, final/name)
        write_json(final/'result.json', dict(stage='chipfinish', status='OK', artifacts=self.flow.outputs('chipfinish', final),
                   summaries=[reports.collect('chipfinish', final)], finished=time.time()))
        state.update(revision=revision, payload=meta['payload'])
        write_json(self.state, state)
        self.pointer(revision)
        self.observe()
        self.flow.invalidate_final_consumers('恢复工作区版本：'+revision[:12])
        self.accept_record(revision)
        shutil.rmtree(str(staging))
        print('工作区已恢复到 '+revision[:12]+'；下游结果需重新验证，旧历史和恢复备份保留。')

    def history(self):
        if self.flow.env.get('LEGACY') == '1':
            old = LegacyVersions(self.flow)
            if not old.repo.exists():
                print('没有旧版本历史。'); return
            print('旧历史只读展示；不改变新版工作区选择。')
            print(old.git(['log', '--all', '--date=iso', '--format=%h %p %ad %s']))
            return
        if not self.ready():
            print('尚未建立新版工作区历史。先 make eco-init；旧历史可用 LEGACY=1 查看。'); return
        print('当前基线提交：'+str(self.selected())+'；工作区：'+('已修改，未提交' if self.dirty() else '干净'))
        print(self.git(['log', '--all', '--date=iso', '--format=%h %p %ad %s']))