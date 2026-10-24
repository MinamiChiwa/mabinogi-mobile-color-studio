import unittest
import numpy as np

from atlas_mask_route_review import supplemental_positions, _support
from atlas_masks import material_masks
from live_atlas_capture import grid_scan_plan, coverage_fill_positions


class MaskRouteReviewTests(unittest.TestCase):
    def test_supplemental_positions_break_the_base_scan_aliases(self):
        positions=supplemental_positions((100,200,600,700))
        self.assertEqual([row['translation'] for row in positions],
                         [[50,0],[450,0],[650,0],[250,400]])
        self.assertTrue(all(row['translation'][0] % 100 != 0 for row in positions))

    def test_capture_plan_uses_the_same_supplemental_offsets_as_the_diagnostic(self):
        plan=grid_scan_plan((100,200,600,700),row_stagger=0.)
        x=y=0;actual=[]
        for step in plan:
            x+=step['dx'];y+=step['dy']
            if step['supplemental_kind']=='marker_column_fill':actual.append([x,y])
        self.assertEqual(actual,[row['translation'] for row in supplemental_positions((100,200,600,700))])

    def test_coverage_fill_positions_are_present_as_bounded_route_detours(self):
        board=(0,0,498,498)
        plan=grid_scan_plan(board,row_stagger=.05)
        x=y=0;actual=[]
        for step in plan:
            x+=step['dx'];y+=step['dy']
            if step['supplemental_kind']=='coverage_fill':actual.append([x,y])
            self.assertLessEqual(abs(step['dx']),100)
            self.assertLessEqual(abs(step['dy']),200)
        self.assertEqual(sorted(map(tuple,actual)),
                         sorted((p['x'],p['y']) for p in coverage_fill_positions(board)))

    def test_full_circle_columns_have_complete_support_for_saved_period(self):
        # Geometry regression for the new mask, not a color or live-motion test.
        # Holdout colors/support stay excluded from the training union.
        scene=dict(board=(0,0,498,498), markers=[(83,397),(249,127),(415,190)])
        masks=material_masks(scene)
        points=[np.zeros(2)]; position=np.zeros(2)
        for step in grid_scan_plan(scene['board'],row_stagger=.05):
            position=position+[step['dx'],step['dy']]
            if not step['holdout']:points.append(position.copy())
        atlas=_support(masks,masks.shape[1:],
                       [[804.8569414366233,0],[0,804.7127029098418]],points,768)
        self.assertTrue((atlas.count>0).all())


if __name__=='__main__':unittest.main()
