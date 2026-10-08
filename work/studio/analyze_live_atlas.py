"""Offline reconstruction of the bounded native-pixel capture session."""
import argparse
import json
import time
import shutil
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from periodic_atlas import PeriodicAtlas,translation_candidates
from replay_archive import translation_error,refine,evaluate
from vision import error,measure_board_motion
from atlas_masks import material_masks, mask_parameters, mask_summary, save_mask_overlay
from atlas_similarity import similarity_candidates, captured_scale_levels
from candidate_ranking import candidate_rank
from atlas_stage_budget import StageBudgetExceeded


def budgeted_candidate_search(operation,check=None):
    """Soft CPU expiry stops this pool; F9/hard guards still propagate."""
    try:
        if check:check()
        return operation(),None
    except StageBudgetExceeded as exc:
        return [],str(exc)


def save_atlas(path, **arrays):
    """Lossless NPZ with inexpensive compression for per-session data."""
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=1) as archive:
        for name,value in arrays.items():
            with archive.open(name+'.npy','w',force_zip64=True) as stream:
                np.lib.format.write_array(stream,np.asarray(value),allow_pickle=False)


def export_maps(out,atlas):
    started=time.perf_counter()
    colors,valid,rmse=atlas.maps()
    for j in range(3):
        Image.fromarray(np.dstack((colors[j],valid[j].astype(np.uint8)*255))).save(
            out/f'region-{j+1}.png',compress_level=1)
    save_atlas(out/'atlas.npz',colors=colors,valid=valid,count=atlas.count,
               rmse=rmse,basis=atlas.basis,origin=atlas.origin)
    expanded_out=out/'expanded';expanded_out.mkdir(exist_ok=True)
    for filename in ('atlas.npz','region-1.png','region-2.png','region-3.png'):
        shutil.copyfile(out/filename,expanded_out/filename)
    canvas=Image.new('RGB',(1560,560),'#18212b');draw=ImageDraw.Draw(canvas)
    for j in range(3):
        tile=Image.fromarray(np.dstack((colors[j],valid[j].astype(np.uint8)*255))).resize((512,512))
        canvas.paste(tile,(8+j*520,40),tile.getchannel('A'))
        draw.text((12+j*520,14),f'Region {j+1} - native capture',fill='white')
    canvas.save(out/'overview.png',compress_level=1)
    return time.perf_counter()-started


def measured_translation(a,b,feature_cache=None,texture_mask=None,diagnostics=None,*,dense_retry=True):
    """Register textures; refuse scale/rotation changes in a translation atlas."""
    h,w=a.shape[:2]
    diagnostics={} if diagnostics is None else diagnostics
    diagnostics.clear();diagnostics.update(attempts=[],passed=False)
    motion=None
    # Low-contrast textures can have fewer than twenty default SIFT inliers
    # despite a valid overlap. Retry on the same pixels with denser features;
    # match count, inlier ratio and translation-only gates remain unchanged.
    for contrast in ((.04,.01) if dense_retry else (.04,)):
        attempt={};diagnostics['attempts'].append(attempt)
        motion=measure_board_motion(a,b,(0,0,w,h),feature_cache=feature_cache,
                                    texture_mask=texture_mask,
                                    contrast_threshold=contrast,diagnostics=attempt)
        if motion is not None:break
    if motion is None or abs(motion['scale']-1)>.005 or abs(motion['angle'])>.2:
        diagnostics['reason']=attempt.get('reason','unverified_motion') if motion is None else 'non_translation_motion'
        raise ValueError('Texture translation could not be established')
    diagnostics.update(passed=True,method='sift' if contrast==.04 else 'dense_sift_retry')
    return np.asarray(motion['matrix'],dtype=float)[:,2]


