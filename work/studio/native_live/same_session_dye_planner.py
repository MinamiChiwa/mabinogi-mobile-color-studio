"""Same-session research planning and archived feedback; never sends input.

Checkpoint flags come from the existing stable reader, not a live authenticity
proof. Current calibration was observed after the actions. Every result stays
ready_for_input=False until a separate live protocol supplies that evidence.
"""
import copy
from dataclasses import asdict
import hashlib, json, math, re, sys, time
import numpy as np
from native_input_pipeline import search_native_input_pipeline,bind_native_route_seeds
from native_input_response import InputGeometry, InputSettings, _pose, replay_native_route
from native_input_compile import native_drag_gesture
from native_input_route_search import _needed
from native_input_pivot_refine import refine_native_wheel_pivots
from native_palette_scoring import score_native_pose
from hex_refinement import score_codes
from input_gestures import PointerGesture
from .compromise import predicted_quality,choose_compromise
from native_periodic_search import search_periodic_targets
from native_periodic_route import compile_periodic_approach
from dye_regions import region_count, rule_region_count, session_region_count, validate_region_rules

POLICY='all_recorded_points'
PLAN_OBSERVATION_MAX_AGE_SECONDS=15.


def normalize_target_rules(rules):
    """Own canonical, strictly typed actual-layout targets; no silent coercion."""
    rule_region_count(rules)
    owned=[]
    from region_priority import priority_indices
    priority_indices(rules)
    for rule in rules:
        if not isinstance(rule,dict) or type(rule.get('enabled')) is not bool or type(rule.get('exact')) is not bool:
            raise ValueError('Target enabled/exact must be booleans')
        colors=rule.get('colors');tolerance=rule.get('tolerance')
        if (not isinstance(colors,(list,tuple)) or len(colors)>64
            or (rule['enabled'] and not colors)):
            raise ValueError('Enabled target requires one to 64 HEX alternatives')
        if type(tolerance) not in (int,float) or not math.isfinite(tolerance) or tolerance<0:
            raise ValueError('Target tolerance must be finite and nonnegative')
        normalized=[]
        for color in colors:
            if not isinstance(color,str) or not re.fullmatch(r'#?[0-9a-fA-F]{6}',color.strip()):
                raise ValueError('Target must be a six-digit HEX')
            normalized.append('#'+color.strip().lstrip('#').upper())
        row=dict(enabled=rule['enabled'],exact=rule['exact'],colors=sorted(set(normalized)),
            tolerance=0. if rule['exact'] else float(tolerance))
        if 'priority' in rule:row['priority']=rule['priority']
        owned.append(row)
    if not any(r['enabled'] for r in owned):raise ValueError('At least one target region must be enabled')
    return owned


def _json(value):
    return json.dumps(value, sort_keys=True, allow_nan=False)


def _fingerprint(context):
    session=context['session']
    session_region_count(session)
    data={k:context[k] for k in ('checkpoint_binding','board','local_size','settings',
        'wheel_delta_per_step','input_coordinate_convention','calibration_evidence')}
    if context.get('pixel_mapping') is not None:
        data['pixel_mapping'] = context['pixel_mapping']
    data.update(capture_id=session['capture_id'],picker_uv=session['picker_uv'],
        color_preserve_ratio=session['color_preserve_ratio'],initial_pose=session['initial_pose'],
        pixel_sha256=[hashlib.sha256(np.asarray(p,dtype=np.uint8).tobytes()).hexdigest()
                      for p in session['pixels']])
    return hashlib.sha256(_json(data).encode()).hexdigest()


def _checked_checkpoint(context, checkpoint):
    if _fingerprint(context)!=context['fingerprint']:
        raise ValueError('Planning context changed')
    if checkpoint.get('checkpoint_valid') is not True or checkpoint.get('cpu_matches') is not True:
        raise ValueError('Stable CPU-verified checkpoint required')
    if checkpoint.get('binding')!=context['checkpoint_binding']:
        raise ValueError('Session/process/settings/window binding changed')
    if list(checkpoint.get('board',()))!=context['board'] or list(checkpoint.get('local_size',()))!=context['local_size']:
        raise ValueError('Checkpoint geometry changed')
    if _json(checkpoint.get('pixel_mapping')) != _json(context.get('pixel_mapping')):
        raise ValueError('Checkpoint physical pixel mapping changed')
    codes=checkpoint.get('client_hex')
    count=session_region_count(context['session'])
    if checkpoint.get('region_count',count)!=count or checkpoint.get('actual_count',count)!=count:
        raise ValueError('Checkpoint dye region count changed')
    if not isinstance(codes,(list,tuple)) or len(codes)!=count or any(not isinstance(c,str) or not re.fullmatch(r'#[0-9A-F]{6}',c) for c in codes):
        raise ValueError('Observed HEX values must match the actual dye layout')
    pose=_pose(checkpoint['pose'])
    rules=[dict(enabled=True,exact=True,colors=[c],tolerance=0) for c in codes]
    if score_native_pose(context['session'],pose,rules)['colors']!=list(codes):
        raise ValueError('Captured palette/picker does not reproduce checkpoint HEX')
    return pose


