"""Explicit Windows callbacks for the per-session atlas service.

Acquisition waits for the user to enter the timed dye screen manually. The
adapter never clicks a dye-entry control, so starting the tool cannot consume
a dye.
"""
from pathlib import Path
import time
import uuid
from contextlib import nullcontext
import numpy as np
from live_atlas_capture import acquire
from atlas_adapter import build_from_capture
from atlas_execution import CandidateBatch, Context, execute_candidate, reposition_budget, verify_result
from atlas_service import AtlasCallbacks, _protected_route
from atlas_runtime import Adapter
from workflow_budget import earliest_deadline
from atlas_pose import homogeneous,candidate_pose,pose_fields
from atlas_replan import reachable_candidates, bind_nearby_zoom_detents
from atlas_pose_scoring import rescore_candidate
from atlas_bound_route import bind_candidate
from candidate_ranking import candidate_rank,candidate_quality
from atlas_similarity import select_color_candidates
from atlas_stage_budget import ExecutionStageBudget
from execution_diagnostics import execution_diagnostics
from platform_win import Interrupted


def _automatic_route_allowed(row, budget=None):
    """Return whether a bound route may be sent by the automatic path.

    A forecast can be geometrically valid while the game input response is
    still unknown.  Translation has a directly measured response in the
    current workflow, but rotation and wheel routes need the explicit live
    response certificate.  Keep unverified transform rows in diagnostics and
    suppress them before constructing the executable batch.
    """
    budget = budget or row.get('execution_budget') or {}
    actions = budget.get('actions') or {}
    transforms = int(actions.get('rotate', 0) or 0) or int(actions.get('wheel', 0) or 0)
    stability = row.get('route_stability') or {}
    # A few offline callers provide already-bound diagnostic rows without the
    # production stability schema. Preserve those fixtures and low-level
    # simulations; only rows carrying the schema are subject to publication
    # gates.
    if 'passed' not in stability:
        return True
    if not bool(stability.get('passed', False)):
        return False
    if not transforms:
        # Translation routes are measured directly by the current game pose.
        # They can therefore remain executable even when their colour sample
        # is a labelled compromise (the service reports that status).
        return bool(stability.get('samples_complete', True))
    route = row.get('planned_route') or {}
    return bool(stability.get('response_profile_verified') and
                route.get('game_response_verified') and
                stability.get('landing_safe', row.get('landing_safe', False)))


def _candidate_is_no_worse(replacement, current, *, maximum_slack=1.0):
    """Reject a measured-pose fallback that materially worsens the target.

    A replan is allowed to trade a tiny amount of predicted colour error for
    a route that is actually executable.  It must not silently replace the
    current route with a much worse compromise, which was the source of the
    visible ``gets worse after every action`` behaviour.
    """
    if replacement is None:
        return False
    old=candidate_quality(current)
    new=candidate_quality(replacement)
    # Accepted/family safety tiers remain authoritative.  For two candidates
    # in the same tier compare the worst predicted Delta-E with a small
    # allowance for resampling noise; lower ranked fields are only tie-breaks.
    if bool(new[0]) != bool(old[0]):
        return not bool(new[0])
    try:
        old_max=float(old[1]);new_max=float(new[1])
    except (TypeError,ValueError):
        return False
    return new_max <= old_max + float(maximum_slack)


def acquire_current(_owner, _rules, capture_dir, entry=None, strategy='grid', entry_size=None, **context):
    folder=Path(capture_dir)
    artifact=acquire(folder,None,strategy=strategy,
                     stop=_owner.stop,target=context.get('target'),
                      activate=bool(context.get('activate',False)),entry_size=entry_size,
                      emit=getattr(_owner,'event',None),row_stagger=.05)
    artifact['progress']=lambda **data:_owner.event('atlas_progress',**data)
    return artifact


