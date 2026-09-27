"""Saved-image consistency and synthetic sensitivity audit, never live input.

Inverse-consistency and agreement do not establish true measurement accuracy.
Synthetic warps test this image-processing pipeline, not the game's renderer.
Identical saved frames do not measure temporal screenshot stability.
"""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
import cv2
import numpy as np
from PIL import Image
from atlas_runtime import motion, texture_mask
from vision import measure_board_motion


def homogeneous(record):
    matrix = np.asarray(record['matrix'], float)
    if matrix.shape != (2, 3) or not np.isfinite(matrix).all():
        raise ValueError('Finite affine matrix required')
    result = np.eye(3)
    result[:2] = matrix
    return result


def marker_error(estimated, expected, points):
    points = np.asarray(points, float)
    delta = np.column_stack((points, np.ones(len(points)))) @ (estimated - expected).T
    return np.linalg.norm(delta[:, :2], axis=1).tolist()


def synthetic_frame(image, scene, dx, dy):
    l, t, r, b = scene.board
    crop = image[t:b, l:r]
    matrix = np.float32([[1, 0, dx], [0, 1, dy]])
    shifted = cv2.warpAffine(crop, matrix, (r-l, b-t), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT_101)
    # Preserve masked UI. Composite boundaries can still affect SIFT support;
    # this is a sensitivity stress test, not a clean renderer calibration.
    mask = texture_mask(scene, image.shape) > 0
    result = image.copy()
    result[t:b, l:r][mask] = shifted[mask]
    expected = np.eye(3)
    expected[:2, 2] = [dx, dy]
    return result, expected


def main(source, output):
    source, output = Path(source), Path(output)
    output.mkdir(parents=True, exist_ok=False)
    log = json.loads((source/'log.json').read_text())
    scene = SimpleNamespace(**next(row for row in log if row['kind'] == 'sampling_ready'))
    points = np.asarray(scene.markers, float) - scene.board[:2]
    images = {i: np.array(Image.open(source/f'probe_{i:03d}.png').convert('RGB')) for i in (0, 1, 2, 4, 8, 16)}
    reference = images[0]
    real = []
    for index, frame in images.items():
        forward = motion(reference, frame, scene)
        reverse = motion(frame, reference, scene)
        unmasked = measure_board_motion(reference, frame, scene.board)
        row = dict(frame=f'probe_{index:03d}', forward=forward, reverse=reverse, unmasked=unmasked)
        if forward is not None and reverse is not None:
            row['forward_reverse_closure_pixels'] = marker_error(homogeneous(reverse) @ homogeneous(forward), np.eye(3), points)
        if forward is not None and unmasked is not None:
            row['mask_sensitivity_pixels'] = marker_error(homogeneous(forward), homogeneous(unmasked), points)
        real.append(row)
        print('saved', index, 'closure', row.get('forward_reverse_closure_pixels'),
              'mask sensitivity', row.get('mask_sensitivity_pixels'), flush=True)
    synthetic = []
    for index in (0, 8):
        for dx, dy in ((.02, 0), (.035, 0), (.125, 0), (.25, 0), (0, .125), (0, .25)):
            shifted, expected = synthetic_frame(images[index], scene, dx, dy)
            measured = motion(images[index], shifted, scene)
            row = dict(frame=f'probe_{index:03d}', requested_translation=[dx, dy],
                       interpolation='OpenCV cubic, 8-bit RGB, fixed UI restored', measured=measured)
            if measured is not None:
                row['known_warp_marker_error_pixels'] = marker_error(homogeneous(measured), expected, points)
            synthetic.append(row)
            print('synthetic', index, dx, dy, row.get('known_warp_marker_error_pixels'), flush=True)
    report = dict(game_input_sent=False, pose_tolerance=.035, live_accuracy_validated=False,
                  same_pose_temporal_captures_available=False, saved_pairs=real, synthetic=synthetic,
                  limitations=['Saved self-match is not an independent same-pose observation.',
                               'Forward/reverse closure and mask sensitivity are consistency checks, not error bounds.',
                               'Known synthetic warps include interpolation/quantization and are not game motion.',
                               'Fixed-UI compositing boundaries may influence feature estimates.',
                               'No tolerance changed, no registration implementation promoted.'])
    (output/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('output')
    args = parser.parse_args()
    main(args.source, args.output)