def bind_planning_context(session, checkpoint, geometry, settings, *, wheel_delta_per_step, calibration_evidence):
    """Bind an explicit research calibration to a saved session and checkpoint."""
    if not isinstance(geometry,InputGeometry) or not isinstance(settings,InputSettings):
        raise ValueError('Explicit native geometry and effective settings required')
    if geometry.input_coordinate_convention!='windows_legacy_mouse_pixels':
        raise ValueError('This research entry requires the verified legacy convention')
    evidence=copy.deepcopy(calibration_evidence)
    viewport = geometry.pixel_mapping or dict(viewport_origin=[0,0], viewport_scale=[1,1])
    if (not isinstance(evidence,dict) or not isinstance(evidence.get('source'),str) or not evidence['source']
        or evidence.get('viewport_origin')!=viewport['viewport_origin']
        or evidence.get('viewport_scale')!=viewport['viewport_scale']
        or type(evidence.get('backend_during_actions_synchronously_recorded')) is not bool):
        raise ValueError('Explicit matching native viewport calibration evidence required')
    if type(wheel_delta_per_step) not in (int,float) or not math.isfinite(wheel_delta_per_step) or wheel_delta_per_step!=1.:
        raise ValueError('Only the observed net wheel mapping +1 per project step is supported')
    # ProjectProbeIO preserves the complete _binding tuple from the reader.
    binding=json.loads(checkpoint['binding'])
    if not isinstance(binding,list) or len(binding)!=5 or binding[3]!=asdict(settings):
        raise ValueError('Effective settings differ from checkpoint binding')
    owned=copy.deepcopy(session)
    for pixels in owned['pixels']:pixels.setflags(write=False)
    context=dict(schema=1,session=owned,checkpoint_binding=checkpoint['binding'],
        board=list(geometry.board),local_size=list(geometry.local_size),settings=asdict(settings),
        input_coordinate_convention=geometry.input_coordinate_convention,
        wheel_delta_per_step=float(wheel_delta_per_step),calibration_evidence=evidence,
        ready_for_input=False,scope='research_checkpoint_binding_not_live_authentication')
    if geometry.pixel_mapping is not None:
        context['pixel_mapping'] = geometry.pixel_mapping_record()
    context['fingerprint']=_fingerprint(context)
    _checked_checkpoint(context,checkpoint)
    return context


EARLY_TIMER_GRACE_SECONDS=30.
EXECUTION_RESERVE_SECONDS=10.

def _frames(checkpoint, frames):
    if not isinstance(frames,(list,tuple)) or len(frames)!=2:
        raise ValueError('Two independent screenshot reads required')
    count=region_count(len(checkpoint['client_hex']))
    previous=None
    for frame in frames:
        if frame.get('hex')!=checkpoint['client_hex']:
            raise ValueError('Screenshot and checkpoint HEX disagree')
        for key in ('screenshot_hex','hex_source','cards','markers'):
            if key in frame and len(frame[key])!=count:
                raise ValueError('Screenshot region count differs from checkpoint')
        if frame.get('region_count',count)!=count:
            raise ValueError('Screenshot dye region count changed')
        seconds=None if frame.get('timer_advisory') is True else frame.get('remaining_seconds')
        when=frame.get('captured_monotonic')
        if (seconds is not None and (type(seconds) is not int or not 1<=seconds<=120)) or type(when) not in (int,float) or not math.isfinite(when) or when<=0:
            raise ValueError('Observed timer and capture timestamp required')
        if previous is not None:
            old,old_when=previous;elapsed=when-old_when
            if elapsed<=0:raise ValueError('Screenshot capture timestamps are discontinuous')
            if seconds is None or old is None:
                previous=(seconds,when);continue
            if seconds>old+1 or old-seconds>math.ceil(elapsed)+3:
                # OCR can briefly read a timer glyph from the wrong animation
                # frame. Keep the color evidence and discard only this timer
                # sample; the engineering deadline remains authoritative.
                frame['remaining_seconds']=None
                frame['timer_confidence']='discontinuity_advisory'
                seconds=None
        previous=(seconds,when)
    return previous


def _timer_deadline(frames,deadline,reserve):
    limits=[deadline]
    for frame in frames:
        seconds=frame.get('remaining_seconds')
        if frame.get('timer_advisory') is not True and type(seconds) is int and 1<=seconds<=120:
            limits.append(frame['captured_monotonic']+seconds-reserve)
    return min(limits)


def _fresh(now, frames):
    when=frames[-1]['captured_monotonic']
    if type(now) not in (int,float) or not math.isfinite(now) or not 0<=now-when<=5.:
        raise ValueError('Fresh checkpoint frames required for planning/revalidation')


