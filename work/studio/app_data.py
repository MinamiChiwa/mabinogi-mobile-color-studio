"""Choose a writable location for per-user application data."""
import os
import shutil
import tempfile
import uuid
from pathlib import Path


PERSISTENT_FILES = ('settings.json', 'profile.json', 'presets.json', 'history.json')
APP_DATA_NAME = 'MabinogiMobileColorStudio'


def _prepare_directory(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    probe = path / f'.write-check-{uuid.uuid4().hex}'
    try:
        with probe.open('xb') as stream:
            stream.write(b'ColorStudio')
    finally:
        try:
            probe.unlink(missing_ok=True)
        except OSError:
            pass
    return path


def _copy_user_data(source, destination):
    if source == destination or not source.is_dir():
        return
    for name in PERSISTENT_FILES:
        old = source / name
        new = destination / name
        if old.is_file() and not new.exists():
            try:
                shutil.copy2(old, new)
            except OSError:
                pass


def resolve_data_directory(preferred, local_app_data=None, temp_root=None):
    """Use the portable directory when writable, then per-user and temp storage."""
    preferred = Path(preferred)
    if local_app_data is None:
        local_app_data = os.environ.get('LOCALAPPDATA')
    if temp_root is None:
        temp_root = tempfile.gettempdir()

    candidates = [preferred]
    if local_app_data:
        candidates.append(Path(local_app_data) / APP_DATA_NAME / 'data')
    if temp_root:
        candidates.append(Path(temp_root) / APP_DATA_NAME / 'data')

    seen = set()
    errors = []
    for candidate in candidates:
        key = os.path.normcase(os.path.abspath(candidate))
        if key in seen:
            continue
        seen.add(key)
        try:
            selected = _prepare_directory(candidate)
        except OSError as exc:
            errors.append(f'{candidate}: {exc}')
            continue
        if selected != preferred:
            _copy_user_data(preferred, selected)
        return selected

    detail = '; '.join(errors)
    raise RuntimeError(f'Unable to create a writable data directory. {detail}')
