"""Prepared game bridge for the diagnostic; not wired to any live entry point.

Construction requires an already recognized manual session and its original
WorkflowBudget. This module never finds/opens a game, starts zoom, or launches
a capture workflow. Tests use fake games; no live run is authorized by import.
"""
import json
import math
from pathlib import Path
import re
import time
from dataclasses import asdict
import numpy as np
from PIL import Image
from atlas_execution import Context
from atlas_runtime import motion as registered_motion
from micro_return_probe import run_micro_return, strict_codes
from vision import configure_ocr, recognize
from workflow_budget import WorkflowBudget


class MicroReturnAdapter:
    def __init__(self, game, scene, budget, folder, *, session, clock=time.monotonic):
        if not isinstance(budget, WorkflowBudget) or not session:
            raise ValueError('Existing workflow budget and session identity required')
        if not callable(getattr(game, 'input_scope', None)):
            raise ValueError('Game requires final-boundary input_scope support')
        if not math.isfinite(game.until):
            raise ValueError('Game must already have an OCR-derived finite deadline')
        self.g, self.scene, self.budget = game, scene, budget
        self.session, self.clock = session, clock
        self.until = min(budget.deadline, game.until, getattr(game, 'stage_until', float('inf')))
        self.initial_geometry = tuple(game.geometry())
        self.initial_context = self.context()
        self.folder = Path(folder)
        self.events = []
        self._captures = {}
        self._codes = {}
        self._stage_deadline = None
        self._used = False
        self._attempted_notches = 0
        self.check()
        configure_ocr(strict=True)
        self.check()
        self.folder.mkdir(parents=True, exist_ok=False)
        self.log('micro_return_adapter_ready', budget=asdict(budget), deadline=self.until,
                 geometry=list(self.initial_geometry), board=list(scene.board),
                 markers=[list(p) for p in scene.markers], cards=[list(c) for c in scene.cards],
                 live_validated=False, production_entry_connected=False)

    def log(self, kind, **fields):
        self.events.append(dict(kind=kind, at=self.clock(), **fields))
        # Keep every completed event in a recoverable journal, including failures.
        with (self.folder/'adapter-events.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(self.events[-1], ensure_ascii=False, allow_nan=False) + '\n')

    def check(self):
        self.g.check()
        if self.context() != self.initial_context:
            raise RuntimeError('Diagnostic session geometry changed')
        if self.clock() >= self.until:
            raise RuntimeError('Diagnostic shared deadline expired')
        if self._stage_deadline is not None and self.clock() >= self._stage_deadline:
            raise RuntimeError('Diagnostic stage deadline expired')

    def context(self):
        return Context(self.session, tuple(self.g.geometry()), tuple(self.scene.board),
                       tuple(map(tuple, self.scene.markers)))

    def marker_points(self):
        # Runtime motion returns board-crop matrices, not full-client matrices.
        return (np.asarray(self.scene.markers, float) - self.scene.board[:2]).tolist()

    def begin(self, deadline):
        if self._used or not math.isfinite(deadline):
            raise RuntimeError('Diagnostic adapter is single use')
        self._stage_deadline = min(deadline, self.until, self.clock() + 25.)
        self._used = True
        self.check()

    def capture(self, name):
        self.check()
        if not self._used:
            raise RuntimeError('Diagnostic has not begun')
        if (re.fullmatch(r'[a-z][a-z0-9_]*', name) is None or name in self._captures or
                (self.folder/(name+'.png')).exists() or (self.folder/(name+'_board.png')).exists()):
            raise ValueError('Unique safe capture name required')
        # Move the cursor above the board only inside the active deadline guard.
        park = (int(self.initial_geometry[2] * .5), int(self.initial_geometry[3] * .15))
        l, t, r, b = map(int, self.scene.board)
        if l <= park[0] <= r and t <= park[1] <= b:
            raise ValueError('No verified cursor parking position outside board')
        with self.g.input_scope(min(self.until, self._stage_deadline or self.until), self.check):
            self.g.move_to(park)
        self.g.pause(.10)
        self.check()
        captured_at = self.clock()
        image = self.g.capture()
        self.check()
        expected = (self.initial_geometry[3], self.initial_geometry[2], 3)
        if image.shape != expected or image.dtype != np.uint8:
            raise RuntimeError('Capture dimensions or RGB format changed')
        Image.fromarray(image).save(self.folder/(name+'.png'), compress_level=1)
        Image.fromarray(image[t:b, l:r]).save(self.folder/(name+'_board.png'), compress_level=1)
        self._captures[name] = (image, captured_at)
        self.log('micro_return_frame', name=name, captured_at=captured_at,
                 full_image=name+'.png', board_image=name+'_board.png')
        self.check()
        return image

    def motion(self, reference, frame):
        self.check()
        result = registered_motion(reference, frame, self.scene)
        self.check()
        reverse = registered_motion(frame, reference, self.scene)
        self.check()
        record = dict(forward=result, reverse=reverse, closure_pixels=None)
        if result is not None and reverse is not None:
            matrices = []
            for item in (result, reverse):
                affine = np.asarray(item['matrix'], float)
                if affine.shape != (2, 3) or not np.isfinite(affine).all():
                    raise RuntimeError('Invalid diagnostic registration matrix')
                value = np.eye(3)
                value[:2] = affine
                matrices.append(value)
            composed = matrices[1] @ matrices[0]
            points = np.column_stack((self.marker_points(), np.ones(3)))
            residual = np.linalg.norm((points @ (composed - np.eye(3)).T)[:, :2], axis=1)
            record['closure_pixels'] = residual.tolist()
        self.log('micro_return_bidirectional_motion', **record)
        self.check()
        if record['closure_pixels'] is None or max(record['closure_pixels']) > .035:
            raise RuntimeError('Bidirectional registration exceeds the provisional 0.035 pixel consistency gate')
        # Passing this necessary consistency check is not an accuracy bound.
        return result

    def read_codes(self, image):
        self.check()
        captured = next(((name, at) for name, (saved, at) in self._captures.items() if saved is image), None)
        if captured is None:
            raise ValueError('Only this session\'s preserved captures can be read')
        name, captured_at = captured
        if name in self._codes:
            raise RuntimeError('Repeated OCR of one image is not an independent observation')
        self._codes[name] = None
        timed = recognize(image, with_ocr=True, previous=self.scene)
        self.check()
        # Recognition keeps calibrated marker coordinates when card geometry is
        # stable. A changed board or card invalidates this diagnostic context.
        if (tuple(timed.board) != tuple(self.scene.board) or
                tuple(map(tuple, timed.cards)) != tuple(map(tuple, self.scene.cards)) or
                tuple(map(tuple, timed.markers)) != tuple(map(tuple, self.scene.markers))):
            raise RuntimeError('Recognized board geometry changed')
        seconds = timed.seconds
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or not 0 < seconds <= 120:
            raise RuntimeError('Reliable game countdown missing during diagnostic')
        # A later OCR reading may only tighten the original shared deadline.
        self.until = min(self.until, captured_at + seconds)
        colors = strict_codes(timed.colors)
        self._codes[name] = colors
        self.log('micro_return_ocr', frame=name, colors=colors, timer_seconds=seconds, deadline=self.until)
        self.check()
        return colors

    def wheel(self, notch, anchor, *, deadline, guard):
        self.check()
        if not self._used or self._stage_deadline is None:
            raise RuntimeError('Diagnostic has not begun')
        if notch not in (-1, 1) or self._attempted_notches >= 8:
            raise ValueError('One bounded notch per call, at most eight total')
        p = np.asarray(anchor, float)
        l, t, r, b = self.scene.board
        if p.shape != (2,) or not np.isfinite(p).all() or not (l+8 < p[0] < r-8 and t+8 < p[1] < b-8):
            raise ValueError('Wheel anchor must be safely inside current board')
        if 'baseline_0' not in self._codes or 'baseline_1' not in self._codes:
            raise RuntimeError('Two separately captured baseline readings required before wheel input')
        if self._codes['baseline_0'] is None or self._codes['baseline_0'] != self._codes['baseline_1']:
            raise RuntimeError('Baseline HEX is unverified or unstable')
        self._attempted_notches += 1
        self.log('micro_return_input_attempt', notch=notch, anchor=p.tolist(), attempt=self._attempted_notches)

        def checked_guard():
            self.check()
            guard()
        with self.g.input_scope(min(deadline, self.until, self._stage_deadline), checked_guard):
            checked_guard()
            self.g.wheel(self.scene.board, notch, anchor=p.tolist())
        self.check()

    def pause(self, seconds):
        self.check()
        self.g.pause(seconds)
        self.check()

    def release(self):
        try:
            self.g.send(4)
        finally:
            self.g.send(16)


def run_prepared_diagnostic(adapter, anchors, *, limits=None):
    """Single-use bridge; caller must supply the already prepared session.

    Even a protocol pass remains provisional: registration uncertainty and
    actual game reversibility need separate evidence. No automatic retry.
    """
    from micro_return_probe import ReturnLimits
    limits = limits or ReturnLimits()
    deadline = min(adapter.until, adapter.clock() + limits.stage_seconds)
    try:
        adapter.begin(deadline)
        result = run_micro_return(adapter, anchors, deadline, clock=adapter.clock, limits=limits)
        result.update(registration_uncertainty_validated=False, production_ready=False)
        # Journaling consumes real time too. Never return a current-state claim
        # if the deadline/context expired while the controller result was saved.
        (adapter.folder/'return-result.json').write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf-8')
        adapter.log('micro_return_finished', protocol_passed=result['protocol_passed'], reason=result['reason'])
        if result['current_verified']:
            try:
                adapter.check()
            except Exception as exc:
                result.update(reason='stopped', error=str(exc), current=None, current_verified=False,
                              baseline_verified_now=False, returned_to_baseline=False, protocol_passed=False)
                (adapter.folder/'return-result.json').write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf-8')
                adapter.log('micro_return_postsave_failure', error=str(exc))
        return result
    except Exception as exc:
        try:
            adapter.log('micro_return_adapter_failure', error=str(exc))
        finally:
            adapter.release()
        raise
