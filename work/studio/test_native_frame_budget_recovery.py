"""A local OCR allowance must not expire an otherwise healthy dye session."""
import copy
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from native_live import project_probe_io as probe
from native_live.controller import run_goal_loop
from test_native_live_controller import FixtureIO


class FrameBudgetRecoveryTests(unittest.TestCase):
    def test_first_ocr_card_survives_later_card_timeout(self):
        scene=SimpleNamespace(cards=[[100,100,80,80],[300,100,80,80],[500,100,80,80]],
            markers=[(140,300),(340,300),(540,300)],board=[40,200,640,800])
        def unreadable_glyph(*args,**kwargs):return dict(hex=None,glyphs_unambiguous=False)
        def read(image,cards,markers,enabled=None,**kwargs):
            if enabled==[True,False,False]:return ['#112233',None,None]
            raise TimeoutError('OCR observation deadline expired')
        with patch.object(probe,'recognize',return_value=scene),patch.object(probe,'read_codes',side_effect=read):
            with self.assertRaises(TimeoutError) as caught:
                probe.read_probe_frame(np.zeros((960,1280,3),np.uint8),deadline=100.,clock=lambda:1.,
                    hex_fallback=unreadable_glyph,timer_mode='skip')
        self.assertEqual(caught.exception.partial_frame['hex'],['#112233',None,None])

    def test_advisory_timer_exhaustion_preserves_completed_hex(self):
        tick=[1.]
        scene=SimpleNamespace(cards=[],markers=[],board=[0,0,500,500])
        def colors(*args,**kwargs):tick[0]=4.4;return ['#112233']*3
        def timer(*args,**kwargs):
            tick[0]=5.05;raise TimeoutError('OCR observation deadline expired')
        with patch.object(probe,'recognize',return_value=scene), \
             patch.object(probe,'read_codes',side_effect=colors), \
             patch.object(probe,'read_timer',side_effect=timer):
            result=probe.read_probe_frame(np.zeros((960,1280,3),np.uint8),deadline=5.,
                clock=lambda:tick[0],timer_mode='advisory')
        self.assertEqual(result['hex'],['#112233']*3)
        self.assertIsNone(result['remaining_seconds'])
        self.assertEqual(result['timer_confidence'],'unknown')
        self.assertIn('deadline',result['timer_error'])

    def test_real_session_deadline_still_interrupts_advisory_timer(self):
        tick=[1.]
        scene=SimpleNamespace(cards=[],markers=[],board=[0,0,500,500])
        def check():
            if tick[0]>=5.:raise TimeoutError('Probe deadline expired')
        def timer(*args,**kwargs):
            tick[0]=5.05;raise TimeoutError('OCR observation deadline expired')
        with patch.object(probe,'recognize',return_value=scene), \
             patch.object(probe,'read_codes',return_value=['#112233']*3), \
             patch.object(probe,'read_timer',side_effect=timer):
            with self.assertRaisesRegex(TimeoutError,'Probe deadline expired'):
                probe.read_probe_frame(np.zeros((960,1280,3),np.uint8),deadline=5.,
                    clock=lambda:tick[0],check=check,timer_mode='advisory')

    def test_partial_glyph_color_survives_local_ocr_exhaustion_in_frames(self):
        image=np.zeros((960,1280,3),np.uint8)
        cards=[[100,100,80,80],[300,100,80,80],[500,100,80,80]]
        codes=['#112233','#445566','#778899']
        for (x,y,w,h),rgb in zip(cards,[(17,34,51),(68,85,102),(119,136,153)]):
            image[y:y+h,x:x+w]=rgb
        scene=SimpleNamespace(cards=cards,markers=[],board=[40,200,640,800])
        observation=dict(session_token=['session'],process_identity=[1,2,3,'build'],
            motion=dict(binding={},settings={}),window_context=dict(window=dict(client_size_physical=[1280,960])),
            window_mapping_candidate=dict(client_board_candidate=scene.board))
        def glyph(image,card,**unused):
            return dict(hex=codes[0] if list(card)==cards[0] else None,
                glyphs_unambiguous=list(card)==cards[0])
        def exhausted(*args,**kwargs):raise TimeoutError('OCR observation deadline expired')
        with tempfile.TemporaryDirectory() as folder:
            io=probe.ProjectProbeIO(None,dict(session_deadline_monotonic=float('inf'),baseline=observation),
                folder,game=SimpleNamespace(check=lambda:None,capture=lambda:image),f9_pressed=lambda:False)
            io.check=lambda deadline:None;io._input_guard=lambda:None
            io.last_client_hex=codes;io.hex_fallback=glyph;io.timer_grace_until=float('inf')
            with patch.object(probe,'_recognize_native_layout',return_value=scene), \
                 patch.object(probe,'read_codes',side_effect=exhausted):
                frames=io.frames('partial',float('inf'))
        self.assertEqual([frame['hex'] for frame in frames],[codes,codes])
        self.assertEqual(frames[0]['screenshot_hex'],[codes[0],None,None])
        self.assertEqual(frames[0]['hex_source'],['screenshot','native_checkpoint','native_checkpoint'])
        self.assertFalse(frames[0]['screenshot_hex_verified'])
        self.assertIn('deadline',frames[0]['hex_error'])


