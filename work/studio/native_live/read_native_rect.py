"""Build-checked native RectTransform cache diagnostic, never game calls.

Requires an explicitly resolved managed RectTransform. It does not discover a
TouchArea, refresh engine layout, or emit input-ready geometry.
"""
import math,struct

SUPPORTED_UNITYPLAYER='e969642866c2195f16a0bd0e52ff8ffe87cad5b213fda9a62ca1564970e2fa26'


def read_native_rect_cache(reader,managed_rect_address,*,unityplayer_sha256,check=lambda:None):
    if unityplayer_sha256!=SUPPORTED_UNITYPLAYER:raise ValueError('Unsupported native UnityPlayer layout')
    check();reads={}
    def read(a,size):
        check();raw=reader.read(a,size)
        if len(raw)!=size:raise ValueError('Short native rect read')
        if reads.setdefault((a,size),raw)!=raw:raise ValueError('Native rect changed during read')
        return raw
    if type(managed_rect_address) is not int or managed_rect_address<=0:raise ValueError('Managed rect address required')
    cls=struct.unpack('<Q',read(managed_rect_address,8))[0]
    if reader.class_name(cls)!='UnityEngine.RectTransform':raise ValueError('Expected managed RectTransform')
    native=struct.unpack('<Q',read(managed_rect_address+16,8))[0]
    if not native or native%8:raise ValueError('Null/unaligned native RectTransform')
    parent=struct.unpack('<Q',read(native+0x90,8))[0]
    fields=struct.unpack('<14f',read(native+0xb8,56))
    if not all(math.isfinite(v) for v in fields):raise ValueError('Nonfinite native rect fields')
    flag=read(native+0xf1,1)[0]
    if flag not in (0,1):raise ValueError('Invalid native rect refresh flag')
    rect=fields[:4];pivot=fields[12:14]
    consistent=all(abs(rect[i]-(-rect[i+2]*pivot[i]))<=1e-3 for i in range(2))
    for (a,size),raw in reads.items():
        check()
        if reader.read(a,size)!=raw:raise ValueError('Native rect changed during read')
    check()
    return dict(source='native_rect_cache_diagnostic',managed_rect_address=hex(managed_rect_address),
        native_rect_address=hex(native),parent_native_address=hex(parent),cached_local_rect=list(rect),
        anchor_min=list(fields[4:6]),anchor_max=list(fields[6:8]),anchored_position=list(fields[8:10]),
        size_delta=list(fields[10:12]),pivot=list(pivot),local_refresh_pending=bool(flag),
        cache_origin_consistent=consistent,cache_freshness_verified=False,screen_geometry_available=False,
        runtime_measurement_verified=False,ready_for_input=False,execution_verified=False,game_response_verified=False,
        scope='Raw double-checked native layout cache only; parent refresh/transform matrix/screen projection unresolved')
