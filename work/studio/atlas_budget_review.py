"""Read-only comparison of deterministic capture subsets from two saved sessions.

Every variant retains all original holdouts. Geometry is remeasured using only
retained images, including holdout texture; heldout colors never enter the map.
No changed capture trajectory or live timing is claimed by this replay.
"""
import argparse
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import time
import numpy as np
from PIL import Image
from periodic_atlas import PeriodicAtlas
from analyze_live_atlas import (frame_sequence,scene_record,measured_translation,
                               measure_periods,quality_gate,validation_summary)
from replay_archive import translation_error,refine,evaluate
from vision import error
from atlas_masks import material_masks


def subset_indices(log,variant):
    sequence=frame_sequence(log)
    if sequence['strategy']!='grid':raise ValueError('Grid captures required')
    holdout=set(sequence['holdout_indices'])
    commands=[r for r in log if r['kind']=='command']
    keep={0}
    for index,row in enumerate(commands,1):
        if variant=='full':selected=True
        elif variant=='columns_02467':selected=row['column'] in (0,2,4,6,7)
        elif variant=='rows_024':selected=row['row'] in (0,2,4)
        elif variant=='rows_0234':selected=row['row'] in (0,2,3,4)
        else:raise ValueError('Unknown variant')
        if selected:keep.add(index)
    training=sorted(keep-holdout)
    return training,sorted(holdout),sorted(keep|holdout)


def load_capture(source):
    source=Path(source);log=json.loads((source/'log.json').read_text())
    scene=scene_record(log);sequence=frame_sequence(log);names=sequence['names']
    images=[np.array(Image.open(source/(name+'_board.png')).convert('RGB')) for name in names]
    h,w=images[0].shape[:2]
    markers=np.array(scene['markers'])-scene['board'][:2];spacing=markers[1,0]-markers[0,0]
    masks=material_masks(scene)
    return dict(log=log,names=names,images=images,markers=markers,masks=masks,source=source)


def measure_subset(data,retained,holdout):
    images=data['images'];masks=data['masks'];cache={};offsets={0:np.zeros(2)};motions=[]
    commands=[r for r in data['log'] if r['kind']=='command']
    for previous,index in zip(retained,retained[1:]):
        a,b=images[previous],images[index]
        command=np.sum([[r['dx'],r['dy']] for r in commands[previous:index]],axis=0)
        try:measured=measured_translation(a,b,cache,masks.any(axis=0))
        except ValueError as exc:
            raise ValueError(f'Retained-frame {previous}->{index}, command hint {command.tolist()}: {exc}') from exc
        # Commands constrain aliases but are never used as measured offsets.
        if np.linalg.norm(measured-command)>12:
            raise ValueError(f'Unverified retained-frame motion {previous}->{index}')
        dx,dy=measured
        dx,e=refine(lambda v:translation_error(a,b,masks,v,dy),dx,.6,.04)
        dy,e=refine(lambda v:translation_error(a,b,masks,dx,v),dy,.3,.025)
        absolute=offsets[previous]+[dx,dy]
        if index%8==0 or index in holdout:
            ax,ae=refine(lambda v:translation_error(images[0],b,masks,v,absolute[1]),absolute[0],2.5,.25)
            ay,ae=refine(lambda v:translation_error(images[0],b,masks,ax,v),absolute[1],1.5,.15)
            if np.isfinite(ae) and ae<=8:absolute=np.array([ax,ay])
        offsets[index]=absolute
        motions.append(dict(previous=previous,index=index,measured=[dx,dy],rgb_rmse=e))
    periods=measure_periods([images[i] for i in retained],[offsets[i] for i in retained],masks,cache)
    return offsets,periods,motions


