"""Read exact physical integer pixels in the selected window's cursor units."""
import ctypes as C
from ctypes import wintypes as W
from contextlib import contextmanager
import hashlib,json,math,time


class _Win32MappingAPI:
    def __init__(self):
        self.u=C.WinDLL('user32',use_last_error=True)
        for name,args,result in (
            ('GetClientRect',[W.HWND,C.POINTER(W.RECT)],W.BOOL),
            ('ClientToScreen',[W.HWND,C.POINTER(W.POINT)],W.BOOL),
            ('ScreenToClient',[W.HWND,C.POINTER(W.POINT)],W.BOOL),
            ('GetWindowDpiAwarenessContext',[W.HWND],C.c_void_p),
            ('GetThreadDpiAwarenessContext',[],C.c_void_p),
            ('SetThreadDpiAwarenessContext',[C.c_void_p],C.c_void_p),
            ('AreDpiAwarenessContextsEqual',[C.c_void_p,C.c_void_p],W.BOOL),
            ('PhysicalToLogicalPointForPerMonitorDPI',[W.HWND,C.POINTER(W.POINT)],W.BOOL),
            ('LogicalToPhysicalPointForPerMonitorDPI',[W.HWND,C.POINTER(W.POINT)],W.BOOL),
            ('GetCursorPos',[C.POINTER(W.POINT)],W.BOOL),
            ('GetPhysicalCursorPos',[C.POINTER(W.POINT)],W.BOOL)):
            fn=getattr(self.u,name);fn.argtypes=args;fn.restype=result
    @contextmanager
    def target_context(self,hwnd):
        context=self.u.GetWindowDpiAwarenessContext(hwnd)
        if not context:raise OSError('Target window DPI context unavailable')
        previous=self.u.SetThreadDpiAwarenessContext(C.c_void_p(context))
        if not previous:raise OSError('Cannot enter target window DPI context')
        try:
            if not self.u.AreDpiAwarenessContextsEqual(self.u.GetThreadDpiAwarenessContext(),C.c_void_p(context)):
                raise OSError('Target window DPI context unconfirmed')
            yield
        finally:
            if not self.u.SetThreadDpiAwarenessContext(C.c_void_p(previous)):
                raise OSError('Cannot restore pixel mapping reader DPI context')
    def _point(self,name,hwnd,point):
        p=W.POINT(*point)
        if not getattr(self.u,name)(hwnd,C.byref(p)):raise OSError(name+' failed during pixel mapping')
        return [p.x,p.y]
    def client_size(self,hwnd):
        r=W.RECT()
        if not self.u.GetClientRect(hwnd,C.byref(r)):raise OSError('Cannot read target client extent')
        if r.left or r.top:raise ValueError('Unexpected target client origin')
        return [r.right,r.bottom]
    def physical_to_client(self,hwnd,point):
        logical=self._point('PhysicalToLogicalPointForPerMonitorDPI',hwnd,point)
        return self._point('ScreenToClient',hwnd,logical)
    def client_to_physical(self,hwnd,point):
        logical=self._point('ClientToScreen',hwnd,point)
        return self._point('LogicalToPhysicalPointForPerMonitorDPI',hwnd,logical)
    def _cursor(self,name):
        p=W.POINT()
        if not getattr(self.u,name)(C.byref(p)):raise OSError('Cannot read cursor coordinate route')
        return [p.x,p.y]
    def cursor_check(self,hwnd):
        before=self._cursor('GetPhysicalCursorPos');logical=self._cursor('GetCursorPos')
        client=self._point('ScreenToClient',hwnd,logical);after=self._cursor('GetPhysicalCursorPos')
        size=self.client_size(hwnd)
        physical_origin=self.client_to_physical(hwnd,[0,0]);physical_lower=self.client_to_physical(hwnd,size)
        if not all(physical_origin[i]<=before[i]<physical_lower[i] for i in range(2)):
            return dict(stationary=False,matches=False,reason='cursor_outside_selected_client',
                        physical_before=before,physical_after=after,reader_cursor_screen=logical,
                        reader_cursor_target_client=client)
        converted=self.physical_to_client(hwnd,before)
        stationary=before==after
        return dict(stationary=stationary,matches=stationary and client==converted,
                    physical_before=before,physical_after=after,reader_cursor_screen=logical,
                    reader_cursor_target_client=client,converted_target_client=converted,
                    target_client_delta=[client[i]-converted[i] for i in range(2)],
                    scope='Reader emulates target window awareness, not cached game mouse freshness')


