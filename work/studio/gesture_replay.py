"""Read-only input/response audit with session-separated model evaluation.

Reads saved execution JSON only; imports no Windows input or game modules.
Legacy paths are reconstructed, not claimed to be recorded cursor traces.
"""
import argparse
import json
from pathlib import Path
import numpy as np
from input_gestures import planned_gesture, rotation_gesture


def read_attempt(file, board, session):
    data=json.loads(Path(file).read_text(encoding='utf8'))
    commands={}; measured={};registered={}
    for event in data.get('events',[]):
        if event.get('kind')=='atlas_command':commands[event['step']]=event
        elif event.get('kind')=='atlas_positioning':measured[event['step']]=event
        elif (event.get('kind')=='atlas_registration' and event.get('phase')=='positioning'
              and event.get('measured') is not None):registered[event['step']]=event
    rows=[]
    for step,event in commands.items():
        row=dict(session=session,attempt=Path(file).name,step=step,
                 action=event['action'],command=event['command'],board=list(board),
                 anchor=event.get('anchor'),attempt_error=data.get('error'),
                 status='unmeasured',measurement_source='saved_image_registration')
        try:
            # Missing descriptors predate grouped arcs. Never reconstruct old
            # observations using the current production input implementation.
            make=rotation_gesture if event['action']=='rotate' else None
            legacy=(make(board,event['command'],event.get('anchor')) if make else
                    planned_gesture(event['action'],board,event['command'],event.get('anchor')))
            gesture=planned_gesture(event['action'],board,event['command'],event.get('anchor'))
            recorded=event.get('gesture')
            row['input']=recorded if recorded else legacy.record()
            row['input_source']='recorded_descriptor' if recorded else 'reconstructed_legacy_descriptor'
            row['descriptor_matches_current']=json.dumps(row['input'],sort_keys=True)==json.dumps(gesture.record(),sort_keys=True)
            measurement=measured.get(step,registered.get(step))
            if measurement is not None:
                matrix=np.asarray(measurement['measured'],float)
                if matrix.shape!=(2,3) or not np.isfinite(matrix).all():
                    raise ValueError('Invalid measured transform')
                angle=float(np.degrees(np.arctan2(matrix[1,0],matrix[0,0])))
                scale=float(np.hypot(matrix[0,0],matrix[1,0]))
                if scale<=0:raise ValueError('Invalid measured scale')
                row.update(status='measured' if step in measured else 'measured_rejected',matrix=matrix.tolist(),
                           response=dict(angle=angle,scale=scale))
                if event['action']=='rotate':
                    row['response'].update(request_error=angle-float(event['command']),
                                           cursor_arc_error=angle-float(row['input']['cursor_arc_degrees']),
                                           no_angular_response=abs(angle)<.025)
                elif event['action']=='wheel' and gesture.wheel_steps:
                    row['response'].update(log_per_notch=float(np.log(scale)/gesture.wheel_steps),
                                           no_scale_response=abs(scale-1)<.0005)
                if event.get('anchor') is not None:
                    pivot=np.asarray(gesture.anchor)-np.asarray(board[:2])
                    row['response']['pivot_shift']=float(np.linalg.norm(matrix[:,:2]@pivot+matrix[:,2]-pivot))
        except (ValueError,TypeError,KeyError) as exc:
            row['audit_error']=str(exc)
        rows.append(row)
    return rows


def error_stats(errors):
    values=np.abs(np.asarray(errors,float))
    return dict(count=len(values),mean=float(values.mean()),maximum=float(values.max())) if len(values) else dict(count=0)


def rotation_holdouts(rows):
    rotations=[r for r in rows if r['action']=='rotate' and r['status']=='measured' and 'audit_error' not in r]
    output={}
    for name,feature in (('request',lambda r:float(r['command'])),
                         ('cursor_arc',lambda r:r['input']['cursor_arc_degrees'])):
        identity=[];fitted=[];folds=[]
        for session in sorted({r['session'] for r in rotations}):
            train=[r for r in rotations if r['session']!=session]
            test=[r for r in rotations if r['session']==session]
            if not train:continue
            x=np.asarray([feature(r) for r in train]);y=np.asarray([r['response']['angle'] for r in train])
            denominator=float(x@x)
            if denominator<1e-12:continue
            gain=float(x@y/denominator)
            base=[r['response']['angle']-feature(r) for r in test]
            errors=[r['response']['angle']-gain*feature(r) for r in test]
            identity.extend(base);fitted.extend(errors)
            folds.append(dict(held_out_session=session,training_sessions=sorted({r['session'] for r in train}),
                              gain=gain,identity=error_stats(base),fitted=error_stats(errors)))
        output[name]=dict(identity=error_stats(identity),fitted=error_stats(fitted),folds=folds)
    return output


