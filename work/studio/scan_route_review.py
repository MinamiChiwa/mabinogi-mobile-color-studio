"""Replay reordered saved endpoints; never execute or synthesize a game route.

Commands constrain registration aliases but do not supply measured offsets.
All original color holdouts remain held out; their texture can contribute to
geometry. Missing intermediate screenshots and actual route timings remain
unvalidated, even when endpoint registration succeeds.
"""
import argparse
import json
from pathlib import Path
import time
import numpy as np
from atlas_budget_review import load_capture, subset_indices, replay_variant
from analyze_live_atlas import measured_translation, measure_periods
from replay_archive import refine, translation_error


def commanded_positions(log):
    commands = [[r['dx'], r['dy']] for r in log if r.get('kind') == 'command']
    return np.vstack(([0., 0.], np.cumsum(commands, axis=0)))


def vertical_route(retained, columns=8):
    """Visit saved grid lanes vertically; row staggering stays in actual poses."""
    if not retained or 0 not in retained or len(set(retained)) != len(retained):
        raise ValueError('Unique retained indices including reference zero required')
    lanes = [[] for _ in range(columns)]
    for index in retained:
        row, step = divmod(index, columns)
        lane = step if row % 2 == 0 else columns - 1 - step
        lanes[lane].append(index)
    route = []
    for lane, indices in enumerate(lanes):
        route.extend(sorted(indices, key=lambda i: i // columns, reverse=bool(lane % 2)))
    if route[0] != 0:
        raise ValueError('Route must begin at captured reference')
    return route


def route_actions(route, positions, shape):
    """Count required drag segments using existing Game.drag 65% clamp.

    Splitting only defines requested input. No intermediate position is
    measured by this calculation. Do not round the clamp upward.
    """
    h, w = shape[:2]
    limit = np.floor(np.asarray([w, h]) * .65).astype(int)
    if np.min(limit) < 1:
        raise ValueError('Board too small')
    rows = []
    for previous, index in zip(route, route[1:]):
        delta = np.asarray(positions[index]) - positions[previous]
        count = max(1, int(np.ceil(np.max(np.abs(delta) / limit))))
        points = np.rint(np.linspace([0., 0.], delta, count + 1)).astype(int)
        steps = np.diff(points, axis=0)
        rows.append(dict(previous=previous, index=index, command_hint=delta.tolist(),
                         drag_count=count, drag_requests=steps.tolist(),
                         unobserved_intermediate_poses=count - 1))
    return rows


def measure_route(data, route, holdout):
    images, masks = data['images'], data['masks']
    cache = {}
    offsets = {0: np.zeros(2)}
    motions = []
    positions = commanded_positions(data['log'])
    for previous, index in zip(route, route[1:]):
        a, b = images[previous], images[index]
        command = positions[index] - positions[previous]
        try:
            measured = measured_translation(a, b, cache)
            if np.linalg.norm(measured - command) > 12:
                raise ValueError('Measured motion disagrees with command hint; no unmeasured alias accepted')
            dx, dy = measured
            dx, _ = refine(lambda v: translation_error(a, b, masks, v, dy), dx, .6, .04)
            dy, error = refine(lambda v: translation_error(a, b, masks, dx, v), dy, .3, .025)
            if not np.isfinite(error) or error > 8:
                raise ValueError('Same-material photometric overlap failed existing RMSE 8 gate')
            absolute = offsets[previous] + [dx, dy]
            if index % 8 == 0 or index in holdout:
                ax, _ = refine(lambda v: translation_error(images[0], b, masks, v, absolute[1]), absolute[0], 2.5, .25)
                ay, ae = refine(lambda v: translation_error(images[0], b, masks, ax, v), absolute[1], 1.5, .15)
                if np.isfinite(ae) and ae <= 8:
                    absolute = np.array([ax, ay])
            offsets[index] = absolute
            motions.append(dict(previous=previous, index=index, measured=[dx, dy], rgb_rmse=error))
        except ValueError as exc:
            return dict(geometry_passed=False, failure_pair=[previous, index], error=str(exc), motions=motions)
    try:
        periods = measure_periods([images[i] for i in route], [offsets[i] for i in route], masks, cache)
    except ValueError as exc:
        return dict(geometry_passed=False, error=str(exc), motions=motions)
    return dict(geometry_passed=True, offsets={str(k): v.tolist() for k, v in offsets.items()},
                periods=periods, motions=motions)


def review(data, variant, codes):
    started = time.perf_counter()
    training, holdout, retained = subset_indices(data['log'], variant)
    route = vertical_route(retained)
    actions = route_actions(route, commanded_positions(data['log']), data['images'][0].shape)
    measured = measure_route(data, route, holdout)
    registration_seconds = time.perf_counter() - started
    result = dict(variant=variant, route=route, training_count=len(training), captured_count=len(retained),
                  holdout_indices=holdout, actions=actions, drag_count=sum(a['drag_count'] for a in actions),
                  unobserved_intermediate_poses=sum(a['unobserved_intermediate_poses'] for a in actions),
                  validation_geometry_uses_heldout_texture=True, game_input_sent=False, live_validated=False,
                  registration_seconds=registration_seconds, **measured)
    if measured['geometry_passed']:
        quality = replay_variant(data, variant, codes, known_geometry=measured)
        quality['geometry_source'] = 'Independently remeasured reordered retained endpoints, including holdout texture; no discarded frames'
        result['quality'] = quality
    result['offline_seconds'] = time.perf_counter() - started
    return result


def main(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    sessions = [('new', 'outputs/atlas-capture-20260926-113839-673', 'outputs/review-20260926-113839/all-codes.json'),
                ('old', 'atlas_capture_2026-09-24_2141', 'outputs/transfer-validation-20260926/old-verified-codes.json')]
    rows = []
    for label, source, codes_path in sessions:
        data = load_capture(source)
        codes = json.loads(Path(codes_path).read_text())
        codes = codes.get('codes', codes)
        for variant in ('full', 'rows_024', 'rows_0234', 'columns_02467'):
            row = dict(session=label, **review(data, variant, codes))
            rows.append(row)
            (output/'report.json').write_text(json.dumps(dict(game_input_sent=False, rows=rows,
                limitations=['Saved endpoint order is not an executed trajectory.',
                             'Intermediate drag poses are unobserved; live timing is not estimated.',
                             'Geometry includes heldout texture; heldout colors never enter training.']), indent=2), encoding='utf-8')
            print(label, variant, 'frames', row['captured_count'], 'drags', row['drag_count'],
                  'geometry', row['geometry_passed'], 'quality', row.get('quality', {}).get('quality_gate'),
                  'failure', row.get('failure_pair'), row.get('error'), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output')
    main(parser.parse_args().output)