def build_current(capture, rules, **_context):
    game=capture['game']
    if capture.get('deadline') is None:raise RuntimeError('Game countdown deadline is unavailable')
    deadline=earliest_deadline(capture['deadline'],game.until,_context.get('selection_deadline'))
    if deadline is None:raise RuntimeError('Game countdown deadline is unavailable')
    game.until=deadline
    game.check()
    if time.monotonic()>=deadline:raise RuntimeError('Workflow deadline expired before build')
    report=build_from_capture(capture,rules)
    game.check()
    if time.monotonic()>=deadline:raise RuntimeError('Workflow deadline expired during build')
    report['selection_deadline']=deadline
    artifact=capture
    rows=report.get('candidates',[])
    if not report.get('quality_gate',{}).get('passed'):return report
    game=artifact['game'];scene=artifact['scene']
    runtime=report.get('runtime',{})
    if runtime.get('atlas') is None:
        raise RuntimeError('Atlas is unavailable for route endpoint scoring')
    prepared=[];route_diagnostics=[]
    binding_started=time.perf_counter()
    # Candidate route binding can be expensive and must not consume the time
    # reserved for an actual attempt, return, and two-frame verification.
    # These estimates are deliberately conservative and diagnostic only; the
    # hard game deadline and per-route budget remain authoritative.
    budget_guard_enabled=bool(_context.get('enable_binding_budget_guard', False))
    finish_reserve=float(_context.get('finish_reserve_seconds',15.0))
    minimum_attempt_seconds=float(_context.get('minimum_attempt_seconds',8.0))
    binding_seconds_per_candidate=float(_context.get('binding_seconds_per_candidate',.5))
    if min(finish_reserve,minimum_attempt_seconds,binding_seconds_per_candidate)<0:
        raise ValueError('Search budget estimates must be non-negative')
    binding_stop_reason=None
    unbound_candidate_count=0
    progress=capture.get('progress')
    for index,row in enumerate(rows,1):
        game.check()
        remaining=deadline-time.monotonic()
        required=(finish_reserve+minimum_attempt_seconds+
                  binding_seconds_per_candidate)
        if budget_guard_enabled and remaining<=required:
            binding_stop_reason='finish_and_attempt_reserve'
            unbound_candidate_count=len(rows)-index+1
            break
        if progress:progress(stage='search',current=index,total=len(rows))
        candidate_started=time.perf_counter()
        try:
            ready,budget=bind_candidate(row,runtime['atlas'],runtime['capture_offset'],
                scene.board,scene.markers,rules,time.monotonic(),deadline,check=game.check,
                require_stable=True,allow_color_compromise=True)
        except (ValueError,TypeError,KeyError) as exc:
            ready=None;budget=dict(allowed=False,reason='invalid_route',detail=str(exc))
        route_diagnostics.append(dict(candidate_id=row['id'],
            binding_seconds=time.perf_counter()-candidate_started,
            budget={k:v for k,v in budget.items() if k!='input_route'}))
        if ready is not None:prepared.append(ready)
    # A missing game response profile is an evidence gap, not a reason to
    # spend a dye on a guessed rotation/zoom endpoint.  Keep these rows in
    # route_diagnostics for the experiment report, but only translations may
    # enter the automatic executable batch until the profile is verified.
    suppressed_rows=[]
    unverified_transform_rows=[]
    unstable_landing_rows=[]
    unstable_route_rows=[]
    for row in prepared:
        if _automatic_route_allowed(row):
            continue
        actions=(row.get('execution_budget') or {}).get('actions') or {}
        transforms=int(actions.get('rotate',0) or 0) or int(actions.get('wheel',0) or 0)
        stability=row.get('route_stability') or {}
        if not stability.get('passed',False):
            reason='unstable_route';unstable_route_rows.append(row)
        elif transforms and not stability.get('response_profile_verified',False):
            reason='unverified_transform_response';unverified_transform_rows.append(row)
        elif transforms and not stability.get('landing_safe',row.get('landing_safe',False)):
            reason='unstable_landing';unstable_landing_rows.append(row)
        else:
            reason='unstable_route';unstable_route_rows.append(row)
        row.setdefault('route_stability',{})['automatic_execution_allowed']=False
        row['automatic_execution_blocked_reason']=reason
        suppressed_rows.append(row)
    prepared=[row for row in prepared if _automatic_route_allowed(row)]
    def _stable_translation(row):
        actions=(row.get('execution_budget') or {}).get('actions') or {}
        stability=row.get('route_stability') or {}
        return (int(actions.get('rotate',0))==0 and int(actions.get('wheel',0))==0
                and ('passed' not in stability or bool(stability.get('passed')))
                and (bool(row.get('family_consistent')) or 'family_consistent' not in row)
                and (bool(stability.get('quality_preferred')) or 'quality_preferred' not in stability))

    # Translation alternatives are useful fallback routes. Their existence
    # does not invalidate separately bound rotate/zoom endpoints: compare
    # every supported endpoint using the same color and landing-risk score.
    safe_translations=[row for row in prepared if _stable_translation(row)]
    has_route_metadata=any('execution_budget' in row for row in prepared)
    needs_translation_fallback=(not prepared or bool(suppressed_rows) or
                                (has_route_metadata and not safe_translations))
    if needs_translation_fallback and binding_stop_reason is None and time.monotonic()<deadline:
        # No transform route survived. Retain the already captured pose and
        # search its atlas for integer translations instead of publishing an
        # unattainable continuous candidate or throwing away the session.
        if progress:progress(stage='search')
        # Limit this last search to translations that fit the actual remaining
        # countdown; distant same-family points must not crowd out nearby
        # executable compromises. There is no elapsed-workflow time limit.
        span=min(scene.board[2]-scene.board[0],scene.board[3]-scene.board[1])*.16
        max_move=min(10.,max(0.,(deadline-time.monotonic()-5.)/1.2))*span
        fallback=reachable_candidates(runtime['atlas'],runtime['capture_offset'],
            homogeneous([[1,0,0],[0,1,0]]),scene.markers,scene.board,rules,0,
            check=game.check,max_move=max_move)
        first_id=max((row['id'] for row in rows),default=-1)+1
        for index,row in enumerate(fallback):
            ready,budget=bind_candidate(dict(row,id=first_id+index),runtime['atlas'],runtime['capture_offset'],
                scene.board,scene.markers,rules,time.monotonic(),deadline,check=game.check,
                require_stable=True,allow_color_compromise=True)
            route_diagnostics.append(dict(candidate_id=first_id+index,fallback=True,
                budget={k:v for k,v in budget.items() if k!='input_route'}))
            if ready is not None:
                if _automatic_route_allowed(ready):
                    prepared.append(ready)
                else:
                    suppressed_rows.append(ready)
                    reason='unstable_route'
                    stability=ready.get('route_stability') or {}
                    actions=(ready.get('execution_budget') or {}).get('actions') or {}
                    transforms=int(actions.get('rotate',0) or 0) or int(actions.get('wheel',0) or 0)
                    if transforms and not stability.get('response_profile_verified',False):
                        unverified_transform_rows.append(ready);reason='unverified_transform_response'
                    elif transforms and not stability.get('landing_safe',ready.get('landing_safe',False)):
                        unstable_landing_rows.append(ready);reason='unstable_landing'
                    else:
                        unstable_route_rows.append(ready)
                    ready.setdefault('route_stability',{})['automatic_execution_allowed']=False
                    ready['automatic_execution_blocked_reason']=reason
        safe_translations=[row for row in prepared if _stable_translation(row)]
    # Keep supported endpoints available to the shared quality/risk ordering.
    # A boolean family boundary must not discard a more balanced or reliable
    # endpoint before its actual bound route is compared.
    same_family_rows=[row for row in prepared if row.get('family_consistent')]
    # Keep a bounded route representative for the best family-consistent
    # colour tuples as well as the balanced default.  The previous plain
    # de-duplication ran after binding and could discard every same-family
    # option, leaving only cross-family compromises for a multi-region run.
    rows=select_color_candidates(prepared,rules,8,preserve_routes=True)
    report['candidates']=rows
    report['search_diagnostics']=dict(report.get('search_diagnostics') or {},route_binding=route_diagnostics,
        binding_budget_guard_enabled=budget_guard_enabled,
        route_binding_seconds=time.perf_counter()-binding_started,
        route_binding_stop_reason=binding_stop_reason,
        route_binding_unprocessed_count=unbound_candidate_count,
        route_binding_budget=dict(finish_reserve_seconds=finish_reserve,
            minimum_attempt_seconds=minimum_attempt_seconds,
            estimated_next_binding_seconds=binding_seconds_per_candidate),
        stability_required=True,stable_route_count=len(rows),
        transform_routes_suppressed=bool(unverified_transform_rows or unstable_landing_rows),
        transform_routes_suppressed_count=len(unverified_transform_rows),
        suppressed_unverified_transform_count=len(unverified_transform_rows),
        suppressed_unstable_landing_count=len(unstable_landing_rows),
        suppressed_unstable_route_count=len(unstable_route_rows),
        stable_translation_count=len(safe_translations),
        rejected_unstable_route_count=sum(d.get('budget',{}).get('reason') in
                                          ('unstable_landing','unstable_route')
                                          for d in route_diagnostics),
        cross_family_fallback_count=sum(row.get('cross_family_fallback',False) for row in rows),
        same_family_search_count=len(same_family_rows))
    if not rows:return report
    context=Context(uuid.uuid4().hex,tuple(game.geometry()),tuple(scene.board),
                    tuple(map(tuple,scene.markers)))
    batch=CandidateBatch(rows,context,deadline)
    adapter=Adapter(game,scene,context.session)
    # Failed input is handled as a read-only recovery observation.  The
    # executor never retries from an unverified pose and never reports that
    # observation as a successful candidate.
    adapter.recovery_enabled=True
    report.update(batch=batch,batch_id=batch.id,board=tuple(scene.board),
                  markers=tuple(map(tuple,scene.markers)),
                  selection_deadline=deadline,adapter=adapter,
                  reference=artifact['image'],rules=rules,
                  capture_folder=Path(artifact['folder']) if artifact.get('folder') else None)
    return report


