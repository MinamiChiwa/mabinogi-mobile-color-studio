"""Finite native candidate presentation and protected fresh-reference compilation."""
import copy
import hashlib
import time
import numpy as np
from native_input_response import InputGeometry,InputSettings,replay_native_route
from native_input_route_search import _needed
from native_palette_scoring import score_native_pose
from native_periodic_route import compile_periodic_approach
from hex_refinement import score_codes
from .compromise import predicted_quality,quality_fields


class CandidateUnavailable(ValueError):pass
class _CollectionExpired(Exception):pass


def exact_observed_rules(colors):
    return [dict(enabled=True,exact=True,colors=[color],tolerance=0.) for color in colors]


def actual_colors(context,pose,check=lambda:None):
    count=len(context['session']['pixels'])
    return score_native_pose(context['session'],pose,exact_observed_rules(['#000000']*count),check=check)['colors']


def collect_candidate_pool(context,checkpoint,rules,rows,*,proposals=(),deadline,
        clock=time.monotonic,check=lambda:None,max_proposals=160,limit=12):
    """Deduplicate actual full-layout HEX; retain only independent route audits."""
    from .same_session_dye_planner import audit_candidate_endpoint
    geometry=InputGeometry(context['board'],context['local_size'],context['input_coordinate_convention'],
        pixel_mapping=context.get('pixel_mapping'));settings=InputSettings(**context['settings'])
    retained={}
    def guard():
        if clock()>=deadline:raise _CollectionExpired()
        check()
        if clock()>=deadline:raise _CollectionExpired()
    def order(row):return (*predicted_quality(row['prediction'],rules),row['needed'],len(row['input_route']))
    def retain(row):
        guard()
        audited=audit_candidate_endpoint(context,checkpoint,rules,row,check=guard)
        audited['actual_colors']=actual_colors(context,audited['final_pose'],guard)
        signature=tuple(audited['actual_colors']);previous=retained.get(signature)
        if previous is None or order(audited)<order(previous):retained[signature]=audited
        if len(retained)>limit:
            del retained[max(retained,key=lambda key:order(retained[key]))]
    # Already audited rows remain useful even if supplementation has no budget.
    try:
        for row in rows:
            if row is not None:retain(row)
        for index,(source,route) in enumerate(proposals):
            if index>=max_proposals or clock()>=deadline:break
            guard()
            replay=replay_native_route(checkpoint['pose'],route,geometry,settings,
                wheel_delta_per_step=context['wheel_delta_per_step'],sample_policy='all_recorded_points',check=guard)
            row=dict(input_route=route,final_pose=replay['final_pose'],
                prediction=score_native_pose(context['session'],replay['final_pose'],rules,check=guard),
                needed=_needed(route,3.,.5),source=source)
            retain(row)
    except _CollectionExpired:pass
    return sorted(retained.values(),key=order)


def candidate_observation(colors,rules):
    score=score_codes(colors,rules);fields=quality_fields(score,rules,verified=True)
    return dict(verified=True,screenshot_verified=True,actual_colors=list(colors),actual_deltas=score['deltas'],
        maximum=fields['maximum'],average=fields['average'],accepted=score['accepted'],
        target_exact=score['target_exact'],exact_matches=fields.get('exact_matches'),
        exact_total=fields.get('exact_total'))


def candidate_id(batch_id,colors):
    return batch_id+':'+hashlib.sha256(','.join(colors).encode()).hexdigest()[:12]


def present_candidates(batch_id,rows,rules,current_colors,observations,*,deadline):
    current_id=None;presented=[]
    for index,row in enumerate(rows):
        colors=row['actual_colors'];item_id=candidate_id(batch_id,colors)
        fields=quality_fields(row['prediction'],rules)
        current=colors==current_colors
        if current:current_id=item_id
        presented.append(dict(id=item_id,colors=colors,deltas=row['prediction']['deltas'],
            maximum=fields['maximum'],average=fields['average'],accepted=bool(row['prediction']['predicted_accepted']),
            target_exact=bool(row['prediction']['target_exact']),source=row.get('source'),
            exact_matches=fields.get('exact_matches'),exact_total=fields.get('exact_total'),
            current=current,predicted=not current,available=not current))
    if current_id:observations[current_id]=candidate_observation(current_colors,rules)
    return dict(batch_id=batch_id,region_count=len(rules),candidates=presented,current_colors=current_colors,
        current_candidate_id=current_id,default_id=presented[0]['id'] if presented else None,
        effective_deadline=deadline,observations=copy.deepcopy(observations))


def compile_candidate_selection(context,checkpoint,rules,target,*,deadline,
        clock=time.monotonic,check=lambda:None):
    """Compile anew and independently audit every outward prefix and its return."""
    from .same_session_dye_planner import _checked_checkpoint,audit_candidate_endpoint
    _checked_checkpoint(context,checkpoint)
    geometry=InputGeometry(context['board'],context['local_size'],context['input_coordinate_convention'],
        pixel_mapping=context.get('pixel_mapping'));settings=InputSettings(**context['settings'])
    markers=np.asarray(context['session']['picker_uv'],float);l,t,r,b=geometry.board
    markers=np.column_stack((l+markers[:,0]*(r-l),b-markers[:,1]*(b-t)))
    def guard():
        check()
        if clock()>=deadline:raise CandidateUnavailable('candidate_compile_timeout')
    def compile_to(reference,pose,target_rules,seconds):
        guard()
        compiled=compile_periodic_approach(pose,reference['pose'],geometry,settings,markers,
            wheel_delta_per_step=context['wheel_delta_per_step'],
            time_budget_seconds=max(.001,min(seconds,deadline-clock())),clock=clock,check=guard)
        route=compiled['input_route']
        return audit_candidate_endpoint(context,reference,target_rules,dict(input_route=route,
            final_pose=compiled['final_pose'],prediction=score_native_pose(context['session'],
                compiled['final_pose'],target_rules,check=guard),needed=_needed(route,3.,.5),
            source='fresh_candidate_selection'),check=guard)
    anchor_rules=exact_observed_rules(checkpoint['client_hex'])
    selected_rules=exact_observed_rules(target['actual_colors'])
    outward=compile_to(checkpoint,target['final_pose'],rules,1.5)
    if actual_colors(context,outward['final_pose'],guard)!=target['actual_colors']:
        raise CandidateUnavailable('candidate_endpoint_not_reproduced')
    returns=[]
    for index in range(1,len(outward['input_route'])+1):
        guard()
        pose=replay_native_route(checkpoint['pose'],outward['input_route'][:index],geometry,settings,
            wheel_delta_per_step=context['wheel_delta_per_step'],sample_policy='all_recorded_points',check=guard)['final_pose']
        prefix=dict(checkpoint,pose=pose,client_hex=actual_colors(context,pose,guard))
        recovery=compile_to(prefix,checkpoint['pose'],anchor_rules,.75)
        if not recovery['prediction']['predicted_accepted']:
            raise CandidateUnavailable('candidate_return_not_proven')
        recovery['prefix_index']=index;returns.append(recovery)
    guard()
    outward.update(actual_colors=actual_colors(context,outward['final_pose'],guard),
        selection_rules=selected_rules,prefix_recoveries=returns,
        protection_audit=dict(every_prefix_has_checked_return=True,prefix_count=len(returns),
            actual_return_verified=False))
    return outward
