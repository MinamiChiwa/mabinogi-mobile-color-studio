"""Read saved settling probes; never capture a screen or send game input."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image
from scan_settling import ScanSettlingObserver


def read_rgb(path):
    return np.asarray(Image.open(path).convert('RGB'))


def review(source):
    source = Path(source)
    log = json.loads((source/'log.json').read_text(encoding='utf8'))
    scene = next(row for row in log if row.get('kind')=='sampling_ready')
    observer = ScanSettlingObserver(SimpleNamespace(**scene))
    previous = read_rgb(source/'max_sampling_board.png')
    rows = []
    for record in log:
        if record.get('kind')!='frame' or not record.get('name','').startswith('grid_'):
            continue
        name = record['name']
        timing = record.get('scan_timing',{})
        row = dict(frame=name, has_probes=False, eligible=False,
                   potential_saving_seconds=0., motion_observed=False)
        late = read_rgb(source/(name+'_board.png'))
        try:
            early = read_rgb(source/(name+'-settle-early.png'))
            check = read_rgb(source/(name+'-settle-check.png'))
        except OSError:
            row['reason']='probe_files_unavailable'
        else:
            comparisons=dict(early_to_check=observer.compare(early,check),
                             check_to_reference=observer.compare(check,late),
                             previous_to_reference=observer.compare(previous,late))
            valid=all(v['reason']=='compared' for v in comparisons.values())
            moved=valid and not comparisons['previous_to_reference']['equal']
            matched=valid and all(comparisons[k]['equal'] for k in ('early_to_check','check_to_reference'))
            times=timing.get('probe_times',[])
            separated=len(times)==2 and times[1]['start_seconds']-times[0]['end_seconds']>=.059
            eligible=bool(moved and matched and separated and not timing.get('fallback_reason'))
            row.update(has_probes=True, comparisons=comparisons,
                       motion_observed=bool(moved), pixels_equal=bool(matched),
                       full_board_equal=bool(np.array_equal(check,late)), eligible=eligible,
                       reason='compared', baseline_late_seconds=timing.get('baseline_late_seconds'),
                       potential_saving_seconds=(timing.get('potential_saving_seconds',0.)
                                                 if eligible else 0.))
        rows.append(row)
        previous=late
    return dict(source=str(source.resolve()), mode='offline_observation_review',
                frames=len(rows), compared=sum(r['has_probes'] for r in rows),
                eligible=sum(r['eligible'] for r in rows),
                potential_saving_seconds=sum(r['potential_saving_seconds'] for r in rows),
                all_material_pixels_identical=bool(len(rows)==48 and all(r['eligible'] for r in rows)),
                limitations=['No actual fast scan was executed.',
                             'One session does not establish a cross-device settling bound.',
                             'Full registration, atlas quality and game HEX validation remain required.'],
                rows=rows)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    result=review(args.source)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k!='rows'},indent=2))
