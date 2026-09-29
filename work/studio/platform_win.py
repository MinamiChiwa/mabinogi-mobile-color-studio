"""DPI-aware Windows client capture and paced, cancellable SendInput."""
import ctypes as C, time
from ctypes import wintypes as W
import numpy as np
from PIL import ImageGrab
from window_target import resolve_target,valid_target,WindowUnavailable
from input_gestures import (drag_gesture, grouped_rotation_gesture, rotation_path,
                            wheel_gesture, path_gesture)

u=C.windll.user32
try:u.SetProcessDpiAwarenessContext(C.c_void_p(-4))
except (AttributeError,OSError):
    try:C.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:pass
u.FindWindowW.argtypes=[W.LPCWSTR,W.LPCWSTR]; u.FindWindowW.restype=W.HWND
u.GetForegroundWindow.restype=W.HWND
for name in ['GetClientRect','ClientToScreen','SetForegroundWindow','IsIconic','GetDpiForWindow','IsWindow']:
    getattr(u,name).argtypes=[W.HWND]+([C.c_void_p] if name in ['GetClientRect','ClientToScreen'] else [])
ULONG_PTR=C.c_size_t
class Mouse(C.Structure):
    _fields_=[('dx',W.LONG),('dy',W.LONG),('mouseData',W.DWORD),('dwFlags',W.DWORD),('time',W.DWORD),('dwExtraInfo',ULONG_PTR)]
class Keyboard(C.Structure):
    _fields_=[('wVk',W.WORD),('wScan',W.WORD),('dwFlags',W.DWORD),('time',W.DWORD),('dwExtraInfo',ULONG_PTR)]
class Payload(C.Union):
    _fields_=[('mi',Mouse),('ki',Keyboard)]
class Input(C.Structure):
    _anonymous_=('p',); _fields_=[('type',W.DWORD),('p',Payload)]
u.SendInput.argtypes=[W.UINT,C.POINTER(Input),C.c_int]; u.SendInput.restype=W.UINT

class Interrupted(Exception):pass

