"""Describe saved response evidence without installing a response model.

This is a read-only audit of local sessions. Observed extrema are descriptive,
not calibrated uncertainty bounds or a guarantee for unseen display settings.
"""
import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path
import numpy as np
from gesture_replay import audit,error_stats


def capture_evidence(capture):
    capture=Path(capture)
    log=json.loads((capture/'log.json').read_text(encoding='utf8'))
    frames=[e for e in log if e.get('kind')=='frame']
    ready=next((e for e in log if e.get('kind')=='sampling_ready'),
               next((e for e in log if e.get('kind')=='ready'),{}))
    calibrations=[]
    for event in log:
        if event.get('kind')!='zoom_calibration':continue
        for row in event.get('measurements',[]):
            item=dict(steps=row['steps'],passed=bool(event.get('passed')),
                      error=row.get('error'),source='capture_calibration',
                      raw_frame_pair_available=False)
            motion=row.get('motion')
            if motion and motion.get('matrix') is not None:
                matrix=np.asarray(motion['matrix'],float)
                scale=float(np.hypot(matrix[0,0],matrix[1,0]))
                item.update(scale=scale,log_per_notch=float(np.log(scale)/row['steps']),
                            reported_scale=motion.get('scale'),matrix=matrix.tolist())
            calibrations.append(item)
    pairs=[]
    for file in sorted((capture/'execution').glob('attempt-*.json')):
        data=json.loads(file.read_text(encoding='utf8'))
        registrations=[e for e in data.get('events',[]) if e.get('kind')=='atlas_registration']
        last=registrations[-1] if registrations else {}
        named=data.get('motion_frames',{})
        available=all(named.get(key) and (file.parent/named[key]).is_file() for key in ('before','after'))
        pairs.append(dict(attempt=file.name,available=bool(available),
                          phase=last.get('phase'),step=last.get('step'),
                          completed=(data.get('result') or {}).get('positioning_complete'),
                          recovered=bool((data.get('result') or {}).get('recovered')),
                          association='Last registration only; intermediate pairs were not saved'))
    return dict(session=capture.parent.name,board=ready.get('board'),
                geometry=frames[0].get('geometry') if frames else None,
                dpi=next((e['dpi'] for e in log if e.get('dpi') is not None),None),
                sampling_zoom=next((e for e in log if e.get('kind')=='sampling_zoom'),None),
                calibration=calibrations,execution_pairs=pairs)


def condition_summary(rows):
    groups=defaultdict(list)
    for row in rows:
        board=row.get('board')
        if not board:continue
        size=(board[2]-board[0],board[3]-board[1])
        command=row['command'];action=row['action']
        band=('under_one_degree' if abs(command)<1 else 'one_degree_or_more') if action=='rotate' else 'all'
        direction=int(np.sign(command)) if action in ('rotate','wheel') else 0
        groups[(action,size,direction,band)].append(row)
    output=[]
    for (action,size,direction,band),group in sorted(groups.items()):
        result=dict(action=action,board_size=list(size),direction=direction,request_band=band,
                    samples=len(group),sessions=sorted({r['session'] for r in group}),
                    statuses=dict(Counter(r['status'] for r in group)))
        measured=[r for r in group if 'response' in r and 'audit_error' not in r]
        if action=='rotate':
            result['request_residual_degrees']=error_stats([r['response']['request_error'] for r in measured])
            result['arc_residual_degrees']=error_stats([r['response']['cursor_arc_error'] for r in measured])
            result['no_angular_response']=sum(r['response']['no_angular_response'] for r in measured)
        elif action=='wheel':
            values=[r['response']['log_per_notch'] for r in measured]
            if values:result['log_per_notch']=dict(minimum=min(values),maximum=max(values),median=float(np.median(values)))
        pivots=[r['response']['pivot_shift'] for r in measured if 'pivot_shift' in r['response']]
        result['pivot_shift_pixels']=error_stats(pivots)
        output.append(result)
    return output


def evidence(roots):
    baseline=audit(roots);sessions=[];errors=[];seen=set()
    for root in map(Path,roots):
        captures=[root] if root.name=='atlas_capture' else list(root.glob('*/atlas_capture'))
        if (root/'atlas_capture').is_dir():captures.append(root/'atlas_capture')
        for capture in captures:
            if capture.resolve() in seen or not any((capture/'execution').glob('attempt-*.json')):continue
            seen.add(capture.resolve())
            try:sessions.append(capture_evidence(capture))
            except (OSError,ValueError,KeyError,TypeError) as exc:
                errors.append(dict(session=capture.parent.name,error=str(exc)))
    pairs=[p for s in sessions for p in s['execution_pairs'] if p['available']]
    calibration=[dict(session=s['session'],**r) for s in sessions for r in s['calibration']]
    return dict(schema=1,summary=baseline['summary'],conditions=condition_summary(baseline['rows']),
                sessions=sessions,calibrations=calibration,read_errors=baseline['read_errors']+errors,
                saved_pairs=dict(total=len(pairs),by_phase=dict(Counter(p['phase'] for p in pairs))),
                response_model_installed=False,
                limitation='Saved registrations are measurements, not ground truth. Extrema do not establish '
                           'coverage or an uncertainty bound. Legacy input descriptors are reconstructed. '
                           'Missing DPI or intermediate screenshots cannot be inferred.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sessions-root',action='append',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();result=evidence(args.sessions_root)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf8')
    print(json.dumps({key:result[key] for key in ('summary','conditions','saved_pairs')},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
