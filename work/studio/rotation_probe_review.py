"""Review saved response frames and a diagnostic incremental-angle hypothesis.

The fitted threshold is an analysis result, never a runtime calibration. A
within-session repeat is distinct from validation on an independent session.
"""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from PIL import Image
from atlas_runtime import texture_mask
from gesture_replay import error_stats
from atlas_pose import homogeneous, marker_errors


def compare_responses(rows, board, markers):
    """Audit saved inputs and full transforms without fitting a response model.

    The integer arc endpoint is an explicit hypothesis. Residuals are observed
    errors in these records, never a universal accuracy/admission threshold.
    Missing cursor samples cannot be counted as matching samples.
    """
    local=np.asarray(markers,float)-np.asarray(board[:2],float)
    observations=[];groups={}
    for row in rows:
        gesture=row['gesture']
        if gesture['kind']!='rotate':continue
        trace=row.get('input_trace') or []
        points=gesture['points'];by_slot={}
        duplicate_slots=0;invalid_slots=0
        for item in trace:
            slot=item.get('slot')
            if not isinstance(slot,int) or not 0<=slot<len(points):
                invalid_slots+=1;continue
            if slot in by_slot:duplicate_slots+=1
            by_slot[slot]=item
        missing=[];mismatches=[];actual=[]
        for slot,point in enumerate(points):
            item=by_slot.get(slot,{})
            value=item.get('actual_client')
            if (item.get('error') or value is None or np.asarray(value).shape!=(2,)
                    or not np.isfinite(value).all()):
                missing.append(slot);continue
            actual.append(value)
            if tuple(point)!=tuple(value) or tuple(item.get('requested',()))!=tuple(point):
                mismatches.append(slot)
        trace_complete=not (missing or duplicate_slots or invalid_slots)
        observed_arc=None
        if trace_complete:
            observed_arc=float(angular_increments(dict(points=actual,arc_start=gesture['arc_start'])).sum())
        record=dict(step=row['step'],name=row['name'],variant=row.get('variant','legacy'),
                    repeat=row['repeat'],anchor_name=row['anchor_name'],
                    requested_angle=gesture['requested_angle'],arc_degrees=gesture['cursor_arc_degrees'],
                    trace=dict(expected=len(points),samples=len(trace),complete=trace_complete,
                               missing_slots=missing,mismatched_slots=mismatches,
                               duplicate_slots=duplicate_slots,invalid_slots=invalid_slots,
                               actual_cursor_arc_degrees=observed_arc),
                    measured=bool(row.get('registration_complete') and row.get('response')))
        if record['measured']:
            angle=float(gesture['cursor_arc_degrees']);theta=np.radians(angle)
            linear=np.array([[np.cos(theta),-np.sin(theta)],[np.sin(theta),np.cos(theta)]])
            pivot=np.asarray(points[0],float)-board[:2]
            predicted=homogeneous(np.column_stack((linear,pivot-linear@pivot)))
            measured=homogeneous(row['response']['matrix'])
            record.update(response_angle=row['response']['angle'],
                          arc_error=row['response']['angle']-angle,
                          request_error=row['response']['angle']-gesture['requested_angle'],
                          marker_errors=marker_errors(predicted,measured,local).tolist(),
                          pivot_error=float(np.linalg.norm(measured[:2,:2]@pivot+measured[:2,2]-pivot)))
        observations.append(record)
    for variant in sorted({r['variant'] for r in observations}):
        selected=[r for r in observations if r['variant']==variant]
        measured=[r for r in selected if r['measured']]
        groups[variant]=dict(count=len(selected),measured=len(measured),
            angle_error=error_stats([r['arc_error'] for r in measured]),
            request_error=error_stats([r['request_error'] for r in measured]),
            marker_error=error_stats([v for r in measured for v in r['marker_errors']]),
            repeats={str(i):error_stats([r['arc_error'] for r in measured if r['repeat']==i])
                     for i in sorted({r['repeat'] for r in selected})})
    return dict(observations=observations,variants=groups,
                trace_expected=sum(r['trace']['expected'] for r in observations),
                trace_samples=sum(r['trace']['samples'] for r in observations),
                trace_missing=sum(len(r['trace']['missing_slots']) for r in observations),
                trace_mismatches=sum(len(r['trace']['mismatched_slots']) for r in observations),
                trace_complete=all(r['trace']['complete'] for r in observations) if observations else False,
                response_model_installed=False)


def angular_increments(record):
    points=np.asarray(record['points'],float)
    vectors=points[int(record['arc_start']):]-points[0]
    if len(vectors)<2 or (np.linalg.norm(vectors,axis=1)<1e-9).any():
        raise ValueError('Arc requires nonzero vectors relative to the pivot')
    return np.diff(np.degrees(np.unwrap(np.arctan2(vectors[:,1],vectors[:,0]))))


def incremental_prediction(record,threshold):
    increments=angular_increments(record)
    return float(increments[np.abs(increments)>=threshold].sum())


