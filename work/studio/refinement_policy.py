"""Polishing preserves acceptance and each unsatisfied region's preference.

Global search is intentionally outside this policy: it may still choose a
priority-ordered compromise. Satisfied Similar regions may move inside their
configured tolerance; Exact matches cannot be lost. No lower raw Delta E can
authorize a hue-preference regression during additional local polishing.
"""
import math

from region_priority import priority_indices
from vision import error, normalize_hex
from color_matching import matching_score


class RefinementPolicy:
    def __init__(self, rules, baseline):
        self.rules = rules
        self.order = priority_indices(rules)
        if self.order is None:
            self.order = [i for i, rule in enumerate(rules) if rule['enabled']]
        self.targets = [[normalize_hex(c) for c in rule['colors']] for rule in rules]
        self.baseline = self._state(baseline)

    def _state(self, colors, deltas=None):
        count = len(self.rules)
        result = dict(colors=list(colors), deltas=[None]*count, scores=[None]*count,
                      hits=[False]*count, verified=False)
        if not self.order or len(colors) != count or deltas is not None and len(deltas) != count:
            return result
        try:
            for i in self.order:
                if not isinstance(colors[i],str):return result
                code = normalize_hex(colors[i])
                delta = float(error(code, self.targets[i], False) if deltas is None else deltas[i])
                if not math.isfinite(delta) or delta < 0:
                    return result
                result['colors'][i] = code
                result['deltas'][i] = delta
                result['scores'][i] = matching_score(code, self.rules[i])
                result['hits'][i] = (code in self.targets[i] if self.rules[i]['exact']
                    else delta <= float(self.rules[i]['tolerance']))
        except (TypeError, ValueError):
            return result
        result['verified'] = True
        return result

    def assess(self, colors, *, deltas=None):
        state = self._state(colors, deltas)
        verified = self.baseline['verified'] and state['verified']
        # Numerical comparison tolerance only, not a perceptual color bin.
        epsilon = 1e-9
        regressions = ([i for i in self.order if
            (self.baseline['hits'][i] and not state['hits'][i]) or
            (not state['hits'][i] and not self.baseline['hits'][i] and
             state['scores'][i] > self.baseline['scores'][i]+epsilon)] if verified else list(self.order))
        not_worse = bool(verified and not regressions)
        def ordered(value):
            parts=[]
            for i in self.order:
                parts.extend((int(not value['hits'][i]),
                    (0. if value['hits'][i] else value['scores'][i]) if value['verified'] else math.inf))
            scores=[value['scores'][i] for i in self.order] if value['verified'] else [math.inf]
            return (int(not all(value['hits'][i] for i in self.order)), *parts,
                    max(scores),sum(scores)/len(scores))
        rank=ordered(state)
        # A total order prevents cycling between tolerance-compliant colors.
        improved=bool(not_worse and rank<ordered(self.baseline))
        return dict(verified=bool(verified), not_worse=not_worse, improved=improved,
            lost_matches=([i for i in self.order if self.baseline['hits'][i] and not state['hits'][i]]
                if verified else list(self.order)),
            regressed_regions=regressions, baseline_colors=list(self.baseline['colors']),
            baseline_deltas=list(self.baseline['deltas']), actual_deltas=state['deltas'],
            baseline_scores=list(self.baseline['scores']), actual_scores=state['scores'],
            baseline_hits=list(self.baseline['hits']), actual_hits=state['hits'], rank=rank)


def compare_refinement(colors, baseline, rules):
    return RefinementPolicy(rules, baseline).assess(colors)


def recovery_rank(colors, baseline, rules):
    """Prefer the least regression while returning, without replacing the floor."""
    policy=RefinementPolicy(rules,baseline);decision=policy.assess(colors)
    if not decision['verified']:return (math.inf,)
    losses=[(0. if decision['actual_hits'][i] else
             max(0.,decision['actual_scores'][i]-decision['baseline_scores'][i])) for i in policy.order]
    lost=[int(i in decision['lost_matches']) for i in policy.order]
    return (*lost,max(losses,default=0.),*losses,*decision['rank'])
