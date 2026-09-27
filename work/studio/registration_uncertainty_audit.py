"""Parameter-perturbation audit for saved micro-motion registration.

The variants are deliberately diagnostic and are never selected as a new
production matcher. A narrow spread between variants is only repeatability;
without an independent pose truth it is not an accuracy bound.
"""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
import cv2
import numpy as np
from PIL import Image
from atlas_runtime import texture_mask
from micro_registration_review import homogeneous, marker_error, synthetic_frame
from registration_precision_methods import board_masks, ecc_translation


def sift_variant(before, after, scene, ratio=.7, ransac=1.5):
    if not .5 <= ratio < 1 or not .25 <= ransac <= 5:
        raise ValueError('Invalid diagnostic SIFT parameters')
    l, t, r, b = map(int, scene.board)
    mask = texture_mask(scene, before.shape)
    detector = cv2.SIFT_create(nfeatures=2400)
    ka, da = detector.detectAndCompute(cv2.cvtColor(before[t:b, l:r], cv2.COLOR_RGB2GRAY), mask)
    kb, db = detector.detectAndCompute(cv2.cvtColor(after[t:b, l:r], cv2.COLOR_RGB2GRAY), mask)
    if da is None or db is None or len(db) < 2:
        raise RuntimeError('Missing SIFT descriptors')
    pairs = cv2.BFMatcher().knnMatch(da, db, k=2)
    good = [row[0] for row in pairs if len(row) == 2 and row[0].distance < ratio * row[1].distance]
    if len(good) < 20:
        raise RuntimeError('Too few SIFT matches')
    src = np.float32([ka[row.queryIdx].pt for row in good])
    dst = np.float32([kb[row.trainIdx].pt for row in good])
    matrix, inliers = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC,
                                                   ransacReprojThreshold=ransac)
    if matrix is None or inliers is None or int(inliers.sum()) < 20:
        raise RuntimeError('SIFT affine fit failed')
    return dict(method='sift_variant', ratio=ratio, ransac=ransac,
                matrix=np.asarray(matrix, float).tolist(), matches=len(good),
                inliers=int(inliers.sum()), inlier_fraction=float(inliers.mean()))


def ecc_variant(before, after, scene, sigma, erosion=0):
    mask = texture_mask(scene, before.shape)
    if erosion:
        mask = cv2.erode(mask, np.ones((2 * erosion + 1, 2 * erosion + 1), np.uint8))
    result = ecc_translation(before, after, scene, mask=mask, sigma=sigma)
    result.update(method='ecc_variant', sigma=sigma, erosion=erosion)
    return result


def variants(before, after, scene):
    specs = [
        ('sift_065_r1', lambda: sift_variant(before, after, scene, .65, 1.)),
        ('sift_070_r1', lambda: sift_variant(before, after, scene, .70, 1.)),
        ('sift_070_r15', lambda: sift_variant(before, after, scene, .70, 1.5)),
        ('sift_070_r2', lambda: sift_variant(before, after, scene, .70, 2.)),
        ('sift_075_r15', lambda: sift_variant(before, after, scene, .75, 1.5)),
        ('ecc_s05', lambda: ecc_variant(before, after, scene, .5)),
        ('ecc_s15', lambda: ecc_variant(before, after, scene, 1.5)),
        ('ecc_s2', lambda: ecc_variant(before, after, scene, 2.)),
        ('ecc_s4', lambda: ecc_variant(before, after, scene, 4.)),
        ('ecc_s2_erode2', lambda: ecc_variant(before, after, scene, 2., 2)),
    ]
    rows = []
    for name, callback in specs:
        try:
            value = callback()
            value['variant'] = name
        except (RuntimeError, ValueError, cv2.error) as exc:
            value = dict(variant=name, error=str(exc))
        rows.append(value)
    return rows


def displacement(matrix, points):
    return np.asarray(points, float) @ (np.asarray(matrix, float)[:, :2] - np.eye(2)).T + np.asarray(matrix, float)[:, 2]


