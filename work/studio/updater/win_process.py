"""Crash-released OS file lock and identity-bound process waits."""
import os,time,ctypes,subprocess
from pathlib import Path
from .paths import checked_root

class UpdateLock:
    def __init__(self,root):self.path=checked_root(root)/'.colorstudio-update.lock';self.handle=None
    def __enter__(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.handle=self.path.open('a+b');self.handle.seek(0);self.handle.write(b'0');self.handle.flush();self.handle.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            self.handle.close();self.handle=None;raise RuntimeError('another update is already running')
        return self
    def __exit__(self,*exc):
        if self.handle:
            self.handle.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.handle.fileno(),msvcrt.LK_UNLCK,1)
            self.handle.close();self.handle=None

def process_creation(pid):
    if os.name!='nt':return 0
    from ctypes import wintypes as W
    k=ctypes.WinDLL('kernel32',use_last_error=True)
    k.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];k.OpenProcess.restype=W.HANDLE
    k.CloseHandle.argtypes=[W.HANDLE]
    k.GetProcessTimes.argtypes=[W.HANDLE,*([ctypes.POINTER(W.FILETIME)]*4)]
    handle=k.OpenProcess(0x1000|0x100000,False,pid)
    if not handle:return None
    try:
        times=[W.FILETIME() for _ in range(4)]
        if not k.GetProcessTimes(handle,*(ctypes.byref(v) for v in times)):return None
        return times[0].dwLowDateTime|(times[0].dwHighDateTime<<32)
    finally:k.CloseHandle(handle)

def wait_parent(pid,creation,timeout=60):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        if process_creation(pid)!=creation:return
        time.sleep(.1)
    raise RuntimeError('parent process did not exit; installation cancelled')

def launch_helper(helper,transaction,pid,creation):
    return subprocess.Popen([str(helper),'--transaction',str(transaction),'--parent-pid',str(pid),
        '--parent-creation',str(creation)],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),close_fds=True)

def other_install_instances(root,exclude=()):
    """Only same-install ColorStudio instances; unrelated tools/game stay alone."""
    if os.name!='nt':return []
    from ctypes import wintypes as W
    k=ctypes.WinDLL('kernel32',use_last_error=True)
    class Entry(ctypes.Structure):
        _fields_=[('dwSize',W.DWORD),('cntUsage',W.DWORD),('th32ProcessID',W.DWORD),
            ('th32DefaultHeapID',ctypes.c_size_t),('th32ModuleID',W.DWORD),('cntThreads',W.DWORD),
            ('th32ParentProcessID',W.DWORD),('pcPriClassBase',W.LONG),('dwFlags',W.DWORD),('szExeFile',W.WCHAR*260)]
    k.CreateToolhelp32Snapshot.argtypes=[W.DWORD,W.DWORD];k.CreateToolhelp32Snapshot.restype=W.HANDLE
    k.Process32FirstW.argtypes=[W.HANDLE,ctypes.POINTER(Entry)];k.Process32NextW.argtypes=[W.HANDLE,ctypes.POINTER(Entry)]
    k.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];k.OpenProcess.restype=W.HANDLE
    k.QueryFullProcessImageNameW.argtypes=[W.HANDLE,W.DWORD,W.LPWSTR,ctypes.POINTER(W.DWORD)]
    k.CloseHandle.argtypes=[W.HANDLE]
    handle=k.CreateToolhelp32Snapshot(2,0)
    if handle==ctypes.c_void_p(-1).value:raise OSError('Cannot enumerate tool processes')
    excluded={os.getpid(),*exclude};found=[];expected=os.path.normcase(str(Path(root).absolute()/'ColorStudio.exe'))
    try:
        entry=Entry();entry.dwSize=ctypes.sizeof(entry);valid=k.Process32FirstW(handle,ctypes.byref(entry))
        while valid:
            if entry.th32ProcessID not in excluded and entry.szExeFile.casefold()=='colorstudio.exe':
                process=k.OpenProcess(0x1000,False,entry.th32ProcessID)
                if not process:raise PermissionError('Cannot check another ColorStudio instance')
                try:
                    size=W.DWORD(32768);buffer=ctypes.create_unicode_buffer(size.value)
                    if not k.QueryFullProcessImageNameW(process,0,buffer,ctypes.byref(size)):raise OSError('Cannot resolve tool process')
                    if os.path.normcase(buffer.value)==expected:found.append(entry.th32ProcessID)
                finally:k.CloseHandle(process)
            valid=k.Process32NextW(handle,ctypes.byref(entry))
    finally:k.CloseHandle(handle)
    return found
