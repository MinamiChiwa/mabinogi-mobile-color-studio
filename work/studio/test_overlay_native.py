"""Native overlay z-order, pass-through and capture fallback without game input."""
import ctypes
import importlib
import importlib.util
import threading
import sys
import time
import weakref
import unittest
from unittest.mock import Mock, patch

from search_overlay import SearchOverlay


class OverlayAPI:
    def __init__(self):
        self.style=0x80000
        self.topmost=False
        self.foreground=99
        self.visible={10:True,11:False}
        self.affinity=0
        self.affinity_supported=True
        self.affinity_ack=True
        self.fail_position=False
        self.shown=[]
        self.moves=[]
    def GetWindowLongPtrW(self, hwnd, index):return self.style
    def SetWindowLongPtrW(self, hwnd, index, value):
        previous=self.style;self.style=value;return previous
    def SetWindowPos(self, hwnd, after, x,y,w,h,flags):
        self.moves.append((hwnd,after,flags))
        if self.fail_position:return False
        self.topmost=after == -1;return True
    def SetWindowDisplayAffinity(self, hwnd, affinity):
        if not self.affinity_supported:return False
        self.affinity=affinity if self.affinity_ack else 1;return True
    def GetWindowDisplayAffinity(self, hwnd, pointer):
        pointer._obj.value=self.affinity;return True
    def IsWindow(self, hwnd):return hwnd in self.visible
    def IsWindowVisible(self, hwnd):return self.visible[hwnd]
    def ShowWindow(self, hwnd, command):
        self.shown.append((hwnd,command));self.visible[hwnd]=command != 0
        return True


class NativeOverlayTests(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('overlay_native'),'Native overlay policy missing')
        return importlib.import_module('overlay_native')
    def setUp(self):self.api=OverlayAPI()
    def test_passive_overlay_is_topmost_without_activation_and_capture_exclusion_is_acknowledged(self):
        module=self.module()
        with patch.object(module,'_u',self.api):
            record=module.configure_overlay(10,passive=True)
            self.assertTrue(self.api.topmost)
            self.assertEqual(self.api.foreground,99)
            self.assertEqual(self.api.style & 0x080800A0,0x080800A0)
            self.assertTrue(record['capture_excluded'])
            self.assertEqual(self.api.moves,[(10,-1,0x13)])
        module.unregister_overlay(10)
    def test_interactive_policy_removes_only_input_transparency(self):
        module=self.module();self.api.style=0x080800A0 | 0x200
        with patch.object(module,'_u',self.api):
            module.configure_overlay(10,passive=False)
        self.assertFalse(self.api.style & 0x20)
        self.assertTrue(self.api.style & 0x80000)
        self.assertTrue(self.api.style & 0x200)
        module.unregister_overlay(10)
    def test_unsupported_capture_affinity_hides_only_visible_overlay_during_capture(self):
        module=self.module();self.api.affinity_supported=False
        with patch.object(module,'_u',self.api):
            result=module.configure_overlay(10)
            module.register_overlay(11,capture_excluded=False)
            self.assertFalse(result['capture_excluded'])
            with module.capture_scope():
                self.assertFalse(self.api.visible[10])
                self.assertFalse(self.api.visible[11])
            self.assertTrue(self.api.visible[10])
            self.assertFalse(self.api.visible[11])
            self.assertEqual(self.api.shown,[(10,0),(10,4)])
            self.assertEqual(self.api.foreground,99)
        module.unregister_overlay(10);module.unregister_overlay(11)
    def test_affinity_success_without_exclude_ack_uses_failure_fallback(self):
        module=self.module();self.api.affinity_ack=False
        with patch.object(module,'_u',self.api):
            result=module.configure_overlay(10)
            self.assertFalse(result['capture_excluded'])
            with module.capture_scope():self.assertFalse(self.api.visible[10])
            self.assertTrue(self.api.visible[10])
        module.unregister_overlay(10)
    def test_verified_exclusion_keeps_overlay_visible_during_capture(self):
        module=self.module()
        with patch.object(module,'_u',self.api):
            module.configure_overlay(10)
            with module.capture_scope():self.assertTrue(self.api.visible[10])
            self.assertEqual(self.api.shown,[])
        module.unregister_overlay(10)
    def test_capture_exception_restores_without_activating_overlay(self):
        module=self.module()
        with patch.object(module,'_u',self.api):
            module.register_overlay(10,capture_excluded=False)
            with self.assertRaisesRegex(OSError,'capture failed'):
                with module.capture_scope():raise OSError('capture failed')
            self.assertTrue(self.api.visible[10]);self.assertEqual(self.api.foreground,99)
        module.unregister_overlay(10)
    def test_dismissed_overlay_is_not_restored_by_capture_fallback(self):
        module=self.module()
        with patch.object(module,'_u',self.api):
            module.register_overlay(10,capture_excluded=False)
            with module.capture_scope():module.unregister_overlay(10)
            self.assertFalse(self.api.visible[10])
    def test_failed_topmost_policy_is_not_silently_claimed(self):
        module=self.module();self.api.fail_position=True
        with patch.object(module,'_u',self.api):
            with self.assertRaises(OSError):module.configure_overlay(10)
        module.unregister_overlay(10)
    def test_failed_refresh_during_capture_does_not_restore_unsafe_overlay(self):
        module=self.module();self.api.affinity_supported=False
        with patch.object(module,'_u',self.api):
            module.configure_overlay(10)
            with module.capture_scope():
                self.api.fail_position=True
                with self.assertRaises(OSError):module.configure_overlay(10,passive=True)
            self.assertFalse(self.api.visible[10])
    def test_policy_refresh_can_finish_while_capture_waits_for_window_messages(self):
        module=self.module();hidden=threading.Event();release=threading.Event();refreshed=threading.Event()
        failures=[];original=self.api.ShowWindow
        def show(hwnd,command):
            result=original(hwnd,command)
            if command==0:
                hidden.set()
                if not release.wait(2):raise TimeoutError('Fixture hide did not release')
            return result
        self.api.ShowWindow=show
        def capture():
            try:
                with module.capture_scope():pass
            except Exception as exc:failures.append(exc)
        def refresh():
            try:module.configure_overlay(10,passive=True);refreshed.set()
            except Exception as exc:failures.append(exc)
        with patch.object(module,'_u',self.api):
            module.register_overlay(10,capture_excluded=False)
            worker=threading.Thread(target=capture);worker.start()
            self.assertTrue(hidden.wait(1))
            policy=threading.Thread(target=refresh);policy.start()
            try:self.assertTrue(refreshed.wait(.2),'UI policy refresh blocked on worker capture')
            finally:release.set();worker.join(2);policy.join(2)
            self.assertFalse(worker.is_alive());self.assertFalse(policy.is_alive())
            self.assertEqual(failures,[]);self.assertTrue(self.api.visible[10])
        module.unregister_overlay(10)


