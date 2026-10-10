"""Read-only physical client/desktop window metadata. No capture or input APIs."""
import ctypes as C
from ctypes import wintypes as W


class WindowGeometryError(ValueError):
 """A rejected read with the physical/API measurements collected so far."""
 def __init__(self,message,diagnostic):
  super().__init__(message)
  self.diagnostic=dict(diagnostic)


class _MonitorInfo(C.Structure):
 _fields_=[('cbSize',W.DWORD),('rcMonitor',W.RECT),('rcWork',W.RECT),('dwFlags',W.DWORD)]


class _Win32WindowAPI:
 def __init__(self):
  self.u=C.WinDLL('user32',use_last_error=True);self.dwm=C.WinDLL('dwmapi')
  signatures={
   'GetWindowThreadProcessId':([W.HWND,C.POINTER(W.DWORD)],W.DWORD),
   'GetClientRect':([W.HWND,C.POINTER(W.RECT)],W.BOOL),
   'GetWindowRect':([W.HWND,C.POINTER(W.RECT)],W.BOOL),
   'ClientToScreen':([W.HWND,C.POINTER(W.POINT)],W.BOOL),
   'ScreenToClient':([W.HWND,C.POINTER(W.POINT)],W.BOOL),
   'LogicalToPhysicalPointForPerMonitorDPI':([W.HWND,C.POINTER(W.POINT)],W.BOOL),
   'PhysicalToLogicalPointForPerMonitorDPI':([W.HWND,C.POINTER(W.POINT)],W.BOOL),
   'GetDpiForWindow':([W.HWND],W.UINT),
   'IsWindowVisible':([W.HWND],W.BOOL),'IsIconic':([W.HWND],W.BOOL),'IsWindow':([W.HWND],W.BOOL),
   'GetForegroundWindow':([],W.HWND),
   'SetThreadDpiAwarenessContext':([C.c_void_p],C.c_void_p),
   'GetThreadDpiAwarenessContext':([],C.c_void_p),
   'AreDpiAwarenessContextsEqual':([C.c_void_p,C.c_void_p],W.BOOL),
   'GetWindowDpiAwarenessContext':([W.HWND],C.c_void_p),
   'GetAwarenessFromDpiAwarenessContext':([C.c_void_p],C.c_int),
   'MonitorFromWindow':([W.HWND,W.DWORD],W.HANDLE),
   'GetMonitorInfoW':([W.HANDLE,C.POINTER(_MonitorInfo)],W.BOOL),
   'GetSystemMetrics':([C.c_int],C.c_int),
  }
  for name,(args,result) in signatures.items():
   fn=getattr(self.u,name);fn.argtypes=args;fn.restype=result
  self.callback=C.WINFUNCTYPE(W.BOOL,W.HWND,W.LPARAM)
  self.u.EnumWindows.argtypes=[self.callback,W.LPARAM];self.u.EnumWindows.restype=W.BOOL
  self.dwm.DwmGetWindowAttribute.argtypes=[W.HWND,W.DWORD,C.c_void_p,W.DWORD]
  self.dwm.DwmGetWindowAttribute.restype=C.c_long
 def pid(self,hwnd):
  value=W.DWORD()
  if not self.u.GetWindowThreadProcessId(hwnd,C.byref(value)):raise OSError('Window process unavailable')
  return value.value
 def windows(self,pid):
  rows=[];errors=[]
  @self.callback
  def visit(hwnd,_):
   try:
    if self.u.IsWindowVisible(hwnd) and self.pid(hwnd)==pid:rows.append(int(hwnd))
   except OSError as exc:errors.append(exc);return False
   return True
  if not self.u.EnumWindows(visit,0):raise OSError('Window enumeration failed')
  if errors:raise errors[0]
  return rows
 def snapshot(self,hwnd):
  diagnostic=dict(hwnd=int(hwnd),physical_coordinates=False,coordinate_validation={})
  rect=lambda r:[r.left,r.top,r.right,r.bottom]
  old=self.u.SetThreadDpiAwarenessContext(C.c_void_p(-4))
  if not old:raise WindowGeometryError('Cannot enter physical per-monitor DPI context',diagnostic)
  try:
   physical=bool(self.u.AreDpiAwarenessContextsEqual(self.u.GetThreadDpiAwarenessContext(),C.c_void_p(-4)))
   diagnostic['physical_coordinates']=physical
   if not physical or not self.u.IsWindow(hwnd):raise ValueError('Physical window context unavailable')
   window_context=self.u.GetWindowDpiAwarenessContext(hwnd)
   if not window_context:raise ValueError('Window DPI awareness context unavailable')
   awareness=int(self.u.GetAwarenessFromDpiAwarenessContext(window_context))
   diagnostic.update(dpi=int(self.u.GetDpiForWindow(hwnd)),window_dpi_awareness=awareness,
    client_api_coordinate_units='reader_per_monitor_v2_GetClientRect_units',physical_coordinate_units='physical_screen_pixels')
   client=W.RECT();window=W.RECT();origin=W.POINT(0,0)
   if self.u.GetWindowRect(hwnd,C.byref(window)):diagnostic['window_bounds_physical']=rect(window)
   else:raise OSError('Cannot read physical window bounds')
   if not self.u.GetClientRect(hwnd,C.byref(client)):raise OSError('Cannot read API client bounds')
   diagnostic.update(raw_client_rect=rect(client),api_client_size=[client.right-client.left,client.bottom-client.top])
   diagnostic['coordinate_validation']['raw_client_origin_zero']=client.left==0 and client.top==0
   if client.left!=0 or client.top!=0:raise ValueError('Unexpected client origin')
   # Raw GetClientRect and ClientToScreen can expose different API units for a
   # target with another awareness. Keep this route only as diagnostic evidence.
   lower=W.POINT(client.right,client.bottom)
   if self.u.ClientToScreen(hwnd,C.byref(origin)) and self.u.ClientToScreen(hwnd,C.byref(lower)):
    diagnostic.update(client_size_from_reader_api=[lower.x-origin.x,lower.y-origin.y],
     client_bounds_from_reader_api=[origin.x,origin.y,lower.x,lower.y])
   else:diagnostic['reader_client_endpoint_error']='Cannot convert reader API client rectangle'
   previous=self.u.SetThreadDpiAwarenessContext(C.c_void_p(window_context))
   if not previous:raise OSError('Cannot enter target window DPI context')
   try:
    if not self.u.AreDpiAwarenessContextsEqual(self.u.GetThreadDpiAwarenessContext(),C.c_void_p(window_context)):
     raise ValueError('Target window DPI context unavailable')
    target_client=W.RECT()
    if not self.u.GetClientRect(hwnd,C.byref(target_client)):raise OSError('Cannot read target-context client bounds')
    diagnostic.update(client_rect_in_window_dpi_context=rect(target_client),
     client_size_in_window_dpi_context=[target_client.right-target_client.left,target_client.bottom-target_client.top],
     window_context_client_coordinate_units='target_window_dpi_context_client_units')
    target_valid=target_client.left==0 and target_client.top==0 and all(1<=v<=65536 for v in diagnostic['client_size_in_window_dpi_context'])
    diagnostic['coordinate_validation']['target_context_client_extent']=target_valid
    if not target_valid:raise ValueError('Invalid target-context client bounds')
    if awareness==0:
     diagnostic['client_size_logical']=diagnostic['client_size_in_window_dpi_context']
    # Both client and screen coordinates belong to the target context here.
    # The HWND conversion supplies physical pixels independently of caller DPI.
    corners=[[0,0],[target_client.right,0],[0,target_client.bottom],[target_client.right,target_client.bottom]]
    logical_corners=[];physical_corners=[]
    diagnostic.update(target_client_corners=corners,target_logical_screen_corners=logical_corners,
     client_corners_physical=physical_corners,
     physical_client_source='target_context_GetClientRect_ClientToScreen_LogicalToPhysicalPointForPerMonitorDPI')
    for corner in corners:
     point=W.POINT(*corner)
     if not self.u.ClientToScreen(hwnd,C.byref(point)):raise OSError('Cannot read target-context client screen corner')
     logical_corners.append([point.x,point.y])
     if not self.u.LogicalToPhysicalPointForPerMonitorDPI(hwnd,C.byref(point)):
      raise OSError('Cannot convert target-context client corner to physical pixels')
     physical_corners.append([point.x,point.y])
     if len(physical_corners)==1:diagnostic['client_origin_physical']=[point.x,point.y]
    origin=W.POINT(*physical_corners[0]);lower=W.POINT(*physical_corners[3])
    size=[lower.x-origin.x,lower.y-origin.y]
    diagnostic.update(client_size_physical=size,client_bounds_physical=[origin.x,origin.y,lower.x,lower.y])
    valid_size=all(1<=v<=65536 for v in size+diagnostic['api_client_size'])
    diagnostic['coordinate_validation']['positive_bounded_extents']=valid_size
    if not valid_size:raise ValueError('Invalid physical/API client extent')
    axis_aligned=physical_corners==[[origin.x,origin.y],[lower.x,origin.y],[origin.x,lower.y],[lower.x,lower.y]]
    diagnostic['coordinate_validation']['physical_corners_axis_aligned']=axis_aligned
    if not axis_aligned:raise ValueError('Physical client corners inconsistent')
    contained=window.left<=origin.x<lower.x<=window.right and window.top<=origin.y<lower.y<=window.bottom
    diagnostic['coordinate_validation']['client_within_window']=contained
    if not contained:raise ValueError('Physical client endpoints outside window bounds')
    inverse=[];forward=[]
    diagnostic.update(client_endpoint_inverse_api=inverse,client_endpoint_roundtrip_physical=forward)
    for corner in physical_corners:
     back=W.POINT(*corner)
     if not self.u.PhysicalToLogicalPointForPerMonitorDPI(hwnd,C.byref(back)):
      raise OSError('Cannot convert physical client corner to target-context pixels')
     if not self.u.ScreenToClient(hwnd,C.byref(back)):raise OSError('Cannot validate target-context client corner')
     inverse.append([back.x,back.y])
     again=W.POINT(back.x,back.y)
     if not self.u.ClientToScreen(hwnd,C.byref(again)):
      raise OSError('Cannot validate target-context client corner roundtrip')
     if not self.u.LogicalToPhysicalPointForPerMonitorDPI(hwnd,C.byref(again)):
      raise OSError('Cannot validate physical client corner roundtrip')
     forward.append([again.x,again.y])
    roundtrip=inverse==corners and forward==physical_corners
    diagnostic['coordinate_validation']['screen_to_client_roundtrip']=roundtrip
    if not roundtrip:raise ValueError('Physical/target-client corner conversion inconsistent')
   finally:
    if not self.u.SetThreadDpiAwarenessContext(C.c_void_p(previous)):
     raise OSError('Cannot restore physical reader DPI context')
   monitor=self.u.MonitorFromWindow(hwnd,2);info=_MonitorInfo();info.cbSize=C.sizeof(info)
   if not monitor or not self.u.GetMonitorInfoW(monitor,C.byref(info)):raise OSError('Cannot read monitor bounds')
   extended=W.RECT();extended_bounds=None
   if self.dwm.DwmGetWindowAttribute(hwnd,9,C.byref(extended),C.sizeof(extended))==0:
    extended_bounds=rect(extended)
   diagnostic.update(pid=self.pid(hwnd),dwm_frame_bounds_physical=extended_bounds,
    visible=bool(self.u.IsWindowVisible(hwnd)),minimized=bool(self.u.IsIconic(hwnd)),
    foreground=self.u.GetForegroundWindow()==hwnd,physical_coordinates=physical,
    monitor_bounds_physical=rect(info.rcMonitor),monitor_work_bounds_physical=rect(info.rcWork),
    virtual_desktop_physical=[self.u.GetSystemMetrics(v) for v in (76,77,78,79)])
   return diagnostic
  except (OSError,ValueError) as exc:
   if isinstance(exc,WindowGeometryError):raise
   diagnostic['geometry_error']=str(exc)
   raise WindowGeometryError(str(exc),diagnostic) from exc
  finally:
   if not self.u.SetThreadDpiAwarenessContext(C.c_void_p(old)):
    diagnostic['geometry_error']='Cannot restore reader thread DPI context'
    raise WindowGeometryError(diagnostic['geometry_error'],diagnostic)


