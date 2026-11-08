"""Adaptive clients must remain read-only until the current session is proved."""
import copy
import hashlib
import struct
from dataclasses import replace
from types import SimpleNamespace

import pytest

from native_live import adaptive_build as adaptation
from native_live import il2cpp_discovery as discovery
from native_live.build_adapters import (BuildUnsupported, TW_ADAPTER, UNITY_BUILD,
    enable_selected_server_input, input_is_allowed, require_input_capability)


def candidate():
    return replace(TW_ADAPTER, adapter_id='adaptive-test', gameassembly_sha256='a' * 64,
                   metadata_sha256='b' * 64, capability='diagnostic_only',
                   _discovery_authority=adaptation._AUTHORITY)


def session(server='tw', count=3):
    identity=(12, 34, 56, 'a' * 64)
    backend=SimpleNamespace(adapter=candidate(), process_identity=lambda:identity)
    enable_selected_server_input(backend, server)
    observed=dict(active=True, process_identity=identity, session_token=['palette', 123],
                  client_hex=['#123456'] * count)
    baseline=dict(stop_reason='passive_baseline_collected', baseline=copy.deepcopy(observed),
                  capture=dict(cpu_comparison=dict(client_float_hex_equal=True, float_within_tolerance=True)))
    frames=[dict(screenshot_hex=observed['client_hex'][:], screenshot_hex_verified=True,
                 hex_source=['screenshot'] * count) for _ in range(2)]
    return backend, baseline, observed, frames


@pytest.mark.parametrize('server', ['tw', 'kr'])
@pytest.mark.parametrize('count', [2, 3])
def test_new_build_needs_current_palette_model_and_two_independent_frames(server, count):
    backend, baseline, observed, frames=session(server, count)
    assert not input_is_allowed(backend)
    with pytest.raises(ValueError, match='live input verification'):
        require_input_capability(backend)
    adaptation.enable_session_input(backend, baseline, observed, frames)
    assert input_is_allowed(backend)
    assert backend.adapter.capability == 'diagnostic_only'
    assert not backend.adapter.input_verified  # No permanent build promotion.
    backend.process_identity=lambda:(99, 34, 56, 'a' * 64)
    assert not input_is_allowed(backend)


@pytest.mark.parametrize('failure', ['cpu_hex','cpu_float','inactive','token','process','frame_count',
                                    'hex','missing_hex','native_fallback','unverified','baseline'])
def test_failed_model_or_visual_evidence_never_allows_input(failure):
    backend, baseline, observed, frames=session()
    adaptation.enable_session_input(backend, baseline, observed, frames)
    if failure=='cpu_hex':baseline['capture']['cpu_comparison']['client_float_hex_equal']=False
    elif failure=='cpu_float':baseline['capture']['cpu_comparison']['float_within_tolerance']=False
    elif failure=='inactive':observed['active']=False
    elif failure=='token':observed['session_token']=['other']
    elif failure=='process':backend.process_identity=lambda:(999,)
    elif failure=='frame_count':frames.pop()
    elif failure=='hex':frames[0]['screenshot_hex'][0]='#ABCDEF'
    elif failure=='missing_hex':frames[1]['screenshot_hex'][0]=None
    elif failure=='native_fallback':frames[0]['hex_source'][0]='native_checkpoint'
    elif failure=='unverified':frames[0]['screenshot_hex_verified']=False
    elif failure=='baseline':baseline['stop_reason']='binding_changed'
    with pytest.raises(ValueError, match='independent screenshot'):
        adaptation.enable_session_input(backend, baseline, observed, frames)
    assert not input_is_allowed(backend)


def test_saved_candidates_cannot_supply_discovery_authority_or_session_grants():
    backend, baseline, observed, frames=session()
    backend.adapter=replace(backend.adapter, _discovery_authority=None)
    backend.validation_input_enabled=True
    backend._adaptive_input_session=['adapter-from-json', observed['process_identity'], observed['session_token']]
    adaptation.enable_session_input(backend, baseline, observed, frames)
    assert not input_is_allowed(backend)


def test_other_server_and_unselected_client_cannot_use_adaptive_input():
    backend, baseline, observed, frames=session()
    with pytest.raises(ValueError, match='服务器'):
        enable_selected_server_input(backend, 'jp')
    backend._adaptive_selected_server=None
    with pytest.raises(ValueError, match='server selection'):
        adaptation.enable_session_input(backend, baseline, observed, frames)
    assert not input_is_allowed(backend)


