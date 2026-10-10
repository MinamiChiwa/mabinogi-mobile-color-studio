"""Read current-build legacy mouse branch and viewport; no game calls/input."""
import math,struct,time
from .read_native_rect import SUPPORTED_UNITYPLAYER
from .read_unity_screen import unityplayer_module_base


def read_input_backend(backend,deadline,*,check=lambda:None,clock=time.monotonic):
    if not math.isfinite(deadline):raise ValueError('Finite input-read deadline required')
    r=backend.reader;prior=r.guard;reads={}
    def guard():
        check()
        if clock()>=deadline:raise TimeoutError('Input backend read expired')
    def read(address,size):
        guard();raw=r.read(address,size)
        if len(raw)!=size:raise ValueError('Short input backend read')
        if reads.setdefault((address,size),raw)!=raw:raise ValueError('Input backend changed')
        return raw
    def pointer(address):
        value=struct.unpack('<Q',read(address,8))[0]
        if value<0x100000000 or value%8:raise ValueError('Invalid input backend pointer')
        return value
    try:
        r.guard=guard;guard();identity=list(backend.process_identity())
        if backend.unityplayer_version!=SUPPORTED_UNITYPLAYER:raise ValueError('Unsupported mouse layout build')
        base=backend.base;unity=getattr(backend,'unityplayer_base',None)
        if unity is None:unity=unityplayer_module_base(r,check=guard)
        cls=pointer(base+0x1074fa20)
        if r.class_name(cls)!='MM.Client.Framework.InputSystem.MMInputSystem':raise ValueError('Input class differs')
        static=pointer(cls+0xb8);manager=pointer(static+r.fields(cls)['inputSystem'])
        manager_class=pointer(manager);name=r.class_name(manager_class)
        if name!='MM.Client.Framework.InputSystem.InputManager':raise ValueError('Input backend branch differs')
        assistant=struct.unpack('<Q',read(manager+r.fields(manager_class)['inputEventAssistant'],8))[0]
        if assistant!=0:raise ValueError('Input assistant overrides legacy mouse')
        function=struct.unpack('<Q',read(base+0x11100078,8))[0]
        if function!=unity+0x185310:raise ValueError('Legacy mouse getter unresolved or differs')
        screen=pointer(unity+0x1b23390);viewport=read(screen+0x120,24)
        origin=list(struct.unpack('<2i',viewport[:8]));scale=list(struct.unpack('<2f',viewport[16:]))
        if origin!=[0,0] or scale!=[1.,1.]:raise ValueError('Only one-to-one origin-zero viewport validated')
        for (address,size),raw in reads.items():
            guard()
            if r.read(address,size)!=raw:raise ValueError('Input branch or viewport changed during read')
        guard()
        if list(backend.process_identity())!=identity:raise ValueError('Input process identity changed')
        return dict(process_identity=identity,backend_object=hex(manager),backend_type=name,input_assistant='0x0',
            legacy_mouse_getter_rva='0x185310',viewport_origin=origin,viewport_scale=scale,
            observed_monotonic=clock(),inputs_sent=0,ready_for_input=False,cached_mouse_freshness_verified=False,
            scope='Repeated input branch/viewport read near checkpoint, not event instrumentation or frame atomicity')
    finally:r.guard=prior


def input_backend_binding(record):
    return {k:record[k] for k in ('process_identity','backend_object','backend_type','input_assistant',
        'legacy_mouse_getter_rva','viewport_origin','viewport_scale')}
