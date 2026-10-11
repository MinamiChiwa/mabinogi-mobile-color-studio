"""Stream one verified blob into one verified application file."""
import zipfile,hashlib,stat,re
from pathlib import Path
from .paths import hash_file

def unpack_blob(blob,row,destination):
    blob=Path(blob);destination=Path(destination)
    if blob.stat().st_size!=row.download_size or hash_file(blob)!=row.blob_sha256:raise ValueError('Blob hash or size mismatch')
    with zipfile.ZipFile(blob) as archive:
        infos=archive.infolist()
        if not 1<=len(infos)<=128:raise ValueError('Unexpected blob content')
        names=set();total=0
        for info in infos:
            if info.filename in names or (info.filename!='payload' and not re.fullmatch(r'files/[0-9a-f]{64}',info.filename)):
                raise ValueError('Unexpected blob member')
            if info.is_dir() or stat.S_ISLNK(info.external_attr>>16):raise ValueError('Blob link rejected')
            names.add(info.filename);total+=info.file_size
        if total>2*1024**3:raise ValueError('Blob too large')
        info=archive.getinfo(row.member)
        if stat.S_ISLNK(info.external_attr>>16) or info.file_size!=row.size:raise ValueError('Invalid payload size or link')
        destination.parent.mkdir(parents=True,exist_ok=True);h=hashlib.sha256();written=0
        try:
            with archive.open(info) as source,destination.open('wb') as target:
                for chunk in iter(lambda:source.read(65536),b''):
                    written+=len(chunk)
                    if written>row.size:raise ValueError('Payload too large')
                    target.write(chunk);h.update(chunk)
            if written!=row.size or h.hexdigest()!=row.sha256:raise ValueError('Payload hash mismatch')
        except BaseException:destination.unlink(missing_ok=True);raise
