"""Keep the first observed stop source without inferring a player's intent."""
import threading
import time


class StopEvent(threading.Event):
    def __init__(self):
        super().__init__();self._source_lock=threading.Lock();self._diagnostic=None

    def request(self,source,**details):
        with self._source_lock:
            if not self.is_set():
                self._diagnostic=dict(details,source=source,requested_monotonic=time.monotonic())
                super().set()

    def set(self):self.request('unattributed_stop_flag')

    def clear(self):
        with self._source_lock:self._diagnostic=None;super().clear()

    def diagnostic(self):
        with self._source_lock:return None if self._diagnostic is None else dict(self._diagnostic)


def request_stop(event,source,**details):
    request=getattr(event,'request',None)
    if callable(request):request(source,**details)
    else:event.set()


def stop_diagnostic(event):
    reader=getattr(event,'diagnostic',None)
    if callable(reader):return reader()
    return dict(source='unattributed_stop_flag') if event.is_set() else None


def interruption_reason(error,diagnostic):
    if '游戏失去焦点' in error:return 'focus_lost'
    if '窗口位置或尺寸' in error:return 'window_changed'
    if '无法激活游戏' in error:return 'activation_failed'
    source=(diagnostic or {}).get('source')
    return {'ui_button':'user_stop','main_stop_button':'user_stop','overlay_stop_button':'user_stop','window_close':'window_closed',
            'hotkey_message':'stop_hotkey','hotkey_poll':'stop_key_detected',
            'native_f9_poll':'stop_key_detected','screenshot_f9_poll':'stop_key_detected',
            'unattributed_stop_flag':'stop_signal_unknown'
            }.get(source,'unknown_interruption')