def _coordinates(window,screen):
    hwnd=window.get('hwnd');pid=window.get('pid')
    size=window.get('client_size_physical');origin=window.get('client_origin_physical');native=screen.get('size')
    if type(hwnd) is not int or hwnd<=0 or type(pid) is not int or pid<=0:
        raise ValueError('Selected window identity required for pixel mapping')
    for value in (size,native):
        if not isinstance(value,(list,tuple)) or len(value)!=2 or any(type(v) is not int or not 1<=v<=65536 for v in value):
            raise ValueError('Positive bounded physical/native extent required')
    if not isinstance(origin,(list,tuple)) or len(origin)!=2 or any(type(v) is not int for v in origin):
        raise ValueError('Physical window origin required')
    if window.get('physical_coordinates') is not True or window.get('visible') is not True or window.get('minimized') is not False:
        raise ValueError('Visible physical window required')
    binding={k:window.get(k) for k in ('hwnd','pid','client_origin_physical','client_size_physical',
        'client_size_api','api_client_size','client_size_logical','target_client_size_in_windowdpi',
        'client_size_in_window_dpi_context','client_rect_in_window_dpi_context',
        'client_rect_api','raw_client_rect','client_bounds_physical','client_lower_physical',
        'window_dpi_awareness','dpi','monitor_bounds_physical')}
    binding['native_screen_size']=list(native)
    return hwnd,list(size),list(origin),list(native),binding


def _guard(deadline,check,clock):
    if type(deadline) not in (int,float) or not math.isfinite(deadline):raise ValueError('Finite mapping deadline required')
    def guard():
        check()
        if clock()>=deadline:raise TimeoutError('Window pixel mapping read expired')
    return guard


def _cursor_proof(api,hwnd,guard,diagnostics=None):
    for _ in range(3):
        guard()
        try:cursor=api.cursor_check(hwnd)
        except (InterruptedError,TimeoutError):raise
        except OSError as exc:
            guard()
            cursor=dict(stationary=False,matches=False,status='reader_cursor_unavailable',
                error=type(exc).__name__+': '+str(exc))
            if diagnostics is not None:diagnostics['cursor_route']=cursor
            return dict(stationary_route_verified=False,reader_cursor_route_status='reader_cursor_unavailable')
        guard()
        if cursor.get('stationary') is True:
            status='matched_in_reader_context' if cursor.get('matches') is True else 'mismatch_in_reader_context'
            row=dict(stationary_route_verified=cursor.get('matches') is True,reader_cursor_route_status=status)
            if diagnostics is not None:diagnostics['cursor_route']=dict(cursor,status=status)
            return row
    # A moving cursor is not a contradictory observation or game input.
    reason=cursor.get('reason','cursor_moved_during_read')
    if diagnostics is not None:diagnostics['cursor_route']=dict(cursor,status=reason)
    return dict(stationary_route_verified=False,reader_cursor_route_status=reason,reason=reason)


def _fingerprint(record):
    return hashlib.sha256(json.dumps({k:v for k,v in record.items() if k!='mapping_sha256'},
        sort_keys=True,allow_nan=False).encode()).hexdigest()