def test_selecting_server_again_revokes_the_session_grant():
    backend, baseline, observed, frames=session()
    adaptation.enable_session_input(backend, baseline, observed, frames)
    enable_selected_server_input(backend,'kr')
    assert not input_is_allowed(backend)


def test_known_client_keeps_registered_adapter_without_offline_discovery(monkeypatch):
    monkeypatch.setattr(adaptation,'discover_adapter',lambda *args:pytest.fail('known build parsed'))
    hashes=dict(gameassembly=TW_ADAPTER.gameassembly_sha256, metadata=TW_ADAPTER.metadata_sha256,
                unityplayer=UNITY_BUILD)
    assert adaptation.resolve_adapter({},hashes) is TW_ADAPTER


def test_cache_reuses_only_matching_file_fingerprints_and_never_permissions(monkeypatch):
    monkeypatch.setattr(adaptation,'_cache',adaptation.OrderedDict())
    calls=[]
    def discover(files, hashes, check):
        calls.append(hashes.copy())
        return replace(candidate(), metadata_sha256=hashes['metadata'])
    monkeypatch.setattr(adaptation,'discover_adapter',discover)
    hashes=dict(gameassembly='a'*64,metadata='b'*64,unityplayer=UNITY_BUILD)
    first=adaptation.resolve_adapter({},hashes)
    assert adaptation.resolve_adapter({},hashes) is first
    hashes['metadata']='c'*64
    assert adaptation.resolve_adapter({},hashes) is not first
    assert len(calls)==2
    assert not input_is_allowed(SimpleNamespace(adapter=first,validation_input_enabled=True))
    def cancel():raise InterruptedError('stop')
    with pytest.raises(InterruptedError):adaptation.resolve_adapter({},hashes,cancel)


def test_unknown_unity_cannot_reuse_native_offsets(monkeypatch):
    monkeypatch.setattr(adaptation,'Build',lambda *args:pytest.fail('unknown Unity parsed'))
    with pytest.raises(BuildUnsupported,match='UnityPlayer'):
        adaptation.discover_adapter({},dict(unityplayer='unknown'))


class LayoutBuild:
    def __init__(self):
        self.check=lambda:None
        self.types=[]
        for i,(name,layout) in enumerate(adaptation.LAYOUTS.items()):
            v=[0]*24;v[4]=i;v[2]=i
            self.types.append((v,name))
    def type_name(self,index):return list(adaptation.LAYOUTS.values())[index][0]
    def field_offsets(self,index):
        return [dict(name=n,offset=o,type_name=t) for n,o,t in list(adaptation.LAYOUTS.values())[index][1]]


def test_all_reader_layouts_must_exist_and_match_types_offsets_and_parents():
    build=LayoutBuild()
    assert len(adaptation.validate_layout(build))==len(adaptation.LAYOUTS)
    fields=build.field_offsets
    build.field_offsets=lambda i:fields(i)+[dict(name='new',offset=123,type_name='int32')]
    with pytest.raises(ValueError,match='layout'):adaptation.validate_layout(build)
    build=LayoutBuild();build.types.pop()
    with pytest.raises(ValueError,match='Missing'):adaptation.validate_layout(build)
    build=LayoutBuild();build.types.append(build.types[0])
    with pytest.raises(ValueError,match='Ambiguous'):adaptation.validate_layout(build)
    build=LayoutBuild();build.type_name=lambda index:'wrong-parent'
    with pytest.raises(ValueError,match='layout'):adaptation.validate_layout(build)


@pytest.mark.parametrize('offsets,own,accepted', [([8],[8],True),([8,24],[8],True),
    ([8,24],[8,24],False),([8],[],False),([8],[24],False)])
def test_class_marker_requires_unique_own_reference(monkeypatch, offsets, own, accepted):
    definition=[0,0,7]
    marker=0x20000001|(7<<1)
    raw=bytearray(64)
    for offset in offsets:struct.pack_into('<Q',raw,offset,marker)
    build=SimpleNamespace(d=raw,check=lambda:None,pe=SimpleNamespace(get_rva_from_offset=lambda x:x))
    monkeypatch.setattr(adaptation,'_references',lambda *args:{(rva,struct.unpack_from('<Q',raw,rva)[0],'mov') for rva in own})
    if accepted:assert adaptation._class_slot(build,(0,definition))==(8,marker)
    else:
        with pytest.raises(ValueError,match='Ambiguous'):adaptation._class_slot(build,(0,definition))


