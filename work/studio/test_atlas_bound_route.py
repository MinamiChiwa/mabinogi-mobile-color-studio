import copy
import json
import unittest
import time
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from atlas_bound_route import bind_candidate, bound_motion, forecast_gesture
from atlas_pose import candidate_pose, homogeneous, relative_candidate, marker_errors
from atlas_execution import (CandidateBatch, execute_candidate, reposition_budget,
                              _route_needs_replan)
from test_atlas_similarity_execution import SimilarityGame
from test_atlas_pose_scoring import CoordinateAtlas


class ConstantAtlas:
    basis=np.diag([100.,100.])
    resolution=16
    def sample(self,region,points,offset):
        return np.tile([17,34,51],(len(points),1)),np.ones(len(points),bool)


class IntegerGame(SimilarityGame):
    """Input/response contract simulation, not a live game accuracy test."""
    def __init__(self):
        super().__init__();self.sent=[];self.deviate=False
    def perform_gesture(self,gesture):
        self.sent.append(gesture.record());self.actions.append(gesture.kind)
        response=forecast_gesture(gesture,self.ctx.board,self.tick,self.tick)
        if gesture.kind=='rotate' and self.deviate:
            response=np.eye(3)
        self.pose=response@self.pose


class BoundRouteTests(unittest.TestCase):
    def test_measured_entry_return_executes_translation_and_stops_after_double_hex(self):
        from atlas_live_adapter import bind_entry_checkpoint,_execute_recorded
        target=(-40.,0.)
        baseline=dict(candidate_id=-1,verified=True,pose_reliable=True,frame_ids=['entry-a','entry-b'],
            actual_colors=['#FFFEFE']*3,actual_deltas=[.44]*3,maximum=.44,average=.44,accepted=False)
        owner=SimpleNamespace(event=lambda *a,**k:None)
        report=dict(baseline_result=baseline,board=self.game.ctx.board,markers=self.game.ctx.markers,
                    adapter=self.game,runtime={},selection_deadline=time.monotonic()+120)
        rules=[dict(enabled=True,exact=True,colors=['#FFFFFF'],tolerance=0)]*3
        row,budget=bind_entry_checkpoint(dict(baseline,entry_checkpoint=True,dx=target[0],dy=target[1]),
                                         report,rules,report['selection_deadline'])
        self.assertIsNotNone(row)
        def codes(frame):
            self.game.reads+=1
            return ['#FFFEFE' if np.allclose(frame[:2,2],target) else '#777777']*3
        self.game.read_codes=codes
        batch=CandidateBatch([row],self.game.ctx,report['selection_deadline'])
        with patch('atlas_execution._feedback_refine',side_effect=AssertionError('No new target during return')):
            result=_execute_recorded(owner,report,row,rules,batch,self.game.capture(),recording_return=True)
        self.assertTrue(result['verified']);self.assertFalse(result['accepted'])
        self.assertEqual(result['actual_colors'],baseline['actual_colors'])
        self.assertEqual(self.game.actions,['drag'])
        self.assertEqual(self.game.reads,2)
        self.assertEqual(self.game.releases,1)

    def setUp(self):
        self.game=IntegerGame();self.atlas=ConstantAtlas()
        self.rules=[dict(enabled=True,exact=False,colors=['#112233'],tolerance=8)]*3
        self.row=dict(id=7,dx=85,dy=-45,angle=24,scale=1.01**-4,
                      colors=['#FFFFFF']*3,deltas=[0]*3,accepted=True,maximum=0,average=0)

    def bind(self,row=None):
        row,budget=bind_candidate(row or self.row,self.atlas,[0,0],self.game.ctx.board,
            self.game.ctx.markers,self.rules,0,1000)
        self.assertIsNotNone(row,budget)
        return row

    def test_route_replan_uses_hysteresis_around_one_pixel_registration_noise(self):
        self.assertFalse(_route_needs_replan([1.0, .9, 1.1]))
        self.assertFalse(_route_needs_replan([1.24, 1.0, .8]))
        self.assertTrue(_route_needs_replan([1.26, 1.0, .8]))
        self.assertTrue(_route_needs_replan([.1, .1, .1], rotation_quantized=True))

    def execute(self,row,events=None):
        batch=CandidateBatch([row],self.game.ctx,1000,clock=lambda:0)
        return execute_candidate(self.game,batch,batch.id,row['id'],self.game.capture(),
            self.rules,clock=lambda:0,emit=lambda k,d:events.append((k,d)) if events is not None else None)

    def test_forecast_route_rescores_then_sends_exact_bound_integer_inputs(self):
        original=copy.deepcopy(self.row);row=self.bind()
        self.assertEqual(row['colors'],['#112233']*3)
        self.assertEqual(self.row,original)
        self.assertEqual(row['prediction_pose_source'],'bound_integer_route_forecast')
        self.assertFalse(row['planned_route']['game_response_verified'])
        # JSON serialisation must preserve a binding, including exact points.
        row=json.loads(json.dumps(row));events=[]
        result=self.execute(row,events)
        self.assertEqual(json.loads(json.dumps(self.game.sent)),row['planned_route']['inputs'])
        np.testing.assert_allclose(result['actual_pose'],row['planned_route']['endpoint'],atol=1e-8)
        self.assertFalse(any(k=='atlas_replanned' for k,d in events))
        self.assertEqual(self.game.releases,1)
        self.assertEqual(self.game.reads,2)

    def test_endpoint_uses_integer_arc_instead_of_continuous_request(self):
        row=self.bind(dict(self.row,dx=0,dy=0,angle=.4,scale=1))
        route=bound_motion(row,self.game.ctx.board,self.game.ctx.markers)
        self.assertEqual(route['actions']['rotate'],1)
        gesture=route['gestures'][0]
        self.assertNotAlmostEqual(gesture.arc_degrees,gesture.requested_angle,places=3)
        self.assertAlmostEqual(row['angle'],gesture.arc_degrees)

    def test_rounded_translation_recomputes_colour_before_publication(self):
        rules=[dict(enabled=True,exact=False,colors=['#FFFFFF'],tolerance=8)]*3
        markers=((150,260),(170,280),(190,300));board=(100,200,400,500)
        row,budget=bind_candidate(dict(self.row,dx=5.4,dy=0,angle=0,scale=1),
            CoordinateAtlas(),[5,7],board,markers,rules,0,1000)
        self.assertEqual(row['dx'],5)
        self.assertEqual(row['colors'][0],'#28351E')
        self.assertFalse(row['accepted'])
        np.testing.assert_array_equal(row['prediction_pose'],[[1,0,5],[0,1,0]])
        self.assertEqual(reposition_budget(row,0,100,board,markers=markers)['input_route'],
                         row['planned_route']['inputs'])

    def test_observed_no_response_discards_remaining_route_and_replans_from_identity(self):
        row=self.bind();original_inputs=row['planned_route']['inputs']
        self.assertGreater(len(original_inputs),2)
        self.game.deviate=True;observed=[];events=[]
        def replan(actual,current,rules):
            observed.append(actual.copy())
            fresh=relative_candidate(current,np.eye(3),self.game.ctx.board)
            return dict(fresh,matrix=(homogeneous([[1,0,7],[0,1,0]])@actual)[:2].tolist())
        self.game.replan=replan
        self.game.rebind=lambda *args:self.fail('A stalled rotation must not be retried')
        result=self.execute(row,events)
        self.assertTrue(result['replanned'])
        self.assertEqual(self.game.actions,['rotate','drag'])
        np.testing.assert_array_equal(observed,[np.eye(3)])
        self.assertTrue(any(k=='atlas_route_discarded' for k,d in events))
        self.assertEqual(self.game.sent[0],original_inputs[0])
        self.assertEqual(result['actual_pose'],[[1.,0.,7.],[0.,1.,0.]])

    def test_measured_drift_rebinds_remaining_route_without_losing_original_target(self):
        row=self.bind();events=[];observed=[];perform=self.game.perform_gesture
        def drift_once(gesture):
            perform(gesture)
            if len(self.game.sent)==1:
                self.game.pose=homogeneous([[1,0,.9],[0,1,.1]])@self.game.pose
        self.game.perform_gesture=drift_once
        def rebind(actual,current,rules):
            observed.append(actual.copy())
            fresh,budget=bind_candidate(relative_candidate(current,actual,self.game.ctx.board),
                self.atlas,[0,0],self.game.ctx.board,self.game.ctx.markers,rules,0,1000,
                reference_pose=actual)
            self.assertTrue(budget['allowed'])
            return fresh
        self.game.rebind=rebind
        self.game.replan=lambda *args:self.fail('Valid remaining route should not lose rotation/zoom')
        result=self.execute(row,events)
        self.assertEqual(len(observed),1)
        self.assertTrue(result['replanned'])
        self.assertIn('wheel',self.game.actions)
        self.assertEqual(sum(kind=='atlas_route_rebound' for kind,data in events),1)
        errors=marker_errors(candidate_pose(row,self.game.ctx.board),self.game.pose,
            np.asarray(self.game.ctx.markers)-self.game.ctx.board[:2])
        self.assertLessEqual(max(errors),.65)
        self.assertEqual(self.game.reads,2)
        self.assertEqual(self.game.releases,1)

    def test_repeated_drift_bounds_rebinding_then_uses_measured_fallback(self):
        row=self.bind(dict(self.row,angle=60));events=[];attempts=[];perform=self.game.perform_gesture
        def drift(gesture):
            perform(gesture)
            if gesture.kind=='rotate':
                self.game.pose=homogeneous([[1,0,.9],[0,1,.1]])@self.game.pose
        self.game.perform_gesture=drift
        def rebind(actual,current,rules):
            attempts.append(actual.copy())
            return bind_candidate(relative_candidate(current,actual,self.game.ctx.board),
                self.atlas,[0,0],self.game.ctx.board,self.game.ctx.markers,rules,0,1000,
                reference_pose=actual)[0]
        self.game.rebind=rebind
        def fallback(actual,current,rules):
            fresh=relative_candidate(current,np.eye(3),self.game.ctx.board)
            return dict(fresh,matrix=(homogeneous([[1,0,7],[0,1,0]])@actual)[:2].tolist())
        self.game.replan=fallback
        result=self.execute(row,events)
        self.assertEqual(len(attempts),2)
        self.assertEqual(self.game.actions,['rotate','rotate','rotate','drag'])
        self.assertTrue(result['verified'])
        self.assertEqual(self.game.releases,1)

    def test_stop_during_rebinding_never_sends_more_inputs(self):
        row=self.bind();perform=self.game.perform_gesture
        def drift(gesture):
            perform(gesture)
            self.game.pose=homogeneous([[1,0,.9],[0,1,.1]])@self.game.pose
        self.game.perform_gesture=drift
        def rebind(*args):self.game.stop=True;return None
        self.game.rebind=rebind
        with self.assertRaises(InterruptedError):self.execute(row)
        self.assertEqual(len(self.game.sent),1)
        self.assertEqual(self.game.releases,1)

    def test_long_rotation_can_rebind_beyond_twice_after_measured_progress(self):
        row=self.bind(dict(self.row,angle=165));events=[];attempts=[];perform=self.game.perform_gesture
        def drift(gesture):
            perform(gesture)
            if gesture.kind=='rotate':
                self.game.pose=homogeneous([[1,0,.24],[0,1,.02]])@self.game.pose
        self.game.perform_gesture=drift
        def rebind(actual,current,rules):
            attempts.append(actual.copy())
            return bind_candidate(relative_candidate(current,actual,self.game.ctx.board),
                self.atlas,[0,0],self.game.ctx.board,self.game.ctx.markers,rules,0,1000,
                reference_pose=actual)[0]
        self.game.rebind=rebind
        self.game.replan=lambda *args:self.fail('Progressing long route should retain its rotation and zoom')
        result=self.execute(row,events)
        self.assertGreater(len(attempts),2)
        self.assertIn('wheel',self.game.actions)
        corrections=[data for kind,data in events if kind=='atlas_route_rebound']
        extended=[r for r in corrections if r['progress_extension']]
        self.assertTrue(extended)
        for before,after in zip(corrections,corrections[1:]):
            if after['progress_extension']:
                self.assertLess(after['measured_target_error'],before['measured_target_error']-.65)
        self.assertTrue(result['verified'])
        errors=marker_errors(candidate_pose(row,self.game.ctx.board),self.game.pose,
                             np.asarray(self.game.ctx.markers)-self.game.ctx.board[:2])
        self.assertLessEqual(max(errors),1)
        self.assertEqual(self.game.releases,1)

    def test_live_callback_rebinds_and_rescores_in_capture_coordinates(self):
        from atlas_live_adapter import default_current
        from test_atlas_service import Owner
        # This callback exercises the production transform route after the
        # response certificate has been established.  Without the certificate
        # the live adapter must suppress the route and use translation-only
        # recovery instead (covered by the publication-gate tests below).
        self.atlas.response_profile_verified=True
        row=self.bind();perform=self.game.perform_gesture
        def drift_once(gesture):
            perform(gesture)
            if len(self.game.sent)==1:
                self.game.pose=homogeneous([[1,0,.9],[0,1,.1]])@self.game.pose
        self.game.perform_gesture=drift_once
        deadline=time.monotonic()+1000
        report=dict(batch=CandidateBatch([row],self.game.ctx,deadline),adapter=self.game,
                    reference=self.game.capture(),runtime=dict(atlas=self.atlas,capture_offset=[0,0]))
        owner=Owner()
        result=default_current(owner,report,row,self.rules)
        self.assertTrue(any(kind=='atlas_route_rebound' for kind,_ in owner.events))
        self.assertEqual(result['prediction_pose_source'],'measured_final_pose')
        self.assertTrue(result['family_consistent'])
        np.testing.assert_allclose(result['prediction_pose'],self.game.pose[:2])
        self.assertEqual(result['predicted_colors'],['#112233']*3)

    def test_live_rebind_keeps_supported_route_across_a_family_boundary(self):
        from atlas_live_adapter import default_current
        from test_atlas_service import Owner
        self.atlas.response_profile_verified=True
        row=self.bind();perform=self.game.perform_gesture
        self.assertTrue(row['family_consistent'])
        def drift_once(gesture):
            perform(gesture)
            if len(self.game.sent)==1:
                self.game.pose=homogeneous([[1,0,.9],[0,1,.1]])@self.game.pose
        self.game.perform_gesture=drift_once
        def rebound(*args,**kwargs):
            ready,budget=bind_candidate(*args,**kwargs)
            if ready is not None:
                ready=dict(ready,family_consistent=False,cross_family_fallback=True)
            return ready,budget
        report=dict(batch=CandidateBatch([row],self.game.ctx,time.monotonic()+1000),
                    adapter=self.game,reference=self.game.capture(),
                    runtime=dict(atlas=self.atlas,capture_offset=[0,0]))
        owner=Owner()
        with patch('atlas_live_adapter.bind_candidate',side_effect=rebound), \
             patch('atlas_live_adapter.reachable_candidates',side_effect=AssertionError('unexpected target replacement')):
            result=default_current(owner,report,row,self.rules)
        self.assertTrue(any(kind=='atlas_route_rebound' for kind,_ in owner.events))
        self.assertTrue(result['verified'])
        self.assertLessEqual(max(result['marker_errors']),1)

    def test_live_translation_fallback_preserves_measured_rotation_and_scale(self):
        from atlas_live_adapter import default_current
        from atlas_pose import pose_fields
        from test_atlas_service import Owner
        row=self.bind();perform=self.game.perform_gesture;fallback_starts=[]
        def drift_once(gesture):
            perform(gesture)
            if len(self.game.sent)==1:
                self.game.pose=homogeneous([[1,0,.9],[0,1,.1]])@self.game.pose
        self.game.perform_gesture=drift_once
        def reachable(atlas,offset,actual,markers,board,rules,candidate_id,**kwargs):
            fallback_starts.append(actual.copy())
            target=homogeneous([[1,0,-29],[0,1,18]])@actual
            return [dict(row,**pose_fields(target,board))]
        bind_calls=[]
        def binding(*args,**kwargs):
            bind_calls.append(args[0])
            # Force the actual production adapter's fallback after a rejected
            # rebind. Its returned binding is local to the measured pose.
            if len(bind_calls)==1:return None,dict(allowed=False,reason='unstable_landing')
            return bind_candidate(*args,**kwargs)
        deadline=time.monotonic()+1000
        report=dict(batch=CandidateBatch([row],self.game.ctx,deadline),adapter=self.game,
                    reference=self.game.capture(),runtime=dict(atlas=self.atlas,capture_offset=[0,0]))
        owner=Owner()
        with patch('atlas_live_adapter.bind_candidate',side_effect=binding), \
             patch('atlas_live_adapter.reachable_candidates',side_effect=reachable):
            result=default_current(owner,report,row,self.rules)
        self.assertEqual(self.game.actions,['rotate','drag'])
        expected=homogeneous([[1,0,-29],[0,1,18]])@fallback_starts[0]
        np.testing.assert_allclose(result['actual_pose'],expected[:2],atol=1e-8)
        replacement=next(data['candidate'] for kind,data in owner.events if kind=='atlas_replanned')
        np.testing.assert_allclose(replacement['matrix'],expected[:2],atol=1e-8)
        self.assertEqual(replacement['rebound_route']['route']['inputs'],self.game.sent[1:])
        self.assertLessEqual(max(result['marker_errors']),1)

    def test_unbound_detent_replan_adopts_binding_in_measured_pose(self):
        from atlas_pose import pose_fields
        # An unbound transform reaches a physical detent, then the same
        # production callback returns an integer translation binding.
        row=dict(self.row,angle=0,scale=.99**4)
        starts=[]
        def replan(actual,current,rules):
            starts.append(actual.copy())
            proposal=dict(current,**pose_fields([[1,0,9],[0,1,-6]],self.game.ctx.board))
            return bind_candidate(proposal,self.atlas,[0,0],self.game.ctx.board,
                self.game.ctx.markers,rules,0,1000,reference_pose=actual)[0]
        self.game.replan=replan
        result=self.execute(row)
        self.assertTrue(starts)
        expected=homogeneous([[1,0,9],[0,1,-6]])@starts[0]
        np.testing.assert_allclose(result['actual_pose'],expected[:2],atol=1e-8)
        self.assertTrue(result['verified'])
        self.assertEqual(self.game.actions[-1],'drag')

    def test_blue_candidate_with_purple_landing_neighbour_is_not_stable(self):
        class EdgeAtlas(ConstantAtlas):
            def sample(self,region,points,offset):
                values,valid=super().sample(region,points,offset)
                values[:]=[80,80,150]
                if len(values)>1:values[-1]=[105,38,143]
                return values,valid
        rules=[dict(enabled=True,exact=False,colors=['#0000FF'],tolerance=8)]*3
        bound,budget=bind_candidate(dict(self.row,dx=0,dy=0,angle=0,scale=1),EdgeAtlas(),[0,0],
            self.game.ctx.board,self.game.ctx.markers,rules,0,1000,require_stable=True)
        self.assertIsNone(bound)
        self.assertEqual(budget['reason'],'unstable_landing')
        self.assertGreater(budget['route_stability']['landing_family_maximum'],0)

    def test_cross_family_fallback_can_publish_only_close_same_hue_compromise(self):
        class CloseBlueAtlas(ConstantAtlas):
            def sample(self,region,points,offset):
                values,valid=super().sample(region,points,offset)
                values=np.asarray(values).copy()
                values[:]=[80,80,150]
                return values,valid
        rules=[dict(enabled=True,exact=False,colors=['#0000FF'],tolerance=8)]*3
        candidate=dict(self.row,dx=0,dy=0,angle=0,scale=1,
                       family_consistent=False,family_maximum=.2)
        bound,budget=bind_candidate(candidate,CloseBlueAtlas(),[0,0],self.game.ctx.board,
            self.game.ctx.markers,rules,0,1000,require_stable=True,allow_cross_family=True)
        self.assertIsNotNone(bound,budget)
        self.assertTrue(bound['cross_family_fallback'])

    def test_cross_family_fallback_rejects_obviously_unrelated_colour(self):
        class GreenAtlas(ConstantAtlas):
            def sample(self,region,points,offset):
                values,valid=super().sample(region,points,offset)
                values[:]=[20,180,30]
                return values,valid
        rules=[dict(enabled=True,exact=False,colors=['#0000FF'],tolerance=8)]*3
        candidate=dict(self.row,dx=0,dy=0,angle=0,scale=1,
                       family_consistent=False,family_maximum=1.2)
        bound,budget=bind_candidate(candidate,GreenAtlas(),[0,0],self.game.ctx.board,
            self.game.ctx.markers,rules,0,1000,require_stable=True,allow_cross_family=True)
        self.assertIsNone(bound)
        self.assertEqual(budget['reason'],'unstable_landing')

    def test_stale_or_modified_binding_never_sends_input(self):
        for changed in ('point','endpoint','board','timing','zoom'):
            with self.subTest(changed=changed):
                self.setUp();row=self.bind();route=row['planned_route']
                if changed=='point':
                    points=list(route['inputs'][0]['points']);points[-1]=(0,0)
                    route['inputs'][0]['points']=points
                if changed=='endpoint':row['matrix'][0][2]+=1
                if changed=='board':route['board'][0]+=1
                if changed=='timing':route['inputs'][0]['timing']['before_up']=0
                if changed=='zoom':row['zoom_log_step']=.02
                with self.assertRaises(ValueError):self.execute(row)
                self.assertEqual(self.game.sent,[])
                self.assertEqual(self.game.releases,1)

    def test_rebase_invalidates_binding_and_new_binding_scores_in_original_atlas(self):
        row=self.bind();relative=relative_candidate(row,[[1,0,20],[0,1,0]],self.game.ctx.board)
        self.assertNotIn('planned_route',relative)
        rebound,budget=bind_candidate(relative,self.atlas,[0,0],self.game.ctx.board,
            self.game.ctx.markers,self.rules,0,1000,reference_pose=[[1,0,20],[0,1,0]])
        self.assertIsNotNone(rebound,budget)
        np.testing.assert_allclose(rebound['prediction_pose'],
            (candidate_pose(rebound,self.game.ctx.board)@homogeneous([[1,0,20],[0,1,0]]))[:2])

    def test_f9_after_bound_input_releases_without_sending_rest(self):
        row=self.bind();perform=self.game.perform_gesture
        def stop(gesture):perform(gesture);self.game.stop=True
        self.game.perform_gesture=stop
        with self.assertRaises(InterruptedError):self.execute(row)
        self.assertEqual(len(self.game.sent),1)
        self.assertEqual(self.game.releases,1);self.assertEqual(self.game.reads,0)

    def test_unsupported_endpoint_and_short_deadline_never_keep_old_colours(self):
        class MissingAtlas:
            def sample(self,region,points,offset):
                return np.zeros((len(points),3)),np.zeros(len(points),bool)
        for atlas,deadline,reason in ((MissingAtlas(),1000,'unsupported_endpoint'),
                                      (self.atlas,.1,'insufficient_time')):
            row,budget=bind_candidate(self.row,atlas,[0,0],self.game.ctx.board,
                self.game.ctx.markers,self.rules,0,deadline)
            self.assertIsNone(row);self.assertEqual(budget['reason'],reason)

    def test_production_binding_rejects_unstable_landing_before_publication(self):
        # Force the atlas to change outside the center point. Centre scoring
        # remains valid, but a one-pixel landing neighbourhood is unsafe.
        class NarrowAtlas:
            def sample(self,region,points,offset):
                points=np.asarray(points)
                values=np.tile([17,34,51],(len(points),1))
                valid=np.ones(len(points),bool)
                if np.any(np.abs(points[:,0]-points[0,0])>.5):
                    values[:,0]=90
                return values,valid
        row=dict(self.row,dx=0,dy=0,angle=0,scale=1)
        bound,budget=bind_candidate(row,NarrowAtlas(),[0,0],self.game.ctx.board,
            self.game.ctx.markers,self.rules,0,1000,require_stable=True)
        self.assertIsNone(bound)
        self.assertEqual(budget['reason'],'unstable_landing')
        self.assertFalse(budget['route_stability']['landing_safe'])

    def test_diagnostic_binding_can_still_inspect_unstable_center(self):
        row=self.bind(dict(self.row,angle=0,scale=1,dx=0,dy=0))
        self.assertIn('route_stability',row)
        self.assertFalse(row['route_stability']['passed'])
        self.assertEqual(row['route_stability']['reason'],'landing_neighbourhood_not_stable')

    def test_stability_requirement_survives_route_rebinding(self):
        class UnstableAtlas(ConstantAtlas):
            def sample(self,region,points,offset):
                values,valid=super().sample(region,points,offset)
                values=np.asarray(values).copy()
                if np.any(np.abs(np.asarray(points)[:,0]-np.asarray(points)[0,0])>.5):
                    values[:,0]=200
                return values,valid
        move=relative_candidate(self.row,[[1,0,0],[0,1,0]],self.game.ctx.board)
        row,budget=bind_candidate(move,UnstableAtlas(),[0,0],self.game.ctx.board,
            self.game.ctx.markers,self.rules,0,1000,require_stable=True)
        self.assertIsNone(row)
        self.assertEqual(budget['reason'],'unstable_landing')

    def test_compromise_family_stability_does_not_require_delta_acceptance(self):
        class SoftWhiteAtlas(ConstantAtlas):
            def sample(self,region,points,offset):
                return np.tile([245,245,245],(len(points),1)),np.ones(len(points),bool)
        rules=[dict(enabled=True,exact=True,colors=['#FFFFFF'],tolerance=0)]*3
        row=dict(self.row,dx=0,dy=0,angle=0,scale=1)
        bound,budget=bind_candidate(row,SoftWhiteAtlas(),[0,0],self.game.ctx.board,
            self.game.ctx.markers,rules,0,1000,require_stable=True)
        self.assertIsNotNone(bound,budget)
        self.assertFalse(bound['accepted'])
        self.assertTrue(bound['route_stability']['passed'])
        self.assertTrue(bound['route_stability']['landing_family_safe'])

    def test_small_landing_family_fluctuation_is_stable(self):
        class SlightFamilyDriftAtlas(ConstantAtlas):
            def sample(self,region,points,offset):
                values,valid=super().sample(region,points,offset)
                values=np.asarray(values).copy()
                # Simulate a one-pixel interpolation drift that remains inside
                # the requested family envelope.  It must not erase every
                # executable route during publication.
                if len(values)>1: values[-1]=[40,55,70]
                return values,valid
        rules=[dict(enabled=True,exact=False,colors=['#112233'],tolerance=8)]*3
        bound,budget=bind_candidate(dict(self.row,dx=0,dy=0,angle=0,scale=1),
            SlightFamilyDriftAtlas(),[0,0],self.game.ctx.board,self.game.ctx.markers,
            rules,0,1000,require_stable=True)
        self.assertIsNotNone(bound,budget)
        self.assertLessEqual(bound['route_stability']['landing_family_maximum'],.30)
        self.assertTrue(bound['route_stability']['passed'])

    def test_unverified_transform_route_is_published_with_feedback_status(self):
        self.atlas.basis=np.eye(2)
        bound,budget=bind_candidate(self.row,self.atlas,[0,0],self.game.ctx.board,
            self.game.ctx.markers,self.rules,0,1000,require_stable=True)
        self.assertIsNotNone(bound,budget)
        self.assertTrue(bound['route_stability']['passed'])
        self.assertFalse(bound['route_stability']['response_profile_verified'])
        self.assertEqual(bound['route_stability']['response_profile'],'unverified_transform')

    def test_live_builder_binds_and_reranks_before_creating_batch(self):
        from atlas_live_adapter import build_current
        rules=[dict(enabled=i==0,exact=False,colors=['#4EC31E'],tolerance=8) for i in range(3)]
        rows=[dict(self.row,id=0,angle=0,scale=1,dx=30.4,dy=0),
              dict(self.row,id=1,angle=0,scale=1,dx=5.4,dy=0,accepted=False,maximum=99)]
        deadline=time.monotonic()+1000
        game=SimpleNamespace(until=deadline,check=lambda:None,geometry=lambda:self.game.ctx.geometry)
        capture=dict(game=game,deadline=deadline,scene=SimpleNamespace(board=self.game.ctx.board,
            markers=self.game.ctx.markers),image='reference')
        report=dict(quality_gate={'passed':True},candidates=rows,
                    runtime=dict(atlas=CoordinateAtlas(),capture_offset=[0,0]))
        with patch('atlas_live_adapter.build_from_capture',return_value=report):
            built=build_current(capture,rules)
        self.assertEqual([row['id'] for row in built['candidates']],[1,0])
        self.assertEqual(built['batch'].best()['id'],1)
        self.assertTrue(all('planned_route' in row for row in built['candidates']))

    def test_protected_choice_executes_prepared_inputs_without_a_second_rebinding(self):
        from atlas_live_adapter import prepare_choice,choice_current
        owner=SimpleNamespace(event=lambda *a,**k:None)
        deadline=time.monotonic()+120
        report=dict(adapter=self.game,selection_deadline=deadline,
                    actual_pose=np.eye(3)[:2].tolist(),pose_reference=self.game.capture(),
                    runtime=dict(atlas=self.atlas,capture_offset=[0,0]))
        proposal=dict(self.row,angle=0,scale=1,dx=7,dy=0)
        prepared,budget=prepare_choice(owner,report,proposal,self.rules)
        self.assertEqual(self.game.sent,[])
        self.assertTrue(budget['allowed'])
        prepared['protect_observed_result']=True
        with patch('atlas_live_adapter.bind_candidate',side_effect=AssertionError('Must use prepared inputs')):
            result=choice_current(owner,report,prepared,self.rules)
        self.assertTrue(result['verified'])
        self.assertEqual(self.game.sent,prepared['planned_route']['inputs'])

    def test_protected_choice_rejects_changed_reference_before_input(self):
        from atlas_live_adapter import prepare_choice,choice_current
        owner=SimpleNamespace(event=lambda *a,**k:None)
        report=dict(adapter=self.game,selection_deadline=time.monotonic()+120,
                    actual_pose=np.eye(3)[:2].tolist(),pose_reference=self.game.capture(),
                    runtime=dict(atlas=self.atlas,capture_offset=[0,0]))
        prepared,_=prepare_choice(owner,report,dict(self.row,angle=0,scale=1,dx=7,dy=0),self.rules)
        prepared['protect_observed_result']=True
        report['actual_pose']=[[1,0,3],[0,1,0]]
        with self.assertRaisesRegex(RuntimeError,'reference changed'):
            choice_current(owner,report,prepared,self.rules)
        self.assertEqual(self.game.sent,[])

    def test_protected_route_cannot_replan_away_from_checkpoint_target(self):
        from atlas_live_adapter import _execute_recorded
        owner=SimpleNamespace(event=lambda *a,**k:None)
        report=dict(adapter=self.game,runtime=dict(atlas=self.atlas,capture_offset=[0,0]))
        row=dict(self.row,protect_observed_result=True)
        batch=CandidateBatch([row],self.game.ctx,1000,clock=lambda:0)
        with patch('atlas_live_adapter.execute_candidate',return_value={}), \
             patch('atlas_live_adapter.reachable_candidates') as search:
            _execute_recorded(owner,report,row,self.rules,batch,self.game.capture())
            self.assertIsNone(self.game.replan(np.eye(3),row,self.rules))
            search.assert_not_called()
        with patch('atlas_live_adapter.time.monotonic',return_value=0):
            self.assertIsNone(self.game.rebind(np.eye(3),row,self.rules))
        self.assertEqual(self.game.sent,[])

    def test_measured_replan_rejects_materially_worse_fallback(self):
        from atlas_live_adapter import _candidate_is_no_worse
        current=dict(self.row,accepted=False,maximum=10.,average=8.)
        close=dict(self.row,accepted=False,maximum=10.5,average=8.2)
        worse=dict(self.row,accepted=False,maximum=25.,average=20.)
        self.assertTrue(_candidate_is_no_worse(close,current))
        self.assertFalse(_candidate_is_no_worse(worse,current))

    def test_live_builder_records_route_binding_time(self):
        from atlas_live_adapter import build_current
        deadline=time.monotonic()+1000
        game=SimpleNamespace(until=deadline,check=lambda:None,geometry=lambda:self.game.ctx.geometry)
        capture=dict(game=game,deadline=deadline,scene=SimpleNamespace(board=self.game.ctx.board,
            markers=self.game.ctx.markers),image='reference')
        report=dict(quality_gate={'passed':True},candidates=[dict(self.row,angle=0,scale=1)],
                    runtime=dict(atlas=self.atlas,capture_offset=[0,0]))
        with patch('atlas_live_adapter.build_from_capture',return_value=report):
            built=build_current(capture,self.rules)
        self.assertIn('route_binding_seconds',built['search_diagnostics'])
        self.assertGreaterEqual(built['search_diagnostics']['route_binding_seconds'],0.)

    def test_live_builder_falls_back_to_current_pose_translation_when_routes_fail(self):
        from atlas_live_adapter import build_current
        deadline=time.monotonic()+1000
        game=SimpleNamespace(until=deadline,check=lambda:None,geometry=lambda:self.game.ctx.geometry)
        capture=dict(game=game,deadline=deadline,scene=SimpleNamespace(board=self.game.ctx.board,
            markers=self.game.ctx.markers),image='reference')
        report=dict(quality_gate={'passed':True},candidates=[dict(self.row,angle=0,scale=1.01**-7.5)],
                    runtime=dict(atlas=self.atlas,capture_offset=[0,0]))
        fallback=[dict(self.row,id=0,angle=0,scale=1,dx=7,dy=0)]
        with patch('atlas_live_adapter.build_from_capture',return_value=report), \
             patch('atlas_live_adapter.reachable_candidates',return_value=fallback) as search:
            built=build_current(capture,self.rules)
        self.assertEqual(len(built['candidates']),1)
        self.assertEqual(built['candidates'][0]['dx'],7)
        np.testing.assert_array_equal(search.call_args.args[2],np.eye(3))
        self.assertEqual(built['candidates'][0]['execution_budget']['actions']['rotate'],0)

    def test_live_builder_suppresses_unverified_transform_and_uses_translation_fallback(self):
        from atlas_live_adapter import build_current
        deadline=time.monotonic()+1000
        game=SimpleNamespace(until=deadline,check=lambda:None,geometry=lambda:self.game.ctx.geometry)
        capture=dict(game=game,deadline=deadline,
            scene=SimpleNamespace(board=self.game.ctx.board,markers=self.game.ctx.markers),
            image='reference')
        # The first candidate would require a rotation and wheel response.
        # Its forecast is valid geometrically but the game response profile is
        # intentionally unverified, so publication must fall back to a
        # measured-pose translation candidate.
        transform=dict(self.row,id=0,angle=24,scale=1.01**-4,dx=85,dy=-45)
        fallback=dict(self.row,id=1,angle=0,scale=1,dx=7,dy=0)
        report=dict(quality_gate={'passed':True},candidates=[transform],
                    runtime=dict(atlas=self.atlas,capture_offset=[0,0]))
        with patch('atlas_live_adapter.build_from_capture',return_value=report), \
             patch('atlas_live_adapter.reachable_candidates',return_value=[fallback]):
            built=build_current(capture,self.rules)
        diagnostics=built['search_diagnostics']
        self.assertTrue(diagnostics['transform_routes_suppressed'])
        self.assertEqual(diagnostics['transform_routes_suppressed_count'],1)
        self.assertTrue(built['candidates'])
        for row in built['candidates']:
            actions=(row.get('execution_budget') or {}).get('actions') or {}
            self.assertEqual(int(actions.get('rotate',0)),0)
            self.assertEqual(int(actions.get('wheel',0)),0)

    def test_live_builder_uses_cross_family_after_searching_executable_same_family_rows(self):
        from atlas_live_adapter import build_current
        class CloseBlueAtlas(ConstantAtlas):
            def sample(self,region,points,offset):
                values,valid=super().sample(region,points,offset)
                values=np.asarray(values).copy(); values[:]=[80,80,150]
                return values,valid
        rules=[dict(enabled=True,exact=False,colors=['#0000FF'],tolerance=8)]*3
        deadline=time.monotonic()+1000
        game=SimpleNamespace(until=deadline,check=lambda:None,geometry=lambda:self.game.ctx.geometry)
        capture=dict(game=game,deadline=deadline,
            scene=SimpleNamespace(board=self.game.ctx.board,markers=self.game.ctx.markers),
            image='reference')
        row=dict(self.row,id=0,angle=0,scale=1,dx=0,dy=0,
                 family_consistent=False,family_maximum=.2,accepted=False)
        report=dict(quality_gate={'passed':True},candidates=[row],
                    runtime=dict(atlas=CloseBlueAtlas(),capture_offset=[0,0]))
        with patch('atlas_live_adapter.build_from_capture',return_value=report):
            built=build_current(capture,rules)
        self.assertEqual(len(built['candidates']),1)
        self.assertTrue(built['candidates'][0]['cross_family_fallback'])
        self.assertEqual(built['search_diagnostics']['cross_family_fallback_count'],1)


if __name__=='__main__':unittest.main()
