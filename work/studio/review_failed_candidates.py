"""Read saved sessions and compare bounded search variants; never sends input."""
import argparse
import json
import time
from pathlib import Path
from unittest.mock import patch
import numpy as np
from periodic_atlas import PeriodicAtlas
from atlas_similarity import similarity_candidates, captured_scale_levels, _sample_transforms
from atlas_execution import reposition_budget


class PermutedAtlas:
    def __init__(self, atlas, order):
        self.atlas, self.order = atlas, order
        self.basis, self.origin, self.resolution = atlas.basis, atlas.origin, atlas.resolution

    def maps(self, region):
        return self.atlas.maps(region=self.order[region])

    def sample(self, region, points):
        return self.atlas.sample(self.order[region], points)


def load_snapshot(path):
    with np.load(path, allow_pickle=False) as saved:
        colors = saved['colors'].astype(float)
        count = saved['count'] * saved['valid']
        atlas = PeriodicAtlas(saved['basis'], saved['origin'], colors.shape[1])
        atlas.count = count
        atlas.total = colors * count[..., None]
        atlas.squared = (colors**2 + saved['rmse'][..., None]**2) * count[..., None]
    return atlas.snapshot()


def inspect_session(session):
    session = Path(session)
    capture = session/'atlas_capture'
    def read(path):
        return json.loads(path.read_text(encoding='utf-8'))
    log = read(capture/'log.json')
    report = read(capture/'analysis/report.json')
    review = read(capture/'analysis/expanded/review.json')
    summary = read(session/'run-summary.json')
    rows = review['candidates']
    ready = next(r for r in log if r['kind'] == 'ready')['elapsed_seconds']
    end = next(r for r in log if r['kind'] == 'CAPTURE_COMPLETE')['elapsed_seconds']
    timer = next(r for r in log if r['kind'] == 'timer')
    # Wall time and capture monotonic elapsed time have slightly different
    # origins. This is an approximate remaining-time audit, not a new deadline.
    elapsed = summary['events'][-1]['time'] - summary['events'][1]['time']
    remaining = timer['deadline_elapsed_seconds'] - elapsed
    result = dict(session=str(session.resolve()), game_input_sent=False,
                  rules=review['rules'], quality_gate=review['quality_gate'],
                  capture_seconds=end-ready, analysis_seconds=report['timings']['total_seconds'],
                  approximate_remaining_seconds=remaining,
                  last_event=summary['events'][-1], raw_count=len(rows),
                  accepted_count=sum(bool(r['accepted']) for r in rows),
                  best_prediction=rows[0] if rows else None,
                  best_budget=(reposition_budget(rows[0], 0, remaining, report['scene']['board']) if rows else None),
                  execution_files=list(map(str, (capture/'execution').glob('*'))), variants=[])
    atlas = load_snapshot(capture/'analysis/atlas.npz')
    markers = np.array(report['scene']['markers']) - report['scene']['board'][:2]
    l,t,r,b = report['scene']['board']
    levels, _ = captured_scale_levels(log)
    # Reordering the first two material indices switches the seed pair from
    # black+orange to black+white. Maps, markers and rules must move together.
    for order in ((0,1,2), (1,0,2)):
        for seed_limit, discrete in ((128,True), (512,True), (128,False)):
            source = PermutedAtlas(atlas, order)
            rules = [review['rules'][i] for i in order]
            best = None
            def sampled(atlas, markers, rules, multipliers, offsets, jitter=(0,0)):
                nonlocal best
                values = _sample_transforms(atlas, markers, rules, multipliers, offsets, jitter)
                if jitter == (0,0):
                    support = np.ones(len(multipliers), bool)
                    for region in range(3):
                        points = (complex(*markers[region])-offsets)/multipliers
                        _, valid = atlas.sample(region, np.c_[points.real, points.imag])
                        support &= valid
                    ids = np.flatnonzero(support)
                    if len(ids):
                        i = ids[np.argmin(values[1][ids])]
                        if best is None or values[1][i] < best['maximum']:
                            deltas = [None]*3
                            for region in range(3):deltas[order[region]] = float(values[4][region][i])
                            best = dict(maximum=float(values[1][i]), deltas=deltas)
                return values
            diag = {}
            start = time.perf_counter()
            with patch('atlas_similarity._sample_transforms', side_effect=sampled):
                candidates = similarity_candidates(source, markers[list(order)], rules,
                    report['offsets'][-1], (b-t,r-l), scale_bounds=(min(levels),1),
                    scale_levels=levels if discrete else None, seed_limit=seed_limit, diagnostics=diag)
            variant = dict(order=order, seed_limit=seed_limit, discrete=discrete,
                           seconds=time.perf_counter()-start, diagnostics=diag,
                           accepted_count=len(candidates), best_sampled_prediction=best,
                           candidates=candidates)
            result['variants'].append(variant)
            print(session.name, order, seed_limit, discrete, 'accepted', len(candidates),
                  'tested', diag['evaluated_transforms'], 'best', best, flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('sessions', nargs='+', type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for session in args.sessions:
        report = inspect_session(session)
        (args.output/(session.name+'.json')).write_text(json.dumps(report, indent=2), encoding='utf-8')
