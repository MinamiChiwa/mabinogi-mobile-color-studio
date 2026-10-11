"""Explicit same-session retry signalling and calibrated minimum-scale input."""
import copy
import math

import numpy as np

from input_gestures import PointerGesture
from native_input_response import replay_native_route


class RetryRequested(Exception):
    """User retry, distinct from F9; IO may attach a released partial receipt."""


MINIMUM_USEFUL_SEARCH_SECONDS=.25


def phase_allowances(costs,*,closing=False):
    """Budget measured IO phases, never another game-end idle reserve.

    Recent maxima plus a small scheduling allowance cover actual reads and
    preparation. Before a successful warm sample, retain the normal probe
    defaults rather than pretending a screenshot costs a fraction of a second.
    """
    def measured(name,default,jitter):
        rows=costs.get(name,[])[-3:]
        return max(rows)+jitter if rows else default
    native=measured('native',1.5,.15)
    visual=measured('closing_visual' if closing else 'visual',4.,.15)
    preparation=measured('input',.6,.1)
    return native,visual,preparation


def retry_budget(route,costs,*,include_reference,continuous=False):
    """Admit a real reset and useful search, then audit any target route itself.

    A continuous reset pays one preparation and the final complete visual read.
    Adapters without that input boundary retain per-group preparation/readback.
    A search result never inherits authorization to execute input.
    """
    native,visual,preparation=phase_allowances(costs,closing=True)
    actions=len(route);duration=sum(g['input_seconds'] for g in route)
    if continuous and route:
        duration=PointerGesture('wheel',tuple(map(tuple,route[0]['points'])),
            wheel_steps=sum(g['wheel_steps'] for g in route)).duration
        actions=1
    reset=duration+actions*preparation+(0. if continuous else actions*native)
    reference=native if include_reference else 0.
    minimum_search=MINIMUM_USEFUL_SEARCH_SECONDS;closing=0.
    return dict(native_allowance_seconds=native,visual_allowance_seconds=visual,
        input_preparation_allowance_seconds=preparation,reset_input_seconds=duration,
        reset_allowance_seconds=reset,reference_allowance_seconds=reference,
        minimum_search_seconds=minimum_search,closing_guard_seconds=closing,
        required_seconds=reference+reset+visual+minimum_search+closing,
        reset_mode='continuous_wheel' if continuous else 'observed_groups',
        reset_actions=actions,required_actions=actions+1)


def at_minimum_scale(pose,settings):
    minimum=float(np.float32(settings.minimum_scale))
    return math.isclose(float(pose['scale']),minimum,rel_tol=2e-7,abs_tol=0.)


def minimum_scale_route(pose,geometry,settings,*,max_groups=64):
    """Use the production float32 wheel kernel; group at most 32 down notches."""
    if at_minimum_scale(pose,settings):return []
    l,t,r,b=geometry.board
    anchor=(round((l+r)/2),round((t+b)/2))
    if not l+12<anchor[0]<r-12 or not t+12<anchor[1]<b-12:
        raise ValueError('Retry anchor outside safe board')
    current=copy.deepcopy(pose);route=[]
    for _ in range(max_groups):
        before=current['scale'];chosen=None
        for steps in range(1,33):
            gesture=PointerGesture('wheel',(anchor,),wheel_steps=-steps).record()
            after=replay_native_route(current,[gesture],geometry,settings,
                wheel_delta_per_step=1.,sample_policy='all_recorded_points')['final_pose']
            chosen=(gesture,after)
            if at_minimum_scale(after,settings):break
        gesture,current=chosen
        if current['scale']>=before:raise ValueError('Retry wheel does not reduce scale')
        route.append(gesture)
        if at_minimum_scale(current,settings):return route
    raise ValueError('Retry minimum scale exceeds bounded wheel allowance')
