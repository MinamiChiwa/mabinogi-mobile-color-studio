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

    def __post_init__(self):
        values=(self.input_deadline,self.observation_deadline,self.hard_deadline)
        if (not all(math.isfinite(v) for v in values) or
                not self.input_deadline <= self.observation_deadline <= self.hard_deadline):
            raise ValueError('Execution stage deadlines must be finite and ordered')

    @classmethod
    def for_attempt(cls,deadline,hard_deadline,*,observation_seconds=3.5,clock=time.monotonic):
        end=min(float(deadline),float(hard_deadline))
        return cls(end-float(observation_seconds),end,float(hard_deadline),clock)

    def check_input(self):
        if self.clock() >= self.input_deadline:
            raise StageBudgetExceeded('Positioning stage ended; observing the current pose')

    def check_observation(self):
        if self.clock() >= self.observation_deadline:
            raise StageBudgetExceeded('Observation stage ended; preserving the return reserve')

    def can_observe(self,seconds=0.):
        return self.clock()+float(seconds) < self.observation_deadline
