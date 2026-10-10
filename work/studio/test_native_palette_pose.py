from test_support import read_local_fixture_text
from test_support import load_local_palette_session
import json
import unittest
from pathlib import Path
import numpy as np
from native_palette_model import view_uv
from native_palette_scoring import load_session, score_native_pose
from native_palette_pose import native_to_board, relative_board_pose, board_to_native, score_board_pose

ROOT = Path(__file__).parent / 'fixtures' / 'native_palette'


class NativePalettePoseTests(unittest.TestCase):
    def test_translation_y_flip_and_rotation_sign(self):
        board = [100, 200, 630, 730]
        pose = dict(position=[.1, .2], scale=1, rotation_degrees=0)
        matrix = native_to_board(pose, board)
        np.testing.assert_allclose(matrix, [[530, 0, 318], [0, -530, 159], [0, 0, 1]], atol=1e-5)
        relative = relative_board_pose(pose, dict(position=[0, 0], scale=1, rotation_degrees=0), board)
        np.testing.assert_allclose(relative[:2, 2], [53, -106], atol=1e-5)
        rotated = relative_board_pose(dict(pose, rotation_degrees=90), pose, board)
        self.assertLess(rotated[1, 0], 0)

    def test_relative_matrix_preserves_native_query_coordinates(self):
        board = [100, 200, 630, 730]
        reference = dict(position=[.07, -.09], scale=1.3, rotation_degrees=23)
        target = dict(position=[-.196, .013], scale=.99, rotation_degrees=-1.03)
        relative = relative_board_pose(target, reference, board)
        points = np.array([[13., 71.], [290., 220.], [490., 510.]])
        source = (np.c_[points, np.ones(3)] @ np.linalg.inv(relative).T)[:, :2]
        def uv(p):
            return np.c_[p[:, 0] / 530, 1 - p[:, 1] / 530]
        np.testing.assert_allclose(view_uv(uv(points), **target), view_uv(uv(source), **reference), atol=3e-7)
        recovered = board_to_native(relative, reference, board)
        np.testing.assert_allclose(recovered['position'], target['position'], atol=1e-7)
        self.assertAlmostEqual(recovered['scale'], target['scale'], places=7)
        self.assertAlmostEqual(recovered['rotation_degrees'], target['rotation_degrees'], places=6)

    def test_all_recorded_poses_score_identically_through_adapter(self):
        names = json.loads(read_local_fixture_text(ROOT / 'manifest.json'))['snapshots'][1:]
        session = load_local_palette_session(ROOT / names[0])
        board = [757, 428, 1287, 958]
        rules = [dict(enabled=True, exact=True, colors=['#000000'], tolerance=0)] * 3
        for name in names:
            target = load_local_palette_session(ROOT / name)['initial_pose']
            relative = relative_board_pose(target, session['initial_pose'], board)
            direct = score_native_pose(session, target, rules)
            adapted = score_board_pose(session, relative, session['initial_pose'], board, rules)
            self.assertEqual(adapted['colors'], direct['colors'])
            self.assertFalse(adapted['execution_verified'])

    def test_reject_rectangular_or_invalid_geometry_and_non_similarity(self):
        pose = dict(position=[0, 0], scale=1, rotation_degrees=0)
        for board in [[0, 0, 530, 400], [0, 0, 0, 0], [0, 0, np.inf, 530]]:
            with self.assertRaises(ValueError):
                relative_board_pose(pose, pose, board)
        with self.assertRaises(ValueError):
            board_to_native([[1, .2, 0], [0, 1, 0]], pose, [0, 0, 530, 530])

    def test_live_float32_square_roundoff_can_compile_and_roundtrip(self):
        board=[713.5999755859375,428.7999267578125,1212.7999267578125,927.9999694824219]
        reference=dict(position=[0,0],scale=1,rotation_degrees=0)
        target=dict(position=[.02,-.01],scale=.99,rotation_degrees=1.)
        relative=relative_board_pose(target,reference,board)
        recovered=board_to_native(relative,reference,board)
        np.testing.assert_allclose(recovered['position'],target['position'],atol=1e-7)
        self.assertAlmostEqual(recovered['scale'],.99,places=7)
        self.assertAlmostEqual(recovered['rotation_degrees'],1.,places=6)
        # The adapter must provide an actual similarity, not a tiny shear.
        self.assertAlmostEqual(relative[0,0],relative[1,1],places=12)
        self.assertAlmostEqual(relative[0,1],-relative[1,0],places=12)

    def test_submillipixel_tolerance_cannot_admit_physical_rectangles(self):
        pose=dict(position=[0,0],scale=1,rotation_degrees=0)
        for board in ([0,0,499.2,499.202],[0,0,10000,10000.01]):
            with self.assertRaises(ValueError):relative_board_pose(pose,pose,board)


if __name__ == '__main__':
    unittest.main()
