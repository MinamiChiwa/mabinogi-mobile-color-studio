"""Build deterministic signed GitHub and offline update assets."""
import argparse,hashlib,json,shutil,zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from updater.manifest import sign_ed25519,validate_relative_path,verify_manifest
from updater.paths import checked_root,hash_file

def _zip_payload(path):
    from io import BytesIO
    out=BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        info=zipfile.ZipInfo('payload',(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
        info.external_attr=0o600<<16;archive.writestr(info,path.read_bytes())
    return out.getvalue()

def _hex_seed(value):
    if isinstance(value,(bytes,bytearray)):return bytes(value)
    raw=Path(value).read_bytes().strip()
    try:return bytes.fromhex(raw.decode('ascii'))
    except (ValueError,UnicodeDecodeError):
        import base64
        return base64.b64decode(raw,validate=True)

def build_assets(package,out,version,channel,private_seed,*,release_sequence=1,previous_manifest=None,key_id='release-tooling'):
    package=checked_root(package);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    if not package.is_dir() or not (package/'ColorStudio.exe').is_file():raise ValueError('Complete package with ColorStudio.exe required')
    rows=[];blobs={}
    small=[]
    for path in sorted(p for p in package.rglob('*') if p.is_file()):
        relative=path.relative_to(package).as_posix()
        if relative.casefold().startswith('data/') or relative.casefold() in {'update-manifest.json','update-manifest.sig','update-location.json'}:continue
        validate_relative_path(relative)
        if path.stat().st_size<65536 and relative!='ColorStudio.exe':
            small.append((relative,path));continue
        payload=_zip_payload(path);blob_digest=hashlib.sha256(payload).hexdigest();blob_name=f'blob-{blob_digest}.zip'
        (out/blob_name).write_bytes(payload);blobs[blob_name]=payload
        digest=hashlib.sha256(path.read_bytes()).hexdigest();size=path.stat().st_size
        rows.append({'path':relative,'sha256':digest,'size':size,'blob':blob_name,'blob_sha256':blob_digest,'download_size':len(payload)})
    from io import BytesIO
    for start in range(0,len(small),128):
        group=small[start:start+128];stream=BytesIO();members={};group_rows=[]
        with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
            for relative,path in group:
                data=path.read_bytes();digest=hashlib.sha256(data).hexdigest();member='files/'+digest
                if member not in members:
                    info=zipfile.ZipInfo(member,(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o600<<16
                    archive.writestr(info,data);members[member]=True
                group_rows.append(dict(path=relative,sha256=digest,size=len(data),member=member))
        payload=stream.getvalue();blob_digest=hashlib.sha256(payload).hexdigest();blob_name='blob-'+blob_digest+'.zip'
        blobs[blob_name]=payload;(out/blob_name).write_bytes(payload)
        for row in group_rows:rows.append(dict(row,blob=blob_name,blob_sha256=blob_digest,download_size=len(payload)))
    rows.sort(key=lambda row:row['path'])
    if len(blobs)>990:raise ValueError('Too many release assets; use larger resource bundles')
    manifest={'schema':1,'app_id':'MabinogiMobileColorStudio','version':version,'channel':channel,
        'platform':'win32','architecture':'x86_64','release_sequence':release_sequence,'minimum_updater':1,
        'data_schema_read':[1],'data_schema_write':1,'key_id':key_id,'files':rows}
    raw=json.dumps(manifest,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
    signature=sign_ed25519(raw,_hex_seed(private_seed));(out/'update-manifest.json').write_bytes(raw);(out/'update-manifest.sig').write_bytes(signature)
    offline_name=f'UPDATE-ONLY-ColorStudio-{version}-win-x64.zip'
    with zipfile.ZipFile(out/offline_name,'w',zipfile.ZIP_STORED) as archive:
        for name,data in [('update-manifest.json',raw),('update-manifest.sig',signature),*blobs.items()]:
            info=zipfile.ZipInfo(name,(1980,1,1,0,0,0));info.external_attr=0o600<<16;archive.writestr(info,data)
    delta_name=None;changed=list(blobs)
    if previous_manifest:
        prior=Path(previous_manifest).read_bytes();previous=json.loads(prior)
        unchanged={(r['path'].casefold(),r['sha256']) for r in previous['files']}
        changed=sorted({r['blob'] for r in rows if (r['path'].casefold(),r['sha256']) not in unchanged})
        delta_name=f"UPDATE-ONLY-ColorStudio-from-{previous['version']}-to-{version}-win-x64.zip"
        delta=dict(schema=1,key_id=key_id,base_manifest_sha256=hashlib.sha256(prior).hexdigest(),
            target_manifest_sha256=hashlib.sha256(raw).hexdigest())
        delta_raw=json.dumps(delta,sort_keys=True,separators=(',',':')).encode('utf-8')
        delta_sig=sign_ed25519(delta_raw,_hex_seed(private_seed))
        with zipfile.ZipFile(out/delta_name,'w',zipfile.ZIP_STORED) as archive:
            for name,data in [('update-manifest.json',raw),('update-manifest.sig',signature),
                    ('offline-base.json',delta_raw),('offline-base.sig',delta_sig),*((n,blobs[n]) for n in changed)]:
                info=zipfile.ZipInfo(name,(1980,1,1,0,0,0));info.external_attr=0o600<<16;archive.writestr(info,data)
    return {'version':version,'file_count':len(rows),'download_bytes':sum(len(data) for data in blobs.values()),
            'offline_name':offline_name,'delta_name':delta_name,'changed_blobs':tuple(changed),
            'changed_bytes':sum(len(blobs[n]) for n in changed),'manifest_sha256':hashlib.sha256(raw).hexdigest(),'blobs':tuple(sorted(blobs))}

def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument('--package',required=True);parser.add_argument('--out',required=True);parser.add_argument('--version',required=True);parser.add_argument('--channel',default='stable',choices=('stable','prerelease'));parser.add_argument('--key-file',required=True)
    parser.add_argument('--previous-manifest');parser.add_argument('--key-id',required=True);parser.add_argument('--release-sequence',type=int,required=True)
    args=parser.parse_args(argv);print(json.dumps(build_assets(args.package,args.out,args.version,args.channel,args.key_file,
        previous_manifest=args.previous_manifest,key_id=args.key_id,release_sequence=args.release_sequence),indent=2))

if __name__=='__main__':main()
