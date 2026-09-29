"""Finite input-response measurements in an already entered manual session.

This diagnostic does not open a game or a dye, build an atlas, or choose a
colour. The injected game retains all input guards and the game deadline.
Opposite inputs are observations, never assumed to restore the original pose.
"""
from dataclasses import dataclass
import time
import numpy as np
from atlas_pose import homogeneous, marker_errors, pose_fields
from input_gestures import rotation_gesture, wheel_gesture


@dataclass(frozen=True)
class ProbeAction:
    name: str
    anchor_name: str
    repeat: int
    gesture: object
    variant: str = 'legacy'


def response_probe_plan(board):
    l,t,r,b=board
    anchors={'center':(round((l+r)/2),round((t+b)/2)),
             'offset':(round(l+(r-l)*.22),round(t+(b-t)*.72))}
    result=[]
    # Repeat each condition within the same session, preserving the full
    # measured state. An independent later session is still needed to validate.
    for repeat in range(2):
        for name,anchor in anchors.items():
            for angle in (12.,-12.,.4,-.4,.1,-.1):
                result.append(ProbeAction(f'{name}_r{repeat}_a{angle:+g}',name,repeat,
                                         rotation_gesture(board,angle,anchor)))
        for steps in (-1,1):
            result.append(ProbeAction(f'center_r{repeat}_w{steps:+d}','center',repeat,
                                     wheel_gesture(board,steps,anchors['center'])))
    return tuple(result)


def rotation_comparison_plan(board):
    from rotation_comparison import grouped_rotation_gesture
    l,t,r,b=board
    anchors={'center':(round((l+r)/2),round((t+b)/2)),
             'offset':(round(l+(r-l)*.22),round(t+(b-t)*.72))}
    result=[]
    for repeat in range(2):
        variants=(('legacy',rotation_gesture),('grouped',grouped_rotation_gesture))
        if repeat:variants=variants[::-1]
        for name,anchor in anchors.items():
            for angle in (.4,-.4,5.,-5.):
                for variant,make in variants:
                    result.append(ProbeAction(f'{name}_r{repeat}_a{angle:+g}_{variant}',
                        name,repeat,make(board,angle,anchor),variant))
    return tuple(result)


