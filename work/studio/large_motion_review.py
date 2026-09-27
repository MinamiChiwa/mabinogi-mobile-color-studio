"""Diagnose lost material overlap in saved larger-displacement frame pairs.

Full-trajectory offsets are reference diagnostics only, never supplied to the
feature matcher as recovered motion. This module never sends game input.
"""
import argparse
import json
from pathlib import Path
import cv2
import numpy as np
from atlas_budget_review import load_capture


def overlap_counts(masks,translation):
    """Count same-material source pixels that land in valid destination masks."""
    masks=np.asarray(masks,bool)
    delta=np.asarray(translation,float)
    if masks.ndim!=3 or min(masks.shape)<1 or min(masks.shape[1:])<2:
        raise ValueError('Nonempty material masks of at least 2 by 2 pixels are required')
    if delta.shape!=(2,) or not np.isfinite(delta).all():
        raise ValueError('Finite two-dimensional translation is required')
    h,w=masks.shape[1:];dx,dy=delta
    rows=[]
    for mask in masks:
        y,x=np.where(mask)
        xx=x+dx;yy=y+dy
        good=(xx>=0)&(xx<w-1)&(yy>=0)&(yy<h-1)
        ix=np.floor(np.clip(xx,0,w-2)).astype(int);iy=np.floor(np.clip(yy,0,h-2)).astype(int)
        good &= mask[iy,ix]&mask[iy+1,ix]&mask[iy,ix+1]&mask[iy+1,ix+1]
        rows.append(dict(pixels=int(good.sum()),fraction=float(good.mean()) if len(good) else 0.))
    return rows


def feature_diagnosis(a,b,masks,mode,reference_translation,basis):
    detector=cv2.SIFT_create(nfeatures=1800)
    mask=None if mode=='unmasked' else (masks.any(axis=0)*255).astype(np.uint8)
    ka,da=detector.detectAndCompute(cv2.cvtColor(a,cv2.COLOR_RGB2GRAY),mask)
    kb,db=detector.detectAndCompute(cv2.cvtColor(b,cv2.COLOR_RGB2GRAY),mask)
    result=dict(source_features=len(ka),destination_features=len(kb),mode=mode)
    if da is None or db is None or len(db)<2:
        return dict(result,accepted=False,reason='missing_descriptors')
    matched=[p[0] for p in cv2.BFMatcher().knnMatch(da,db,k=2) if len(p)==2 and p[0].distance<.7*p[1].distance]
    src=np.float32([ka[m.queryIdx].pt for m in matched]).reshape(-1,2)
    dst=np.float32([kb[m.trainIdx].pt for m in matched]).reshape(-1,2)
    h,w=a.shape[:2]
    def region(points):
        xy=np.rint(points).astype(int);xy[:,0]=np.clip(xy[:,0],0,w-1);xy[:,1]=np.clip(xy[:,1],0,h-1)
        valid=masks[:,xy[:,1],xy[:,0]]
        return np.where(valid.any(axis=0),valid.argmax(axis=0),-1)
    ra,rb=region(src),region(dst);same=(ra>=0)&(ra==rb)
    if mode=='same_material':src,dst=src[same],dst[same];ra,rb=ra[same],rb[same]
    delta=dst-src
    equivalents=np.array([reference_translation+np.asarray([x,y])@basis.T for x in (-1,0,1) for y in (-1,0,1)])
    consistent=np.min(np.linalg.norm(delta[:,None,:]-equivalents,axis=2),axis=1)<2 if len(delta) else np.zeros(0,bool)
    result.update(ratio_matches=len(matched),retained_matches=len(src),
                  static_matches=int((np.linalg.norm(delta,axis=1)<2).sum()),
                  reference_consistent_matches=int(consistent.sum()),
                  reference_consistent_same_material=int((consistent&(ra>=0)&(ra==rb)).sum()))
    if len(src)<20:return dict(result,accepted=False,reason='fewer_than_20_matches')
    matrix,inliers=cv2.estimateAffinePartial2D(src,dst,method=cv2.RANSAC,ransacReprojThreshold=2)
    if matrix is None:return dict(result,accepted=False,reason='no_affine_fit')
    count=int(inliers.sum());fraction=float(inliers.mean())
    scale=float(np.hypot(matrix[0,0],matrix[1,0]));angle=float(np.degrees(np.arctan2(matrix[1,0],matrix[0,0])))
    accepted=count>=20 and fraction>=.5 and abs(scale-1)<=.005 and abs(angle)<=.2
    return dict(result,matrix=matrix.tolist(),inliers=count,inlier_fraction=fraction,scale=scale,angle=angle,
                accepted=accepted,reason='ok' if accepted else 'existing_geometry_or_confidence_gate')


def main(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    sources=[('new','outputs/atlas-capture-20260926-113839-673'),('old','atlas_capture_2026-09-24_2141')]
    results=[]
    for label,source in sources:
        data=load_capture(source)
        report=json.loads(Path(f'outputs/atlas-budget-20260926/{label}-optimized-1/report.json').read_text())
        offsets=np.asarray(report['offsets']);basis=np.diag([report['period_x'],report['period_y']])
        for first,last in ((0,1),(0,2),(7,8),(7,12),(7,23)):
            delta=offsets[last]-offsets[first]
            overlaps=[]
            for x in (-1,0,1):
                for y in (-1,0,1):
                    shift=delta+np.array([x,y])@basis.T
                    overlaps.append(dict(cycle=[x,y],translation=shift.tolist(),regions=overlap_counts(data['masks'],shift)))
            row=dict(session=label,pair=[first,last],reference_translation=delta.tolist(),
                     maximum_overlap_per_region=[max(r['regions'][i]['fraction'] for r in overlaps) for i in range(3)],
                     periodic_overlap=overlaps,features=[feature_diagnosis(data['images'][first],data['images'][last],
                         data['masks'],mode,delta,basis) for mode in ('unmasked','masked','same_material')])
            results.append(row)
            print(label,[first,last],'overlap',row['maximum_overlap_per_region'],
                  'features',[(v['mode'],v.get('retained_matches',0),v.get('reference_consistent_same_material',0),v['accepted']) for v in row['features']],flush=True)
    result=dict(game_input_sent=False,pairs=results,
                reference_scope='Full-trajectory measured geometry used only to diagnose overlap; includes heldout texture.',
                limitations=['Masking cannot recover texture that is not visible in both same-material regions.',
                             'No quality gates changed and no matcher promoted to production.',
                             'Saved endpoint pairs cannot establish execution time or all intermediate game poses.'])
    (output/'report.json').write_text(json.dumps(result,indent=2))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output')
    main(parser.parse_args().output)
