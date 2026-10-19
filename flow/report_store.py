"""报告归集与安全解压；不遍历 Innovus 数据库或工具软链接。"""
import gzip
import os
from pathlib import Path
import shutil
import tarfile
import time
import uuid
import zipfile
from state import no_links, read_json, write_json

PNR = ('init', 'floorplan', 'powerplan', 'placement', 'cts', 'route', 'chipfinish')


def unpack(path):
    """保留压缩原件，文本 gzip 每次刷新；归档禁止链接和路径越界。"""
    path = no_links(path)
    archive = path.name.endswith(('.tar.gz', '.tgz', '.tar', '.zip'))
    if not archive:
        if path.suffix == '.gz':
            target = no_links(path.with_suffix(''))
            with gzip.open(str(path), 'rb') as source, target.open('wb') as output:
                shutil.copyfileobj(source, output)
        return
    destination = no_links(path.parent/(path.name+'.unpacked'))
    if destination.exists():
        shutil.rmtree(str(destination))
    destination.mkdir()
    def target(name):
        relative = Path(name.replace('\\', '/'))
        if relative.is_absolute() or '..' in relative.parts or ':' in name:
            raise ValueError('压缩包包含越界路径：'+name)
        result = no_links(destination/relative)
        result.parent.mkdir(parents=True, exist_ok=True)
        return result
    if path.suffix == '.zip':
        with zipfile.ZipFile(str(path)) as source:
            for entry in source.infolist():
                if (entry.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError('报告压缩包不允许软链接：'+entry.filename)
                output = target(entry.filename)
                if entry.filename.endswith('/'):
                    output.mkdir(exist_ok=True)
                else:
                    with source.open(entry) as inp, output.open('wb') as out:
                        shutil.copyfileobj(inp, out)
    else:
        with tarfile.open(str(path), 'r:*') as source:
            for entry in source:
                output = target(entry.name)
                if entry.isdir():
                    output.mkdir(exist_ok=True)
                elif entry.isfile():
                    with source.extractfile(entry) as inp, output.open('wb') as out:
                        shutil.copyfileobj(inp, out)
                else:
                    raise ValueError('报告压缩包不允许链接或特殊文件：'+entry.name)


def collect(flow, stage, directory=None, revision=None):
    source = directory or flow.ws.stage(stage)
    if not source.exists():
        return
    root = no_links(flow.root/'reports'/flow.cfg['DESIGN_NAME']/flow.cfg['TECH'])
    relative = Path('innovus')/stage if stage in PNR else Path(stage)
    if stage == 'eco':
        relative /= revision or 'draft'
    destination = no_links(root/relative)
    if destination.exists():
        archive = no_links(root/'history'/(time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])/relative)
        archive.parent.mkdir(parents=True)
        destination.rename(archive)
    destination.mkdir(parents=True)
    errors = []
    for current, directories, files in os.walk(str(source), followlinks=False):
        directories[:] = [n for n in directories if not n.endswith('.enc.dat') and
                          n not in ('history', 'record-history', 'sessions', '.git') and
                          not (Path(current)/n).is_symlink()]
        for name in files:
            path = Path(current)/name
            if path.is_symlink():
                continue
            rel = path.relative_to(source)
            in_reports = any(p in ('reports', 'timingReports') for p in rel.parts)
            report = in_reports or name.endswith(('.rpt', '.rep', '.report', '.summary', '.log', '.rpt.gz', '.summary.gz'))
            if not report:
                continue
            # 合并 reports 与 timingReports 入口，但保留其它相对层次（例如 PT corner）。
            parts = [p for p in rel.parts if p != 'reports']
            output = no_links(destination.joinpath(*parts))
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(path), str(output))
    # 全部复制后再解压，旧文本不能覆盖新解压结果。
    for path in list(destination.rglob('*')):
        if path.is_file() and path.name.endswith(('.gz', '.zip', '.tar', '.tgz')):
            try:
                unpack(path)
            except (OSError, ValueError, EOFError, tarfile.TarError, zipfile.BadZipFile) as exc:
                errors.append(str(exc))
    write_json(destination/'来源.json', dict(stage=stage, source=str(source),
               selected=read_json(flow.ws.base/'active-final.json'), revision=revision,
               collected=time.time(), errors=errors, result=read_json(source/'result.json'),
               workspace=read_json(flow.ws.base/'versions-v2/observed.json')))
    if errors:
        raise ValueError('报告解压失败：'+'; '.join(errors))


def refresh(flow):
    from state import STAGES
    with flow.require_workspace().lock():
        from workspace_versions import Versions
        Versions(flow).observe()
        for stage in STAGES:
            if stage == 'eco' and read_json(flow.ws.base/'active-final.json').get('workspace_format') == 2:
                collect(flow, stage, flow.ws.stage('chipfinish'), 'working')
            elif stage == 'eco' and flow.final_stage() == 'eco':
                selection = read_json(flow.ws.base/'active-final.json')
                collect(flow, stage, flow.final_directory(), selection.get('revision'))
            else:
                collect(flow, stage)
    print('报告已归集到 reports/{}/{}/；请核对来源.json 的版本与状态。'.format(flow.cfg['DESIGN_NAME'], flow.cfg['TECH']))