"""Audit saved micro-motion geometry and OCR cost without game input.

The source trajectory only moved forwards. Inverting an estimated matrix is
an offline geometric calculation, never evidence of a successful game return.
"""
import argparse
import json
from pathlib import Path
import time
import numpy as np
from PIL import Image
from vision import configure_ocr,read_codes,error


def audit_geometry(affine_rows,codes):
    first=affine_rows[0];base=np.asarray(first['points'],float)
    def matrix(row):
        value=np.eye(3);value[:2]=row['matrix'];return value
    origin=matrix(first);rows=[];previous=base
    for record in affine_rows:
        points=np.asarray(record['points'],float)
        relative=matrix(record)@np.linalg.inv(origin)
        singular=np.linalg.svd(relative[:2,:2],compute_uv=False)
        delta=points-base;step=points-previous
        residual=delta-delta.mean(axis=0)
        rows.append(dict(frame=record['frame'],relative_affine=relative.tolist(),
                         relative_scales=singular.tolist(),
                         three_point_delta=delta.tolist(),three_point_step=step.tolist(),
                         maximum_translation_model_residual=float(np.max(np.linalg.norm(residual,axis=1))),
                         maximum_step=float(np.max(np.linalg.norm(step,axis=1)))))
        previous=points
    # Spatially near observed poses are useful evidence of local sensitivity,
    # but are neither reverse commands nor duplicate-image stability tests.
    pairs=[]
    for i,a in enumerate(affine_rows):
        for b in affine_rows[i+2:]:
            distance=np.linalg.norm(np.asarray(a['points'])-np.asarray(b['points']),axis=1)
            if np.max(distance)>.75:continue
            pairs.append(dict(a=a['frame'],b=b['frame'],point_distances=distance.tolist(),
                              delta_e76=[error(x,[y],False) for x,y in zip(codes[a['frame']],codes[b['frame']])],
                              exact_colors_equal=codes[a['frame']]==codes[b['frame']]))
    return dict(rows=rows,nearby_pose_pairs=pairs,
                maximum_translation_model_residual=max(r['maximum_translation_model_residual'] for r in rows),
                maximum_relative_scale_deviation=max(abs(s-1) for r in rows for s in r['relative_scales']),
                reverse_motion_observed=False,return_validated=False,
                proposed_controller_pose_tolerance=.035,
                limitations=['Affine estimates are noisy and not ground-truth displacement.',
                             'Point coordinates originate from the prior UI-circle and texture registration study.',
                             'Only forward actions were recorded; inverse matrices do not demonstrate game reversibility.'])


def audit_ocr(source,codes):
    configure_ocr(strict=True)
    log=json.loads((source/'log.json').read_text())
    scene=next(r for r in log if r['kind']=='sampling_ready')
    rows=[]
    for name in ('probe_000','probe_003','probe_006','probe_008','probe_011','probe_016'):
        image=np.array(Image.open(source/(name+'.png')).convert('RGB'))
        for repeat in range(2):
            start=time.perf_counter();actual=read_codes(image,scene['cards'],scene['markers'])
            elapsed=time.perf_counter()-start
            rows.append(dict(frame=name,repeat=repeat,seconds=elapsed,codes=actual,
                             correct=actual==codes[name]))
    return dict(reads=rows,median_read_seconds=float(np.median([r['seconds'] for r in rows])),
                maximum_read_seconds=max(r['seconds'] for r in rows),all_correct=all(r['correct'] for r in rows),
                scope='Same saved pixels read twice. Excludes capture, motion, guards and temporal stability.')


def main(source,review,output):
    source=Path(source);review=Path(review);output=Path(output)
    output.mkdir(parents=True,exist_ok=False)
    codes=json.loads((review/'verified-codes.json').read_text())['codes']
    rows=json.loads((review/'affine-points.json').read_text())
    result=dict(game_input_sent=False,geometry=audit_geometry(rows,codes),ocr=audit_ocr(source,codes))
    (output/'review.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(dict(geometry={k:v for k,v in result['geometry'].items() if k not in ('rows','nearby_pose_pairs')},
                         ocr={k:v for k,v in result['ocr'].items() if k!='reads'}),indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source');parser.add_argument('review');parser.add_argument('output')
    args=parser.parse_args();main(args.source,args.review,args.output)
