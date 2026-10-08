import unittest
from atlas_budget_review import subset_indices
from live_atlas_capture import grid_scan_plan
from micro_return_review import audit_geometry
from progressive_atlas_replay import anchor_first_indices


class BudgetReviewTests(unittest.TestCase):
    def test_subsets_keep_every_holdout_and_never_train_on_it(self):
        log=[dict(kind='frame',name='max_sampling')]
        for i,action in enumerate(grid_scan_plan((0,0,500,500)),1):
            log.extend([dict(kind='frame',name=f'grid_{i:03d}'),dict(kind='command',**action)])
        for variant in ('full','columns_02467','rows_024','rows_0234'):
            training,holdout,retained=subset_indices(log,variant)
            self.assertEqual(holdout,[9,16,24,33,39,45])
            self.assertFalse(set(training)&set(holdout))
            self.assertEqual(sorted(training+holdout),retained)
        self.assertEqual(len(subset_indices(log,'full')[0]),43)

    def test_affine_audit_distinguishes_translation_and_scale_drift(self):
        points=[[0,0],[10,0],[20,0]]
        rows=[dict(frame='a',points=points,matrix=[[1,0,0],[0,1,0]]),
              dict(frame='b',points=[[-1,0],[9,0],[19,0]],matrix=[[1,0,1],[0,1,0]]),
              dict(frame='c',points=[[-1,0],[8.9,0],[18.8,0]],matrix=[[1.01,0,1],[0,1.01,0]])]
        result=audit_geometry(rows,{k:['#000000']*3 for k in ('a','b','c')})
        self.assertEqual(result['rows'][1]['maximum_translation_model_residual'],0)
        self.assertGreater(result['rows'][2]['maximum_translation_model_residual'],.035)
        self.assertFalse(result['return_validated'])

    def test_anchor_replay_retains_complete_contiguous_route_without_claiming_capture_savings(self):
        log=[dict(kind='frame',name='max_sampling')]
        for i,action in enumerate(grid_scan_plan((0,0,500,500)),1):
            log.extend([dict(kind='frame',name=f'grid_{i:03d}'),dict(kind='command',**action)])
        training,holdout,retained=anchor_first_indices(log)
        self.assertEqual(holdout,[9,16,24,33,39,45])
        self.assertFalse(set(training)&set(holdout))
        self.assertEqual(sorted(training+holdout),retained)
        # Current replay needs every intermediate registration frame and the
        # return tail. It is a full-route reference, not a shorter live scan.
        self.assertEqual(retained, list(range(49)))
        self.assertEqual(training, subset_indices(log, 'full')[0])
        commands = [row for row in log if row['kind'] == 'command']
        self.assertTrue(all(abs(row['dx']) <= 100 and abs(row['dy']) <= 200
                            for row in commands))


if __name__=='__main__':unittest.main()
