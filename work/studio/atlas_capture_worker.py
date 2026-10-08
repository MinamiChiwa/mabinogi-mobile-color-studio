"""Bounded background PNG storage and registration; never sends game input."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from collections import deque
import threading
import time
from PIL import Image
from analyze_live_atlas import CaptureAlignment


class CaptureWorker:
    """Persist frames and register them without blocking the input loop forever.

    Registration is deliberately asynchronous, but a failed/slow worker must
    become a visible terminal capture state.  The foreground loop polls
    ``error`` between actions; this class bounds both queue backpressure and
    shutdown so a worker cannot leave the UI parked at ``N/48`` indefinitely.
    """
    def __init__(self, folder, scene, *, max_pending=2, wait_timeout=.8,
                 record_lock=None):
        self.folder=folder
        self.alignment=CaptureAlignment(scene)
        self._error=None
        self._error_lock=threading.Lock()
        self._failure_event=threading.Event()
        self.record_lock=record_lock or threading.RLock()
        self.max_pending=max(1,int(max_pending))
        self.wait_timeout=max(.05,float(wait_timeout))
        self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='atlas-capture')
        self.pending=deque()
        self.closed=False
        self.close_timeout=False

    @property
    def error(self):
        with self._error_lock:
            return self._error

    def _set_error(self, exc):
        message=str(exc) or exc.__class__.__name__
        with self._error_lock:
            if self._error is None:
                self._error=message
        self._failure_event.set()

    def _future_done(self, future):
        try:
            future.result()
        except BaseException as exc:
            self._set_error(exc)

    def _discard_done(self):
        while self.pending and self.pending[0].done():
            future=self.pending.popleft()
            try:future.result()
            except BaseException as exc:self._set_error(exc)

    def submit(self,name,image,board,record,command,check,probes=()):
        if self.closed:
            self._set_error(RuntimeError('capture worker is closed'))
            return False
        deadline=time.monotonic()+self.wait_timeout
        while len(self.pending)>=self.max_pending:
            check()
            self._discard_done()
            if self.error:
                # A failed alignment is a hard input boundary. Keep waiting
                # only long enough to finish queued raw-frame storage.
                if not self.pending:
                    break
                remaining=deadline-time.monotonic()
                if remaining<=0:
                    record['background_submit']='worker_failed'
                    return False
                try:
                    self.pending[0].result(timeout=min(.025,remaining))
                except TimeoutError:
                    continue
                except BaseException as exc:
                    self._set_error(exc)
                self.pending.popleft()
                continue
            if not self.pending:
                break
            remaining=deadline-time.monotonic()
            if remaining<=0:
                self._set_error(TimeoutError(
                    f'capture worker exceeded {self.wait_timeout:.2f}s backpressure limit'))
                record['background_submit']='backpressure_timeout'
                return False
            try:
                self.pending[0].result(timeout=min(.025,remaining))
            except TimeoutError:
                continue
            except BaseException as exc:
                self._set_error(exc)
                record['background_submit']='worker_exception'
                return False
            self.pending.popleft()
        if self.error:
            # Preserve this captured frame for offline retry, but do not
            # treat it as another alignment sample after the hard failure.
            if len(self.pending) < self.max_pending:
                future=self.pool.submit(self._process,name,image,board,record,command,probes)
                future.add_done_callback(self._future_done)
                self.pending.append(future)
                record['background_submit']='queued_storage_only'
            else:
                record['background_submit']='worker_failed'
            return False
        future=self.pool.submit(self._process,name,image,board,record,command,probes)
        future.add_done_callback(self._future_done)
        self.pending.append(future)
        record['background_submit']='queued'
        return True

    def wait_latest(self, check, *, timeout=None):
        """Drain queued work up to a bounded deadline and report health."""
        deadline=time.monotonic()+self.wait_timeout if timeout is None else time.monotonic()+max(.05,float(timeout))
        while self.pending:
            check()
            future=self.pending[0]
            remaining=deadline-time.monotonic()
            if remaining<=0:
                self._set_error(TimeoutError('capture worker wait exceeded deadline'))
                return False
            try:
                future.result(timeout=min(.025,remaining))
            except TimeoutError:
                continue
            except BaseException as exc:
                self._set_error(exc)
            self.pending.popleft()
            if self.error:
                return False
        return self.error is None

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
        with self.record_lock:
            record['png_seconds']=time.perf_counter()-started
        if self.error is None:
            try:
                self.alignment.append(name,crop,command)
                if self.alignment.motions:
                    last=self.alignment.motions[-1]
                    if isinstance(last,dict) and last.get('frame')==name:
                        with self.record_lock:
                            record['alignment']=last
            except Exception as exc:
                self._set_error(exc)
                with self.record_lock:
                    record['alignment_error']=self.error
                failure=getattr(self.alignment,'last_failure',None)
                if isinstance(failure,dict):
                    with self.record_lock:
                        record['alignment_failure']=failure
        # Early frames are diagnostic board crops only: never append them to
        # the alignment chain or create training/holdout frame log entries.
        probe_started=time.perf_counter()
        for label,pixels in probes:
            filename=name+'-settle-'+label+'.png'
            try:
                Image.fromarray(pixels).save(self.folder/filename,compress_level=1)
                with self.record_lock:
                    record.setdefault('settling_probe_files',[]).append(filename)
            except OSError as exc:
                with self.record_lock:
                    record['settling_storage_error']=str(exc)
        if probes:
            with self.record_lock:
                record['settling_png_seconds']=time.perf_counter()-probe_started

    def close(self, *, timeout=2.0):
        if self.closed:
            return self.alignment if self.error is None else None
        timeout=max(.05,float(timeout))
        deadline=time.monotonic()+timeout
        # Keep queued storage jobs after an alignment error so every frame
        # captured before the hard boundary remains available for offline
        # retry. The bounded drain below prevents this from blocking forever.
        while self.pending and time.monotonic()<deadline:
            future=self.pending[0]
            try:future.result(timeout=min(.025,max(.001,deadline-time.monotonic())))
            except TimeoutError:continue
            except BaseException as exc:self._set_error(exc)
            self.pending.popleft()
        if self.pending:
            self.close_timeout=True
            self._set_error(TimeoutError('capture worker close exceeded deadline'))
            for future in list(self.pending):future.cancel()
        # A running future cannot be killed safely.  Do not wait for it on the
        # UI thread; queued work is cancelled and the worker's error remains
        # available in the session log.
        self.pool.shutdown(wait=False if self.pending else True,cancel_futures=True)
        self.closed=True
        return self.alignment if self.error is None else None
