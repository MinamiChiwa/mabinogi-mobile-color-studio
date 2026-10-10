"""Explicit normalized-native to board-local pixel coordinate adapter.

Relative matrices describe texture motion, not material-column motion or
mouse commands. Rectangular boards are rejected because atlas_pose requires
a similarity while unequal width/height would produce an affine transform.
"""
import numpy as np
from atlas_pose import homogeneous
from native_palette_scoring import _pose, score_native_pose


def _size(board):
    bounds = np.asarray(board, dtype=float)
    if bounds.shape != (4,) or not np.isfinite(bounds).all():
        raise ValueError('Invalid board bounds')
    width, height = bounds[2:] - bounds[:2]
    if width <= 0 or height <= 0 or not np.isclose(width, height, rtol=0, atol=1e-3):
        raise ValueError('A square board is required for similarity adaptation')
    # Native float32 corner calculations can differ by ~1e-4 physical pixels.
    # Normalize only this submillipixel discrepancy for the similarity adapter;
    # replay and observed bounds retain their original separate dimensions.
    side=(width+height)/2
    return side,side


def native_to_board(pose, board):
    """Map undistorted normalized canonical coordinates to board-local pixels.

    This absolute map flips Y and is not itself an atlas similarity. Only
    target @ inverse(reference) may be passed to atlas_pose consumers.
    """
    pose = _pose(pose)
    width, height = _size(board)
    angle = np.radians(pose['rotation_degrees'])
    c, s = np.cos(angle), np.sin(angle)
    flip = np.diag([width, -height])
    matrix = np.eye(3)
    matrix[:2, :2] = flip @ (pose['scale'] * np.array([[c, -s], [s, c]]))
    matrix[:2, 2] = np.array([width / 2, height / 2]) + flip @ pose['position']
    return matrix


def relative_board_pose(target, reference, board):
    """Return a board-local similarity mapping reference texture to target."""
    return homogeneous(native_to_board(target, board) @ np.linalg.inv(native_to_board(reference, board)))


def board_to_native(relative, reference, board):
    """Recover native absolute pose from a relative atlas pixel matrix."""
    width, height = _size(board)
    absolute = homogeneous(relative) @ native_to_board(reference, board)
    inverse_flip = np.diag([1 / width, -1 / height])
    rotation_scale = inverse_flip @ absolute[:2, :2]
    position = inverse_flip @ (absolute[:2, 2] - [width / 2, height / 2])
    return _pose(dict(position=position,
                      scale=float(np.hypot(rotation_scale[0, 0], rotation_scale[1, 0])),
                      rotation_degrees=float(np.degrees(np.arctan2(rotation_scale[1, 0], rotation_scale[0, 0])))))


def score_board_pose(session, relative, reference, board, rules, *, check=lambda: None):
    """Recompute native color predictions at an explicit relative pixel pose."""
    matrix = homogeneous(relative)
    result = score_native_pose(session, board_to_native(matrix, reference, board), rules, check=check)
    result.update(prediction_pose=matrix[:2].tolist(),
                  prediction_pose_source='explicit_board_relative_to_native_adapter')
    return result