def assess_feedback(context, checkpoint, frames, rules, *, expected_pose=None):
    """Assess recorded observations; acceptance never means server confirmation."""
    _frames(checkpoint,frames)
    result=assess_native_feedback(context,checkpoint,rules,expected_pose=expected_pose)
    result['screenshot_verified']=all(
        frame.get('screenshot_hex',frame['hex'])[i]==checkpoint['client_hex'][i] and
        frame.get('hex_source',['screenshot']*len(rules))[i]=='screenshot'
        for frame in frames for i,rule in enumerate(rules) if rule['enabled'])
    if result['observed_target_accepted'] and not result['screenshot_verified']:
        result.update(observed_target_accepted=False,stop_reason='target_visual_unconfirmed')
    return result


def assess_native_feedback(context, checkpoint, rules, *, expected_pose=None):
    """Intermediate bound native readback, never a screenshot success claim."""
    rules=normalize_target_rules(rules)
    pose=_checked_checkpoint(context,checkpoint)
    validate_region_rules(context['session'],rules)
    score=score_codes(checkpoint['client_hex'],rules)
    status='target_observed' if score['accepted'] else 'replan_required'
    errors=None
    if expected_pose is not None:
        expected=_pose(expected_pose)
        errors=dict(position=float(np.max(np.abs(np.asarray(pose['position'])-expected['position']))),
            scale=abs(pose['scale']-expected['scale']),rotation=abs(pose['rotation_degrees']-expected['rotation_degrees']))
        if errors['position']>2e-7 or errors['scale']>1e-7 or errors['rotation']>1e-5:
            status='model_response_mismatch'
    return dict(stop_reason=status,observed_target_accepted=score['accepted'],observed_score=score,
        observed_pose=pose,replan_pose=pose if status=='replan_required' else None,pose_error=errors,
        archived_color_feedback_verified=True,screenshot_verified=False,live_closed_loop_verified=False,
        server_confirmation_verified=False,ready_for_input=False)


def _supported_route(route, board):
    l,t,r,b=board
    return (len(route)<=8 and all(g['kind'] in ('drag','wheel') and len(g['points'])<=128
        and g.get('coordinate_space')=='physical_client_pixels'
        and all(type(v) is int for p in g['points'] for v in p)
        and all(l+12<p[0]<r-12 and t+12<p[1]<b-12 for p in g['points'])
        and (g['kind']!='wheel' or abs(g['wheel_steps'])==1) for g in route))


def _plan_fingerprint(plan):
    fields=('context_fingerprint','reference_pose','reference_frame_monotonic',
            'planned_at','effective_deadline','candidate','reserve_seconds','verification_margin_seconds')
    if plan.get('schema',1)>=2:
        fields+=('schema','normalized_rules','rules_fingerprint','result_classification',
                 'nearest_diagnostic','reachability_conclusion')
    if plan.get('schema',1)>=3:fields+=('compromise_candidate',)
    if plan.get('schema',1)>=4:fields+=('approach_candidate',)
    return hashlib.sha256(_json({key:plan[key] for key in fields}).encode()).hexdigest()


def audit_candidate_endpoint(context, checkpoint, rules, candidate, *, check=lambda:None):
    """Replay every point from the actual reference, then rescore and check sender policy.

    This validates offline descriptors/model arithmetic, never actual input or
    server success. The sender's remaining attempt count is a separate live guard.
    """
    from .project_closed_loop_io import validate_research_gesture
    check();rules=normalize_target_rules(rules);pose=_checked_checkpoint(context,checkpoint)
    row=copy.deepcopy(candidate);route=row.get('input_route')
    if not isinstance(route,(list,tuple)) or len(route)>64:
        raise ValueError('Candidate exceeds bounded route accounting')
    for gesture in route:check();validate_research_gesture(gesture,context['board'])
    geometry=InputGeometry(context['board'],context['local_size'],context['input_coordinate_convention'],
                           pixel_mapping=context.get('pixel_mapping'))
    replay=replay_native_route(pose,route,geometry,InputSettings(**context['settings']),
        wheel_delta_per_step=context['wheel_delta_per_step'],sample_policy=POLICY,check=check)
    prediction=score_native_pose(context['session'],replay['final_pose'],rules,check=check)
    if row.get('final_pose')!=replay['final_pose']:
        raise ValueError('Candidate endpoint differs from complete route replay')
    for field in ('colors','deltas','rank','target_exact','predicted_accepted'):
        if _json(row.get('prediction',{}).get(field))!=_json(prediction[field]):
            raise ValueError('Candidate score differs from independent endpoint score')
    needed=_needed(route,3.,.5)
    if row.get('needed')!=needed:raise ValueError('Candidate timing differs from route timing')
    row.update(prediction=prediction,needed=needed,execution_verified=False,game_response_verified=False,
        endpoint_audit=dict(full_route_replayed=True,cpu_rescored=True,research_descriptors_supported=True,
            actual_input_verified=False,remaining_live_attempts_verified=False))
    return row


