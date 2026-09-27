"""Offline candidate/landing review of a saved current-session atlas.

Reads heldout game HEX for evaluation only. No game input or fabricated frames.
Example targets are benchmarks, not a replacement for the user's configuration.
"""
import argparse
import json
import time
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from atlas_trial import load_atlas
from periodic_atlas import translation_candidates
from vision import configure_ocr, read_codes, error


def landing_review(atlas, markers, rules, current, candidate):
    # Integer mouse commands plus a one-pixel neighborhood. This is atlas
    # sensitivity, not a guarantee of measured input precision or game HEX.
    move = np.rint([candidate['dx'], candidate['dy']])
    rows = []
    for offset in ((0,0),(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)):
        codes = []; distances = []; supported = True
        for i, rule in enumerate(rules):
            if not rule['enabled']:
                codes.append(None); distances.append(None); continue
            values, valid = atlas.sample(i, [markers[i]], current+move+offset)
            code = '#%02X%02X%02X'%tuple(np.rint(values[0]).clip(0,255).astype(int))
            supported &= bool(valid[0]); codes.append(code)
            distances.append(error(code, rule['colors'], False))
        rows.append(dict(offset=offset, supported=supported, colors=codes,
                         maximum=max(v for v in distances if v is not None)))
    return dict(rounded_move=move.tolist(), center=rows[0],
                neighborhood_supported=all(v['supported'] for v in rows),
                neighborhood_maximum=max(v['maximum'] for v in rows))


def run(analysis, output, landing_radius=1.):
    analysis=Path(analysis); output=Path(output); output.mkdir(parents=True,exist_ok=False)
    report=json.loads((analysis/'report.json').read_text(encoding='utf-8'))
    source=Path(report['source']); log=json.loads((source/'log.json').read_text(encoding='utf-8'))
    names=['max_sampling']+[v['name'] for v in log if v['kind']=='frame' and v['name'].startswith('grid_')]
    offsets=dict(zip(names,report['offsets']))
    scene=report['scene']; markers=np.array(scene['markers'])-scene['board'][:2]
    current=np.array(report['offsets'][-1]); atlas=load_atlas(analysis/'atlas.npz').snapshot()
    configure_ocr(strict=True)
    checks=[]; cards=Image.new('RGB',(810,len(report['heldout'])*210),'#18212b'); draw=ImageDraw.Draw(cards)
    for row,name in enumerate(report['heldout']):
        image=np.array(Image.open(source/(name+'.png')).convert('RGB'))
        codes=read_codes(image,scene['cards'],scene['markers']); predicted=[]
        for i,(x,y,w,h) in enumerate(scene['cards']):
            values,valid=atlas.sample(i,[markers[i]],offsets[name])
            code='#%02X%02X%02X'%tuple(np.rint(values[0]).clip(0,255).astype(int)) if valid[0] else None
            predicted.append(dict(region=i+1,predicted=code,game_hex=codes[i],
                delta_e76=error(code,[codes[i]],False) if code and codes[i] else None))
            cards.paste(Image.fromarray(image[y:y+h,x:x+w]).resize((160,160)),(i*270+8,row*210+25))
            draw.text((i*270+8,row*210+5),f'{name} R{i+1}',fill='white')
            draw.text((i*270+8,row*210+188),f'OCR: {codes[i]}',fill='white')
        checks.append(dict(frame=name,checks=predicted))
    cards.save(output/'heldout-cards.png')
    cases=[('black-single',[True,False,False],['#202020']*3),
           ('black-pair',[True,False,True],['#202020']*3),
           ('black-triple',[True]*3,['#202020']*3)]
    for check in checks:
        codes=[v['game_hex'] for v in check['checks']]
        if all(codes):cases.append((check['frame']+'-triple',[True]*3,codes))
    result=dict(source=str(source),analysis=str(analysis),game_input_sent=False,
                timing_scope='Serial offline search; excludes live capture, gestures, OCR and verification.',
                target_scope='Dark example plus heldout-color feasibility probes; not user-configured targets.',
                heldout_checks=checks,cases=[])
    for label,enabled,targets in cases:
        rules=[dict(enabled=enabled[i],colors=[targets[i]],exact=False,tolerance=8.) for i in range(3)]
        started=time.perf_counter(); candidates=translation_candidates(atlas,markers,rules,current,
                                                                        landing_radius=landing_radius)
        seconds=time.perf_counter()-started
        rows=[dict(**v,landing=landing_review(atlas,markers,rules,current,v)) for v in candidates]
        result['cases'].append(dict(name=label,rules=rules,search_seconds=seconds,
                                   accepted_count=sum(v['accepted'] for v in rows),candidates=rows))
        (output/'report.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(label,'accepted',sum(v['accepted'] for v in rows),'seconds',round(seconds,3),
              'best',round(rows[0]['maximum'],3) if rows else None,
              'landing',round(rows[0]['landing']['neighborhood_maximum'],3) if rows else None,flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('analysis',type=Path); parser.add_argument('output',type=Path)
    parser.add_argument('--landing-radius',type=float,default=1.)
    args=parser.parse_args(); run(args.analysis,args.output,args.landing_radius)
