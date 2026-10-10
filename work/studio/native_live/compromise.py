"""Rank native route endpoints for explicit, observed compromise positioning."""
import copy,math,time
import numpy as np
from candidate_ranking import candidate_quality
from hex_refinement import score_codes
from native_palette_scoring import score_native_pose
from native_input_response import InputGeometry,InputSettings,replay_native_route
from native_input_route_search import _needed
from region_priority import priority_fields


def quality_fields(prediction,rules,*,landing_maximum=None,verified=False):
    values=[prediction['deltas'][i] for i,r in enumerate(rules) if r['enabled']]
    if not values or any(v is None or not math.isfinite(v) or v<0 for v in values):
        raise ValueError('Compromise requires finite enabled-region Delta-E')
    exact=[i for i,r in enumerate(rules) if r['enabled'] and r['exact']]
    hits=sum(prediction['colors'][i] in rules[i]['colors'] for i in exact)
    worst=max(values);mean=sum(values)/len(values)
    return dict(maximum=worst,average=mean,landing_maximum=worst if landing_maximum is None else landing_maximum,
        accepted=prediction.get('predicted_accepted',prediction.get('accepted',False)),verified=verified,
        exact_matches=hits,exact_total=len(exact),exact_maximum=max((prediction['deltas'][i] for i in exact),default=0.),
        exact_average=sum(prediction['deltas'][i] for i in exact)/len(exact) if exact else 0.,
        **priority_fields(prediction['colors'],prediction['deltas'],rules))


def _center_quality(fields):
    """Native center maximum/mean precede the uncalibrated sampled risk tie."""
    quality=candidate_quality(fields)
    count=len(fields.get('region_priority',()))
    not_accepted,*tail=quality
    ordered=tail[:count]
    risk,maximum,average,*ties=tail[count:]
    return (not_accepted,*ordered,maximum,average,risk,*ties)


def predicted_quality(prediction,rules,*,landing_maximum=None):
    """Keep acceptance, then balanced center Delta-E; neighborhood only ties."""
    return _center_quality(quality_fields(prediction,rules,landing_maximum=landing_maximum))


def observed_quality(codes,rules):
    return _center_quality(quality_fields(score_codes(codes,rules),rules,verified=True))


def choose_compromise(context,checkpoint,rules,candidates,*,deadline,clock=time.monotonic,check=lambda:None):
    """Only complete audits and9-point CPU neighborhoods earn a retained candidate."""
    from .same_session_dye_planner import audit_candidate_endpoint
    class Expired(Exception):pass
    def guard():
        check()
        if clock()>=deadline:raise Expired()
    best=None;l,t,r,b=context['board']
    try:
        for candidate in candidates:
            guard()
            row=audit_candidate_endpoint(context,checkpoint,rules,candidate,check=guard)
            if row['prediction']['predicted_accepted']:continue
            risk=max(v for v in row['prediction']['deltas'] if v is not None)
            for dx,dy in (() if not row['input_route'] else ((x,y) for y in (-1,0,1) for x in (-1,0,1) if x or y)):
                guard();pose=copy.deepcopy(row['final_pose'])
                pose['position']=np.asarray(np.asarray(pose['position'],dtype=np.float32)+
                    np.asarray([dx/(r-l),dy/(b-t)],dtype=np.float32),dtype=np.float32).tolist()
                prediction=score_native_pose(context['session'],pose,rules,check=guard)
                risk=max(risk,max(v for v in prediction['deltas'] if v is not None))
            row['compromise_metrics']=quality_fields(row['prediction'],rules,landing_maximum=risk)
            row['compromise_metrics'].update(neighborhood_radius_pixels=1 if row['input_route'] else 0,
                neighborhood_samples=9 if row['input_route'] else 1,
                scope='Finite CPU translation neighborhood, not measured live input confidence')
            row['compromise_quality']=predicted_quality(row['prediction'],rules,landing_maximum=risk)
            guard()
            key=(*row['compromise_quality'],row['needed'],len(row['input_route']))
            if best is None or key<best[0]:best=(key,row)
    except Expired:pass
    return best[1] if best else None


def rebase_compromise_plan(context,checkpoint,frames,rules,route,template,*,now,check=lambda:None,purpose='compromise'):
    """Rebuild the remaining route from actual feedback, never a predicted old pose."""
    from .same_session_dye_planner import _checked_checkpoint,_frames,_plan_fingerprint,audit_candidate_endpoint,_timer_deadline
    pose=_checked_checkpoint(context,checkpoint);_frames(checkpoint,frames);check()
    geometry=InputGeometry(context['board'],context['local_size'],context['input_coordinate_convention'],
                           pixel_mapping=context.get('pixel_mapping'))
    replay=replay_native_route(pose,route,geometry,InputSettings(**context['settings']),
        wheel_delta_per_step=context['wheel_delta_per_step'],sample_policy='all_recorded_points',check=check)
    row=dict(input_route=copy.deepcopy(route),final_pose=replay['final_pose'],
        prediction=score_native_pose(context['session'],replay['final_pose'],rules,check=check),
        needed=_needed(route,3.,.5),source='actual_feedback_'+purpose+'_suffix')
    row=audit_candidate_endpoint(context,checkpoint,rules,row,check=check)
    plan=copy.deepcopy(template)
    plan.update(reference_pose=pose,reference_frame_monotonic=frames[-1]['captured_monotonic'],
        planned_at=now,effective_deadline=_timer_deadline(frames,template['effective_deadline'],template['reserve_seconds']))
    plan.update(seed_mode='actual_feedback_'+purpose+'_suffix',periodic_search_reused=True)
    if row['prediction']['predicted_accepted']:
        plan.update(candidate=row,compromise_candidate=None,result_classification='predicted_exact'
            if row['prediction']['target_exact'] else 'predicted_within_tolerance')
    else:plan.update(candidate=None,compromise_candidate=row,result_classification='not_found_in_budget')
    plan['plan_fingerprint']=_plan_fingerprint(plan)
    return plan
