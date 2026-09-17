"""DPI-aware Windows client capture and paced, cancellable SendInput."""
import ctypes as C, time, math
from ctypes import wintypes as W
import numpy as np
from PIL import ImageGrab

u=C.windll.user32
try:u.SetProcessDpiAwarenessContext(C.c_void_p(-4))
except (AttributeError,OSError):
    try:C.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:pass
u.FindWindowW.argtypes=[W.LPCWSTR,W.LPCWSTR]; u.FindWindowW.restype=W.HWND
u.GetForegroundWindow.restype=W.HWND
for name in ['GetClientRect','ClientToScreen','SetForegroundWindow','IsIconic','GetDpiForWindow']:
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

def rotation_path(board,anchor,angle):
    """Use the longest safe arc to reduce angular error from integer pixels."""
    l,t,r,b=board;cx,cy=map(round,anchor);best=None
    if not(l+8<cx<r-8 and t+8<cy<b-8):raise ValueError('旋转按下点距离色板边缘太近。')
    for base in range(0,360,15):
        angles=np.radians(base+np.linspace(0,angle,49));vx=np.cos(angles);vy=np.sin(angles)
        limits=[min(r-l,b-t)*.8]
        for values,negative,positive in ((vx,cx-l-6,r-cx-6),(vy,cy-t-6,b-cy-6)):
            if np.any(values>1e-6):limits.append(float(np.min(positive/values[values>1e-6])))
            if np.any(values<-1e-6):limits.append(float(np.min(-negative/values[values<-1e-6])))
        radius=min(limits)
        if best is None or radius>best[0]:best=(radius,base)
    radius,base=best;theta=math.radians(base)
    points=[(round(cx+radius*i/8*math.cos(theta)),round(cy+radius*i/8*math.sin(theta))) for i in range(9)]
    points += [(round(cx+radius*math.cos(math.radians(base+angle*i/24))),round(cy+radius*math.sin(math.radians(base+angle*i/24)))) for i in range(1,25)]
    return points

class Game:
    def __init__(self,stop):
        self.stop=stop; self.hwnd=u.FindWindowW(None,'瑪奇 Mobile')
        if not self.hwnd:raise RuntimeError('未找到瑪奇 Mobile。请先启动台服游戏。')
        self.initial=self.geometry()
    def geometry(self):
        if u.IsIconic(self.hwnd):raise RuntimeError('游戏窗口已最小化，请恢复后重试。')
        r=W.RECT(); p=W.POINT(0,0)
        if not u.GetClientRect(self.hwnd,C.byref(r)) or not u.ClientToScreen(self.hwnd,C.byref(p)):raise RuntimeError('游戏窗口已关闭。')
        return p.x,p.y,r.right,r.bottom
    def focus(self):
        u.SetForegroundWindow(self.hwnd); time.sleep(.18)
        if u.GetForegroundWindow()!=self.hwnd:raise RuntimeError('无法激活游戏。请点击游戏后按 F8。')
    def check(self):
        if self.stop.is_set():raise Interrupted('已停止，鼠标已释放。')
        if u.GetForegroundWindow()!=self.hwnd:raise Interrupted('已暂停：游戏失去焦点。返回游戏后按 F8 重新开始。')
        if self.geometry()!=self.initial:raise Interrupted('窗口位置或尺寸已变化。已停止，请按 F8 重新识别。')
    def capture(self):
        self.check(); x,y,w,h=self.geometry()
        return np.array(ImageGrab.grab(bbox=(x,y,x+w,y+h),all_screens=True).convert('RGB'))
    def capture_waiting(self):
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
        self.check(); down,up=(8,16) if right else (2,4)
        self.move_to(points[0]); time.sleep(.08); self.send(down)
        try:
            time.sleep(.10)
            previous=points[0]
            for p in points[1:]:
                self.check()
                # Relative MOUSEEVENTF_MOVE emits real movement events for game input.
                dx,dy=round(p[0]-previous[0]),round(p[1]-previous[1])
                if dx or dy:
                    if absolute:self.move_to(p)
                    else:self.send(1,dx,dy)
                previous=p; time.sleep(.018)
            time.sleep(.08)
        finally:self.send(up)
    def drag(self,board,dx,dy):
        l,t,r,b=board; margin=12
        dx=int(np.clip(dx,-(r-l)*.65,(r-l)*.65)); dy=int(np.clip(dy,-(b-t)*.65,(b-t)*.65))
        sx=round((l+r-dx)/2); sy=round((t+b-dy)/2)
        count=max(1,min(24,max(abs(dx),abs(dy))))
        pts=[(round(sx+dx*i/count),round(sy+dy*i/count)) for i in range(count+1)]
        self.path(pts,absolute=True)
    def rotate(self,board,angle=30,anchor=None):
        l,t,r,b=board; cx,cy=anchor if anchor is not None else ((l+r)/2,(t+b)/2)
        # The game anchors rotation at right-button DOWN, not the arc's center.
        # Establish that anchor, move radially out while held, then trace the arc.
        pts=rotation_path(board,(cx,cy),angle)
        self.path(pts,right=True,absolute=True)
    def wheel(self,board,steps,anchor=None):
        self.check(); l,t,r,b=board
        point=anchor if anchor is not None else ((l+r)/2,(t+b)/2)
        if not(l<point[0]<r and t<point[1]<b):raise ValueError('缩放中心必须位于色板内。')
        self.move_to(point)
        # Separate notches so the game receives each tick; cancellable during bursts.
        for _ in range(min(32,abs(int(steps)))):
            self.check();self.send(0x800,data=(1 if steps>0 else -1)*120);time.sleep(.018)
        time.sleep(.10)
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
