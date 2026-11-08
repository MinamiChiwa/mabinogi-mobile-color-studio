"""客户端无关数据和非指针指令不参与自适应地址的唯一性判定。"""
import struct
from types import SimpleNamespace

import capstone
import pytest

from native_live import adaptive_build as adaptation


BASE = 0x180000000
CODE = 0x1000
DATA = 0x3000
MARKER = 0x2000000F


class ReferenceBuild:
    def __init__(self, operations, *, value=0, duplicate=False):
        self.base = BASE
        self.check = lambda: None
        self.d = bytearray(0x4000)
        self.code = bytearray()
        for opcode, slot in operations:
            address = BASE + CODE + len(self.code)
            self.code.extend(opcode + struct.pack('<i', BASE + DATA + slot - address - len(opcode) - 4))
            struct.pack_into('<Q', self.d, DATA + slot, value)
        if duplicate:
            # 无关的只读数据中也出现相同 8 字节，不是目标类使用的槽位。
            struct.pack_into('<Q', self.d, 0x200, value)
        section = SimpleNamespace(Characteristics=0xC0000040, VirtualAddress=DATA,
                                  SizeOfRawData=0x1000, Misc_VirtualSize=0x1000)
        self.pe = SimpleNamespace(get_section_by_rva=lambda rva: section if DATA <= rva < DATA + 0x1000 else None,
                                  get_rva_from_offset=lambda offset: offset)
        self.md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        self.md.detail = True

    def methods(self, *args):
        return [dict(name='get_mousePosition_Injected', rva=hex(CODE))]

    def instructions(self, rva):
        return list(self.md.disasm(bytes(self.code), BASE + int(rva, 16)))

    def u64(self, address):
        return struct.unpack_from('<Q', self.d, address - BASE)[0]


def test_unreferenced_duplicate_bytes_do_not_hide_unique_class_slot():
    build = ReferenceBuild([(b'\x48\x8b\x05', 0)], value=MARKER, duplicate=True)
    assert adaptation._class_slot(build, (0, [0, 0, 7])) == (DATA, MARKER)


def test_narrow_reads_and_pointer_stores_do_not_become_mouse_cache_candidates():
    build = ReferenceBuild([(b'\x48\x8b\x05', 0),   # mov rax, qword ptr [rip + ...]
                            (b'\x8b\x0d', 8),        # mov ecx, dword ptr [rip + ...]
                            (b'\x48\x89\x05', 16)]) # mov qword ptr [rip + ...], rax
    assert adaptation._references(build, (0, []), 'get_mousePosition_Injected') == {(DATA, 0, 'mov')}


def test_multiple_actual_class_slots_remain_ambiguous():
    build = ReferenceBuild([(b'\x48\x8b\x05', 0), (b'\x48\x8b\x0d', 8)], value=MARKER)
    with pytest.raises(ValueError, match='Ambiguous'):
        adaptation._class_slot(build, (0, [0, 0, 7]))


def test_lea_remains_a_valid_class_metadata_reference():
    build = ReferenceBuild([(b'\x48\x8d\x0d', 0)], value=MARKER)
    assert adaptation._class_slot(build, (0, [0, 0, 7])) == (DATA, MARKER)


def test_missing_own_reference_cannot_use_a_file_marker():
    build = ReferenceBuild([], value=MARKER, duplicate=True)
    with pytest.raises(ValueError, match='unreferenced'):
        adaptation._class_slot(build, (0, [0, 0, 7]))