class ControllerFrameBudgetRecoveryTests(unittest.TestCase):
    def run_io(self,io,*,purpose='target',**kwargs):
        # This suite tests feedback allowances, not heuristic search speed.
        # Use the fixture's already verified two-action route and a clock
        # advanced only by IO, so parallel CPU load cannot expire the session.
        from native_live.same_session_dye_planner import _plan_fingerprint,audit_candidate_endpoint
        from native_input_route_search import _needed
        from native_input_response import replay_native_route
        from native_palette_scoring import score_native_pose
        io.clock=lambda:io.t
        def planner(context,checkpoint,frames,rules,grid,*,now,engineering_deadline,**unused):
            route=[copy.deepcopy(row['gesture']) for row in io.case['actual_steps']]
            replay=replay_native_route(checkpoint['pose'],route,io.geometry,io.settings,
                wheel_delta_per_step=1.,sample_policy='all_recorded_points')
            candidate=audit_candidate_endpoint(context,checkpoint,rules,dict(input_route=route,
                final_pose=replay['final_pose'],prediction=score_native_pose(io.session,replay['final_pose'],rules),
                needed=_needed(route,3.,.5),source='recorded_verified_fixture_route'))
            if purpose=='approach':candidate['target_prediction']=candidate['prediction']
            plan=dict(schema=1,context_fingerprint=context['fingerprint'],reference_pose=checkpoint['pose'],
                reference_frame_monotonic=frames[-1]['captured_monotonic'],planned_at=now,
                effective_deadline=engineering_deadline,candidate=candidate if purpose=='target' else None,
                approach_candidate=candidate if purpose=='approach' else None,reserve_seconds=10.,
                verification_margin_seconds=8.)
            plan['plan_fingerprint']=_plan_fingerprint(plan)
            return plan
        return run_goal_loop(io,io.session,io.settings,io.case['rules'],
            engineering_deadline=kwargs.pop('engineering_deadline',90.),clock=io.clock,planner=planner,
            pause=lambda seconds:setattr(io,'t',io.t+seconds),**kwargs)

    def test_target_and_approach_reserve_complete_action_quota_before_input(self):
        for purpose in ('target','approach'):
            with self.subTest(purpose=purpose):
                io=FixtureIO();result=self.run_io(io,purpose=purpose,max_actions=1)
                self.assertEqual(io.actions,[])
                self.assertEqual(result['stop_reason'],'insufficient_route_actions')
                self.assertTrue(result['verified'])

    def test_target_and_approach_reserve_complete_readback_time_before_input(self):
        for purpose in ('target','approach'):
            with self.subTest(purpose=purpose):
                io=FixtureIO();result=self.run_io(io,purpose=purpose,engineering_deadline=12.)
                self.assertEqual(io.actions,[])
                self.assertEqual(result['stop_reason'],'insufficient_time')
                self.assertTrue(result['verified'])

    def test_postinput_local_frame_timeout_recovers_without_repeating_input(self):
        io=FixtureIO();original=io.frames;failed=[]
        def frames(label,deadline):
            if label.startswith('candidate_') and not failed:
                failed.append(label);io.t+=5.;raise TimeoutError('Frame read deadline expired')
            return original(label,deadline)
        io.frames=frames;result=self.run_io(io)
        self.assertTrue(result['accepted'],result.get('error'))
        self.assertEqual(len(io.actions),2)
        self.assertEqual(result['observation_retries'],1)

    def test_persistent_local_timeout_preserves_native_current_and_is_not_session_expiry(self):
        io=FixtureIO();original=io.frames
        def frames(label,deadline):
            if label.startswith('candidate_'):
                io.t+=5.;raise TimeoutError('Frame read deadline expired')
            return original(label,deadline)
        io.frames=frames;result=self.run_io(io)
        self.assertEqual(result['stop_reason'],'observation_failed')
        self.assertFalse(result['accepted']);self.assertFalse(result['verified'])
        self.assertEqual(result['actual_colors'],result['native_current']['checkpoint']['client_hex'])
        self.assertEqual(len(io.actions),2)
        self.assertGreater(result['effective_deadline']-io.t,40.)


if __name__=='__main__':unittest.main()
