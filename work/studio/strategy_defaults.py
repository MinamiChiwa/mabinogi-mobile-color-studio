"""One-time screenshot preference migration; no change to player color rules."""
import copy,json
from pathlib import Path
from profile_store import _write

MIGRATION_KEY='screenshot_default_revision'
MIGRATION_REVISION=1

def migrate_strategy_defaults(directory,*,persist=True):
    result=dict(settings={},profile=None,errors=[])
    for name in ('profile.json','presets.json','settings.json'):
        path=Path(directory)/name
        try:
            raw=json.loads(path.read_text(encoding='utf8')) if path.exists() else None
            if raw is None:
                if name!='settings.json':continue
                raw={}
            if name=='profile.json' and isinstance(raw,list):raw=dict(schema=1,regions=raw)
            if not isinstance(raw,dict):raise ValueError('Invalid preference object')
            value=copy.deepcopy(raw)
            if value.get(MIGRATION_KEY)!=MIGRATION_REVISION:
                if name=='presets.json':
                    rows=value.get('presets')
                    if value.get('schema')!=1 or not isinstance(rows,list):raise ValueError('Invalid preset collection')
                    for row in rows:
                        profile=row['profile']
                        if isinstance(profile,list):profile=dict(schema=1,regions=profile);row['profile']=profile
                        if not isinstance(profile,dict):raise ValueError('Invalid preset profile')
                        profile['search_strategy']='screenshot'
                else:value['search_strategy']='screenshot'
                value[MIGRATION_KEY]=MIGRATION_REVISION
            if name=='presets.json':
                for row in value.get('presets',[]):
                    if row['profile'].get('search_strategy')=='atlas':row['profile']['search_strategy']='screenshot'
            elif value.get('search_strategy')=='atlas':value['search_strategy']='screenshot'
            if name=='settings.json':result['settings']=value
            elif name=='profile.json':result['profile']=value
            if persist and value!=raw:_write(path,value)
        except (OSError,ValueError,TypeError,KeyError) as exc:
            result['errors'].append(dict(file=name,error=str(exc)))
    # A damaged settings file is preserved; the current launch still uses the
    # screenshot default. Each valid file records migration independently.
    result['settings'].setdefault('search_strategy','screenshot')
    return result
