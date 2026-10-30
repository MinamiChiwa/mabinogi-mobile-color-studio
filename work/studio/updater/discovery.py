"""GitHub is a discovery hint; only signed release bytes are authoritative."""
import json,time
from dataclasses import dataclass,replace
from packaging.version import Version,InvalidVersion
from .manifest import ManifestError,verify_manifest

REPOSITORY='MinamiChiwa/mabinogi-mobile-color-studio'
BASE='https://github.com/'+REPOSITORY
API='https://api.github.com/repos/'+REPOSITORY+'/releases'
LATEST_MANIFEST=BASE+'/releases/latest/download/update-manifest.json'

@dataclass(frozen=True)
class CheckResult:
    status: str
    manifest: object=None
    reason_code: str=''
    checked_at: float=0.
    etag: str=''
    raw: bytes=b''
    signature: bytes=b''
    assets: object=None
    retry_at: float=0.

def read_body(response,limit,check=None):
    body=bytearray()
    try:
        for chunk in response.iter_bytes():
            if check is not None:check()
            body.extend(chunk)
            if len(body)>limit:raise ManifestError('Response too large')
        return bytes(body)
    finally:
        if hasattr(response,'close'):response.close()

def check_release(current_version,channel,cache,cancel,*,client,trusted_keys,manifest_url=None):
    started=time.monotonic();now=time.time();release=None;etag='';assets={}
    def result(status,reason='',**kw):return CheckResult(status,reason_code=reason,checked_at=time.time(),**kw)
    def get(url,headers=None):
        if cancel():raise InterruptedError('cancelled')
        if time.monotonic()-started>=20:raise TimeoutError('check budget')
        return client.get(url,headers=headers or {},timeout=(5,min(15,max(.1,20-(time.monotonic()-started)))))
    def check():
        if cancel():raise InterruptedError('cancelled')
        if time.monotonic()-started>=20:raise TimeoutError('check budget')
    def read(response,limit):return read_body(response,limit,check)
    try:current=Version(current_version)
    except InvalidVersion:return result('error','invalid_current_version')
    if cancel():return result('cancelled','cancelled')
    if not trusted_keys:return result('unavailable','trust_unconfigured')
    try:
        if manifest_url is None and channel=='stable':
            # Official release downloads do not share anonymous API quotas.
            # Only transport/HTTP failure permits API fallback; invalid signed
            # content, cancellation and compatibility decisions are terminal.
            direct=check_release(current_version,channel,cache,
                lambda:cancel() or time.monotonic()-started>=20,
                client=client,trusted_keys=trusted_keys,manifest_url=LATEST_MANIFEST)
            if direct.status!='unavailable':return direct
            check()
            try:api_retry_at=float(cache.get('api_retry_at',0))
            except (TypeError,ValueError):api_retry_at=0
            if now<api_retry_at:return direct
        if manifest_url is None:
            url=API+'/latest' if channel=='stable' else API+'?per_page=100'
            response=get(url,{'If-None-Match':cache['api_etag']} if cache.get('api_etag') else {})
            etag=response.headers.get('ETag','');status=int(response.status)
            if status==304 and cache.get('release'):release=cache['release'];read(response,1)
            elif status==304:
                read(response,1);response=get(url);status=int(response.status)
                etag=response.headers.get('ETag','')
            if status in (403,429):
                retry=response.headers.get('Retry-After','')
                try:retry_at=now+float(retry) if retry else float(response.headers.get('X-RateLimit-Reset',now+3600))
                except ValueError:retry_at=now+3600
                read(response,1024*1024)
                cache['api_retry_at']=retry_at
                return result('unavailable','rate_limit',retry_at=retry_at)
            elif status in (200,304):cache.pop('api_retry_at',None)
            if release is None and status==200:
                payload=json.loads(read(response,8*1024*1024))
                rows=[payload] if isinstance(payload,dict) else payload
                candidates=[]
                for row in rows:
                    if not isinstance(row,dict) or row.get('draft') or channel=='stable' and row.get('prerelease'):continue
                    try:version=Version(row.get('tag_name','').removeprefix('v'))
                    except InvalidVersion:continue
                    if version>current:candidates.append((version,row))
                if not candidates:return result('none')
                if channel=='prerelease':
                    manual=None
                    for _,candidate in sorted(candidates,key=lambda pair:pair[0],reverse=True)[:10]:
                        check();tag=candidate['tag_name'];candidate_assets={}
                        for row in candidate.get('assets',[]):
                            name=row.get('name','');asset=row.get('browser_download_url','')
                            if asset.startswith(BASE+'/releases/download/'+tag+'/') and asset.endswith('/'+name):candidate_assets[name]=asset
                        if not {'update-manifest.json','update-manifest.sig'}.issubset(candidate_assets):continue
                        local=dict(cache)
                        local.pop('etag',None)
                        selected=check_release(current_version,channel,local,lambda:cancel() or time.monotonic()-started>=20,
                            client=client,trusted_keys=trusted_keys,manifest_url=candidate_assets['update-manifest.json'])
                        if selected.status=='manual':manual=selected;continue
                        if (selected.status=='available' and Version(tag.removeprefix('v'))==Version(selected.manifest.version)
                                and all(row.blob in candidate_assets for row in selected.manifest.files)):
                            cache.update(local);return replace(selected,assets=candidate_assets)
                    return manual or result('none','compatible_release')
                release=max(candidates,key=lambda pair:pair[0])[1]
            if release is not None:
                tag=release['tag_name']
                for row in release.get('assets',[]):
                    name=row.get('name','');url=row.get('browser_download_url','')
                    if url.startswith(BASE+'/releases/download/'+tag+'/') and url.endswith('/'+name):assets[name]=url
                if not {'update-manifest.json','update-manifest.sig'}.issubset(assets):return result('none','incomplete_assets')
                manifest_url=assets['update-manifest.json']
                cache['release']=release;cache['api_etag']=etag
            elif channel=='stable':
                if response is not None and status!=304:read(response,1024*1024)
                # The API is only a fallback discovery path; release files go through the mirror-first client.
                return result('unavailable',f'http_{status}')
            else:return result('unavailable','network')
        response=get(manifest_url,{'If-None-Match':cache['etag']} if cache.get('etag') else {})
        status=int(response.status);etag=response.headers.get('ETag','')
        if status==304 and cache.get('manifest_raw') and cache.get('signature'):
            read(response,1);raw=cache['manifest_raw'];sig=cache['signature']
        else:
            if status==304:read(response,1);response=get(manifest_url);status=int(response.status)
            if status!=200:read(response,1024*1024);return result('unavailable',f'http_{status}')
            raw=read(response,8*1024*1024)
            response=get(manifest_url.removesuffix('.json')+'.sig')
            if int(response.status)!=200:read(response,1024);return result('invalid','signature')
            sig=read(response,64)
        manifest=verify_manifest(raw,sig,trusted_keys)
        if manifest.minimum_updater>1:return result('manual','minimum_updater')
        if manifest.data_schema_write!=1 or 1 not in manifest.data_schema_read:return result('manual','data_schema')
        if channel=='stable' and manifest.channel!='stable':return result('none','channel')
        if manifest.release_sequence<int(cache.get('sequence',0)):return result('invalid','replay')
        if manifest.release_sequence==int(cache.get('sequence',0)) and cache.get('signed_version') not in (None,manifest.version):
            return result('invalid','replay')
        if release and Version(release['tag_name'].removeprefix('v'))!=Version(manifest.version):return result('invalid','version_mismatch')
        if assets and any(r.blob not in assets for r in manifest.files):return result('none','incomplete_assets')
        if not assets:
            assets={r.blob:BASE+'/releases/download/v'+manifest.version+'/'+r.blob for r in manifest.files}
        cache.update(sequence=max(int(cache.get('sequence',0)),manifest.release_sequence),signed_version=manifest.version,etag=etag,manifest_raw=raw,signature=sig)
        return result('available' if Version(manifest.version)>current else 'none',manifest=manifest,etag=etag,raw=raw,signature=sig,assets=assets)
    except InterruptedError:return result('cancelled','cancelled')
    except ManifestError:return result('invalid','signature')
    except Exception:return result('unavailable','network')
