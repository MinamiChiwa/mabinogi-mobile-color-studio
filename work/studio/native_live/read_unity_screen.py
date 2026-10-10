"""Current UnityPlayer Screen.width/height fields, without getter calls."""
import ctypes
import ntpath
import struct
from ctypes import wintypes
from pathlib import Path

from .read_native_rect import SUPPORTED_UNITYPLAYER
from .runtime_read import P


def _windows_module_path(path):
    value=str(path).replace('/', '\\')
    if value[:8].casefold()=='\\\\?\\unc\\':value='\\\\'+value[8:]
    elif value.startswith('\\\\?\\'):value=value[4:]
    return ntpath.normcase(ntpath.normpath(value))


def _same_loaded_file(loaded_path, expected_path):
    """Confirm a spelling difference only when both paths identify one file."""
    try:
        return Path(loaded_path).samefile(Path(expected_path))
    except (OSError, ValueError):
        return False


def unityplayer_module_base(reader, *, expected_path=None, check=lambda:None):
    """Find the loaded Unity DLL, bound to the selected build path when known."""
    if expected_path is None:
        expected_path=getattr(reader,'module_files',{}).get('unityplayer.dll')
    expected=_windows_module_path(expected_path) if expected_path is not None else None
    check();modules=(ctypes.c_void_p*2048)();needed=wintypes.DWORD()
    if not P.EnumProcessModulesEx(reader.h,modules,ctypes.sizeof(modules),ctypes.byref(needed),3):
        raise OSError('Cannot enumerate UnityPlayer module')
    if needed.value>ctypes.sizeof(modules):raise ValueError('Too many process modules')
    matches=[]
    for module in modules[:needed.value//ctypes.sizeof(ctypes.c_void_p)]:
        check();name=ctypes.create_unicode_buffer(32768)
        if not P.GetModuleFileNameExW(reader.h,module,name,len(name)):raise OSError('Cannot read module path')
        path=_windows_module_path(name.value)
        if ntpath.basename(path)!='unityplayer.dll':continue
        same_expected = expected is None or path == expected or _same_loaded_file(name.value, expected_path)
        if same_expected:
            matches.append(module)
    if len(matches)!=1:raise ValueError('Expected unique current-build UnityPlayer module')
    return matches[0]


def read_unity_screen_extent(reader,module_base,*,unityplayer_sha256,check=lambda:None):
    if unityplayer_sha256!=SUPPORTED_UNITYPLAYER:raise ValueError('Unsupported Screen layout build')
    if type(module_base) is not int or module_base<=0 or module_base%4096:raise ValueError('Invalid UnityPlayer base')
    reads={}
    def read(a,size):
        check();raw=reader.read(a,size)
        if len(raw)!=size or reads.setdefault((a,size),raw)!=raw:raise ValueError('Short/changed Screen read')
        return raw
    state=struct.unpack('<Q',read(module_base+0x1b23390,8))[0]
    if not state or state%8:raise ValueError('Null/unaligned Screen state')
    width=struct.unpack('<i',read(state+0xfc,4))[0]
    height=struct.unpack('<i',read(state+0x108,4))[0]
    hwnd=struct.unpack('<Q',read(state+0xe0,8))[0]
    if not 1<=width<=65536 or not 1<=height<=65536:raise ValueError('Invalid Unity screen extent')
    for (a,size),raw in reads.items():
        check()
        if reader.read(a,size)!=raw:raise ValueError('Unity screen extent changed')
    return dict(source='current_build_native_screen_fields',module_base=module_base,state_address=state,
                size=[width,height],hwnd=hwnd,ready_for_input=False,
                scope='Original Screen getters field semantics; double-read only, no frame atomicity or desktop mapping proof')
