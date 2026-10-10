"""Opt-in journal for one timed, real-game mechanism experiment.

This module only structures evidence.  It never sends input, starts a dye,
confirms a result, or infers that a dye was consumed.  Callers must provide
the externally observed consumption marker explicitly (``True``/``False`` or
``None`` when it is not known).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping
import time


def _finite_number(value: Any) -> float | None:
    """Return a finite numeric value, preserving missing evidence as None."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def _numeric_values(value: Any) -> list[float]:
    """Flatten one scalar/sequence of explicitly measured numeric values."""
    if isinstance(value, (list, tuple)):
        result: list[float] = []
        for item in value:
            number = _finite_number(item)
            if number is not None:
                result.append(number)
        return result
    number = _finite_number(value)
    return [] if number is None else [number]


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * float(quantile)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


@dataclass
class MechanismExperimentRecorder:
    """Collect baseline and per-action evidence without changing game state."""

    started_at: float = field(default_factory=time.monotonic)
    dye_consumed: bool | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    action_count: int = 0

    def _elapsed(self, clock=time.monotonic) -> float:
        return max(0.0, float(clock()) - float(self.started_at))

    def set_consumption(self, consumed: bool | None) -> None:
        """Set an explicit human/game observation; no inference is performed."""
        if consumed is not None and not isinstance(consumed, bool):
            raise TypeError("dye_consumed must be True, False, or None")
        self.dye_consumed = consumed

    def baseline(self, *, frame: str | None = None,
                 hexes: Any = None, countdown_seconds: float | None = None,
                 registration_seconds: float | None = None,
                 points: Any = None, clock=time.monotonic, **extra: Any) -> dict[str, Any]:
        row = dict(kind="mechanism_baseline", elapsed_seconds=self._elapsed(clock),
                   frame=frame, hex_before=hexes,
                   countdown_seconds=countdown_seconds,
                   registration_seconds=registration_seconds,
                   points=points, dye_consumed=self.dye_consumed)
        row.update(extra)
        self.events.append(row)
        return row

    def action(self, *, name: str, direction: Any = None, step: Any = None,
               frame_before: str | None = None, frame_after: str | None = None,
               hex_before: Any = None, hex_after: Any = None,
               hex_first: Any = None, hex_settled: Any = None,
               countdown_before: float | None = None,
               countdown_after: float | None = None,
               registration_seconds: float | None = None,
               registration_p95_seconds: float | None = None,
               input_seconds: float | None = None,
               pose: Any = None, residual: Any = None,
               clock=time.monotonic, **extra: Any) -> dict[str, Any]:
        self.action_count += 1
        row = dict(kind="mechanism_action", action_index=self.action_count,
                   name=name, direction=direction, step=step,
                   frame_before=frame_before, frame_after=frame_after,
                   hex_before=hex_before, hex_after=hex_after,
                   hex_first=hex_first, hex_settled=hex_settled,
                   countdown_before=countdown_before,
                   countdown_after=countdown_after,
                   registration_seconds=registration_seconds,
                   registration_p95_seconds=registration_p95_seconds,
                   input_seconds=input_seconds, pose=pose, residual=residual,
                   elapsed_seconds=self._elapsed(clock),
                   dye_consumed=self.dye_consumed)
        row.update(extra)
        self.events.append(row)
        return row

    def finish(self, *, status: str, final_hexes: Any = None,
               countdown_seconds: float | None = None,
               return_success: bool | None = None, clock=time.monotonic,
               **extra: Any) -> dict[str, Any]:
        row = dict(kind="mechanism_experiment_complete",
                   status=status, elapsed_seconds=self._elapsed(clock),
                   action_count=self.action_count, final_hexes=final_hexes,
                   countdown_seconds=countdown_seconds,
                   return_success=return_success,
                   dye_consumed=self.dye_consumed,
                   evidence_scope="same_session_observation_only")
        row.update(extra)
        self.events.append(row)
        return row

    def report(self) -> dict[str, Any]:
        """Return evidence grouped for review; no mechanism conclusion is made."""
        observed = [e for e in self.events if e["kind"] in
                    ("mechanism_baseline", "mechanism_action")]
        actions = [e for e in observed if e["kind"] == "mechanism_action"]
        delta_values: list[float] = []
        max_delta_values: list[float] = []
        mean_delta_values: list[float] = []
        hit_values: list[float] = []
        input_times: list[float] = []
        registration_times: list[float] = []
        for event in actions:
            delta = event.get("delta_e", event.get("deltaE"))
            if isinstance(delta, Mapping):
                values = _numeric_values(list(delta.values()))
            else:
                values = _numeric_values(delta)
            if values:
                delta_values.extend(values)
                max_delta_values.append(max(values))
                mean_delta_values.append(sum(values) / len(values))
            hit = _finite_number(event.get("hit_count", event.get("precise_hits")))
            if hit is not None:
                hit_values.append(hit)
            input_time = _finite_number(event.get("input_seconds"))
            if input_time is not None:
                input_times.append(input_time)
            registration_time = _finite_number(event.get("registration_seconds"))
            if registration_time is not None:
                registration_times.append(registration_time)
        finish_events = [e for e in self.events
                         if e["kind"] == "mechanism_experiment_complete"]
        finish = finish_events[-1] if finish_events else {}
        return dict(schema=2, protocol="mechanism_experiment",
                    events=list(self.events), action_count=self.action_count,
                    dye_consumed=self.dye_consumed, observed=observed,
                    inferred=[], summary=dict(
                        action_count=self.action_count,
                        max_delta_e=max(max_delta_values) if max_delta_values else None,
                        mean_delta_e=(sum(mean_delta_values) / len(mean_delta_values)
                                      if mean_delta_values else None),
                        precise_hit_count=(max(hit_values) if hit_values else None),
                        input_seconds_total=sum(input_times) if input_times else None,
                        registration_seconds_total=(sum(registration_times)
                                                    if registration_times else None),
                        registration_seconds_p95=(_percentile(registration_times, .95)
                                                  if registration_times else None),
                        first_usable_elapsed_seconds=finish.get(
                            "first_usable_elapsed_seconds"),
                        final_remaining_seconds=finish.get("countdown_seconds"),
                        return_success=finish.get("return_success"),
                        double_frame_confirmed=finish.get("double_frame_confirmed"),
                    ),
                    unverified=["cross_session", "cross_device",
                                "production_response_model"])


