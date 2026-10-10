"""Offline shared-pose predictions using captured native dye pixels.

Native pose coordinates are normalized bottom-up screen UV, NOT atlas
board-local pixel matrices. No result certifies input reachability or game HEX.
"""
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image
from native_palette_model import picker_view_uv, distort_cpu_uv, sample_cpu, color32
from hex_refinement import score_codes
from dye_regions import region_count, session_region_count, validate_region_rules


def _pose(value):
    position = np.asarray(value['position'], dtype=np.float32)
    scale = float(value['scale'])
    rotation = float(value['rotation_degrees'])
    if position.shape != (2,) or not np.isfinite(position).all() or not np.isfinite([scale, rotation]).all() or scale <= 0:
        raise ValueError('Invalid normalized native pose')
    return dict(position=position.tolist(), scale=scale, rotation_degrees=rotation)


def load_session(folder):
    """Load and validate an actual-layout saved session; never query a process."""
    folder = Path(folder).resolve()
    data = json.loads((folder / 'snapshot.json').read_text(encoding='utf-8'))
    count = region_count(len(data['fragments']))
    if not data['state_stable_during_read']:
        raise ValueError('A stable dye capture is required')
    for key in ('region_count', 'actual_count'):
        if key in data and region_count(data[key]) != count:
            raise ValueError('Actual dye count differs from captured fragments')
    if 'picker_colors_rgba' in data and len(data['picker_colors_rgba']) != count:
        raise ValueError('Captured client color count differs from fragments')
    p = float(data['color_preserve_ratio'])
    if not np.isfinite(p) or not 0 <= p < 1:
        raise ValueError('Unsupported color preservation ratio')
    pixels, points = [], []
    for index, fragment in enumerate(data['fragments']):
        if fragment.get('index', index) != index:
            raise ValueError('Captured fragment order differs from picker order')
        source = (folder / fragment['pixel_file']).resolve()
        if not source.is_relative_to(folder):
            raise ValueError('Pixel file must remain in the capture directory')
        if (fragment['width'], fragment['height'], fragment['channels']) != (254, 254, 3):
            raise ValueError('Unexpected fragment dimensions')
        with Image.open(source) as image:
            array = np.asarray(image.convert('RGB')).copy()
        if array.shape != (254, 254, 3) or hashlib.sha256(array[::-1].tobytes()).hexdigest() != fragment['raw_sha256']:
            raise ValueError('Fragment fingerprint mismatch')
        y = float(fragment['normalized_picker_y'])
        if not np.isfinite(y) or not 0 <= y <= 1:
            raise ValueError('Invalid picker position')
        array.setflags(write=False)
        pixels.append(array)
        points.append([(index + .5) / count, y])
    return dict(pixels=tuple(pixels), picker_uv=points, color_preserve_ratio=p, region_count=count,
                initial_pose=_pose(data), source='captured_native_pixels',
                capture_id=data.get('captured_at_utc', folder.name))


def score_native_pose(session, pose, rules, *, check=lambda: None):
    """Predict and rank the enabled cards using existing exact/Delta-E rules."""
    pose = _pose(pose)
    count = validate_region_rules(session, rules)
    check()
    coordinates = np.array([distort_cpu_uv(picker_view_uv(i, count, uv[1], pose['position'], pose['scale'], pose['rotation_degrees']))
                            for i, uv in enumerate(session['picker_uv'])])
    if not np.isfinite(coordinates).all():
        raise ValueError('Nonfinite transformed UV')
    colors, floats = [None] * count, [None] * count
    for index, rule in enumerate(rules):
        check()
        if not rule['enabled']:
            continue
        rgb = sample_cpu(session['pixels'][index], coordinates[index], session['color_preserve_ratio']) / np.float32(255)
        floats[index] = rgb.tolist()
        colors[index] = '#%02X%02X%02X' % tuple(int(v) for v in color32(rgb))
    result = score_codes(colors, rules)
    result['predicted_accepted'] = result.pop('accepted')
    result.update(predicted=True, verified=False, execution_verified=False,
                  predicted_pick_rgb=floats, native_pose=pose,
                  coordinate_space='native_normalized_bottom_up_uv',
                  capture_id=session['capture_id'], input_reachability='unverified')
    return result


def rank_native_poses(session, poses, rules, *, max_candidates=10000, check=lambda: None):
    """Score only an explicit bounded candidate set; no reachability claim."""
    if not isinstance(max_candidates, int) or max_candidates < 1:
        raise ValueError('Positive candidate limit required')
    results = []
    for index, pose in enumerate(poses):
        check()
        if index >= max_candidates:
            raise ValueError('Candidate limit exceeded')
        row = score_native_pose(session, pose, rules, check=check)
        row['candidate_index'] = index
        results.append(row)
    return sorted(results, key=lambda row: row['rank'])
