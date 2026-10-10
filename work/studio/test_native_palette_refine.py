from test_support import read_local_fixture_text
from test_support import load_local_palette_session
import json
import unittest
from itertools import chain, repeat
from pathlib import Path
from native_palette_scoring import load_session, score_native_pose
from native_palette_refine import refine_native_poses


class NativePaletteRefineTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).parent / 'fixtures' / 'native_palette'
        name = json.loads(read_local_fixture_text(root / 'manifest.json'))['snapshots'][1]
        self.session = load_local_palette_session(root / name)
        self.rules = [dict(enabled=True, exact=True, colors=['#D7856D'], tolerance=0),
                      dict(enabled=True, exact=True, colors=['#D0D2B4'], tolerance=0),
                      dict(enabled=True, exact=True, colors=['#6D8354'], tolerance=0)]

    def test_refinement_keeps_exact_initial_and_reports_layers(self):
        seed = [dict(position=[0., 0.], scale=1., rotation_degrees=0.)]
        result = refine_native_poses(self.session, seed, self.rules,
                                     translation_steps=(.01, .0025), scale_steps=(.01,),
                                     rotation_steps=(1.,), top_k=2)
        self.assertTrue(result['candidates'][0]['predicted_accepted'])
        self.assertEqual(result['layers_evaluated'], 2)
        self.assertEqual(result['stop_reason'], 'refinement_exhausted')
        self.assertEqual(result['candidates'][0]['native_pose']['position'], [0., 0.])

    def test_duplicate_seeds_are_deduplicated_and_limits_apply(self):
        seeds = [dict(position=[0., 0.], scale=1., rotation_degrees=0.)] * 3
        result = refine_native_poses(self.session, seeds, self.rules,
                                     translation_steps=(.01,), scale_steps=(.01,),
                                     rotation_steps=(1.,), max_candidates=4, top_k=3)
        self.assertEqual(result['evaluated'], 4)
        self.assertEqual(result['stop_reason'], 'candidate_limit')
        self.assertFalse(result['complete'])

    def test_deadline_and_invalid_step_stop(self):
        seed = [dict(position=[0., 0.], scale=1., rotation_degrees=0.)]
        with self.assertRaises(ValueError):
            refine_native_poses(self.session, seed, self.rules, translation_steps=(0.,))
        ticks = chain([0.], repeat(2.))
        result = refine_native_poses(self.session, seed, self.rules, time_budget_seconds=1.,
                                     clock=lambda: next(ticks))
        self.assertEqual(result['evaluated'], 0)
        self.assertEqual(result['stop_reason'], 'deadline')

    def test_translation_refinement_finds_known_neighbor(self):
        target = dict(position=[.01, 0.], scale=1., rotation_degrees=0.)
        codes = score_native_pose(self.session, target, self.rules)['colors']
        rules = [dict(rule, colors=[code]) for rule, code in zip(self.rules, codes)]
        seed = [dict(target, position=[0., 0.])]
        self.assertFalse(score_native_pose(self.session, seed[0], rules)['predicted_accepted'])
        result = refine_native_poses(self.session, seed, rules, translation_steps=(.01, .0025), top_k=1)
        self.assertTrue(result['candidates'][0]['predicted_accepted'])
        self.assertEqual(result['candidates'][0]['colors'], codes)

    def test_cancellation_and_small_positive_scale(self):
        seeds = [dict(position=[0., 0.], scale=.001, rotation_degrees=0.)]
        def stop():
            raise InterruptedError('F9')
        with self.assertRaises(InterruptedError):
            refine_native_poses(self.session, seeds, self.rules, check=stop)
        result = refine_native_poses(self.session, seeds, self.rules, translation_steps=(.01,), top_k=1)
        self.assertTrue(result['complete'])
        self.assertGreater(result['candidates'][0]['native_pose']['scale'], 0)


if __name__ == '__main__':
    unittest.main()
