import unittest
import test_native_palette_actions as fixtures
from native_palette_action_search import search_native_actions
from native_action_refine import refine_action_endpoints


class ActionRefineTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.NativePaletteActionsTests()
        self.f.setUp()

    def test_keep_exact_endpoint_and_rescore_generated_neighbors(self):
        f = self.f
        initial = search_native_actions(f.session, [f.reference], f.reference, f.board, f.markers,
                                        f.rules, now=0, deadline=100)
        result = refine_action_endpoints(f.session, initial['candidates'], f.reference, f.board,
                                         f.markers, f.rules, now=0, deadline=100,
                                         pixel_steps=(1., .25), angle_steps=(.05,), scale_steps=(.0001,))
        self.assertTrue(result['candidates'][0]['planned_predicted_accepted'])
        self.assertFalse(result['execution_verified'])
        self.assertEqual(result['layers_completed'], 2)
        self.assertGreater(result['evaluated'], 1)

    def test_bad_steps_and_expired_budget(self):
        f = self.f
        with self.assertRaises(ValueError):
            refine_action_endpoints(f.session, [], f.reference, f.board, f.markers, f.rules,
                                    now=0, deadline=100, pixel_steps=(0,))
        result = refine_action_endpoints(f.session, [], f.reference, f.board, f.markers, f.rules,
                                         now=100, deadline=100)
        self.assertEqual(result['candidates'], [])
        self.assertEqual(result['stop_reason'], 'deadline')

    def test_other_session_and_cancel_are_rejected(self):
        f = self.f
        initial = search_native_actions(f.session, [f.reference], f.reference, f.board, f.markers,
                                        f.rules, now=0, deadline=100)
        other = dict(initial['candidates'][0], capture_id='other_session')
        with self.assertRaises(ValueError):
            refine_action_endpoints(f.session, [other], f.reference, f.board, f.markers,
                                    f.rules, now=0, deadline=100)
        def stop():
            raise InterruptedError('F9')
        with self.assertRaises(InterruptedError):
            refine_action_endpoints(f.session, initial['candidates'], f.reference, f.board,
                                    f.markers, f.rules, now=0, deadline=100, check=stop)


if __name__ == '__main__':
    unittest.main()
