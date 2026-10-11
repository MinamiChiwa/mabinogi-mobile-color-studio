"""Signed raw-byte manifests and Windows application ownership."""
import base64
import json
import re
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from packaging.version import Version, InvalidVersion
from .types import FileEntry, Manifest

class ManifestError(ValueError): pass

def sign_ed25519(message, private_seed):
    return Ed25519PrivateKey.from_private_bytes(bytes(private_seed)).sign(message)

def verify_ed25519(message, signature, public_key):
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature, message)
        return True
    except (ValueError, TypeError, InvalidSignature): return False

_HEX=re.compile(r'^[0-9a-f]{64}$')
_BLOB=re.compile(r'^blob-[0-9a-f]{64}\.zip$')
APP_ROOT_FILES={'colorstudio.exe','colorstudioupdater.exe','readme.md','readme.zh-tw.md','readme.en.md','testing.md','release_notes.md','native-window-check.ps1','window_check.zh-cn.md','window_check.zh-tw.md','window_check.en.md'}
APP_DIRS={'_internal','third_party'}

def application_path(value):
    parts=value.split('/')
    return (len(parts)>1 and parts[0].casefold() in APP_DIRS) or value.casefold() in APP_ROOT_FILES or value in ('work/studio/VERIFICATION.md','docs/automatic-updates.md')

_DEVICE={'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}

def validate_relative_path(value):
    if not isinstance(value,str) or not value or len(value)>240 or any(ord(c)<32 for c in value):raise ManifestError('Invalid manifest path')
    if any(c in value for c in '\\:*?"<>|') or value.startswith('/') or value.startswith('//'):raise ManifestError('Unsafe manifest path')
    parts=value.split('/')
    if not parts or any(part in ('','.','..') for part in parts):raise ManifestError('Unsafe manifest path')
    if any(part.rstrip(' .').upper().split('.')[0] in _DEVICE for part in parts):raise ManifestError('Reserved manifest path')
    if any(part!=part.rstrip(' .') for part in parts):raise ManifestError('Ambiguous manifest path')
    if parts[0].casefold()=='data':raise ManifestError('Manifest cannot own data')
    if not application_path(value):
        raise ManifestError('Outside application ownership')
    return '/'.join(parts)

def _key_bytes(value):
    if isinstance(value,bytes):return value
    if isinstance(value,str):
        try:return bytes.fromhex(value)
        except ValueError:return __import__('base64').b64decode(value,validate=True)
    raise ManifestError('Invalid trusted key')

def _field(obj,name,kind):
    value=obj.get(name)
    if not isinstance(value,kind):raise ManifestError('Invalid manifest field: '+name)
    return value

def verify_manifest(raw:bytes,signature:bytes,trusted_keys:dict):
    if not isinstance(raw,(bytes,bytearray)) or len(raw)>8*1024*1024:raise ManifestError('Manifest too large')
    if not isinstance(signature,(bytes,bytearray)) or len(signature)!=64:raise ManifestError('Invalid manifest signature')
    try:obj=json.loads(bytes(raw).decode('utf-8'))
    except (UnicodeDecodeError,json.JSONDecodeError) as exc:raise ManifestError('Invalid manifest JSON') from exc
    if not isinstance(obj,dict):raise ManifestError('Manifest root must be an object')
    key_id=obj.get('key_id')
    if not isinstance(key_id,str) or key_id not in trusted_keys:raise ManifestError('Untrusted manifest key')
    if not verify_ed25519(bytes(raw),bytes(signature),_key_bytes(trusted_keys[key_id])):raise ManifestError('Manifest signature invalid')
    if type(obj.get('schema')) is not int or obj['schema']!=1 or obj.get('app_id')!='MabinogiMobileColorStudio':raise ManifestError('Unsupported manifest schema')
    try:Version(_field(obj,'version',str))
    except InvalidVersion as exc:raise ManifestError('Invalid manifest version') from exc
    if obj.get('channel') not in ('stable','prerelease') or obj.get('platform')!='win32' or obj.get('architecture')!='x86_64':raise ManifestError('Unsupported update target')
    for name in ('release_sequence','minimum_updater','data_schema_write'):
        if type(obj.get(name)) is not int or obj[name]<1:raise ManifestError('Invalid manifest integer: '+name)
    read=obj.get('data_schema_read')
    if not isinstance(read,list) or not read or any(type(v) is not int or v<1 for v in read):raise ManifestError('Invalid data schema')
    rows=obj.get('files')
    if not isinstance(rows,list) or len(rows)>20000:raise ManifestError('Invalid manifest files')
    seen=set();files=[];blobs={};total=0
    for row in rows:
        if not isinstance(row,dict):raise ManifestError('Invalid manifest file entry')
        path=validate_relative_path(row.get('path'));fold=path.casefold()
        if fold in seen:raise ManifestError('Duplicate manifest path')
        seen.add(fold)
        if any(not isinstance(row.get(n),str) or not _HEX.fullmatch(row[n]) for n in ('sha256','blob_sha256')):raise ManifestError('Invalid file hash')
        if not isinstance(row.get('blob'),str) or not _BLOB.fullmatch(row['blob']) or row['blob']!='blob-'+row['blob_sha256']+'.zip':raise ManifestError('Invalid blob name')
        if type(row.get('size')) is not int or row['size']<0 or row['size']>4*1024*1024*1024:raise ManifestError('Invalid file size')
        if type(row.get('download_size')) is not int or not 1<=row['download_size']<=2*1024**3:raise ManifestError('Invalid download size')
        total+=row['size']
        if total>4*1024**3:raise ManifestError('Application too large')
        member=row.get('member','payload')
        if member!='payload' and (not isinstance(member,str) or not re.fullmatch(r'files/[0-9a-f]{64}',member)):
            raise ManifestError('Invalid bundle member')
        identity=(row['blob_sha256'],row['download_size'])
        if row['blob'] in blobs and blobs[row['blob']]!=identity:raise ManifestError('Conflicting blob identity')
        blobs[row['blob']]=identity
        files.append(FileEntry(path,row['sha256'],row['size'],row['blob'],row['blob_sha256'],row['download_size'],member))
    for path in seen:
        parts=path.split('/')
        if any('/'.join(parts[:i]) in seen for i in range(1,len(parts))):raise ManifestError('File/directory conflict')
    if obj['channel']=='stable' and Version(obj['version']).is_prerelease:raise ManifestError('Prerelease in stable channel')
    base=obj.get('base_manifest_sha256')
    if base is not None and (not isinstance(base,str) or not _HEX.fullmatch(base)):raise ManifestError('Invalid base manifest hash')
    return Manifest(obj['schema'],obj['app_id'],obj['version'],obj['channel'],obj['platform'],obj['architecture'],
        obj['release_sequence'],obj['minimum_updater'],tuple(read),obj['data_schema_write'],key_id,tuple(files),base)
