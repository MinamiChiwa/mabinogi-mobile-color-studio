"""Discover a game window once and bind input to its HWND and process."""
import ctypes as C
from ctypes import wintypes as W
from dataclasses import dataclass
import os,unicodedata

@dataclass(frozen=True)
class WindowTarget:
    hwnd:int
    pid:int
    title:str
    executable:str=''

class WindowUnavailable(RuntimeError):pass

u=C.windll.user32;k=C.windll.kernel32
u.GetWindowThreadProcessId.argtypes=[W.HWND,C.POINTER(W.DWORD)];u.GetWindowThreadProcessId.restype=W.DWORD
u.GetWindowTextLengthW.argtypes=[W.HWND];u.GetWindowTextLengthW.restype=C.c_int
u.GetWindowTextW.argtypes=[W.HWND,W.LPWSTR,C.c_int];u.GetWindowTextW.restype=C.c_int
u.IsWindowVisible.argtypes=[W.HWND];u.IsWindowVisible.restype=W.BOOL
u.IsWindow.argtypes=[W.HWND];u.IsWindow.restype=W.BOOL
u.GetForegroundWindow.restype=W.HWND
k.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];k.OpenProcess.restype=W.HANDLE
k.QueryFullProcessImageNameW.argtypes=[W.HANDLE,W.DWORD,W.LPWSTR,C.POINTER(W.DWORD)];k.QueryFullProcessImageNameW.restype=W.BOOL
k.CloseHandle.argtypes=[W.HANDLE]
CALLBACK=C.WINFUNCTYPE(W.BOOL,W.HWND,W.LPARAM)
u.EnumWindows.argtypes=[CALLBACK,W.LPARAM];u.EnumWindows.restype=W.BOOL

def window_pid(hwnd):
    pid=W.DWORD();u.GetWindowThreadProcessId(hwnd,C.byref(pid));return pid.value

def window_title(hwnd):
    text=C.create_unicode_buffer(u.GetWindowTextLengthW(hwnd)+1)
    u.GetWindowTextW(hwnd,text,len(text));return text.value

def list_windows():
    windows=[]
    @CALLBACK
    def visit(hwnd,_):
        if not u.IsWindowVisible(hwnd):return True
        title=window_title(hwnd);pid=window_pid(hwnd)
        if not title or pid==os.getpid():return True
        executable='';handle=k.OpenProcess(0x1000,False,pid)
        if handle:
            try:
                size=W.DWORD(32768);buffer=C.create_unicode_buffer(size.value)
                if k.QueryFullProcessImageNameW(handle,0,buffer,C.byref(size)):executable=os.path.basename(buffer.value)
            finally:k.CloseHandle(handle)
        windows.append(WindowTarget(int(hwnd),pid,title,executable));return True
    if not u.EnumWindows(visit,0):raise RuntimeError('无法读取窗口列表，请重试。')
    return windows

def normalized_title(title):
    return ''.join(unicodedata.normalize('NFKC',title).casefold().split())

def choose_auto(windows,foreground=0):
    aliases={'瑪奇mobile','玛奇mobile','mabinogimobile'}
    candidates=[w for w in windows if normalized_title(w.title) in aliases or w.executable.casefold()=='mabinogimobile.exe']
    if len(candidates)==1:return candidates[0]
    active=[w for w in candidates if w.hwnd==foreground]
    if len(active)==1:return active[0]
    if candidates:raise WindowUnavailable('发现多个游戏窗口，请手动选择目标窗口。')
    raise WindowUnavailable('未找到游戏窗口。请启动游戏，或手动选择窗口。')

def valid_target(target):
    return bool(u.IsWindow(target.hwnd)) and window_pid(target.hwnd)==target.pid

def resolve_target(target=None):
    if target is None:return choose_auto(list_windows(),u.GetForegroundWindow())
    if not valid_target(target):raise WindowUnavailable('所选窗口已关闭，请重新选择游戏窗口。')
    return target
