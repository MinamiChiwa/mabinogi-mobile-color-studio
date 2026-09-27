"""Offline comparison of translation estimators on saved board screenshots.

This module is a diagnostic only. It does not change the production matcher,
send input, or turn consistency into an accuracy guarantee. ECC is translation
only; it cannot explain the scale drift observed in the saved trajectory.
"""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
import cv2
import numpy as np
from PIL import Image
from atlas_runtime import motion as sift_motion, texture_mask
from atlas_masks import material_masks
from micro_registration_review import homogeneous, marker_error, synthetic_frame


def board_masks(scene):
    """Return three conservative same-material masks in board coordinates."""
    return material_masks(scene).astype(np.uint8) * 255


def _board_gray(image, scene, sigma):
    l, t, r, b = map(int, scene.board)
    crop = image[t:b, l:r]
    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.
    if sigma > 0:
        gray = cv2.GaussianBlur(gray, (0, 0), sigma)
    return gray


def ecc_translation(before, after, scene, mask=None, sigma=1.5, iterations=300):
    """Estimate a translation with masked ECC; return board-crop coordinates."""
    if mask is None:
        # Use the same board-local exclusion mask as the runtime adapter;
        # including card stems/marker rings can dominate subpixel ECC.
        mask = texture_mask(scene, before.shape)
    mask = np.asarray(mask, np.uint8)
    if mask.ndim != 2 or mask.shape != _board_gray(before, scene, 0).shape or not np.any(mask):
        raise ValueError('Nonempty board-sized ECC mask required')
    template = _board_gray(before, scene, sigma)
    image = _board_gray(after, scene, sigma)
    warp = np.eye(2, 3, dtype=np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, int(iterations), 1e-7)
    try:
        score, matrix = cv2.findTransformECC(template, image, warp,
                                              cv2.MOTION_TRANSLATION, criteria,
                                              inputMask=mask, gaussFiltSize=1)
    except cv2.error as exc:
        raise RuntimeError('ECC translation failed') from exc
    matrix = np.asarray(matrix, float)
    return dict(matrix=matrix.tolist(), translation=matrix[:, 2].tolist(),
                score=float(score), sigma=float(sigma), method='ecc_translation')


def regional_ecc(before, after, scene, sigma=1.5, iterations=300):
    masks = board_masks(scene)
    rows = []
    for index, mask in enumerate(masks, 1):
        try:
            row = ecc_translation(before, after, scene, mask, sigma, iterations)
            row['region'] = index
        except RuntimeError as exc:
            row = dict(region=index, method='ecc_translation', error=str(exc))
        rows.append(row)
    good = [row for row in rows if 'matrix' in row]
    if not good:
        return dict(method='regional_ecc', regions=rows, error='No material region produced ECC')
    translations = np.asarray([row['translation'] for row in good], float)
    median = np.median(translations, axis=0)
    spread = np.linalg.norm(translations - median, axis=1)
    matrix = np.eye(2, 3)
    matrix[:, 2] = median
    return dict(method='regional_ecc', regions=rows, matrix=matrix.tolist(),
                translation=median.tolist(), score=float(np.mean([row['score'] for row in good])),
                region_translation_spread=spread.tolist(), region_count=len(good))


def method_result(before, after, scene, method, sigma=1.5):
    if method == 'sift_affine':
        result = sift_motion(before, after, scene)
        return None if result is None else dict(result, method=method)
    if method == 'ecc_full':
        return ecc_translation(before, after, scene, sigma=sigma)
    if method == 'regional_ecc':
        return regional_ecc(before, after, scene, sigma=sigma)
    raise ValueError('Unknown registration method')


def closure(forward, reverse, points):
    if not forward or not reverse or 'matrix' not in forward or 'matrix' not in reverse:
        return None
    composed = homogeneous(reverse) @ homogeneous(forward)
    return marker_error(composed, np.eye(3), points)


