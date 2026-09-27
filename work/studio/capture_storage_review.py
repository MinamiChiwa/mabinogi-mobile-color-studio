"""Benchmark lossless PNG compression using saved images, never the desktop."""
import argparse
import json
from pathlib import Path
import statistics
import tempfile
import time
import numpy as np
from PIL import Image


def run(source,output,repeats=2):
    source=Path(source);output=Path(output)
    output.mkdir(parents=True,exist_ok=False)
    log=json.loads((source/'log.json').read_text())
    scene=next(r for r in log if r['kind']=='sampling_ready')
    board=tuple(scene['board']);names=['max_sampling','grid_006','grid_012','grid_024','grid_030','grid_039']
    frames={name:Image.open(source/(name+'.png')).convert('RGB') for name in names}
    rows=[]
    with tempfile.TemporaryDirectory(dir=output) as folder:
        folder=Path(folder)
        for repeat in range(repeats):
            levels=(6,1,0) if repeat%2==0 else (0,1,6)
            for level in levels:
                for name,im in frames.items():
                    crop=im.crop(board);a=folder/'full.png';b=folder/'board.png'
                    started=time.perf_counter()
                    im.save(a,compress_level=level);crop.save(b,compress_level=level)
                    elapsed=time.perf_counter()-started
                    exact=np.array_equal(im,np.array(Image.open(a))) and np.array_equal(crop,np.array(Image.open(b)))
                    rows.append(dict(frame=name,repeat=repeat,compression=level,seconds=elapsed,
                                     bytes=a.stat().st_size+b.stat().st_size,roundtrip_exact=bool(exact)))
    summary=[dict(compression=level,median_seconds=statistics.median(r['seconds'] for r in rows if r['compression']==level),
                  maximum_seconds=max(r['seconds'] for r in rows if r['compression']==level),
                  median_bytes=statistics.median(r['bytes'] for r in rows if r['compression']==level),
                  all_exact=all(r['roundtrip_exact'] for r in rows if r['compression']==level)) for level in (6,1,0)]
    report=dict(source=str(source.resolve()),game_input_sent=False,rows=rows,summary=summary,
                limitations=['Warm filesystem saved-image benchmark; excludes capture, input and real game scheduling.',
                             'Full and board PNGs preserved; only compression effort changes.'])
    (output/'report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(summary,indent=2))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('source');parser.add_argument('output')
    args=parser.parse_args();run(args.source,args.output)