def replay_variant(data,variant,codes,known_geometry=None):
    started=time.perf_counter()
    training,holdout,retained=subset_indices(data['log'],variant)
    result=dict(variant=variant,training_count=len(training),captured_count=len(retained),
                training=[data['names'][i] for i in training],
                holdout=[data['names'][i] for i in holdout],
                retained_indices=retained,live_validated=False,
                validation_geometry_uses_heldout_texture=True)
    stage=time.perf_counter()
    try:
        if known_geometry is None:offsets,periods,motions=measure_subset(data,retained,holdout)
        else:
            offsets={int(k):np.asarray(v) for k,v in known_geometry['offsets'].items()}
            periods=known_geometry['periods'];motions=[]
            result['geometry_source']='Full trajectory, including discarded frames: color ablation only, not executable reduced capture'
    except ValueError as exc:
        result.update(error=str(exc),geometry_passed=False,total_seconds=time.perf_counter()-started)
        return result
    result.update(geometry_passed=True,periods=periods,motions=motions,
                  registration_seconds=time.perf_counter()-stage,
                  offsets={str(k):v.tolist() for k,v in offsets.items()})
    atlas=PeriodicAtlas([[periods[0][0],0],[0,periods[1][0]]],resolution=768)
    stage=time.perf_counter()
    for i in training:atlas.add_resampled(data['images'][i],data['masks'],offsets[i])
    atlas=atlas.snapshot();coverage=atlas.report()
    result['atlas_and_maps_seconds']=time.perf_counter()-stage
    stage=time.perf_counter()
    validation=[dict(frame=data['names'][i],prediction=evaluate(atlas,data['images'][i],data['masks'],offsets[i])) for i in holdout]
    result['validation_seconds']=time.perf_counter()-stage
    summary=validation_summary(validation)
    markers=[]
    for i in holdout:
        name=data['names'][i]
        for region in range(3):
            values,supported=atlas.sample(region,[data['markers'][region]],offsets[i])
            predicted='#%02X%02X%02X'%tuple(np.rint(values[0]).clip(0,255).astype(int)) if supported[0] else None
            actual=codes.get(name,[None]*3)[region]
            markers.append(dict(frame=name,region=region+1,predicted=predicted,game_hex=actual,
                                delta_e76=error(predicted,[actual],False) if predicted and actual else None))
    by_region=[]
    for region in (1,2,3):
        values=[r['delta_e76'] for r in markers if r['region']==region and r['delta_e76'] is not None]
        by_region.append(dict(region=region,supported=len(values),total=len(holdout),
                              maximum=max(values) if values else None))
    result.update(coverage=coverage,validation=validation,validation_summary=summary,
                  quality_gate=quality_gate(coverage,summary),marker_checks=markers,
                  marker_summary=by_region,total_seconds=time.perf_counter()-started)
    return result


def benchmark_analyzers(sources,output,repeats):
    import analyze_live_atlas as optimized
    spec=importlib.util.spec_from_file_location('analysis_baseline',output/'analyze_baseline.py')
    baseline=importlib.util.module_from_spec(spec);spec.loader.exec_module(baseline)
    rows=[]
    for label,source,_codes in sources:
        reports={}
        for repeat in range(repeats):
            order=[('baseline',baseline),('optimized',optimized)]
            if repeat%2:order.reverse()
            for name,module in order:
                folder=output/f'{label}-{name}-{repeat}'
                with contextlib.redirect_stdout(io.StringIO()):
                    report=module.run(source,output=folder)
                reports[name]=report
                rows.append(dict(session=label,implementation=name,repeat=repeat,timings=report['timings']))
        # Exact geometry, predictions, validity, diagnostics and exports.
        comparison={}
        for key in ('period_x','period_y','offsets','coverage','validation','expanded','quality_gate'):
            comparison[key]=reports['baseline'][key]==reports['optimized'][key]
        for filename in ('atlas.npz','expanded/atlas.npz'):
            a=np.load(output/f'{label}-baseline-{repeats-1}'/filename)
            b=np.load(output/f'{label}-optimized-{repeats-1}'/filename)
            comparison[filename]=a.files==b.files and all(np.array_equal(a[k],b[k]) for k in a.files)
        (output/f'{label}-equivalence.json').write_text(json.dumps(comparison,indent=2))
        if not all(comparison.values()):raise AssertionError(f'Numerical regression in {label}: {comparison}')
        print(label,'equivalence',comparison,flush=True)
        (output/'timings.json').write_text(json.dumps(rows,indent=2))
    return rows


def main(output,repeats=2):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    sources=[('new',Path('outputs/atlas-capture-20260926-113839-673'),
              Path('outputs/review-20260926-113839/all-codes.json')),
             ('old',Path('atlas_capture_2026-09-24_2141'),
              Path('outputs/transfer-validation-20260926/old-verified-codes.json'))]
    if repeats:benchmark_analyzers(sources,output,repeats)
    all_results={}
    for label,source,code_path in sources:
        data=load_capture(source);codes=json.loads(code_path.read_text())
        if 'codes' in codes:codes=codes['codes']
        variants=[];ablations=[];baseline=None
        for variant in ('full','columns_02467','rows_024','rows_0234'):
            result=replay_variant(data,variant,codes);variants.append(result)
            if variant=='full':baseline=result
            elif baseline.get('geometry_passed'):
                ablation=replay_variant(data,variant,codes,known_geometry=baseline)
                ablations.append(ablation)
                (output/f'{label}-color-ablations.json').write_text(json.dumps(ablations,indent=2))
            print(label,variant,json.dumps({k:result[k] for k in ('training_count','captured_count','geometry_passed','total_seconds')},ensure_ascii=False),flush=True)
            if result.get('geometry_passed'):print(result['quality_gate'],flush=True)
            (output/f'{label}-subsets.json').write_text(json.dumps(variants,indent=2))
        all_results[label]=variants
    return all_results


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path);parser.add_argument('--repeats',type=int,default=2)
    args=parser.parse_args();main(args.output,args.repeats)