def compare_pair(before, after, scene, points, sigma=1.5):
    rows = []
    for method in ('sift_affine', 'ecc_full', 'regional_ecc'):
        try:
            forward = method_result(before, after, scene, method, sigma)
            reverse = method_result(after, before, scene, method, sigma)
            row = dict(method=method, forward=forward, reverse=reverse,
                       closure_pixels=closure(forward, reverse, points))
            if method == 'regional_ecc' and forward and 'region_translation_spread' in forward:
                row['forward_region_spread'] = forward['region_translation_spread']
            if method == 'regional_ecc' and reverse and 'region_translation_spread' in reverse:
                row['reverse_region_spread'] = reverse['region_translation_spread']
        except (RuntimeError, ValueError) as exc:
            row = dict(method=method, error=str(exc), closure_pixels=None)
        rows.append(row)
    return rows


def synthetic_rows(image, scene, points, sigma):
    rows = []
    for dx, dy in ((.02, 0), (.035, 0), (.125, 0), (.25, 0), (0, .125), (0, .25)):
        shifted, expected = synthetic_frame(image, scene, dx, dy)
        item = dict(requested_translation=[dx, dy], expected=expected.tolist())
        for method in ('sift_affine', 'ecc_full', 'regional_ecc'):
            try:
                measured = method_result(image, shifted, scene, method, sigma)
                item[method] = dict(measured=measured,
                                    known_warp_marker_error=None if not measured else marker_error(
                                        homogeneous(measured), expected, points))
            except (RuntimeError, ValueError) as exc:
                item[method] = dict(error=str(exc), known_warp_marker_error=None)
        rows.append(item)
    return rows


def main(source, output):
    source, output = Path(source), Path(output)
    output.mkdir(parents=True, exist_ok=False)
    log = json.loads((source/'log.json').read_text())
    scene = SimpleNamespace(**next(row for row in log if row['kind'] == 'sampling_ready'))
    points = np.asarray(scene.markers, float) - scene.board[:2]
    indices = (0, 1, 2, 4, 8, 16)
    images = {i: np.array(Image.open(source/f'probe_{i:03d}.png').convert('RGB')) for i in indices}
    pairs = []
    for index in indices:
        pairs.append(dict(frame=f'probe_{index:03d}', methods=compare_pair(images[0], images[index], scene, points)))
    synthetic = synthetic_rows(images[0], scene, points, sigma=1.5)
    sweep = []
    for sigma in (.5, .75, 1., 1.5, 2., 3., 4.):
        real_closures = []
        real_translations = []
        for index in indices[1:]:
            try:
                forward = method_result(images[0], images[index], scene, 'ecc_full', sigma)
                reverse = method_result(images[index], images[0], scene, 'ecc_full', sigma)
                values = closure(forward, reverse, points)
                real_closures.append(dict(frame=f'probe_{index:03d}', maximum=max(values), values=values))
                real_translations.append(dict(frame=f'probe_{index:03d}', translation=forward['translation']))
            except (RuntimeError, ValueError) as exc:
                real_closures.append(dict(frame=f'probe_{index:03d}', error=str(exc)))
        synthetic_sigma = synthetic_rows(images[0], scene, points, sigma)
        errors = [max(row['ecc_full']['known_warp_marker_error'])
                  for row in synthetic_sigma
                  if row['ecc_full'].get('known_warp_marker_error')]
        sweep.append(dict(sigma=sigma, real_closures=real_closures,
                          real_translations=real_translations,
                          synthetic_max_error=max(errors) if errors else None,
                          synthetic_over_tolerance=sum(v > .035 for v in errors),
                          synthetic_count=len(errors)))
    report = dict(game_input_sent=False, live_accuracy_validated=False,
                  pose_tolerance=.035, sigma=1.5, pairs=pairs, synthetic=synthetic,
                  ecc_sigma_sweep=sweep, candidate_not_promoted=True,
                  limitations=['ECC estimates translation only and cannot remove scale drift.',
                               'Synthetic images use the existing OpenCV compositing stress test, not game motion.',
                               'Closed-loop agreement is a consistency measure, not a true error bound.',
                               'Changing blur scale changes the result; no single scale is selected as a production truth.',
                               'No production matcher or threshold changed.'])
    (output/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('output')
    args = parser.parse_args()
    main(args.source, args.output)
