"""Current-build typed UIChildTransform binding to a native rect diagnostic."""
import struct

from .read_native_rect import SUPPORTED_UNITYPLAYER, read_native_rect_cache

SUPPORTED_GAMEASSEMBLY = '1675c2131534d0ab2fc053af8a2e394d326ba7d22eff0019734be96b1808678f'
SUPPORTED_METADATA = '3f6827a41d26ab50ef0051b881cb2c6dcab0c12aab5e95cc7da0071fae63a847'


def read_toucharea_rect_cache(reader, slot_address, *, gameassembly_sha256,
                             metadata_sha256, unityplayer_sha256,
                             expected_touch_area=None, check=lambda: None):
    if (gameassembly_sha256 != SUPPORTED_GAMEASSEMBLY or metadata_sha256 != SUPPORTED_METADATA
            or unityplayer_sha256 != SUPPORTED_UNITYPLAYER):
        raise ValueError('Unsupported TouchArea/native layout build')
    observed = {}
    layouts = {}

    def read(address, size):
        check()
        if type(address) is not int or address <= 0:
            raise ValueError('Invalid TouchArea read address')
        raw = reader.read(address, size)
        if len(raw) != size or observed.setdefault((address, size), raw) != raw:
            raise ValueError('Short or changed TouchArea read')
        return raw

    def ptr(address):
        value = struct.unpack('<Q', read(address, 8))[0]
        if not value or value % 8:
            raise ValueError('Null/unaligned TouchArea pointer')
        return value

    def typed(address, name, required):
        cls = ptr(address)
        check()
        if reader.class_name(cls) != name:
            raise ValueError('Unexpected TouchArea binding type')
        fs = dict(reader.fields(cls))
        if any(type(fs.get(key)) is not int or fs[key] != offset for key, offset in required.items()):
            raise ValueError('Unexpected TouchArea field layout')
        layouts[cls] = (name, fs)

    typed(slot_address, 'Client.CodeGenerated.UI.DyeingPaletteSlot', {'<TouchArea>k__BackingField': 0x38})
    touch = ptr(slot_address + 0x38)
    if expected_touch_area is not None and (type(expected_touch_area) is not int or touch != expected_touch_area):
        raise ValueError('TouchArea disagrees with motion binding')
    typed(touch, 'MM.Client.Framework.UI.Object.UIChildTransform',
          {'<Transform>k__BackingField': 0x18, '<UISystem>k__BackingField': 0x20})
    # The slot UISystem offset is inherited and is confirmed by the base ctor.
    if ptr(slot_address + 0x28) != ptr(touch + 0x20):
        raise ValueError('TouchArea UISystem mismatch')
    rect = ptr(touch + 0x18)
    typed(rect, 'UnityEngine.RectTransform', {})
    cache = read_native_rect_cache(reader, rect, unityplayer_sha256=unityplayer_sha256, check=check)
    for (address, size), raw in observed.items():
        check()
        if reader.read(address, size) != raw:
            raise ValueError('TouchArea binding changed during cache read')
    for cls, (name, fs) in layouts.items():
        check()
        if reader.class_name(cls) != name or reader.fields(cls) != fs:
            raise ValueError('TouchArea runtime class changed')
    check()
    return dict(binding=dict(ui_slot_address=slot_address, touch_area_address=touch, managed_rect_address=rect),
                cache=cache, ready_for_input=False, screen_geometry_available=False,
                runtime_measurement_verified=False, execution_verified=False, game_response_verified=False,
                scope='Double-checked wrapper to native local cache; no layout freshness, screen projection, or active session proof')
