from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class FileEntry:
    path: str
    sha256: str
    size: int
    blob: str
    blob_sha256: str
    download_size: int
    member: str='payload'


@dataclass(frozen=True)
class Manifest:
    schema: int
    app_id: str
    version: str
    channel: str
    platform: str
    architecture: str
    release_sequence: int
    minimum_updater: int
    data_schema_read: tuple
    data_schema_write: int
    key_id: str
    files: tuple
    base_manifest_sha256: Optional[str] = None

    @classmethod
    def for_test(cls, version, files):
        return cls(1,'MabinogiMobileColorStudio',version,'stable','win32','x86_64',
                   1,1,(1,),1,'test',tuple(files))


@dataclass(frozen=True)
class BlobEntry:
    name: str
    sha256: str
    size: int
    download_size: int


@dataclass(frozen=True)
class UpdatePlan:
    installs: tuple = field(default_factory=tuple)
    removals: tuple = field(default_factory=tuple)
    reused: tuple = field(default_factory=tuple)
    conflicts: tuple = field(default_factory=tuple)
    protected_paths: tuple = field(default_factory=tuple)
    required_blobs: tuple = field(default_factory=tuple)
    download_bytes: int = 0
    stage_bytes: int = 0
    backup_bytes: int = 0
    old_version: str = ''
    new_version: str = ''


@dataclass(frozen=True)
class ProgressEvent:
    kind: str
    received: int = 0
    total: int = 0
    reason_code: str = ''
    version: str = ''
