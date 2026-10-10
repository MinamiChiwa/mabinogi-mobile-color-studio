"""Periodic target solutions must not inherit the local action neighborhood."""
from test_support import load_local_palette_session
import unittest
from pathlib import Path
import numpy as np
from native_palette_scoring import score_native_pose


class PeriodicSearchTests(unittest.TestCase):
    def session(self):
        a=np.full((32,32,3),180,np.uint8);b=a.copy()
        a[11,25]=0;b[12,5]=0
        return dict(pixels=(a,b,a),picker_uv=[[1/6,.25],[.5,.26],[5/6,.2]],
            color_preserve_ratio=0.,initial_pose=dict(position=[0.,0.],scale=1.,rotation_degrees=0.),
            capture_id='periodic-test')

    def rules(self):
        return [dict(enabled=i<2,exact=True,colors=['#000000'] if i<2 else [],tolerance=0.) for i in range(3)]

    def search(self,session=None,rules=None,**kwargs):
        from native_periodic_search import search_periodic_targets
        return search_periodic_targets(session or self.session(),rules or self.rules(),
            minimum_scale=.5,maximum_scale=3.,**kwargs)

    def test_two_targets_are_solved_outside_the_micro_scale_grid(self):
        result=self.search()
        self.assertTrue(result['candidates'])
        row=result['candidates'][0]
        self.assertTrue(score_native_pose(self.session(),row['native_pose'],self.rules())['predicted_accepted'])
        self.assertGreater(abs(row['native_pose']['scale']-1.),.02)
        self.assertFalse(row['execution_verified'])
        self.assertEqual(result['domain']['translation'],'one_full_canonical_period')
        self.assertEqual(result['domain']['scale'],[.5,3.])
        self.assertFalse(result['continuous_complete'])

    def test_rc8_board_keeps_verified_targets_before_pair_enumeration_deadline(self):
        from native_palette_scoring import load_session
        session=load_local_palette_session(Path(__file__).parent/'fixtures/native_live/rc8_double_black/palette')
        ticks=[0.]
        def charged_check():ticks[0]+=.0002
        result=self.search(session,subpixel_fractions=(0.,.5),time_budget_seconds=.05,
            clock=lambda:ticks[0],check=charged_check)
        self.assertTrue(result['candidates'],'Pair enumeration consumed the budget before verifying any target')
        self.assertGreater(result['cpu_evaluations'],0)
        for row in result['candidates']:
            self.assertEqual(score_native_pose(session,row['native_pose'],self.rules())['colors'][:2],['#000000']*2)

    def test_rc9_triple_targets_are_checked_before_movement_cost_pruning(self):
        from native_palette_scoring import load_session
        session=load_local_palette_session(Path(__file__).parent/'fixtures/native_live/rc9_triple_black/palette')
        rules=[dict(enabled=True,exact=True,colors=['#000000'],tolerance=0.) for _ in range(3)]
        result=self.search(session,rules,subpixel_fractions=(0.,.5),time_budget_seconds=3.)
        self.assertTrue(result['candidates'],'A cost-pruned double-target pool hid exact triple-target intersections')
        for row in result['candidates']:
            self.assertEqual(score_native_pose(session,row['native_pose'],rules)['colors'],['#000000']*3)

    def test_all_black_sites_are_counted_without_a_nearest_eight_pixel_cutoff(self):
        session=self.session()
        pixels=np.zeros((32,32,3),np.uint8)
        session['pixels']=(pixels,pixels,pixels)
        result=self.search(session)
        self.assertEqual(result['target_sites_per_region'][:2],[1024,1024])

    def test_periodic_equivalent_reference_is_verified_in_original_float32_model(self):
        from native_palette_model import predict_hex
        session=self.session()
        result=self.search(session)
        pose=result['candidates'][0]['native_pose']
        session['initial_pose']=pose
        again=self.search(session)
        for row in again['candidates']:
            self.assertTrue(score_native_pose(session,row['native_pose'],self.rules())['predicted_accepted'])

    def test_third_enabled_picker_must_also_pass_exact_verification(self):
        rules=[dict(enabled=True,exact=True,colors=['#010203'],tolerance=0.)]*3
        result=self.search(rules=rules)
        self.assertEqual(result['candidates'],[])
        self.assertFalse(result['continuous_complete'])
        self.assertEqual(result['stop_reason'],'target_not_present_on_sample_lattice')

    def test_deadline_and_cancel_preserve_partial_coverage(self):
        ticks=iter([0.,2.,2.,2.])
        result=self.search(time_budget_seconds=1.,clock=lambda:next(ticks,2.))
        self.assertEqual(result['stop_reason'],'deadline')
        self.assertFalse(result['site_scan_complete'])
        def cancel():raise InterruptedError('F9')
        with self.assertRaises(InterruptedError):self.search(check=cancel)

    def test_search_reports_enabled_regions_and_nearest_model_pose_when_exact_is_absent(self):
        rules=[dict(enabled=True,exact=True,colors=['#000000'],tolerance=0.)]*3
        result=self.search(rules=rules,time_budget_seconds=3.)
        self.assertEqual(result['enabled_regions'],[0,1,2])
        self.assertFalse(result['candidates'])
        self.assertIn('nearest_prediction',result)
        self.assertEqual(len(result['nearest_prediction']['colors']),3)


if __name__=='__main__':unittest.main()
