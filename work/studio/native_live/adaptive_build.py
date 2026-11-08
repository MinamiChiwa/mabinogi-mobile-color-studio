"""Discover compatible TW/KR clients without trusting saved candidate JSON.

The bounded memory cache contains file-verified addresses, never session/input
permissions. Every backend still fingerprints all three files before lookup.
"""
import hashlib
import json
import re
import struct
from collections import OrderedDict
from threading import Lock
from pefile import PEFormatError

from .build_adapters import BuildAdapter, BuildUnsupported, UNITY_LAYOUT, select_adapter
from .il2cpp_discovery import Build
from .managed_layout_contract import CONTRACT_ID, LAYOUTS

PALETTE = 'MM.Client.Presentation.UI.Instances.StageScene.Dyeing.DyeingPaletteInstanceImpl'
INPUT = 'MM.Client.Framework.InputSystem.MMInputSystem'
DISCOVERY_VERSION = 2
_AUTHORITY = object()
_cache = OrderedDict()
_lock = Lock()


def is_adaptive(adapter):
    return getattr(adapter, '_discovery_authority', None) is _AUTHORITY


def matches_fingerprints(adapter, hashes):
    return (adapter.gameassembly_sha256 == hashes.get('gameassembly')
            and adapter.metadata_sha256 == hashes.get('metadata')
            and adapter.unity_layout.sha256 == hashes.get('unityplayer'))


def validate_layout(build):
    """Require unique definitions, including parents and every field's type."""
    found = {}
    for index, (definition, name) in enumerate(build.types):
        if index % 1024 == 0:
            build.check()
        if name not in LAYOUTS:
            continue
        if name in found:
            raise ValueError('Ambiguous metadata class: ' + name)
        actual = (build.type_name(definition[4]),
                  [(f['name'], f['offset'], f['type_name']) for f in build.field_offsets(index)])
        if actual != LAYOUTS[name]:
            raise ValueError('Unsupported managed metadata layout: ' + name)
        found[name] = (index, definition)
    missing = LAYOUTS.keys() - found.keys()
    if missing:
        raise ValueError('Missing metadata classes: ' + ', '.join(sorted(missing)))
    return found


def _references(build, entry, method_name=None):
    import capstone
    result = set()
    for method in build.methods(*entry):
        build.check()
        if not method['rva'] or method_name is not None and method['name'] != method_name:
            continue
        for instruction in build.instructions(method['rva']):
            for operand in instruction.operands:
                if (operand.type == capstone.x86.X86_OP_MEM
                        and operand.mem.base == capstone.x86.X86_REG_RIP
                        and operand.size == 8 and operand.access & capstone.CS_AC_READ):
                    address = instruction.address + instruction.size + operand.mem.disp
                    section = build.pe.get_section_by_rva(address - build.base)
                    if section is not None and section.Characteristics & 0x80000000 and address % 8 == 0:
                        delta=address-build.base-section.VirtualAddress
                        if delta+8<=section.SizeOfRawData:
                            value=build.u64(address)
                        elif section.SizeOfRawData<=delta and delta+8<=section.Misc_VirtualSize:
                            value=0  # Loader zero-fill; never read unrelated file bytes.
                        else:
                            continue
                        result.add((address - build.base, value, instruction.mnemonic))
    return result


def _class_slot(build, entry):
    marker = 0x20000001 | (entry[1][2] << 1)
    # A marker value can also occur in unrelated code, resources or data.
    # Only a mapped writable slot referenced by this class is evidence.
    # _references verifies pointer width/access, alignment and file backing.
    own = {rva for rva, value, _ in _references(build, entry) if value == marker}
    if len(own) != 1:
        raise ValueError('Ambiguous or unreferenced metadata class slot')
    return own.pop(), marker


