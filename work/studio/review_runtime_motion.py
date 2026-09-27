"""Read-only replay of archived capture and failed execution registrations."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from time import perf_counter

import numpy as np
from PIL import Image

from atlas_runtime import motion


def replay_pair(before, after, scene, command=None):
    diagnostics={}
    start=perf_counter()
    result=motion(before,after,scene,diagnostics)
    row=dict(result=result,diagnostics=diagnostics,seconds=perf_counter()-start)
    if command is not None:
        row['command']=command
        if result is not None:
            row['translation_error']=float(np.linalg.norm(np.array(result['matrix'])[:,2]-command))
    return row


def replay(folder):
    log=json.loads((folder/'log.json').read_text(encoding='utf-8'))
    scene=SimpleNamespace(**next(e for e in log if e['kind']=='sampling_ready'))
    commands=[e for e in log if e['kind']=='command']
    names=[e['name'] for e in log if e['kind']=='frame' and e['name'].startswith('grid_')]
    previous=np.array(Image.open(folder/'max_sampling.png').convert('RGB'))
    pairs=[]
    for name,command in zip(names,commands):
        current=np.array(Image.open(folder/(name+'.png')).convert('RGB'))
        row=replay_pair(previous,current,scene,[command['dx'],command['dy']])
        row['frame']=name;pairs.append(row);previous=current
    execution=[]
    for path in sorted((folder/'execution').glob('attempt-*.json')):
        record=json.loads(path.read_text(encoding='utf-8'))
        files=record.get('motion_frames',{})
        if files:
            before=np.array(Image.open(path.parent/files['before']).convert('RGB'))
            after=np.array(Image.open(path.parent/files['after']).convert('RGB'))
            reference='saved exact motion pair'
        elif path.stem=='attempt-01' and path.with_suffix('.png').is_file():
            before=previous
            after=np.array(Image.open(path.with_suffix('.png')).convert('RGB'))
            reference='last capture reference; immediate pre-action frame was not saved'
        else:
            continue
        row=replay_pair(before,after,scene)
        row.update(attempt=path.name,reference=reference,original_error=record.get('error'))
        if row['result'] is not None:
            reverse=replay_pair(after,before,scene)
            row['reverse']=reverse
            if reverse['result'] is not None:
                a=np.vstack((row['result']['matrix'],[0,0,1]))
                b=np.vstack((reverse['result']['matrix'],[0,0,1]))
                markers=np.column_stack((np.array(scene.markers)-scene.board[:2],np.ones(3)))
                row['roundtrip_marker_error']=np.linalg.norm((markers@(b@a).T-markers)[:,:2],axis=1).tolist()
        execution.append(row)
    successful=[row for row in pairs if row['result'] is not None]
    summary=dict(capture_pairs=len(pairs),passed=len(successful),
                 dense_retries=sum(len(row['diagnostics']['attempts'])>1 for row in pairs),
                 max_translation_error=max((row['translation_error'] for row in successful),default=None),
                 max_region_rgb_rmse=max((max(row['result']['region_rgb_rmse']) for row in successful),default=None),
                 total_registration_seconds=sum(row['seconds'] for row in pairs),
                 execution_pairs=len(execution),execution_passed=sum(row['result'] is not None for row in execution))
    return dict(folder=str(folder),summary=summary,capture=pairs,execution=execution)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    parser.add_argument('captures',type=Path,nargs='+')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    summaries=[]
    for folder in args.captures:
        result=replay(folder)
        name=folder.parent.name if folder.name=='atlas_capture' else folder.name
        (args.output/(name+'.json')).write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
        summary=dict(name=name,**result['summary']);summaries.append(summary)
        print(json.dumps(summary,ensure_ascii=False),flush=True)
    (args.output/'summary.json').write_text(json.dumps(summaries,indent=2),encoding='utf-8')


if __name__=='__main__':main()
