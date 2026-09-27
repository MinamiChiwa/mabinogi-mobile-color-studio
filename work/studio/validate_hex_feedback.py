"""Read-only saved-path replay, distinct from simulated 2-D refinement.

This scores only the 17 recorded poses in capture order. It never invents
unseen colors, reverses the recorded path or claims an executed restoration.
The examples were chosen after inspecting this dataset, not blind trials.
"""
import argparse
import json
from pathlib import Path
import numpy as np
from hex_refinement import score_codes


def run(capture, review, output):
    capture=Path(capture);review=Path(review);output=Path(output)
    output.mkdir(parents=True,exist_ok=False)
    codes=json.loads((review/'verified-codes.json').read_text(encoding='utf-8'))['codes']
    points=json.loads((review/'affine-points.json').read_text(encoding='utf-8'))
    log=json.loads((capture/'log.json').read_text(encoding='utf-8'))
    times={r['name']:r['elapsed_seconds'] for r in log if r['kind']=='frame'}
    names=[f'probe_{i:03d}' for i in range(17)]
    geometry={r['frame']:r for r in points}
    origin=np.asarray(geometry[names[0]]['points'])
    cases=[dict(name='three_region_compromise',targets=['#704030','#001018','#484644'],
                exact=False,tolerance=3.,enabled=[True]*3),
           dict(name='three_region_dark_target',targets=['#703030','#000000','#484848'],
                exact=False,tolerance=5.,enabled=[True]*3),
           dict(name='recorded_exact_sanity',targets=codes['probe_006'],
                exact=True,tolerance=0.,enabled=[True]*3),
           dict(name='region_two_only_diagnostic',targets=['#000000']*3,
                exact=False,tolerance=5.,enabled=[False,True,False])]
    results=[]
    for case in cases:
        rules=[dict(colors=[color],enabled=enabled,exact=case['exact'],tolerance=case['tolerance'])
               for color,enabled in zip(case['targets'],case['enabled'])]
        trajectory=[];best=None
        for name in names:
            row=dict(frame=name,elapsed_from_probe_start=times[name]-times[names[0]],
                     # Each marker has its own inverse-affine texture point:
                     # the captured wheel pairs are not pure translation.
                     measured_texture_point_delta=(np.asarray(geometry[name]['points'])-origin).tolist(),
                     **score_codes(codes[name],rules))
            if best is None or row['rank']<best['rank']:best=row
            row['best_observed_frame']=best['frame'];trajectory.append(row)
        results.append(dict(**case,rules=rules,start=trajectory[0],best=best,
                            end=trajectory[-1],trajectory=trajectory,
                            best_was_revisited=False,restoration_validated=False))
    report=dict(mode='saved_path_scoring_only',game_input_sent=False,frame_count=len(names),
                source=str(capture.resolve()),codes_source=str((review/'verified-codes.json').resolve()),
                total_recorded_path_seconds=times[names[-1]]-times[names[0]],cases=results,
                limitations=[
                    'Targets selected after viewing this dataset; not independent accuracy validation.',
                    'Only recorded forward poses are available; no arbitrary 2-D response or reverse motion is inferred.',
                    'HEX labels were manually verified; live double-read stability and OCR cost are not measured here.',
                    'Geometric evidence includes affine scale drift; not proof of pure translation.',
                    'A best historical pose is not the current pose. No restore was executed.',
                    'Exact sanity targets deliberately reproduce a recorded point; not a game success-rate estimate.'])
    (output/'saved-path-replay.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    summary=[dict(name=c['name'],start_max_delta_e=max(v for v in c['start']['deltas'] if v is not None),
                  best_frame=c['best']['frame'],best_max_delta_e=max(v for v in c['best']['deltas'] if v is not None),
                  best_accepted=c['best']['accepted'],end_accepted=c['end']['accepted']) for c in results]
    (output/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary,indent=2))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture');parser.add_argument('review');parser.add_argument('output')
    args=parser.parse_args();run(args.capture,args.review,args.output)
