"""Compile a same-session return to measured colours after a deliberate reset."""
import copy,math,time
import numpy as np
from input_gestures import PointerGesture
from native_input_compile import native_drag_gesture
from native_input_response import InputGeometry,InputSettings,replay_native_route
from native_input_route_search import _needed
from native_palette_scoring import score_native_pose
from .compromise import observed_quality,predicted_quality
from refinement_policy import RefinementPolicy


def prepare_retry_recovery(context,checkpoint,anchor,rules,*,deadline,clock=time.monotonic,
        check=lambda:None,preferred_routes=(),preserve_regions=False,admit=None):
    """Replay bounded scale corrections; original colours remain authoritative.

    A downward reset is not inverted by the same number of upward notches.
    Search the original float32 wheel kernel, including fractional scale pairs,
    and native integer translations. No live input or old-pose permission.
    """
    from .same_session_dye_planner import _checked_checkpoint,audit_candidate_endpoint
    class Expired(Exception):pass
    def guard():
        check()
        if clock()>=deadline:raise Expired()
    geometry=InputGeometry(context['board'],context['local_size'],context['input_coordinate_convention'],
        pixel_mapping=context.get('pixel_mapping'))
    settings=InputSettings(**context['settings']);l,t,r,b=geometry.board
    centre=(round((l+r)/2),round((t+b)/2))
    wanted=observed_quality(anchor['client_hex'],rules)
    policy=RefinementPolicy(rules,anchor['client_hex']) if preserve_regions else None
    seen=set()
    def evaluate(route):
        guard()
        if len(route)>64:return None
        signature=repr(route)
        if signature in seen:return None
        seen.add(signature)
        pose=replay_native_route(checkpoint['pose'],route,geometry,settings,
            wheel_delta_per_step=context['wheel_delta_per_step'],sample_policy='all_recorded_points',check=guard)['final_pose']
        prediction=score_native_pose(context['session'],pose,rules,check=guard)
        if (not policy.assess(prediction['colors'],deltas=prediction['deltas'])['not_worse']
                if policy is not None else predicted_quality(prediction,rules)>wanted):return None
        row=dict(input_route=copy.deepcopy(route),final_pose=pose,prediction=prediction,
            needed=_needed(route,3.,.5),source='measured_retry_return')
        row=audit_candidate_endpoint(context,checkpoint,rules,row,check=guard)
        return row if admit is None or admit(row) else None
    def wheel_route(up,down):
        route=[]
        for sign,count in ((1,up),(-1,down)):
            while count:
                n=min(32,count);count-=n
                route.append(PointerGesture('wheel',(centre,),wheel_steps=sign*n).record())
        return route
    try:
        _checked_checkpoint(context,checkpoint);_checked_checkpoint(context,anchor);guard()
        for route in ([],*preferred_routes):
            row=evaluate(route)
            if row is not None:return row
        if abs(checkpoint['pose']['rotation_degrees']-anchor['pose']['rotation_degrees'])>1e-5:
            from native_periodic_route import compile_periodic_approach
            markers=np.asarray(context['session']['picker_uv'],float)
            markers=np.column_stack((l+markers[:,0]*(r-l),b-markers[:,1]*(b-t)))
            compiled=compile_periodic_approach(anchor['pose'],checkpoint['pose'],geometry,settings,markers,
                wheel_delta_per_step=context['wheel_delta_per_step'],time_budget_seconds=max(.001,deadline-clock()),
                clock=clock,check=guard)
            row=evaluate(compiled['input_route'])
            if row is not None:return row
        ratio=settings.scroll_zoom_ratio
        if not 0<ratio<1:return None
        desired=math.log(anchor['pose']['scale']/checkpoint['pose']['scale'])
        positive=math.log(1+ratio);negative=math.log(1-ratio)
        combinations=[]
        for down in range(257):
            up=round((desired-down*negative)/positive)
            if not 0<=up or up+down>512:continue
            # The scale pair estimate assumes no clamp. A route crossing the
            # upper clamp has a different net scale and cannot be this seed.
            if checkpoint['pose']['scale']*math.exp(up*positive)>settings.maximum_scale*(1+1e-6):continue
            combinations.append((abs(up*positive+down*negative-desired),up+down,up,down))
        # Keep the most accurate scale starts and the shortest direct start.
        seeds=sorted(combinations)[:32]
        if combinations:seeds.append(min(combinations,key=lambda x:x[1]))
        for _,_,up,down in seeds:
            route=wheel_route(up,down)
            row=evaluate(route)
            if row is not None:return row
            pose=replay_native_route(checkpoint['pose'],route,geometry,settings,
                wheel_delta_per_step=context['wheel_delta_per_step'],sample_policy='all_recorded_points',check=guard)['final_pose']
            dx=round((anchor['pose']['position'][0]-pose['position'][0])*(r-l))
            dy=round((pose['position'][1]-anchor['pose']['position'][1])*(b-t))
            for ox,oy in ((0,0),(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)):
                guard();drag=native_drag_gesture(geometry,settings,dx+ox,dy+oy)
                if drag.has_effect:
                    row=evaluate([*route,drag.record()])
                    if row is not None:return row
    except Expired:pass
    return None