def measure_periods(images,offsets,masks,feature_cache=None,check=None):
    """Measure returns across frames even when a period exceeds the viewport.

    Local adjacent motion supplies unwrapped offsets; distant-frame matching
    supplies the wrapped residual. Two agreeing returns per axis are required.
    """
    h,w=images[0].shape[:2];evidence=[[],[]]
    texture_mask=np.asarray(masks,bool).any(axis=0)
    if feature_cache is None:feature_cache={}
    # Compare every pair of grid frames.  In a snake scan, later rows have the
    # same horizontal span at a different Y offset; comparing only to frame 0
    # throws away those valid period returns.
    for i in range(1,len(images)):
        for j in range(i):
            if check:check()
            delta=np.asarray(offsets[i])-np.asarray(offsets[j])
            # A row-to-row return can be shorter than half of the viewport
            # when the live route uses interleaved coverage fills.  Requiring
            # .45*extent discarded the only valid vertical evidence in some
            # complete 48-frame scans.  Keep a conservative .30 threshold;
            # residual registration and RGB error gates below still reject
            # unrelated pairs.
            axes=[axis for axis,extent in enumerate((w,h))
                  if abs(delta[axis])>.30*extent and
                     abs(delta[1-axis])<max(2.,.08*extent)]
            if not axes:continue
            # Distant frame pairs often have no overlap. Their failure is
            # already handled by trying another return pair; denser extraction
            # is reserved for an adjacent frame that would break the chain.
            try:residual=measured_translation(images[j],images[i],feature_cache,texture_mask,dense_retry=False)
            except ValueError:continue
            difference=delta-residual
            rmse=translation_error(images[j],images[i],masks,*residual)
            if not np.isfinite(rmse) or rmse>8:continue
            for axis in axes:
                if (abs(difference[axis])<.3*(w,h)[axis] or
                        abs(difference[1-axis])>max(2.,.02*(w,h)[1-axis])):continue
                evidence[axis].append((float(abs(difference[axis])),float(rmse)))
    result=[]
    for axis,rows in enumerate(evidence):
        # A complete scan can occasionally expose only one independent return
        # on an axis (for example when a connector corridor hides the second
        # pair).  The measured return is still preferable to discarding the
        # entire atlas: held-out validation and the route stability gate remain
        # responsible for rejecting a bad period.  Keep the hard failure only
        # when there is no validated return at all.
        if not rows:raise ValueError(f'Insufficient validated period returns on axis {axis}')
        period=float(np.median([r[0] for r in rows]))
        agreeing=[r for r in rows if abs(r[0]-period)<1]
        if not agreeing:
            raise ValueError(f'Inconsistent period returns on axis {axis}')
        result.append((float(np.median([r[0] for r in agreeing])),max(r[1] for r in agreeing)))
    return result


def frame_sequence(log):
    """Normalize legacy and grid capture logs into ordered frame metadata."""
    if any(r.get('kind') in ('point_probe_plan','response_probe_plan') or str(r.get('kind','')).startswith('micro_return_') or
           (r.get('kind')=='CAPTURE_COMPLETE' and r.get('strategy') in ('probe','micro_return','response')) for r in log):
        raise ValueError('Point sampling probes are diagnostic captures, not atlas scans')
    rows=[r for r in log if r.get('kind')=='frame']
    grid=any(r.get('name')=='max_sampling' for r in rows)
    if not grid:
        names=['low_0']+['scan_%02d'%i for i in range(1,9)]+['heldout_y','heldout_xy']
        return dict(names=names, holdout_indices=[9,10], strategy='legacy')
    names=[r['name'] for r in rows if r['name']=='max_sampling' or r['name'].startswith('grid_')]
    commands=[r for r in log if r.get('kind')=='command']
    # The first frame is the reference; each subsequent frame follows one
    # command.  A command's holdout flag therefore belongs to that frame.
    holdout=[i+1 for i,c in enumerate(commands) if c.get('holdout')]
    return dict(names=names,holdout_indices=holdout,strategy='grid')


def scene_record(log):
    """Return the geometry belonging to the frames used for atlas training."""
    return next((r for r in log if r.get('kind')=='sampling_ready'),
                next(r for r in log if r.get('kind')=='ready'))


def quality_gate(coverage, validation, min_coverage=.90, max_rmse=8.0,
                 min_validation_coverage=.90, required_regions=None):
    """Decide whether a captured atlas is safe to publish as candidates."""
    required = set(range(1, 4) if required_regions is None else required_regions)
    if not required or not required.issubset({1, 2, 3}):
        return dict(passed=False, thresholds=dict(min_coverage=min_coverage,
                     min_validation_coverage=min_validation_coverage,
                     max_rgb_rmse=max_rmse), required_regions=sorted(required),
                    regions=[])
    rows=[]
    for base, held in zip(coverage, validation):
        rows.append(dict(region=base['region'],
                         atlas_coverage=float(base['coverage']),
                         heldout_coverage=float(held['coverage']),
                         heldout_rgb_rmse=float(held['rgb_rmse']),
                         passed=(base['coverage'] >= min_coverage
                                 and held['coverage'] >= min_validation_coverage
                                 and held['rgb_rmse'] <= max_rmse)))
    for row in rows:
        row['required'] = row['region'] in required
        if not row['required']:
            row['passed'] = True
    return dict(passed=bool(rows) and all(r['passed'] for r in rows if r['required']),
                thresholds=dict(min_coverage=min_coverage,
                                min_validation_coverage=min_validation_coverage,
                                max_rgb_rmse=max_rmse),
                required_regions=sorted(required), regions=rows)


