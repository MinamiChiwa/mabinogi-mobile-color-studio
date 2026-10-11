"""Thread-safe update state machine; UI callers only receive plain events."""
from dataclasses import dataclass,field
import threading
from .types import ProgressEvent

@dataclass
class UpdateService:
    emit: object
    installer: object=None
    state: str='idle'
    manifest: object=None
    plan: object=None
    busy: bool=False
    _cancel: object=field(default_factory=threading.Event,init=False)

    def cancelled(self):return self._cancel.is_set() or self.busy
    def set_busy(self,value):
        self.busy=bool(value)
        if self.busy and self.state in ('checking','downloading'):
            self._cancel.set()
    def clear_cancel(self):self._cancel.clear()

    def _event(self,kind,reason=''):
        version=self.manifest.get('version','') if isinstance(self.manifest,dict) else getattr(self.manifest,'version','')
        event=ProgressEvent(kind,reason_code=reason,version=version)
        if callable(self.emit):self.emit(event)
        return event
    def mark_available(self,manifest):self.manifest=manifest;self.state='available';return self._event('available')
    def mark_ready(self,plan):self.plan=plan;self.state='ready';return self._event('ready')
    def begin_download(self):
        if self.state!='available':return self._event('rejected','not_available')
        if self.busy:return self._event('blocked','busy')
        self.clear_cancel()
        self.state='downloading';return self._event('downloading')
    def cancel(self):
        self._cancel.set()
        if self.state in ('downloading','checking'):self.state='available' if self.manifest else 'idle'
        return self._event(self.state,'cancelled')
    def install(self):
        if self.state!='ready':return self._event('rejected','not_ready')
        if self.busy:return self._event('blocked','busy')
        if not callable(self.installer):return self._event('blocked','installer_unavailable')
        self.state='installing';self._event('installing')
        try:self.installer(self.plan)
        except Exception:self.state='ready';self._event('failed','install_failed');raise
        self.state='waiting_for_exit';return self._event('waiting_for_exit')
