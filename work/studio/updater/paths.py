"""Never resolve through junctions or expand deletion ownership."""
import os,stat,hashlib,json,uuid
from pathlib import Path
from .manifest import ManifestError,validate_relative_path

def hash_file(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def checked_root(root):
    root=Path(os.path.abspath(root))
    if str(root).startswith('\\\\'):raise ManifestError('Network installations unsupported')
    for node in (root,*root.parents):
        if node.exists() or node.is_symlink():
            info=node.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400:
                raise ManifestError('Reparse paths unsupported')
    return root

def safe_path(root,relative,*,metadata=False):
    root=checked_root(root)
    if metadata and relative in ('update-manifest.json','update-manifest.sig','update-location.json'):pass
    else:validate_relative_path(relative)
    path=root.joinpath(*relative.split('/'))
    for node in (path,*path.parents):
        if node==root:break
        if node.exists() or node.is_symlink():
            info=node.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400:
                raise ManifestError('Reparse target unsupported')
    return path

def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with tmp.open('x',encoding='utf-8') as stream:
            json.dump(value,stream,ensure_ascii=False,sort_keys=True);stream.flush();os.fsync(stream.fileno())
        os.replace(tmp,path)
    finally:tmp.unlink(missing_ok=True)
