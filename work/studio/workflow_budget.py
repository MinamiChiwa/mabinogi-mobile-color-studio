"""Timing metadata for a manually started, timed dye workflow.

``game_deadline`` is the hard game cutoff.  Exploration gets a separate,
earlier deadline so that the final positioning, two-frame verification and
return can never be crowded out by a fixed scan route.  The old
``sampling_deadline`` property intentionally remains the hard cutoff for
callers that only need a read-only observation limit.
"""
from dataclasses import dataclass
import math
import time

WORKFLOW_SECONDS = 60.0  # advisory performance reference, never a hard stop
FINISH_RESERVE_SECONDS = 15.0


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
    finish_reserve_seconds: float = FINISH_RESERVE_SECONDS

    def __post_init__(self):
        if not all(math.isfinite(v) for v in
                   (self.ready_at, self.game_deadline, self.finish_reserve_seconds)):
            raise ValueError('Workflow timestamps must be finite')
        if self.finish_reserve_seconds < 0:
            raise ValueError('Finish reserve must be non-negative')

    @property
    def workflow_deadline(self):
        return self.ready_at + WORKFLOW_SECONDS

    @property
    def deadline(self):
        return self.game_deadline

    @property
    def sampling_deadline(self):
        return self.game_deadline

    @property
    def exploration_deadline(self):
        """Last instant at which exploratory input may be started."""
        return max(self.ready_at,
                   self.game_deadline - self.finish_reserve_seconds)

    @property
    def finish_deadline(self):
        """Absolute hard deadline retained for final positioning/verification."""
        return self.game_deadline

    def estimate_cost(self, *, action_seconds=0., registration_seconds=0.,
                      verification_seconds=0., return_seconds=0.,
                      safety_seconds=0.):
        """Return the complete projected cost of one candidate attempt.

        All values are durations in seconds.  Keeping this calculation in the
        budget object makes callers account for both observation frames and
        the mandatory return before sending the next input.
        """
        values=(action_seconds, registration_seconds, verification_seconds,
                return_seconds, safety_seconds)
        if any(not math.isfinite(float(value)) or float(value) < 0
               for value in values):
            raise ValueError('Attempt costs must be finite and non-negative')
        return float(sum(values))

    def can_start_exploration(self, *, now=None, action_seconds=0.,
                              registration_seconds=0., verification_seconds=0.,
                              return_seconds=0., safety_seconds=0.,
                              clock=time.monotonic):
        """Whether a projected attempt fits before the exploration cutoff."""
        now = float(clock() if now is None else now)
        if not math.isfinite(now):
            raise ValueError('Current time must be finite')
        projected=self.estimate_cost(action_seconds=action_seconds,
                                     registration_seconds=registration_seconds,
                                     verification_seconds=verification_seconds,
                                     return_seconds=return_seconds,
                                     safety_seconds=safety_seconds)
        return now + projected < self.exploration_deadline

    def allow_operation(self, *, now, operation_seconds, return_seconds,
                        verification_seconds, positioning_seconds=0.):
        """Price CPU or input work without borrowing the final return tail.

        operation_seconds includes THIS operation's own reads/registration.
        verification_seconds is the independent final two-frame check.
        Unknown durations fail closed instead of becoming zero-cost work.
        """
        values=(now,operation_seconds,return_seconds,verification_seconds,positioning_seconds)
        try:
            valid=all(not isinstance(value,bool) and math.isfinite(float(value))
                      and float(value)>=0 for value in values)
        except (ValueError,TypeError):
            valid=False
        if not valid:
            raise ValueError('Operation timing must be finite and nonnegative')
        reserve=max(self.finish_reserve_seconds,
                    float(return_seconds)+float(verification_seconds)+2.)
        return float(now)+float(operation_seconds)+float(positioning_seconds)+reserve < self.game_deadline
