"""Keep route correction aimed at a chosen joint destination.

Global search still owns the user's priority order. Recovering a selected
destination must not run that global election again and chase one exact chip.
"""
import math

from refinement_policy import RefinementPolicy
from vision import error


class DestinationPolicy:
    def __init__(self, rules, target, baseline, *, preserve_baseline=True):
        self.floor = RefinementPolicy(rules, baseline)
        self.goal = RefinementPolicy(rules, target)
        self.target = list(target)
        self.preserve_baseline = preserve_baseline
        self._decisions = {}
        self._ranks = {}
        self.baseline_rank = self.rank(baseline)

    def _decision(self, colors):
        key = tuple(colors)
        if key not in self._decisions:
            self._decisions[key] = self.floor.assess(colors)
        return self._decisions[key]

    def rank(self, colors):
        key = tuple(colors)
        if key in self._ranks:
            return self._ranks[key]
        decision = self._decision(colors)
        if not decision['verified'] or not self.goal.baseline['verified']:
            return (math.inf, math.inf)
        distances = [float(error(colors[i], [self.target[i]], False)) for i in self.floor.order]
        # All regions of this already chosen destination matter. Priorities
        # have been applied by global search; they only break joint ties here.
        rank = (max(distances), sum(distances)/len(distances), *decision['rank'])
        self._ranks[key] = rank
        return rank

    def allows(self, colors):
        decision = self._decision(colors)
        if not decision['verified'] or not self.goal.baseline['verified']:
            return False
        if self.preserve_baseline:
            return decision['not_worse']
        # A global screenshot proposal may intentionally trade priorities.
        # Permit those planned trades, but no additional loss beyond BOTH
        # the measured fallback and the selected proposal in any region.
        for i in self.floor.order:
            base, goal = self.floor.baseline, self.goal.baseline
            if base['hits'][i] and goal['hits'][i] and not decision['actual_hits'][i]:
                return False
            if (not decision['actual_hits'][i] and
                    decision['actual_scores'][i] > max(base['scores'][i], goal['scores'][i])+1e-9):
                return False
        return True

    def improves(self, colors):
        return self.allows(colors) and self.rank(colors) < self.baseline_rank
