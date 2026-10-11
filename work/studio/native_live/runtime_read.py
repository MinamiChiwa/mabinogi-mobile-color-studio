"""Read-only Windows process inspection for dye-specific IL2CPP data."""
import ctypes,struct,json
from ctypes import wintypes
from pathlib import Path
from process_access import ProcessReadDenied
K=ctypes.WinDLL('kernel32',use_last_error=True);P=ctypes.WinDLL('psapi',use_last_error=True)
K.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];K.OpenProcess.restype=wintypes.HANDLE
K.ReadProcessMemory.argtypes=[wintypes.HANDLE,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.POINTER(ctypes.c_size_t)];K.ReadProcessMemory.restype=wintypes.BOOL
K.CloseHandle.argtypes=[wintypes.HANDLE]
class MBI(ctypes.Structure):
 _fields_=[('BaseAddress',ctypes.c_void_p),('AllocationBase',ctypes.c_void_p),('AllocationProtect',wintypes.DWORD),('PartitionId',wintypes.WORD),('_pad',wintypes.WORD),('RegionSize',ctypes.c_size_t),('State',wintypes.DWORD),('Protect',wintypes.DWORD),('Type',wintypes.DWORD)]
class _SYSTEM_INFO_ARCH(ctypes.Structure):
 _fields_=[('wProcessorArchitecture',wintypes.WORD),('wReserved',wintypes.WORD)]
class _SYSTEM_INFO_UNION(ctypes.Union):
 _anonymous_=('arch',)
 _fields_=[('dwOemId',wintypes.DWORD),('arch',_SYSTEM_INFO_ARCH)]
class SYSTEM_INFO(ctypes.Structure):
 _anonymous_=('processor',)
 _fields_=[('processor',_SYSTEM_INFO_UNION),('dwPageSize',wintypes.DWORD),
  ('lpMinimumApplicationAddress',ctypes.c_void_p),('lpMaximumApplicationAddress',ctypes.c_void_p),
  ('dwActiveProcessorMask',ctypes.c_size_t),('dwNumberOfProcessors',wintypes.DWORD),
  ('dwProcessorType',wintypes.DWORD),('dwAllocationGranularity',wintypes.DWORD),
  ('wProcessorLevel',wintypes.WORD),('wProcessorRevision',wintypes.WORD)]
K.GetNativeSystemInfo.argtypes=[ctypes.POINTER(SYSTEM_INFO)];K.GetNativeSystemInfo.restype=None
K.VirtualQueryEx.argtypes=[wintypes.HANDLE,ctypes.c_void_p,ctypes.POINTER(MBI),ctypes.c_size_t];K.VirtualQueryEx.restype=ctypes.c_size_t
P.EnumProcessModulesEx.argtypes=[wintypes.HANDLE,ctypes.POINTER(ctypes.c_void_p),wintypes.DWORD,ctypes.POINTER(wintypes.DWORD),wintypes.DWORD];P.EnumProcessModulesEx.restype=wintypes.BOOL
P.GetModuleFileNameExW.argtypes=[wintypes.HANDLE,ctypes.c_void_p,wintypes.LPWSTR,wintypes.DWORD]
class Reader:
 def __init__(self,pid):
  self.pid=pid;self.h=K.OpenProcess(0x410,False,pid)
  if not self.h:
   error=ctypes.get_last_error()
   if error==5:raise ProcessReadDenied(pid,error,read_access=0x410)
   raise OSError(error,'OpenProcess read-only failed')
  modules=(ctypes.c_void_p*2048)();needed=wintypes.DWORD()
  if not P.EnumProcessModulesEx(self.h,modules,ctypes.sizeof(modules),ctypes.byref(needed),3):raise OSError(ctypes.get_last_error(),'EnumProcessModules failed')
  self.base=None;self.module_files={}
  for module in modules[:needed.value//ctypes.sizeof(ctypes.c_void_p)]:
   name=ctypes.create_unicode_buffer(32768);P.GetModuleFileNameExW(self.h,module,name,len(name))
   self.module_files[Path(name.value).name.lower()]=name.value
   if name.value.lower().endswith('gameassembly.dll'):self.base=module
  if self.base is None:raise ValueError('GameAssembly module not found')
 def read(self,a,size):
  if not a or size<0 or size>64*1024*1024:raise ValueError('Invalid read range')
  if size>=64*1024:
   # Reuse only destination storage, never process contents. string_at below
   # returns independent immutable bytes for suspended scan cursors and for
   # before/after state checks. Small metadata reads do not copy the bulk buffer.
   data=getattr(self,'_read_buffer',None)
   if data is None or ctypes.sizeof(data)<size:
    data=ctypes.create_string_buffer(size);self._read_buffer=data
  else:data=ctypes.create_string_buffer(size)
  got=ctypes.c_size_t()
  if not K.ReadProcessMemory(self.h,a,data,size,ctypes.byref(got)):raise OSError(ctypes.get_last_error(),f'ReadProcessMemory {a:x}')
  if got.value>size:raise OSError('Process read returned more than requested')
  return ctypes.string_at(data,got.value)
 def u64(self,a):return struct.unpack('<Q',self.read(a,8))[0]
 def cstring(self,a,maxlen=256):return self.read(a,maxlen).split(b'\0',1)[0].decode('utf-8','replace')
 def class_name(self,a):
  name=self.cstring(self.u64(a+16));ns=self.cstring(self.u64(a+24));return ns+'.'+name
 def fields(self,cls):
  p=self.u64(cls+0x80);result={}
  for i in range(256):
   b=self.read(p+i*32,32);namep,typ,parent,offset,token=struct.unpack('<QQQiI',b)
   if parent!=cls:break
   result[self.cstring(namep)]=offset
  return result
 def regions(self):
  info=SYSTEM_INFO();K.GetNativeSystemInfo(ctypes.byref(info))
  minimum=info.lpMinimumApplicationAddress;maximum=info.lpMaximumApplicationAddress
  if minimum is None or maximum is None or not 0<minimum<=maximum<2**(8*ctypes.sizeof(ctypes.c_void_p))-1:
   raise OSError('GetNativeSystemInfo returned invalid application address bounds')
  a=minimum;limit=maximum+1
  while a<limit:
   m=MBI()
   returned=K.VirtualQueryEx(self.h,a,ctypes.byref(m),ctypes.sizeof(m))
   if not returned:raise OSError(ctypes.get_last_error(),f'VirtualQueryEx {a:x} before application address limit {limit:x}')
   if returned!=ctypes.sizeof(m):raise OSError(f'VirtualQueryEx {a:x} returned incomplete memory information')
   base=m.BaseAddress or 0;nexta=base+m.RegionSize
   if m.RegionSize<=0 or not base<=a<nexta<=limit:
    raise OSError(f'VirtualQueryEx {a:x} returned invalid or nonprogressing region {base:x}+{m.RegionSize:x}')
   yield m
   a=nexta
 def close(self):
  if self.h:K.CloseHandle(self.h);self.h=None
  self._read_buffer=None
