import unittest
import numpy as np
from hex_refinement import RefinementLimits, refine_hex, score_codes,refinement_translation


def rules(exact=False,tolerance=1):
    return [dict(enabled=True,colors=['#646464'],exact=exact,tolerance=tolerance) for _ in range(3)]


def gray(value):
    value=int(np.clip(round(value),0,255))
    return '#%02X%02X%02X'%(value,value,value)


class SyntheticAdapter:
    def __init__(self,surface=None,gain=.8):
        self.pose=np.zeros(2);self.now=0.;self.gain=gain;self.moves=[];self.reads=0
        self.released=False;self.scale=1.;self.ctx='session';self.stopped=False
        self.surface=surface or (lambda p:[gray(100+40*(p[0]-.5)),
                                           gray(100+40*(p[1]+.25)),
                                           gray(100+20*(p[0]+p[1]-.25))])
    def check(self):
        if self.stopped:raise RuntimeError('stop/focus/geometry guard')
    def context(self):return self.ctx
    def marker_points(self):return [[80,350],[250,250],[420,360]]
    def capture(self):self.now+=.02;return self.pose.copy()
    def motion(self,a,b):
        return dict(matrix=[[self.scale,0,b[0]-a[0]],[0,self.scale,b[1]-a[1]]],
                    scale=self.scale,angle=0)
    def nudge(self,dx,dy):
        self.moves.append((dx,dy));self.pose+=np.array([dx,dy])*self.gain;self.now+=.1
    def read_codes(self,frame):self.reads+=1;self.now+=.03;return self.surface(frame)
    def pause(self,s):self.now+=s
    def release(self):self.released=True


