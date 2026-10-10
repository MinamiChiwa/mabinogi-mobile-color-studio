"""Timing metadata for a manually started, timed dye workflow.

The nominal workflow duration is a performance reference only.  It must not
abort a normal run; the game's OCR-derived countdown remains the only hard
input deadline.
"""
from dataclasses import dataclass
import math

WORKFLOW_SECONDS = 60.0  # advisory performance reference, never a hard stop
FINISH_RESERVE_SECONDS = 0.0  # retained as a named compatibility constant


def earliest_deadline(*limits):
    """Optional limits may tighten a deadline, never extend it."""
    values = [float(value) for value in limits if value is not None]
    if any(not math.isfinite(value) for value in values):
        raise ValueError('Deadline must be finite')
    return min(values) if values else None


@dataclass(frozen=True)
class WorkflowBudget:
    ready_at: float
    game_deadline: float

    def __post_init__(self):
        if not all(math.isfinite(v) for v in (self.ready_at, self.game_deadline)):
            raise ValueError('Workflow timestamps must be finite')

    @property
    def workflow_deadline(self):
        return self.ready_at + WORKFLOW_SECONDS

    @property
    def deadline(self):
        return self.game_deadline

    @property
    def sampling_deadline(self):
        return self.game_deadline
