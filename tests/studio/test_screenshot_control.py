import time,threading,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
import numpy as np

class ScreenshotControlTests(unittest.TestCase):
    def test_optional_sampling_yields_before_best_return_reserve(self):
        from screenshot_control import Budget,TimeEnded
        from screenshot_live import _sampling_check
        c=SimpleNamespace(check=lambda:None,owner=SimpleNamespace(consume_retry_request=lambda:False),
            budget=Budget(5,.02),return_cost=lambda:6.)
        with self.assertRaises(TimeEnded):_sampling_check(c)
    def test_release_error_cannot_turn_terminal_interruption_into_recovery(self):
        from screenshot_control import Controller,Budget
        from platform_win import Interrupted
        from unittest.mock import Mock
        owner=SimpleNamespace(stop=threading.Event(),consume_retry_request=lambda:False,
            event=lambda *a,**k:None,folder=Path(tempfile.gettempdir()))
        game=Mock();game.release.side_effect=RuntimeError('cleanup failed')
        c=Controller(owner,game,SimpleNamespace(board=(0,0,20,20),cards=[],markers=[]),[],Budget(120,.4))
        c.frame=np.zeros((20,20,3),np.uint8);c.best=dict(matrix=np.eye(3))
        def failed():raise Interrupted('lost focus')
        with __import__('unittest').mock.patch('screenshot_control.u.GetAsyncKeyState',return_value=0):
            with self.assertRaises(RuntimeError):c.act('interrupted',failed)
            game.release.side_effect=None
            recovery=c.safe_restore('processing_error')
        self.assertFalse(recovery['attempted']);game.capture.assert_not_called()
    def test_terminal_focus_loss_never_recovers_even_if_focus_returns(self):
        from screenshot_control import Controller,Budget
        from platform_win import Interrupted
        from unittest.mock import Mock
        owner=SimpleNamespace(stop=threading.Event(),event=lambda *a,**k:None,folder=Path(tempfile.gettempdir()))
        game=Mock();c=Controller(owner,game,SimpleNamespace(board=(0,0,20,20),cards=[],markers=[]),[],Budget(120,.4))
        c.best=dict(matrix=np.eye(3));c.check=lambda:None
        result=c.safe_restore('interrupted',interruption=Interrupted('lost focus'))
        self.assertEqual(result['blocked'],'terminal_interruption')
        game.capture.assert_not_called();game.move_to.assert_not_called()
    def test_capture_retries_one_flash_without_input(self):
        from screenshot_control import Controller,Budget
        from unittest.mock import Mock,patch
        scene=SimpleNamespace(board=(0,0,20,20),cards=[],markers=[])
        owner=SimpleNamespace(stop=threading.Event(),event=lambda *a,**k:None,folder=Path(tempfile.gettempdir()))
        game=Mock();game.capture.return_value=np.zeros((20,20,3),np.uint8)
        c=Controller(owner,game,scene,[],Budget(120,.4));c.check=lambda:None
        try:
            with patch('screenshot_control.recognize',side_effect=[ValueError('flash'),scene]):c.capture('flash')
            self.assertEqual(game.capture.call_count,2)
            self.assertEqual(c.failed_board_frames,0)
            game.move_to.assert_not_called()
        finally:c.close()

    def test_capture_confirmed_closed_board_requires_three_failures(self):
        from screenshot_control import Controller,Budget,PaletteEnded
        from unittest.mock import Mock,patch
        scene=SimpleNamespace(board=(0,0,20,20),cards=[],markers=[])
        owner=SimpleNamespace(stop=threading.Event(),event=lambda *a,**k:None,folder=Path(tempfile.gettempdir()))
        game=Mock();game.capture.return_value=np.zeros((20,20,3),np.uint8)
        c=Controller(owner,game,scene,[],Budget(120,.4));c.check=lambda:None
        with patch('screenshot_control.recognize',side_effect=ValueError('closed')):
            with self.assertRaises(PaletteEnded):c.capture('closed')
        self.assertEqual(game.capture.call_count,3)

    def test_cost_estimates_include_compute_and_do_not_change_actual_deadline(self):
        from screenshot_control import Budget
        budget=Budget(120,.5,now=100)
        for seconds in (1.,1.1,1.2,20.):budget.record_cost('registration',seconds)
        self.assertLess(budget.estimate('registration'),2.)
        self.assertGreater(budget.estimate('registration'),1.)
        self.assertEqual(budget.deadline,220)

    def test_high_timer_short_bar_restricts_work_but_reserves_actual_recovery(self):
        from screenshot_control import Budget
        budget=Budget(119,.07,now=100)
        self.assertLess(budget.work_remaining(100),30)
        self.assertFalse(budget.can_input(30,now=100))
        self.assertTrue(budget.can_input(30,now=100,recovery=True))
        self.assertGreater(budget.remaining(100),30)

    def test_initial_uncertainty_accepts_consistent_late_text_during_grace(self):
        from screenshot_control import Budget
        budget=Budget(None,.08,now=100)
        budget.observe(18,.075,now=101);budget.observe(17,.071,now=102)
        self.assertLessEqual(budget.remaining(102),17)

    def test_failed_gesture_clears_in_progress_and_invalidates_pose(self):
        from screenshot_control import Controller,Budget
        from unittest.mock import Mock
        owner=SimpleNamespace(stop=threading.Event(),consume_retry_request=lambda:False,
            event=lambda *a,**k:None,folder=Path(tempfile.gettempdir()))
        game=Mock();c=Controller(owner,game,SimpleNamespace(board=(0,0,20,20),cards=[],markers=[]),[],Budget(120,.4))
        c.check=lambda:None;c.frame=np.zeros((20,20,3),np.uint8)
        def fail():raise OSError('partial gesture')
        with self.assertRaises(OSError):c.act('failed',fail)
        self.assertFalse(c.input_in_progress)
        self.assertFalse(c.pose_known)
        self.assertTrue(c.input_uncertain)
        game.release.assert_called_once()

    def test_failed_release_also_clears_in_progress(self):
        from screenshot_control import Controller,Budget
        from unittest.mock import Mock
        owner=SimpleNamespace(stop=threading.Event(),consume_retry_request=lambda:False,
            event=lambda *a,**k:None,folder=Path(tempfile.gettempdir()))
        game=Mock();game.release.side_effect=OSError('release failed')
        c=Controller(owner,game,SimpleNamespace(board=(0,0,20,20),cards=[],markers=[]),[],Budget(120,.4))
        c.check=lambda:None;c.frame=np.zeros((20,20,3),np.uint8)
        with self.assertRaises(OSError):c.act('failed',lambda:None)
        self.assertFalse(c.input_in_progress)
        self.assertFalse(c.pose_known)

    def test_polled_f9_sets_stop_before_unwinding_period_or_recovery(self):
        from screenshot_control import Controller,Budget
        from platform_win import Interrupted
        from run_stop import StopEvent
        from unittest.mock import patch
        owner=SimpleNamespace(stop=StopEvent(),event=lambda *args,**kwargs:None,folder=Path(tempfile.gettempdir()))
        c=Controller(owner,SimpleNamespace(check=lambda:None),SimpleNamespace(board=(0,0,20,20),cards=[],markers=[]),[],Budget(120,.4))
        with patch('screenshot_control.u.GetAsyncKeyState',return_value=-32768):
            with self.assertRaises(Interrupted):c.check()
        self.assertTrue(owner.stop.is_set(),'Polled F9 must suppress unexpected interruption dialogs')
        self.assertEqual(owner.stop.diagnostic()['source'],'screenshot_f9_poll')

    def test_best_with_unknown_pose_has_no_assumed_free_return(self):
        from screenshot_control import Controller,Budget
        owner=SimpleNamespace(stop=threading.Event(),event=lambda *a,**k:None,folder=Path(tempfile.gettempdir()))
        c=Controller(owner,None,SimpleNamespace(board=(0,0,20,20),cards=[],markers=[]),[],Budget(120,.4))
        self.assertEqual(c.return_cost(),0.)
        c.best=dict(matrix=np.eye(3));c.pose_known=False
        self.assertTrue(np.isinf(c.return_cost()))
        c.pose_known=True;c.best['matrix']=None
        self.assertTrue(np.isinf(c.return_cost()))

    def test_real_game_adapter_releases_both_buttons_without_masking_stop(self):
        from platform_win import Game,Interrupted
        from unittest.mock import patch
        game=object.__new__(Game)
        with patch.object(Game,'send',side_effect=[Interrupted('stopped'),None]) as sender:
            game.release()
        self.assertEqual([call.args[0] for call in sender.call_args_list],[4,16])

    def test_early_lost_hundreds_digit_does_not_end_new_round(self):
        from screenshot_control import Budget
        budget=Budget(17,.42,now=100)
        self.assertAlmostEqual(budget.remaining(105),115)
        budget.observe(13,.39,now=105)
        self.assertAlmostEqual(budget.remaining(105),115)

    def test_real_late_entry_respects_short_timer_and_three_second_tail(self):
        from screenshot_control import Budget
        budget=Budget(17,.07,now=100)
        self.assertAlmostEqual(budget.remaining(105),12)
        self.assertTrue(budget.can_input(2,now=109))
        self.assertFalse(budget.can_input(2,now=113))

    def test_failed_registration_cannot_insert_commanded_pose(self):
        from screenshot_control import Controller,Budget
        owner=SimpleNamespace(stop=threading.Event(),event=lambda *a,**k:None,folder=Path(tempfile.gettempdir()))
        c=Controller(owner,None,SimpleNamespace(board=(0,0,20,20),cards=[],markers=[]),[],Budget(120,.4))
        initial=c.pose.copy();c.record_motion(None,dict(reason='failed'))
        np.testing.assert_array_equal(c.pose,initial)
        self.assertFalse(c.pose_known)

    def test_fine_shift_preserves_subpixel_offset_using_two_real_pivots(self):
        from screenshot_control import fine_proposal
        p=fine_proposal((100,200,801,901),[.5,-.25]);first,second=p
        np.testing.assert_array_equal(second-first,[50,-25])
        self.assertTrue(all(100<x<801 and 200<y<901 for x,y in p))

    def test_stop_during_input_releases_mouse_without_cursor_parking(self):
        from screenshot_control import Controller,Budget
        from platform_win import Interrupted
        from unittest.mock import Mock
        owner=SimpleNamespace(stop=threading.Event(),consume_retry_request=lambda:False,
            event=lambda *a,**k:None,folder=Path(tempfile.gettempdir()))
        game=Mock()
        c=Controller(owner,game,SimpleNamespace(board=(0,0,20,20),cards=[],markers=[]),[],Budget(120,.4))
        c.frame=np.zeros((20,20,3),np.uint8)
        with __import__('unittest').mock.patch('screenshot_control.u.GetAsyncKeyState',return_value=0):
            with self.assertRaises(Interrupted):c.act('stop',lambda:owner.stop.set())
        game.release.assert_called_once();game.move_to.assert_not_called();game.capture.assert_not_called()

    def test_fine_shift_is_split_to_fit_small_board_without_losing_total(self):
        from screenshot_control import Controller,Budget
        owner=SimpleNamespace(stop=threading.Event(),event=lambda *a,**k:None,folder=Path(tempfile.gettempdir()))
        game=SimpleNamespace(move_to=lambda p:None,send=lambda *a,**k:None)
        board=(100,200,400,500)
        c=Controller(owner,game,SimpleNamespace(board=board,cards=[],markers=[]),[],Budget(120,.4))
        rows=[]
        c.act=lambda *a,**k:rows.append(a[3] if len(a)>3 else k['receipt'])
        c.fine_shift([2.49,-2],'small-board')
        self.assertGreater(len(rows),1)
        shifts=[(np.array(v['anchors'][1])-v['anchors'][0])/100 for v in rows]
        np.testing.assert_allclose(np.sum(shifts,axis=0),[2.49,-2],atol=.02)
        self.assertTrue(all(100<x<400 and 200<y<500 for v in rows for x,y in v['anchors']))

    def test_direct_best_image_match_recovers_pose_when_reference_match_failed(self):
        from screenshot_control import Controller,Budget
        from unittest.mock import patch
        owner=SimpleNamespace(stop=threading.Event(),event=lambda *a,**k:None,folder=Path(tempfile.gettempdir()))
        c=Controller(owner,None,SimpleNamespace(board=(0,0,20,20),cards=[],markers=[]),[],Budget(120,.4))
        c.pose_known=False;c.frame=np.zeros((20,20,3),np.uint8)
        c.check=lambda:None
        c.best=dict(matrix=np.eye(3),frame=c.frame.copy(),rank=(1,0),verified=True)
        direct=np.eye(3);direct[0,2]=10
        poses=[]
        c.move_to=lambda *a,**k:poses.append((c.pose.copy(),c.pose_known))
        c.observe=lambda *a:dict(verified=True,rank=(1,0))
        with patch('screenshot_control.register',return_value=(direct,{})):
            c.restore()
        self.assertTrue(poses[0][1])
        self.assertAlmostEqual(poses[0][0][0,2],-10)

    def test_missing_initial_timer_is_corrected_by_repeated_late_readings(self):
        from screenshot_control import Budget
        c=Budget(None,.08,now=100)
        c.observe(6,.05,now=174);c.observe(5,.05,now=175)
        self.assertLessEqual(c.remaining(175),5)
        self.assertFalse(c.can_input(2,now=175))

    def test_missing_bar_cannot_corroborate_a_ten_second_ocr_error(self):
        from screenshot_control import Budget
        budget=Budget(120,.474,now=100)
        budget.observe(29,0,now=181)
        budget.observe(20,0,now=190)
        self.assertAlmostEqual(budget.remaining(190),30)

    def test_short_bar_contradicts_consistent_but_wrong_timer_digits(self):
        from screenshot_control import Budget
        budget=Budget(120,.474,now=100)
        budget.observe(29,.154,now=181)
        budget.observe(20,.119,now=190)
        self.assertAlmostEqual(budget.remaining(190),30)
        budget.observe(19,.075,now=201)
        self.assertAlmostEqual(budget.remaining(201),19)

    def test_local_return_corrects_small_angle_with_large_marker_span(self):
        from screenshot_control import Controller,Budget
        scene=SimpleNamespace(board=(0,0,701,701),cards=[],markers=[(100,560),(350,200),(580,260)])
        owner=SimpleNamespace(stop=threading.Event(),event=lambda *a,**k:None,folder=Path(tempfile.gettempdir()))
        c=Controller(owner,None,scene,[],Budget(120,.4))
        angle=np.radians(.097);desired=np.array([[np.cos(angle),-np.sin(angle),0],
            [np.sin(angle),np.cos(angle),0],[0,0,1.]])
        def rotate(degrees,*a,**kw):
            r=np.radians(degrees);matrix=np.array([[np.cos(r),-np.sin(r),0],[np.sin(r),np.cos(r),0],[0,0,1.]])
            c.pose=matrix@c.pose;return matrix
        def translate(shift,*a,**kw):
            matrix=np.eye(3);matrix[:2,2]=shift;c.pose=matrix@c.pose;return matrix
        c.rotate=rotate
        c.fine_shift=translate;c.drag=translate
        c.move_to(desired,'return-best',local=True)
        points=np.column_stack((scene.markers,np.ones(3)))
        self.assertLess(float(np.max(np.linalg.norm((points@c.pose.T-points@desired.T)[:,:2],axis=1))),.1)

    def test_unreadable_return_still_corrects_pose_before_reporting_result(self):
        from screenshot_control import Controller,Budget
        from unittest.mock import patch
        owner=SimpleNamespace(stop=threading.Event(),event=lambda *a,**k:None,folder=Path(tempfile.gettempdir()))
        c=Controller(owner,None,SimpleNamespace(board=(0,0,20,20),cards=[],markers=[]),[],Budget(120,.4))
        c.frame=np.zeros((20,20,3),np.uint8)
        c.check=lambda:None
        c.best=dict(matrix=np.eye(3),frame=c.frame.copy(),rank=(1,0),verified=True)
        def move(desired,*a,**kw):c.pose=np.asarray(desired);return True
        c.move_to=move
        readings=iter([dict(verified=False,rank=(1,1)),dict(verified=True,rank=(1,0))])
        c.observe=lambda *a:next(readings)
        with patch('screenshot_control.register',return_value=(np.eye(3),{})):
            result=c.restore()
        self.assertTrue(result['verified'])

    def test_short_tail_return_does_not_overshoot_scale_before_unaffordable_fine_pairs(self):
        from screenshot_control import Controller,Budget,TimeEnded
        scene=SimpleNamespace(board=(0,0,701,701),cards=[],markers=[(100,560),(350,200),(580,260)])
        owner=SimpleNamespace(stop=threading.Event(),event=lambda *a,**k:None,folder=Path(tempfile.gettempdir()))
        c=Controller(owner,None,scene,[],Budget(10,.04))
        desired=np.diag([1.0005,1.0005,1.])
        def wheel(steps,*a,**kw):
            c.pose[:2]*=(1.01**steps if steps>0 else .99**-steps)
        def pairs(count,*a,**kw):
            if not c.budget.can_input(count*.13+.35):raise TimeEnded()
            c.pose[:2]*=.9999**count
        def translate(shift,*a,**kw):c.pose[:2,2]+=shift
        c.wheel=wheel;c.pairs=pairs;c.fine_shift=translate;c.drag=translate
        try:c.move_to(desired,'return-best',local=True)
        except TimeEnded:pass
        self.assertLess(float(np.hypot(c.pose[0,0],c.pose[1,0])),1.001)

    def test_return_estimate_includes_whole_wheel_fine_scale_work(self):
        from screenshot_control import Controller,Budget
        owner=SimpleNamespace(stop=threading.Event(),event=lambda *a,**k:None,folder=Path(tempfile.gettempdir()))
        c=Controller(owner,None,SimpleNamespace(board=(0,0,20,20),cards=[],markers=[]),[],Budget(120,.4))
        self.assertGreater(c.return_cost(dict(matrix=np.diag([1.0005,1.0005,1.]))),13)

