"""Read the supported legacy mouse cache without claiming event freshness."""
import math,struct,time
from .read_native_rect import SUPPORTED_UNITYPLAYER


def read_native_mouse_cache(reader,module_base,unityplayer_sha256,deadline,*,check=lambda:None,clock=time.monotonic):
    result=dict(source='current_build_native_legacy_mouse_cache',stable_read=False,
        repeat_values_equal=False,freshness_verified=False,ready_for_input=False,inputs_sent=0,
        scope='Repeated native getter cache only; no frame freshness, game event instrumentation or mapping selection')
    if unityplayer_sha256!=SUPPORTED_UNITYPLAYER:return dict(result,status='unsupported_build')
    if type(module_base) is not int or module_base<=0 or module_base%4096:return dict(result,status='invalid_module_base')
    if type(deadline) not in (int,float) or not math.isfinite(deadline):return dict(result,status='invalid_deadline')
    prior=reader.guard
    def guard():
        check()
        if clock()>=deadline:raise TimeoutError('Native mouse diagnostic expired')
    def read(address,size):
        guard();raw=reader.read(address,size)
        if len(raw)!=size:raise ValueError('Short native mouse diagnostic read')
        return raw
    try:
        reader.guard=guard
        first=read(module_base+0x1ae5628,8);state=struct.unpack('<Q',first)[0]
        if state<0x100000000 or state%8:return dict(result,status='invalid_mouse_cache_pointer')
        initial=read(state+0xc8,8);second=read(module_base+0x1ae5628,8);final=read(state+0xc8,8)
        if first!=second or initial!=final:return dict(result,status='cache_changed_during_read')
        xy=list(struct.unpack('<2f',initial))
        if not all(math.isfinite(v) for v in xy):return dict(result,status='nonfinite_mouse_cache')
        return dict(result,status='cache_collected',stable_read=True,repeat_values_equal=True,
                    input_state_address=hex(state),cached_mouse_unity=xy)
    except InterruptedError:raise
    except (ValueError,OSError,TimeoutError) as exc:
        return dict(result,status='unavailable',error=type(exc).__name__+': '+str(exc))
    finally:reader.guard=prior
