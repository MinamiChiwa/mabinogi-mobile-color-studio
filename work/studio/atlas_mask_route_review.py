"""Evaluate extra capture positions using masks only, without inventing colors.

The result estimates phase-grid support from capture geometry. It is not a
reconstruction, registration test, held-out color test, or live route claim.
"""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

from atlas_masks import material_masks, mask_parameters, mask_summary
from analyze_live_atlas import frame_sequence
from periodic_atlas import PeriodicAtlas


def supplemental_positions(board):
    """Candidate X offsets chosen to break the old 100px mask-phase aliases."""
    left, top, right, bottom = map(float, board)
    width, height = right-left, bottom-top
    return [
        dict(name='row0_x10', translation=[round(width*.10), 0]),
        dict(name='row0_x90', translation=[round(width*.90), 0]),
        dict(name='row0_x130', translation=[round(width*1.30), 0]),
        dict(name='row2_x50_y80', translation=[round(width*.50), round(height*.80)]),
    ]


def _support(masks, shape, basis, translations, resolution):
    height, width = shape
    atlas=PeriodicAtlas(basis,resolution=resolution)
    blank=np.zeros((height,width,3),dtype=np.uint8)
    for translation in translations:
        atlas.add_resampled(blank,masks,translation)
    return atlas


def review(source, analysis, output):
    source=Path(source);analysis=Path(analysis);output=Path(output)
    output.mkdir(parents=True,exist_ok=False)
    report=json.loads((analysis/'report.json').read_text(encoding='utf-8'))
    log=json.loads((source/'log.json').read_text(encoding='utf-8'))
    scene=next(row for row in log if row.get('kind')=='sampling_ready')
    masks=material_masks(scene)
    names=['max_sampling']+[row['name'] for row in log
        if row.get('kind')=='frame' and row.get('name','').startswith('grid_')]
    holdout=set(frame_sequence(log)['holdout_indices'])
    offset_by_name=dict(zip(names,report['offsets']))
    training=[name for i,name in enumerate(names) if i not in holdout]
    offsets=[offset_by_name[name] for name in training]
    extras=supplemental_positions(scene['board'])
    extra_offsets=[row['translation'] for row in extras]
    shape=masks.shape[1:]
    bases=[[report['period_x'],0],[0,report['period_y']]]
    results={}
    for resolution in (768,1024):
        baseline=_support(masks,shape,bases,offsets,resolution)
        augmented=_support(masks,shape,bases,offsets+extra_offsets,resolution)
        results[str(resolution)]=dict(
            existing_mask_only_coverage=[float(v) for v in (baseline.count>0).mean(axis=(1,2))],
            with_four_extra_mask_only_coverage=[float(v) for v in (augmented.count>0).mean(axis=(1,2))],
            extra_frames=extras,
            game_input_sent=False,
            color_pixels_simulated=False,
        )
    result=dict(source=str(source.resolve()),analysis=str(analysis.resolve()),
        game_input_sent=False,mask_parameters=mask_parameters(),
        masks=mask_summary(masks),training_frames=training,
        heldout_frames=[names[i] for i in sorted(holdout)],
        period_basis=bases,extra_positions=extras,resolutions=results,
        limitations=[
            'Only binary mask support is accumulated; no pixel values are synthesized.',
            'Extra positions are analytical proposals, not captured or registered game frames.',
            'The six original held-out frames stay independent and are not used as training colors.',
            'A future run must still pass real image registration, coverage, held-out RGB and game HEX checks.',
        ])
    (output/'report.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('analysis',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args();review(args.source,args.analysis,args.output)
