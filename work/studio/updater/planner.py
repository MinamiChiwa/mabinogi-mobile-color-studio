from pathlib import Path
from .paths import hash_file, safe_path, checked_root
from .types import Manifest, UpdatePlan

def plan_update(root, old, new, *, protected_paths=()):
    root=checked_root(root)
    if not isinstance(old,Manifest) or not isinstance(new,Manifest):raise ValueError('Manifest required')
    old_map={r.path.casefold():r for r in old.files};new_map={r.path.casefold():r for r in new.files}
    installs=[];removals=[];reused=[];conflicts=[];blobs={};backup=0
    protected=[(root/'data').absolute(),*(Path(p).absolute() for p in protected_paths)]
    def target(relative):
        path=safe_path(root,relative)
        if any(path==p or p in path.parents for p in protected):raise ValueError('Update targets user data')
        return path
    for row in new.files:
        path=target(row.path)
        if path.exists():
            if not path.is_file():conflicts.append(row.path);continue
            current=hash_file(path)
            if current==row.sha256:reused.append(row.path);continue
            prior=old_map.get(row.path.casefold())
            if prior is None or current!=prior.sha256:conflicts.append(row.path);continue
            backup+=path.stat().st_size
        installs.append(row.path);blobs[row.blob]=row
    for row in old.files:
        if row.path.casefold() in new_map:continue
        path=target(row.path)
        if not path.exists():continue
        if path.is_file() and hash_file(path)==row.sha256:
            removals.append(row.path);backup+=path.stat().st_size
        else:conflicts.append(row.path)
    entries={r.path:r for r in new.files}
    return UpdatePlan(tuple(installs),tuple(removals),tuple(reused),tuple(conflicts),tuple(['data',*(str(p) for p in protected[1:])]),
        tuple(sorted(blobs)),sum(r.download_size for r in blobs.values()),sum(entries[p].size for p in installs),
        backup,old.version,new.version)
