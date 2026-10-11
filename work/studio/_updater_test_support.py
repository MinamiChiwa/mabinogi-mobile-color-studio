"""Test-only signed fixtures; the RFC private seed never ships in the app."""
import json
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

SEED=bytes.fromhex('9d61b19deffd5a60ba844af492ec2cc4' '4449c5697b326919703bac031cae7f60')
PUBLIC=Ed25519PrivateKey.from_private_bytes(SEED).public_key().public_bytes_raw()
KEYS={'test':PUBLIC,'release-tooling':PUBLIC}

def signed(files=(),**changes):
    payload=dict(schema=1,app_id='MabinogiMobileColorStudio',version='0.4.3',channel='stable',
        platform='win32',architecture='x86_64',release_sequence=2,minimum_updater=1,
        data_schema_read=[1],data_schema_write=1,key_id='test',files=list(files))
    payload.update(changes)
    raw=json.dumps(payload,sort_keys=True,separators=(',',':')).encode()
    return raw,Ed25519PrivateKey.from_private_bytes(SEED).sign(raw)

def entry(path='ColorStudio.exe',**changes):
    value=dict(path=path,sha256='a'*64,size=1,blob='blob-'+'b'*64+'.zip',blob_sha256='b'*64,download_size=100)
    value.update(changes);return value
