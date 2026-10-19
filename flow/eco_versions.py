"""独立 Git 数据库：保存成套检查点，使用父提交回退，不覆盖历史。"""
import io
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import time
import uuid
import reports
import report_store
from state import no_links, read_json, write_json, files_hash


def export_log(directory, final_directory=None):
    """从最后一次成套导出的 editable 保存起点核验，保留原会话日志。"""
    log = directory/'gui.log'
    lines = log.read_text(encoding='utf-8', errors='replace').splitlines(True)
    def saves(name, base=None):
        expected = str((base or directory)/name)
        return [i for i, line in enumerate(lines)
                if line.startswith('<CMD> saveDesign ') and
                line[len('<CMD> saveDesign '):].strip().strip('{}"') == expected]
    editable, final = saves('editable.enc'), saves('design.enc', final_directory)
    if not final or not any(i < final[-1] for i in editable):
        raise ValueError('日志缺少完整导出的检查点保存记录，请重新 eco_export')
    start = max(i for i in editable if i < final[-1])
    output = no_links(directory/'accept-export.log')
    output.write_text(''.join(lines[start:]), encoding='utf-8')
    # 连接断开不能作为普通几何 DRC 放行；dangling 单独留给报告审核。
    opens = [line.strip() for line in lines[start:] if re.search(r'^Net .+:.*\bopens\b', line)]
    if opens:
        raise ValueError('导出结果存在断线：'+'; '.join(opens))
    return output

