"""An ordinary missed return must spend live recovery time, not abandon colour."""
import copy
import itertools
import unittest
from unittest.mock import patch
import numpy as np

import test_refinement_retention as retention


class RecoveryRankingTests(unittest.TestCase):
    def test_closest_return_preserves_high_priority_hits_before_error_tradeoffs(self):
        from refinement_policy import recovery_rank
        rules=retention.black_rules();baseline=['#000000','#000000','#505050']
        loses_hits=['#010101','#010101','#505050']
        keeps_hits=['#000000','#000000','#606060']
        self.assertLess(recovery_rank(keeps_hits,baseline,rules),recovery_rank(loses_hits,baseline,rules))


class ScreenshotRecoveryTests(unittest.TestCase):
    controller=retention.ScreenshotRetentionTests.controller

    def test_fourth_return_can_recover_after_three_missed_landings(self):
        baseline=['#020202','#505050','#808080'];bad=['#FFFFFF']*3
        with self.controller(retention.black_rules(),iter([baseline,bad,bad,bad,bad,baseline])) as c:
            c.refinement_anchor=c.best;c.observe('trial')
            def move(matrix,*a,**kw):
                c.pose=np.asarray(matrix).copy();c.actions.append(dict(name='return'));return True
            c.move_to=move
            c.fine_shift=lambda *a,**kw:c.actions.append(dict(name='correct'))
            result=c.restore()
            self.assertEqual(result['actual_colors'],baseline)
            self.assertTrue(c.at_least_best(result,c.best))

    def test_motionless_geometry_miss_switches_to_real_colour_correction(self):
        baseline=['#020202','#505050','#808080'];bad=['#FFFFFF']*3;corrected=[]
        def readings():
            yield baseline
            while not corrected:yield bad
            while True:yield baseline
        with self.controller(retention.black_rules(),readings()) as c:
            c.refinement_anchor=c.best;c.observe('trial')
            c.move_to=lambda *a,**kw:True
            def correct(shift,*a,**kw):
                corrected.append(shift);c.pose[:2,2]+=shift;c.actions.append(dict(name='correct'))
            c.fine_shift=correct
            result=c.restore()
            self.assertTrue(corrected)
            self.assertEqual(result['actual_colors'],baseline)

    def test_unknown_pose_return_remeasures_instead_of_ending_at_bad_colour(self):
        baseline=['#020202','#505050','#808080'];bad=['#FFFFFF']*3
        with self.controller(retention.black_rules(),iter([baseline,bad,bad,baseline])) as c:
            c.refinement_anchor=c.best;c.observe('trial');c.pose_known=False
            matches=iter([(None,{}),(np.eye(3),{})]);c.register=lambda *a:next(matches)
            c.fine_shift=lambda *a,**kw:None
            result=c.restore()
            self.assertEqual(result['actual_colors'],baseline)

    def test_recovery_keeps_time_to_return_to_its_closest_measured_landing(self):
        baseline=['#020202','#505050','#808080'];bad=['#FFFFFF']*3
        closer=['#202020','#606060','#909090'];worse=['#AAAAAA']*3
        actual=[baseline];now=[0.];moves=[]
        def readings():
            while True:yield actual[0]
        with patch('screenshot_control.time.monotonic',side_effect=lambda:now[0]), \
                self.controller(retention.black_rules(),readings()) as c:
            c.refinement_anchor=c.best;c.return_cost=lambda *a,**kw:3.
            c.refresh_timer=lambda *a:None;actual[0]=bad;c.observe('trial')
            def move(matrix,label='return-best',**kw):
                moves.append(label);c.actions.append(dict(name=label))
                c.pose=np.asarray(matrix).copy()
                if label=='return-recovery-best':actual[0]=closer
                else:
                    actual[0]=closer if len(moves)==1 else worse
                    c.pose[0,2]+=.1*len(moves)
                    if len(moves)>=2:now[0]=111.+len(moves)
                return True
            c.move_to=move
            def fine(shift,*a,**kw):c.pose[:2,2]+=shift
            c.fine_shift=fine
            result=c.restore()
            self.assertEqual(result['actual_colors'],closer)
            self.assertIn('return-recovery-best',moves)
            self.assertEqual(c.best['actual_colors'],baseline)
            # Outer finish/exception callers may invoke restore again. They
            # must not spend the held return allowance on another risky probe.
            again=c.restore()
            self.assertEqual(again['actual_colors'],closer)

    def test_f9_during_extended_return_never_sends_another_correction(self):
        from platform_win import Interrupted
        baseline=['#020202','#505050','#808080'];bad=['#FFFFFF']*3
        with self.controller(retention.black_rules(),itertools.chain([baseline],itertools.repeat(bad))) as c:
            c.refinement_anchor=c.best;c.observe('trial');c.move_to=lambda *a,**kw:True
            sent=[]
            def correct(*a,**kw):
                sent.append(True);c.owner.stop.set()
            c.fine_shift=correct
            def check():
                if c.owner.stop.is_set():raise Interrupted('F9',reason='user_stop')
            c.check=check
            with self.assertRaises(Interrupted):c.restore()
            self.assertEqual(sent,[True])


