"""Planning layout reads must not pay final-color OCR or certify a hit."""
import copy
import inspect
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from native_live import project_probe_io as probe
from native_live.project_closed_loop_io import ProjectClosedLoopIO
from native_live.controller import run_goal_loop
from native_input_response import replay_native_route
from test_native_route_feedback import RecordedRouteIO
from test_native_two_region_visual import dye_frame


class PlanningFrameTests(unittest.TestCase):
    def test_planning_reads_real_layout_without_decoding_color_or_timer_text(self):
        for count in (2,3):
            with self.subTest(count=count),tempfile.TemporaryDirectory() as folder:
                image,board,codes=dye_frame(count)
                observation=dict(session_token=['test'],process_identity=[1,2,3,'build'],region_count=count,
                    motion=dict(binding={},settings={}),window_context=dict(window=dict(client_size_physical=[1600,1300])),
                    window_mapping_candidate=dict(client_board_candidate=board))
                captures=[]
                def capture():captures.append(True);return image.copy()
                project=ProjectClosedLoopIO.__new__(ProjectClosedLoopIO)
                probe.ProjectProbeIO.__init__(project,None,dict(session_deadline_monotonic=float('inf'),baseline=observation),
                    folder,game=SimpleNamespace(check=lambda:None,capture=capture),f9_pressed=lambda:False)
                project.check=lambda deadline:None;project._input_guard=lambda:None
                project.last_client_hex=codes;project.hex_fallback=lambda *a,**kw:self.fail('Planning requested glyph recognition')
                callback=getattr(project,'planning_frames',project.frames)
                with patch.object(probe,'read_codes',side_effect=AssertionError('Planning requested OCR')), \
                     patch.object(probe,'read_timer',side_effect=AssertionError('Planning requested timer OCR')):
                    rows=callback('plan_reference',float('inf'))
                self.assertEqual(len(captures),2)
                self.assertEqual([row['hex'] for row in rows],[codes,codes])
                self.assertEqual([row['screenshot_hex'] for row in rows],[[None]*count]*2)
                self.assertTrue(all(row['hex_source']==['native_checkpoint']*count for row in rows))
                self.assertTrue(all(not row['screenshot_hex_verified'] for row in rows))
                self.assertEqual(project.card_cache,{})
                self.assertTrue(all(Path(row['file']).is_file() for row in rows))

    def test_fast_planning_still_rejects_a_hidden_card_and_honors_stop(self):
        image,board,_=dye_frame(3,missing=2)
        kwargs=dict(deadline=100.,clock=lambda:1.,native_board=board,region_count=3,timer_mode='skip')
        if 'read_colors' in inspect.signature(probe.read_probe_frame).parameters:kwargs['read_colors']=False
        with self.assertRaises(ValueError):probe.read_probe_frame(image,**kwargs)
        image,board,_=dye_frame(2);kwargs.update(native_board=board,region_count=2)
        def stopped():raise InterruptedError('F9')
        with self.assertRaisesRegex(InterruptedError,'F9'):probe.read_probe_frame(image,check=stopped,**kwargs)


class PlanningReferenceIO(RecordedRouteIO):
    def __init__(self):
        super().__init__();self.offset=0.;self.full_labels=[];self.layout_labels=[]
    def clock(self):return super().clock()+self.offset
    def frames(self,label,deadline):
        self.full_labels.append(label)
        rows=super().frames(label,deadline)
        if not self.actions:
            # Saved rc7 failure: last image was >5 seconds old after two
            # decoder allowances. No game time is actually slept here.
            self.offset+=12.
        return rows
    def planning_frames(self,label,deadline):
        self.layout_labels.append(label)
        rows=super().frames(label,deadline)
        for row in rows:
            row.update(screenshot_hex=[None]*3,hex_source=['native_checkpoint']*3,
                screenshot_hex_verified=False,remaining_seconds=None,observation_scope='planning_layout')
        return rows
    def perform_candidate(self,record,label,deadline):
        self.check(deadline);self.actions.append(copy.deepcopy(record))
        self.pose=replay_native_route(self.pose,[record],self.geometry,self.settings,
            wheel_delta_per_step=1.,sample_policy='all_recorded_points')['final_pose']
        return dict(completed=True,released=True,gesture=record,
            actual_trace=[dict(actual_client=list(p)) for p in record['points']])


