"""Opt-in bounded diagnostics. Normal searches create no session files."""
import json,time,threading,queue,re
from pathlib import Path
from PIL import Image

LIMIT=200*1024*1024
MARKER='.color-studio-diagnostics'
SESSION_RETENTION_DAYS=30
SESSION_RETENTION_COUNT=20
SESSION_RETENTION_BYTES=512*1024*1024

def cleanup_sessions(root, now=None, keep_days=SESSION_RETENTION_DAYS,
                     keep_count=SESSION_RETENTION_COUNT,
                     max_bytes=SESSION_RETENTION_BYTES):
    """Bound normal atlas session storage without touching unrelated files.

    Only timestamp-named child directories created by the studio are eligible.
    The newest sessions and any directory modified in the last five minutes are
    retained; older sessions are removed when they exceed the age or total-size
    budget. Unexpected files make the directory stay in place.
    """
    root=Path(root)
    if root.is_symlink() or not root.is_dir():return dict(removed=0,bytes=0)
    now=time.time() if now is None else float(now)
    entries=[]
    for folder in root.iterdir():
        if (folder.is_symlink() or not folder.is_dir() or
                not re.fullmatch(r'\d{8}-\d{6}',folder.name)):continue
        try:
            files=[p for p in folder.rglob('*') if p.is_file() and not p.is_symlink()]
            entries.append((folder.stat().st_mtime,folder,files,
                            sum(p.stat().st_size for p in files)))
        except OSError:continue
    newest={id(item[1]) for item in sorted(entries,key=lambda item:item[0],reverse=True)[:keep_count]}
    entries.sort(key=lambda item:item[0])
    total=sum(item[3] for item in entries);removed=removed_bytes=0
    for stamp,folder,files,size in entries:
        recent=now-stamp<300
        over_size=total>max_bytes
        old=now-stamp>keep_days*86400
        if recent or id(folder) in newest or not (old or over_size):continue
        try:
            for path in files:path.unlink(missing_ok=True)
            for child in sorted(folder.rglob('*'),key=lambda p:len(p.parts),reverse=True):
                if child.is_dir() and not child.is_symlink():child.rmdir()
            folder.rmdir()
            total-=size;removed+=1;removed_bytes+=size
        except OSError:continue
    return dict(removed=removed,bytes=removed_bytes)

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
