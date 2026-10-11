import hashlib,re,json,time
from pathlib import Path
from .paths import hash_file,atomic_json

class DownloadError(RuntimeError): pass
class DownloadCancelled(DownloadError): pass

def download_bytes(client,url,partial,size,sha256,*,cancel=lambda:False,emit=lambda e:None,timeout=(5,15),max_retries=2):
    partial=Path(partial);partial.parent.mkdir(parents=True,exist_ok=True);attempt=0
    meta=partial.with_name(partial.name+'.json')
    try:identity=json.loads(meta.read_text(encoding='utf-8'))
    except (OSError,ValueError):identity={}
    if identity and (identity.get('sha256')!=sha256 or identity.get('size')!=size):
        partial.unlink(missing_ok=True);identity={}
    atomic_json(meta,dict(sha256=sha256,size=size,etag=identity.get('etag','')))
    def complete():
        if not partial.exists() or partial.stat().st_size!=size or hash_file(partial)!=sha256:return None
        completed=partial.with_suffix('');partial.replace(completed);meta.unlink(missing_ok=True);return completed
    while True:
        if cancel():raise DownloadCancelled('cancelled')
        existing=partial.stat().st_size if partial.exists() else 0
        if existing>size:partial.unlink();existing=0
        headers={}
        if existing:headers.update(Range=f'bytes={existing}-')
        if existing and identity.get('etag'):headers['If-Range']=identity['etag']
        try:response=client.get(url,headers=headers,timeout=timeout)
        except Exception as exc:
            if attempt>=max_retries:raise DownloadError('network') from exc
            attempt+=1;continue
        status=int(getattr(response,'status',0))
        append=False
        if status==206:
            content_range=str(getattr(response,'headers',{}).get('Content-Range',''))
            match=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)',content_range)
            if not match or tuple(map(int,match.groups()))!=(existing,size-1,size):raise DownloadError('invalid content range')
            if identity.get('etag') and response.headers.get('ETag',identity['etag'])!=identity['etag']:raise DownloadError('download changed')
            append=existing>0
        elif status==200:
            if existing:partial.unlink(missing_ok=True)
        elif status==416:
            if hasattr(response,'close'):response.close()
            ready=complete()
            if ready is not None:return ready
            partial.unlink(missing_ok=True)
            if attempt>=max_retries:raise DownloadError('invalid range')
            attempt+=1;continue
        elif status in (429,500,502,503,504) and attempt<max_retries:
            if hasattr(response,'close'):response.close()
            attempt+=1
            try:delay=min(5.,max(.1,float(getattr(response,'headers',{}).get('Retry-After',.25*attempt))))
            except ValueError:delay=.25*attempt
            until=time.monotonic()+delay
            while time.monotonic()<until:
                if cancel():raise DownloadCancelled('cancelled')
                time.sleep(min(.1,until-time.monotonic()))
            continue
        else:
            if hasattr(response,'close'):response.close()
            raise DownloadError(f'HTTP {status}')
        identity=dict(sha256=sha256,size=size,etag=getattr(response,'headers',{}).get('ETag',''))
        atomic_json(meta,identity)
        mode='ab' if append else 'wb';received=existing if append else 0
        try:
            with partial.open(mode) as stream:
                for chunk in response.iter_bytes():
                    if cancel():raise DownloadCancelled('cancelled')
                    if not isinstance(chunk,(bytes,bytearray)):raise DownloadError('invalid response body')
                    if received+len(chunk)>size:raise DownloadError('download too large')
                    stream.write(chunk);received+=len(chunk);emit(dict(kind='download',received=received,total=size))
        except DownloadCancelled:raise
        except Exception as exc:
            if isinstance(exc,DownloadError) or attempt>=max_retries:raise DownloadError(str(exc)) from exc
            attempt+=1;continue
        finally:
            if hasattr(response,'close'):response.close()
        if received!=size:
            if received<size and status==416:raise DownloadError('download size mismatch')
            partial.unlink(missing_ok=True);raise DownloadError('download size mismatch')
        digest=hash_file(partial)
        if digest!=sha256:
            partial.unlink(missing_ok=True);raise DownloadError('download hash mismatch')
        return complete()