def read_rotation_audit(file):
    """Use a preserved prior audit when its original sessions have moved.

    It contains completed rotations only, so it cannot replace the complete
    event stream or establish absence of failures. Keep that provenance.
    """
    data=json.loads(Path(file).read_text(encoding='utf8'))
    return [dict(session=r['session'],attempt='preserved_rotation_audit',step=r['step'],
                 action='rotate',command=r['requested'],anchor=r['anchor'],status='measured',
                 input_source='previous_offline_reconstruction',source_file=Path(file).name,
                 measurement_source='preserved_audit_of_saved_image_registration',
                 input=dict(points=r['points'],cursor_arc_degrees=r['outer_arc_extent']),
                 response=dict(angle=r['measured'],request_error=r['request_error'],
                               cursor_arc_error=r['outer_arc_error'],no_angular_response=abs(r['measured'])<.025))
            for r in data['rotations']]


def audit(roots, rotation_audits=()):
    rows=[];read_errors=[];files=set()
    for root in roots:
        root=Path(root)
        if not root.is_dir():raise ValueError(f'Missing sessions root: {root}')
        captures=[root] if root.name=='atlas_capture' else list(root.glob('*/atlas_capture'))
        if (root/'atlas_capture').is_dir():captures.append(root/'atlas_capture')
        for capture in captures:
            try:
                report=json.loads((capture/'analysis/report.json').read_text(encoding='utf8'))
                board=report['scene']['board']
                for file in sorted((capture/'execution').glob('attempt-*.json')):
                    if file.resolve() in files:continue
                    files.add(file.resolve())
                    rows.extend(read_attempt(file,board,capture.parent.name))
            except (OSError,ValueError,KeyError) as exc:
                read_errors.append(dict(session=capture.parent.name,error=str(exc)))
    raw_sessions={r['session'] for r in rows}
    for file in rotation_audits:
        # A complete raw session takes precedence over a partial export.
        rows.extend(r for r in read_rotation_audit(file) if r['session'] not in raw_sessions)
    wheel={}
    for direction in (-1,1):
        values=[r['response']['log_per_notch'] for r in rows
                if r['action']=='wheel' and r['status']=='measured' and
                'log_per_notch' in r.get('response',{}) and np.sign(r['command'])==direction]
        wheel[str(direction)]=(dict(count=len(values),minimum=min(values),maximum=max(values),median=float(np.median(values)))
                                if values else dict(count=0))
    summary=dict(attempts=len(files),commands=len(rows),sessions=len({r['session'] for r in rows}),
                 actions={kind:sum(r['action']==kind for r in rows) for kind in ('drag','rotate','wheel')},
                 measured=sum(r['status']=='measured' for r in rows),
                 measured_rejected=sum(r['status']=='measured_rejected' for r in rows),
                 unmeasured=sum(r['status']=='unmeasured' for r in rows),
                 read_errors=len(read_errors),wheel_log_per_notch=wheel)
    return dict(schema=1,summary=summary,rotation_holdouts=rotation_holdouts(rows),
                rows=rows,read_errors=read_errors,
                limitation='Saved registrations and reconstructed legacy inputs are not ground truth. '
                           'Holdout gains are analysis only, never installed as runtime calibration.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sessions-root',action='append',default=[],type=Path)
    parser.add_argument('--rotation-audit',action='append',default=[],type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    if not args.sessions_root and not args.rotation_audit:
        parser.error('At least one sessions root or preserved rotation audit is required')
    result=audit(args.sessions_root,args.rotation_audit)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf8')
    print(json.dumps(dict(summary=result['summary'],rotation_holdouts={k:{a:b for a,b in v.items() if a!='folds'}
                     for k,v in result['rotation_holdouts'].items()}),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
