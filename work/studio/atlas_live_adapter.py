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
from atlas_execution import CandidateBatch, Context, execute_candidate, reposition_budget
from atlas_service import AtlasCallbacks, _protected_route
from atlas_runtime import Adapter
from workflow_budget import earliest_deadline
from atlas_pose import homogeneous,candidate_pose,pose_fields
from atlas_replan import reachable_candidates
from atlas_pose_scoring import rescore_candidate
from atlas_bound_route import bind_candidate
from candidate_ranking import candidate_rank,candidate_quality
from atlas_stage_budget import ExecutionStageBudget
from execution_diagnostics import execution_diagnostics


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
    progress=capture.get('progress')
    for index,row in enumerate(rows,1):
        game.check()
        if progress:progress(stage='search',current=index,total=len(rows))
        try:
            ready,budget=bind_candidate(row,runtime['atlas'],runtime['capture_offset'],
                scene.board,scene.markers,rules,time.monotonic(),deadline,check=game.check,
                require_stable=True,allow_color_compromise=True)
        except (ValueError,TypeError,KeyError) as exc:
            ready=None;budget=dict(allowed=False,reason='invalid_route',detail=str(exc))
        route_diagnostics.append(dict(candidate_id=row['id'],
            budget={k:v for k,v in budget.items() if k!='input_route'}))
        if ready is not None:prepared.append(ready)
    if not any(row.get('family_consistent') for row in prepared) and time.monotonic()<deadline:
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
            if ready is not None:prepared.append(ready)
    # Keep supported endpoints available to the shared quality/risk ordering.
    # A boolean family boundary must not discard a more balanced or reliable
    # endpoint before its actual bound route is compared.
    same_family_rows=[row for row in prepared if row.get('family_consistent')]
    rows=[];seen=set()
    for row in sorted(prepared,key=candidate_rank):
        key=tuple(row['colors'])
        if key in seen:continue
        seen.add(key);rows.append(row)
        if len(rows)>=8:break
    report['candidates']=rows
    report['search_diagnostics']=dict(report.get('search_diagnostics') or {},route_binding=route_diagnostics,
        stability_required=True,stable_route_count=len(rows),
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


def _execute_recorded(owner,report,candidate,rules,batch,reference,reservation='legacy'):
    events=[];result=None;failure=None
    adapter=report['adapter']
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
            except (ValueError,TypeError,KeyError):
                return None
            route_check()
            # Color-family boundaries do not invalidate a supported route.
            # Optional trials still require a reliable return to the observed
            # checkpoint; compare their rescored quality in the service.
            if current.get('protect_observed_result') and (ready is None or not _protected_route(ready,_budget)):
                return None
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
                if ready is not None:prepared.append(ready)
            route_check()
            return min(prepared,key=candidate_rank) if prepared else None
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
        if not _protected_route(row,budget):raise RuntimeError('Protected route is no longer available')
    elif runtime.get('atlas') is not None:
        row,budget=bind_candidate(row,runtime['atlas'],runtime['capture_offset'],
            adapter.context().board,adapter.context().markers,rules,time.monotonic(),deadline,
            reference_pose=report.get('actual_pose'),check=adapter.check,
            require_stable=True,allow_color_compromise=True)
        if row is None:raise RuntimeError('Selected route has no supported endpoint: '+budget['reason'])
        owner.event('atlas_prediction_updated',candidate_id=row['id'],
            candidate=row,colors=row['colors'],deltas=row['deltas'],prediction_pose_source=row['prediction_pose_source'])
    batch=CandidateBatch([row],adapter.context(),deadline)
    result=_execute_recorded(owner,report,row,rules,batch,reference)
    if result.get('actual_pose') is not None:
        result['actual_pose']=(homogeneous(result['actual_pose'])@homogeneous(report['actual_pose']))[:2].tolist()
    report['pose_reference']=adapter.verified_frame
    report['actual_pose']=result['actual_pose']
    return result


def callbacks(capture_dir, entry=None, strategy='grid', entry_size=None):
    """Create explicit live callbacks; nothing is enabled by importing this."""
    return AtlasCallbacks(
        acquire=lambda owner,rules,**ctx:acquire_current(
            owner,rules,capture_dir,entry,strategy=strategy,
            entry_size=entry_size,**ctx),
        build=build_current,default=default_current,choice=choice_current,prepare=prepare_choice)
