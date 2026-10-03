"""Session ownership and bounded, best-effort diagnostic storage."""
import json,time,threading,queue,re,datetime,uuid
from pathlib import Path
from PIL import Image

LIMIT=200*1024*1024
MARKER='.color-studio-diagnostics'
SESSION_MARKER='.color-studio-session'
ACTIVE_MARKER='.color-studio-active'
SESSION_RETENTION_DAYS=30
# Keep only a small diagnostic history. Running/recent sessions are protected
# separately below so reducing this count never removes the current run.
SESSION_RETENTION_COUNT=3
# There is deliberately no default aggregate byte cap. A single atlas
# capture can legitimately be larger than a convenient cache budget; count-
# based retention must not delete it before it can be inspected.
SESSION_RETENTION_BYTES=None

def mark_session(folder):
    """Identify an owned session before any normal atlas/quick-search writes."""
    folder=Path(folder)
    try:
        folder.mkdir(parents=True,exist_ok=True)
        (folder/SESSION_MARKER).write_text('ColorStudio session v1',encoding='ascii')
        return True
    except OSError:
        return False  # Optional evidence storage must not prevent dyeing.

def new_session_path(root, now=None):
    """Return a collision-resistant timestamped path without creating it."""
    stamp=(now or datetime.datetime.now()).strftime('%Y%m%d-%H%M%S')
    base=Path(root)/(stamp+'-'+uuid.uuid4().hex[:8])
    while base.exists():base=Path(root)/(stamp+'-'+uuid.uuid4().hex[:8])
    return base

def start_session_cleanup(root):
    """Run best-effort session housekeeping away from the UI thread."""
    def run():
        try:cleanup_sessions(root)
        except OSError:pass
    worker=threading.Thread(target=run,name='session-cleanup',daemon=True)
    worker.start()
    return worker

def cleanup_sessions(root, now=None, keep_days=SESSION_RETENTION_DAYS,
                     keep_count=SESSION_RETENTION_COUNT,
                     max_bytes=SESSION_RETENTION_BYTES):
    """Bound normal atlas session storage without touching unrelated files.

    Only timestamp-named child directories created by the studio are eligible.
    Active/recent sessions are always retained. The newest three completed
    sessions are kept as a small history. There is no aggregate byte limit by
    default: a large single capture remains available for inspection. A
    caller may still pass ``max_bytes`` for an explicit maintenance operation;
    even then the retained newest sessions are never sacrificed. Unexpected
    files make the directory stay in place.
    """
    root=Path(root)
    if root.is_symlink() or not root.is_dir():return dict(removed=0,bytes=0)
    resolved_root=root.resolve()
    now=time.time() if now is None else float(now)
    entries=[]
    for folder in root.iterdir():
        if (folder.is_symlink() or not folder.is_dir() or
                not re.fullmatch(r'\d{8}-\d{6}(?:-[0-9a-f]{8})?',folder.name)):continue
        try:
            # The timestamp is only a naming convention. Require a marker
            # written by the normal or diagnostic session writer;
            # users may legitimately have unrelated timestamped folders.
            if not any((folder/name).is_file() and not (folder/name).is_symlink()
                       for name in (SESSION_MARKER,MARKER)):
                continue
            files=[p for p in folder.rglob('*') if p.is_file() and not p.is_symlink()]
            # A directory mtime changes when a child is created, but not when
            # an existing log or image is appended/replaced.  Use the newest
            # contained file as well, otherwise a long capture can look stale
            # while it is still receiving frames.
            mtimes=[folder.stat().st_mtime]
            mtimes.extend(p.stat().st_mtime for p in files)
            entries.append((max(mtimes),folder,files,
                            sum(p.stat().st_size for p in files)))
        except OSError:continue
    completed=[item for item in entries if not (item[1]/ACTIVE_MARKER).is_file()]
    newest={item[1] for item in sorted(completed,key=lambda item:item[0],reverse=True)[:max(0,int(keep_count))]}
    entries.sort(key=lambda item:item[0])
    total=sum(item[3] for item in entries);removed=removed_bytes=0

    def is_protected(entry):
        """Return whether this session is active or was updated very recently."""
        stamp,folder,_,_=entry
        # Re-scan mtimes before deletion so a file written after the initial
        # directory scan cannot make a live session look stale.
        try:
            latest=max([folder.stat().st_mtime]+[
                path.stat().st_mtime for path in folder.rglob('*')
                if path.is_file() and not path.is_symlink()])
            if now-latest<300:return True
        except OSError:
            return True
        marker=folder/ACTIVE_MARKER
        if marker.is_file():
            try:return now-marker.stat().st_mtime<300
            except OSError:return True
        return False

    def remove_entry(entry):
        nonlocal total,removed,removed_bytes
        stamp,folder,files,size=entry
        # Recheck the activity marker immediately before deletion. A running
        # writer may have touched it after the initial directory scan.
        if is_protected(entry):return False
        try:
            # Validate the final deletion target under this explicit cache
            # root; never follow a redirected directory outside the session
            # tree during recursive maintenance.
            resolved=folder.resolve()
            if resolved.parent!=resolved_root or folder.is_symlink():return False
            children=list(folder.rglob('*'))
            if any(path.is_symlink() or
                   (hasattr(path,'is_junction') and path.is_junction())
                   for path in children):return False
            for path in files:path.unlink(missing_ok=True)
            for child in sorted(folder.rglob('*'),key=lambda p:len(p.parts),reverse=True):
                if child.is_dir() and not child.is_symlink():child.rmdir()
            folder.rmdir()
            total-=size;removed+=1;removed_bytes+=size
            return True
        except OSError:return False

    # An explicit byte threshold is only a maintenance hint for callers that
    # request one. The application uses the default ``None`` and therefore
    # never rejects a large capture because of aggregate size.
    if max_bytes is not None and total>max_bytes:
        for entry in entries:
            if total<=max_bytes:break
            if entry[1] in newest:continue
            remove_entry(entry)

    # Enforce the small history window after any optional maintenance pass.
    # This is deliberately a count rule rather than an age-only rule so old
    # captures do not accumulate indefinitely when they are small.
    for entry in entries:
        stamp,folder,files,size=entry
        if not folder.exists() or is_protected(entry):continue
        if folder not in newest:
            remove_entry(entry)
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
            active=self.folder/ACTIVE_MARKER;active.write_text('active',encoding='ascii')
            while not self.closed or not self.pending.empty():
                try:kind,value=self.pending.get(timeout=.1)
                except queue.Empty:continue
                marker.touch()
                try:active.touch()
                except OSError:pass
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
        if self.worker:
            self.worker.join(timeout=2)
            try:(self.folder/ACTIVE_MARKER).unlink(missing_ok=True)
            except OSError:pass
