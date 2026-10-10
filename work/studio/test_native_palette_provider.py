import unittest
from native_palette_provider import NativePaletteProvider, PaletteUnavailable


class Backend:
    def __init__(self):
        self.identity = ('pid', 'start', 'version')
        self.token = 'a'
        self.active = True
        self.captures = self.discoveries = 0

    def process_identity(self):
        return self.identity

    def discover(self, deadline, check):
        check()
        self.discoveries += 1
        return 123

    def probe(self, address, deadline, check):
        check()
        return dict(active=self.active, session_token=self.token,
                    pose={'position': [0, 0], 'scale': 1, 'rotation_degrees': 0})

    def capture(self, address, deadline, check):
        check()
        self.captures += 1
        return {'capture_id': self.token}


class ProviderTests(unittest.TestCase):
    def test_same_session_reuses_pixels_but_probes_each_read(self):
        backend = Backend()
        provider = NativePaletteProvider(backend, clock=lambda: 0)
        a = provider.read(deadline=10)
        b = provider.read(deadline=10)
        self.assertIs(a['session'], b['session'])
        self.assertEqual(backend.captures, 1)
        self.assertEqual(backend.discoveries, 1)
        self.assertTrue(b['pixel_cache_hit'])

    def test_ended_session_and_restart_never_return_cached_pixels(self):
        backend = Backend()
        provider = NativePaletteProvider(backend, clock=lambda: 0)
        provider.read(deadline=10)
        backend.active = False
        with self.assertRaises(PaletteUnavailable):
            provider.read(deadline=10)
        backend.active = True
        backend.identity = ('new_pid', 'start', 'version')
        backend.token = 'b'
        result = provider.read(deadline=10)
        self.assertEqual(result['session']['capture_id'], 'b')
        self.assertEqual(backend.captures, 2)

    def test_changed_token_recaptures_and_mid_capture_change_rejects(self):
        backend = Backend()
        provider = NativePaletteProvider(backend, clock=lambda: 0)
        provider.read(deadline=10)
        backend.token = 'b'
        self.assertFalse(provider.read(deadline=10)['pixel_cache_hit'])
        original = backend.capture
        def changed(*args):
            result = original(*args)
            backend.token = 'c'
            return result
        backend.capture = changed
        backend.token = 'd'
        with self.assertRaises(PaletteUnavailable):
            provider.read(deadline=10)

    def test_deadline_cancellation_and_read_error_clear_cache(self):
        backend = Backend()
        provider = NativePaletteProvider(backend, clock=lambda: 0)
        with self.assertRaises(PaletteUnavailable):
            provider.read(deadline=0)
        provider.read(deadline=10)
        def stop():
            raise InterruptedError('F9')
        with self.assertRaises(InterruptedError):
            provider.read(deadline=10, check=stop)
        def fail(*args):
            raise OSError('process lost')
        backend.probe = fail
        with self.assertRaises(PaletteUnavailable):
            provider.read(deadline=10)
        self.assertIsNone(provider.cached_address)

    def test_pose_change_and_probe_fingerprint_change_reject_reuse(self):
        backend = Backend()
        provider = NativePaletteProvider(backend, clock=lambda: 0)
        provider.read(deadline=10)
        original = backend.probe
        calls = [0]
        def unstable(*args):
            value = original(*args)
            calls[0] += 1
            if calls[0] % 2 == 0:
                value['pose'] = dict(value['pose'], scale=.99)
            return value
        backend.probe = unstable
        with self.assertRaises(PaletteUnavailable):
            provider.read(deadline=10)
        self.assertIsNone(provider.cached_address)
        backend.probe = original
        backend.token = 'pixel_fingerprint_changed'
        result = provider.read(deadline=10)
        self.assertFalse(result['pixel_cache_hit'])


if __name__ == '__main__':
    unittest.main()
