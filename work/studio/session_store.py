"""Opt-in bounded diagnostics. Normal searches create no session files."""
import json,time,threading,queue,re
from pathlib import Path
from PIL import Image

LIMIT=200*1024*1024
MARKER='.color-studio-diagnostics'

def cleanup(root,now=None,limit=LIMIT):
    now=time.time() if now is None else now
    entries=[]
    for folder in Path(root).glob('*'):
        marker=folder/MARKER
        if folder.is_symlink() or not folder.is_dir() or not marker.is_file():continue
        # Only our named artifacts; never recursively delete an arbitrary directory.
        files=[p for p in folder.iterdir() if p.is_file() and not p.is_symlink()
               and (p.name==MARKER or p.name=='events.jsonl' or re.fullmatch(r'[a-zA-Z0-9_-]+\.png',p.name))]
        size=sum(p.stat().st_size for p in files)
        entries.append((marker.stat().st_mtime,folder,files,size))
    total=sum(e[3] for e in entries)
    for stamp,folder,files,size in sorted(entries):
        if now-stamp<300:continue  # active/recent runs are never removed
        if now-stamp<=7*86400 and total<=limit:continue
        for p in files:p.unlink(missing_ok=True)
        total-=size
        try:folder.rmdir()
        except OSError:pass
    return total

class SessionStore:
    def __init__(self,folder,enabled=False):
        self.folder=Path(folder);self.enabled=enabled;self.pending=queue.Queue(maxsize=4)
        self.closed=False;self.worker=None
        if enabled:
            self.worker=threading.Thread(target=self._run,daemon=True);self.worker.start()
    def event(self,entry):
        if self.enabled:
            try:self.pending.put_nowait(('event',entry))
            except queue.Full:pass
    def image(self,label,image):
        # Limit queued pixel buffers even on very large monitors.
        if self.enabled and image.nbytes<=16*1024*1024 and not self.pending.full():
            try:self.pending.put_nowait(('image',(label,image.copy())))
            except queue.Full:pass
    def _run(self):
        try:
            self.folder.parent.mkdir(parents=True,exist_ok=True)
            used=cleanup(self.folder.parent)
            if used>=LIMIT:return
            self.folder.mkdir(exist_ok=True)
            marker=self.folder/MARKER;marker.write_text('ColorStudio diagnostics v1',encoding='utf-8')
            while not self.closed or not self.pending.empty():
                try:kind,value=self.pending.get(timeout=.1)
                except queue.Empty:continue
                marker.touch()
                if kind=='event':
                    data=(json.dumps(value,ensure_ascii=False)+'\n').encode('utf-8')
                    if used+len(data)<=LIMIT:
                        with (self.folder/'events.jsonl').open('ab') as f:f.write(data)
                        used+=len(data)
                else:
                    import io
                    label,image=value;buffer=io.BytesIO();Image.fromarray(image).save(buffer,format='PNG',compress_level=1)
                    data=buffer.getvalue()
                    if used+len(data)<=LIMIT:
                        path=self.folder/(label+'.png');old=path.stat().st_size if path.exists() else 0
                        path.write_bytes(data);used+=len(data)-old
            cleanup(self.folder.parent)
        except OSError:pass  # diagnostics must never interrupt dyeing
    def close(self):
        self.closed=True
        if self.worker:self.worker.join(timeout=2)
