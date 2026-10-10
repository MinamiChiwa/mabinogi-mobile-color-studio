"""Bounded user-goal controller; IO owns reads and actual input, never apply."""
import copy,json,math,time,traceback
import numpy as np
from native_input_response import InputGeometry,replay_native_route
from native_palette_search import PoseGrid
from native_palette_scoring import score_native_pose
from hex_refinement import score_codes
from .same_session_dye_planner import (normalize_target_rules,bind_planning_context,assess_feedback,
    plan_from_checkpoint,validate_plan_reference,assess_native_feedback,_frames,EARLY_TIMER_GRACE_SECONDS,EXECUTION_RESERVE_SECONDS,
    audit_candidate_endpoint)
from .read_dye_input_backend import input_backend_binding
from .project_closed_loop_io import validate_research_gesture,InputNotStarted
from .dye_visual_readiness import VisualNotReady
from .compromise import rebase_compromise_plan,observed_quality,predicted_quality,quality_fields
from .refinement import find_refinement,find_recovery
from native_input_route_search import _needed
from dye_regions import session_region_count,bind_region_rules
from .candidate_selection import (candidate_id,candidate_observation,present_candidates,
    compile_candidate_selection,CandidateUnavailable,exact_observed_rules,actual_colors)


class GoalStop(Exception):pass