def test_client_file_read_rejects_mutations_wrong_fingerprints_and_cancellation(tmp_path):
    path=tmp_path/'client';path.write_bytes(b'x'*2**20+b'end')
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    assert discovery.read_build_file(path,digest,2**21,lambda:None)==path.read_bytes()
    with pytest.raises(ValueError,match='changed'):
        discovery.read_build_file(path,'0'*64,2**21,lambda:None)
    with pytest.raises(ValueError,match='size'):
        discovery.read_build_file(path,digest,10,lambda:None)
    calls=0
    def change():
        nonlocal calls
        calls+=1
        if calls==3:path.write_bytes(b'changed')
    with pytest.raises(ValueError,match='changed'):
        discovery.read_build_file(path,digest,2**21,change)
    def cancel():raise InterruptedError('F9')
    with pytest.raises(InterruptedError):discovery.read_build_file(path,digest,2**21,cancel)


def test_unsupported_or_corrupt_metadata_fails_before_pe_parsing(tmp_path):
    path=tmp_path/'metadata'
    for content in (b'short',struct.pack('<II',0xfab11baf,32)+bytes(200)):
        path.write_bytes(content)
        with pytest.raises(ValueError,match='schema'):
            discovery.Build(dict(metadata=path),dict(metadata=hashlib.sha256(content).hexdigest()))


def test_adapter_is_bound_to_all_three_fingerprints():
    adapter=candidate()
    hashes=dict(gameassembly=adapter.gameassembly_sha256,metadata=adapter.metadata_sha256,unityplayer=UNITY_BUILD)
    assert adaptation.matches_fingerprints(adapter,hashes)
    for key in hashes:
        changed=dict(hashes);changed[key]='changed'
        assert not adaptation.matches_fingerprints(adapter,changed)


@pytest.mark.parametrize('server,shift', [('tw',0),('kr',128)])
def test_discovery_relocates_both_clients_without_granting_input(monkeypatch,server,shift):
    class Client(LayoutBuild):
        def __init__(self,*args):
            super().__init__()
            self.pe=SimpleNamespace(get_rva_from_offset=lambda x:x,close=lambda:None)
            raw=bytearray(512)
            self.refs={}
            for name,slot in ((adaptation.PALETTE,16+shift),(adaptation.INPUT,48+shift)):
                i=next(i for i,(_,n) in enumerate(self.types) if n==name)
                marker=0x20000001|(self.types[i][0][2]<<1)
                struct.pack_into('<Q',raw,slot,marker)
                self.refs[i]={(slot,marker,'mov')}
            i=next(i for i,(_,n) in enumerate(self.types) if n=='UnityEngine.Input')
            self.refs[i]={(80+shift,0,'mov')}
            self.d=raw
    monkeypatch.setattr(adaptation,'Build',Client)
    monkeypatch.setattr(adaptation,'_references',lambda b,e,method_name=None:b.refs[e[0]])
    hashes=dict(gameassembly='c'*64,metadata='d'*64,unityplayer=UNITY_BUILD)
    adapter=adaptation.discover_adapter({},hashes)
    assert adaptation.is_adaptive(adapter)
    assert (adapter.palette_class_rva,adapter.input_class_rva,adapter.mouse_getter_cache_rva)==(16+shift,48+shift,80+shift)
    backend=SimpleNamespace(adapter=adapter)
    enable_selected_server_input(backend,server)
    assert not input_is_allowed(backend)


def test_session_grant_cannot_follow_another_palette_in_the_same_process():
    backend,baseline,observed,frames=session()
    adaptation.enable_session_input(backend,baseline,observed,frames)
    adaptation.require_session_input(backend,observed)
    observed['session_token']=['new-palette']
    with pytest.raises(ValueError,match='session changed'):
        adaptation.require_session_input(backend,observed)
    assert not input_is_allowed(backend)