class Game:
    def __init__(self,stop,target=None):
        self.stop=stop;self.manual_target=target;self.target=resolve_target(target);self.hwnd=self.target.hwnd
        self.initial=None if u.IsIconic(self.hwnd) else self.geometry()
    def geometry(self):
        if not valid_target(self.target):raise Interrupted('所选窗口已关闭，请重新选择游戏窗口。')
        if u.IsIconic(self.hwnd):raise RuntimeError('游戏窗口已最小化，请恢复后重试。')
        r=W.RECT(); p=W.POINT(0,0)
        if not u.GetClientRect(self.hwnd,C.byref(r)) or not u.ClientToScreen(self.hwnd,C.byref(p)):raise RuntimeError('游戏窗口已关闭。')
        return p.x,p.y,r.right,r.bottom
    def focus(self):
        if u.IsIconic(self.hwnd):
            u.ShowWindow.argtypes=[W.HWND,C.c_int];u.ShowWindow(self.hwnd,9)
        self.initial=self.geometry()
        u.SetForegroundWindow(self.hwnd); time.sleep(.18)
        if u.GetForegroundWindow()!=self.hwnd:raise RuntimeError('无法激活游戏。请点击游戏后按 F8。')
    def check(self):
        if self.stop.is_set():raise Interrupted('已停止，鼠标已释放。')
        if u.GetForegroundWindow()!=self.hwnd:raise Interrupted('已暂停：游戏失去焦点。返回游戏后按 F8 重新开始。')
        if self.geometry()!=self.initial:raise Interrupted('窗口位置或尺寸已变化。已停止，请按 F8 重新识别。')
    def capture(self):
        self.check(); x,y,w,h=self.geometry()
        self.captured_at=time.monotonic()
        return np.array(ImageGrab.grab(bbox=(x,y,x+w,y+h),all_screens=True).convert('RGB'))
    def capture_waiting(self):
        if not valid_target(self.target):
            if self.manual_target is not None:raise WindowUnavailable('所选窗口已关闭，请重新选择游戏窗口。')
            try:self.target=resolve_target();self.hwnd=self.target.hwnd
            except WindowUnavailable:return None
        if self.stop.is_set():raise Interrupted('已停止，鼠标已释放。')
        if u.IsIconic(self.hwnd) or u.GetForegroundWindow()!=self.hwnd:return None
        self.initial=self.geometry()
        return self.capture()
    def send(self,flags,dx=0,dy=0,data=0):
        event=Input(type=0,mi=Mouse(dx,dy,data&0xffffffff,flags,0,0))
        if u.SendInput(1,C.byref(event),C.sizeof(Input))!=1:raise RuntimeError('Windows 未接受鼠标输入。请检查游戏与工具是否使用相同权限运行。')
    def move_to(self,p):
        x,y,w,h=self.geometry(); vx,vy=u.GetSystemMetrics(76),u.GetSystemMetrics(77)
        vw,vh=u.GetSystemMetrics(78),u.GetSystemMetrics(79)
        self.send(0x8000|0x4000|1,round((x+p[0]-vx)*65535/max(1,vw-1)),round((y+p[1]-vy)*65535/max(1,vh-1)))
    def path(self,points,right=False,absolute=False):
        return self.perform_gesture(path_gesture(points,right,absolute))
    def perform_gesture(self,gesture):
        """Send the already planned integer descriptor without regenerating it."""
        self.check()
        self.last_gesture=gesture
        if not gesture.has_effect:return False
        timing=gesture.timing;points=gesture.points
        trace=[] if getattr(self,'capture_input_trace',False) else None
        self.last_input_trace=trace
        trace_origin=self.geometry()[:2] if trace is not None else None
        trace_start=time.perf_counter() if trace is not None else None
        def observe(slot):
            if trace is None:return
            try:
                cursor=W.POINT()
                if not u.GetCursorPos(C.byref(cursor)):raise OSError('GetCursorPos failed')
                actual=[int(cursor.x-trace_origin[0]),int(cursor.y-trace_origin[1])]
                error=None
            except Exception as exc:
                actual=None;error=str(exc)
            trace.append(dict(slot=slot,requested=list(points[slot]),actual_client=actual,
                              elapsed_seconds=time.perf_counter()-trace_start,error=error))
        self.move_to(gesture.anchor)
        if gesture.kind=='wheel':
            observe(0)
            for _ in range(abs(gesture.wheel_steps)):
                self.check()
                self.send(0x800,data=(1 if gesture.wheel_steps>0 else -1)*120)
                time.sleep(timing.point_interval)
            time.sleep(timing.after_wheel)
            return True
        down,up=(8,16) if gesture.right else (2,4)
        time.sleep(timing.before_down)
        observe(0)
        try:
            self.send(down)
            time.sleep(timing.after_down)
            previous=points[0]
            for slot,p in enumerate(points[1:],1):
                self.check()
                # Relative MOUSEEVENTF_MOVE emits real movement events for game input.
                dx,dy=round(p[0]-previous[0]),round(p[1]-previous[1])
                if dx or dy:
                    if gesture.absolute:self.move_to(p)
                    else:self.send(1,dx,dy)
                previous=p; time.sleep(timing.point_interval)
                observe(slot)
            time.sleep(timing.before_up)
        finally:self.send(up)
        return True
    def drag(self,board,dx,dy):
        return self.perform_gesture(drag_gesture(board,dx,dy))
    def rotate(self,board,angle=30,anchor=None):
        # The game anchors rotation at right-button DOWN, not the arc's center.
        # Establish that anchor, move radially out while held, then trace the arc.
        return self.perform_gesture(grouped_rotation_gesture(board,angle,anchor))
    def wheel(self,board,steps,anchor=None):
        return self.perform_gesture(wheel_gesture(board,steps,anchor))
    def click(self,p):
        self.check(); self.move_to(p); time.sleep(.06); self.send(2)
        try:time.sleep(.09)
        finally:self.send(4)
    def escape(self):
        self.check()
        for flag in [0,2]:
            event=Input(type=1,ki=Keyboard(0x1B,0,flag,0,0))
            if u.SendInput(1,C.byref(event),C.sizeof(Input))!=1:raise RuntimeError('键盘输入被 Windows 拒绝。')
            time.sleep(.08)