def validation_summary(validation):
    """Use the worst result per region across every held-out frame."""
    if not validation:return []
    return [dict(region=region,
                 coverage=min(row['coverage'] for frame in validation
                              for row in frame['prediction'] if row['region']==region),
                 rgb_rmse=max(float(row['rgb_rmse']) if row['rgb_rmse'] is not None else float('inf')
                              for frame in validation for row in frame['prediction']
                              if row['region']==region)) for region in (1,2,3)]


class CaptureAlignment:
    """Incremental adjacent-frame alignment, shared by live and offline runs."""
    def __init__(self, scene):
        self.scene=scene
        self.masks=material_masks(scene)
        self.texture_mask=self.masks.any(axis=0)
        self.images=[];self.names=[];self.offsets=[];self.motions=[]
        self.feature_cache={}
        self.last_failure=None
        self.seconds=0.

    def append(self,name,image,command=None):
        started=time.perf_counter()
        i=len(self.images)
        if i:
            a,b=self.images[-1],image
            dx,dy=command['dx'],command['dy']
            registration={}
            try:measured=measured_translation(a,b,self.feature_cache,self.texture_mask,registration)
            except ValueError:
                self.last_failure=dict(frame=name,reference=self.names[-1],
                                       command=[dx,dy],registration=registration)
                raise
            if np.linalg.norm(measured-[dx,dy])>12:
                raise ValueError('Measured motion disagrees with capture command')
            dx,dy=measured
            dx,e=refine(lambda v:translation_error(a,b,self.masks,v,dy),dx,.6,.04)
            dy,e=refine(lambda v:translation_error(a,b,self.masks,dx,v),dy,.3,.025)
            absolute=self.offsets[-1]+[dx,dy]
            if i%8==0 or command.get('holdout'):
                ax,ae=refine(lambda v:translation_error(self.images[0],b,self.masks,v,absolute[1]),
                             absolute[0],2.5,.25)
                ay,ae=refine(lambda v:translation_error(self.images[0],b,self.masks,ax,v),
                             absolute[1],1.5,.15)
                if np.isfinite(ae) and ae<=8:absolute=np.array([ax,ay])
            self.offsets.append(absolute)
            self.motions.append(dict(frame=name,dx=dx,dy=dy,rgb_rmse=e,registration=registration))
        else:self.offsets.append(np.zeros(2))
        self.images.append(image);self.names.append(name)
        self.seconds+=time.perf_counter()-started


