"""Independent onefile updater. No dependency on the installation's _internal."""
import argparse,json,os,subprocess,time,sys
from pathlib import Path
from updater.manifest import verify_manifest
from updater.trust import TRUSTED_KEYS
from updater.paths import checked_root,safe_path,hash_file,atomic_json
from updater.planner import plan_update
from updater.transaction import apply_update,recover_update
from updater.win_process import UpdateLock,wait_parent,other_install_instances,process_creation

def validated_transaction(tx,trusted_keys):
    tx=checked_root(tx);record=json.loads((tx/'transaction.json').read_text(encoding='utf-8'))
    root=checked_root(record['root'])
    old=verify_manifest((tx/'old-manifest.json').read_bytes(),(tx/'old-manifest.sig').read_bytes(),trusted_keys)
    new=verify_manifest((tx/'new-manifest.json').read_bytes(),(tx/'new-manifest.sig').read_bytes(),trusted_keys)
    if new.version!=record['version']:raise ValueError('Transaction version mismatch')
    from packaging.version import Version
    if Version(new.version)<=Version(old.version) or new.minimum_updater>1 or new.data_schema_write!=1 or 1 not in new.data_schema_read:
        raise ValueError('Incompatible update')
    plan=plan_update(root,old,new,protected_paths=[record['data']])
    if set(plan.conflicts)&{r.path for r in new.files}:raise ValueError('Application files changed; installation cancelled')
    expected={p:'replace' for p in plan.installs}|{p:'remove' for p in plan.removals}
    actual={op['path']:op['kind'] for op in record['operations'] if op['path'] not in ('update-manifest.json','update-manifest.sig','update-location.json')}
    paths=[op['path'].casefold() for op in record['operations']]
    if len(paths)!=len(set(paths)) or expected!=actual:raise ValueError('Transaction operations changed')
    metadata={op['path']:op['kind'] for op in record['operations'] if op['path'] in ('update-manifest.json','update-manifest.sig','update-location.json')}
    if metadata!={'update-manifest.json':'replace','update-manifest.sig':'replace','update-location.json':'replace'}:
        raise ValueError('Transaction metadata changed')
    stage=checked_root(record['staging']);backup=checked_root(record['backup'])
    if (stage.parent!=root or backup.parent!=root or not stage.name.startswith('.colorstudio-stage-')
            or not backup.name.startswith('.colorstudio-backup-') or stage==backup):
        raise ValueError('Transaction storage escaped')
    rows={r.path:r for r in new.files}
    for path in plan.installs:
        if hash_file(safe_path(stage,path))!=rows[path].sha256:raise ValueError('Staged file changed')
    for name,signed in (('update-manifest.json','new-manifest.json'),('update-manifest.sig','new-manifest.sig')):
        if (stage/name).read_bytes()!=(tx/signed).read_bytes():raise ValueError('Staged ownership changed')
    location=json.loads((stage/'update-location.json').read_text(encoding='utf-8'))
    expected_data=Path(record['data'])
    located=Path(location['data']);located=located if located.is_absolute() else root/located
    if located.absolute()!=expected_data.absolute():raise ValueError('Data location changed')
    return record,root