def fit_increment_hypothesis(rows):
    rotations=[r for r in rows if r['gesture']['kind']=='rotate' and r.get('registration_complete')]
    train=[r for r in rotations if r['repeat']==0]
    test=[r for r in rotations if r['repeat']!=0]
    if not train:return dict(available=False)
    # Each open interval between observed increments produces one response.
    values=np.unique(np.r_[0.,*[np.abs(angular_increments(r['gesture'])) for r in train]])
    intervals=[(float(a),float(b)) for a,b in zip(values[:-1],values[1:]) if b-a>1e-8]
    trials=[]
    for lower,upper in intervals:
        threshold=(lower+upper)/2
        residuals=[r['response']['angle']-incremental_prediction(r['gesture'],threshold) for r in train]
        trials.append((float(np.mean(np.abs(residuals))),lower,upper,threshold))
    if not trials:return dict(available=False,reason='No distinct angular increments')
    _,lower,upper,threshold=min(trials)
    def assess(data):
        return error_stats([r['response']['angle']-incremental_prediction(r['gesture'],threshold) for r in data])
    return dict(available=True,threshold=threshold,identical_training_prediction_interval=[lower,upper],
                training=assess(train),within_session_repeat=assess(test),
                training_steps=[r['step'] for r in train],repeat_steps=[r['step'] for r in test],
                response_model_installed=False)


def review(folder,legacy_file=None,game_resolution=None):
    folder=Path(folder);events=json.loads((folder/'log.json').read_text(encoding='utf8'))
    plan=next(e for e in events if e['kind']=='response_probe_plan')
    scene=SimpleNamespace(board=plan['board'],markers=plan['markers'])
    rows=[e for e in events if e['kind']=='response_probe_measurement']
    outcome=next((e for e in events if e['kind']=='response_probe_complete'),None)
    observations=[]
    for row in rows:
        before=np.asarray(Image.open(folder/(row['reference']+'.png')).convert('RGB'))
        after=np.asarray(Image.open(folder/(row['settled']+'.png')).convert('RGB'))
        l,t,r,b=scene.board;mask=texture_mask(scene,before.shape)>0
        difference=np.max(np.abs(after[t:b,l:r].astype(np.int16)-before[t:b,l:r].astype(np.int16)),axis=2)[mask]
        gesture=row['gesture']
        record=dict(step=row['step'],name=row['name'],repeat=row['repeat'],
                    anchor_name=row['anchor_name'],variant=row.get('variant','legacy'),
                    kind=gesture['kind'],response=row.get('response'),
                    pixel_changed_fraction=float(np.mean(difference>0)),
                    pixel_over_four_fraction=float(np.mean(difference>4)),
                    max_pixel_difference=int(difference.max()),
                    max_closure=max(row.get('closure_pixels',[0.])),
                    max_settling=max(row.get('settling_pixels',[0.])),
                    complete=row['registration_complete'])
        if gesture['kind']=='rotate':
            increments=angular_increments(gesture)
            record.update(requested_angle=gesture['requested_angle'],arc_degrees=gesture['cursor_arc_degrees'],
                          nonzero_increments=[float(v) for v in increments if abs(v)>1e-8])
        observations.append(record)
    hypothesis=fit_increment_hypothesis(rows)
    if legacy_file and hypothesis.get('available'):
        legacy=json.loads(Path(legacy_file).read_text(encoding='utf8'))['rows']
        legacy=[r for r in legacy if r['action']=='rotate' and r['status']=='measured']
        hypothesis['independent_legacy_sessions']=error_stats([
            r['response']['angle']-incremental_prediction(r['input'],hypothesis['threshold']) for r in legacy])
    elapsed=None if outcome is None else outcome['elapsed_seconds']-plan['elapsed_seconds']
    return dict(schema=2,folder=str(folder),protocol=plan.get('protocol','baseline'),geometry=plan['geometry'],board=plan['board'],dpi=plan.get('dpi'),
                reported_game_resolution=game_resolution,
                game_resolution_source='user_reported_setting' if game_resolution else None,
                measurement_seconds=elapsed,
                comparison=compare_responses(rows,plan['board'],plan['markers']),
                outcome=outcome,observations=observations,hypothesis=hypothesis,
                limitation='Pixel differences use fixed material/UI masks. A fitted angular deadband is a '
                           'hypothesis; it does not prove game implementation or a universal response bound.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder',type=Path);parser.add_argument('--legacy',type=Path)
    parser.add_argument('--game-resolution',help='User-reported game setting; separate from measured client size')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=review(args.folder,args.legacy,args.game_resolution)
    args.output.parent.mkdir(exist_ok=True,parents=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')
    print(json.dumps(dict(outcome=result['outcome'],hypothesis=result['hypothesis'],
        observations=[{k:r[k] for k in ('step','name','pixel_changed_fraction','pixel_over_four_fraction','max_settling')}
                      for r in result['observations']]),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