def read_window_state(pid,*,hwnd=None,api=None,check=lambda:None):
 if type(pid) is not int or pid<=0:raise ValueError('Explicit process id required')
 check();api=api or _Win32WindowAPI()
 if hwnd is None:
  handles=api.windows(pid)
  if len(handles)!=1:raise ValueError('Expected one visible window for selected process')
  hwnd=handles[0]
 if type(hwnd) is not int or hwnd<=0:raise ValueError('Invalid window handle')
 check();first=api.snapshot(hwnd);check();second=api.snapshot(hwnd);check()
 if first!=second or first.get('hwnd')!=hwnd or first.get('pid')!=pid:
  raise WindowGeometryError('Window identity/geometry changed',dict(second,window_measurements=[first,second],geometry_error='Window identity/geometry changed'))
 if first.get('physical_coordinates') is not True or first.get('minimized') is not False or first.get('visible') is not True:
  raise WindowGeometryError('Window physical geometry unavailable',dict(first,geometry_error='Window physical geometry unavailable'))
 size=first.get('client_size_physical');origin=first.get('client_origin_physical');dpi=first.get('dpi')
 if not isinstance(size,(list,tuple)) or len(size)!=2 or any(type(v) is not int or not 1<=v<=65536 for v in size):
  raise WindowGeometryError('Invalid physical client size',dict(first,geometry_error='Invalid physical client size'))
 if not isinstance(origin,(list,tuple)) or len(origin)!=2 or any(type(v) is not int for v in origin):
  raise WindowGeometryError('Invalid physical client origin',dict(first,geometry_error='Invalid physical client origin'))
 if type(dpi) is not int or not 1<=dpi<=960:raise WindowGeometryError('Invalid window DPI',dict(first,geometry_error='Invalid window DPI'))
 return dict(first,source='win32_client_physical',ready_for_input=False,
  scope='Repeated physical Win32 window/client measurement with temporary reader thread DPI context; no game/UI input or Unity mapping proof')