def discover_adapter(files, hashes, check=lambda: None):
    check()
    if hashes.get('unityplayer') != UNITY_LAYOUT.sha256:
        raise BuildUnsupported(hashes, 'Unsupported UnityPlayer build; native layout requires review')
    build = None
    try:
        build = Build(files, hashes, check)
        classes = validate_layout(build)
        palette, palette_marker = _class_slot(build, classes[PALETTE])
        input_slot, input_marker = _class_slot(build, classes[INPUT])
        mouse = {rva for rva, value, mnemonic in _references(build, classes['UnityEngine.Input'],
                                                            'get_mousePosition_Injected')
                 if value == 0 and mnemonic == 'mov'}
        if len(mouse) != 1:
            raise ValueError('Ambiguous metadata mouse getter cache')
        evidence = hashlib.sha256(json.dumps(LAYOUTS, sort_keys=True).encode()).hexdigest()
        return BuildAdapter('adaptive-v2-' + hashes['gameassembly'][:16], hashes['gameassembly'],
            hashes['metadata'], palette, 'legacy-mouse-v1',
            palette_uninitialized_marker=palette_marker, input_class_rva=input_slot,
            input_class_uninitialized_marker=input_marker, mouse_getter_cache_rva=mouse.pop(),
            capability='diagnostic_only', managed_layout_id=CONTRACT_ID,
            managed_layout_evidence_sha256=evidence, _discovery_authority=_AUTHORITY)
    except (ValueError, IndexError, StopIteration, struct.error, PEFormatError) as exc:
        raise BuildUnsupported(hashes, 'Adaptive build discovery rejected: ' + str(exc)) from exc
    finally:
        if build is not None:
            build.pe.close()


def resolve_adapter(files, hashes, check=lambda: None):
    """Known builds retain their registry; compatible unknown builds relocate."""
    check()
    try:
        return select_adapter(hashes)
    except BuildUnsupported:
        pass
    key = (DISCOVERY_VERSION, *(hashes.get(k) for k in ('gameassembly', 'metadata', 'unityplayer')))
    with _lock:
        cached = _cache.get(key)
        if cached is not None:
            _cache.move_to_end(key)
    if cached is not None:
        check()
        return cached
    adapter = discover_adapter(files, hashes, check)
    check()
    with _lock:
        _cache[key] = adapter
        while len(_cache) > 4:
            _cache.popitem(last=False)
    return adapter


def enable_session_input(backend, baseline, observation, frames):
    """A passive model check plus independent screenshots grants one session.

    Called only after normal IO has checked live geometry and session binding.
    The grant is in memory and is never loaded from a cache or diagnostic file.
    """
    if not is_adaptive(getattr(backend, 'adapter', None)):
        return
    backend._adaptive_input_session = None
    if getattr(backend, '_adaptive_selected_server', None) not in ('tw', 'kr'):
        raise ValueError('Adaptive build requires Taiwan or Korea server selection')
    comparison = baseline.get('capture', {}).get('cpu_comparison', {})
    colors = observation.get('client_hex')
    # The IO caller adds the independently bound checkpoint colors.
    identity = observation.get('process_identity')
    token = observation.get('session_token')
    if (baseline.get('stop_reason') != 'passive_baseline_collected'
            or comparison.get('client_float_hex_equal') is not True
            or comparison.get('float_within_tolerance') is not True
            or observation.get('active') is not True
            or identity != baseline.get('baseline', {}).get('process_identity')
            or token != baseline.get('baseline', {}).get('session_token')
            or backend.process_identity() != identity
            or not isinstance(colors, list) or len(colors) not in (2, 3)
            or any(not isinstance(color,str) or not re.fullmatch('#[0-9A-F]{6}',color) for color in colors)
            or not isinstance(frames, list) or len(frames) != 2
            or any(frame.get('screenshot_hex_verified') is not True
                   or frame.get('screenshot_hex') != colors
                   or frame.get('hex_source') != ['screenshot'] * len(colors) for frame in frames)):
        raise ValueError('Adaptive build requires passive model and independent screenshot HEX verification')
    backend._adaptive_input_session = (backend.adapter, identity, token)


def session_input_allowed(backend):
    grant = getattr(backend, '_adaptive_input_session', None)
    return bool(is_adaptive(getattr(backend, 'adapter', None)) and isinstance(grant,tuple) and len(grant)==3
                and grant[0] is backend.adapter and grant[1] == backend.process_identity())


def require_session_input(backend, observation):
    if not is_adaptive(getattr(backend,'adapter',None)):
        return
    grant=getattr(backend,'_adaptive_input_session',None)
    if (not session_input_allowed(backend) or observation.get('active') is not True
            or grant[1]!=observation.get('process_identity') or grant[2]!=observation.get('session_token')):
        backend._adaptive_input_session=None
        raise ValueError('Adaptive build input session changed; independent verification required')
