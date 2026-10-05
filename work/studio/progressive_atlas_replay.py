"""Offline, held-out comparison of full and staged atlas search.

This module reads a saved atlas capture and never sends game input. It compares
the current complete 48-frame reconstruction with an anchor-first 42-frame
reconstruction, then evaluates both candidate generators against the same
saved game HEX samples where available. It is an offline study, not evidence
that a live 42-step route is safe or that predicted colors match the game.
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np

from analyze_live_atlas import (CaptureAlignment, frame_sequence, material_masks,
                                measure_periods, quality_gate, scene_record,
                                validation_summary, evaluate)
from atlas_budget_review import load_capture, subset_indices, measure_subset
from candidate_ranking import candidate_rank
from periodic_atlas import PeriodicAtlas, progressive_translation_candidates, translation_candidates
from replay_archive import refine, translation_error


def anchor_first_indices(log, anchor_columns=(0, 4), anchor_rows=(0, 2, 4),
                         max_step=1):
    """Return selected captures for two distributed anchor columns.

    All established holdouts remain validation-only. The original frame is
    always retained. This schedule is a replay hypothesis, not a live route.
    """
    sequence = frame_sequence(log)
    if sequence['strategy'] != 'grid':
        raise ValueError('Progressive replay requires a grid capture')
    commands = [row for row in log if row.get('kind') == 'command']
    holdouts = set(sequence['holdout_indices'])
    selected = {0}
    previous = 0
    for index, action in enumerate(commands, 1):
        if action.get('column') in anchor_columns and action.get('row') in anchor_rows:
            # Keep every intermediate frame between anchors. A progressive
            # route may omit colour-map frames, but registration still needs
            # a bounded adjacent step; sparse jumps are not executable.
            selected.update(range(previous + 1, index + 1))
            previous = index
    # The last anchor may be followed by a long return segment. Keep that
    # adjacent tail as well so the staged replay has a valid current pose.
    selected.update(range(previous + 1, len(commands) + 1))
    return sorted(selected - holdouts), sorted(holdouts), sorted(selected | holdouts)


def _build_atlas(data, indices, offsets, periods, resolution=768):
    atlas = PeriodicAtlas([[periods[0][0], 0], [0, periods[1][0]]],
                          resolution=resolution)
    for index in indices:
        atlas.add_resampled(data['images'][index], data['masks'], offsets[index])
    return atlas.snapshot()


def _rules_from_saved_review(capture, review_path=None):
    if review_path is None:
        review_path = Path(capture) / 'analysis' / 'expanded' / 'review.json'
    review = json.loads(Path(review_path).read_text(encoding='utf-8'))
    rules = review.get('rules') or []
    if len(rules) != 3:
        raise ValueError('Saved review must contain three target rules')
    return rules, review


def _saved_game_codes(capture):
    """Load optional manually transcribed codes from known review artifacts."""
    choices = [Path(capture) / 'analysis' / 'all-codes.json',
               Path(capture).parent / 'all-codes.json']
    for path in choices:
        if path.is_file():
            data = json.loads(path.read_text(encoding='utf-8'))
            return data.get('codes', data)
    return {}


def _candidate_metrics(rows, rules):
    if not rows:
        return dict(count=0, strict_accepted_count=0, best=None)
    accepted = [row for row in rows if row.get('accepted')]
    return dict(count=len(rows), strict_accepted_count=len(accepted),
                best=min(rows, key=candidate_rank))


def replay(capture, output, *, review_path=None, resolution=768):
    capture = Path(capture)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    data = load_capture(capture)
    rules, saved_review = _rules_from_saved_review(capture, review_path)
    codes = _saved_game_codes(capture)
    full_indices, holdout, _ = subset_indices(data['log'], 'full')
    staged_indices, staged_holdout, staged_retained = anchor_first_indices(data['log'])
    if holdout != staged_holdout:
        raise AssertionError('Anchor schedule changed the established holdout set')

    # Measure geometry once from the complete saved trajectory. The staged
    # replay removes frames only from color-map training; it does not pretend
    # that a live route can jump between distant anchors without registration.
    full_offsets, full_periods, full_motions = measure_subset(
        data, list(range(len(data['names']))), holdout)
    results = {}
    for label, train, retained in (
            ('full48', full_indices, list(range(len(data['names'])))),
            ('anchor_progressive', staged_indices, staged_retained)):
        started = time.perf_counter()
        offsets, periods, motions = full_offsets, full_periods, full_motions
        atlas = _build_atlas(data, train, offsets, periods, resolution)
        coverage = atlas.report()
        validation = [dict(frame=data['names'][index],
                           prediction=evaluate(atlas, data['images'][index],
                                               data['masks'], offsets[index]))
                      for index in holdout]
        summary = validation_summary(validation)
        gate = quality_gate(coverage, summary)
        markers = []
        for index in holdout:
            frame_codes = codes.get(data['names'][index], [None, None, None])
            for region in range(3):
                sampled, valid = atlas.sample(region, [data['markers'][region]], offsets[index])
                predicted = ('#%02X%02X%02X' % tuple(np.rint(sampled[0]).clip(0, 255).astype(int))
                             if valid[0] else None)
                actual = frame_codes[region] if region < len(frame_codes) else None
                markers.append(dict(frame=data['names'][index], region=region + 1,
                                    predicted=predicted, game_hex=actual))
        if not gate.get('passed'):
            progressive_rows = []
            complete_rows = []
            diagnostics = dict(fallback=True, reason='quality_gate_failed')
        else:
            current = offsets[max(offsets)]
            progressive_diag = {}
            progressive_rows = progressive_translation_candidates(
                atlas, data['markers'], rules, current,
                anchor_regions=(0, 1), anchor_limit=8, refine_radius=3,
                limit=24, landing_radius=1., diagnostics=progressive_diag)
            complete_rows = translation_candidates(
                atlas, data['markers'], rules, current,
                limit=24, landing_radius=1., integer_moves=True)
            diagnostics = dict(fallback=bool(progressive_diag.get('fallback')),
                               stages=progressive_diag)
        results[label] = dict(
            live_validated=False, training_count=len(train), retained_count=len(retained),
            training_frames=[data['names'][i] for i in train],
            retained_frames=[data['names'][i] for i in retained],
            holdout_frames=[data['names'][i] for i in holdout],
            periods=periods, motions=motions, coverage=coverage,
            validation=validation, quality_gate=gate, marker_samples=markers,
            elapsed_seconds=time.perf_counter() - started,
            complete_search=_candidate_metrics(complete_rows, rules),
            progressive_search=_candidate_metrics(progressive_rows, rules),
            progressive_diagnostics=diagnostics)

    report = dict(schema=1, offline_only=True, verified=False,
                  source=str(capture.resolve()),
                  saved_review_mode=saved_review.get('mode'),
                  strict_all_region_game_hex_hit_claimed=False,
                  decision=('Anchor route is only a replay hypothesis. Keep the live 48-step '
                            'baseline until a separate live run verifies acquisition geometry, '
                            'timing, return, and repeated game HEX behavior.'),
                  comparisons=results)
    (output / 'progressive-replay.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--review', type=Path)
    parser.add_argument('--resolution', type=int, default=768)
    args = parser.parse_args()
    report = replay(args.capture, args.output, review_path=args.review,
                    resolution=args.resolution)
    print(json.dumps({key: {name: value['quality_gate']
                            for name, value in report['comparisons'].items()}
                      for key in ('comparisons',)}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
