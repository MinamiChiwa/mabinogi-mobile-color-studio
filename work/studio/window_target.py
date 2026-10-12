"""Discover a game window once and bind input to its HWND and process."""
import ctypes as C
from ctypes import wintypes as W
from dataclasses import dataclass
import os,time,unicodedata

@dataclass(frozen=True)
class WindowTarget:
    hwnd:int
    pid:int
    title:str
    executable:str=''

class WindowUnavailable(RuntimeError):pass
class MultipleWindows(WindowUnavailable):pass

u=C.windll.user32;k=C.windll.kernel32
u.GetWindowThreadProcessId.argtypes=[W.HWND,C.POINTER(W.DWORD)];u.GetWindowThreadProcessId.restype=W.DWORD
u.GetWindowTextLengthW.argtypes=[W.HWND];u.GetWindowTextLengthW.restype=C.c_int
u.GetWindowTextW.argtypes=[W.HWND,W.LPWSTR,C.c_int];u.GetWindowTextW.restype=C.c_int
u.IsWindowVisible.argtypes=[W.HWND];u.IsWindowVisible.restype=W.BOOL
u.IsWindow.argtypes=[W.HWND];u.IsWindow.restype=W.BOOL
u.GetForegroundWindow.restype=W.HWND
u.SetForegroundWindow.argtypes=[W.HWND];u.SetForegroundWindow.restype=W.BOOL
u.BringWindowToTop.argtypes=[W.HWND];u.BringWindowToTop.restype=W.BOOL
u.AttachThreadInput.argtypes=[W.DWORD,W.DWORD,W.BOOL];u.AttachThreadInput.restype=W.BOOL
u.ShowWindow.argtypes=[W.HWND,C.c_int];u.ShowWindow.restype=W.BOOL
k.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];k.OpenProcess.restype=W.HANDLE
k.QueryFullProcessImageNameW.argtypes=[W.HANDLE,W.DWORD,W.LPWSTR,C.POINTER(W.DWORD)];k.QueryFullProcessImageNameW.restype=W.BOOL
k.CloseHandle.argtypes=[W.HANDLE]
k.GetCurrentThreadId.restype=W.DWORD
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

SERVER_TITLES={'tw':('瑪奇 Mobile','玛奇 Mobile'),
               'kr':('마비노기 모바일',), 'jp':('マビモバ','マビノギモバイル')}

def matching_game_windows(windows,server=None):
    if server is not None and server not in SERVER_TITLES:raise ValueError('Unknown game server')
    titles={normalized_title(t):s for s,aliases in SERVER_TITLES.items() for t in aliases}
    candidates=[]
    for w in windows:
        title=normalized_title(w.title);known=titles.get(title)
        if known is not None:
            if server is None or server==known:candidates.append(w)
        elif title=='mabinogimobile' or w.executable.casefold()=='mabinogimobile.exe':
            candidates.append(w)
    return candidates

def choose_auto(windows,foreground=0,*,server=None):
    candidates=matching_game_windows(windows,server)
    if len(candidates)==1:return candidates[0]
    active=[w for w in candidates if w.hwnd==foreground]
    if len(active)==1:return active[0]
    if candidates:raise MultipleWindows('发现多个游戏窗口，请手动选择目标窗口。')
    raise WindowUnavailable('未找到游戏窗口。请启动游戏，或手动选择窗口。')

def valid_target(target):
    return bool(u.IsWindow(target.hwnd)) and window_pid(target.hwnd)==target.pid

def activate_target_window(target):
    """Return the bound game window to the foreground after an overlay click.

    The retry button is deliberately usable without activating the overlay,
    but Windows can still leave the game unfocused on some DPI/window-manager
    combinations. Reasserting the already validated HWND before the worker
    consumes the request prevents the input guard from treating the button
    click as a session failure.
    """
    if target is None or not valid_target(target):
        return False
    if u.IsIconic(target.hwnd):
        u.ShowWindow(target.hwnd,9)  # SW_RESTORE
    current_thread=int(k.GetCurrentThreadId())
    foreground=u.GetForegroundWindow()
    foreground_thread=(int(u.GetWindowThreadProcessId(foreground,None))
                       if foreground else 0)
    attached=False
    if foreground_thread and foreground_thread!=current_thread:
        attached=bool(u.AttachThreadInput(current_thread,foreground_thread,True))
    try:
        u.BringWindowToTop(target.hwnd)
        u.SetForegroundWindow(target.hwnd)
        for _ in range(6):
            foreground=u.GetForegroundWindow()
            if foreground and int(foreground)==int(target.hwnd):return True
            time.sleep(.03)
        return False
    finally:
        if attached:u.AttachThreadInput(current_thread,foreground_thread,False)

def resolve_target(target=None,*,server=None):
    if target is None:return choose_auto(list_windows(),u.GetForegroundWindow(),server=server)
    if not valid_target(target):raise WindowUnavailable('所选窗口已关闭，请重新选择游戏窗口。')
    return target
