"""Persist actual results separately from the editable target profile."""
import datetime,json,math
from vision import error

def describe_result(colors,rules):
    regions=[]
    for i,(color,rule) in enumerate(zip(colors,rules)):
        delta=error(color,rule['colors'],False) if rule['enabled'] and color else None
        regions.append(dict(region=i+1,color=color,enabled=rule['enabled'],
                            targets=rule.get('colors',[]),delta=delta))
    values=[r['delta'] for r in regions if r['enabled']]
    valid=bool(values) and all(v is not None and math.isfinite(v) for v in values)
    return dict(regions=regions,maximum=max(values) if valid else None,
                average=sum(values)/len(values) if valid else None)

def read_history(path):
    try:
        data=json.loads(path.read_text(encoding='utf-8'))
        return data if isinstance(data,list) else []
    except (OSError,ValueError):return []

def save_result(path,colors,rules,outcome,restored=None,best_colors=None):
    entry=describe_result(colors,rules)
    entry.update(time=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),outcome=outcome,restored=restored)
    if best_colors:entry['best']=describe_result(best_colors,rules)
    rows=[entry]+read_history(path)
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(rows[:50],ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(path)
    return entry