def summarize_pair(forward, reverse, points):
    complete = [
        (f['variant'], f, reverse.get(f['variant']))
        for f in forward if 'matrix' in f and f['variant'] in reverse and 'matrix' in reverse[f['variant']]
    ]
    if not complete:
        return dict(variant_count=0, closure_ranges=None, forward_ranges=None)
    closures = {name: marker_error(homogeneous(r) @ homogeneous(f), np.eye(3), points)
                for name, f, r in complete}
    arrays = np.asarray([displacement(f['matrix'], points) for _, f, _ in complete])
    ranges = np.linalg.norm(arrays.max(axis=0) - arrays.min(axis=0), axis=1)
    values = [max(row) for row in closures.values()]
    groups = {}
    for label, prefix in (('sift', 'sift_'), ('ecc', 'ecc_')):
        selected = [(name, f, r) for name, f, r in complete if name.startswith(prefix)]
        if not selected:
            continue
        group_arrays = np.asarray([displacement(f['matrix'], points) for _, f, _ in selected])
        group_closures = [max(closures[name]) for name, _, _ in selected]
        translation = np.asarray([np.asarray(f['matrix'], float)[:, 2] for _, f, _ in selected])
        groups[label] = dict(variant_count=len(selected),
                             maximum_closure=float(max(group_closures)),
                             within_gate=sum(value <= .035 for value in group_closures),
                             translation_range=float(np.linalg.norm(translation.max(axis=0) - translation.min(axis=0))),
                             marker_range_max=float(np.max(np.linalg.norm(group_arrays.max(axis=0) - group_arrays.min(axis=0), axis=1))))
    return dict(variant_count=len(complete), closure_ranges=closures,
                maximum_closure=float(max(values)), within_gate=sum(v <= .035 for v in values),
                forward_marker_ranges=ranges.tolist(),
                forward_marker_range_max=float(max(ranges)), groups=groups)


def synthetic_summary(image, scene, points):
    rows = []
    for dx, dy in ((.02, 0), (.035, 0), (.125, 0), (.25, 0), (0, .125), (0, .25)):
        shifted, expected = synthetic_frame(image, scene, dx, dy)
        forward = variants(image, shifted, scene)
        errors = []
        for row in forward:
            if 'matrix' in row:
                errors.append(dict(variant=row['variant'], error=max(marker_error(homogeneous(row), expected, points))))
        rows.append(dict(requested=[dx, dy], variants=errors,
                         maximum_error=max((row['error'] for row in errors), default=None),
                         within_gate=sum(row['error'] <= .035 for row in errors),
                         variant_count=len(errors)))
    return rows


def main(source, output):
    source, output = Path(source), Path(output)
    output.mkdir(parents=True, exist_ok=False)
    log = json.loads((source/'log.json').read_text())
    scene = SimpleNamespace(**next(row for row in log if row['kind'] == 'sampling_ready'))
    points = np.asarray(scene.markers, float) - scene.board[:2]
    indices = (0, 1, 2, 4, 8, 16)
    images = {i: np.array(Image.open(source/f'probe_{i:03d}.png').convert('RGB')) for i in indices}
    pair_rows = []
    for index in indices[1:]:
        forward = variants(images[0], images[index], scene)
        reverse_rows = variants(images[index], images[0], scene)
        reverse = {row['variant']: row for row in reverse_rows}
        pair_rows.append(dict(frame=f'probe_{index:03d}', summary=summarize_pair(forward, reverse, points),
                              forward=forward, reverse=reverse_rows))
    report = dict(game_input_sent=False, live_accuracy_validated=False,
                  pose_tolerance=.035, pairs=pair_rows,
                  synthetic=synthetic_summary(images[0], scene, points),
                  candidate_not_promoted=True,
                  limitations=['Variant spread measures repeatability, not accuracy.',
                               'All variants use the same saved images and can share bias.',
                               'Synthetic warps are not game motion or an independent temporal capture.',
                               'No production matcher, quality threshold, or return tolerance changed.'])
    (output/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('output')
    args = parser.parse_args()
    main(args.source, args.output)
