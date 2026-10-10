"""Atomic last-used draft and independent named dye presets."""
import copy
import json
import math
import uuid
from pathlib import Path
from vision import normalize_hex


def default_profile():
    return dict(schema=1, priority_order=[0, 1, 2], search_strategy='native',
                regions=[dict(enabled=True, target='#202020', alt='', mode='精准 HEX',
                              tolerance=8.) for _ in range(3)])


def canonical_profile(value, *, strict=False):
    if isinstance(value, list):
        value = dict(regions=value)
    if not isinstance(value, dict):
        raise ValueError('方案格式无效。')
    regions = value.get('regions')
    if not isinstance(regions, list) or len(regions) != 3:
        raise ValueError('方案必须包含三个区域。')
    order = value.get('priority_order', [0, 1, 2])
    if not isinstance(order, list) or len(order) != 3 or any(type(v) is not int for v in order) or sorted(order) != [0, 1, 2]:
        raise ValueError('区域优先级必须包含三个不同区域。')
    strategy = value.get('search_strategy', 'native')
    if strategy not in ('native', 'atlas'):
        raise ValueError('寻色方式无效。')
    clean = []
    for row in regions:
        if not isinstance(row, dict) or type(row.get('enabled')) is not bool:
            raise ValueError('区域设置无效。')
        target, alt = row.get('target'), row.get('alt', '')
        mode, tolerance = row.get('mode'), row.get('tolerance')
        if not isinstance(target, str) or not isinstance(alt, str) or len(target) > 64 or len(alt) > 2048:
            raise ValueError('颜色输入无效。')
        if mode not in ('精准 HEX', '相似颜色') or type(tolerance) not in (float, int) or not math.isfinite(tolerance) or not 1 <= tolerance <= 35:
            raise ValueError('匹配模式或色差范围无效。')
        if strict and row['enabled']:
            target = normalize_hex(target)
            alternatives = [normalize_hex(c) for c in alt.replace('，', ',').split(',') if c.strip()]
            if len(alternatives) > 63:
                raise ValueError('替代颜色最多为 63 个。')
            alt = ', '.join(alternatives)
        clean.append(dict(enabled=row['enabled'], target=target, alt=alt,
                          mode=mode, tolerance=float(tolerance)))
    if strict and not any(row['enabled'] for row in clean):
        raise ValueError('请至少启用一个区域。')
    return dict(schema=1, regions=clean, priority_order=list(order), search_strategy=strategy)


def _write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def read_profile(path, *, search_strategy='native'):
    path=Path(path)
    if not path.exists():
        value=default_profile();value['search_strategy']=search_strategy
        return value
    try:
        value=json.loads(path.read_text(encoding='utf-8'))
        if isinstance(value,list):value=dict(regions=value,search_strategy=search_strategy)
        elif isinstance(value,dict) and 'search_strategy' not in value:value=dict(value,search_strategy=search_strategy)
        return canonical_profile(value)
    except (ValueError, TypeError) as exc:
        raise ValueError('当前设置无法读取，原文件已保留。') from exc


def write_profile(path, value):
    value=canonical_profile(value);path=Path(path)
    if path.exists():
        try:read_profile(path)
        except ValueError:
            import shutil
            shutil.copy2(path,path.with_name(path.name+'.unreadable-'+uuid.uuid4().hex))
    _write(path, value)


class PresetStore:
    def __init__(self, path):
        self.path = Path(path)

    def rows(self):
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(data, dict) or data.get('schema') != 1 or not isinstance(data.get('presets'), list):
                raise ValueError('方案库格式无效。')
            rows = data['presets']; ids = set(); names = set()
            for row in rows:
                if not isinstance(row, dict) or not isinstance(row.get('id'), str) or not isinstance(row.get('name'), str):
                    raise ValueError('方案库格式无效。')
                if row['id'] in ids or row['name'] in names:
                    raise ValueError('方案库包含重复记录。')
                ids.add(row['id']); names.add(row['name'])
                row['profile'] = canonical_profile(row['profile'], strict=True)
            return copy.deepcopy(rows)
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError('方案库无法读取，请保留文件并检查内容。') from exc

    def get(self, preset_id):
        for row in self.rows():
            if row['id'] == preset_id:
                return row
        raise ValueError('所选方案已不存在。')

    def save(self, name, profile, *, preset_id=None):
        name = name.strip()
        if not name or len(name) > 60 or any(ord(c) < 32 for c in name):
            raise ValueError('方案名称请输入 1 至 60 个字符。')
        owned = canonical_profile(profile, strict=True)
        rows = self.rows()
        if any(row['name'].casefold() == name.casefold() and row['id'] != preset_id for row in rows):
            raise ValueError('此方案名称已存在，请使用其他名称。')
        if preset_id is not None and not any(row['id'] == preset_id for row in rows):
            raise ValueError('所选方案已不存在。')
        preset_id = preset_id or uuid.uuid4().hex
        row = dict(id=preset_id, name=name, profile=owned)
        rows = [row if old['id'] == preset_id else old for old in rows]
        if not any(old['id'] == preset_id for old in rows):
            rows.append(row)
        _write(self.path, dict(schema=1, presets=rows))
        return preset_id

    def delete(self, preset_id):
        rows = self.rows()
        if not any(row['id'] == preset_id for row in rows):
            raise ValueError('所选方案已不存在。')
        _write(self.path, dict(schema=1, presets=[row for row in rows if row['id'] != preset_id]))
