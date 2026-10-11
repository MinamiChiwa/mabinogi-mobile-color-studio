"""One background job at a time; install starts only from a user UI action."""
import base64,json,os,shutil,sys,tempfile,threading,time,uuid
from pathlib import Path
from .service import UpdateService
from .discovery import check_release
from .http_client import GitHubClient
from .manifest import verify_manifest
from .planner import plan_update
from .download import download_bytes
from .offline import import_offline
from .payload import unpack_blob
from .paths import atomic_json,hash_file,safe_path,checked_root
from .trust import TRUSTED_KEYS
from .win_process import launch_helper,process_creation,other_install_instances

class UpdateRuntime:
    def __init__(self,root,data,version,emit,*,keys=None,client=None):
        self.root=Path(root);self.data=Path(data);self.version=version;self.emit=emit
        self.keys=TRUSTED_KEYS if keys is None else keys;self.client=client or GitHubClient()
        self.service=UpdateService(lambda event:self.emit(dict(kind=event.kind,reason=event.reason_code,
            version=event.version)),installer=self.prepare_install)
        self.storage=self.data/'updates';self.cache=self.storage/'blobs';self.worker=None;self.result=None
        self.prefs_path=self.storage/'preferences.json';self.prefs=self._load(self.prefs_path)
        self._worker_lock=threading.Lock()
    def _load(self,path):
        try:
            value=json.loads(Path(path).read_text(encoding='utf-8'))
            return value if isinstance(value,dict) else {}
        except (OSError,ValueError):return {}
    def preference(self,**values):
        self.prefs.update(values);atomic_json(self.prefs_path,self.prefs)
    def set_busy(self,value):self.service.set_busy(value)
    def cancel(self):self.service.cancel()
    def _start(self,job):
        with self._worker_lock:
            if self.worker is not None and self.worker.is_alive():return False
            if self.service.busy:self.emit(dict(kind='blocked',reason='busy'));return False
            self.service.clear_cancel()
            previous_state=self.service.state
            def run():
                try:job()
                except BaseException as exc:
                    self.service.state='ready' if previous_state=='ready' else 'available' if self.service.manifest else 'idle'
                    reason=('cancelled' if self.service.cancelled() else 'wrong_base' if 'wrong_base' in str(exc)
                        else 'conflicts' if 'conflict' in str(exc).lower() else 'verification')
                    self.emit(dict(kind='failed',reason=reason))
                    try:atomic_json(self.storage/'last-error.json',dict(type=type(exc).__name__,message=str(exc)))
                    except OSError:pass
            self.worker=threading.Thread(target=run,daemon=True);self.worker.start();return True
    def check(self,manual=False):
        if not manual and (not self.prefs.get('automatic',True) or time.time()-self.prefs.get('checked_at',0)<86400):return False
        def job():
            self.service.state='checking';self.emit(dict(kind='checking'))
            cache=self._load(self.storage/'discovery.json')
            for field in ('manifest_raw','signature'):
                if field in cache:cache[field]=base64.b64decode(cache[field])
            channel='prerelease' if self.prefs.get('prerelease',False) else 'stable'
            result=check_release(self.version,channel,cache,self.service.cancelled,client=self.client,trusted_keys=self.keys)
            for field in ('manifest_raw','signature'):
                if field in cache:cache[field]=base64.b64encode(cache[field]).decode()
            atomic_json(self.storage/'discovery.json',cache)
            if result.status!='cancelled':self.preference(checked_at=result.checked_at)
            if result.status=='available':
                self.result=result;self.service.manifest=result.manifest;self.service.state='available'
                try:plan=self._plan(result.manifest)
                except (OSError,ValueError):
                    self.service.state='idle';self.emit(dict(kind='manual',reason='bootstrap_required',version=result.manifest.version));return
                self.service.plan=plan
                if manual or self.prefs.get('ignored')!=result.manifest.version:
                    self.emit(dict(kind='available',version=result.manifest.version,download_bytes=plan.download_bytes,conflicts=list(plan.conflicts)))
            else:
                self.service.state='idle';self.emit(dict(kind=result.status,reason=result.reason_code))
        return self._start(job)
    def _old(self):
        raw=(self.root/'update-manifest.json').read_bytes();sig=(self.root/'update-manifest.sig').read_bytes()
        return verify_manifest(raw,sig,self.keys),raw,sig
    def _plan(self,new):
        old,_,_=self._old()
        return plan_update(self.root,old,new,protected_paths=[self.data])
    def download(self):
        if self.result is None:return False
        def job():
            self.service.begin_download();plan=self._plan(self.result.manifest)
            if any(p in {r.path for r in self.result.manifest.files} for p in plan.conflicts):raise ValueError('Application conflicts')
            rows={r.blob:r for r in self.result.manifest.files};received=0
            self.cache.mkdir(parents=True,exist_ok=True)
            for name in plan.required_blobs:
                row=rows[name];blob=self.cache/name
                if blob.is_file() and blob.stat().st_size==row.download_size and hash_file(blob)==row.blob_sha256:
                    received+=row.download_size;continue
                start=received
                def progress(event):self.emit(dict(kind='download',received=start+event['received'],total=plan.download_bytes))
                download_bytes(self.client,self.result.assets[name],blob.with_name(blob.name+'.part'),
                    row.download_size,row.blob_sha256,cancel=self.service.cancelled,emit=progress)
                received+=row.download_size
            (self.cache/'update-manifest.json').write_bytes(self.result.raw)
            (self.cache/'update-manifest.sig').write_bytes(self.result.signature)
            self._ready(self.result.manifest)
        return self._start(job)
    def offline(self,archive):
        def job():
            self.service.state='downloading';self.emit(dict(kind='importing'))
            old,old_raw,_=self._old()
            pending=self.storage/('.import-'+uuid.uuid4().hex)
            try:
                new=import_offline(archive,pending,trusted_keys=self.keys,root=self.root,old_raw=old_raw,
                    cancel=self.service.cancelled,emit=lambda e:self.emit(dict(e,kind='download')))
                from packaging.version import Version
                if Version(new.version)<=Version(self.version):raise ValueError('Downgrades are unsupported')
                cached=self._load(self.storage/'discovery.json')
                if new.release_sequence<cached.get('sequence',0):raise ValueError('Replay rejected')
                if new.minimum_updater>1 or new.data_schema_write!=1 or 1 not in new.data_schema_read:raise ValueError('Incompatible updater')
                if self.service.cancelled():raise RuntimeError('cancelled')
                self._plan(new)
                self.cache.mkdir(parents=True,exist_ok=True)
                for path in pending.iterdir():path.replace(self.cache/path.name)
                cached.update(sequence=max(cached.get('sequence',0),new.release_sequence),signed_version=new.version)
                atomic_json(self.storage/'discovery.json',cached)
                self.service.manifest=new;self._ready(new)
            finally:
                if pending.exists():shutil.rmtree(pending)
        return self._start(job)
    def _ready(self,manifest):
        if self.service.cancelled():raise RuntimeError('cancelled')
        plan=self._plan(manifest)
        self.service.manifest=manifest;self.service.mark_ready(plan)
        self.emit(dict(kind='ready',version=manifest.version,download_bytes=plan.download_bytes,
            conflicts=list(plan.conflicts)))
    def install(self):return self._start(self.service.install)
    def prepare_install(self,plan):
        if self.service.busy:raise RuntimeError('busy')
        if not getattr(sys,'frozen',False):raise RuntimeError('Install only supported from portable package')
        root=checked_root(self.root);new_raw=(self.cache/'update-manifest.json').read_bytes();new_sig=(self.cache/'update-manifest.sig').read_bytes()
        if other_install_instances(root):raise RuntimeError('Other tool instances must exit first')
        new=verify_manifest(new_raw,new_sig,self.keys);old,old_raw,old_sig=self._old();plan=self._plan(new)
        if any(path in {r.path for r in new.files} for path in plan.conflicts):raise ValueError('Application conflicts; use clean official package')
        # The external helper must remain writable without relying on the
        # parent folder of a portable install (often read-only for users).
        tx=Path(tempfile.gettempdir())/('ColorStudio-update-'+uuid.uuid4().hex);tx.mkdir()
        stage=root/('.colorstudio-stage-'+tx.name[-32:]);stage.mkdir()
        if shutil.disk_usage(root).free<plan.stage_bytes+plan.backup_bytes+16*1024**2:raise OSError('Insufficient disk space')
        if shutil.disk_usage(tx).free<32*1024**2:raise OSError('Insufficient helper disk space')
        rows={r.path:r for r in new.files}
        for path in plan.installs:
            if self.service.cancelled():raise RuntimeError('cancelled')
            unpack_blob(self.cache/rows[path].blob,rows[path],safe_path(stage,path))
        for name,raw in (('old-manifest.json',old_raw),('old-manifest.sig',old_sig),('new-manifest.json',new_raw),('new-manifest.sig',new_sig)):
            (tx/name).write_bytes(raw)
        (stage/'update-manifest.json').write_bytes(new_raw);(stage/'update-manifest.sig').write_bytes(new_sig)
        location=str(self.data.relative_to(root)) if self.data.is_relative_to(root) else str(self.data)
        atomic_json(stage/'update-location.json',dict(schema=1,data=location))
        operations=[]
        for path in [*plan.installs,*plan.removals,'update-manifest.json','update-manifest.sig','update-location.json']:
            target=safe_path(root,path,metadata=True);source=safe_path(stage,path,metadata=True)
            operations.append(dict(path=path,kind='remove' if path in plan.removals else 'replace',
                before=hash_file(target) if target.is_file() else None,after=hash_file(source) if source.is_file() else None))
        operations.sort(key=lambda op:(op['path'] in ('ColorStudio.exe','update-manifest.json','update-manifest.sig','update-location.json'),op['path']))
        import i18n
        record=dict(schema=1,root=str(root),data=str(self.data),staging=str(stage),backup=str(root/('.colorstudio-backup-'+tx.name[-32:])),
            token=uuid.uuid4().hex,version=new.version,operations=operations,language=i18n.language)
        atomic_json(tx/'transaction.json',record)
        atomic_json(tx/'state.json',dict(transaction_id=tx.name,status='staged',completed=[],intents={}))
        helper=root/'ColorStudioUpdater.exe'
        old_helper=next((r for r in old.files if r.path=='ColorStudioUpdater.exe'),None)
        if old_helper is None or not helper.is_file() or hash_file(helper)!=old_helper.sha256:raise ValueError('Independent updater missing or changed')
        shutil.copy2(helper,tx/helper.name)
        target_helper=next((r for r in new.files if r.path=='ColorStudioUpdater.exe'),None)
        source_helper=stage/'ColorStudioUpdater.exe' if 'ColorStudioUpdater.exe' in plan.installs else helper
        if target_helper is None or hash_file(source_helper)!=target_helper.sha256:raise ValueError('Target recovery helper unavailable')
        shutil.copy2(source_helper,tx/'target-helper.exe')
        atomic_json(root/'.colorstudio-pending.json',dict(transaction=str(tx)))
        try:launch_helper(tx/helper.name,tx,os.getpid(),process_creation(os.getpid()))
        except BaseException:
            (root/'.colorstudio-pending.json').unlink(missing_ok=True)
            atomic_json(tx/'state.json',dict(transaction_id=tx.name,status='cancelled',completed=[],intents={}))
            raise
        self.emit(dict(kind='exit_requested'))
