"""Write-ahead file journal; recovery never touches user data."""
import json,os,time,uuid
from pathlib import Path
from .paths import atomic_json,checked_root,safe_path,hash_file

class TransactionError(RuntimeError):pass

def _read(tx):
    tx=checked_root(tx);payload=json.loads((tx/'transaction.json').read_text(encoding='utf-8'))
    if payload.get('schema')!=1 or not isinstance(payload.get('operations'),list):raise TransactionError('Invalid transaction')
    root=checked_root(payload['root']);backup=checked_root(payload['backup']);staging=checked_root(payload['staging'])
    if (not (backup.is_relative_to(tx) or backup.is_relative_to(root)) or not staging.is_relative_to(root)
            or backup==root or staging==root or backup==staging):raise TransactionError('Invalid transaction storage')
    for op in payload['operations']:
        safe_path(root,op.get('path'),metadata=True)
        if op.get('kind') not in ('replace','remove'):raise TransactionError('Unknown operation')
    return payload,root,backup,staging

def _write_state(tx,state):atomic_json(Path(tx)/'state.json',state)

def _move(source,target):
    for attempt in range(4):
        try:os.replace(source,target);return
        except PermissionError:
            if attempt==3:raise
            time.sleep(.15*(attempt+1))

def apply_update(transaction_dir,fault=None,emit=lambda e:None,health_check=None):
    tx=Path(transaction_dir);payload,root,backup,staging=_read(tx);backup.mkdir(parents=True,exist_ok=True)
    state={'transaction_id':tx.name,'status':'applying','completed':[],'intents':{}}
    _write_state(tx,state)
    def inject(point):
        if fault==point:raise RuntimeError('Injected fault '+point)
        if callable(fault):fault(point)
    try:
        for index,op in enumerate(payload['operations']):
            relative=op['path'];target=safe_path(root,relative,metadata=True);saved=safe_path(backup,relative,metadata=True)
            if target.exists() and not target.is_file():raise TransactionError('Target is not a regular file')
            before=hash_file(target) if target.exists() else None
            if 'before' in op and op['before']!=before:raise TransactionError('Installation changed')
            source=None;after=None
            if op['kind']=='replace':
                source=safe_path(staging,relative,metadata=True)
                if not source.is_file():raise TransactionError('Staged file missing')
                after=hash_file(source)
                if op.get('after',after)!=after:raise TransactionError('Staged file changed')
            state['intents'][str(index)]={'before':before,'after':after};_write_state(tx,state);inject('after_intent')
            if target.exists():
                saved.parent.mkdir(parents=True,exist_ok=True);_move(target,saved);emit(dict(kind='backup',path=relative));inject('after_backup')
            if source is not None:
                target.parent.mkdir(parents=True,exist_ok=True);_move(source,target);emit(dict(kind='replace',path=relative));inject('after_replace')
            state['completed'].append(index);_write_state(tx,state);inject('after_done')
        state['status']='pending_health';_write_state(tx,state)
        if health_check is not None and not health_check():
            return recover_update(tx,emit=emit)
        state['status']='committed';_write_state(tx,state);return state
    except BaseException:
        state['status']='recovery_required';_write_state(tx,state);raise

def recover_update(transaction_dir,emit=lambda e:None,*,force=False):
    tx=Path(transaction_dir);payload,root,backup,staging=_read(tx)
    try:state=json.loads((tx/'state.json').read_text(encoding='utf-8'))
    except (OSError,ValueError):raise TransactionError('Recovery journal missing; preserve backups')
    if state.get('status') in ('recovered','committed') and not force:return state
    state['status']='rolling_back';_write_state(tx,state)
    try:
        for index,op in reversed(list(enumerate(payload['operations']))):
            intent=state.get('intents',{}).get(str(index))
            if intent is None:continue
            target=safe_path(root,op['path'],metadata=True);saved=safe_path(backup,op['path'],metadata=True)
            before=intent['before'];after=intent['after']
            current=hash_file(target) if target.is_file() else None
            if target.exists() and not target.is_file():raise TransactionError('Unexpected recovery target')
            if saved.exists():
                if hash_file(saved)!=before:raise TransactionError('Backup changed')
                if target.exists():
                    if current!=after:raise TransactionError('Application changed during recovery')
                    target.unlink()
                target.parent.mkdir(parents=True,exist_ok=True);_move(saved,target);emit(dict(kind='restore',path=op['path']))
            elif before is None:
                if target.exists():
                    if current!=after:raise TransactionError('New file changed during recovery')
                    target.unlink()
            elif current!=before:raise TransactionError('Missing recovery backup')
        state.update(status='recovered');_write_state(tx,state);return state
    except BaseException:
        state['status']='recovery_required';_write_state(tx,state);raise
