"""Shared deterministic fixtures for the search and return-protocol tests.

These adapters model game input and affine board motion only.  They are kept in
one support module so tests that exercise the same protocol do not each carry a
slightly different copy of the fixture.
"""

from types import SimpleNamespace
import json
from pathlib import Path
import unittest

import numpy as np


def requires_local_fixture(*paths):
    """Skip only undistributed files; malformed or wrong evidence still fails."""
    for value in paths:
        path = Path(value)
        if not path.is_file():
            raise unittest.SkipTest('Optional local fixture not distributed: ' + str(path))


def requires_palette_fixture(folder):
    folder = Path(folder)
    snapshot = folder / 'snapshot.json'
    requires_local_fixture(snapshot)
    # Do not catch JSON/schema errors: existing corrupted evidence must fail.
    data = json.loads(snapshot.read_text(encoding='utf-8'))
    requires_local_fixture(*(folder / fragment['pixel_file'] for fragment in data['fragments']))


def requires_native_case(folder):
    folder = Path(folder)
    requires_local_fixture(folder / 'case.json')
    requires_palette_fixture(folder / 'palette')


def load_local_palette_session(folder):
    """Keep the real production loader and its hashes after presence checks."""
    from native_palette_scoring import load_session
    requires_palette_fixture(folder)
    return load_session(folder)


def read_local_fixture_text(path, **kwargs):
    requires_local_fixture(path)
    return Path(path).read_text(**kwargs)


class SimulatedReturnAdapter:
    """Reciprocal zoom about individual anchors, with explicit fault hooks."""

    def __init__(self):
        self.now = 0.
        self.pose = np.eye(3)
        self.ctx = 'same-session-geometry'
        self.stopped = False
        self.released = False
        self.wheels = []
        self.captures = []
        self.reads = 0
        self.after_wheel = lambda: None
        self.before_input = lambda: None
        self.after_capture = lambda: None
        self.after_read = lambda: None
        self.after_motion = lambda: None
        self.after_pause = lambda: None
        self.codes = lambda frame: (
            ['#123456', '#789ABC', '#DEF012']
            if frame['notches'] % 4 == 0
            else ['#234567', '#89ABCD', '#EF0123']
        )

    def check(self):
        if self.stopped:
            raise RuntimeError('Stopped / focus / countdown guard')

    def context(self):
        return self.ctx

    def marker_points(self):
        return [[80, 350], [250, 250], [420, 360]]

    def capture(self, name):
        self.now += .05
        frame = dict(name=name, pose=self.pose.copy(), notches=len(self.wheels))
        self.captures.append(frame)
        self.after_capture()
        return frame

    def motion(self, reference, frame):
        self.now += .05
        matrix = (frame['pose'] @ np.linalg.inv(reference['pose']))[:2]
        self.after_motion()
        return dict(matrix=matrix.tolist(), scale=float(np.hypot(*matrix[:, 0])),
                    angle=float(np.degrees(np.arctan2(matrix[1, 0], matrix[0, 0]))),
                    inliers=100)

    def read_codes(self, frame):
        self.now += .44
        self.reads += 1
        self.after_read()
        return self.codes(frame)

    def wheel(self, notch, anchor, *, deadline, guard):
        # Model a cursor move that may consume time or change foreground before
        # the final wheel boundary. Recheck there, not only in the controller.
        self.before_input()
        guard()
        if self.now >= deadline:
            raise RuntimeError('Input deadline')
        scale = 1.01 if notch == 1 else 1 / 1.01
        zoom = np.eye(3)
        zoom[:2, :2] *= scale
        zoom[:2, 2] = (1 - scale) * np.asarray(anchor)
        self.pose = zoom @ self.pose
        self.wheels.append(dict(notch=notch, anchor=np.asarray(anchor).tolist(), at=self.now))
        self.now += .01
        self.after_wheel()

    def pause(self, seconds):
        self.now += seconds
        self.after_pause()

    def release(self):
        self.released = True


def scene():
    """Minimal board/marker scene shared by affine single-region tests."""
    return SimpleNamespace(board=(0, 0, 300, 300),
                           markers=[(50, 150), (150, 150), (250, 150)], cards=[])


def rules(exact=True):
    """Three-region rules with only the first region enabled for unit tests."""
    return [dict(enabled=i == 0, colors=['#000000'], exact=exact, tolerance=8)
            for i in range(3)]


class StopRequested(Exception):
    """Fixture exception used to model the user's stop hotkey."""


class AffineGame:
    """Small affine game model with non-reversible directional zoom."""

    def __init__(self, color=None, *, up=1.013, down=.991,
                 native_limits=(.5, 2), now=0.):
        self.now = float(now)
        self.pose = np.eye(3)
        self.up = up
        self.down = down
        self.native_limits = native_limits
        self.commands = []
        self.events = []
        self.frames = {}
        self.reads = 0
        self.stopped = False
        self.color = color or (lambda game: '#111111')
        self.motion_available = True

    @property
    def scale(self):
        return float(np.sqrt(np.linalg.det(self.pose[:2, :2])))

    @property
    def source(self):
        return (np.linalg.inv(self.pose) @ [50, 150, 1])[:2]

    def clock(self):
        return self.now

    def check(self):
        if self.stopped:
            raise StopRequested('F9')

    def pause(self, seconds):
        self.check()
        self.now += seconds

    def capture(self):
        self.check()
        self.now += .025
        image = np.full((300, 300, 3), 90, np.uint8)
        self.frames[id(image)] = self.pose.copy()
        return image

    def drag(self, board, dx, dy):
        self.check()
        self.commands.append(('drag', dx, dy, self.now))
        self.now += .35
        matrix = np.eye(3)
        matrix[:2, 2] = [dx, dy]
        self.pose = matrix @ self.pose

    def wheel(self, board, steps, anchor=None):
        self.check()
        self.commands.append(('wheel', int(steps), tuple(anchor), self.now))
        self.now += .15
        gain = self.up ** steps if steps > 0 else self.down ** (-steps)
        target = np.clip(self.scale * gain, *self.native_limits)
        gain = float(target / self.scale)
        pivot = np.asarray(anchor, float)
        matrix = np.eye(3)
        matrix[:2, :2] *= gain
        matrix[:2, 2] = pivot - gain * pivot
        self.pose = matrix @ self.pose

    def measure(self, before, after, _scene):
        self.check()
        self.now += .045
        if not self.motion_available:
            return None
        motion = self.frames[id(after)] @ np.linalg.inv(self.frames[id(before)])
        return dict(matrix=motion.tolist(), origin=[0, 0])

    def read(self, image, *, enabled, deadline):
        self.check()
        self.reads += 1
        self.now += .10
        return [self.color(self) if enabled[0] else None, None, None]

    def emit(self, kind, **data):
        self.events.append((kind, data))
