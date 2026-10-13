"""Bounded diagnostic encoding; game capture never waits for PNG or disk IO."""
import queue,threading
from PIL import Image


class ScreenshotWriter:
    def __init__(self,folder,capacity=2):
        self.folder=folder;self.jobs=queue.Queue(maxsize=capacity)
        self.stopped=threading.Event();self.dropped=0;self.saved=0;self.errors=0
        self.worker=threading.Thread(target=self._run,name='screenshot-evidence',daemon=True)
        self.worker.start()

    @property
    def pending(self):return self.jobs.qsize()

    def submit(self,name,frame):
        if self.stopped.is_set():return
        item=(name,frame.copy())
        self._enqueue(item)

    def submit_task(self,function):
        if not self.stopped.is_set():self._enqueue((None,function))

    def _enqueue(self,item):
        try:self.jobs.put_nowait(item)
        except queue.Full:
            try:self.jobs.get_nowait();self.dropped+=1
            except queue.Empty:pass
            try:self.jobs.put_nowait(item)
            except queue.Full:self.dropped+=1

    def _run(self):
        while not self.stopped.is_set() or not self.jobs.empty():
            try:name,frame=self.jobs.get(timeout=.05)
            except queue.Empty:continue
            try:
                if name is None:frame()
                else:Image.fromarray(frame).save(self.folder/name,compress_level=1)
                self.saved+=1
            except Exception:self.errors+=1

    def close(self,timeout=1.):
        self.stopped.set();self.worker.join(timeout)
