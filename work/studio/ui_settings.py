"""Small UI preferences file; preserve unrelated settings on each update."""
import json
from pathlib import Path


def read_settings(path):
    try:
        value=json.loads(Path(path).read_text(encoding='utf-8'))
        return value if isinstance(value,dict) else {}
    except (OSError,ValueError):return {}


def save_settings(path,**updates):
    path=Path(path);data=read_settings(path);data.update(updates)
    try:
        path.parent.mkdir(parents=True,exist_ok=True)
        temp=path.with_suffix('.tmp');temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        temp.replace(path)
    except OSError:pass
