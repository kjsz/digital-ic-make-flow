"""交付文件快照：无 EDA 依赖，缺项跳过，不推断签核状态。"""
import hashlib
from pathlib import Path
import shutil
import time
import uuid
import zipfile
from state import identifier, no_links, read_json, write_json


def package(flow):
    design, tech = flow.cfg.get('DESIGN_NAME', ''), flow.cfg.get('TECH', '')
    source, selection = None, {}
    try:
        identifier(design, 'DESIGN_NAME')
        identifier(tech, 'TECH')
        if flow.ws is not None:
            selection = read_json(flow.ws.base/'active-final.json')
            if selection.get('git_version'):
                from eco_versions import Versions
                versions = Versions(flow)
                meta = versions.metadata(selection.get('revision'))
                # 只查看当前快照目录，不恢复 Git 缓存，不替用户生成上游结果。
                source = versions.root/'revisions'/meta['token']/'final'
            else:
                source = flow.ws.stage(flow.final_stage())
    except (OSError, ValueError, RuntimeError) as exc:
        print('提示：当前版本不可读取，将跳过缺失交付文件：'+str(exc))
    try:
        identifier(design, 'DESIGN_NAME')
    except ValueError:
        design = 'unconfigured-design'
    try:
        identifier(tech, 'TECH')
    except ValueError:
        tech = 'unconfigured-tech'
    token = time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]
    destination = no_links(flow.root/'output'/design/tech/token)
    destination.mkdir(parents=True)
    names = [design+suffix for suffix in ('.v', '_lvs.v', '.sdc', '.sdf', '.def', '.lef', '.gds')] + ['hcell_list']
    entries = []
    for name in names:
        path = source/name if source else None
        entry = dict(file=name, source=str(path) if path else None, status='skipped')
        try:
            if path is None or not path.is_file():
                entry['reason'] = '当前版本中不存在'
            else:
                target = no_links(destination/name)
                shutil.copy2(str(path), str(target))
                digest = hashlib.sha256()
                with target.open('rb') as stream:
                    for block in iter(lambda: stream.read(1024*1024), b''):
                        digest.update(block)
                entry.update(status='copied', bytes=target.stat().st_size, sha256=digest.hexdigest())
        except OSError as exc:
            partial = destination/name
            if partial.is_file(): partial.unlink()
            entry['reason'] = str(exc)
        entries.append(entry)
        print(('已收集：' if entry['status'] == 'copied' else '跳过：')+name+('（'+entry.get('reason', '')+'）' if entry['status'] != 'copied' else ''))
    write_json(destination/'manifest.json', dict(design=design, tech=tech, version=selection,
               source=str(source) if source else None, created=time.time(), files=entries,
               note='仅收集当前版本已存在文件，不运行上游，不证明 DRC/LVS/时序通过。'))
    archive = no_links(destination.with_suffix('.zip'))
    with zipfile.ZipFile(str(archive), 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as stream:
        for path in destination.iterdir():
            if path.is_file():
                stream.write(str(path), destination.name+'/'+path.name)
    print('交付目录：'+str(destination))
    print('压缩包：'+str(archive))