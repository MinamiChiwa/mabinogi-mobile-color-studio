"""Bounded background PNG storage and registration; never sends game input."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from collections import deque
import time
from PIL import Image
from analyze_live_atlas import CaptureAlignment


class CaptureWorker:
    def __init__(self, folder, scene):
        self.folder=folder
        self.alignment=CaptureAlignment(scene)
        self.error=None
        self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='atlas-capture')
        self.pending=deque()
        self.closed=False

    def submit(self,name,image,board,record,command,check,probes=()):
        # At most two full client frames and their optional two board probes
        # wait in memory; registration retains only the production board crops.
        while len(self.pending)>=2:
            check()
            try:self.pending[0].result(timeout=.025)
            except TimeoutError:continue
            self.pending.popleft()
        self.pending.append(self.pool.submit(self._process,name,image,board,record,command,probes))

    def _process(self,name,image,board,record,command,probes=()):
        l,t,r,b=board
        crop=image[t:b,l:r].copy()
        started=time.perf_counter()
        try:
            Image.fromarray(image).save(self.folder/(name+'.png'),compress_level=1)
            Image.fromarray(crop).save(self.folder/(name+'_board.png'),compress_level=1)
        except OSError as exc:
            # Pixels remain available in memory even when diagnostic storage
            # is unavailable. Record the failure without discarding samples.
            record['storage_error']=str(exc)
        record['png_seconds']=time.perf_counter()-started
        if self.error is None:
            try:
                self.alignment.append(name,crop,command)
                if self.alignment.motions:
                    last=self.alignment.motions[-1]
                    if isinstance(last,dict) and last.get('frame')==name:
                        record['alignment']=last
            except Exception as exc:
                self.error=str(exc)
                record['alignment_error']=self.error
                failure=getattr(self.alignment,'last_failure',None)
                if isinstance(failure,dict):record['alignment_failure']=failure
        # Early frames are diagnostic board crops only: never append them to
        # the alignment chain or create training/holdout frame log entries.
        probe_started=time.perf_counter()
        for label,pixels in probes:
            filename=name+'-settle-'+label+'.png'
            try:
                Image.fromarray(pixels).save(self.folder/filename,compress_level=1)
                record.setdefault('settling_probe_files',[]).append(filename)
            except OSError as exc:
                record['settling_storage_error']=str(exc)
        if probes:record['settling_png_seconds']=time.perf_counter()-probe_started

    def close(self):
        if not self.closed:
            self.pool.shutdown(wait=True,cancel_futures=False)
            self.closed=True
        return self.alignment if self.error is None else None
