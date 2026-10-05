"""Soft execution stages inside the game's independent hard deadline."""
from dataclasses import dataclass
import math
import time


class StageBudgetExceeded(RuntimeError):
    """Stop this attempt while retaining time to observe and return."""


@dataclass(frozen=True)
class ExecutionStageBudget:
    input_deadline: float
    observation_deadline: float
    hard_deadline: float
    clock: object = time.monotonic
    finish_reserve_seconds: float = 15.0
    # Directly constructed budgets retain legacy stage semantics; production
    # attempt budgets created by ``for_attempt`` enable the full cost gate.
    enforce_attempt_costs: bool = False

    def __post_init__(self):
        values=(self.input_deadline,self.observation_deadline,self.hard_deadline,
                self.finish_reserve_seconds)
        if (not all(math.isfinite(v) for v in values) or
                not self.input_deadline <= self.observation_deadline <= self.hard_deadline):
            raise ValueError('Execution stage deadlines must be finite and ordered')
        if self.finish_reserve_seconds < 0:
            raise ValueError('Finish reserve must be non-negative')

    @classmethod
    def for_attempt(cls,deadline,hard_deadline,*,observation_seconds=3.5,
                    finish_reserve_seconds=15.0,clock=time.monotonic):
        end=min(float(deadline),float(hard_deadline))
        # The input cutoff must leave enough wall-clock time for the final
        # return and two-frame verification.  A short trial deadline can still
        # tighten this further; the hard game cutoff remains authoritative.
        reserve_cutoff=float(hard_deadline)-float(finish_reserve_seconds)
        input_deadline=min(end-float(observation_seconds),reserve_cutoff)
        observation_deadline=min(end,float(hard_deadline))
        # If the trial itself ends before the reserve cutoff, preserve the
        # historical behaviour while still carrying the reserve metadata.
        if input_deadline > observation_deadline:
            input_deadline=observation_deadline
        return cls(input_deadline,observation_deadline,float(hard_deadline),clock,
                   float(finish_reserve_seconds),True)

    def check_input(self):
        if self.clock() >= self.input_deadline:
            raise StageBudgetExceeded('Positioning stage ended; observing the current pose')

    def check_observation(self):
        if self.clock() >= self.observation_deadline:
            raise StageBudgetExceeded('Observation stage ended; preserving the return reserve')

    def can_observe(self,seconds=0.):
        return self.clock()+float(seconds) < self.observation_deadline

    @property
    def exploration_deadline(self):
        """Latest input instant after reserving finalization time."""
        return min(self.input_deadline,
                   self.hard_deadline-self.finish_reserve_seconds)

    def estimate_cost(self, *, action_seconds=0., registration_seconds=0.,
                      verification_seconds=0., return_seconds=0.,
                      safety_seconds=0.):
        values=(action_seconds, registration_seconds, verification_seconds,
                return_seconds, safety_seconds)
        if any(not math.isfinite(float(value)) or float(value) < 0
               for value in values):
            raise ValueError('Attempt costs must be finite and non-negative')
        return float(sum(values))

    def can_start_attempt(self, *, action_seconds=0., registration_seconds=0.,
                          verification_seconds=0., return_seconds=0.,
                          safety_seconds=0.):
        """Check a projected action before issuing its first input."""
        projected=self.estimate_cost(action_seconds=action_seconds,
                                     registration_seconds=registration_seconds,
                                     verification_seconds=verification_seconds,
                                     return_seconds=return_seconds,
                                     safety_seconds=safety_seconds)
        return self.clock()+projected < self.exploration_deadline

    def check_attempt(self, **costs):
        # Legacy stage budgets only gate the current stage boundary. Full
        # attempt costing is enabled by ``for_attempt`` in live execution.
        if not self.enforce_attempt_costs:
            self.check_input()
            return
        if not self.can_start_attempt(**costs):
            raise StageBudgetExceeded(
                'Not enough time for action, observation and return reserve')
