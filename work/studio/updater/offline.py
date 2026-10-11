"""Offline import prepares bytes only; it never runs archive code."""
import hashlib,zipfile,stat,uuid,shutil,json
from pathlib import Path
from .manifest import ManifestError,verify_manifest,verify_ed25519,_key_bytes
from .paths import hash_file

class OfflinePackageError(ValueError):pass

def import_offline(archive,cache_dir,cache=None,*,trusted_keys,emit=lambda e:None,
        max_members=25000,max_uncompressed=4*1024**3,root=None,old_raw=None,cancel=lambda:False):
    archive=Path(archive);cache_dir=Path(cache_dir)
    staging=cache_dir/('.offline-'+uuid.uuid4().hex)
    try:
        with zipfile.ZipFile(archive) as source:
            infos=source.infolist();names=set();total=0
            if len(infos)>max_members:raise OfflinePackageError('Too many offline members')
            for info in infos:
                name=info.filename
                if name.casefold() in names or '/' in name or '\\' in name or ':' in name or name in ('','.','..'):
                    raise OfflinePackageError('Unsafe offline member')
                names.add(name.casefold());total+=info.file_size
                if total>max_uncompressed or info.file_size>2*1024**3:raise OfflinePackageError('Offline package too large')
                if info.is_dir() or stat.S_ISLNK(info.external_attr>>16) or info.flag_bits&1:raise OfflinePackageError('Unsupported offline member')
                if name not in ('update-manifest.json','update-manifest.sig','offline-base.json','offline-base.sig') and not __import__('re').fullmatch(r'blob-[0-9a-f]{64}\.zip',name):
                    raise OfflinePackageError('Unexpected offline member')
            if not {'update-manifest.json','update-manifest.sig'}.issubset(names):raise OfflinePackageError('Offline signature missing')
            if source.getinfo('update-manifest.json').file_size>8*1024**2 or source.getinfo('update-manifest.sig').file_size!=64:
                raise OfflinePackageError('Invalid manifest size')
            raw=source.read('update-manifest.json');sig=source.read('update-manifest.sig')
            manifest=verify_manifest(raw,sig,trusted_keys)
            if 'offline-base.json' in names or 'offline-base.sig' in names:
                if not {'offline-base.json','offline-base.sig'}.issubset(names):raise OfflinePackageError('Offline base signature missing')
                if source.getinfo('offline-base.json').file_size>4096 or source.getinfo('offline-base.sig').file_size!=64:
                    raise OfflinePackageError('Invalid offline base size')
                base_raw=source.read('offline-base.json');base_sig=source.read('offline-base.sig');base=json.loads(base_raw)
                key=base.get('key_id')
                if (base.get('schema')!=1 or key not in trusted_keys or not verify_ed25519(base_raw,base_sig,_key_bytes(trusted_keys[key]))
                        or base.get('target_manifest_sha256')!=hashlib.sha256(raw).hexdigest()):raise OfflinePackageError('Invalid offline base signature')
                if old_raw is None or base.get('base_manifest_sha256')!=hashlib.sha256(old_raw).hexdigest():
                    raise OfflinePackageError('wrong_base: import a full offline package')
            if manifest.base_manifest_sha256 and (old_raw is None or hashlib.sha256(old_raw).hexdigest()!=manifest.base_manifest_sha256):
                raise OfflinePackageError('wrong_base: import a full offline package')
            expected={r.blob:r for r in manifest.files}
            if names-{'update-manifest.json','update-manifest.sig','offline-base.json','offline-base.sig'}-set(expected):raise OfflinePackageError('Unknown offline blob')
            for row in manifest.files:
                if row.blob not in names:
                    if root is None or not (Path(root)/row.path).is_file() or hash_file(Path(root)/row.path)!=row.sha256:
                        raise OfflinePackageError('wrong_base: required blob missing')
            staging.mkdir(parents=True)
            received=0
            for name,row in expected.items():
                if name not in names:continue
                info=source.getinfo(name)
                if info.file_size!=row.download_size:raise OfflinePackageError('Offline blob size mismatch')
                h=hashlib.sha256();written=0
                with source.open(info) as stream,(staging/name).open('wb') as target:
                    for chunk in iter(lambda:stream.read(65536),b''):
                        if cancel():raise OfflinePackageError('cancelled')
                        written+=len(chunk)
                        if written>row.download_size:raise OfflinePackageError('Offline blob too large')
                        target.write(chunk);h.update(chunk);received+=len(chunk)
                        emit(dict(kind='offline',received=received,total=total))
                if written!=row.download_size or h.hexdigest()!=row.blob_sha256:raise OfflinePackageError('Offline hash mismatch')
            (staging/'update-manifest.json').write_bytes(raw);(staging/'update-manifest.sig').write_bytes(sig)
            cache_dir.mkdir(parents=True,exist_ok=True)
            for p in staging.iterdir():p.replace(cache_dir/p.name)
            staging.rmdir();return manifest
    except (OSError,zipfile.BadZipFile,ManifestError,ValueError) as exc:
        if staging.exists():shutil.rmtree(staging)
        raise OfflinePackageError(str(exc)) from exc
