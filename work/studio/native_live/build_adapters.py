"""Server-neutral build adapter registry.

The title/locale is a hint only. A fingerprint is required before any static
address or input backend is allowed to run.
"""
from dataclasses import dataclass

TW_BUILD='1675c2131534d0ab2fc053af8a2e394d326ba7d22eff0019734be96b1808678f'
TW_METADATA='3f6827a41d26ab50ef0051b881cb2c6dcab0c12aab5e95cc7da0071fae63a847'

@dataclass(frozen=True)
class BuildAdapter:
    adapter_id:str
    gameassembly_sha256:str
    metadata_sha256:str
    palette_class_rva:int
    input_backend_id:str
    region_layouts:tuple=(2,3)

KNOWN=(BuildAdapter('unity-static-v1',TW_BUILD,TW_METADATA,0x106c9010,'legacy-mouse-v1'),)

class BuildUnsupported(ValueError):
    def __init__(self,hashes):
        self.hashes=dict(hashes);super().__init__('Unsupported game/metadata build for static object walk')

def select_adapter(hashes):
    for adapter in KNOWN:
        if hashes.get('gameassembly')==adapter.gameassembly_sha256 and hashes.get('metadata')==adapter.metadata_sha256:return adapter
    raise BuildUnsupported(hashes)
