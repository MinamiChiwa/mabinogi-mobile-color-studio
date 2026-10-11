"""Explicit same-session retry signalling and calibrated minimum-scale input."""
import copy
import math

import numpy as np

from input_gestures import PointerGesture
from native_input_response import replay_native_route


class RetryRequested(Exception):
    """User retry, distinct from F9; IO may attach a released partial receipt."""


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