def observe_current(owner, captured, rules, *, reason=None, selection_deadline=None, **_context):
    """Read the current board after a read-only multi-region early exit.

    No atlas, route, motion registration or mouse input is used here.  The
    capture's own game deadline remains authoritative; ordinary OCR failures
    produce an explicit unknown observation rather than a guessed colour.
    """
    game=captured.get('game') if isinstance(captured,dict) else None
    scene=captured.get('scene') if isinstance(captured,dict) else None
    if game is None or scene is None:
        return None
    game.check()
    observed_frames=0
    def unknown(detail):
        return dict(candidate_id=None,verified=False,accepted=False,observed_accepted=False,
                    actual_colors=[None]*3,actual_deltas=[None]*3,maximum=None,average=None,
                    predicted_colors=[None]*3,predicted_deltas=[None]*3,
                    actual_pose=None,marker_errors=None,pose_reliable=False,
                    positioning_complete=False,recovered=True,best_result_current=False,
                    recovery_reason=reason,observation_error=detail,
                    observed_frames=observed_frames)
    try:
        limits=[captured.get('deadline'),captured.get('game_deadline'),selection_deadline]
        game_limit=getattr(game,'until',None)
        if game_limit is not None and np.isfinite(game_limit):limits.append(game_limit)
        deadline=earliest_deadline(*limits)
        if deadline is None:return unknown('deadline_unavailable')
        if time.monotonic()>=deadline:
            raise Interrupted('游戏倒计时已到安全截止时间。')
        observation_deadline=min(deadline-.25,time.monotonic()+3.5)
        if observation_deadline<=time.monotonic():return unknown('insufficient_observation_time')
        budget=ExecutionStageBudget(observation_deadline,observation_deadline,deadline,
                                    clock=time.monotonic)
        adapter=Adapter(game,scene,'early-observation')
        adapter.enabled=[bool(rule.get('enabled')) for rule in rules]
        with adapter.execution_scope(budget):
            first=adapter.capture();observed_frames=1
            codes_first=adapter.read_codes(first)
            adapter.pause(.15)
            second=adapter.capture();observed_frames=2
            codes_second=adapter.read_codes(second)
            adapter.check_observation()
    except Exception as exc:
        if exc.__class__.__name__ in ('Interrupted','InterruptedError'):raise
        # OCR/capture failures may coincide with F9, focus/geometry loss or
        # the hard game deadline. Recheck safety before treating the failure
        # as an ordinary unknown observation; this sends no new input.
        game.check()
        return unknown(str(exc))
    stable=all((not rules[i].get('enabled')) or
               (codes_first[i] is not None and codes_first[i]==codes_second[i])
               for i in range(len(rules)))
    if not stable:
        return unknown('unstable_or_unreadable_hex')
    observed=verify_result(dict(id=None,colors=[None]*len(scene.cards),
                                deltas=[None]*len(scene.cards)),codes_second,rules)
    return dict(observed,candidate_id=None,actual_pose=None,marker_errors=None,
                pose_reliable=False,positioning_complete=False,recovered=True,
                accepted=False,observed_accepted=bool(observed.get('accepted')),
                best_result_current=False,
                recovery_reason=reason,observed_frames=2,
                predicted_colors=[None]*len(scene.cards),predicted_deltas=[None]*len(scene.cards),
                compromise=not bool(observed.get('accepted')))