def record_probe_event(recorder: MechanismExperimentRecorder | None, kind: str,
                       data: Mapping[str, Any], *, clock=time.monotonic) -> None:
    """Bridge a response-probe event into the opt-in experiment journal."""
    if recorder is None:
        return
    if kind == "response_probe_plan":
        recorder.baseline(frame="max_sampling", points=data.get("markers"),
                          hexes=data.get("hex_before"),
                          countdown_seconds=data.get("countdown_seconds"),
                          clock=clock, protocol=data.get("protocol"),
                          planned_actions=len(data.get("actions") or ()))
    elif kind == "response_probe_measurement":
        measurements = data.get("measurements") or {}
        registration = measurements.get("forward") or {}
        details = data.get("diagnostics") or {}
        gesture = data.get("gesture") or {}
        direction = gesture.get("kind")
        step = (gesture.get("wheel_steps") if direction == "wheel"
                else gesture.get("requested_angle"))
        recorder.action(name=data.get("name", ""),
                        direction=direction,
                        step=step,
                        frame_before=data.get("reference"),
                        frame_after=data.get("settled", data.get("frame")),
                        hex_before=data.get("hex_before"),
                        hex_after=data.get("hex_after"),
                        hex_first=data.get("hex_first"),
                        hex_settled=data.get("hex_settled"),
                        countdown_before=data.get("countdown_before"),
                        countdown_after=data.get("countdown_after"),
                        input_seconds=data.get(
                            "input_seconds", data.get("input_elapsed_seconds")),
                        registration_seconds=data.get(
                            "registration_seconds",
                            details.get("registration_seconds")),
                        # A regular rotation probe supplies forward/reverse
                        # closure; the wheel probe supplies per-step marker
                        # errors instead. Preserve whichever was actually
                        # measured rather than inventing a common residual.
                        residual=data.get("closure_pixels",
                                         data.get("marker_errors")),
                        pose=data.get("pose_after"), clock=clock,
                        registration_complete=data.get("registration_complete"),
                        measured_motion=registration,
                        registration_diagnostics=details)
    elif kind == "response_probe_complete":
        recorder.finish(status=data.get("status", "unknown"),
                        countdown_seconds=data.get("countdown_seconds"),
                        clock=clock, planned=data.get("planned"),
                        completed=data.get("completed"))
