"""Message hotkeys with registered-key polling fallback and edge deduplication."""
import time

class KeyEdges:
    def __init__(self):self.down={};self.last={}
    def accept(self,key,now):
        if now-self.last.get(key,-100)<.35:return False
        self.last[key]=now;return True
    def poll(self,key,down,now):
        rising=down and not self.down.get(key,False);self.down[key]=down
        return rising and self.accept(key,now)

def run_hotkeys(user,ctypes,types,stop,emit,keys):
    user.RegisterHotKey.argtypes=[types.HWND,ctypes.c_int,types.UINT,types.UINT]
    user.RegisterHotKey.restype=types.BOOL
    user.UnregisterHotKey.argtypes=[types.HWND,ctypes.c_int]
    user.GetAsyncKeyState.argtypes=[ctypes.c_int];user.GetAsyncKeyState.restype=ctypes.c_short
    user.PeekMessageW.argtypes=[ctypes.POINTER(types.MSG),types.HWND,types.UINT,types.UINT,types.UINT]
    user.PeekMessageW.restype=types.BOOL
    registered={};edges=KeyEdges()
    try:
        for key,vk in keys:
            if user.RegisterHotKey(None,key,0x4000,vk):registered[key]=vk
        emit('hotkey_status',{'available':list(registered),'failed':[key for key,vk in keys if key not in registered]})
        msg=types.MSG()
        while not stop.is_set():
            while user.PeekMessageW(ctypes.byref(msg),None,0x312,0x312,1):
                key=int(msg.wParam)
                if key in registered and edges.accept(key,time.monotonic()):emit('hotkey',{'id':key})
            for key,vk in registered.items():
                if edges.poll(key,bool(user.GetAsyncKeyState(vk)&0x8000),time.monotonic()):emit('hotkey',{'id':key})
            stop.wait(.025)
    except Exception as exc:
        emit('hotkey_status',{'available':[],'failed':[key for key,vk in keys],'error':str(exc)})
    finally:
        for key in registered:user.UnregisterHotKey(None,key)