def run_response_probe(game,scene,reference,snap,log,*,register=None,
                       clock=time.monotonic,protocol='baseline'):
    """Run a bounded plan; return the last frame and a structured outcome.

    snap(name, scene) preserves original frames. log(kind, **data) journals
    each attempted input before sending it, so interrupted/failed samples stay
    reviewable. Missing registration ends this diagnostic with partial data.
    """
    if register is None:
        from atlas_runtime import motion as register
    game.check()
    if protocol not in ('baseline','rotation_compare'):
        raise ValueError('Unknown response measurement protocol')
    plan=(rotation_comparison_plan if protocol=='rotation_compare' else response_probe_plan)(scene.board)
    local=np.asarray(scene.markers,float)-scene.board[:2]
    geometry=tuple(game.geometry())
    park=(int(geometry[2]*.5),int(geometry[3]*.15))
    l,t,r,b=scene.board
    if l<=park[0]<=r and t<=park[1]<=b:
        raise ValueError('No cursor parking position outside the board')
    log('response_probe_plan',protocol=protocol,actions=[dict(name=p.name,anchor_name=p.anchor_name,
        repeat=p.repeat,variant=p.variant,gesture=p.gesture.record()) for p in plan],
        board=list(scene.board),markers=[list(v) for v in scene.markers],
        geometry=list(geometry),dpi=getattr(game,'response_probe_dpi',None),
        reference='max_sampling',response_model_installed=False)
    current=reference;current_name='max_sampling';pose=np.eye(3);completed=0;skipped=0
    status='complete'
    previous_trace=getattr(game,'capture_input_trace',False)
    game.capture_input_trace=True
    try:
        for index,action in enumerate(plan,1):
            game.check()
            if tuple(game.geometry())!=geometry:
                raise InterruptedError('Session geometry changed during response measurement')
            gesture=action.gesture
            if not gesture.has_effect:
                skipped+=1
                log('response_probe_skipped',step=index,name=action.name,
                    reason='integer_path_has_no_angular_motion',gesture=gesture.record(),variant=action.variant)
                continue
            # A per-action finishing allowance protects the actual countdown;
            # no 60-second elapsed-time cap is added to the workflow.
            deadline=min(game.until,getattr(game,'stage_until',float('inf')))
            if deadline-clock()<gesture.duration+.3+2.:
                status='game_time_remaining';break
            before=current;before_name=current_name
            log('response_probe_command',step=index,name=action.name,
                anchor_name=action.anchor_name,repeat=action.repeat,variant=action.variant,
                reference=before_name,pose_before=pose[:2].tolist(),gesture=gesture.record())
            started=clock()
            game.perform_gesture(gesture)
            input_seconds=clock()-started
            input_trace=getattr(game,'last_input_trace',None)
            log('response_probe_input',step=index,variant=action.variant,
                input_elapsed_seconds=input_seconds,input_trace=input_trace)
            game.pause(.15);game.check();game.move_to(park)
            first_name=f'response_{index:02d}_first'
            first=snap(first_name,scene)
            game.pause(.15)
            current_name=f'response_{index:02d}_settled'
            current=snap(current_name,scene)
            measurements={};diagnostics={}
            for name,a,z in (('forward',before,current),('reverse',current,before),
                             ('settling',first,current)):
                game.check()
                details={}
                try:
                    measurements[name]=register(a,z,scene,details)
                except Exception as exc:
                    if exc.__class__.__name__ in ('Interrupted','InterruptedError'):
                        raise
                    measurements[name]=None
                    details['error']=str(exc)
                diagnostics[name]=details
            record=dict(step=index,name=action.name,anchor_name=action.anchor_name,
                repeat=action.repeat,variant=action.variant,reference=before_name,first=first_name,
                settled=current_name,gesture=gesture.record(),
                input_elapsed_seconds=input_seconds,measurements=measurements,
                input_trace=input_trace,
                diagnostics=diagnostics,pose_before=pose[:2].tolist(),
                registration_complete=all(v is not None for v in measurements.values()))
            if not record['registration_complete']:
                log('response_probe_measurement',**record)
                status='registration_incomplete';break
            forward=homogeneous(measurements['forward']['matrix'])
            reverse=homogeneous(measurements['reverse']['matrix'])
            settling=homogeneous(measurements['settling']['matrix'])
            pose=forward@pose;completed+=1
            record.update(pose_after=pose[:2].tolist(),response=pose_fields(forward,scene.board),
                closure_pixels=marker_errors(np.eye(3),reverse@forward,local).tolist(),
                settling_pixels=marker_errors(np.eye(3),settling,local).tolist())
            log('response_probe_measurement',**record)
            # Same one-pixel movement guard as final game-code verification.
            # This is only a stop-for-visible-motion guard, not a precision bound.
            if max(record['settling_pixels'])>1.:
                status='texture_still_moving';break
        outcome=dict(status=status,planned=len(plan),completed=completed,skipped=skipped,
                     last_frame=current_name,measured_pose=pose[:2].tolist(),
                     response_model_installed=False)
        if status=='registration_incomplete':outcome['measured_pose']=None
        log('response_probe_complete',**outcome)
        return current,outcome
    except Exception as exc:
        log('response_probe_interrupted',completed=completed,skipped=skipped,
            last_frame=current_name,error=str(exc),input_trace=getattr(game,'last_input_trace',None))
        if exc.__class__.__name__ in ('Interrupted','InterruptedError'):
            raise
        outcome=dict(status='measurement_failed',planned=len(plan),completed=completed,
                     skipped=skipped,last_frame=current_name,measured_pose=None,
                     response_model_installed=False,error=str(exc))
        log('response_probe_complete',**outcome)
        return current,outcome
    finally:
        game.capture_input_trace=previous_trace
        try:game.send(4)
        finally:game.send(16)