class ScreenshotRestoreDedupTests(unittest.TestCase):
    def make_controller(self,folder):
        from screenshot_control import Controller,Budget
        from screenshot_search import actual_result
        rules=[dict(enabled=True,colors=['#000000'],exact=True,tolerance=8.,priority=i+1)
            for i in range(3)]
        scene=SimpleNamespace(board=(0,0,100,100),cards=[],markers=[(20,50),(50,50),(80,50)])
        owner=SimpleNamespace(stop=threading.Event(),event=lambda *a,**kw:None,folder=Path(folder))
        c=Controller(owner,None,scene,rules,Budget(120,.4));c.check=lambda:None
        c.frame=np.zeros((100,100,3),np.uint8)
        c.current=actual_result(['#001522','#020202','#10000C'],rules)
        c.best=dict(actual_result(['#000D15','#131915','#150010'],rules),
            matrix=np.eye(3),frame=c.frame.copy())
        c.last_timer=time.monotonic();c.register=lambda *a:(np.eye(3),{})
        def capture(*a):c.frame=c.frame.copy();return c.frame
        c.capture=capture
        return c

    def test_nested_restore_calls_do_not_repeat_verified_motionless_reads(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            c=self.make_controller(folder);moves=[]
            def move(*a,**kw):
                moves.append(True)
                if len(moves)==1:c.actions.append(dict(name='return-best'));c.current=None
                return True
            c.move_to=move
            with patch('screenshot_control.read_visible',return_value=(['#000F19','#0F1311','#0C0009'],[])):
                for _ in range(4):result=c.restore()
            self.assertEqual(len(c.observations),2)
            self.assertEqual(len(moves),2)
            self.assertEqual(len(c.actions),1)
            self.assertTrue(result['verified']);self.assertFalse(result['accepted'])
            self.assertGreater(result['rank'],c.best['rank'])
            self.assertEqual(result['actual_colors'],['#000F19','#0F1311','#0C0009'])

    def test_new_frame_input_retry_or_best_target_all_reopen_recovery(self):
        from unittest.mock import patch
        for change in ('frame','input','retry','best','best_matrix','pose'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as folder:
                c=self.make_controller(folder);c.move_to=lambda *a,**kw:True
                with patch('screenshot_control.read_visible',return_value=(['#000F19','#0F1311','#0C0009'],[])):
                    c.restore();before=len(c.observations)
                    if change=='frame':c.capture('external-observation')
                    elif change=='input':c.actions.append(dict(name='new-input'))
                    elif change=='retry':c.current=None
                    elif change=='best':c.best=dict(c.best)
                    elif change=='best_matrix':c.best['matrix'][0,2]+=.01
                    elif change=='pose':c.pose[0,2]+=.01
                    c.restore()
                self.assertGreater(len(c.observations),before)

    def test_unreadable_color_does_not_suppress_later_recovery_read(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            c=self.make_controller(folder);c.move_to=lambda *a,**kw:True
            with patch('screenshot_control.read_visible',return_value=([None]*3,[])):
                result=c.restore();before=len(c.observations)
            self.assertFalse(result['verified'])
            with patch('screenshot_control.read_visible',return_value=(c.best['actual_colors'],[])):
                result=c.restore()
            self.assertEqual(len(c.observations),before+1)
            self.assertEqual(result['actual_colors'],c.best['actual_colors'])

    def test_recovery_continues_while_real_corrections_improve_the_pose(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            c=self.make_controller(folder)
            def move(*a,**kw):
                c.actions.append(dict(name='correction'));c.current=None
                return True
            c.move_to=move
            readings=[(['#000F19','#0F1311','#0C0009'],[])]*2+[(c.best['actual_colors'],[])]
            with patch('screenshot_control.read_visible',side_effect=readings):result=c.restore()
            self.assertEqual(len(c.actions),3)
            self.assertEqual(result['actual_colors'],c.best['actual_colors'])

    def test_restored_match_still_needs_an_independent_confirmation(self):
        from screenshot_live import _publish
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            c=self.make_controller(folder);c.move_to=lambda *a,**kw:True
            with patch('screenshot_control.read_visible',return_value=(['#000000']*3,[])):
                first=c.restore();result=_publish(c)
            self.assertFalse(first['confirmed'])
            self.assertEqual(len(c.observations),2)
            self.assertTrue(result['accepted']);self.assertTrue(result['confirmed'])

if __name__=='__main__':unittest.main()
