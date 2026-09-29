"""Explicit Windows callbacks for the per-session atlas service.

Acquisition waits for the user to enter the timed dye screen manually. The
adapter never clicks a dye-entry control, so starting the tool cannot consume
a dye.
"""
from pathlib import Path
import time
import uuid
import json
import numpy as np
from PIL import Image
from live_atlas_capture import acquire
from atlas_adapter import build_from_capture
from atlas_execution import CandidateBatch, Context, execute_candidate, reposition_budget
from atlas_service import AtlasCallbacks, _protected_route
from atlas_runtime import Adapter
from workflow_budget import earliest_deadline
from atlas_pose import homogeneous
from atlas_replan import reachable_candidates
from atlas_pose_scoring import rescore_candidate
from atlas_bound_route import bind_candidate
from candidate_ranking import candidate_rank


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
    if not rows:return report
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
                require_stable=True)
        except (ValueError,TypeError,KeyError) as exc:
            ready=None;budget=dict(allowed=False,reason='invalid_route',detail=str(exc))
        route_diagnostics.append(dict(candidate_id=row['id'],
            budget={k:v for k,v in budget.items() if k!='input_route'}))
        if ready is not None:prepared.append(ready)
    # A same-family route is always preferred.  If the atlas produced no
    # same-family candidate at all, make one explicit second pass that permits
    # the closest cross-family compromises.  This is deliberately separate
    # from the normal pass so a cross-family row can never displace a usable
    # same-family route merely because its Delta-E is a little lower.
    same_family_rows = [row for row in rows if row.get('family_consistent', False)]
    cross_family_rows = [row for row in rows if not row.get('family_consistent', False)]
    cross_family_prepared = []
    if not prepared and not same_family_rows and cross_family_rows and time.monotonic()<deadline:
        for index,row in enumerate(cross_family_rows,1):
            game.check()
            if progress:progress(stage='fallback-search',current=index,total=len(rows))
            try:
                ready,budget=bind_candidate(row,runtime['atlas'],runtime['capture_offset'],
                    scene.board,scene.markers,rules,time.monotonic(),deadline,check=game.check,
                    require_stable=True,allow_cross_family=True)
            except (ValueError,TypeError,KeyError) as exc:
                ready=None;budget=dict(allowed=False,reason='invalid_route',detail=str(exc))
            route_diagnostics.append(dict(candidate_id=row['id'],cross_family=True,
                budget={k:v for k,v in budget.items() if k!='input_route'}))
            if ready is not None:cross_family_prepared.append(ready)
        prepared.extend(cross_family_prepared)
    if not prepared and time.monotonic()<deadline:
        # No transform route survived. Retain the already captured pose and
        # search its atlas for integer translations instead of publishing an
        # unattainable continuous candidate or throwing away the session.
        fallback=reachable_candidates(runtime['atlas'],runtime['capture_offset'],
            homogeneous([[1,0,0],[0,1,0]]),scene.markers,scene.board,rules,0,check=game.check)
        for index,row in enumerate(fallback):
            ready,budget=bind_candidate(dict(row,id=index),runtime['atlas'],runtime['capture_offset'],
                scene.board,scene.markers,rules,time.monotonic(),deadline,check=game.check,
                require_stable=True)
            route_diagnostics.append(dict(candidate_id=index,fallback=True,
                budget={k:v for k,v in budget.items() if k!='input_route'}))
            if ready is not None:prepared.append(ready)
    rows=sorted(prepared,key=candidate_rank)
    report['candidates']=rows
    report['search_diagnostics']=dict(report.get('search_diagnostics') or {},route_binding=route_diagnostics,
        stability_required=True,stable_route_count=len(rows),
        rejected_unstable_route_count=sum(d.get('budget',{}).get('reason') in
                                          ('unstable_landing','unstable_route')
                                          for d in route_diagnostics),
        cross_family_fallback_count=len(cross_family_prepared),
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
    runtime=report.get('runtime',{})
    if runtime.get('atlas') is not None:
        def rebind(actual,current,active_rules):
            from atlas_pose import relative_candidate
            move=relative_candidate(current,actual,batch.context.board)
            reference=np.eye(3) if report.get('actual_pose') is None else homogeneous(report['actual_pose'])
            try:
                ready,_budget=bind_candidate(move,runtime['atlas'],runtime['capture_offset'],
                    batch.context.board,batch.context.markers,active_rules,time.monotonic(),
                    batch.deadline,reference_pose=actual@reference,check=adapter.check,
                    require_stable=True)
            except (ValueError,TypeError,KeyError):
                return None
            # A new route must preserve the family's quality after resampling;
            # otherwise search the measured pose for a fresh compromise.
            if current.get('protect_observed_result') and (ready is None or not _protected_route(ready,_budget)):
                return None
            if ready is not None and ready['family_maximum']<=current.get('family_maximum',0)+1e-7:
                return ready
            return None
        adapter.rebind=rebind
        def replan(actual,current,active_rules):
            if current.get('protect_observed_result'):return None
            rows=reachable_candidates(runtime['atlas'],runtime['capture_offset'],actual,
                 batch.context.markers,batch.context.board,active_rules,current['id'],
                 check=adapter.check,reference_pose=report.get('actual_pose'))
            from atlas_pose import relative_candidate
            for row in rows:
                move=relative_candidate(row,actual,batch.context.board)
                reference=np.eye(3) if report.get('actual_pose') is None else homogeneous(report['actual_pose'])
                try:
                    ready,_budget=bind_candidate(move,runtime['atlas'],runtime['capture_offset'],
                        batch.context.board,batch.context.markers,active_rules,time.monotonic(),
                        batch.deadline,reference_pose=actual@reference,check=adapter.check,
                        require_stable=True)
                except (ValueError,TypeError,KeyError):
                    ready=None
                if ready is not None:return ready
            return None
        adapter.replan=replan
        adapter.rescore=lambda actual,current,active_rules:rescore_candidate(
            runtime['atlas'],runtime['capture_offset'],current,actual,
            batch.context.markers,batch.context.board,active_rules,
            pose_source='measured_final_pose',reference_pose=report.get('actual_pose'),
            check=adapter.check)
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
        result=execute_candidate(report['adapter'],batch,batch.id,candidate['id'],reference,rules,
                                 emit=event,clock=time.monotonic,reservation=reservation,verified_kind=None)
        return result
    except Exception as exc:
        failure=str(exc);raise
    finally:
        # Use already captured frames, including the last failed measurement.
        # No extra game access is made after F9, focus loss or expiry.
        if report.get('capture_folder'):
            try:
                folder=Path(report['capture_folder'])/'execution';folder.mkdir(exist_ok=True)
                attempt=report.get('execution_attempt',0)+1;report['execution_attempt']=attempt
                prefix=f'attempt-{attempt:02d}'
                frame=getattr(report['adapter'],'last_frame',None)
                if frame is not None:Image.fromarray(frame).save(folder/(prefix+'.png'),compress_level=1)
                motion_frames={}
                for label in ('before','after'):
                    frame=getattr(adapter,'last_motion_'+label,None)
                    if frame is not None:
                        filename=prefix+'-motion-'+label+'.png'
                        Image.fromarray(frame).save(folder/filename,compress_level=1)
                        motion_frames[label]=filename
                data=dict(candidate=candidate,rules=rules,result=result,error=failure,events=events,
                          code_read_totals=getattr(adapter,'code_read_stats',None),
                          last_registration=getattr(adapter,'last_motion_diagnostics',None),
                          motion_frames=motion_frames,
                          previous_actual_pose=report.get('actual_pose'),
                          pose_scope='Relative to previous verified frame or acquisition frame')
                (folder/(prefix+'.json')).write_text(json.dumps(data,indent=2),encoding='utf-8')
            except OSError:pass  # Diagnostic storage cannot interrupt dyeing.


def default_current(owner, report, candidate, rules, **_context):
    result=_execute_recorded(owner,report,candidate,rules,report['batch'],report['reference'],
                             reservation='default')
    report['pose_reference']=report['adapter'].verified_frame
    report['actual_pose']=result['actual_pose']
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
        reference_pose=source,check=adapter.check,require_stable=True)
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
            require_stable=True)
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
