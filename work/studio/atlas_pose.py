"""Board-local similarity poses shared by planning, budgets and execution."""
import numpy as np


def homogeneous(matrix):
    value = np.asarray(matrix, float)
    if value.shape == (2, 3):
        value = np.vstack((value, [0., 0., 1.]))
    if (value.shape != (3, 3) or not np.isfinite(value).all() or
            not np.allclose(value[2], [0, 0, 1], atol=1e-9)):
        raise ValueError('Invalid pose matrix')
    a = value[:2, :2]
    scale = np.hypot(a[0, 0], a[1, 0])
    if scale <= 0 or not np.allclose(a, [[a[0, 0], -a[1, 0]],
                                        [a[1, 0], a[0, 0]]], atol=1e-6):
        raise ValueError('Pose must be a positive similarity transform')
    return value.copy()


def candidate_pose(candidate, board):
    if 'matrix' in candidate:
        return homogeneous(candidate['matrix'])
    l, t, r, b = board
    center = np.array([(r-l)/2, (b-t)/2])
    angle = np.radians(float(candidate.get('angle', 0)))
    scale = float(candidate.get('scale', 1))
    a = scale*np.array([[np.cos(angle), -np.sin(angle)],
                        [np.sin(angle), np.cos(angle)]])
    offset = center+np.array([candidate['dx'], candidate['dy']])-a@center
    return homogeneous(np.column_stack((a, offset)))


def pose_fields(matrix, board):
    pose = homogeneous(matrix)
    l, t, r, b = board
    center = np.array([(r-l)/2, (b-t)/2])
    move = pose[:2, :2]@center+pose[:2, 2]-center
    return dict(matrix=pose[:2].tolist(), dx=float(move[0]), dy=float(move[1]),
                angle=float(np.degrees(np.arctan2(pose[1, 0], pose[0, 0]))),
                scale=float(np.hypot(pose[0, 0], pose[1, 0])))


def relative_candidate(candidate, actual_pose, board):
    """Rebase from a measured pose, never subtract center displacements."""
    relative = candidate_pose(candidate, board)@np.linalg.inv(homogeneous(actual_pose))
    return dict(candidate, **pose_fields(relative, board))


def marker_errors(target, actual, markers):
    """Where each planned source color actually lands, in screen pixels."""
    target, actual = homogeneous(target), homogeneous(actual)
    points = np.column_stack((np.asarray(markers, float), np.ones(len(markers))))
    landed = points@(actual@np.linalg.inv(target)).T
    return np.linalg.norm(landed[:, :2]-points[:, :2], axis=1)
