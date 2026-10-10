"""Combine local rect and sparse Transform observations into corner candidates."""
import numpy as np

from .read_native_transform import read_native_transform_matrix
from .read_toucharea_rect import SUPPORTED_GAMEASSEMBLY, SUPPORTED_METADATA, SUPPORTED_UNITYPLAYER, read_toucharea_rect_cache


def read_toucharea_geometry_cache(reader, slot_address, *, gameassembly_sha256,
                                  metadata_sha256, unityplayer_sha256,
                                  expected_touch_area=None, check=lambda: None):
    build = dict(gameassembly_sha256=gameassembly_sha256, metadata_sha256=metadata_sha256,
                 unityplayer_sha256=unityplayer_sha256)
    first_rect = read_toucharea_rect_cache(reader, slot_address, **build,
        expected_touch_area=expected_touch_area, check=check)
    managed = first_rect['binding']['managed_rect_address']
    first_matrix = read_native_transform_matrix(reader, managed, unityplayer_sha256=unityplayer_sha256, check=check)
    second_rect = read_toucharea_rect_cache(reader, slot_address, **build,
        expected_touch_area=expected_touch_area, check=check)
    second_matrix = read_native_transform_matrix(reader, managed, unityplayer_sha256=unityplayer_sha256, check=check)
    if first_rect != second_rect or first_matrix != second_matrix:
        raise ValueError('TouchArea geometry changed between observations')
    if int(first_rect['cache']['native_rect_address'], 16) != first_matrix['native_transform_address']:
        raise ValueError('Rect and Transform native object disagree')
    x, y, width, height = first_rect['cache']['cached_local_rect']
    if width <= 0 or height <= 0:
        raise ValueError('Nonpositive TouchArea rect')
    matrix = np.asarray(first_matrix['local_to_world_matrix'], dtype=np.float32)
    local = np.asarray([[x, y], [x + width, y], [x, y + height], [x + width, y + height]], dtype=np.float32)
    with np.errstate(over='ignore', invalid='ignore'):
        world = matrix[:3, 0] * local[:, 0, None] + matrix[:3, 1] * local[:, 1, None] + matrix[:3, 3]
    if not np.isfinite(world).all():
        raise ValueError('Nonfinite TouchArea corner candidates')
    axis_aligned = (matrix[0, 0] > 0 and matrix[1, 1] > 0
                    and all(abs(float(matrix[a, b])) <= 1e-4 for a, b in ((0, 1), (1, 0), (2, 0), (2, 1))))
    check()
    return dict(rect=first_rect, transform=first_matrix, local_corners=local.tolist(),
                predicted_unity_corners=world[:, :2].tolist(), predicted_world_corners=world.tolist(),
                screen_origin='unity_bottom_left', axis_aligned_candidate=bool(axis_aligned),
                cache_freshness_verified=False, runtime_measurement_verified=False,
                screen_geometry_available=False, ready_for_input=False,
                scope='Repeated rect/matrix cache diagnostic and float32 corner calculation; no actual corner measurement, synchronized layout, or desktop/client/DPI mapping')
