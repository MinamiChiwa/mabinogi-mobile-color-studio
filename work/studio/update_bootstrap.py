"""Run before importing Tk, OpenCV or any replaceable application dependency."""
import json,os,sys,subprocess
from pathlib import Path

def installation_root():
    return Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[2]

def pending_transaction(root):
    marker=Path(root)/'.colorstudio-pending.json'
    if not marker.exists():return None
    payload=json.loads(marker.read_text(encoding='utf-8'));tx=Path(payload['transaction'])
    record=json.loads((tx/'transaction.json').read_text(encoding='utf-8'))
    if os.path.normcase(os.path.abspath(record['root']))!=os.path.normcase(os.path.abspath(root)):
        raise RuntimeError('Update recovery root mismatch')
    try:state=json.loads((tx/'state.json').read_text(encoding='utf-8'))
    except (OSError,ValueError):state={}
    if state.get('status') in ('committed','recovered','cancelled'):return None
    return tx

def active_data_directory(root):
    path=Path(root)/'update-location.json'
    if not path.exists():return None
    payload=json.loads(path.read_text(encoding='utf-8'))
    if payload.get('schema')!=1:return None
    data=Path(payload['data'])
    if not data.is_absolute():data=Path(root)/data
    return data

def health_check(transaction):
    # This mode never opens a game, starts hotkeys or writes player settings.
    tx=Path(transaction);record=json.loads((tx/'transaction.json').read_text(encoding='utf-8'))
    from updater.manifest import verify_manifest
    from updater.trust import TRUSTED_KEYS
    from updater.paths import hash_file,safe_path,atomic_json
    manifest=verify_manifest((tx/'new-manifest.json').read_bytes(),(tx/'new-manifest.sig').read_bytes(),TRUSTED_KEYS)
    from build_info import APP_VERSION
    if manifest.version!=APP_VERSION:raise RuntimeError('Health build version mismatch')
    root=Path(record['root'])
    for row in manifest.files:
        path=safe_path(root,row.path)
        if not path.is_file() or path.stat().st_size!=row.size or hash_file(path)!=row.sha256:raise RuntimeError('Health file check failed')
    import cv2,numpy,PIL,customtkinter,tkinter
    from vision import configure_ocr
    configure_ocr(strict=True)
    win=tkinter.Tk();win.withdraw();win.update_idletasks();win.destroy()
    atomic_json(tx/'health.json',dict(token=record['token'],version=manifest.version))
    return 0

def signal_ready(transaction):
    from updater.paths import atomic_json
    tx=Path(transaction);record=json.loads((tx/'transaction.json').read_text(encoding='utf-8'))
    atomic_json(tx/'ready.json',dict(token=record['token'],version=record['version']))

def helper_alive(transaction):
    from updater.win_process import process_creation
    try:owner=json.loads((Path(transaction)/'helper-owner.json').read_text(encoding='utf-8'))
    except (OSError,ValueError):return False
    return owner.get('creation') is not None and process_creation(owner['pid'])==owner['creation']

def dispatch(argv=None):
    argv=list(sys.argv[1:] if argv is None else argv);root=installation_root()
    if '--update-health-check' in argv:
        transaction=Path(argv[argv.index('--update-health-check')+1])
        try:return health_check(transaction)
        except BaseException as exc:
            try:
                from updater.paths import atomic_json
                import traceback
                atomic_json(transaction/'health-error.json',dict(type=type(exc).__name__,message=str(exc),traceback=traceback.format_exc()))
            except BaseException:pass
            return 1
    tx=pending_transaction(root)
    if tx is not None and '--update-ready' not in argv:
        # This code must work while crypto/OpenCV/Tk files are half-replaced.
        # The expected helper digest is embedded in the executable at build
        # time, independent of mutable installation/transaction metadata.
        import hashlib,stat
        from update_recovery_identity import HELPER_SHA256
        helper=None
        for candidate in (tx/'ColorStudioUpdater.exe',tx/'target-helper.exe'):
            if not candidate.is_file():continue
            chain=(candidate,*candidate.parents)
            if any(stat.S_ISLNK(p.lstat().st_mode) or getattr(p.lstat(),'st_file_attributes',0)&0x400 for p in chain):continue
            digest=hashlib.sha256(candidate.read_bytes()).hexdigest()
            if HELPER_SHA256 and digest==HELPER_SHA256:helper=candidate;break
        if helper is None:raise RuntimeError('Recovery helper failed embedded identity verification')
        subprocess.Popen([str(helper),'--transaction',str(tx),'--recover'],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        return 0
    if '--update-ready' in argv:
        supplied=Path(argv[argv.index('--update-ready')+1])
        if tx!=supplied:raise RuntimeError('Invalid update ready transaction')
        state=json.loads((supplied/'state.json').read_text(encoding='utf-8'))
        if state.get('status')!='pending_health':raise RuntimeError('Update is not ready for startup')
    return None
