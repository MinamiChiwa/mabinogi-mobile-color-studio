"""Explicit-layout read-only adapter for runtime observation records.

An upstream discoverer must supply the already validated motion-control object
address and runtime geometry. This module never scans memory or guesses links.
"""
from dataclasses import dataclass
import math
import struct
from native_runtime_observation import validate_observation


@dataclass(frozen=True)
class RuntimeLayout:
    motion_fields: dict
    settings_fields: dict
    animator_fields: dict
    position_animation_fields: dict
    rotation_animation_fields: dict


def _f32(reader,address):
    return struct.unpack('<f',reader.read(address,4))[0]


def _vec2(reader,address):
    return [_f32(reader,address),_f32(reader,address+4)]


def _ptr(reader,address):
    value=reader.u64(address)
    if not value: raise ValueError('Null runtime object pointer')
    return value


def _animator(reader,address,fields,animation_fields,vector):
    is_done=bool(reader.read(address+fields['is_done'],1)[0])
    stop_requested=bool(reader.read(address+fields['stop_requested'],1)[0])
    animation=_ptr(reader,address+fields['animation'])
    duration=_f32(reader,animation+animation_fields['duration'])
    if vector:
        last=_vec2(reader,animation+animation_fields['last']);target=_vec2(reader,animation+animation_fields['target'])
    else:
        last=_f32(reader,animation+animation_fields['last']);target=_f32(reader,animation+animation_fields['target'])
    elapsed=_f32(reader,address+fields['elapsed']) if 'elapsed' in fields else None
    return dict(is_done=is_done,stop_requested=stop_requested,elapsed=elapsed,elapsed_observed=elapsed is not None,
                duration=duration,last=last,target=target)


def read_runtime_observation(reader, context, layout, *, check=lambda: None):
    """Read one explicit motion object and validate it as a live observation.

    ``context`` must come from an external, build-checked discoverer and must
    include runtime RectTransform geometry, identity, pixel fingerprints and
    scroll calibration. A missing link or unresolved animation fails closed.
    """
    check()
    if not isinstance(layout,RuntimeLayout) or not isinstance(context,dict): raise ValueError('Explicit runtime context required')
    if context.get('active') is not True:raise ValueError('Explicit active observation required')
    address=context.get('motion_address')
    if type(address) is not int or address<=0: raise ValueError('Motion-control address required')
    mf, sf, af, pf, rf=(layout.motion_fields,layout.settings_fields,layout.animator_fields,layout.position_animation_fields,layout.rotation_animation_fields)
    required=(('motion',mf,('settings','position_animator','rotation_animator','current_position','current_scale','current_rotation')),
              ('settings',sf,('minimum_scale','maximum_scale','move_threshold','move_tolerance','scroll_zoom_ratio')),
              ('animator',af,('is_done','stop_requested','animation')),
              ('position_animation',pf,('duration','last','target')),
              ('rotation_animation',rf,('duration','last','target')))
    for name,fields,names in required:
        if any(key not in fields for key in names): raise ValueError(f'Incomplete {name} layout')
    check();settings_address=_ptr(reader,address+mf['settings'])
    check();position_animator=_ptr(reader,address+mf['position_animator'])
    check();rotation_animator=_ptr(reader,address+mf['rotation_animator'])
    settings={key:_f32(reader,settings_address+offset) for key,offset in sf.items()}
    check();position=_vec2(reader,address+mf['current_position'])
    scale=_f32(reader,address+mf['current_scale']);rotation=_f32(reader,address+mf['current_rotation'])
    check();position_state=_animator(reader,position_animator,af,pf,True)
    check();rotation_state=_animator(reader,rotation_animator,af,rf,False)
    if (not position_state['is_done'] or not rotation_state['is_done']
            or position_state['stop_requested'] or rotation_state['stop_requested']):
        raise ValueError('Runtime animator state is not settled')
    record=dict(context,active=True,pose=dict(position=position,scale=scale,rotation_degrees=rotation),
        animator=dict(position=position_state,rotation=rotation_state),settings=settings)
    check();validated=validate_observation(record);check();return validated