def run(tx,*,parent_pid=None,parent_creation=None,recover=False,trusted_keys=None):
    tx=checked_root(tx);keys=TRUSTED_KEYS if trusted_keys is None else trusted_keys
    initial=json.loads((tx/'transaction.json').read_text(encoding='utf-8'));root=checked_root(initial['root'])
    if parent_pid is not None:wait_parent(parent_pid,parent_creation)
    with UpdateLock(root):
        if other_install_instances(root):raise RuntimeError('Other tool instances must exit first')
        atomic_json(tx/'helper-owner.json',dict(pid=os.getpid(),creation=process_creation(os.getpid())))
        if recover:
            stage=checked_root(initial['staging']);backup=checked_root(initial['backup'])
            if stage.parent!=root or backup.parent!=root or not stage.name.startswith('.colorstudio-stage-') or not backup.name.startswith('.colorstudio-backup-'):
                raise ValueError('Recovery storage changed')
            # Reconstruct ownership from signed manifests even during a mixed installation.
            old=verify_manifest((tx/'old-manifest.json').read_bytes(),(tx/'old-manifest.sig').read_bytes(),keys)
            new=verify_manifest((tx/'new-manifest.json').read_bytes(),(tx/'new-manifest.sig').read_bytes(),keys)
            allowed={r.path for r in old.files}|{r.path for r in new.files}|{'update-manifest.json','update-manifest.sig','update-location.json'}
            if any(op['path'] not in allowed for op in initial['operations']):raise ValueError('Recovery ownership mismatch')
            old_files={r.path:r for r in old.files};new_files={r.path:r for r in new.files}
            for operation in initial['operations']:
                path=operation['path']
                if path in ('update-manifest.json','update-manifest.sig','update-location.json'):continue
                expected_before=old_files[path].sha256 if path in old_files else None
                expected_after=new_files[path].sha256 if path in new_files else None
                if operation.get('before') not in (None,expected_before) or operation.get('after')!=expected_after:
                    raise ValueError('Recovery file identity mismatch')
            result=recover_update(tx)
        else:
            record,root=validated_transaction(tx,keys)
            children=[]
            def stop_children():
                for process in children:
                    if process.poll() is None:
                        process.terminate();process.wait(timeout=10)
            def healthy():
                exe=root/'ColorStudio.exe'
                process=subprocess.Popen([str(exe),'--update-health-check',str(tx)],cwd=root)
                children.append(process)
                try:status=process.wait(timeout=90)
                except subprocess.TimeoutExpired:
                    process.terminate();process.wait(timeout=10);return False
                if status!=0:return False
                health=json.loads((tx/'health.json').read_text(encoding='utf-8'))
                if health!={'token':record['token'],'version':record['version']}:return False
                process=subprocess.Popen([str(exe),'--update-ready',str(tx)],cwd=root)
                children.append(process)
                end=time.monotonic()+90
                while time.monotonic()<end and process.poll() is None:
                    try:
                        ready=json.loads((tx/'ready.json').read_text(encoding='utf-8'))
                        if ready==health:return True
                    except (OSError,ValueError):pass
                    time.sleep(.1)
                if process.poll() is None:process.terminate();process.wait(timeout=10)
                return False
            try:result=apply_update(tx,health_check=healthy)
            except BaseException:
                stop_children()
                result=recover_update(tx)
                if result['status']=='recovered':
                    (root/'.colorstudio-pending.json').unlink(missing_ok=True)
                    subprocess.Popen([str(root/'ColorStudio.exe')],cwd=root)
                raise
        if result['status'] in ('recovered','committed'):
            (root/'.colorstudio-pending.json').unlink(missing_ok=True)
        if result['status']=='recovered':subprocess.Popen([str(root/'ColorStudio.exe')],cwd=root)
        return result

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--transaction',required=True);p.add_argument('--parent-pid',type=int)
    p.add_argument('--parent-creation',type=int);p.add_argument('--recover',action='store_true');a=p.parse_args(argv)
    try:run(a.transaction,parent_pid=a.parent_pid,parent_creation=a.parent_creation,recover=a.recover);return 0
    except BaseException as exc:
        try:atomic_json(Path(a.transaction)/'helper-error.json',dict(error_type=type(exc).__name__,message=str(exc)))
        except OSError:pass
        if os.name=='nt':
            import ctypes
            try:
                record=json.loads((Path(a.transaction)/'transaction.json').read_text(encoding='utf-8'))
                state=json.loads((Path(a.transaction)/'state.json').read_text(encoding='utf-8'))
            except (OSError,ValueError):record={};state={}
            recovered=state.get('status')=='recovered'
            messages={
                '简体中文':('更新未完成，已恢复原版本；用户资料已保留。' if recovered else '更新未完成，请保留恢复记录并使用完整官方包修复程序。'),
                '繁體中文':('更新未完成，已恢復原版本；使用者資料已保留。' if recovered else '更新未完成，請保留恢復紀錄並使用完整官方套件修復程式。'),
                'English':('Update failed. The previous version was restored and user data was kept.' if recovered else 'Update did not finish. Keep the recovery files and repair the app using the full official package.'),
                '日本語':('更新に失敗したため、以前のバージョンに戻しました。ユーザーデータは保持されています。' if recovered else '更新が完了しませんでした。復旧用ファイルを残し、公式の完全パッケージで修復してください。'),
                '한국어':('업데이트에 실패하여 이전 버전으로 복원했습니다. 사용자 데이터는 유지되었습니다.' if recovered else '업데이트를 완료하지 못했습니다. 복구 파일을 보관하고 공식 전체 패키지로 프로그램을 복구해 주세요.'),
            }
            ctypes.windll.user32.MessageBoxW(None,messages.get(record.get('language'),messages['English'])+'\n'+str(a.transaction),'ColorStudio Update',0x10)
        return 1

if __name__=='__main__':raise SystemExit(main())
