"""Verify signatures, full ownership and every expanded update file."""
import argparse,hashlib,json,tempfile,zipfile
from pathlib import Path
from updater.manifest import verify_manifest,verify_ed25519,_key_bytes
from updater.payload import unpack_blob
from updater.paths import hash_file

def verify_assets(asset_dir,package=None,*,trusted_keys):
    asset_dir=Path(asset_dir);raw=(asset_dir/'update-manifest.json').read_bytes()
    manifest=verify_manifest(raw,(asset_dir/'update-manifest.sig').read_bytes(),trusted_keys)
    expected={r.path for r in manifest.files}
    with tempfile.TemporaryDirectory() as temporary:
        for row in manifest.files:
            unpack_blob(asset_dir/row.blob,row,Path(temporary)/row.path)
            if package is not None:
                target=Path(package)/row.path
                if not target.is_file() or hash_file(target)!=row.sha256:raise ValueError('Application mismatch: '+row.path)
        for archive in asset_dir.glob('ColorStudio-offline-*.zip'):
            with zipfile.ZipFile(archive) as source:
                signed=verify_manifest(source.read('update-manifest.json'),source.read('update-manifest.sig'),trusted_keys)
                if signed.version!=manifest.version or signed.files!=manifest.files:raise ValueError('Offline manifest mismatch')
                if 'offline-base.json' in source.namelist():
                    base_raw=source.read('offline-base.json');base=json.loads(base_raw)
                    if (base.get('key_id') not in trusted_keys or not verify_ed25519(base_raw,source.read('offline-base.sig'),_key_bytes(trusted_keys[base['key_id']]))
                            or base.get('target_manifest_sha256')!=hashlib.sha256(raw).hexdigest()):raise ValueError('Offline base signature mismatch')
                for name in source.namelist():
                    if name.startswith('blob-'):
                        info=source.getinfo(name)
                        expected_row=next((r for r in manifest.files if r.blob==name),None)
                        if expected_row is None or info.file_size!=expected_row.download_size or hashlib.sha256(source.read(name)).hexdigest()!=expected_row.blob_sha256:
                            raise ValueError('Offline blob mismatch')
                if signed.base_manifest_sha256 is None and 'offline-base.json' not in source.namelist() and not {r.blob for r in manifest.files}.issubset(source.namelist()):raise ValueError('Full offline package incomplete')
    if package is not None:
        actual={p.relative_to(package).as_posix() for p in Path(package).rglob('*') if p.is_file()}
        actual={p for p in actual if not p.startswith('data/') and p not in {'update-manifest.json','update-manifest.sig','update-location.json'}}
        if actual!=expected:raise ValueError('Application ownership mismatch')
    return dict(files=len(manifest.files),manifest_sha256=hashlib.sha256(raw).hexdigest())

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('asset_dir');p.add_argument('--package');p.add_argument('--public-keys',required=True)
    a=p.parse_args(argv);keys=json.loads(Path(a.public_keys).read_text(encoding='utf-8'))
    print(json.dumps(verify_assets(a.asset_dir,Path(a.package) if a.package else None,trusted_keys=keys),indent=2))
if __name__=='__main__':main()
