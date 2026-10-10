"""Connect explicit runtime discovery output to observation validation.

The bridge is deliberately dumb: a guarded scanner supplies candidates and a
field layout; it never searches memory, invokes game methods, or sends input.
"""
import copy
import time
from native_runtime_discovery import select_palette_control
from native_runtime_adapter import read_runtime_observation
from native_runtime_observation import validate_stable_pair


def _read(reader,instance,candidates,context,layout,check):
    check()
    binding=select_palette_control(instance,candidates)
    check()
    bound_context=copy.deepcopy(context)
    bound_context['motion_address']=binding['motion_address']
    observation=read_runtime_observation(reader,bound_context,layout,check=check)
    check()
    return dict(binding=binding,**binding,observation=observation)


def read_bound_observation(reader,instance,candidates,context,layout,*,check=lambda:None):
    """Read one settled observation from one unique explicit control chain."""
    return _read(reader,instance,candidates,context,layout,check)


def read_bound_stable_pair(reader,instance,candidates,first_context,second_context,layout,*,check=lambda:None,
                           clock=time.monotonic,pause=lambda:time.sleep(.1)):
    """Read two observations and require identical control/session bindings."""
    first=_read(reader,instance,candidates,dict(first_context,monotonic_time=clock()),layout,check)
    check();pause();check()
    second=_read(reader,instance,candidates,dict(second_context,monotonic_time=clock()),layout,check)
    if first['binding']!=second['binding']:
        raise ValueError('Runtime control binding changed')
    stable=validate_stable_pair(first['observation'],second['observation'])
    return dict(stable=True,binding=first['binding'],control_address=first['binding']['control_address'],
                motion_address=first['binding']['motion_address'],gesture_address=first['binding']['gesture_address'],
                session_token=stable['session_token'],capture_id=stable['capture_id'],observation=stable,
                execution_verified=False,game_response_verified=False,release_inertia_modelled=False)