class PlanningControllerTests(unittest.TestCase):
    def run_io(self,io,rules=None):
        with patch('native_live.controller.find_refinement',return_value=None):
            return run_goal_loop(io,io.session,io.settings,rules or io.case['rules'],
                engineering_deadline=100.,clock=io.clock,planner=io.plan)

    def test_slow_initial_ocr_cannot_block_search_or_preinput_validation(self):
        io=PlanningReferenceIO();result=self.run_io(io)
        self.assertEqual(result['stop_reason'],'compromise_observed',result.get('error'))
        self.assertEqual(result['actual_colors'],['#FFFFFF','#FFFFFF','#E1E6E2'])
        self.assertTrue(result['screenshot_verified'])
        self.assertGreater(len(io.actions),0)
        self.assertFalse(any(label=='initial' or label.endswith('_revalidate') for label in io.full_labels))
        self.assertIn('initial',io.layout_labels)
        self.assertTrue(any(label.endswith('_after') for label in io.full_labels))
        self.assertFalse(result['initial']['frames'][0]['screenshot_hex_verified'])

    def test_stationary_compromise_gets_full_result_read_before_reporting(self):
        from native_palette_scoring import score_native_pose
        io=PlanningReferenceIO()
        io.case['candidate'].update(input_route=[],final_pose=copy.deepcopy(io.cp['pose']),needed=3.5,
            prediction=score_native_pose(io.session,io.cp['pose'],io.case['rules']))
        result=self.run_io(io)
        self.assertEqual(result['stop_reason'],'compromise_observed',result.get('error'))
        self.assertTrue(result['screenshot_verified'])
        self.assertEqual(io.actions,[])
        self.assertTrue(any(label.endswith('_revalidate') for label in io.full_labels))

    def test_slow_result_read_does_not_expire_an_unchanged_bound_plan(self):
        from native_palette_scoring import score_native_pose
        io=PlanningReferenceIO()
        io.case['candidate'].update(input_route=[],final_pose=copy.deepcopy(io.cp['pose']),needed=3.5,
            prediction=score_native_pose(io.session,io.cp['pose'],io.case['rules']))
        def slow_result(label,deadline):
            io.full_labels.append(label)
            rows=RecordedRouteIO.frames(io,label,deadline)
            if label.endswith('_revalidate'):io.offset+=16.
            return rows
        io.frames=slow_result
        result=self.run_io(io)
        self.assertEqual(result['stop_reason'],'compromise_observed',result.get('error'))
        self.assertTrue(result['screenshot_verified'])
        self.assertEqual(io.actions,[])
        self.assertEqual(result.get('reference_replans',0),0)
        observed=next(row for row in result['observations'] if row['label'].endswith('_revalidate'))
        frame=observed['frames'][-1]
        self.assertGreater(frame['reference_validation']['checked_monotonic']-frame['captured_monotonic'],15.)
        from native_live.same_session_dye_planner import bind_planning_context,validate_plan_reference,_plan_fingerprint
        context=bind_planning_context(io.session,io.cp,io.geometry,io.settings,wheel_delta_per_step=1.,
            calibration_evidence=dict(source='file_replay',viewport_origin=[0,0],viewport_scale=[1,1],
                backend_during_actions_synchronously_recorded=False))
        plan=result['planning_rounds'][0];now=frame['reference_validation']['checked_monotonic']+.01
        for key,value in (('planned_at',now+1.),('reference_frame_monotonic',now+1.),
                          ('effective_deadline',now+plan['compromise_candidate']['needed'])):
            with self.subTest(key=key):
                changed=copy.deepcopy(plan);changed[key]=value;changed['plan_fingerprint']=_plan_fingerprint(changed)
                with self.assertRaises(ValueError):
                    validate_plan_reference(context,changed,observed['checkpoint'],observed['frames'],now=now,
                        rules=io.case['rules'],purpose='compromise',reference_observation_paid=True)

    def test_native_initial_target_still_needs_full_screenshot_confirmation(self):
        io=PlanningReferenceIO()
        rules=[dict(enabled=True,exact=True,colors=[c],tolerance=0.) for c in io.cp['client_hex']]
        original=io.frames
        def missing(label,deadline):
            rows=original(label,deadline)
            for row in rows:row.update(screenshot_hex=[None]*3,hex_source=['native_checkpoint']*3,screenshot_hex_verified=False)
            return rows
        io.frames=missing;result=self.run_io(io,rules)
        self.assertFalse(result['accepted'])
        self.assertFalse(result['screenshot_verified'])
        self.assertEqual(io.actions,[])
        self.assertIn('initial',io.full_labels)
        self.assertEqual(io.layout_labels,[])

    def test_slow_full_read_uses_actual_unchanged_state_instead_of_five_second_stop(self):
        io=PlanningReferenceIO();io.planning_frames=None
        result=self.run_io(io)
        self.assertEqual(result['stop_reason'],'compromise_observed',result.get('error'))
        self.assertEqual(result['actual_colors'],['#FFFFFF','#FFFFFF','#E1E6E2'])
        self.assertGreater(len(io.actions),0)
        self.assertTrue(result['screenshot_verified'])
        self.assertEqual(result['initial']['frames'][0]['captured_monotonic'],
            result['observations'][0]['frames'][0]['captured_monotonic'])
        self.assertGreater(result['initial']['frames'][-1]['reference_validation']['checked_monotonic']-
            result['initial']['frames'][-1]['captured_monotonic'],5.)

    def test_slow_read_with_changed_pose_refreshes_before_planning(self):
        io=PlanningReferenceIO();io.planning_frames=None
        checkpoint=io.checkpoint;changed=[];planned=[];plan=io.plan
        def actual(label,deadline):
            if label.endswith('_post_decode') and not changed:
                changed.append(True);io.pose['position'][0]+=.001
            return checkpoint(label,deadline)
        io.checkpoint=actual
        def inspected_plan(context,cp,*args,**kwargs):
            planned.append(copy.deepcopy(cp))
            return plan(context,cp,*args,**kwargs)
        io.plan=inspected_plan
        result=self.run_io(io)
        self.assertTrue(changed,'Slow decode must actually reread the current pose')
        self.assertGreaterEqual(result['initial_visual_retries'],1)
        self.assertNotEqual(result['initial']['checkpoint']['pose'],io.cp['pose'])
        self.assertEqual(planned[0]['pose'],result['initial']['checkpoint']['pose'])
        # The saved route belongs to the original pose; its complete endpoint
        # audit correctly rejects it. The controller must not send that route.
        self.assertEqual(io.actions,[])
        self.assertFalse(result['accepted'])

    def test_reference_validation_does_not_transfer_to_another_pose_or_capture(self):
        from native_live.same_session_dye_planner import _fresh
        io=PlanningReferenceIO();io.planning_frames=None;result=self.run_io(io)
        cp=result['initial']['checkpoint'];rows=result['initial']['frames']
        now=rows[-1]['reference_validation']['checked_monotonic']+.01
        _fresh(now,rows,cp)
        changed=copy.deepcopy(cp);changed['pose']['position'][0]+=.001
        with self.assertRaises(ValueError):_fresh(now,rows,changed)
        changed=copy.deepcopy(rows);changed[0]['captured_monotonic']+=.001
        with self.assertRaises(ValueError):_fresh(now,changed,cp)
        for row in changed:row.pop('reference_validation',None)
        with self.assertRaises(ValueError):_fresh(now,changed,cp)


if __name__=='__main__':unittest.main()
