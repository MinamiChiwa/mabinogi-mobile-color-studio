from test_support import read_local_fixture_text
from test_support import load_local_palette_session
import json
import unittest
from pathlib import Path
import numpy as np

from native_palette_scoring import load_session, score_native_pose, rank_native_poses
from native_palette_model import color32

ROOT = Path(__file__).parent / 'fixtures' / 'native_palette'


class NativePaletteScoringTests(unittest.TestCase):
    def setUp(self):
        self.names = json.loads(read_local_fixture_text(ROOT / 'manifest.json'))['snapshots']
        self.session = load_local_palette_session(ROOT / self.names[1])

    def test_all_recorded_shared_poses_match_client_and_rule_scores(self):
        for name in self.names:
            session = load_local_palette_session(ROOT / name)
            snapshot = json.loads(read_local_fixture_text(ROOT / name / 'snapshot.json'))
            codes = ['#%02X%02X%02X' % tuple(color32(c[:3])) for c in snapshot['picker_colors_rgba']]
            rules = [dict(enabled=True, exact=True, colors=[c], tolerance=0) for c in codes]
            result = score_native_pose(session, session['initial_pose'], rules)
            self.assertEqual(result['colors'], codes)
            self.assertTrue(result['predicted_accepted'])
            self.assertFalse(result['verified'])
            self.assertFalse(result['execution_verified'])
            self.assertNotIn('accepted', result)

    def test_changed_pose_recomputes_and_disabled_region_is_ignored(self):
        rules = [dict(enabled=i == 0, exact=True, colors=['#000000'], tolerance=0) for i in range(3)]
        before = score_native_pose(self.session, self.session['initial_pose'], rules)
        after = score_native_pose(self.session, dict(position=[.13, -.24], scale=.99, rotation_degrees=2.5), rules)
        self.assertNotEqual(before['colors'][0], after['colors'][0])
        self.assertEqual(after['colors'][1:], [None, None])

    def test_explicit_pose_list_ranks_matching_candidate_first(self):
        pose = self.session['initial_pose']
        rules = [dict(enabled=True, exact=True, colors=['#000000'], tolerance=0) for _ in range(3)]
        colors = score_native_pose(self.session, pose, rules)['colors']
        for rule, color in zip(rules, colors):
            rule['colors'] = [color]
        candidates = [dict(position=[.23, .34], scale=1, rotation_degrees=0), pose]
        results = rank_native_poses(self.session, candidates, rules, max_candidates=2)
        self.assertEqual(results[0]['candidate_index'], 1)
        self.assertTrue(results[0]['predicted_accepted'])
        with self.assertRaises(ValueError):
            rank_native_poses(self.session, candidates, rules, max_candidates=1)

    def test_invalid_pose_and_guard_stop(self):
        rules = [dict(enabled=True, exact=True, colors=['#000000'], tolerance=0)] * 3
        for pose in [dict(position=[0, 0], scale=0, rotation_degrees=0),
                     dict(position=[np.nan, 0], scale=1, rotation_degrees=0),
                     dict(position=[0, 0], scale=1, rotation_degrees=np.inf)]:
            with self.assertRaises(ValueError):
                score_native_pose(self.session, pose, rules)
        def stop():
            raise InterruptedError('F9')
        with self.assertRaises(InterruptedError):
            rank_native_poses(self.session, [self.session['initial_pose']], rules, check=stop)


if __name__ == '__main__':
    unittest.main()
