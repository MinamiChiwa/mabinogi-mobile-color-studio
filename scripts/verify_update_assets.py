"""Verify the signed manifest, full ownership and every expanded update file."""
import argparse,hashlib,json,tempfile
from pathlib import Path
from updater.manifest import verify_manifest
from updater.payload import unpack_blob
from updater.paths import hash_file
from release_documents import development_document_path,validate_package_documents

def verify_assets(asset_dir,package=None,*,trusted_keys):
    asset_dir=Path(asset_dir);raw=(asset_dir/'update-manifest.json').read_bytes()
    manifest=verify_manifest(raw,(asset_dir/'update-manifest.sig').read_bytes(),trusted_keys)
    if any(development_document_path(row.path) for row in manifest.files):
        raise ValueError('Development documents in signed update manifest')
    if package is not None:validate_package_documents(package)
    expected={r.path for r in manifest.files}
    with tempfile.TemporaryDirectory() as temporary:
        for row in manifest.files:
            unpack_blob(asset_dir/row.blob,row,Path(temporary)/row.path)
            if package is not None:
                target=Path(package)/row.path
                if not target.is_file() or hash_file(target)!=row.sha256:raise ValueError('Application mismatch: '+row.path)
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