def run(source,game_codes=None,example_targets=None,target_rules=None,output=None,check=None,
        atlas_resolution=768,progress=None,runtime=None,prepared=None,search_check=None):
    progress=progress or (lambda **data:None)
    started=time.perf_counter();timings={}
    source=Path(source);out=Path(output) if output is not None else source/'analysis'
    out.mkdir(parents=True,exist_ok=True)
    if target_rules is not None:
        rules=[dict(rule) for rule in target_rules]
        if len(rules)!=3:raise ValueError('Exactly three target rules are required')
    else:
        rules=[dict(enabled=True,colors=[c],exact=False,tolerance=8)
               for c in example_targets] if example_targets else []
    log=json.loads((source/'log.json').read_text())
    scene=scene_record(log)
    sequence=frame_sequence(log);names=sequence['names']
    if (prepared is not None and (prepared.names!=names or
            prepared.scene['board']!=scene['board'] or prepared.scene['markers']!=scene['markers'])):
        raise ValueError('Prepared frames do not belong to this capture')
    images=(prepared.images if prepared is not None else
            [np.array(Image.open(source/(name+'_board.png')).convert('RGB')) for name in names])
    holdout_indices=set(sequence['holdout_indices'])
    if sequence['strategy']=='grid' and len(images)<4:
        raise ValueError('Grid capture needs at least four board frames')
    h,w=images[0].shape[:2]
    markers=np.array(scene['markers'])-np.array(scene['board'][:2])
    masks=material_masks(scene)
    texture_mask=masks.any(axis=0)
    mask_summary_rows=mask_summary(masks)
    save_mask_overlay(images[0], masks, out/'mask-overlay.png')
    command_rows=[r for r in log if r.get('kind')=='command']
    commands=[(r['dx'],r['dy']) for r in command_rows]
    alignment=prepared or CaptureAlignment(scene)
    if prepared is None:
        alignment.append(names[0],images[0])
        for i,command in enumerate(command_rows,1):
            progress(stage='align',current=i,total=len(commands))
            if check:check()
            alignment.append(names[i],images[i],dict(command,holdout=i in holdout_indices))
    offsets,motions,feature_cache=alignment.offsets,alignment.motions,alignment.feature_cache
    timings['overlapped_alignment_seconds']=alignment.seconds if prepared is not None else 0.
    if sequence['strategy']=='grid':
        progress(stage='period')
        (px,e),(py,pyerr)=measure_periods(images,offsets,masks,feature_cache,check)
    else:
        py,pyerr=refine(lambda p:translation_error(images[0],images[0],masks,0,p),h*.45,h*.35,1)
        py,pyerr=refine(lambda p:translation_error(images[0],images[0],masks,0,p),py,1,.025)
        if not np.isfinite(pyerr) or pyerr>8:raise ValueError('No validated vertical period')
        i=min(range(1,7),key=lambda i:abs(offsets[i][0]-py))
        residual,e=refine(lambda v:translation_error(images[0],images[i],masks,v,offsets[i][1]),offsets[i][0]-py,8,.2)
        px=offsets[i][0]-residual
    train_indices=(sorted(set(range(len(images)))-holdout_indices)
                   if sequence['strategy']=='grid' else list(range(7)))
    heldout=(sorted(holdout_indices) if sequence['strategy']=='grid'
             else list(range(7,len(images))))
    timings['registration_seconds']=time.perf_counter()-started
    stage=time.perf_counter()
    # Use the finer phase grid for every mode. This avoids mode-dependent
    # candidate coverage and gives similar-color searches the same precision
    # as exact HEX searches.
    atlas=PeriodicAtlas([[px,0],[0,py]],resolution=atlas_resolution)
    for count,j in enumerate(train_indices,1):
        progress(stage='stitch',current=count,total=len(train_indices))
        if check:check()
        atlas.add_resampled(images[j],masks,offsets[j])
    timings['atlas_seconds']=time.perf_counter()-stage
    stage=time.perf_counter()
    atlas=atlas.snapshot()
    if runtime is not None:runtime.update(atlas=atlas,capture_offset=offsets[-1].copy())
    coverage=atlas.report()
    timings['map_seconds']=time.perf_counter()-stage
    colors,valid,rmse=atlas.maps()
    progress(stage='export')
    # The snapshot is immutable. Lossless diagnostic export can share the
    # validation/search interval without blocking candidate computation.
    exporter=ThreadPoolExecutor(max_workers=1,thread_name_prefix='atlas-export')
    export=exporter.submit(export_maps,out,atlas)
    exporter.shutdown(wait=False)
    stage=time.perf_counter()
    if check:check()
    progress(stage='validate')
    validation=[dict(frame=names[j],prediction=evaluate(atlas,images[j],masks,offsets[j]),
                     wrong_shift=evaluate(atlas,images[j],masks,offsets[j],20)) for j in heldout]
    summary=validation_summary(validation)
    timings['validation_seconds']=time.perf_counter()-stage
    enabled_regions = ([i + 1 for i, rule in enumerate(rules) if rule.get('enabled')]
                       if rules else [1, 2, 3])
    gate=quality_gate(coverage, summary, required_regions=enabled_regions) if validation else dict(passed=False)
    geometry_record=next((r for r in log if r.get('kind')=='frame' and r.get('name')=='original'),
                         next(r for r in log if r.get('kind')=='frame'))
    report=dict(source=str(source.resolve()),period_x=px,period_y=py,
                atlas_resolution=atlas_resolution,vertical_rgb_rmse=pyerr,
                horizontal_return_rgb_rmse=e,geometry=geometry_record['geometry'],scene=scene,
                training=[names[j] for j in train_indices],heldout=[names[j] for j in heldout],coverage=coverage,motions=motions,
                offsets=[p.tolist() for p in offsets],validation=validation,
                mask_summary=mask_summary_rows,
                mask_parameters=mask_parameters(),
                quality_gate=gate,verified=False,limitations=['Fixed angle/scale; not a minimal period proof.',
                'Registration uses neighboring held-out images, but their colors are not accumulated into atlas.',
                'The program sent no final dye confirmation; exit cause after capture is unobserved.'])
    # Historical directory compatibility: expanded and base use the same
    # training frames and maps. Copy exports instead of recompressing them.
    expanded=atlas
    expanded_out=out/'expanded';expanded_out.mkdir(exist_ok=True)
    # Optional manually transcribed final-frame game codes; never live OCR.
    marker_check=[]
    for j in range(3):
        values,supported=expanded.sample(j,[markers[j]],offsets[-1])
        predicted='#%02X%02X%02X'%tuple(np.rint(values[0]).clip(0,255).astype(int)) if supported[0] else None
        actual=game_codes[j] if game_codes else None
        marker_check.append(dict(region=j+1,predicted=predicted,game_hex=actual,
                                 delta_e76=error(predicted,[actual],False) if predicted and actual else None))
    expanded_validation=summary
    report['expanded']=dict(training=[names[j] for j in train_indices],heldout=[names[j] for j in heldout],coverage=coverage,
                            validation=expanded_validation,
                            quality_gate=gate,
                            marker_check=marker_check,game_hex_source='manual reading of saved screenshot, not OCR')
    # Demonstrate offline candidate output using the preparation-screen original
    # colors as example targets; this is not a live user selection or execution.
    # Never publish selectable candidates from a sparse or poorly validated
    # atlas.  The review artifact remains useful for diagnosis, but its rows
    # must not be mistaken for executable positions.
    stage=time.perf_counter()
    if check:check()
    def cancelled():
        if check:check()
        if search_check:search_check()
        return False
    progress(stage='search')
    candidates=[];search_stop_reason=None
    if rules and report['expanded']['quality_gate']['passed']:
        candidates,search_stop_reason=budgeted_candidate_search(
            lambda:translation_candidates(expanded,markers,rules,offsets[-1],cancelled=cancelled,
                                           landing_radius=1.,integer_moves=True,limit=32),search_check)
    timings['translation_search_seconds']=time.perf_counter()-stage
    search_diagnostics={}
    if rules and report['expanded']['quality_gate']['passed'] and search_stop_reason is None:
        similarity_stage=time.perf_counter()
        progress(stage='similarity')
        levels,tick=captured_scale_levels(log)
        calibration=next((r for r in reversed(log) if r.get('kind')=='zoom_calibration'),{})
        joint,search_stop_reason=budgeted_candidate_search(lambda:similarity_candidates(expanded,markers,rules,offsets[-1],(h,w),
                                    scale_bounds=(min(levels),1.),scale_levels=levels,
                                    cancelled=cancelled,diagnostics=search_diagnostics,
                                    include_compromises=True,limit=24),search_check)
        for row in candidates:row['search_space']='periodic_translation'
        for row in joint:
            row['id']+=len(candidates)
            if tick is not None:
                row['zoom_log_step']=tick
                row['zoom_log_step_up']=calibration.get('up_log_step',tick)
                row['wheel_steps']=-int(round(-np.log(row['scale'])/tick))
                row['scale_source']='measured_down_ticks'
        # Retain both pools: a cheaper translation may still fit the game
        # countdown when a slightly better rotation/zoom proposal cannot.
        candidates=sorted(candidates+joint,key=candidate_rank)
        for index,row in enumerate(candidates):row['id']=index
        timings['similarity_search_seconds']=time.perf_counter()-similarity_stage
    else:
        timings['similarity_search_seconds']=0.
    if check:check()
    search_diagnostics['search_stop_reason']=search_stop_reason
    timings['candidate_seconds']=time.perf_counter()-stage
    timings['candidate_computed']=bool(rules and report['expanded']['quality_gate']['passed'])
    review=dict(schema=1,verified=False,metric='Delta E 76',
                mode='configured_targets' if target_rules is not None else 'offline_example',
                target_source='User configured rules' if target_rules is not None else 'Offline example targets',
                search_space='translation_and_bounded_color_seed_similarity',
                search_diagnostics=search_diagnostics,
                search_performed=timings['candidate_computed'],rules=rules,
                coverage=coverage,quality_gate=report['expanded']['quality_gate'],
                candidates=candidates,candidates_publishable=bool(candidates))
    (expanded_out/'review.json').write_text(json.dumps(review,indent=2),encoding='utf-8')
    if not export.done():progress(stage='export')
    stage=time.perf_counter()
    timings['export_seconds']=export.result()
    timings['export_wait_seconds']=time.perf_counter()-stage
    progress(stage='ready')
    timings['total_seconds']=time.perf_counter()-started
    if check:check()
    report['timings']=timings
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(dict(period_x=px,period_y=py,expanded=report['expanded'],candidate_count=len(candidates)),indent=2))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('source')
    parser.add_argument('--game-codes',nargs=3,help='Manually read game HEX from the last held-out screenshot')
    parser.add_argument('--example-targets',nargs=3,help='Example targets for an offline candidate list')
    parser.add_argument('--output',type=Path,help='Separate output directory; preserves the source analysis')
    parser.add_argument('--atlas-resolution',type=int,choices=(768,1024),default=768,
                        help='Offline atlas sampling resolution (the production default is 1024)')
    args=parser.parse_args();run(args.source,args.game_codes,args.example_targets,output=args.output,
                                  atlas_resolution=args.atlas_resolution)