class OverlayLifecycleTests(unittest.TestCase):
    def overlay(self):
        overlay=SearchOverlay.__new__(SearchOverlay)
        overlay._dismissed=False;overlay._passive_input=False
        overlay.native=10;overlay._heartbeat_job=None
        overlay._started=overlay._stage_started=0.;overlay._deadline=None
        overlay._native_run=False;overlay.candidate_rows={};overlay.activity=Mock()
        overlay.elapsed=Mock();overlay.after=Mock();overlay.withdraw=Mock()
        overlay.update_activity=Mock();overlay.render=Mock();overlay._prepare_native=Mock()
        return overlay
    def test_running_heartbeat_reapplies_topmost_policy(self):
        overlay=self.overlay();overlay.heartbeat()
        overlay._prepare_native.assert_called_once_with()
        self.assertEqual(overlay.after.call_args.args[0],1000)
    def test_dismissed_heartbeat_never_reapplies_or_reopens(self):
        overlay=self.overlay();overlay._dismissed=True;overlay.heartbeat()
        overlay._prepare_native.assert_not_called();overlay.after.assert_not_called()
    def test_native_progress_enables_pass_through_before_status_update(self):
        overlay=self.overlay();overlay.handle('native_progress',{'stage':'search'})
        self.assertTrue(overlay._passive_input)
        overlay._prepare_native.assert_called_once_with()
    def test_native_finish_hides_and_stops_reasserting_topmost(self):
        overlay=self.overlay();overlay._native_run=True
        overlay.handle('finished',{});overlay.heartbeat()
        overlay.withdraw.assert_called_once_with()
        overlay._prepare_native.assert_not_called();overlay.after.assert_not_called()


