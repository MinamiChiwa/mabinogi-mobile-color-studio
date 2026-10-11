"""Read current-build legacy mouse branch and viewport; no game calls/input."""
import math,struct,time
from .read_native_rect import SUPPORTED_UNITYPLAYER
from .read_unity_screen import unityplayer_module_base
from .build_adapters import TW_ADAPTER


def viewport_mapping_is_verified(origin, scale, mapping):
    """Accept scaled input only when the current target HWND lattice is bound."""
    if list(origin) == [0, 0] and [float(v) for v in scale] == [1., 1.]:
        return True
    return (isinstance(mapping, dict)
            and mapping.get('source') == 'win32_target_awareness_pixel_lattice'
            and mapping.get('coordinate_validation', {}).get('verified') is True
            and bool(mapping.get('mapping_sha256')))


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
        adapter=getattr(backend,'adapter',TW_ADAPTER);layout=adapter.unity_layout
        if backend.unityplayer_version!=layout.sha256:raise ValueError('Unsupported mouse layout build')
        base=backend.base;unity=getattr(backend,'unityplayer_base',None)
        if unity is None:unity=unityplayer_module_base(r,check=guard)
        cls=pointer(base+adapter.input_class_rva)
        if r.class_name(cls)!='MM.Client.Framework.InputSystem.MMInputSystem':raise ValueError('Input class differs')
        static=pointer(cls+0xb8);manager=pointer(static+r.fields(cls)['inputSystem'])
        manager_class=pointer(manager);name=r.class_name(manager_class)
        if name!='MM.Client.Framework.InputSystem.InputManager':raise ValueError('Input backend branch differs')
        assistant=struct.unpack('<Q',read(manager+r.fields(manager_class)['inputEventAssistant'],8))[0]
        if assistant!=0:raise ValueError('Input assistant overrides legacy mouse')
        function=struct.unpack('<Q',read(base+adapter.mouse_getter_cache_rva,8))[0]
        if function!=unity+layout.mouse_getter_rva:raise ValueError('Legacy mouse getter unresolved or differs')
        screen=pointer(unity+layout.screen_global_rva);viewport=read(screen+layout.viewport_offset,24)
        origin=list(struct.unpack('<2i',viewport[:8]));scale=list(struct.unpack('<2f',viewport[16:]))
        mapping=getattr(backend,'win_pixel_mapping',None)
        if not viewport_mapping_is_verified(origin,scale,mapping):
            raise ValueError('Viewport requires a verified target-awareness pixel mapping')
        for (address,size),raw in reads.items():
            guard()
            if r.read(address,size)!=raw:raise ValueError('Input branch or viewport changed during read')
        guard()
        if list(backend.process_identity())!=identity:raise ValueError('Input process identity changed')
        return dict(process_identity=identity,backend_object=hex(manager),backend_type=name,input_assistant='0x0',
            legacy_mouse_getter_rva=hex(layout.mouse_getter_rva),viewport_origin=origin,viewport_scale=scale,
            pixel_mapping_verified=viewport_mapping_is_verified(origin,scale,mapping),
            pixel_mapping_sha256=mapping.get('mapping_sha256') if isinstance(mapping,dict) else None,
            observed_monotonic=clock(),inputs_sent=0,ready_for_input=False,cached_mouse_freshness_verified=False,
            scope='Repeated input branch/viewport read near checkpoint, not event instrumentation or frame atomicity')
    finally:r.guard=prior


def input_backend_binding(record):
    return {k:record.get(k) for k in ('process_identity','backend_object','backend_type','input_assistant',
        'legacy_mouse_getter_rva','viewport_origin','viewport_scale','pixel_mapping_verified',
        'pixel_mapping_sha256')}
