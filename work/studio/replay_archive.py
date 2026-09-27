"""Offline reconstruction experiment on round-two archived frames, no input.

Historical mask geometry is intentionally confined to this replay adapter.
Horizontal period uses measured motion plus a direct one-period return match.
"""
import argparse
import csv
import json
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
from periodic_atlas import PeriodicAtlas


def archive_masks(shape):
    h,w=shape[:2]; y,x=np.mgrid[:h,:w]; u=x*384/w
    clean=(y>24*h/387)&(y<h-24*h/387)
    for center in (60,191,324):clean &= abs(u-center)>=10
    return np.array([clean&(u>lo)&(u<hi) for lo,hi in ((8,121),(134,250),(266,377))])


def translation_error(a,b,masks,dx,dy):
    errors=[]
    for mask in masks:
        y,x=np.where(mask[::5,::5]);x=x*5;y=y*5
        xx=(x+dx).astype(np.float32);yy=(y+dy).astype(np.float32)
        good=(xx>=0)&(xx<a.shape[1]-1)&(yy>=0)&(yy<a.shape[0]-1)
        good &= mask[np.clip(np.rint(yy).astype(int),0,a.shape[0]-1),np.clip(np.rint(xx).astype(int),0,a.shape[1]-1)]
        if good.sum()<100:continue
        actual=cv2.remap(b,xx[good,None],yy[good,None],cv2.INTER_LINEAR).reshape(-1,3)
        errors.append((a[y[good],x[good]].astype(float)-actual)**2)
    return float(np.sqrt(np.concatenate(errors).mean())) if errors else float('inf')


def refine(fn,initial,radius,step):
    best=min(((fn(v),v) for v in np.arange(initial-radius,initial+radius+step/2,step)),key=lambda p:p[0])
    return best[1],best[0]


def evaluate(atlas,image,masks,translation,wrong_shift=0):
    results=[]
    for i,mask in enumerate(masks):
        y,x=np.where(mask[::3,::3]);x=x*3;y=y*3
        predicted,good=atlas.sample(i,np.column_stack((x,y)),np.array(translation)+[wrong_shift,0])
        diff=predicted[good].astype(float)-image[y[good],x[good]]
        results.append(dict(region=i+1,coverage=float(good.mean()),
                            rgb_rmse=float(np.sqrt(np.mean(diff**2))) if good.any() else None))
    return results


def run(source,output):
    source=Path(source);output=Path(output);output.mkdir(parents=True,exist_ok=True)
    rows=list(csv.DictReader((source/'image_motion_v2.tsv').open(encoding='utf-8-sig'),delimiter='\t'))[:72]
    images=[np.array(Image.open(source/r['filename']).convert('RGB')) for r in rows]
    masks=archive_masks(images[0].shape);width=images[0].shape[1]
    initial=710.325*width/1382 # search seed only; measured below on round-two frame
    p,err=refine(lambda v:translation_error(images[0],images[0],masks,0,v),initial,8,.25)
    p,err=refine(lambda v:translation_error(images[0],images[0],masks,0,v),p,.3,.025)
    translations=[0.];registration=[]
    for i in range(1,len(images)):
        guess=float(rows[i]['dx_at384'])*width/384
        shift,error=refine(lambda v:translation_error(images[i-1],images[i],masks,v,0),guess,2,.2)
        shift,error=refine(lambda v:translation_error(images[i-1],images[i],masks,v,0),shift,.2,.025)
        translations.append(translations[-1]+shift)
        registration.append(dict(frame=rows[i]['filename'],measured_dx=shift,rgb_rmse=error))
    # Select training frames near the first return. The vertical period only
    # identifies the return neighborhood; direct RGB matching measures residual.
    options=[i for i in range(2,len(images),2) if abs(translations[i]-p)<60]
    if not options:raise ValueError('No independent horizontal return in replay range')
    horizontal=[]
    for i in options:
        residual,error=refine(lambda v:translation_error(images[0],images[i],masks,v,0),translations[i]-p,4,.1)
        horizontal.append(dict(frame=rows[i]['filename'],period=translations[i]-residual,residual=residual,rgb_rmse=error))
    px=float(np.median([row['period'] for row in horizontal]))
    atlas=PeriodicAtlas([[px,0],[0,p]],resolution=512)
    train=list(range(0,len(rows),2));holdout=list(range(1,len(rows),2))
    for i in train:atlas.add_resampled(images[i],masks,(translations[i],0))
    colors,valid,rmse=atlas.maps()
    for i in range(3):Image.fromarray(np.dstack((colors[i],valid[i].astype(np.uint8)*255))).save(output/f'region-{i+1}.png')
    np.savez_compressed(output/'atlas.npz',colors=colors,valid=valid,rmse=rmse,count=atlas.count,basis=atlas.basis)
    validation=[dict(frame=rows[i]['filename'],prediction=evaluate(atlas,images[i],masks,(translations[i],0)),
                     wrong_shift=evaluate(atlas,images[i],masks,(translations[i],0),20)) for i in holdout]
    summary=[]
    for region in range(3):
        summary.append(dict(region=region+1,
            coverage=atlas.report()[region]['coverage'],
            heldout_coverage=float(np.mean([r['prediction'][region]['coverage'] for r in validation])),
            heldout_rgb_rmse=float(np.mean([r['prediction'][region]['rgb_rmse'] for r in validation])),
            wrong_shift_rgb_rmse=float(np.mean([r['wrong_shift'][region]['rgb_rmse'] for r in validation]))))
    report=dict(source=str(source.resolve()),frame_size=list(images[0].shape[:2]),
        vertical_period=p,vertical_rgb_rmse=err,horizontal_period=px,horizontal_returns=horizontal,
        input_type='historical resized continuous frames, not native-resolution color ground truth',
        training_frames=[rows[i]['filename'] for i in train],heldout_frames=[rows[i]['filename'] for i in holdout],
        summary=summary,registration=registration,validation=validation,
        limitations=['Adjacent held-out frames share the same session and trajectory.',
                     'Horizontal return search uses vertical period as a neighborhood seed; no proof of fundamental period.',
                     'Uncorrected cumulative registration drift and resized screenshots limit color accuracy.',
                     'Masks are historical geometry, never use for live capture.'])
    (output/'replay.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(vertical_period=p,horizontal_period=px,vertical_rgb_rmse=err,summary=summary),indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('source');parser.add_argument('output')
    args=parser.parse_args();run(args.source,args.output)
