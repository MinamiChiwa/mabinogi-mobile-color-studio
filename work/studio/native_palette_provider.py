"""Session cache with injected, guarded read-only process backend.

Backend probe must validate live objects AND pixel identity; a pointer alone
is insufficient. Every operation accepts deadline/check for bounded reads.
"""
import math
import time


class PaletteUnavailable(RuntimeError):
    pass


class NativePaletteProvider:
    def __init__(self, backend, *, clock=time.monotonic):
        self.backend, self.clock = backend, clock
        self.invalidate()

    def invalidate(self):
        self.cached_address = None
        self._identity = self._token = self._session = None

    def read(self, *, deadline, check=lambda: None):
        def guard():
            check()
            if not math.isfinite(deadline) or self.clock() >= deadline:
                raise PaletteUnavailable('Read deadline expired')
        try:
            guard()
            identity = self.backend.process_identity()
            guard()
            if identity != self._identity:
                self.invalidate()
                self._identity = identity
            if self.cached_address is None:
                self.cached_address = self.backend.discover(deadline, guard)
                guard()
            if self.cached_address is None:
                raise PaletteUnavailable('No live palette')
            before = self.backend.probe(self.cached_address, deadline, guard)
            guard()
            if not before['active']:
                raise PaletteUnavailable('Palette is inactive')
            token = before['session_token']
            hit = self._session is not None and token == self._token
            if not hit:
                session = self.backend.capture(self.cached_address, deadline, guard)
            else:
                session = self._session
            after = self.backend.probe(self.cached_address, deadline, guard)
            guard()
            if not after['active'] or token != after['session_token'] or before['pose'] != after['pose']:
                raise PaletteUnavailable('Session or pose changed during read')
            if identity != self.backend.process_identity():
                raise PaletteUnavailable('Process changed during read')
            guard()
            self._session, self._token = session, token
            return dict(session=session, current_pose=after['pose'], pixel_cache_hit=hit,
                        session_token=token, observed_at=self.clock(), source='readonly_backend')
        except InterruptedError:
            self.invalidate()
            raise
        except (OSError, ValueError, KeyError, PaletteUnavailable) as exc:
            self.invalidate()
            if isinstance(exc, PaletteUnavailable):
                raise
            raise PaletteUnavailable(str(exc)) from exc