class Versions:
    def __init__(self, flow):
        self.flow = flow
        self.root = no_links(flow.require_workspace().base/'versions')
        self.repo = no_links(self.root/'repository.git')

    def git(self, args, directory=None, index=None, data=None):
        env = dict(os.environ)
        for key in list(env):
            if key.startswith('GIT_'):
                del env[key]
        env.update(GIT_AUTHOR_NAME='IC ECO', GIT_AUTHOR_EMAIL='eco@localhost',
                   GIT_COMMITTER_NAME='IC ECO', GIT_COMMITTER_EMAIL='eco@localhost')
        command = ['git', '--git-dir='+str(self.repo)]
        if directory is not None:
            command += ['--work-tree='+str(directory)]
        if index is not None:
            env['GIT_INDEX_FILE'] = str(index)
        proc = subprocess.Popen(command+args, cwd=str(directory or self.root), env=env, stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = proc.communicate(data)
        if proc.returncode:
            raise ValueError('Git 版本操作失败：'+err.decode('utf-8', 'replace'))
        return out.decode('utf-8', 'replace').strip()

    def init(self):
        self.root.mkdir(parents=True, exist_ok=True)
        if not self.repo.exists():
            subprocess.check_call(['git', 'init', '--bare', str(self.repo)])

    def resolve(self, revision):
        if not re.fullmatch(r'[0-9a-fA-F]{7,40}', revision or ''):
            raise ValueError('版本号需要 eco-history 中的提交编号（至少 7 位）')
        return self.git(['rev-parse', '--verify', revision+'^{commit}'])

    def metadata(self, revision):
        import json
        revision = self.resolve(revision)
        data = json.loads(self.git(['show', revision+':version.json']))
        token = data.get('token', '')
        if not re.fullmatch(r'[0-9a-f]{32}', token):
            raise ValueError('版本元数据中的路径标识无效')
        return data

    def directory(self, revision):
        meta = self.metadata(revision)
        directory = no_links(self.root/'revisions'/meta['token'])
        if not (directory/'version.json').is_file():
            # 缓存丢失时从 Git 对象恢复；拒绝恢复到已有的半成品目录。
            if directory.exists():
                raise ValueError('版本缓存不完整，请先移走该目录再重试：'+str(directory))
            directory.mkdir(parents=True)
            data = subprocess.check_output(['git', '--git-dir='+str(self.repo), 'archive', self.resolve(revision)])
            with tarfile.open(fileobj=io.BytesIO(data), mode='r:') as archive:
                for entry in archive:
                    relative = Path(entry.name)
                    if relative.is_absolute() or '..' in relative.parts:
                        raise ValueError('Git 归档路径无效')
                    target = no_links(directory/relative)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if entry.isdir():
                        target.mkdir(exist_ok=True)
                    elif entry.issym():
                        link = Path(entry.linkname)
                        if not link.is_absolute() or self.flow.tech.resolve() not in link.resolve().parents:
                            raise ValueError('版本库链接不属于工艺库')
                        target.symlink_to(link)
                    elif entry.isfile():
                        with archive.extractfile(entry) as inp, target.open('wb') as out:
                            shutil.copyfileobj(inp, out)
                    else:
                        raise ValueError('Git 归档包含不支持的条目')
        if read_json(directory/'version.json') != meta:
            raise ValueError('版本快照与 Git 元数据不一致')
        return directory

    def copy_tree(self, source, target):
        source, target = Path(source), no_links(target)
        if source.is_symlink():
            resolved = source.resolve()
            allowed = (self.flow.tech.resolve(), self.flow.ws.base.resolve())
            if not resolved.is_file() or not any(root in resolved.parents for root in allowed):
                raise ValueError('检查点包含不可归档链接：'+str(source))
            target.parent.mkdir(parents=True, exist_ok=True)
            # 工艺库保持链接；工作目录中的小型恢复脚本实体化，避免上游清理使历史失效。
            if self.flow.tech.resolve() in resolved.parents:
                target.symlink_to(resolved)
            else:
                shutil.copy2(str(resolved), str(target))
        elif source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            for child in source.iterdir():
                self.copy_tree(child, target/child.name)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(source), str(target))

    def checkpoint_copy(self, checkpoint, directory):
        checkpoint = Path(checkpoint)
        if not checkpoint.is_file() or not Path(str(checkpoint)+'.dat').is_dir():
            raise ValueError('检查点不完整：'+str(checkpoint))
        self.copy_tree(Path(str(checkpoint)+'.dat'), directory/'design.enc.dat')
        # 原 Innovus loader 以自身路径定位数据库；重命名时同步替换 basename。
        text = checkpoint.read_text(encoding='utf-8')
        text = text.replace(checkpoint.name+'.dat', 'design.enc.dat')
        (directory/'design.enc').write_text(text, encoding='utf-8')

    def snapshot(self, editable, final, message, parent=None, session=None):
        self.init()
        token = uuid.uuid4().hex
        directory = no_links(self.root/'revisions'/token)
        directory.mkdir(parents=True)
        self.checkpoint_copy(editable, directory/'editable')
        self.checkpoint_copy(final/'design.enc', directory/'final')
        for artifact in self.flow.outputs('chipfinish', final):
            path = Path(artifact)
            if not path.is_absolute():
                path = final/path
            relative = path.relative_to(final)
            if relative.parts[0] == 'design.enc' or relative.parts[0] == 'design.enc.dat':
                continue
            self.copy_tree(path, directory/'final'/relative)
        for name in ('reports', 'timingReports', 'config.tcl', 'gui.log', 'tool.log', 'accept-export.log'):
            if (final/name).exists():
                self.copy_tree(final/name, directory/'final'/name)
        self.copy_tree(self.flow.root/'scripts', directory/'scripts')
        meta = dict(token=token, parent=parent, message=message, session=session,
                    design=self.flow.cfg['DESIGN_NAME'], tech=self.flow.cfg['TECH'], created=time.time())
        write_json(directory/'version.json', meta)
        summary = reports.collect('chipfinish', directory/'final')
        if (final/'accept-export.log').is_file():
            summary.update(reports.messages([final/'accept-export.log'] + list((final/'reports').glob('*.rpt'))))
        summary.update(stage='eco', status='OK')
        record = dict(stage='eco', status='OK', artifacts=self.flow.outputs('chipfinish', directory/'final'),
                      summaries=[summary], finished=time.time())
        write_json(directory/'final/result.json', record)
        index = self.root/('index-'+token)
        try:
            self.git(['read-tree', '--empty'], directory, index)
            self.git(['add', '-f', '--', '.'], directory, index)
            tree = self.git(['write-tree'], directory, index)
            args = ['commit-tree', tree] + (['-p', parent] if parent else [])
            revision = self.git(args, data=(message+'\n').encode('utf-8'))
            # 每个提交保留独立引用，即使回退后另开分支，历史仍可列出。
            self.git(['update-ref', 'refs/heads/version-'+token, revision])
        finally:
            if index.exists():
                index.unlink()
        return revision

    def selected(self):
        selection = read_json(self.flow.ws.base/'active-final.json')
        return selection.get('revision') if selection.get('git_version') else None

    def select(self, revision):
        revision = self.resolve(revision)
        directory = self.directory(revision)
        self.flow.outputs('chipfinish', directory/'final')
        self.flow.invalidate_final_consumers('切换最终版本：'+revision[:12])
        write_json(self.flow.ws.base/'active-final.json', dict(stage='eco', revision=revision, git_version=True))
        write_json(self.flow.ws.base/'latest.json', dict(stage='eco'))
        self.flow.memo.clear()
        print('当前版本：'+revision[:12]+'；下游报告与结果需要重新生成。')

    def baseline(self):
        info = read_json(self.root/'baseline.json')
        if info.get('revision'):
            return info['revision']
        if not self.flow.valid('route') or not self.flow.valid('chipfinish'):
            raise ValueError('请先完成 route 和 chipfinish，再建立 ECO 基线')
        revision = self.snapshot(self.flow.checkpoint('route'), self.flow.ws.stage('chipfinish'), '基线：自动布线与收尾')
        write_json(self.root/'baseline.json', dict(revision=revision))
        return revision

    def start(self):
        f = self.flow
        revision = self.selected() or self.baseline()
        base = self.directory(revision)
        workspace = f.ws.stage('eco')
        workspace.mkdir(parents=True, exist_ok=True)
        pointer = read_json(workspace/'current-session.json')
        token = pointer.get('token', '')
        if not re.fullmatch(r'[0-9a-f]{32}', token):
            token = ''
        directory = workspace/'sessions'/token if token else None
        session = read_json(directory/'session.json') if directory else {}
        already_committed = self.selected() and self.metadata(self.selected()).get('session') == token
        if not directory or session.get('parent') != revision or session.get('accepted') or already_committed:
            token = uuid.uuid4().hex
            directory = no_links(workspace/'sessions'/token)
            directory.mkdir(parents=True)
            session = dict(token=token, parent=revision)
        (directory/'reports').mkdir(exist_ok=True)
        checkpoint = directory/'editable.enc'
        if not checkpoint.is_file():
            checkpoint = base/'editable/design.enc'
        f.config_tcl(directory, 'chipfinish')
        f.mmmc(directory)
        write_json(directory/'session.json', session)
        write_json(workspace/'current-session.json', dict(token=token))
        # 打开新会话不改变已接受结果，也不覆盖版本数据库。
        from flow import put, tcl
        script = ('source config.tcl\nsource [file join $FLOW_DIR common.tcl]\n'
                  'source '+tcl(checkpoint)+'\n'
                  'set ECO_DIR '+tcl(directory)+'\nset ECO_TOKEN '+tcl(token)+'\n'
                  'source [file join $FLOW_DIR eco.tcl]\neco_save\n'
                  'if {$CALIBRE_INNOVUS_TCL ne ""} {source $CALIBRE_INNOVUS_TCL}\nwin on\n')
        put(directory/'edit.tcl', script)
        print('ECO 父版本：'+revision[:12]+'；打开 finish 前检查点：'+str(checkpoint), flush=True)
        print('完成后执行 eco_export {备注}，退出后执行 make eco-accept。', flush=True)
        try:
            f.command('INNOVUS', ['-log', 'gui', '-overwrite', '-files', 'edit.tcl'], directory, 'gui.log', interactive=True)
        finally:
            report_store.collect(f, 'eco', directory, 'draft-'+token)

    def accept(self):
        f = self.flow
        pointer = read_json(f.ws.stage('eco')/'current-session.json')
        token = pointer.get('token', '')
        if not re.fullmatch(r'[0-9a-f]{32}', token):
            raise ValueError('没有新框架的 ECO 会话；请运行 make eco')
        directory = no_links(f.ws.stage('eco')/'sessions'/token)
        session = read_json(directory/'session.json')
        current = self.selected()
        if current and self.metadata(current).get('session') == token:
            session['accepted'] = current
            write_json(directory/'session.json', session)
        if session.get('accepted'):
            print('该会话已提交：'+session['accepted']); return
        marker = directory/'exported.json'
        if read_json(marker) != token:
            raise ValueError('请先在本次 Innovus 会话执行 eco_export {备注}')
        parent = self.selected() or self.baseline()
        if session.get('parent') != parent:
            raise ValueError('当前版本已切换，请从当前版本重新开始 ECO')
        artifacts = f.outputs('chipfinish', directory)
        editable = directory/'editable.enc'
        if not editable.is_file() or not (directory/'editable.enc.dat').is_dir():
            raise ValueError('缺少 finish 前检查点')
        saved = [Path(p) for p in artifacts] + [editable]
        saved += [p for p in (directory/'editable.enc.dat').rglob('*') if p.is_file()]
        if any(p.stat().st_mtime > marker.stat().st_mtime for p in saved):
            raise ValueError('导出后检查点或文件又发生变化，请重新 eco_export')
        result = reports.collect('chipfinish', directory)
        messages = reports.messages([export_log(directory)] + list((directory/'reports').glob('*.rpt')))
        if messages['errors'] or result['timing_status'] == 'INCOMPLETE':
            details = messages['errors'][:4]
            if result['timing_status'] == 'INCOMPLETE': details.append('缺少完整 setup/hold 时序汇总')
            raise ValueError('ECO 导出核验失败：'+'; '.join(details))
        message_file = directory/'message.txt'
        message = message_file.read_text(encoding='utf-8').strip() if message_file.exists() else '手工 ECO'
        revision = self.snapshot(editable, directory, message or '手工 ECO', parent, token)
        # 提交已持久化后才切换；重复执行不会生成第二个提交。
        self.select(revision)
        session['accepted'] = revision
        write_json(directory/'session.json', session)
        report_store.collect(f, 'eco', self.directory(revision)/'final', revision)

    def rollback(self, revision=None, original=False):
        current = self.selected()
        if original:
            revision = self.baseline()
        elif not revision:
            if not current:
                raise ValueError('当前尚未选择 Git ECO 版本')
            revision = self.metadata(current).get('parent')
            if not revision:
                raise ValueError('已经是基线，没有上一版')
        self.select(revision)
        # 回退后不复用旧会话草稿；目录保留但取消当前会话指针。
        pointer = self.flow.ws.stage('eco')/'current-session.json'
        if pointer.exists():
            pointer.unlink()

    def history(self):
        if not self.repo.exists():
            print('尚无 ECO 版本；首次 make eco 自动建立基线。'); return
        print('当前版本：'+str(self.selected() or '原始 chipfinish'))
        print(self.git(['log', '--all', '--date=iso', '--format=%h %p %ad %s']))