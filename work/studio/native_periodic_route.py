"""Compile global pose approaches with the existing conditional input model."""
import time
import numpy as np
from native_input_compile import compile_native_route


def compile_periodic_approach(target,reference,geometry,settings,markers,*,wheel_delta_per_step,
        time_budget_seconds=1.,clock=time.monotonic,check=lambda:None):
    started=clock()
    result=compile_native_route(target,reference,geometry,settings,markers,
        wheel_delta_per_step=wheel_delta_per_step,sample_policy='all_recorded_points',
        now=started,deadline=started+time_budget_seconds+120.,max_steps=64,max_proposals=512,
        marker_tolerance=.1,planning_seconds=time_budget_seconds,clock=clock,check=check,
        max_wheel_steps=32,input_margin=20.)
    initial=float(np.max(result['steps'][0]['before_max_error'])) if result['steps'] else 0.
    final=float(np.max(result['marker_errors']))
    result.update(initial_marker_error=initial,final_marker_error=final,
                  model_progress=bool(result['input_route']) and final<initial-1e-5,
                  target_pose=target,execution_verified=False)
    return result