class NativeRecoveryTests(unittest.TestCase):
    fixtures=retention.NativeRetentionTests.fixtures
    setUp=fixtures.ProtectedRefinementControllerTests.setUp
    candidate=fixtures.ProtectedRefinementControllerTests.candidate
    plan=fixtures.ProtectedRefinementControllerTests.plan
    refine=fixtures.ProtectedRefinementControllerTests.refine
    recover=fixtures.ProtectedRefinementControllerTests.recover
    run_loop=fixtures.ProtectedRefinementControllerTests.run_loop

    def test_recovery_planner_skips_an_unaffordable_return_and_finds_short_one(self):
        from native_input_compile import native_drag_gesture
        from native_live.same_session_dye_planner import bind_planning_context
        from native_live.retry_recovery import prepare_retry_recovery
        from native_input_response import replay_native_route
        from native_palette_scoring import score_native_pose
        io=self.io
        context=bind_planning_context(io.session,io.cp,io.geometry,io.settings,wheel_delta_per_step=1.,
            calibration_evidence=dict(source='offline_test',viewport_origin=[0,0],viewport_scale=[1,1],
                backend_during_actions_synchronously_recorded=True))
        drag=lambda x:native_drag_gesture(io.geometry,io.settings,x,0).record()
        pose=replay_native_route(io.pose,[drag(-5)],io.geometry,io.settings,
            wheel_delta_per_step=1.,sample_policy='all_recorded_points')['final_pose']
        actual=dict(io.cp,pose=pose,client_hex=score_native_pose(io.session,pose,self.rules)['colors'])
        seen=[]
        def admit(row):seen.append(len(row['input_route']));return len(row['input_route'])==1
        row=prepare_retry_recovery(context,actual,io.cp,self.rules,deadline=20.,clock=io.clock,
            preferred_routes=[[drag(5),drag(1),drag(-1)],[drag(5)]],
            preserve_regions=True,admit=admit)
        self.assertIsNotNone(row)
        self.assertEqual(len(row['input_route']),1)
        self.assertIn(3,seen)

    def test_two_failed_returns_do_not_end_a_live_round_with_bad_colours(self):
        from native_input_compile import native_drag_gesture
        from native_input_response import replay_native_route
        original=self.io.perform_candidate
        bad=replay_native_route(self.baseline,
            [native_drag_gesture(self.io.geometry,self.io.settings,-5,0).record()],
            self.io.geometry,self.io.settings,wheel_delta_per_step=1.,
            sample_policy='all_recorded_points')['final_pose']
        def disturbed(record,label,deadline):
            receipt=original(record,label,deadline)
            if len(self.io.actions)<=3:self.io.pose=copy.deepcopy(bad)
            return receipt
        self.io.perform_candidate=disturbed
        result=self.run_loop()
        self.assertGreaterEqual(len(self.io.actions),4,result.get('error'))
        self.assertTrue(result['best_current'],result.get('error'))
        self.assertEqual(result['actual_colors'],result['best_actual_colors'])

    def test_unavailable_original_return_keeps_a_better_measured_recovery_landing(self):
        from native_input_compile import native_drag_gesture
        from native_input_response import replay_native_route
        from native_palette_scoring import score_native_pose
        from native_live.retry_recovery import prepare_retry_recovery
        original=self.io.perform_candidate
        def endpoint(dx):
            return replay_native_route(self.baseline,
                [native_drag_gesture(self.io.geometry,self.io.settings,dx,0).record()],
                self.io.geometry,self.io.settings,wheel_delta_per_step=1.,
                sample_policy='all_recorded_points')['final_pose']
        bad=endpoint(-8);near=endpoint(-1)
        expected=score_native_pose(self.io.session,near,self.rules)['colors']
        def disturbed(record,label,deadline):
            receipt=original(record,label,deadline)
            if len(self.io.actions)==2:self.io.pose=copy.deepcopy(near)
            elif len(self.io.actions)<=3:self.io.pose=copy.deepcopy(bad)
            return receipt
        self.io.perform_candidate=disturbed
        initial=list(self.io.cp['client_hex'])
        def unavailable(context,cp,anchor,*args,**kw):
            if anchor['client_hex']==initial:
                self.io.t+=1.;return None
            return prepare_retry_recovery(context,cp,anchor,*args,**kw)
        with patch('native_live.controller.prepare_retry_recovery',side_effect=unavailable):
            result=self.run_loop()
        self.assertGreaterEqual(len(self.io.actions),4)
        self.assertEqual(result['actual_colors'],expected,result.get('error'))
        self.assertTrue(result['screenshot_verified'])
        self.assertFalse(result['best_current'])

    def test_repeated_anchor_misses_reserve_a_return_to_best_recovery_landing(self):
        self._repeated_anchor_misses()

    def test_recovery_reserve_retains_all_checkpoint_hex_with_disabled_region(self):
        self._repeated_anchor_misses(disabled=True)

    def test_trial_landing_is_kept_before_native_return_rebind_discards_frames(self):
        self._repeated_anchor_misses(trial=True)

    def _repeated_anchor_misses(self,disabled=False,trial=False):
        from native_input_compile import native_drag_gesture
        from native_input_response import replay_native_route
        from native_palette_scoring import score_native_pose
        self.rules=[dict(rule,priority=i+1) for i,rule in enumerate(self.rules)]
        if disabled:self.rules[2]['enabled']=False
        def endpoint(dx):
            return replay_native_route(self.baseline,
                [native_drag_gesture(self.io.geometry,self.io.settings,dx,0).record()],
                self.io.geometry,self.io.settings,wheel_delta_per_step=1.,
                sample_policy='all_recorded_points')['final_pose']
        near,bad=endpoint(-1),endpoint(-8)
        expected=score_native_pose(self.io.session,near,self.rules)['colors']
        perform=self.io.perform_candidate
        def disturbed(record,label,deadline):
            receipt=perform(record,label,deadline)
            landed=score_native_pose(self.io.session,self.io.pose,self.rules)['colors']
            if len(self.io.actions)==(1 if trial else 2):self.io.pose=copy.deepcopy(near)
            elif landed!=expected:self.io.pose=copy.deepcopy(bad)
            return receipt
        self.io.perform_candidate=disturbed
        def planned(context,cp,anchor,rules,**kw):
            self.io.t+=1.
            row=self.recover(context,cp,anchor,rules)
            return row if kw.get('admit') is None or kw['admit'](row) else None
        with patch('native_live.controller.prepare_retry_recovery',side_effect=planned):
            result=self.run_loop(deadline=50.,max_actions=5)
        self.assertEqual(result['actual_colors'][:2] if disabled else result['actual_colors'],
            expected[:2] if disabled else expected,result.get('failure_recovery'))
        self.assertTrue(result['verified'])
        self.assertTrue(result['screenshot_verified'])
        self.assertFalse(result['best_current'])
        self.assertLessEqual(result['actual_input_attempts'],5)

    def test_finite_anchor_search_miss_keeps_computing_safely_from_nearest_landing(self):
        initial=list(self.io.cp['client_hex']);calls=[]
        def finite(context,cp,anchor,rules,**kw):
            self.io.t+=1.
            if anchor['client_hex']==initial:
                calls.append(self.io.t)
                return self.recover(context,cp,anchor,rules) if len(calls)>2 else None
            return self.recover(context,cp,anchor,rules)
        self.rules=[dict(rule,priority=i+1) for i,rule in enumerate(self.rules)]
        # This existing fixture enters recovery and visits a better real landing.
        from native_input_compile import native_drag_gesture
        from native_input_response import replay_native_route
        perform=self.io.perform_candidate
        def endpoint(dx):
            return replay_native_route(self.baseline,
                [native_drag_gesture(self.io.geometry,self.io.settings,dx,0).record()],
                self.io.geometry,self.io.settings,wheel_delta_per_step=1.,
                sample_policy='all_recorded_points')['final_pose']
        bad,near=endpoint(-8),endpoint(-1)
        def disturbed(record,label,deadline):
            receipt=perform(record,label,deadline)
            if len(self.io.actions)==2:self.io.pose=copy.deepcopy(near)
            elif len(self.io.actions)<=3:self.io.pose=copy.deepcopy(bad)
            return receipt
        self.io.perform_candidate=disturbed
        with patch('native_live.controller.prepare_retry_recovery',side_effect=finite):
            result=self.run_loop(deadline=90.,max_actions=64)
        self.assertGreater(len(calls),2)
        self.assertTrue(result['best_current'],result.get('failure_recovery'))

    def test_f9_during_expanded_recovery_still_prevents_the_next_input(self):
        from native_input_compile import native_drag_gesture
        from native_input_response import replay_native_route
        original=self.io.perform_candidate
        bad=replay_native_route(self.baseline,
            [native_drag_gesture(self.io.geometry,self.io.settings,-5,0).record()],
            self.io.geometry,self.io.settings,wheel_delta_per_step=1.,
            sample_policy='all_recorded_points')['final_pose']
        def stopped(record,label,deadline):
            receipt=original(record,label,deadline)
            if len(self.io.actions)<=3:self.io.pose=copy.deepcopy(bad)
            else:self.io.cancel=True
            return receipt
        self.io.perform_candidate=stopped
        result=self.run_loop()
        self.assertEqual(len(self.io.actions),4)
        self.assertEqual(result['stop_reason'],'interrupted')
        self.assertFalse(result['verified'])

    def test_one_recovery_read_timeout_does_not_abandon_the_round(self):
        checkpoint=self.io.checkpoint;failed=[]
        def read(label,deadline):
            if label.startswith('failure_return_') and not failed:
                failed.append(label);self.io.t+=.5;raise TimeoutError('one transient read timeout')
            return checkpoint(label,deadline)
        self.io.checkpoint=read
        self.test_two_failed_returns_do_not_end_a_live_round_with_bad_colours()
        self.assertTrue(failed)


if __name__=='__main__':unittest.main()
