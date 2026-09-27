"""Offline diagnosis of a saved run. Never sends game input.

Compares independent colors with shared translation and analytical similarity
transforms. Similarity results are diagnostic only, not executable candidates.
"""
import argparse
import itertools
import json
from pathlib import Path

import numpy as np
from PIL import Image
from periodic_atlas import AtlasSnapshot, PeriodicAtlas, translation_candidates
from analyze_live_atlas import quality_gate, validation_summary
from replay_archive import evaluate
from vision import lab, rgb
from atlas_masks import material_masks, mask_summary, save_mask_overlay


def distances(values, rule):
    converted=lab(values)
    return np.minimum.reduce([np.linalg.norm(converted-target,axis=1)
                              for target in lab([rgb(c) for c in rule['colors']])])


def load_atlas(path):
    atlas=AtlasSnapshot.__new__(AtlasSnapshot)
    with np.load(path) as data:
        for name in ('basis','origin','count','colors','valid','rmse'):
            setattr(atlas,name,data[name])
    atlas.resolution=atlas.colors.shape[1]
    return atlas


def similarity_review(atlas,markers,rules,max_points=1500,
                     scale_bounds=(.50, 1.80), angle_bounds=(-60, 60),
                     cycle_radius=1):
    """Solve two target-colored anchors, then independently check the third.

    Periodic copies are unfolded before fitting. Limits are diagnostic search
    bounds, not proof of safe game gestures. No game HEX is available here.
    """
    enabled=[i for i,r in enumerate(rules) if r['enabled']]
    if len(enabled)<2:raise ValueError('Similarity review needs two or three enabled regions')
    markers=np.asarray(markers,float)
    colors,valid,_=atlas.maps();n=atlas.resolution;points={};counts={}
    for i in enabled:
        delta=distances(colors[i].reshape(-1,3),rules[i]).reshape(n,n)
        yy,xx=np.where(valid[i] & (delta<=rules[i]['tolerance']))
        counts[i]=len(xx)
        if not len(xx):return dict(best=None,anchor_counts=counts,verified=False,executable=False)
        order=np.argsort(delta[yy,xx],kind='stable')
        keep=order if len(order)<=max_points else np.unique(np.r_[order[:max_points//2],
             np.linspace(0,len(xx)-1,max_points//2).astype(int)])
        phase=np.c_[xx[keep]+.5,yy[keep]+.5]/n
        points[i]=phase@atlas.basis.T+atlas.origin
    first,second=sorted(enabled,key=lambda i:len(points[i]))[:2]
    z1=points[first][:,0]+1j*points[first][:,1]
    p1=complex(*markers[first]);p2=complex(*markers[second])
    best=None;tested=0
    for cycle in itertools.product(range(-cycle_radius,cycle_radius+1),repeat=2):
        other=points[second]+np.asarray(cycle)@atlas.basis.T
        z2=other[:,0]+1j*other[:,1]
        for start in range(0,len(z1),128):
            with np.errstate(divide='ignore',invalid='ignore'):
                a=(p2-p1)/(z2[None,:]-z1[start:start+128,None])
                b=p1-a*z1[start:start+128,None]
            finite=np.isfinite(a)
            tested+=int(finite.sum())
            angles=np.degrees(np.angle(a))
            good=finite&(abs(a)>=scale_bounds[0])&(abs(a)<=scale_bounds[1])&(
                (angles>=angle_bounds[0])&(angles<=angle_bounds[1]))
            a=a[good];b=b[good]
            if not len(a):continue
            values=[];deltas=[];usable=np.ones(len(a),bool)
            for i in enabled:
                source=(complex(*markers[i])-b)/a
                value,supported=atlas.sample(i,np.c_[source.real,source.imag])
                value=np.rint(value).clip(0,255).astype(np.uint8)
                delta=distances(value,rules[i]);usable &= supported & (delta<=rules[i]['tolerance'])
                values.append(value);deltas.append(delta)
            if not usable.any():continue
            maximum=np.max(deltas,axis=0);maximum[~usable]=np.inf
            ix=int(np.argmin(maximum))
            if best is not None and maximum[ix]>=best['maximum']:continue
            best=dict(maximum=float(maximum[ix]),regions=[i+1 for i in enabled],
                      colors=['#%02X%02X%02X'%tuple(v[ix]) for v in values],
                      deltas=[float(v[ix]) for v in deltas],scale=float(abs(a[ix])),
                      angle=float(np.degrees(np.angle(a[ix]))),
                      matrix=[[float(a[ix].real),float(-a[ix].imag),float(b[ix].real)],
                              [float(a[ix].imag),float(a[ix].real),float(b[ix].imag)]])
    return dict(best=best,anchor_counts=counts,transforms_checked=tested,
                bounds=dict(scale=list(scale_bounds),angle=list(angle_bounds),
                            period_radius=cycle_radius,max_points=max_points),
                verified=False,executable=False)


def rebuild(source,report,resolution):
    """Change only phase resolution, retaining measured motion and holdouts."""
    scene=report['scene'];l,t,r,b=scene['board'];h,w=b-t,r-l
    markers=np.asarray(scene['markers'])-[l,t];spacing=markers[1,0]-markers[0,0]
    masks=material_masks(scene)
    names=['max_sampling']+[row['frame'] for row in report['motions']]
    offsets=dict(zip(names,report['offsets']))
    atlas=PeriodicAtlas([[report['period_x'],0],[0,report['period_y']]],resolution=resolution)
    for name in report['training']:
        with Image.open(source/(name+'_board.png')) as image:
            atlas.add_resampled(np.array(image.convert('RGB')),masks,offsets[name])
    atlas=atlas.snapshot();validation=[]
    for name in report['heldout']:
        with Image.open(source/(name+'_board.png')) as image:
            validation.append(dict(frame=name,prediction=evaluate(atlas,np.array(image.convert('RGB')),masks,offsets[name])))
    return atlas,quality_gate(atlas.report(),validation_summary(validation))


def run(source,output,analysis_dir=None):
    source=Path(source);output=Path(output);output.mkdir(parents=True,exist_ok=False)
    analysis_dir=Path(analysis_dir) if analysis_dir is not None else source/'analysis'
    report=json.loads((analysis_dir/'report.json').read_text(encoding='utf-8'))
    review=json.loads((analysis_dir/'expanded/review.json').read_text(encoding='utf-8'))
    rules=review['rules'];markers=np.asarray(report['scene']['markers'])-report['scene']['board'][:2]
    result=dict(source=str(source.resolve()),rules=rules,original_search_performed=report['timings']['candidate_computed'],
                original_quality_gate=report['quality_gate'],verified=False,input_sent=False,resolutions={})
    for resolution in (768,1024):
        atlas,gate=(load_atlas(analysis_dir/'atlas.npz'),report['quality_gate']) if resolution==768 else rebuild(source,report,resolution)
        trials={}
        enabled=[i for i,r in enumerate(rules) if r['enabled']]
        for count in range(1,len(enabled)+1):
            for regions in itertools.combinations(enabled,count):
                rr=[dict(r,enabled=i in regions) for i,r in enumerate(rules)]
                rows=translation_candidates(atlas,markers,rr,report['offsets'][-1])
                trials['+'.join(str(i+1) for i in regions)]=dict(best=rows[0] if rows else None,
                                                              quality_gate_passed=all(r['passed'] for r in gate['regions'] if r['region']-1 in regions))
        similarity_trials={}
        for count in range(2,len(enabled)+1):
            for regions in itertools.combinations(enabled,count):
                rr=[dict(r,enabled=i in regions) for i,r in enumerate(rules)]
                similarity_trials['+'.join(str(i+1) for i in regions)]=similarity_review(atlas,markers,rr)
        result['resolutions'][str(resolution)]=dict(quality_gate=gate,translation=trials,
                                                     similarity=similarity_trials)
        (output/'review.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(dict(resolution=resolution,gate=gate,
                             translation_maxima={k:v['best']['maximum'] if v['best'] else None for k,v in trials.items()},
                             similarity=similarity_trials),indent=2),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--analysis',type=Path,help='Use a separate offline atlas analysis directory')
    args=parser.parse_args();run(args.source,args.output,args.analysis)
