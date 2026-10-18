"""Fixed workspace boundaries, content fingerprints and exclusive stage access."""
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat

STAGES = ('sim', 'cov', 'dc', 'formal', 'postsim', 'postsim_sdf', 'init',
          'floorplan', 'powerplan', 'placement', 'cts', 'route', 'chipfinish',
          'merge', 'lvs-input', 'rc', 'pt', 'drc', 'lvs', 'eco', 'hcell')

def identifier(value, label):
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.-]*', value or ''):
        raise ValueError('{} must be a nonempty simple identifier'.format(label))
    return value

def no_links(path):
    path = Path(path).absolute()
    for node in (path, *path.parents):
        if node.is_symlink() or (node.exists() and getattr(node.lstat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('Refusing symlink/junction: {}'.format(node))
    return path

def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def files_hash(paths):
    result = {}
    for path in sorted(set(map(Path, paths))):
        nodes = sorted(path.rglob('*')) if path.is_dir() else [path]
        for node in nodes:
            if '__pycache__' in node.parts:
                continue
            if node.is_file():
                result[str(node)] = digest(node)
            elif not node.exists():
                result[str(node)] = 'MISSING'
    return result

def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}

def write_json(path, value):
    path = Path(path)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')
    temp.replace(path)

class Workspace:
    def __init__(self, root, design, tech):
        self.root = no_links(root)
        self.base = self.root / 'work' / identifier(design, 'DESIGN_NAME') / identifier(tech, 'TECH')
        no_links(self.base)

    def stage(self, name):
        if name not in STAGES:
            raise ValueError('Unknown stage: ' + name)
        return no_links(self.base / name)

    @contextlib.contextmanager
    def lock(self):
        no_links(self.base)
        self.base.mkdir(parents=True, exist_ok=True)
        lock = self.base / '.lock'
        try:
            fd = os.open(str(lock), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            raise ValueError('Workspace locked: {} (check owner before removing a stale lock)'.format(lock))
        try:
            os.write(fd, ('pid={} host={}\n'.format(os.getpid(), os.environ.get('HOSTNAME', os.environ.get('COMPUTERNAME', '?')))).encode())
            os.close(fd)
            yield
        finally:
            lock.unlink()

    def require_real_tree(self, stage):
        """Strict destination check before copying/writing into an existing tree."""
        path = self.stage(stage)
        if path.exists():
            for node in path.rglob('*'):
                no_links(node)
        return path

    def require_record_directory(self, stage):
        """Protect metadata writes without rejecting tool links in other subtrees."""
        directory = self.stage(stage)
        for name in ('result.json', 'result.json.tmp', 'record-history'):
            no_links(directory/name)
        history = directory/'record-history'
        if history.is_dir():
            for node in history.rglob('*'):
                no_links(node)
        return directory

    def require_checkpoint_tree(self, stage, technology):
        """Permit Innovus library file links only inside .enc.dat/libs trees."""
        path = self.stage(stage)
        roots = (no_links(technology).resolve(), self.base.resolve())
        if path.exists():
            for current, directories, files in os.walk(path, followlinks=False):
                for name in directories + files:
                    node = Path(current)/name
                    if node.is_symlink():
                        parts = node.relative_to(path).parts
                        library_link = any(part.endswith('.enc.dat') and
                                           index+1 < len(parts) and parts[index+1] == 'libs'
                                           for index, part in enumerate(parts))
                        target = node.resolve()
                        inside = any(target == root or root in target.parents for root in roots)
                        if library_link and inside and target.is_file():
                            continue
                    no_links(node)
        return path

    def remove(self, stage, preview=False):
        # The stage directory and every ancestor must remain real directories.
        path = self.stage(stage)
        if path.exists():
            if not path.is_dir():
                raise ValueError('Stage is not a directory: ' + str(path))
            # Tool-generated symlinks inside a stage are normal. Never walk into
            # their targets, including external directories and dangling links.
            for directory, dirs, files in os.walk(path, followlinks=False):
                for name in dirs + files:
                    node = Path(directory) / name
                    info = node.lstat()
                    if stat.S_ISLNK(info.st_mode):
                        continue
                    # Keep rejecting Windows junctions/other reparse points.
                    if getattr(info, 'st_file_attributes', 0) & 0x400:
                        raise ValueError('Refusing junction/reparse point: {}'.format(node))
            if os.name == 'posix' and not getattr(shutil.rmtree, 'avoids_symlink_attacks', False):
                raise ValueError('Safe cleanup requires fd-based shutil.rmtree on this platform')
            if not preview:
                # rmtree unlinks child symlinks; it does not delete their targets.
                shutil.rmtree(path)
        return path