def _execute_recorded(owner,report,candidate,rules,batch,reference,reservation='legacy',return_guard=None):
    events=[];result=None;failure=None
    adapter=report['adapter']
    reference_pose=np.eye(3) if report.get('actual_pose') is None else homogeneous(report['actual_pose'])
    if callable(return_guard):
        def guarded_return(actual, upcoming, projected_pose=None):
            current_global=homogeneous(actual) @ reference_pose
            projected_global=(None if projected_pose is None else
                              homogeneous(projected_pose) @ reference_pose)
            return return_guard(current_global, upcoming,
                                projected_pose=projected_global)
        adapter.return_guard=guarded_return
    else:
        adapter.return_guard=None
    adapter.enabled=[bool(rule['enabled']) for rule in rules]
    stage_budget=ExecutionStageBudget.for_attempt(batch.deadline,
        report.get('selection_deadline',batch.deadline),clock=time.monotonic)
    route_check=getattr(adapter,'check_positioning',adapter.check)
    runtime=report.get('runtime',{})
    if runtime.get('atlas') is not None:
        def rebind(actual,current,active_rules):
            route_check()
            from atlas_pose import relative_candidate
            move=relative_candidate(current,actual,batch.context.board)
            reference=np.eye(3) if report.get('actual_pose') is None else homogeneous(report['actual_pose'])
            try:
                ready,_budget=bind_candidate(move,runtime['atlas'],runtime['capture_offset'],
                    batch.context.board,batch.context.markers,active_rules,time.monotonic(),
                    batch.deadline,reference_pose=actual@reference,check=route_check,
                    require_stable=True,allow_color_compromise=True)
                if (ready is None and _budget.get('reason')=='unreachable_scale'
                        and not current.get('protect_observed_result')):
                    ready,_budget=bind_nearby_zoom_detents(current,actual,
                        runtime['atlas'],runtime['capture_offset'],batch.context.board,
                        batch.context.markers,active_rules,time.monotonic(),batch.deadline,
                        reference_pose=reference,wheel_direction=int(current.get('execution_zoom_direction',0)),
                        check=route_check,require_stable=True,allow_color_compromise=True)
            except (ValueError,TypeError,KeyError):
                return None
            route_check()
            # Color-family boundaries do not invalidate a supported route.
            # Optional trials still require a reliable return to the observed
            # checkpoint; compare their rescored quality in the service.
            # Rebinding is still an automatic input path.  Do not let a
            # measured-pose correction reintroduce an unverified transform
            # after the initial publication filter removed those routes.
            if ready is not None and not _automatic_route_allowed(ready, _budget):
                ready=None
            protected=(_protected_route(ready,_budget) if ready is not None else False)
            if current.get('user_selected_route') and ready is not None:
                stability=ready.get('route_stability') or {}
                protected=bool(_budget.get('allowed') and stability.get('passed') and stability.get('samples_complete',True))
            if current.get('protect_observed_result') and not protected:
                return None
            if ready is not None and current.get('user_selected_route'):
                ready.update(user_selected_route=True,protect_observed_result=True)
            return ready
        adapter.rebind=rebind
        def replan(actual,current,active_rules):
            route_check()
            if current.get('protect_observed_result'):return None
            span=min(batch.context.board[2]-batch.context.board[0],
                     batch.context.board[3]-batch.context.board[1])*.16
            max_move=min(10.,max(0.,(batch.deadline-time.monotonic()-5.)/1.2))*span
            rows=reachable_candidates(runtime['atlas'],runtime['capture_offset'],actual,
                 batch.context.markers,batch.context.board,active_rules,current['id'],
                 check=route_check,reference_pose=report.get('actual_pose'),max_move=max_move)
            from atlas_pose import relative_candidate
            prepared=[]
            for row in rows:
                route_check()
                move=relative_candidate(row,actual,batch.context.board)
                reference=np.eye(3) if report.get('actual_pose') is None else homogeneous(report['actual_pose'])
                try:
                    ready,_budget=bind_candidate(move,runtime['atlas'],runtime['capture_offset'],
                        batch.context.board,batch.context.markers,active_rules,time.monotonic(),
                        batch.deadline,reference_pose=actual@reference,check=route_check,
                        require_stable=True,allow_color_compromise=True)
                except (ValueError,TypeError,KeyError):
                    ready=None
                if ready is not None and not _automatic_route_allowed(ready, _budget):
                    ready=None
                if ready is not None:
                    # A measured-pose fallback may already be at the candidate
                    # rotation/zoom endpoint. Do not replay stale transform
                    # gestures; execute only residual translation.
                    try:
                        from atlas_pose import pose_fields
                        residual_fields = pose_fields(
                            relative_candidate(ready, actual, batch.context.board),
                            batch.context.board)
                        if (abs(float(residual_fields.get('angle', 0.0))) <= 0.35 and
                                abs(float(residual_fields.get('scale', 1.0)) - 1.0) <= 0.003):
                            ready = dict(ready, planned_route=None,
                                         prediction_pose_source='measured_fallback_translation')
                    except (TypeError, ValueError, KeyError):
                        pass
                    prepared.append(ready)
            route_check()
            if not prepared:
                return None
            replacement=min(prepared,key=candidate_rank)
            # Keep the measured-pose fallback monotonic.  A route that is
            # merely executable but clearly worse than the current proposal
            # is unsafe from a user perspective; stop and let recovery report
            # the measured result instead of degrading it repeatedly.
            return replacement if _candidate_is_no_worse(replacement,current) else None
        adapter.replan=replan
        adapter.rescore=lambda actual,current,active_rules:rescore_candidate(
            runtime['atlas'],runtime['capture_offset'],current,actual,
            batch.context.markers,batch.context.board,active_rules,
            pose_source='measured_final_pose',reference_pose=report.get('actual_pose'),
            check=getattr(adapter,'check_observation',adapter.check))
    else:
        # The adapter is reused across choices; do not retain a stale closure.
        adapter.replan=None
        adapter.rebind=None
        adapter.rescore=None
    for name in ('last_motion_before','last_motion_after','last_motion_diagnostics'):
        if hasattr(adapter,name):setattr(adapter,name,None)
    def event(kind,data):
        events.append(dict(kind=kind,**data));owner.event(kind,**data)
    try:
        scope=(adapter.execution_scope(stage_budget) if hasattr(adapter,'execution_scope')
               else nullcontext())
        with scope:
            result=execute_candidate(adapter,batch,batch.id,candidate['id'],reference,rules,
                emit=event,clock=time.monotonic,reservation=reservation,verified_kind=None,
                stage_budget=stage_budget)
        return result
    except Exception as exc:
        failure=str(exc);raise
    finally:
        # Use already captured frames, including the last failed measurement.
        # No extra game access is made after F9, focus loss or expiry.
        if report.get('capture_folder'):
            try:
                folder=Path(report['capture_folder'])/'execution'
                attempt=report.get('execution_attempt',0)+1;report['execution_attempt']=attempt
                prefix=f'attempt-{attempt:02d}'
                frames={}
                frame=getattr(report['adapter'],'last_frame',None)
                if frame is not None:frames[prefix+'.png']=frame
                motion_frames={}
                for label in ('before','after'):
                    frame=getattr(adapter,'last_motion_'+label,None)
                    if frame is not None:
                        filename=prefix+'-motion-'+label+'.png'
                        frames[filename]=frame
                        motion_frames[label]=filename
                data=dict(candidate=candidate,rules=rules,result=result,error=failure,events=events,
                          code_read_totals=getattr(adapter,'code_read_stats',None),
                          last_registration=getattr(adapter,'last_motion_diagnostics',None),
                          motion_frames=motion_frames,
                          previous_actual_pose=report.get('actual_pose'),
                          pose_scope='Relative to previous verified frame or acquisition frame')
                report['diagnostic_write']=execution_diagnostics.submit(folder,prefix,data,frames)
            except Exception:pass  # Diagnostic storage cannot interrupt dyeing.


