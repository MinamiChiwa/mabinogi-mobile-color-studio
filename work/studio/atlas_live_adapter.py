"""Explicit Windows callbacks for the per-session atlas service.

Acquisition waits for the user to enter the timed dye screen manually. The
adapter never clicks a dye-entry control, so starting the tool cannot consume
a dye.
"""
from pathlib import Path
import time
import uuid
import json
from PIL import Image
from live_atlas_capture import acquire
from atlas_adapter import build_from_capture
from atlas_execution import CandidateBatch, Context, execute_candidate
from atlas_service import AtlasCallbacks
from atlas_runtime import Adapter
from workflow_budget import earliest_deadline
from atlas_pose import homogeneous


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
    context=Context(uuid.uuid4().hex,tuple(game.geometry()),tuple(scene.board),
                    tuple(map(tuple,scene.markers)))
    batch=CandidateBatch(rows,context,deadline)
    adapter=Adapter(game,scene,context.session)
    report.update(batch=batch,batch_id=batch.id,board=tuple(scene.board),
                  markers=tuple(map(tuple,scene.markers)),
                  selection_deadline=deadline,adapter=adapter,
                  reference=artifact['image'],rules=rules,
                  capture_folder=Path(artifact['folder']) if artifact.get('folder') else None)
    return report


def _execute_recorded(owner,report,candidate,rules,batch,reference,reservation='legacy'):
    events=[];result=None;failure=None
    adapter=report['adapter']
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


def choice_current(owner, report, candidate, rules, **_context):
    # Service rebases the complete target matrix from the last measured pose.
    # Retain the verified frame so manual movement during selection is caught.
    adapter=report['adapter'];adapter.check()
    deadline=earliest_deadline(report['selection_deadline'],_context.get('selection_deadline'))
    if time.monotonic()>=deadline:raise RuntimeError('Workflow deadline expired before choice')
    reference=report['pose_reference'];row=dict(candidate)
    batch=CandidateBatch([row],adapter.context(),deadline)
    result=_execute_recorded(owner,report,row,rules,batch,reference)
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
        build=build_current,default=default_current,choice=choice_current)