class RefinementTests(unittest.TestCase):
    def run_refinement(self,adapter,**kwargs):
        return refine_hex(adapter,kwargs.pop('target_rules',rules()),
                          kwargs.pop('deadline',100.),clock=lambda:adapter.now,**kwargs)

    def test_measured_search_improves_all_regions_with_undertravel(self):
        adapter=SyntheticAdapter()
        limits=RefinementLimits(max_trials=20,pose_tolerance=.006)
        result=self.run_refinement(adapter,limits=limits)
        self.assertTrue(result['accepted'],result)
        self.assertTrue(result['kept_best']);self.assertTrue(adapter.released)
        self.assertLess(result['current']['rank'],result['history'][0]['rank'])
        self.assertTrue(all(max(abs(x),abs(y))<=limits.max_command for x,y in adapter.moves))
        self.assertGreater(len(adapter.moves),result['trials'])
        np.testing.assert_allclose(result['current']['pose'],adapter.pose)

    def test_all_three_regions_affect_rank_and_acceptance(self):
        target_rules=rules(tolerance=5)
        balanced=score_codes(['#666666']*3,target_rules)
        r2_only=score_codes(['#FFFFFF','#646464','#FFFFFF'],target_rules)
        self.assertTrue(balanced['accepted']);self.assertFalse(r2_only['accepted'])
        self.assertLess(balanced['rank'],r2_only['rank'])

    def test_tolerance_acceptance_still_searches_for_closer_colors(self):
        adapter=SyntheticAdapter(lambda p:[gray(104-16*p[0])]*3,gain=1.)
        result=self.run_refinement(adapter,target_rules=rules(tolerance=5))
        self.assertTrue(result['history'][0]['accepted'])
        self.assertGreater(len(adapter.moves),0)
        self.assertTrue(result['current']['target_exact'])
        self.assertEqual(result['reason'],'target_exact')

    def test_exact_rule_does_not_accept_nearby_color(self):
        self.assertFalse(score_codes(['#656464']*3,rules(exact=True))['accepted'])
        self.assertTrue(score_codes(['#646464']*3,rules(exact=True))['accepted'])
        target_rules=rules();target_rules[1]['enabled']=False
        self.assertTrue(score_codes(['#646464',None,'#646464'],target_rules)['accepted'])

    def test_verified_best_is_restored_after_worse_trials(self):
        adapter=SyntheticAdapter(lambda p:[gray(110+50*np.linalg.norm(p))]*3,gain=1.)
        result=self.run_refinement(adapter,limits=RefinementLimits(max_trials=3))
        self.assertEqual(result['trials'],3);self.assertFalse(result['accepted'])
        self.assertTrue(result['kept_best']);self.assertTrue(result['current_verified'])
        np.testing.assert_allclose(adapter.pose,[0,0],atol=.001)

    def test_short_budget_preserves_verified_start_without_exploration(self):
        adapter=SyntheticAdapter()
        result=self.run_refinement(adapter,deadline=3.)
        self.assertEqual(adapter.moves,[]);self.assertEqual(result['reason'],'return_reserve')
        self.assertTrue(result['kept_best'])

    def test_expired_budget_sends_no_move_and_makes_no_best_claim(self):
        adapter=SyntheticAdapter();result=self.run_refinement(adapter,deadline=0.)
        self.assertEqual(adapter.moves,[]);self.assertFalse(result['kept_best'])
        self.assertFalse(result['current_verified']);self.assertTrue(adapter.released)

    def test_missing_or_unstable_ocr_stops_without_moves(self):
        for unstable in (False,True):
            adapter=SyntheticAdapter()
            adapter.surface=lambda p:[None,'#646464','#646464'] if not unstable or adapter.reads%2 else ['#646464']*3
            result=self.run_refinement(adapter)
            self.assertEqual(adapter.moves,[]);self.assertEqual(result['reason'],'stopped')
            self.assertFalse(result['accepted']);self.assertTrue(adapter.released)

    def test_failed_motion_stops_after_first_command_without_blind_return(self):
        adapter=SyntheticAdapter(gain=0.)
        result=self.run_refinement(adapter)
        self.assertEqual(len(adapter.moves),1)
        self.assertIn('no measurable motion',result['error'])
        self.assertFalse(result['kept_best']);self.assertFalse(result['current_verified'])

    def test_stop_after_command_cannot_claim_or_restore_historical_best(self):
        adapter=SyntheticAdapter();original=adapter.nudge
        def stop(dx,dy):original(dx,dy);adapter.stopped=True
        adapter.nudge=stop
        result=self.run_refinement(adapter)
        self.assertEqual(len(adapter.moves),1);self.assertFalse(result['kept_best'])
        self.assertIsNotNone(result['best_observed']);self.assertIsNone(result['current'])

    def test_scale_change_is_not_silently_treated_as_translation(self):
        adapter=SyntheticAdapter();original=adapter.nudge
        def zoom(dx,dy):original(dx,dy);adapter.scale=1.01
        adapter.nudge=zoom;result=self.run_refinement(adapter)
        self.assertEqual(len(adapter.moves),1);self.assertFalse(result['kept_best'])
        self.assertIn('Scale or rotation',result['error'])

    def test_changed_context_stops_input(self):
        adapter=SyntheticAdapter();original=adapter.nudge
        def change(dx,dy):original(dx,dy);adapter.ctx='another session'
        adapter.nudge=change;result=self.run_refinement(adapter)
        self.assertEqual(len(adapter.moves),1);self.assertIn('geometry',result['error'])

    def test_actual_delay_exhausts_budget_without_unsafe_return(self):
        adapter=SyntheticAdapter();original=adapter.nudge
        def slow(dx,dy):original(dx,dy);adapter.now+=20
        adapter.nudge=slow;result=self.run_refinement(adapter,deadline=15.)
        self.assertEqual(len(adapter.moves),1);self.assertIn('deadline',result['error'])
        self.assertFalse(result['kept_best']);self.assertIsNone(result['current'])

    def test_small_scale_change_that_separates_markers_is_rejected(self):
        points=np.array([[80,350],[250,250],[420,360]])
        motion=dict(matrix=[[1.001,0,.2],[0,1.001,0]],scale=1.001,angle=0)
        with self.assertRaisesRegex(RuntimeError,'three-marker'):
            refinement_translation(motion,points,.035)
        motion=dict(matrix=[[1,0,.2],[0,1,-.3]],scale=1,angle=0)
        np.testing.assert_allclose(refinement_translation(motion,points,.035),[.2,-.3])

    def test_missing_marker_geometry_prevents_exploration(self):
        adapter=SyntheticAdapter();adapter.marker_points=lambda:[[0,0]]
        result=self.run_refinement(adapter)
        self.assertEqual(adapter.moves,[]);self.assertIn('marker points',result['error'])

    def test_return_must_reproduce_hex_not_just_position(self):
        adapter=SyntheticAdapter(lambda p:[gray(110+50*np.linalg.norm(p))]*3,gain=1.)
        original=adapter.nudge
        def drift(dx,dy):
            original(dx,dy)
            if len(adapter.moves)==2:adapter.surface=lambda p:['#787878']*3
        adapter.nudge=drift
        result=self.run_refinement(adapter,limits=RefinementLimits(max_trials=1))
        self.assertIn('reproduce best HEX',result['error']);self.assertFalse(result['kept_best'])


if __name__=='__main__':unittest.main()