def _local_input_candidates(geometry,settings):
    """Fixed finite geometry-only proposals; no target pose or saved route."""
    offsets=[(0,0),*((v,0) for d in range(1,6) for v in (-d,d)),
             *((0,v) for d in range(1,6) for v in (-d,d)),
             *((dx,dy) for dx in range(-5,6) for dy in range(-5,6) if dx and dy)]
    for dx,dy in offsets:
        gesture=native_drag_gesture(geometry,settings,dx,dy)
        yield 'fresh_local_integer_drag',[gesture.record()] if gesture.has_effect else []
    l,t,r,b=geometry.board
    for horizontal in (.2,.35,.5,.65,.8):
        for vertical in (.2,.5,.8):
            anchor=(round(l+(r-l)*horizontal),round(t+(b-t)*vertical))
            for sign in (-1,1):
                yield 'fresh_local_single_wheel',[PointerGesture('wheel',(anchor,),wheel_steps=sign).record()]
    # Keep established one-gesture candidates first. Cover the remaining
    # +/-10px integer square with two separately supported micro drags.
    for radius in range(6,11):
        for dx,dy in ((x,y) for y in range(-radius,radius+1) for x in range(-radius,radius+1)
                      if max(abs(x),abs(y))==radius):
            first=(max(-5,min(5,dx)),max(-5,min(5,dy)))
            route=[]
            for ox,oy in (first,(dx-first[0],dy-first[1])):
                gesture=native_drag_gesture(geometry,settings,ox,oy)
                if gesture.has_effect:route.append(gesture.record())
            yield 'fresh_two_micro_drags',route
    # Explicit finite wheel lattice, independent of target colors or witnesses.
    base={(x,y) for x in (.2,.35,.5,.65,.8) for y in (.2,.5,.8)}
    ratios=base|{(x/10,y/10) for x in range(1,10) for y in range(1,10)}
    def wheel(point,sign):return PointerGesture('wheel',(point,),wheel_steps=sign).record()
    anchors=[(ratio,(round(l+(r-l)*ratio[0]),round(t+(b-t)*ratio[1]))) for ratio in sorted(ratios)]
    for ratio,point in anchors:
        if ratio not in base:
            for sign in (-1,1):yield 'fresh_expanded_single_wheel',[wheel(point,sign)]
    for _,point in anchors:
        for sign in (-1,1):
            yield 'fresh_two_wheels',[wheel(point,sign),wheel(point,sign)]
            yield 'fresh_two_wheels',[wheel(point,sign),wheel(point,-sign)]
    # Different-pivot opposite pairs: explicit mirrored horizontal pairs only.
    for y in (.2,.5,.8):
        for x1,x2 in ((.2,.8),(.8,.2),(.35,.65),(.65,.35)):
            a=(round(l+(r-l)*x1),round(t+(b-t)*y))
            z=(round(l+(r-l)*x2),round(t+(b-t)*y))
            for sign in (-1,1):yield 'fresh_two_wheels',[wheel(a,sign),wheel(z,-sign)]
    # Small mixed macros, including both orders (which are not interchangeable).
    for ratio,point in anchors:
        if ratio not in base:continue
        for dx,dy in ((3,0),(-3,0),(0,3),(0,-3),(3,3),(3,-3),(-3,3),(-3,-3)):
            drag=native_drag_gesture(geometry,settings,dx,dy).record()
            for sign in (-1,1):
                record=wheel(point,sign)
                yield 'fresh_micro_drag_wheel',[drag,record]
                yield 'fresh_micro_drag_wheel',[record,drag]


def _research_route_allowed(route,board):
    """Use actual descriptor policy before retention; endpoint audit stays separate."""
    from .project_closed_loop_io import validate_research_gesture
    if not isinstance(route,(list,tuple)) or len(route)>64:return False
    try:
        for gesture in route:validate_research_gesture(gesture,board)
    except ValueError:return False
    return True


def _refine_single_wheels(session,pose,geometry,settings,rules,seeds,*,now,deadline,
        time_budget_seconds,wheel_delta_per_step,clock,check):
    """Bounded independent starts; never combine/drop basins using one global beam.

    Seeds were generated and scored from the current geometry/reference inside
    this planning call. No witnessed target route/pose is supplied here.
    """
    start=clock();end=start+min(time_budget_seconds,max(0.,deadline-now))
    def rank(row):return (*row['prediction']['rank'],row['needed'],len(row['input_route']))
    selected=[]
    for sign in (-1,1):
        selected.extend(sorted((row for row in seeds if row['input_route'][0]['wheel_steps']==sign),key=rank)[:16])
    selected.sort(key=rank);rows=[];attempts=[];reason='seeds_exhausted'
    for index,seed in enumerate(selected):
        check();elapsed=max(0.,clock()-start);remaining=end-clock()
        if remaining<=0:reason='deadline';break
        refined=refine_native_wheel_pivots(session,[seed['input_route']],pose,geometry,settings,rules,
            sample_policy=POLICY,wheel_delta_per_step=wheel_delta_per_step,
            now=now+elapsed,deadline=deadline,pixel_steps=(16,8,4,2,1),beam_width=3,top_k=3,
            max_candidates=300,pivot_grid_radius=8,time_budget_seconds=min(.18,remaining),clock=clock,check=check)
        attempts.append(dict(seed_index=index,seed_route=seed['input_route'],
            evaluated=refined['evaluated'],stop_reason=refined['stop_reason'],elapsed_seconds=refined['elapsed_seconds']))
        for row in refined['candidates']:
            row=dict(row,source='fresh_single_wheel_refinement')
            if _research_route_allowed(row['input_route'],geometry.board):rows.append(row)
        if rows and min(rows,key=rank)['prediction']['predicted_accepted']:
            reason='predicted_candidate';break
    check();rows.sort(key=rank)
    return dict(candidates=rows[:5],attempts=attempts,selected_seed_count=len(selected),
        stop_reason=reason,evaluated=sum(a['evaluated'] for a in attempts),
        elapsed_seconds=max(0.,clock()-start),scope='Finite per-sign16 independent single-wheel starts')


