"""Bounded, best-effort execution evidence, outside the game input thread."""
from copy import deepcopy
import json
from pathlib import Path
import queue
import threading

from PIL import Image


class ExecutionDiagnostics:
    def __init__(self, max_jobs=4, max_bytes=96*1024*1024):
        self.max_jobs=max_jobs;self.max_bytes=max_bytes
        self._lock=threading.Lock();self._pending=0;self._bytes=0
        self._queue=queue.Queue();self._worker=None

    def submit(self,folder,prefix,data,frames):
        """Copy a bounded snapshot and return without waiting for encoding/IO.

        Saturation may omit diagnostic images or the entire diagnostic job.
        Core capture samples and the measured result are never queued here.
        The completion event is for offline tests, never a gameplay barrier.
        """
        unique={id(frame):frame for frame in frames.values()}
        size=sum(frame.nbytes for frame in unique.values())
        with self._lock:
            if self._pending>=self.max_jobs:return None
            include_images=self._bytes+size<=self.max_bytes
            reserved=size if include_images else 0
            self._pending+=1;self._bytes+=reserved
        try:
            record=deepcopy(data)
            copies={key:frame.copy() for key,frame in unique.items()} if include_images else {}
            images={name:copies[id(frame)] for name,frame in frames.items()} if include_images else {}
            record['diagnostic_storage']=dict(background=True,images_omitted=not include_images)
            if not include_images:record['motion_frames']={}
            done=threading.Event()
            with self._lock:
                if self._worker is None:
                    self._worker=threading.Thread(target=self._run,name='execution-diagnostics',daemon=True)
                    try:self._worker.start()
                    except Exception:
                        self._worker=None
                        raise
            self._queue.put_nowait((Path(folder),prefix,record,images,reserved,done))
            return done
        except Exception:
            with self._lock:self._pending-=1;self._bytes-=reserved
            return None

    def _run(self):
        while True:
            folder,prefix,data,frames,reserved,done=self._queue.get()
            try:self._write(folder,prefix,data,frames)
            except Exception:pass  # Diagnostic IO cannot interrupt or hold up input.
            finally:
                frames.clear();data.clear()
                with self._lock:self._pending-=1;self._bytes-=reserved
                self._queue.task_done();done.set()

    @staticmethod
    def _write(folder,prefix,data,frames):
        folder.mkdir(parents=True,exist_ok=True)
        # Preserve route/measurement evidence even if image storage fails.
        (folder/(prefix+'.json')).write_text(json.dumps(data,indent=2),encoding='utf-8')
        for name,frame in frames.items():
            Image.fromarray(frame).save(folder/name,compress_level=1)


execution_diagnostics=ExecutionDiagnostics()