def default_current(owner, report, candidate, rules, **_context):
    result=_execute_recorded(owner,report,candidate,rules,report['batch'],report['reference'],
                             reservation='default')
    report['pose_reference']=report['adapter'].verified_frame
    report['actual_pose']=result['actual_pose']
    # Prepare integer translations at the recovered pose. The service owns
    # the measured checkpoint and reserves a return route before any trial;
    # this callback must not move again and discard that observation.
    if (result.get('recovered') and result.get('pose_reliable') and
            not result.get('observed_accepted') and report.get('runtime',{}).get('atlas') is not None):
        try:
            adapter=report['adapter'];adapter.check()
            owner.event('atlas_progress',stage='search')
            runtime=report['runtime'];board=report['board'];deadline=report['selection_deadline']
            span=min(board[2]-board[0],board[3]-board[1])*.16
            max_move=min(10.,max(0.,(deadline-time.monotonic()-5.)/1.2))*span
            rows=reachable_candidates(runtime['atlas'],runtime['capture_offset'],np.eye(3),
                report['markers'],board,rules,candidate['id'],check=adapter.check,
                reference_pose=result['actual_pose'],max_move=max_move)
            prepared=[]
            first_id=max((row['id'] for row in report.get('candidates',[candidate])),default=0)+1
            for row in sorted(rows,key=candidate_rank):
                if candidate_quality(row)>=candidate_quality(result):continue
                ready,budget=bind_candidate(row,runtime['atlas'],runtime['capture_offset'],
                    board,report['markers'],rules,time.monotonic(),deadline,
                    reference_pose=result['actual_pose'],check=adapter.check,
                    require_stable=True,allow_color_compromise=True)
                if ready is None or candidate_quality(ready)>=candidate_quality(result):continue
                endpoint=candidate_pose(ready,board)@homogeneous(result['actual_pose'])
                lifted=dict(ready,**pose_fields(endpoint,board),id=first_id+len(prepared))
                lifted.pop('planned_route',None);lifted.pop('execution_budget',None)
                prepared.append(lifted)
                if len(prepared)>=8:break
            report['recovery_candidates']=prepared
        except Exception as exc:
            if exc.__class__.__name__ in ('Interrupted','InterruptedError'):raise
            owner.event('atlas_recovery_unavailable',detail=str(exc),
                message='当前颜色已保留，未能进一步调整。')
    return result