def run_goal_loop(io,session,settings,rules,*,engineering_deadline,clock=time.monotonic,
        max_rounds=64,max_actions=64,planner=plan_from_checkpoint,event=lambda row:None,pause=time.sleep,
        candidate_choice=None):
    count=session_region_count(session)
    rules=normalize_target_rules(bind_region_rules(rules,count))
    if (type(max_rounds) is not int or not 1<=max_rounds<=64 or type(max_actions) is not int or not 1<=max_actions<=64
        or not math.isfinite(engineering_deadline)):
        raise ValueError('Invalid native execution limits')
    start=clock();end=engineering_deadline;timer_grace_until=start+EARLY_TIMER_GRACE_SECONDS
    backend_binding=None;previous_timer=None;current=None;context=None
    result=dict(rules=rules,region_count=count,stop_reason='not_started',accepted=False,target_exact=False,verified=False,
        planning_rounds=[],steps=[],observations=[],actual_input_attempts=0,
        server_confirmation_verified=False,initial_visual_retries=0,observation_retries=0,compromise_selected=False)
    compromise_route=None;compromise_template=None;best_observed=None
    target_route=None;target_template=None
    candidate_rows=[];candidate_observations={};batch_id='native-'+str(time.monotonic_ns())
    if candidate_choice is not None and not callable(candidate_choice):raise ValueError('Invalid candidate choice callback')
    costs=dict(native=[],visual=[],input=[])
    io.timer_grace_until=timer_grace_until
    def emit(name,**data):event(dict(event=name,at_monotonic=clock(),**data))
    def guard(phase_deadline=None):
        until=end if phase_deadline is None else min(end,phase_deadline)
        io.check(until)
        if phase_deadline is not None and clock()>=until:raise TimeoutError('observation/input phase deadline')
        if clock()+8.>=end:raise GoalStop('insufficient_time')
    def route_allowance(row):
        route=row['input_route'];count=len(route)
        native=max(1.5,1.5*max(costs['native'][-3:],default=0.)+.3)
        visual=max(4.,1.5*max(costs['visual'][-3:],default=0.)+.5)
        preparation=max(.6,1.5*max(costs['input'][-3:],default=0.)+.25)
        measured=sum(g['input_seconds']+preparation for g in route)+native*max(0,count-1)+visual+8.
        return max(row['needed']+8.+1.5*max(0,count-1),measured),visual
    def reserve_route(row,purpose,*,include_revalidation=False):
        count=len(row['input_route'])
        if count>max_actions-result['actual_input_attempts']:
            raise GoalStop('insufficient_compromise_actions' if purpose=='compromise' else 'insufficient_route_actions')
        allowance,visual=route_allowance(row)
        if count and clock()+allowance+(visual if include_revalidation else 0.)>=end:
            raise GoalStop('insufficient_time')
    def observe(label,phase_deadline=None):
        nonlocal end,backend_binding,previous_timer,current
        current=None
        guard(phase_deadline);began=clock();until=end if phase_deadline is None else min(end,phase_deadline)
        before=io.input_backend(until)
        if backend_binding is None:backend_binding=input_backend_binding(before)
        if input_backend_binding(before)!=backend_binding:raise GoalStop('input_backend_changed')
        cp=io.checkpoint(label,until)
        try:frames=io.frames(label,until)
        except TimeoutError:
            # Retain only this fresh checkpoint, never a previous screenshot
            # pose. A decoder timeout does not invalidate the native readback.
            if (cp.get('checkpoint_valid') is True and cp.get('cpu_matches') is True
                    and before['process_identity']==json.loads(cp['binding'])[1]):
                current=dict(checkpoint=cp,frames=None,screenshot_verified=False)
            raise
        after=io.input_backend(until)
        if input_backend_binding(after)!=backend_binding:raise GoalStop('input_backend_changed')
        if before['process_identity']!=json.loads(cp['binding'])[1]:raise GoalStop('process_changed')
        if cp.get('checkpoint_valid') is not True or cp.get('cpu_matches') is not True:raise GoalStop('checkpoint_unavailable')
        frames=copy.deepcopy(frames)
        for frame in frames:frame['timer_advisory']=True
        _frames(cp,frames)
        for frame in frames:
            seconds,when=frame['remaining_seconds'],frame['captured_monotonic']
            if when<timer_grace_until:
                frame['timer_policy']='startup_advisory';continue
            if previous_timer and type(seconds) is int:
                old,old_when=previous_timer;elapsed=when-old_when
                if elapsed<=0:raise GoalStop('countdown_discontinuity')
                if seconds>old+1 or old-seconds>math.ceil(elapsed)+3:
                    seconds=None
            if type(seconds) is int and 1<=seconds<=120:
                if previous_timer:
                    end=min(end,when+seconds-EXECUTION_RESERVE_SECONDS)
                    frame['timer_policy']='consistent_pair_shortened_deadline'
                else:frame['timer_policy']='first_late_read_advisory'
                previous_timer=(seconds,when)
            else:frame['timer_policy']='unknown_advisory'
        current=dict(checkpoint=cp,frames=frames)
        result['observations'].append(dict(label=label,checkpoint=cp,frames=frames,input_before=before,input_after=after))
        if not label.startswith('initial'):costs['visual'].append(max(0.,clock()-began))
        guard(phase_deadline);return cp,frames
    def observe_resilient(label,phase_deadline=None):
        for retry in range(3):
            try:return observe(label if retry==0 else label+'_retry_'+str(retry),phase_deadline)
            except (VisualNotReady,TimeoutError) as exc:
                # Recheck the actual phase/session deadline and F9 before
                # retrying a local frame allowance. Never repeat the input.
                guard(phase_deadline)
                result['observation_retries']+=1
                emit('observation_wait',label=label,attempt=retry+1,error=str(exc))
                if retry==2:
                    if isinstance(exc,TimeoutError):
                        raise ValueError('Visual observation timed out within the active session: '+str(exc)) from exc
                    raise
                if phase_deadline is not None and clock()+.25>=min(end,phase_deadline):
                    raise TimeoutError('visual retry phase deadline') from exc
                pause(.25)
    def observe_native(label,phase_deadline=None):
        nonlocal current
        current=None;guard(phase_deadline);began=clock();until=end if phase_deadline is None else min(end,phase_deadline)
        before=io.input_backend(until)
        if input_backend_binding(before)!=backend_binding:raise GoalStop('input_backend_changed')
        cp=io.checkpoint(label,until)
        after=io.input_backend(until)
        if input_backend_binding(after)!=backend_binding:raise GoalStop('input_backend_changed')
        if before['process_identity']!=json.loads(cp['binding'])[1]:raise GoalStop('process_changed')
        assess_native_feedback(context,cp,rules)
        current=dict(checkpoint=cp,frames=None,screenshot_verified=False)
        result['observations'].append(dict(label=label,checkpoint=cp,frames=None,
            input_before=before,input_after=after,screenshot_verified=False))
        emit('native_observed',colors=cp['client_hex'],label=label,screenshot_verified=False)
        costs['native'].append(max(0.,clock()-began))
        guard(phase_deadline);return cp
    def submit(gesture,label,fresh,purpose,*,visual_required=True,phase_deadline=None):
        nonlocal current
        validate_research_gesture(gesture,geometry.board)
        expected=replay_native_route(fresh['pose'],[gesture],geometry,settings,
            wheel_delta_per_step=1.,sample_policy='all_recorded_points')['final_pose']
        try:guard(phase_deadline)
        except TimeoutError as exc:
            if phase_deadline is not None:raise InputNotStarted(str(exc)) from exc
            raise
        until=end if phase_deadline is None else min(end,phase_deadline)
        if clock()>=until:raise InputNotStarted('input phase deadline')
        if result['actual_input_attempts']>=max_actions:raise GoalStop('action_limit')
        current=None;result['actual_input_attempts']+=1
        step=dict(before=fresh,requested_gesture=gesture,expected_pose=expected,purpose=purpose);result['steps'].append(step)
        emit('action',kind=gesture['kind'],purpose=purpose)
        performer=(getattr(io,'perform_protected_candidate',io.perform_candidate)
            if phase_deadline is not None and purpose in ('refine','restore_refinement','select_candidate','restore_selection') else io.perform_candidate)
        began=clock();receipt=performer(gesture,label,until);step['receipt']=receipt
        costs['input'].append(max(0.,clock()-began-gesture['input_seconds']))
        if receipt.get('completed') is not True:raise GoalStop('input_outcome_unknown')
        trace=receipt.get('actual_trace')
        trace_ok=(isinstance(trace,list) and len(trace)==len(gesture['points']) and not any(
            row.get('actual_client') is None or np.max(np.abs(np.asarray(row['actual_client'])-point))>1
            for row,point in zip(trace,gesture['points'])))
        if not trace_ok:
            # The game state readback is authoritative. A missing or slightly
            # delayed SendInput trace is useful evidence, but does not prove
            # that the gesture failed; retain it as a warning and replan from
            # the actual checkpoint below.
            step['trace_warning']='cursor_trace_mismatch'
        if visual_required:
            after,after_frames=observe_resilient(label+'_after',until)
            measured=assess_feedback(context,after,after_frames,rules,expected_pose=expected)
        else:
            after=observe_native(label+'_native_after',until);after_frames=None
            measured=assess_native_feedback(context,after,rules,expected_pose=expected)
            if measured['observed_target_accepted'] and purpose not in ('select_candidate','restore_selection'):
                # Confirm an early target hit visually. A valid bound native
                # pose residual only rebases subsequent input; it does not
                # repeat the costly screenshot/OCR phase mid-route.
                step['native_readback']=copy.deepcopy(after)
                after,after_frames=observe_resilient(label+'_after',until)
                measured=assess_feedback(context,after,after_frames,rules,expected_pose=expected)
        step.update(after=after,after_frames=after_frames,screenshot_verified=measured['screenshot_verified'])
        step['feedback']=measured
        if measured['stop_reason']=='target_visual_unconfirmed':raise GoalStop('target_visual_unconfirmed')
        if measured['stop_reason']=='model_response_mismatch':
            # Response residuals calibrate the next reference; their magnitude
            # does not cancel an authorized route. Identity, focus, timing and
            # read validity are checked independently by the IO boundary.
            step['model_response_warning']='model_response_mismatch'
            measured['stop_reason']='replan_required'
        return after,after_frames,measured

    def retain_candidates(plan):
        nonlocal candidate_rows
        if candidate_choice is None:return
        rows=plan.get('candidate_pool',[])
        rows=[*rows,*(row for row in (plan.get('candidate'),plan.get('compromise_candidate')) if row)]
        retained={tuple(row['actual_colors']):row for row in candidate_rows}
        for row in rows:
            owned=copy.deepcopy(row)
            owned.setdefault('actual_colors',actual_colors(context,owned['final_pose']))
            retained[tuple(owned['actual_colors'])]=owned
        candidate_rows=sorted(retained.values(),key=lambda row:(*predicted_quality(row['prediction'],rules),
            row['needed'],len(row['input_route'])))[:12]
        emit('native_candidates',**present_candidates(batch_id,candidate_rows,rules,
            cp['client_hex'],candidate_observations,deadline=end))

    def candidate_choices():
        """Retain this IO/context and reserve a checked return before any selection."""
        nonlocal cp,frames,current,candidate_rows,best_observed
        if candidate_choice is None or not current or not current.get('frames'):return
        score=score_native_pose(session,cp['pose'],rules)
        stationary=audit_candidate_endpoint(context,cp,rules,dict(input_route=[],final_pose=cp['pose'],
            prediction=score,needed=_needed([],3.,.5),source='current_observed_reference'))
        stationary['actual_colors']=cp['client_hex']
        retained={tuple(row['actual_colors']):row for row in candidate_rows}
        retained[tuple(cp['client_hex'])]=stationary
        candidate_rows=sorted(retained.values(),key=lambda row:(*predicted_quality(row['prediction'],rules),
            row['needed'],len(row['input_route'])))
        if len(candidate_rows)>12:
            candidate_rows=[row for row in candidate_rows[:11] if row['actual_colors']!=cp['client_hex']]+[stationary]
            candidate_rows.sort(key=lambda row:(*predicted_quality(row['prediction'],rules),row['needed']))
        result.update(candidate_batch_id=batch_id,candidate_selections=[])
        def ready():
            payload=present_candidates(batch_id,candidate_rows,rules,cp['client_hex'],candidate_observations,deadline=end)
            result['candidates']=copy.deepcopy(payload['candidates']);result['candidate_observations']=copy.deepcopy(payload['observations'])
            emit('native_candidate_ready',**payload)
        ready()
        close_reason='deadline'
        def closing_allowance():return max(4.,1.5*max(costs['visual'][-3:],default=0.)+.5)+8.25
        while clock()+closing_allowance()<end:
            close_allowance=closing_allowance()
            guard();began=clock();poll_end=min(end-close_allowance,began+.25)
            selected_id=candidate_choice(batch_id,poll_end)
            io.check(end)
            if clock()+close_allowance>=end:break
            guard()
            if selected_id is None:
                # A UI poll may return immediately. Keep guards active without
                # consuming a search allowance or extending this session cap.
                left=poll_end-clock()
                if left>0:pause(left)
                continue
            row=next((row for row in candidate_rows if candidate_id(batch_id,row['actual_colors'])==selected_id),None)
            if row is None:
                emit('native_candidate_selected',batch_id=batch_id,candidate_id=selected_id,status='rejected',reason='stale_or_unknown_candidate')
                continue
            if row['actual_colors']==cp['client_hex']:
                cp,frames=observe_resilient('selection_current_revalidate')
                if row['actual_colors']==cp['client_hex']:
                    emit('native_candidate_selected',batch_id=batch_id,candidate_id=selected_id,status='current',
                        **candidate_observation(cp['client_hex'],rules));continue
            # Even the cheapest choice needs fresh frames, full compilation,
            # final frames and protected measured recovery. No partial route
            # begins merely because its first gesture fits.
            if clock()+24.>=end:
                emit('native_candidate_selected',batch_id=batch_id,candidate_id=selected_id,status='rejected',reason='insufficient_protected_time')
                continue
            fresh,fresh_frames=observe_resilient('selection_reference')
            cp,frames=fresh,fresh_frames
            anchor=copy.deepcopy(current);baseline=anchor['checkpoint'];anchor_rules=exact_observed_rules(baseline['client_hex'])
            try:
                compiled=compile_candidate_selection(context,fresh,rules,row,
                    deadline=min(clock()+6.,end-18.),clock=clock,
                    check=lambda:getattr(io,'planning_check',io.check)(end))
                route=compiled['input_route'];returns=compiled['prefix_recoveries']
                outward,visual=route_allowance(compiled)
                return_allowance=max((route_allowance(recovery)[0] for recovery in returns),default=0.)
                return_actions=max((len(recovery['input_route']) for recovery in returns),default=0)+1
                # Two measured return attempts and correction search are reserved.
                recovery_reserve=2*(return_allowance+2.)+visual
                if len(route)+2*return_actions>max_actions-result['actual_input_attempts']:
                    raise CandidateUnavailable('insufficient_protected_actions')
                if clock()+outward+recovery_reserve>=end:
                    raise CandidateUnavailable('insufficient_protected_time')
            except (CandidateUnavailable,ValueError,TimeoutError) as exc:
                emit('native_candidate_selected',batch_id=batch_id,candidate_id=selected_id,status='rejected',reason=str(exc))
                continue
            transaction=dict(candidate_id=selected_id,anchor_colors=baseline['client_hex'],
                target_colors=row['actual_colors'],protection_audit=compiled['protection_audit'],
                status='admitted',return_allowance=recovery_reserve,actual_colors=None)
            result['candidate_selections'].append(transaction)
            emit('native_candidate_selected',batch_id=batch_id,candidate_id=selected_id,status='positioning')
            phase_end=min(end-recovery_reserve,clock()+outward);completed=0;dirty=False
            failure=None;selection_step_start=len(result['steps'])
            try:
                reference=fresh
                for index,gesture in enumerate(route):
                    dirty=True
                    cp,frames,feedback=submit(gesture,'selection_'+str(len(result['candidate_selections']))+'_'+str(index),
                        reference,'select_candidate',visual_required=index==len(route)-1,phase_deadline=phase_end)
                    completed=index+1;reference=cp
                    # A hit on the user's original target is an intermediate,
                    # not permission to truncate the explicitly selected route.
                    if result['steps'][-1].get('model_response_warning') and index+1<len(route):
                        suffix=route[index+1:]
                        replay=replay_native_route(cp['pose'],suffix,geometry,settings,
                            wheel_delta_per_step=1.,sample_policy='all_recorded_points')
                        audited=audit_candidate_endpoint(context,cp,rules,dict(input_route=suffix,
                            final_pose=replay['final_pose'],prediction=score_native_pose(session,replay['final_pose'],rules),
                            needed=_needed(suffix,3.,.5),source='actual_selection_suffix'))
                        result['steps'][-1]['remaining_route_audit']=dict(reference_pose=cp['pose'],
                            final_pose=audited['final_pose'],prediction=audited['prediction'],continued=True)
                        emit('route_revalidated',remaining_gestures=len(suffix),reference_pose=cp['pose'],
                            predicted_colors=audited['prediction']['colors'],purpose='select_candidate')
                if not route:cp,frames=observe_resilient('selection_current',phase_end)
                if not assess_feedback(context,cp,frames,compiled['selection_rules'])['observed_target_accepted']:
                    failure='candidate_endpoint_unconfirmed'
            except (TimeoutError,VisualNotReady,GoalStop,ValueError) as exc:
                if isinstance(exc,GoalStop) and str(exc)!='target_visual_unconfirmed':raise
                latest=result['steps'][-1] if len(result['steps'])>selection_step_start else None
                completed=sum(step.get('receipt',{}).get('completed') is True
                    for step in result['steps'][selection_step_start:])
                if isinstance(exc,InputNotStarted):dirty=completed>0
                if dirty and not isinstance(exc,InputNotStarted) and (latest is None or not latest.get('receipt',{}).get('completed')):
                    raise GoalStop('input_outcome_unknown')
                failure=str(exc)
            if failure is None:
                transaction.update(status='observed',actual_colors=cp['client_hex'])
                candidate_observations[selected_id]=candidate_observation(cp['client_hex'],rules)
                if observed_quality(cp['client_hex'],rules)<observed_quality(best_observed['checkpoint']['client_hex'],rules):
                    best_observed=copy.deepcopy(current)
                result.update(stop_reason='user_candidate_observed',accepted=score_codes(cp['client_hex'],rules)['accepted'])
                emit('native_candidate_selected',batch_id=batch_id,candidate_id=selected_id,status='observed',
                    **candidate_observations[selected_id]);ready();continue
            transaction['failure']=failure
            if not dirty:
                current=anchor;cp,frames=baseline,anchor['frames']
                emit('native_candidate_selected',batch_id=batch_id,candidate_id=selected_id,status='rejected',reason=failure)
                ready();continue
            # Failure returns through fresh native readback; opposite wheel
            # descriptors or an old pose reference never authorize this input.
            restored=False
            for retry in range(2):
                cp=observe_native('selection_return_reference_'+str(retry))
                preferred=returns[min(max(completed,1),len(returns))-1]['input_route'] if returns else []
                replay=replay_native_route(cp['pose'],preferred,geometry,settings,
                    wheel_delta_per_step=1.,sample_policy='all_recorded_points')
                recovery=audit_candidate_endpoint(context,cp,anchor_rules,dict(input_route=preferred,
                    final_pose=replay['final_pose'],prediction=score_native_pose(session,replay['final_pose'],anchor_rules),
                    needed=_needed(preferred,3.,.5),source='actual_selection_return'))
                if not recovery['prediction']['predicted_accepted']:
                    recovery=find_recovery(context,cp,baseline,anchor_rules,
                        deadline=min(clock()+2.,end-8.),clock=clock,
                        check=lambda:getattr(io,'planning_check',io.check)(end),preferred_routes=(preferred,))
                if recovery is None:continue
                allowance,_=route_allowance(recovery)
                if len(recovery['input_route'])>max_actions-result['actual_input_attempts'] or clock()+allowance>=end:break
                reference=cp;return_route=recovery['input_route'];return_end=min(end-8.,clock()+allowance)
                for index,gesture in enumerate(return_route):
                    cp,frames,feedback=submit(gesture,'selection_return_'+str(retry)+'_'+str(index),reference,
                        'restore_selection',visual_required=index==len(return_route)-1,phase_deadline=return_end)
                    reference=cp
                if not return_route:cp,frames=observe_resilient('selection_return_current',return_end)
                if assess_feedback(context,cp,frames,anchor_rules)['observed_target_accepted']:
                    restored=True;break
            if not restored:
                transaction['status']='recovery_unconfirmed'
                emit('native_candidate_selected',batch_id=batch_id,candidate_id=selected_id,status='recovery_unconfirmed',reason=failure)
                raise GoalStop('candidate_recovery_unconfirmed')
            transaction.update(status='restored',actual_colors=cp['client_hex'])
            result['accepted']=score_codes(cp['client_hex'],rules)['accepted']
            restored_id=next((candidate_id(batch_id,row['actual_colors']) for row in candidate_rows
                if row['actual_colors']==cp['client_hex']),None)
            emit('native_candidate_selected',batch_id=batch_id,candidate_id=restored_id,status='restored',reason=failure,
                failed_candidate_id=selected_id,current_candidate_id=restored_id,
                **candidate_observation(cp['client_hex'],rules));ready()
        result['candidate_selection_close']=close_reason
        # Waiting is not evidence that the board stayed at its last measured
        # pose. Re-read two frames before exposing a final current result.
        result['last_verified_candidate_colors']=cp['client_hex']
        cp,frames=observe_resilient('candidate_wait_closed')
        final_id=next((candidate_id(batch_id,row['actual_colors']) for row in candidate_rows
            if row['actual_colors']==cp['client_hex']),None)
        emit('native_candidate_closed',batch_id=batch_id,reason=close_reason,current_colors=cp['client_hex'],
            current_candidate_id=final_id,**candidate_observation(cp['client_hex'],rules))
        result['current_candidate_id']=final_id

    def protected_refinement():
        """Spend only time left after reserving a measured, audited return."""
        nonlocal cp,frames,current,best_observed
        result['refinement_attempts']=[];result['refinement_searches']=[]
        result['refinement_budget_decisions']=[];excluded=[]
        def stop(reason):result['refinement_stop']=reason
        def limits():
            # Each call receives its phase deadline. These allowances absorb
            # measured latency; a slow probe cannot borrow the return window.
            native=max(1.5,1.5*max(costs['native'][-3:],default=0.)+.3)
            visual=max(4.,1.5*max(costs['visual'][-3:],default=0.)+.5)
            # Long earlier drags must not inflate the cost of a tiny arc. Its
            # descriptor duration is known; reserve measured preparation apart.
            action=max(.6,1.5*max(costs['input'][-3:],default=0.)+.25)
            return native,visual,action
        def route_cost(route,native,visual,action):
            return sum(action+g['input_seconds'] for g in route)+native*max(0,len(route)-1)+visual
        def reaudited(reference,route):
            replay=replay_native_route(reference['pose'],route,geometry,settings,
                wheel_delta_per_step=1.,sample_policy='all_recorded_points')
            return audit_candidate_endpoint(context,reference,rules,dict(
                input_route=copy.deepcopy(route),final_pose=replay['final_pose'],
                prediction=score_native_pose(session,replay['final_pose'],rules),
                needed=_needed(route,3.,.5),source='protected_actual_reference'))
        def endpoint_checkpoint(reference,row):
            # Disabled regions are omitted from target predictions, while a
            # bound native checkpoint includes every actual client HEX.
            neutral=[dict(enabled=True,exact=True,colors=['#000000'],tolerance=0.) for _ in range(count)]
            return dict(reference,pose=row['final_pose'],
                client_hex=score_native_pose(session,row['final_pose'],neutral)['colors'])
        while result['actual_input_attempts']<max_actions:
            anchor=copy.deepcopy(current)
            if not anchor or not anchor.get('frames') or not assess_feedback(
                context,anchor['checkpoint'],anchor['frames'],rules)['screenshot_verified']:
                stop('anchor_not_visually_verified');return
            baseline=anchor['checkpoint'];quality=observed_quality(baseline['client_hex'],rules)
            native,visual,action=limits()
            # Reserve the common two short rotations and three-gesture corrected
            # return before allocating search. The selected descriptors are
            # rechecked below against their complete actual duration.
            short_arc_seconds=.296
            prototype_trial=2*(action+short_arc_seconds)+native+visual
            prototype_return=prototype_trial+action+.5+native
            minimum=native+prototype_trial+2*native+2*(2.+prototype_return)+8.
            budget=dict(at_monotonic=clock(),effective_deadline=end,remaining_seconds=end-clock(),
                native_phase_seconds=native,visual_phase_seconds=visual,input_preparation_seconds=action,
                protected_allowance_seconds=minimum)
            result['refinement_budget_decisions'].append(budget)
            if clock()+minimum+.25>=end:stop('insufficient_protected_time');return
            emit('refinement_planning',protected_colors=baseline['client_hex'])
            search_end=min(clock()+10.,end-minimum)
            stats={};search_started=clock()
            try:
                row=find_refinement(context,baseline,rules,deadline=search_end,clock=clock,
                    check=lambda:getattr(io,'planning_check',io.check)(min(end,search_end)),excluded=excluded,
                    stats=stats,progress=lambda update:emit('refinement_search_progress',**update))
            except TimeoutError:
                stop('local_search_timeout');return
            finally:
                stats.update(started_monotonic=search_started,finished_monotonic=clock(),
                    allowance_seconds=search_end-search_started,effective_deadline=end)
                result['refinement_searches'].append(stats)
            if row is None:
                stop('local_family_exhausted' if stats.get('family_exhausted') else
                    'local_search_budget' if stats.get('deadline_reached') else 'no_safe_improvement');return
            route=row.get('input_route',[]);returns=row.get('prefix_recoveries',[])
            if not route or len(route)!=len(returns):stop('recovery_not_proven');return
            # Reproduce both outward and every prefix return against this
            # session. A candidate's own advertised quality is insufficient.
            row=reaudited(baseline,route)
            if predicted_quality(row['prediction'],rules)>=quality:
                stop('no_safe_improvement');return
            longest=0;return_cost=0.
            for index,recovery in enumerate(returns):
                prefix=reaudited(baseline,route[:index+1])
                endpoint=endpoint_checkpoint(baseline,prefix)
                recovery=reaudited(endpoint,recovery['input_route'])
                if predicted_quality(recovery['prediction'],rules)>quality:
                    stop('recovery_not_proven');return
                longest=max(longest,len(recovery['input_route']))
                return_cost=max(return_cost,route_cost(recovery['input_route'],native,visual,action))
            maximum_return_actions=min(4,longest+1)
            if len(route)+2*max(1,maximum_return_actions)>max_actions-result['actual_input_attempts']:
                stop('insufficient_protected_actions');return
            trial_cost=route_cost(route,native,visual,action)
            # A measured endpoint correction can add one bounded drag to the
            # prepared inverse; both return attempts and their refresh fit.
            corrected_return_cost=return_cost+action+.5+native
            reserved_return=2*native+2*(2.+corrected_return_cost)
            required=native+trial_cost+reserved_return+8.
            if clock()+required>=end:stop('insufficient_protected_time');return
            fresh=observe_native('refine_reference',clock()+native)
            if fresh['pose']!=baseline['pose'] or fresh['client_hex']!=baseline['client_hex']:
                cp,frames=observe_resilient('refine_reference_changed');stop('reference_changed');return
            current=anchor
            if clock()+trial_cost+reserved_return+8.>=end:
                stop('insufficient_protected_time');return
            transaction=dict(anchor=anchor,candidate=row,prefix_recoveries=copy.deepcopy(returns),
                admitted_at=clock(),deadline=end,trial_allowance=trial_cost,
                return_allowance=reserved_return,maximum_return_actions=maximum_return_actions,
                status='admitted',recovery_attempts=[])
            result['refinement_attempts'].append(transaction)
            phase_end=min(end-reserved_return-8.,clock()+trial_cost)
            completed_prefix=0;dirty=False;failure=None
            try:
                reference=fresh
                for index,gesture in enumerate(route):
                    dirty=True
                    cp,frames,feedback=submit(gesture,'refine_'+str(len(result['refinement_attempts'])-1)+'_'+str(index),
                        reference,'refine',visual_required=index==len(route)-1,phase_deadline=phase_end)
                    completed_prefix=index+1;reference=cp
                    if feedback['observed_target_accepted']:break
                    if index<len(route)-1:
                        measured_return=reaudited(cp,returns[index]['input_route'])
                        transaction.setdefault('prefix_return_audits',[]).append(measured_return)
                        # Measured feedback, rather than error magnitude, decides
                        # whether the next trial input still has a proven return.
                        if predicted_quality(measured_return['prediction'],rules)>quality:
                            failure='actual_return_requires_revalidation';break
                        for future in range(index+1,len(route)):
                            suffix=reaudited(cp,route[index+1:future+1])
                            endpoint=endpoint_checkpoint(cp,suffix)
                            future_return=reaudited(endpoint,returns[future]['input_route'])
                            transaction.setdefault('remaining_return_audits',[]).append(future_return)
                            if predicted_quality(future_return['prediction'],rules)>quality:
                                failure='remaining_return_requires_revalidation';break
                        if failure:break
                if current and current.get('frames') and assess_feedback(context,cp,frames,rules)['screenshot_verified']:
                    actual_quality=observed_quality(cp['client_hex'],rules)
                    if actual_quality<=quality:
                        transaction.update(status='promoted' if actual_quality<quality else 'retained',actual_colors=cp['client_hex'])
                        if actual_quality<observed_quality(best_observed['checkpoint']['client_hex'],rules):
                            best_observed=copy.deepcopy(current)
                        if feedback['observed_target_accepted']:
                            result.update(accepted=True,stop_reason='target_observed');stop('target_observed');return
                        excluded.append(copy.deepcopy(route))
                        if actual_quality==quality:stop('trial_not_improved');return
                        continue
            except (TimeoutError,VisualNotReady,GoalStop) as exc:
                if isinstance(exc,GoalStop) and str(exc)!='target_visual_unconfirmed':raise
                failure=type(exc).__name__+': '+str(exc)
                # Input whose completion is unknown is not safe to reverse.
                if isinstance(exc,InputNotStarted):
                    if completed_prefix==0:
                        current=anchor;transaction['status']='not_started';stop('trial_not_started');return
                elif not result['steps'][-1].get('receipt',{}).get('completed'):
                    raise GoalStop('input_outcome_unknown')
                else:completed_prefix=index+1
            if not dirty:current=anchor;stop('trial_not_started');return
            transaction['trial_failure']=failure
            # Never improvise a full global search in this reserved phase.
            restore_end=min(end-8.,clock()+reserved_return)
            cp=observe_native('refinement_return_reference',min(restore_end,clock()+native))
            pending_returns=[]
            for recovery_index in range(2):
                guard()
                search_until=min(restore_end-corrected_return_cost,clock()+2.)
                if search_until<=clock():break
                candidate=None
                if recovery_index==0 and 0<completed_prefix<=len(returns):
                    prepared=reaudited(cp,returns[completed_prefix-1]['input_route'])
                    if predicted_quality(prepared['prediction'],rules)<=quality:candidate=prepared
                if candidate is None:
                    try:
                        candidate=find_recovery(context,cp,baseline,rules,deadline=search_until,clock=clock,
                            check=lambda:getattr(io,'planning_check',io.check)(min(end,search_until)),
                            preferred_routes=(*pending_returns,*(r['input_route'] for r in reversed(returns))))
                    except TimeoutError as exc:
                        transaction.setdefault('recovery_search_errors',[]).append(str(exc));continue
                if candidate is None:break
                candidate=reaudited(cp,candidate['input_route'])
                if predicted_quality(candidate['prediction'],rules)>quality:break
                recovery_route=candidate['input_route']
                if (len(recovery_route)>maximum_return_actions or
                    len(recovery_route)>max_actions-result['actual_input_attempts']):break
                allowance=route_cost(recovery_route,native,visual,action)
                if clock()+allowance>restore_end:break
                transaction['recovery_attempts'].append(candidate)
                until=min(restore_end,clock()+allowance)
                recovery_step_start=len(result['steps'])
                try:
                    reference=cp
                    for index,gesture in enumerate(recovery_route):
                        cp,frames,feedback=submit(gesture,'refinement_return_'+str(recovery_index)+'_'+str(index),
                            reference,'restore_refinement',visual_required=index==len(recovery_route)-1,phase_deadline=until)
                        reference=cp
                    if not recovery_route:cp,frames=observe_resilient('refinement_return_current',until)
                    if (current and current.get('frames') and assess_feedback(context,cp,frames,rules)['screenshot_verified'] and
                        observed_quality(cp['client_hex'],rules)<=quality):
                        transaction.update(status='restored',actual_colors=cp['client_hex'])
                        if observed_quality(cp['client_hex'],rules)<observed_quality(best_observed['checkpoint']['client_hex'],rules):
                            best_observed=copy.deepcopy(current)
                        if score_codes(cp['client_hex'],rules)['accepted']:
                            result.update(accepted=True,stop_reason='target_observed')
                        stop('trial_not_improved');return
                except (TimeoutError,VisualNotReady,GoalStop) as exc:
                    if isinstance(exc,GoalStop) and str(exc)!='target_visual_unconfirmed':raise
                    transaction['recovery_read_error']=str(exc)
                    if (recovery_route and not isinstance(exc,InputNotStarted) and
                        not result['steps'][-1].get('receipt',{}).get('completed')):
                        raise GoalStop('input_outcome_unknown')
                    if clock()+native>=restore_end:break
                    cp=observe_native('refinement_return_refresh',min(restore_end,clock()+native))
                finished=sum(s.get('receipt',{}).get('completed') is True
                    for s in result['steps'][recovery_step_start:])
                pending_returns=[recovery_route[finished:]] if finished<len(recovery_route) else []
            transaction['status']='recovery_unconfirmed'
            raise GoalStop('refinement_recovery_unconfirmed')
        stop('insufficient_protected_actions')
    try:
        guard();visual_end=min(end,clock()+EARLY_TIMER_GRACE_SECONDS)
        for attempt in range(120):
            if clock()>=visual_end:raise GoalStop('initial_visual_timeout')
            try:
                cp,frames=observe('initial' if attempt==0 else 'initial_retry_'+str(attempt),visual_end)
                if clock()>=visual_end:raise GoalStop('initial_visual_timeout')
                break
            except (VisualNotReady,TimeoutError) as exc:
                guard()
                if clock()>=visual_end:raise GoalStop('initial_visual_timeout')
                result['initial_visual_retries']+=1
                emit('initial_visual_wait',attempt=attempt+1,error=str(exc),waiting_deadline=visual_end)
                pause(min(.25,max(0.,visual_end-clock())))
        else:raise GoalStop('initial_visual_timeout')
        geometry=InputGeometry(cp['board'],cp['local_size'],'windows_legacy_mouse_pixels',cp.get('pixel_mapping'))
        context=bind_planning_context(session,cp,geometry,settings,wheel_delta_per_step=1.,calibration_evidence=dict(
            source='native_live_repeated_input_backend',viewport_origin=backend_binding['viewport_origin'],
            viewport_scale=backend_binding['viewport_scale'],backend_during_actions_synchronously_recorded=True))
        if settings.move_threshold!=0.:raise GoalStop('unsupported_input_settings')
        result['initial']=copy.deepcopy(current)
        initial_score=score_codes(cp['client_hex'],rules)
        initial_metrics=quality_fields(initial_score,rules,verified=True)
        result.update(initial_maximum=initial_metrics['maximum'],initial_average=initial_metrics['average'])
        best_observed=copy.deepcopy(current)
        for number in range(max_rounds):
            guard();observed=assess_feedback(context,cp,frames,rules)
            emit('observed',colors=cp['client_hex'],remaining_seconds=frames[-1]['remaining_seconds'])
            if observed['stop_reason']=='target_visual_unconfirmed':raise GoalStop('target_visual_unconfirmed')
            if observed['observed_target_accepted']:
                if candidate_choice is not None and not candidate_rows:
                    p=cp['pose'];x,y=p['position'];s=p['scale']
                    grid=PoseGrid((x-.04,x+.04),(y-.02,y+.02),9,5,
                        (s*.99,s,s*1.01,s*.9999),(p['rotation_degrees'],))
                    plan=planner(context,cp,frames,rules,grid,now=clock(),engineering_deadline=end,
                        time_budget_seconds=min(25.,max(.01,end-clock()-15)),clock=clock,
                        check=lambda:getattr(io,'planning_check',io.check)(end),collect_candidates=True)
                    result['planning_rounds'].append(plan);retain_candidates(plan)
                result.update(stop_reason='target_observed',accepted=True);break
            if result['actual_input_attempts']>=max_actions:raise GoalStop('action_limit')
            pose=cp['pose'];x,y=pose['position'];scale=pose['scale']
            grid=PoseGrid((x-.04,x+.04),(y-.02,y+.02),9,5,
                (scale*.99,scale,scale*1.01,scale*.9999),(pose['rotation_degrees'],))
            emit('planning',round=number,purpose='compromise' if compromise_route is not None else 'target')
            if target_route is not None:
                plan=rebase_compromise_plan(context,cp,frames,rules,target_route,target_template,
                    now=clock(),check=lambda:getattr(io,'planning_check',io.check)(end),purpose='target')
                if plan['candidate'] is None:
                    target_route=target_template=None
                    plan=planner(context,cp,frames,rules,grid,now=clock(),engineering_deadline=end,
                        time_budget_seconds=min(25.,max(.01,end-clock()-15)),clock=clock,
                        check=lambda:getattr(io,'planning_check',io.check)(end),
                        **({'collect_candidates':True} if candidate_choice is not None else {}))
            elif compromise_route is None:
                plan=planner(context,cp,frames,rules,grid,now=clock(),engineering_deadline=end,
                    time_budget_seconds=min(25.,max(.01,end-clock()-15)),clock=clock,
                    check=lambda:getattr(io,'planning_check',io.check)(end),
                    **({'collect_candidates':True} if candidate_choice is not None else {}))
            else:
                plan=rebase_compromise_plan(context,cp,frames,rules,compromise_route,compromise_template,
                    now=clock(),check=lambda:getattr(io,'planning_check',io.check)(end))
            result['planning_rounds'].append(plan)
            retain_candidates(plan)
            purpose='target'
            if plan['candidate'] is None:
                if plan.get('approach_candidate') is not None:
                    purpose='approach'
                    emit('target_approach',prediction=plan['approach_candidate']['target_prediction'])
                elif plan.get('compromise_candidate') is None:
                    raise GoalStop('insufficient_time' if plan.get('result_classification')=='insufficient_time' else 'not_found_in_budget')
                else:
                    purpose='compromise';selected=plan['compromise_candidate']
                    result['compromise_selected']=True
                    if compromise_template is None:
                        result['compromise_prediction']=copy.deepcopy(selected)
                        compromise_template=copy.deepcopy(plan)
                        emit('compromise_selected',prediction=selected['prediction'],metrics=selected.get('compromise_metrics'))
            selected=plan[{'target':'candidate','compromise':'compromise_candidate','approach':'approach_candidate'}[purpose]]
            end=min(end,plan['effective_deadline'])
            # Admit the complete sequence and its final visual readback before
            # any gesture, independent of whether it is target or compromise.
            reserve_route(selected,purpose,include_revalidation=True)
            try:
                fresh,fresh_frames=observe_resilient('plan_'+str(number)+'_revalidate')
                validate_plan_reference(context,plan,fresh,fresh_frames,now=clock(),rules=rules,purpose=purpose)
            except ValueError as exc:
                if 'Plan reference differs' not in str(exc):raise
                result['reference_replans']=result.get('reference_replans',0)+1
                compromise_route=None;compromise_template=None
                fresh,fresh_frames=observe_resilient('plan_'+str(number)+'_reference_refresh')
                cp,frames=fresh,fresh_frames
                continue
            route=selected['input_route']
            if not route:
                cp,frames=fresh,fresh_frames
                if purpose=='compromise':result['stop_reason']='compromise_observed';break
                continue
            reserve_route(selected,purpose)
            # Run a validated route in sequence. Every gesture uses the measured
            # previous endpoint; response residuals update that reference and
            # the remaining-route forecast instead of restarting global search.
            route_fresh=fresh
            for gesture_index,gesture in enumerate(route):
                cp,frames,feedback=submit(
                    gesture,
                    'candidate_'+str(number) if gesture_index==0 else
                    'candidate_'+str(number)+'_step_'+str(gesture_index),
                    route_fresh,purpose,visual_required=gesture_index==len(route)-1)
                if observed_quality(cp['client_hex'],rules)<observed_quality(best_observed['checkpoint']['client_hex'],rules):
                    best_observed=copy.deepcopy(current)
                if feedback['observed_target_accepted']:
                    result.update(stop_reason='target_observed',accepted=True);break
                if result['steps'][-1].get('model_response_warning'):
                    suffix=route[gesture_index+1:]
                    if suffix:
                        guard()
                        replay=replay_native_route(cp['pose'],suffix,geometry,settings,
                            wheel_delta_per_step=1.,sample_policy='all_recorded_points')
                        rescored=score_native_pose(session,replay['final_pose'],rules)
                        result['steps'][-1]['remaining_route_audit']=dict(
                            reference_pose=cp['pose'],final_pose=replay['final_pose'],
                            prediction=rescored,continued=True,
                            target_prediction_changed=not bool(rescored['predicted_accepted']))
                        emit('route_revalidated',remaining_gestures=len(suffix),
                            reference_pose=cp['pose'],predicted_colors=rescored['colors'],purpose=purpose)
                route_fresh=cp
            if result.get('accepted'):break
            if result.get('stop_reason')=='compromise_observed':break
            if purpose=='target':
                target_route=target_template=None
            if purpose=='compromise':
                compromise_route=compromise_template=None
                result['stop_reason']='compromise_observed';break
        else:result['stop_reason']='round_limit'
        if (result['stop_reason']=='compromise_observed' and best_observed is not None and
            observed_quality(cp['client_hex'],rules)>observed_quality(best_observed['checkpoint']['client_hex'],rules)):
            # Restore actual measured colors through a new native search. No
            # inverse-wheel assumption or reused old-pose route is permitted.
            restore_rules=[dict(enabled=True,exact=True,colors=[c],tolerance=0.)
                for c in best_observed['checkpoint']['client_hex']]
            result['restoration_rounds']=[]
            for recovery in range(min(2,max_actions-result['actual_input_attempts'])):
                guard();fresh,fresh_frames=observe_resilient('restore_'+str(recovery)+'_before')
                p=fresh['pose'];x,y=p['position'];s=p['scale']
                grid=PoseGrid((x-.04,x+.04),(y-.02,y+.02),9,5,(s*.99,s,s*1.01,s*.9999),(p['rotation_degrees'],))
                recovery_plan=plan_from_checkpoint(context,fresh,fresh_frames,restore_rules,grid,now=clock(),
                    engineering_deadline=end,time_budget_seconds=min(4.,max(.01,end-clock()-12)),clock=clock,
                    check=lambda:getattr(io,'planning_check',io.check)(end))
                result['restoration_rounds'].append(recovery_plan)
                candidate=recovery_plan['candidate']
                if candidate is None:break
                try:reserve_route(candidate,'restore_best',include_revalidation=True)
                except GoalStop as exc:
                    result['restoration_budget_stop']=str(exc);break
                checked,checked_frames=observe_resilient('restore_'+str(recovery)+'_revalidate')
                validate_plan_reference(context,recovery_plan,checked,checked_frames,now=clock(),rules=restore_rules)
                if not candidate['input_route']:cp,frames=checked,checked_frames;break
                try:reserve_route(candidate,'restore_best')
                except GoalStop as exc:
                    result['restoration_budget_stop']=str(exc);break
                restore_fresh=checked;route=candidate['input_route']
                for index,gesture in enumerate(route):
                    cp,frames,feedback=submit(gesture,
                        'restore_'+str(recovery) if index==0 else 'restore_'+str(recovery)+'_step_'+str(index),
                        restore_fresh,'restore_best',visual_required=index==len(route)-1)
                    if (current and current.get('frames') and assess_feedback(context,cp,frames,rules)['screenshot_verified']
                            and observed_quality(cp['client_hex'],rules)<observed_quality(best_observed['checkpoint']['client_hex'],rules)):
                        best_observed=copy.deepcopy(current)
                    if feedback['observed_target_accepted']:
                        result.update(accepted=True,stop_reason='target_observed');break
                    suffix=route[index+1:]
                    if suffix and result['steps'][-1].get('model_response_warning'):
                        # Continue the already admitted suffix from actual
                        # native feedback. Residuals do not trigger another
                        # global search or repeat a completed wheel leg.
                        guard()
                        replay=replay_native_route(cp['pose'],suffix,geometry,settings,
                            wheel_delta_per_step=1.,sample_policy='all_recorded_points')
                        audit=audit_candidate_endpoint(context,cp,restore_rules,dict(
                            input_route=copy.deepcopy(suffix),final_pose=replay['final_pose'],
                            prediction=score_native_pose(session,replay['final_pose'],restore_rules),
                            needed=_needed(suffix,3.,.5),source='actual_feedback_restore_suffix'))
                        result['steps'][-1]['remaining_route_audit']=dict(
                            reference_pose=cp['pose'],final_pose=audit['final_pose'],
                            prediction=audit['prediction'],continued=True,
                            target_prediction_changed=not bool(audit['prediction']['predicted_accepted']))
                        emit('route_revalidated',remaining_gestures=len(suffix),reference_pose=cp['pose'],
                            predicted_colors=audit['prediction']['colors'],purpose='restore_best')
                    restore_fresh=cp
                if result.get('accepted'):break
                # A return is complete only when its actual HEX is independently
                # visible at the final endpoint; native-only hits remain reads.
                if frames and assess_feedback(context,cp,frames,restore_rules)['observed_target_accepted']:break
        if result['stop_reason']=='compromise_observed':protected_refinement()
        try:candidate_choices()
        except Exception:
            # A cancelled or rebound waiting session cannot certify its cached
            # checkpoint as current. Preserve it only as last measured evidence.
            if candidate_choice is not None and current is not None:
                result['last_verified_candidate_colors']=current['checkpoint']['client_hex']
                result['last_verified_candidate']=copy.deepcopy(current)
                current=None
            raise
    except GoalStop as exc:result['stop_reason']=str(exc)
    except InterruptedError as exc:result.update(stop_reason='interrupted',error=str(exc))
    except TimeoutError as exc:result.update(stop_reason='insufficient_time',error=str(exc))
    except (ValueError,OSError,RuntimeError,KeyError) as exc:
        result.update(stop_reason='observation_failed',error=type(exc).__name__+': '+str(exc))
    except Exception as exc:
        result.update(stop_reason='internal_error',error=type(exc).__name__+': '+str(exc),
                      error_traceback=traceback.format_exc())
    finally:
        try:io.release()
        except Exception as exc:result['release_error']=str(exc)
    if current is not None and current.get('frames'):
        score=score_codes(current['checkpoint']['client_hex'],rules)
        result['screenshot_verified']=assess_feedback(context,current['checkpoint'],current['frames'],rules)['screenshot_verified'] if context else False
        result.update(verified=True,actual_colors=score['colors'],actual_deltas=score['deltas'],
            target_exact=score['target_exact'],current=current,remaining_seconds=current['frames'][-1]['remaining_seconds'])
        if candidate_choice is not None:
            result['accepted']=bool(score['accepted'] and result['screenshot_verified'])
            result['actual_colors']=list(current['checkpoint']['client_hex'])
        if candidate_choice is not None:
            result['current_candidate_id']=next((candidate_id(batch_id,row['actual_colors']) for row in candidate_rows
                if row['actual_colors']==current['checkpoint']['client_hex']),None)
        if best_observed is not None:
            result.update(best_actual_colors=best_observed['checkpoint']['client_hex'],
                best_current=observed_quality(score['colors'],rules)<=observed_quality(best_observed['checkpoint']['client_hex'],rules))
            result['restored']=(bool(result['best_current'] and result['screenshot_verified'])
                if result.get('restoration_rounds') else None)
    else:
        result.update(verified=False,accepted=False,target_exact=False,
            actual_colors=[None]*count,actual_deltas=[None]*count,current=None)
        if current is not None:
            result['native_current']=current
            score=score_codes(current['checkpoint']['client_hex'],rules)
            result.update(actual_colors=score['colors'],actual_deltas=score['deltas'],
                screenshot_verified=False)
            if candidate_choice is not None:result['actual_colors']=list(current['checkpoint']['client_hex'])
    result.update(elapsed_seconds=max(0.,clock()-start),effective_deadline=end)
    result['outcome']=('matched' if result['accepted'] else 'compromise' if result['stop_reason'] in ('compromise_observed','user_candidate_observed')
        and result['verified'] else 'not_found' if result['stop_reason']=='not_found_in_budget' else 'stopped')
    values=[v for v in result['actual_deltas'] if v is not None]
    result.update(maximum=max(values) if values else None,average=sum(values)/len(values) if values else None)
    return result