def plan_from_checkpoint(context, checkpoint, frames, rules, grid, *, now, engineering_deadline,
        time_budget_seconds=12., reserve_seconds=EXECUTION_RESERVE_SECONDS, verification_margin_seconds=8., clock=time.monotonic,
        check=lambda:None):
    """Rebase the existing fresh search on the observed pose, with bounded time.

    No recorded routes or after-action pose enter the search. Caller grid is
    heuristic coverage, not a target pose. The selected route is diagnostic.
    """
    started=clock();check();rules=normalize_target_rules(rules)
    feedback=assess_feedback(context,checkpoint,frames,rules);_fresh(now,frames)
    if (not all(math.isfinite(v) for v in (engineering_deadline,time_budget_seconds,reserve_seconds,verification_margin_seconds))
        or time_budget_seconds<=0 or not 10<=reserve_seconds<=40 or not 3<=verification_margin_seconds<=20):
        raise ValueError('Invalid deadline/reserve/search bounds')
    end=_timer_deadline(frames,engineering_deadline,reserve_seconds)
    pose=feedback['observed_pose']
    result=dict(schema=4,context_fingerprint=context['fingerprint'],reference_pose=pose,compromise_candidate=None,
        approach_candidate=None,periodic_search=None,
        normalized_rules=rules,rules_fingerprint=hashlib.sha256(_json(rules).encode()).hexdigest(),
        result_classification='insufficient_time',nearest_diagnostic=None,reachability_conclusion='not_established',
        reference_frame_monotonic=frames[-1]['captured_monotonic'],planned_at=now,effective_deadline=end,
        reserve_seconds=reserve_seconds,verification_margin_seconds=verification_margin_seconds,
        candidate=None,feedback=feedback,ready_for_input=False,game_response_verified=False,
        live_closed_loop_verified=False,server_confirmation_verified=False,
        seed_mode='fresh_from_current_checkpoint',stop_reason='insufficient_time')
    prepared=max(0.,clock()-started);search_now=now+prepared
    result['planned_at']=search_now
    if search_now+verification_margin_seconds>=end or prepared>=time_budget_seconds:
        if search_now+verification_margin_seconds<end:
            result.update(stop_reason='search_budget_exhausted',result_classification='not_found_in_budget')
        result['plan_fingerprint']=_plan_fingerprint(result)
        return result
    session=dict(context['session'],initial_pose=pose)
    geometry=InputGeometry(context['board'],context['local_size'],context['input_coordinate_convention'],
                           pixel_mapping=context.get('pixel_mapping'))
    settings=InputSettings(**context['settings'])
    search_budget=time_budget_seconds-min(.5,time_budget_seconds*.2)
    def rank(row):return (*row['prediction']['rank'],row['needed'],len(row['input_route']))
    compromise_rows={}
    stationary=score_native_pose(session,pose,rules,check=check)
    stationary_row=dict(input_route=[],final_pose=pose,prediction=stationary,needed=_needed([],3.,.5),source='current_observed_reference')
    def retain_compromise(row):
        if row['prediction']['predicted_accepted']:return
        key=(*row['final_pose']['position'],row['final_pose']['scale'],row['final_pose']['rotation_degrees'])
        def order(value):return (*predicted_quality(value['prediction'],rules),value['needed'],len(value['input_route']))
        prior=compromise_rows.get(key)
        if prior is None or order(row)<order(prior):compromise_rows[key]=row
        if len(compromise_rows)>24:
            victim=max(compromise_rows,key=lambda k:order(compromise_rows[k]));del compromise_rows[victim]
    def remember_nearest(row):
        retain_compromise(row)
        if not row['prediction']['predicted_accepted'] and (result['nearest_diagnostic'] is None
                or rank(row)<rank(result['nearest_diagnostic'])):
            result['nearest_diagnostic']=audit_candidate_endpoint(context,checkpoint,rules,row,check=check)
    def finish(candidate,reason):
        if not candidate and compromise_rows:
            selected=choose_compromise(context,checkpoint,rules,
                [stationary_row,*sorted(compromise_rows.values(),key=lambda row:(*predicted_quality(row['prediction'],rules),row['needed']))[:16]],
                deadline=started+time_budget_seconds-.05,clock=clock,check=check)
            if selected is not None:result['compromise_candidate']=selected
        approach=result['approach_candidate'];compromise=result['compromise_candidate']
        if approach is not None and compromise is not None:
            if predicted_quality(compromise['prediction'],rules)<=predicted_quality(approach['prediction'],rules):
                result['approach_candidate']=None
        completed=max(0.,clock()-started);result['planned_at']=now+completed
        def fits(row):return row is not None and now+completed+row['needed']+verification_margin_seconds<end
        if isinstance(candidate,list):candidate=next((row for row in candidate if fits(row)),None)
        if completed>=time_budget_seconds:candidate=None;reason='search_budget_exhausted'
        if not fits(candidate):candidate=None
        if not fits(result['nearest_diagnostic']):result['nearest_diagnostic']=None
        if not fits(result['compromise_candidate']):result['compromise_candidate']=None
        if not fits(result['approach_candidate']):result['approach_candidate']=None
        if completed>=time_budget_seconds:result['compromise_candidate']=None
        if completed>=time_budget_seconds:result['approach_candidate']=None
        classification=('predicted_exact' if candidate['prediction']['target_exact'] else 'predicted_within_tolerance') if candidate else 'not_found_in_budget'
        if candidate is None and now+completed+_needed([],3.,.5)+verification_margin_seconds>=end:
            classification='insufficient_time'
        result.update(candidate=candidate,result_classification=classification,
            stop_reason='predicted_candidate' if candidate else reason)
        if candidate is None and result['approach_candidate'] is not None:
            result.update(result_classification='model_target_approach',stop_reason='model_target_approach')
        result['plan_fingerprint']=_plan_fingerprint(result)
        return result
    # A continuous pose grid can miss a reachable integer micro drag. Generate
    # this bounded neighborhood from geometry alone, never from a live receipt.
    result['local_integer_candidates_evaluated']=0
    result['local_wheel_candidates_evaluated']=0
    result['local_combined_candidates_evaluated']=0
    result['expanded_wheel_candidates_evaluated']=0
    result['two_wheel_candidates_evaluated']=0
    result['mixed_candidates_evaluated']=0
    single_wheel_seeds=[]
    # Global mathematical search is independent of the local pointer policy.
    # A finite sample lattice does not prove continuous-space exhaustion.
    periodic=search_periodic_targets(session,rules,minimum_scale=settings.minimum_scale,
        maximum_scale=settings.maximum_scale,reference=pose,subpixel_fractions=(0.,.5),top_k=32,
        time_budget_seconds=min(4.5 if sum(r['enabled'] for r in rules)==3 else 2.5,
            max(.001,search_budget*.25)),clock=clock,check=check)
    result['periodic_search']=periodic
    result['enabled_regions']=list(periodic.get('enabled_regions',
        [i for i,rule in enumerate(rules) if rule['enabled']]))
    # Keep the best finite-model miss visible in the saved plan. It is a
    # diagnostic only: it never becomes an executable exact target by itself.
    result['periodic_nearest_candidate']=periodic.get('nearest_candidate')
    periodic_routes=[]
    triple=sum(r['enabled'] for r in rules)==3
    if triple:
        markers=np.array(session['picker_uv'],float);l,t,r,b=geometry.board
        markers=np.column_stack((l+markers[:,0]*(r-l),b-markers[:,1]*(b-t)))
        stage_end=min(started+search_budget,clock()+min(6.,search_budget*.3))
        targets=periodic['candidates'] or periodic.get('nearest_candidates',[])
        for target in targets:
            check()
            if clock()>=stage_end:break
            compiled=compile_periodic_approach(target['native_pose'],pose,geometry,settings,markers,
                wheel_delta_per_step=context['wheel_delta_per_step'],
                # A complete 132-degree route needs several bounded rotations
                # plus fractional-scale wheel pairs. Keep the same total
                # stage allowance, but finish each promising model target
                # before retaining another incomplete large-error endpoint.
                time_budget_seconds=max(.001,min(1.,stage_end-clock())),clock=clock,check=check)
            route=compiled['input_route']
            if not route or not _research_route_allowed(route,context['board']):continue
            prediction=score_native_pose(session,compiled['final_pose'],rules,check=check)
            row=dict(input_route=route,final_pose=compiled['final_pose'],prediction=prediction,
                needed=_needed(route,3.,.5),source='periodic_balanced_endpoint')
            row=audit_candidate_endpoint(context,checkpoint,rules,row,check=check)
            if prediction['predicted_accepted']:return finish(row,'predicted_candidate')
            periodic_routes.append(row);remember_nearest(row)
        result['periodic_routes_evaluated']=len(periodic_routes)
        if periodic_routes:
            periodic_routes.sort(key=lambda row:(*predicted_quality(row['prediction'],rules),row['needed']))
            bundle=bind_native_route_seeds(session,geometry,settings,
                [row['input_route'] for row in periodic_routes[:16]],
                wheel_delta_per_step=context['wheel_delta_per_step'],sample_policy=POLICY)
            elapsed=max(0.,clock()-started);cap=max(.001,search_budget-elapsed-2.)
            pipeline=search_native_input_pipeline(session,grid,geometry,settings,rules,
                wheel_delta_per_step=context['wheel_delta_per_step'],sample_policy=POLICY,
                now=now+elapsed,deadline=end-verification_margin_seconds,
                time_budget_seconds=cap,seed_bundle=bundle,generate_target_seeds=False,
                shortlist=16,max_structural=200,macro_candidates=1000,pivot_candidates=3000,
                stage_fractions=(.01,.08,.1,.06,.25,.5),clock=clock,check=check,
                prediction_quality=lambda prediction:predicted_quality(prediction,rules),
                route_filter=lambda route:_research_route_allowed(route,context['board']))
            result['periodic_route_refinement']=pipeline
            eligible=[]
            for row in pipeline['candidates']:
                audited=audit_candidate_endpoint(context,checkpoint,rules,row,check=check)
                if audited['prediction']['predicted_accepted']:eligible.append(audited)
                else:remember_nearest(audited)
            return finish(sorted(eligible,key=rank),'no_supported_accepted_candidate')
    for source,route in _local_input_candidates(geometry,settings):
        check();elapsed=max(0.,clock()-started)
        if elapsed>=search_budget or now+elapsed+verification_margin_seconds>=end:break
        if not _research_route_allowed(route,context['board']):continue
        needed=_needed(route,3.,.5)
        if now+elapsed+needed+verification_margin_seconds>=end:continue
        replay=replay_native_route(pose,route,geometry,settings,
            wheel_delta_per_step=context['wheel_delta_per_step'],sample_policy=POLICY)
        prediction=score_native_pose(session,replay['final_pose'],rules,check=check)
        counter={'fresh_local_integer_drag':'local_integer_candidates_evaluated',
                 'fresh_local_single_wheel':'local_wheel_candidates_evaluated',
                 'fresh_two_micro_drags':'local_combined_candidates_evaluated',
                 'fresh_expanded_single_wheel':'expanded_wheel_candidates_evaluated',
                 'fresh_two_wheels':'two_wheel_candidates_evaluated',
                 'fresh_micro_drag_wheel':'mixed_candidates_evaluated'}[source]
        result[counter]+=1
        row=dict(input_route=route,final_pose=replay['final_pose'],prediction=prediction,
            needed=needed,source=source,execution_verified=False,game_response_verified=False)
        if len(route)==1 and route[0]['kind']=='wheel':single_wheel_seeds.append(row)
        if prediction['predicted_accepted']:
            row=audit_candidate_endpoint(context,checkpoint,rules,row,check=check)
            completed=max(0.,clock()-started)
            if completed>=time_budget_seconds or now+completed+needed+verification_margin_seconds>=end:break
            return finish(row,'no_supported_accepted_candidate')
        remember_nearest(row)
    elapsed=max(0.,clock()-started);search_now=now+elapsed;result['planned_at']=search_now
    if elapsed>=search_budget or search_now+verification_margin_seconds>=end:
        return finish(None,'search_budget_exhausted')
    if single_wheel_seeds:
        # Preserve established local route priority; reserve part of the unused
        # total budget for the existing pipeline and final endpoint audit.
        cap=min(3.,max(0.,search_budget-elapsed-.1)*.85)
        if cap>0:
            refinement=_refine_single_wheels(session,pose,geometry,settings,rules,single_wheel_seeds,
                now=search_now,deadline=end-verification_margin_seconds,time_budget_seconds=cap,
                wheel_delta_per_step=context['wheel_delta_per_step'],clock=clock,check=check)
            result['single_wheel_refinement']=refinement
            for row in refinement['candidates']:
                check()
                if clock()-started>=time_budget_seconds:break
                audited=audit_candidate_endpoint(context,checkpoint,rules,row,check=check)
                if audited['prediction']['predicted_accepted']:return finish(audited,'no_supported_accepted_candidate')
                remember_nearest(audited)
            elapsed=max(0.,clock()-started);search_now=now+elapsed;result['planned_at']=search_now
            if elapsed>=search_budget or search_now+verification_margin_seconds>=end:
                return finish(None,'search_budget_exhausted')
    remaining_budget=search_budget-elapsed
    if periodic['candidates']:
        markers=np.array(session['picker_uv'],float)
        l,t,r,b=geometry.board
        markers=np.column_stack((l+markers[:,0]*(r-l),b-markers[:,1]*(b-t)))
        approach_end=started+min(search_budget,clock()-started+min(1.5,remaining_budget*.5))
        for target in periodic['candidates']:
            check()
            if clock()>=approach_end:break
            compiled=compile_periodic_approach(target['native_pose'],pose,geometry,settings,markers,
                wheel_delta_per_step=context['wheel_delta_per_step'],time_budget_seconds=max(.001,min(.15,approach_end-clock())),
                clock=clock,check=check)
            route=compiled['input_route']
            if not compiled['model_progress'] or not _research_route_allowed(route,context['board']):continue
            prediction=score_native_pose(session,compiled['final_pose'],rules,check=check)
            row=dict(input_route=route,final_pose=compiled['final_pose'],prediction=prediction,
                needed=_needed(route,3.,.5),source='periodic_target_approach',
                target_pose=target['native_pose'],target_prediction=target['prediction'],
                initial_marker_error=compiled['initial_marker_error'],final_marker_error=compiled['final_marker_error'])
            row=audit_candidate_endpoint(context,checkpoint,rules,row,check=check)
            if prediction['predicted_accepted']:return finish(row,'predicted_candidate')
            prior=result['approach_candidate']
            if prior is None or predicted_quality(prediction,rules)<predicted_quality(prior['prediction'],rules):
                result['approach_candidate']=row
        elapsed=max(0.,clock()-started);search_now=now+elapsed;remaining_budget=search_budget-elapsed
        if remaining_budget<=.1:return finish(None,'search_budget_exhausted')
    pipeline=search_native_input_pipeline(session,grid,geometry,settings,rules,
        wheel_delta_per_step=context['wheel_delta_per_step'],sample_policy=POLICY,now=search_now,
        deadline=end-verification_margin_seconds,time_budget_seconds=remaining_budget-min(.4,remaining_budget*.2),
        shortlist=16,max_structural=200,macro_candidates=1000,pivot_candidates=2500,clock=clock,check=check,
        route_filter=lambda route:_research_route_allowed(route,context['board']),
        target_poses=[row['native_pose'] for row in periodic['candidates']])
    result.update(pipeline=pipeline,candidate_audit_rejections=[])
    eligible=[]
    for row in pipeline['candidates']:
        check()
        if clock()-started>=time_budget_seconds:break
        try:audited=audit_candidate_endpoint(context,checkpoint,rules,row,check=check)
        except ValueError as exc:
            result['candidate_audit_rejections'].append(dict(source=row.get('source'),error=str(exc)));continue
        if audited['prediction']['predicted_accepted']:eligible.append(audited)
        else:remember_nearest(audited)
    eligible.sort(key=rank)
    return finish(eligible,'no_supported_accepted_candidate')