def prepare_choice(owner,report,candidate,rules,**context):
    """Read-only route binding for a trial and its measured checkpoint return."""
    adapter=report['adapter'];adapter.check()
    deadline=earliest_deadline(report['selection_deadline'],context.get('selection_deadline'))
    runtime=report.get('runtime',{})
    if runtime.get('atlas') is None:return None,dict(allowed=False,reason='atlas_unavailable')
    source=context.get('reference_pose',report.get('actual_pose'))
    row,budget=bind_candidate(candidate,runtime['atlas'],runtime['capture_offset'],
        adapter.context().board,adapter.context().markers,rules,time.monotonic(),deadline,
        reference_pose=source,check=adapter.check,require_stable=True,allow_color_compromise=True)
    if row is not None:row['prepared_reference_pose']=homogeneous(source)[:2].tolist()
    return row,budget


def choice_current(owner, report, candidate, rules, **_context):
    # Service rebases the complete target matrix from the last measured pose.
    # Retain the verified frame so manual movement during selection is caught.
    adapter=report['adapter'];adapter.check()
    deadline=earliest_deadline(report['selection_deadline'],_context.get('selection_deadline'))
    if time.monotonic()>=deadline:raise RuntimeError('Workflow deadline expired before choice')
    reference=report['pose_reference'];row=dict(candidate)
    runtime=report.get('runtime',{})
    if row.get('protect_observed_result'):
        if not np.allclose(homogeneous(row['prepared_reference_pose']),
                           homogeneous(report['actual_pose']),rtol=0,atol=1e-8):
            raise RuntimeError('Prepared route reference changed')
        budget=reposition_budget(row,time.monotonic(),deadline,adapter.context().board,
                                 markers=adapter.context().markers)
        valid=_protected_route(row,budget)
        if row.get('user_selected_route'):
            stability=row.get('route_stability') or {}
            valid=bool(budget.get('allowed') and stability.get('passed') and stability.get('samples_complete',True))
        if not valid:raise RuntimeError('Protected route is no longer available')
    elif runtime.get('atlas') is not None:
        row,budget=bind_candidate(row,runtime['atlas'],runtime['capture_offset'],
            adapter.context().board,adapter.context().markers,rules,time.monotonic(),deadline,
            reference_pose=report.get('actual_pose'),check=adapter.check,
            require_stable=True,allow_color_compromise=True)
        if row is None:raise RuntimeError('Selected route has no supported endpoint: '+budget['reason'])
        owner.event('atlas_prediction_updated',candidate_id=row['id'],
            candidate=row,colors=row['colors'],deltas=row['deltas'],prediction_pose_source=row['prediction_pose_source'])
    batch=CandidateBatch([row],adapter.context(),deadline)
    result=_execute_recorded(owner,report,row,rules,batch,reference,return_guard=_context.get('return_guard'))
    if result.get('actual_pose') is not None:
        result['actual_pose']=(homogeneous(result['actual_pose'])@homogeneous(report['actual_pose']))[:2].tolist()
    if result.get('best_result', {}).get('actual_pose') is not None:
        result['best_result']['actual_pose']=(
            homogeneous(result['best_result']['actual_pose']) @
            homogeneous(report['actual_pose']))[:2].tolist()
    report['pose_reference']=adapter.verified_frame
    report['actual_pose']=result['actual_pose']
    return result


def callbacks(capture_dir, entry=None, strategy='grid', entry_size=None):
    """Create explicit live callbacks; nothing is enabled by importing this."""
    return AtlasCallbacks(
        acquire=lambda owner,rules,**ctx:acquire_current(
            owner,rules,capture_dir,entry,strategy=strategy,
            entry_size=entry_size,**ctx),
        build=build_current,default=default_current,choice=choice_current,prepare=prepare_choice,
        observe_current=observe_current)
