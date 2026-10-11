"""Server-neutral build adapter registry.

The title/locale is a hint only. A fingerprint is required before any static
address or input backend is allowed to run.
"""
from dataclasses import dataclass

TW_BUILD='1675c2131534d0ab2fc053af8a2e394d326ba7d22eff0019734be96b1808678f'
TW_METADATA='3f6827a41d26ab50ef0051b881cb2c6dcab0c12aab5e95cc7da0071fae63a847'
KR_BUILD='bd9d827b7cd342c677c1e93a752f61c2e75a913d08ac9879ce285c852986ca08'
KR_METADATA='cdeed3914cc11325e9771047bdbe4bb0acf1733f16f01783418f753c2a6fde8a'
UNITY_BUILD='e969642866c2195f16a0bd0e52ff8ffe87cad5b213fda9a62ca1564970e2fa26'

@dataclass(frozen=True)
class UnityLayout:
    layout_id:str
    sha256:str
    mouse_getter_rva:int=0x185310
    screen_global_rva:int=0x1b23390
    viewport_offset:int=0x120

UNITY_LAYOUT=UnityLayout('unity-2021.3.51p3-x64',UNITY_BUILD)

@dataclass(frozen=True)
class BuildAdapter:
    adapter_id:str
    gameassembly_sha256:str
    metadata_sha256:str
    palette_class_rva:int
    input_backend_id:str
    region_layouts:tuple=(2,3)
    palette_uninitialized_marker:int=0x20035507
    input_class_rva:int=0x1074fa20
    input_class_uninitialized_marker:int=0x20041b49
    mouse_getter_cache_rva:int=0x11100078
    capability:str='input_verified'
    managed_layout_id:str='dye-managed-v31-v1'
    managed_layout_evidence_sha256:str='tw-original-verified-runtime-layouts'
    unity_layout:UnityLayout=UNITY_LAYOUT

    @property
    def input_verified(self):return self.capability=='input_verified'

    def diagnostic(self):
        return dict(adapter_id=self.adapter_id,capability=self.capability,input_verified=self.input_verified,
            managed_layout_id=self.managed_layout_id,managed_layout_evidence_sha256=self.managed_layout_evidence_sha256,
            unity_layout_id=self.unity_layout.layout_id,region_layouts=list(self.region_layouts))

TW_ADAPTER=BuildAdapter('unity-static-v1',TW_BUILD,TW_METADATA,0x106c9010,'legacy-mouse-v1')
KR_ADAPTER=BuildAdapter('kr-20261012-research-candidate',KR_BUILD,KR_METADATA,0x10d1bf18,'legacy-mouse-v1',
    palette_uninitialized_marker=0x20036bfb,input_class_rva=0x10d7e580,input_class_uninitialized_marker=0x20043315,
    mouse_getter_cache_rva=0x11694ce8,capability='diagnostic_only',
    managed_layout_evidence_sha256='ae9f8974b2b3a54c9cf49832cea394824fe43408905bc71f81a66744138fd90a')
KNOWN=(TW_ADAPTER,KR_ADAPTER)

class BuildUnsupported(ValueError):
    def __init__(self,hashes):
        self.hashes=dict(hashes);super().__init__('Unsupported game/metadata build for static object walk')

def select_adapter(hashes):
    for adapter in KNOWN:
        if (hashes.get('gameassembly')==adapter.gameassembly_sha256 and hashes.get('metadata')==adapter.metadata_sha256
                and hashes.get('unityplayer')==adapter.unity_layout.sha256):return adapter
    raise BuildUnsupported(hashes)


def input_is_allowed(backend):
    adapter=getattr(backend,'adapter',None)
    return adapter is None or adapter.input_verified or (
        adapter==KR_ADAPTER and getattr(backend,'validation_input_enabled',False) is True)


def require_input_capability(backend):
    if not input_is_allowed(backend):
        raise ValueError('This game build still requires live input verification')


def enable_known_validation_input(backend,adapter_id):
    """Explicit test launch only; discoveries/config JSON never authorize input."""
    if adapter_id!=KR_ADAPTER.adapter_id or getattr(backend,'adapter',None)!=KR_ADAPTER:
        raise ValueError('Validation input requires the exact Korean game build')
    backend.validation_input_enabled=True