def read_pixel_mapping(window,screen,deadline,check=lambda:None,*,clock=time.monotonic,api=None,diagnostics=None):
    """Collect every physical axis pixel twice using Win32 target DPI units."""
    guard=_guard(deadline,check,clock);guard()
    hwnd,size,origin,native,binding=_coordinates(window,screen);api=api or _Win32MappingAPI()
    w,h=size
    with api.target_context(hwnd):
        guard();target=list(api.client_size(hwnd))
        if target!=native:raise ValueError('Native Screen extent differs from target-awareness client units')
        expected_edges=[[origin[0],origin[1]],[origin[0]+w,origin[1]],
                        [origin[0],origin[1]+h],[origin[0]+w,origin[1]+h]]
        edges=[]
        for p,expected in zip(([0,0],[target[0],0],[0,target[1]],target),expected_edges):
            guard();physical=api.client_to_physical(hwnd,p)
            if physical!=expected:raise ValueError('Target-to-physical client edges disagree with measured window')
            edges.append(dict(target_client=list(p),physical_screen=list(physical)))
        axes=[]
        for axis,length in enumerate(size):
            fixed_size=size[1-axis]
            other_offsets=(0,fixed_size//2,fixed_size-1)
            values=[]
            for i in range(length):
                if i%128==0:guard()
                converted=[]
                for offset in other_offsets:
                    p=list(origin);p[axis]+=i;p[1-axis]+=offset
                    row=api.physical_to_client(hwnd,p)
                    if len(row)!=2 or any(type(v) is not int for v in row):raise ValueError('Integer target client point required')
                    converted.append(row[axis])
                if len(set(converted))!=1:raise ValueError('Target DPI pixel mapping is not axis separable')
                values.append(converted[0])
            if any(a>b for a,b in zip(values,values[1:])) or any(v<0 or v>target[axis] for v in values):
                raise ValueError('Target DPI pixel lattice lies outside client bounds or is nonmonotonic')
            # Endpoint rounding may legitimately map the final physical pixel
            # to the exclusive logical edge; preserve it instead of clipping.
            for i,expected in enumerate(values):
                if i%128==0:guard()
                p=list(origin);p[axis]+=i;p[1-axis]+=fixed_size//2
                if api.physical_to_client(hwnd,p)[axis]!=expected:
                    raise ValueError('Target DPI pixel mapping changed between reads')
            axes.append(values)
        guard()
        if list(api.client_size(hwnd))!=target:raise ValueError('Target client changed during pixel mapping')
        for edge in edges:
            guard()
            if api.client_to_physical(hwnd,edge['target_client'])!=edge['physical_screen']:
                raise ValueError('Target physical client edges changed during pixel mapping')
        cursor=_cursor_proof(api,hwnd,guard,diagnostics)
    guard()
    record=dict(source='win32_target_awareness_pixel_lattice',hwnd=hwnd,pid=window['pid'],
        physical_client_size=size,native_screen_size=native,target_client_size=target,
        client_origin_physical=origin,window_dpi_awareness=window.get('window_dpi_awareness'),
        target_client_x_by_physical_x=axes[0],target_client_y_by_physical_y=axes[1],
        window_binding=binding,edge_samples=edges,coordinate_validation=dict(verified=True,
        scheme='physical_to_logical_for_hwnd_then_target_context_screen_to_client',
        axis_separability_verified=True,integer_axes_double_read=True,
        stationary_route_scope='initial_reader_process_observation_only',**cursor),
        ready_for_input=False,inputs_sent=0,
        scope='Exact Win32 target-awareness integer axis map; supported legacy route assumption, no game event instrumentation')
    record['mapping_sha256']=_fingerprint(record)
    return record


def validate_pixel_mapping(record,window,screen,deadline,check=lambda:None,*,clock=time.monotonic,api=None,diagnostics=None):
    """Refresh bound geometry and sampled conversions without rebuilding axes."""
    guard=_guard(deadline,check,clock);guard()
    hwnd,size,origin,native,binding=_coordinates(window,screen)
    if record.get('source')!='win32_target_awareness_pixel_lattice' or record.get('window_binding')!=binding:
        raise ValueError('Window pixel mapping binding changed')
    if record.get('mapping_sha256')!=_fingerprint(record):raise ValueError('Window pixel mapping contents changed')
    if (record.get('physical_client_size')!=size or record.get('native_screen_size')!=native
            or record.get('coordinate_validation',{}).get('verified') is not True):
        raise ValueError('Window pixel mapping proof differs')
    api=api or _Win32MappingAPI()
    with api.target_context(hwnd):
        guard()
        if list(api.client_size(hwnd))!=record.get('target_client_size'):raise ValueError('Target client extent changed')
        for edge in record['edge_samples']:
            guard()
            if api.client_to_physical(hwnd,edge['target_client'])!=edge['physical_screen']:
                raise ValueError('Target physical client edges changed')
        for axis,length in enumerate(size):
            table=record['target_client_x_by_physical_x' if axis==0 else 'target_client_y_by_physical_y']
            if len(table)!=length:raise ValueError('Pixel mapping axis length changed')
            for i in sorted(set((0,1 if length>1 else 0,length//4,length//2,3*length//4,length-1))):
                guard();p=list(origin);p[axis]+=i;p[1-axis]+=size[1-axis]//2
                if api.physical_to_client(hwnd,p)[axis]!=table[i]:raise ValueError('Target pixel conversion changed')
        _cursor_proof(api,hwnd,guard,diagnostics)
    guard();return True