def test_adaptive_planning_requires_full_visual_proof_before_first_input(monkeypatch,tmp_path):
    from native_live.project_probe_io import ProjectProbeIO
    from native_live.project_closed_loop_io import ProjectClosedLoopIO
    from native_live.dye_visual_readiness import VisualNotReady
    backend,baseline,observed,frames=session()
    backend.build_diagnostic={}
    io=object.__new__(ProjectClosedLoopIO)
    io.backend=backend;io.reference=baseline;io.last_observation=observed
    io.last_client_hex=observed['client_hex'];io.folder=tmp_path;io.input_attempts=0
    reads=[]
    def capture(self,label,deadline,*,read_colors=True):
        reads.append(read_colors)
        return frames
    monkeypatch.setattr(ProjectProbeIO,'frames',capture)
    frames[0]['hex_source'][0]='native_checkpoint'
    with pytest.raises(VisualNotReady):io.planning_frames('initial',999.)
    assert not input_is_allowed(backend)
    frames[0]['hex_source'][0]='screenshot'
    assert io.planning_frames('initial',999.)==frames
    assert input_is_allowed(backend)
    io.planning_frames('next',999.)
    assert reads==[True,True,False]
    assert (tmp_path/'adaptive-session.json').is_file()


def test_incomplete_pe_or_metadata_tables_produce_a_build_error(monkeypatch):
    from pefile import PEFormatError
    def corrupt(*args):raise PEFormatError('truncated PE')
    monkeypatch.setattr(adaptation,'Build',corrupt)
    with pytest.raises(BuildUnsupported,match='truncated PE'):
        adaptation.discover_adapter({},dict(unityplayer=UNITY_BUILD))


def test_pe_pointer_cannot_read_across_raw_section_or_into_virtual_zero_fill():
    build=object.__new__(discovery.Build)
    build.base=0x180000000;build.d=bytes(range(32));build.check=lambda:None
    section=SimpleNamespace(VirtualAddress=0x1000,SizeOfRawData=16,PointerToRawData=0)
    build.pe=SimpleNamespace(get_section_by_rva=lambda rva:section)
    assert build.u64(build.base+0x1008)==struct.unpack('<Q',bytes(range(8,16)))[0]
    with pytest.raises(ValueError,match='Truncated'):build.u64(build.base+0x100c)
    with pytest.raises(ValueError,match='Unmapped'):build.u64(build.base+0x1010)


def test_discovered_client_can_read_toucharea_without_static_registry_reselection(monkeypatch):
    from native_live import read_toucharea_rect as rect
    adapter=candidate()
    memory={0x1000:0x5000,0x1038:0x2000,0x1028:0x4000,
            0x2000:0x6000,0x2018:0x3000,0x2020:0x4000,0x3000:0x7000}
    names={0x5000:'Client.CodeGenerated.UI.DyeingPaletteSlot',
           0x6000:'MM.Client.Framework.UI.Object.UIChildTransform',0x7000:'UnityEngine.RectTransform'}
    fields={0x5000:{'<TouchArea>k__BackingField':0x38},
            0x6000:{'<Transform>k__BackingField':0x18,'<UISystem>k__BackingField':0x20},0x7000:{}}
    reader=SimpleNamespace(read=lambda address,size:struct.pack('<Q',memory[address]),
                           class_name=lambda cls:names[cls],fields=lambda cls:fields[cls].copy())
    monkeypatch.setattr(rect,'read_native_rect_cache',lambda *args,**kwargs:{'native_rect_address':'0x8000'})
    kwargs=dict(gameassembly_sha256=adapter.gameassembly_sha256,metadata_sha256=adapter.metadata_sha256,
                unityplayer_sha256=UNITY_BUILD,adapter=adapter)
    result=rect.read_toucharea_rect_cache(reader,0x1000,**kwargs,expected_touch_area=0x2000)
    assert result['binding']['managed_rect_address']==0x3000
    assert result['ready_for_input'] is False
    kwargs['metadata_sha256']='changed'
    with pytest.raises(ValueError,match='Unsupported'):
        rect.read_toucharea_rect_cache(reader,0x1000,**kwargs)
    kwargs['metadata_sha256']=adapter.metadata_sha256
    kwargs['adapter']=replace(adapter,_discovery_authority=None)
    with pytest.raises(ValueError,match='Unsupported'):
        rect.read_toucharea_rect_cache(reader,0x1000,**kwargs)