def validate_plan_reference(context, plan, checkpoint, frames, *, now, rules=None,purpose='target'):
    """Detect stale plans; this check does not grant permission to send input."""
    pose=_checked_checkpoint(context,checkpoint);_frames(checkpoint,frames);_fresh(now,frames)
    if plan.get('plan_fingerprint')!=_plan_fingerprint(plan):
        raise ValueError('Plan contents changed')
    if plan.get('schema',1)>=2:
        if rules is None or normalize_target_rules(rules)!=plan['normalized_rules']:
            raise ValueError('Current target differs from bound plan rules')
    if plan.get('context_fingerprint')!=context['fingerprint'] or plan.get('reference_pose')!=pose:
        raise ValueError('Plan reference differs from current session/pose')
    if now<plan['planned_at'] or now-plan['planned_at']>PLAN_OBSERVATION_MAX_AGE_SECONDS or frames[-1]['captured_monotonic']<plan['reference_frame_monotonic']:
        raise ValueError('Plan expired or observations precede the plan reference')
    if purpose not in ('target','compromise','approach'):raise ValueError('Invalid plan validation purpose')
    candidate=plan.get({'target':'candidate','compromise':'compromise_candidate','approach':'approach_candidate'}[purpose])
    end=_timer_deadline(frames,plan['effective_deadline'],plan['reserve_seconds'])
    if candidate is None or now+candidate['needed']+plan['verification_margin_seconds']>=end:
        raise ValueError('Plan has no accepted candidate or insufficient remaining time')
    if plan.get('schema',1)>=2:
        audited=audit_candidate_endpoint(context,checkpoint,rules,candidate)
        if purpose=='target' and not audited['prediction']['predicted_accepted']:
            raise ValueError('Diagnostic candidate is not an accepted target route')
        if purpose=='compromise' and audited['prediction']['predicted_accepted']:
            raise ValueError('Accepted candidate should use target validation')
        if purpose=='approach':
            target=score_native_pose(context['session'],candidate['target_pose'],rules)
            if not target['predicted_accepted'] or candidate['final_marker_error']>=candidate['initial_marker_error']:
                raise ValueError('Approach must advance toward an accepted model target')
    return dict(reference_unchanged=True,target_rules_revalidated=plan.get('schema',1)>=2,
        ready_for_input=False,live_closed_loop_verified=False)