@unittest.skipUnless(sys.platform=='win32','Native Tk capture fallback requires Windows')
class NativeOverlayWorkerTests(unittest.TestCase):
    def setUp(self):
        import i18n
        self.enterContext(patch.object(i18n,'_widgets',weakref.WeakSet()))
        self.enterContext(patch.object(i18n,'_refreshers',weakref.WeakKeyDictionary()))
    def test_passive_overlay_leaves_dummy_window_foreground_hit_and_capture_unchanged(self):
        import tkinter as tk
        import overlay_native as native
        from PIL import ImageGrab
        root=tk.Tk();root.configure(bg='#16B86A');root.geometry('620x500+80+80')
        root.attributes('-topmost',True)
        def close():
            for job in root.tk.call('after','info'):root.tk.call('after','cancel',job)
            root.destroy()
            import customtkinter as ct
            ct.ScalingTracker.update_loop_running=False
        self.addCleanup(close)
        root.update()
        user=ctypes.windll.user32
        class Point(ctypes.Structure):_fields_=[('x',ctypes.c_long),('y',ctypes.c_long)]
        user.GetAncestor.argtypes=[ctypes.c_void_p,ctypes.c_uint];user.GetAncestor.restype=ctypes.c_void_p
        user.GetForegroundWindow.restype=ctypes.c_void_p
        user.SetForegroundWindow.argtypes=[ctypes.c_void_p]
        user.WindowFromPoint.argtypes=[Point];user.WindowFromPoint.restype=ctypes.c_void_p
        background=user.GetAncestor(root.winfo_id(),2)
        user.SetWindowPos.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_uint]
        # Desktop composition and other app windows can lag behind Tk mapping.
        # Establish the independently known visible pixel before testing the
        # status overlay, while keeping the actual capture comparison strict.
        user.SetForegroundWindow(background);root.update()
        x,y=root.winfo_rootx()+60,root.winfo_rooty()+60
        bbox=(x,y,x+12,y+12)
        until=time.monotonic()+2.
        while True:
            user.SetWindowPos(background,ctypes.c_void_p(-1),0,0,0,0,0x53)
            root.update()
            ctypes.WinDLL('dwmapi').DwmFlush()
            baseline=ImageGrab.grab(bbox=bbox,all_screens=True).convert('RGB')
            if baseline.getpixel((5,5))==(22,184,106) or time.monotonic()>=until:break
            time.sleep(.01)
        self.assertEqual(baseline.getpixel((5,5)),(22,184,106))
        foreground=user.GetForegroundWindow()
        rules=[dict(enabled=True,exact=True,colors=['#000000'],tolerance=0.) for _ in range(3)]
        overlay=SearchOverlay(root,lambda:None)
        self.addCleanup(overlay.destroy)
        overlay.begin(rules,passive=True)
        overlay.geometry(f'+{root.winfo_rootx()+20}+{root.winfo_rooty()+20}')
        end=time.monotonic()+.25
        while time.monotonic()<end:root.update();time.sleep(.005)
        overlay._prepare_native()
        self.assertEqual(user.GetForegroundWindow(),foreground,
            f'background={background} overlay={overlay.native} foreground={user.GetForegroundWindow()}')
        hit=user.WindowFromPoint(Point(x+5,y+5))
        self.assertEqual(user.GetAncestor(hit,2),background,'Passive surface intercepted dummy client hit')
        with native.capture_scope():
            captured=ImageGrab.grab(bbox=bbox,all_screens=True).convert('RGB')
        self.assertEqual(captured.tobytes(),baseline.tobytes(),'Visible status surface contaminated capture')
        native.register_overlay(overlay.native,capture_excluded=False)
        with native.capture_scope():
            self.assertFalse(user.IsWindowVisible(overlay.native))
            fallback=ImageGrab.grab(bbox=bbox,all_screens=True).convert('RGB')
        self.assertEqual(fallback.tobytes(),baseline.tobytes())
        self.assertTrue(user.IsWindowVisible(overlay.native))
        self.assertEqual(user.GetForegroundWindow(),foreground)
        overlay.dismiss()

    def test_worker_capture_and_ui_policy_refresh_complete_without_focus_change(self):
        import tkinter as tk
        import overlay_native as native
        root=tk.Tk();root.withdraw()
        self.addCleanup(root.destroy)
        overlay=tk.Toplevel(root);overlay.withdraw();overlay.overrideredirect(True)
        overlay.geometry('180x90+80+80');overlay.configure(bg='#D02030')
        root.update_idletasks()
        user=ctypes.windll.user32
        user.GetAncestor.argtypes=[ctypes.c_void_p,ctypes.c_uint];user.GetAncestor.restype=ctypes.c_void_p
        user.GetForegroundWindow.restype=ctypes.c_void_p
        hwnd=user.GetAncestor(overlay.winfo_id(),2)
        native.configure_overlay(hwnd,passive=True)
        overlay.deiconify();root.update()
        native.configure_overlay(hwnd,passive=True)
        foreground=user.GetForegroundWindow()
        # Force the supported fallback independently of this machine's WDA.
        native.register_overlay(hwnd,capture_excluded=False)
        self.addCleanup(native.unregister_overlay,hwnd)
        entered=threading.Event();finished=threading.Event();failures=[]
        def worker():
            try:
                with native.capture_scope():
                    entered.set();time.sleep(.08)
            except Exception as exc:failures.append(exc)
            finally:finished.set()
        thread=threading.Thread(target=worker,daemon=True);thread.start()
        end=time.monotonic()+3
        while not finished.is_set() and time.monotonic()<end:
            root.update()
            if entered.is_set():native.configure_overlay(hwnd,passive=True)
            time.sleep(.005)
        self.assertTrue(finished.is_set(),'Worker capture did not finish while Tk processed policy updates')
        thread.join(.2)
        self.assertEqual(failures,[])
        self.assertTrue(user.IsWindowVisible(hwnd))
        self.assertEqual(user.GetForegroundWindow(),foreground)


if __name__=='__main__':unittest.main()
