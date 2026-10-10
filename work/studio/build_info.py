"""Small, local build identity for reproducible session reports."""
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import sys

APP_VERSION = '0.4.0'
POLICY_REVISION = 'native-priority-similar-fine-scale-v15'


def source_identity(root):
    """Hash production Python sources only; never include settings or captures."""
    digest = hashlib.sha256()
    root=Path(root)
    files=list(root.glob('*.py'))+list((root/'native_live').rglob('*.py'))
    files+=list((root/'native_live/assets').glob('*'))
    for path in sorted(p for p in files if p.is_file()):
        if path.name.startswith('test_'):
            continue
        digest.update(path.relative_to(root).as_posix().encode('utf-8') + b'\0')
        digest.update(path.read_bytes())
    return dict(app_version=APP_VERSION, policy_revision=POLICY_REVISION,
                source_sha256=digest.hexdigest())


@lru_cache(maxsize=1)
def runtime_identity():
    root = Path(__file__).resolve().parent
    if getattr(sys, 'frozen', False):
        try:
            value = json.loads((Path(sys._MEIPASS) / 'build-info.json').read_text(encoding='utf-8'))
            if isinstance(value, dict) and value.get('app_version') == APP_VERSION:
                return {key: value.get(key) for key in
                        ('app_version', 'policy_revision', 'source_sha256', 'git_commit')}
        except (OSError, ValueError, AttributeError):
            pass
        return dict(app_version=APP_VERSION, policy_revision=POLICY_REVISION,
                    source_sha256=None)
    try:
        return source_identity(root)
    except OSError:
        return dict(app_version=APP_VERSION, policy_revision=POLICY_REVISION,
                    source_sha256=None)
