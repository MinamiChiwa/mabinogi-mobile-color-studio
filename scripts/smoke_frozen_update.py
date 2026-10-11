"""Isolated test-signed frozen upgrade. Never targets the desktop installation."""
import argparse,hashlib,json,shutil,subprocess,sys,time
from pathlib import Path
from unittest.mock import patch
from updater.runtime import UpdateRuntime
from updater.paths import hash_file

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--old-package',type=Path,required=True);p.add_argument('--offline',type=Path,required=True)
    p.add_argument('--keys',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--expect-rollback',action='store_true');p.add_argument('--crash-after-backup',action='store_true');a=p.parse_args(argv)
    out=a.out.resolve();out.mkdir(parents=True,exist_ok=True);root=out/'测试 安装/ColorStudio'
    if root.exists():raise RuntimeError('Use a fresh isolated smoke directory')
    shutil.copytree(a.old_package,root)
    data=root/'data';data.mkdir();(data/'sessions/old').mkdir(parents=True);(data/'sessions/old/keep.bin').write_bytes(bytes(range(256))*20)
    profile={'schema':1,'regions':[dict(enabled=True,target='#000000',alt='',mode='精准 HEX',tolerance=8.) for _ in range(3)],
        'priority_order':[0,1,2],'search_strategy':'native'}
    (data/'profile.json').write_text(json.dumps(profile),encoding='utf-8');(data/'settings.json').write_text('{}')
    (root/'personal.txt').write_bytes(b'unknown user file')
    before={str(p.relative_to(root)):hash_file(p) for p in root.rglob('*') if p.is_file() and (p.is_relative_to(data) or p.name=='personal.txt')}
    old=json.loads((root/'update-manifest.json').read_text());keys=json.loads(a.keys.read_text())
    events=[];runtime=UpdateRuntime(root,data,old['version'],events.append,keys=keys)
    runtime.offline(a.offline);runtime.worker.join(30)
    if runtime.worker.is_alive() or runtime.service.state!='ready':raise RuntimeError(str(events))
    with patch('updater.runtime.sys.frozen',True,create=True),patch('updater.runtime.launch_helper'):
        runtime.prepare_install(runtime.service.plan)
    tx=Path(json.loads((root/'.colorstudio-pending.json').read_text())['transaction'])
    started=time.monotonic()
    if a.crash_after_backup:
        from updater.transaction import apply_update
        try:apply_update(tx,fault='after_backup')
        except RuntimeError:pass
        helper=subprocess.Popen([str(root/'ColorStudio.exe')],cwd=root)
    else:helper=subprocess.Popen([str(tx/'ColorStudioUpdater.exe'),'--transaction',str(tx)])
    try:code=helper.wait(timeout=210)
    except subprocess.TimeoutExpired:
        helper.terminate();helper.wait(timeout=10);raise RuntimeError('Frozen helper smoke timeout')
    if a.crash_after_backup:
        end=time.monotonic()+60
        while time.monotonic()<end:
            state=json.loads((tx/'state.json').read_text())
            if state['status'] in ('recovered','committed'):break
            time.sleep(.1)
    state=json.loads((tx/'state.json').read_text());after={path:hash_file(root/path) for path in before}
    manifest=json.loads((root/'update-manifest.json').read_text())
    verified=all(hash_file(root/r['path'])==r['sha256'] for r in manifest['files'])
    report=dict(exit_code=code,status=state['status'],version=manifest['version'],elapsed=time.monotonic()-started,
        user_data_unchanged=before==after,application_files_verified=verified,download_bytes=runtime.service.plan.download_bytes,
        total_files=len(manifest['files']),transaction=str(tx),installation=str(root))
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
    # Shut down only the frozen UI launched by this isolated helper. It has not
    # read game data or sent input. The desktop tool and game are untouched.
    if sys.platform=='win32':
        from updater.win_process import other_install_instances
        import ctypes
        from ctypes import wintypes as W
        user=ctypes.WinDLL('user32');callback=ctypes.WINFUNCTYPE(W.BOOL,W.HWND,W.LPARAM)
        pids=set(other_install_instances(root))
        @callback
        def close(hwnd,_):
            pid=W.DWORD();user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
            if pid.value in pids:user.PostMessageW(hwnd,0x10,0,0)
            return True
        user.EnumWindows(close,0)
    expected='recovered' if a.expect_rollback else 'committed'
    if (state['status']!=expected or not a.expect_rollback and code!=0 or before!=after or not verified
            or a.expect_rollback and manifest['version']!=old['version']):raise RuntimeError('Frozen update verification failed')
    return 0
if __name__=='__main__':raise SystemExit(main())
