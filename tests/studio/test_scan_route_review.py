import unittest
import numpy as np
from atlas_budget_review import subset_indices
from live_atlas_capture import grid_scan_plan
from scan_route_review import commanded_positions, vertical_route, route_actions


class ScanRouteTests(unittest.TestCase):
    def log(self):
        log = [dict(kind='frame', name='max_sampling')]
        for i, action in enumerate(grid_scan_plan((0, 0, 498, 498), row_stagger=.05), 1):
            log.extend([dict(kind='frame', name=f'grid_{i:03d}'), dict(kind='command', **action)])
        return log

    def test_reordering_preserves_every_holdout_and_training_separation(self):
        for variant in ('full', 'rows_024', 'rows_0234', 'columns_02467'):
            train, holdout, retained = subset_indices(self.log(), variant)
            route = vertical_route(retained)
            self.assertEqual(route[0], 0)
            self.assertEqual(sorted(route), retained)
            self.assertFalse(set(train) & set(holdout))
            self.assertEqual(holdout, [9, 16, 24, 33, 39, 45])
        self.assertEqual(vertical_route(list(range(40)))[:10], [0, 15, 16, 31, 32, 33, 30, 17, 14, 1])

    def test_398_pixel_endpoint_gap_requires_two_drags(self):
        actions = route_actions([0, 1], np.array([[0, 0], [0, 398]]), (498, 498, 3))
        self.assertEqual(actions[0]['drag_count'], 2)
        self.assertEqual(actions[0]['unobserved_intermediate_poses'], 1)
        np.testing.assert_array_equal(np.sum(actions[0]['drag_requests'], axis=0), [0, 398])
        self.assertLessEqual(np.max(abs(np.asarray(actions[0]['drag_requests']))), 323)

    def test_stagger_and_reverse_are_kept_as_command_hints(self):
        positions = commanded_positions(self.log())
        # The first pose of row 1 still begins one 5% stagger right of the
        # row-0 endpoint; added row-0 filler poses only change frame indices.
        first_row1=next(i+1 for i,row in enumerate(
            [r for r in self.log() if r.get('kind')=='command'])
            if row.get('row')==1 and row.get('column')==0)
        np.testing.assert_array_equal(positions[first_row1], [725, 199])
        actions = route_actions([0, first_row1, 0], positions, (498, 498, 3))
        self.assertEqual(actions[0]['command_hint'], [725, 199])
        self.assertEqual(actions[1]['command_hint'], [-725, -199])

    def test_malformed_route_is_rejected(self):
        for indices in ([], [1, 2], [0, 1, 1]):
            with self.assertRaises(ValueError):
                vertical_route(indices)


if __name__ == '__main__':
    unittest.main()
