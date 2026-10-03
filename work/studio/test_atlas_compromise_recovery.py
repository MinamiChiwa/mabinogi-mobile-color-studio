import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from atlas_bound_route import bind_candidate
from atlas_execution import CandidateBatch, execute_candidate
from atlas_live_adapter import build_current, default_current
from atlas_pose_scoring import rescore_candidate
from candidate_ranking import candidate_rank, candidate_quality, candidate_order
from test_atlas_bound_route import ConstantAtlas, IntegerGame


class CompromiseRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.game=IntegerGame()
        self.rules=[dict(enabled=True,exact=False,colors=['#FFFFFF'],tolerance=8)]*3
        self.row=dict(id=0,dx=20,dy=0,angle=0,scale=1,colors=['#FFFFFF']*3,
                      deltas=[0]*3,maximum=0,average=0,accepted=True)

    def build(self,rows,atlas):
        deadline=time.monotonic()+100
        game=SimpleNamespace(until=deadline,check=lambda:None,geometry=lambda:self.game.ctx.geometry)
        capture=dict(game=game,deadline=deadline,image=None,
            scene=SimpleNamespace(board=self.game.ctx.board,markers=self.game.ctx.markers))
        report=dict(quality_gate=dict(passed=True),candidates=rows,
                    runtime=dict(atlas=atlas,capture_offset=[0,0]))
        with patch('atlas_live_adapter.build_from_capture',return_value=report):
            return build_current(capture,self.rules)

    def test_color_neighbourhood_is_a_preference_not_an_input_failure(self):
        class BorderAtlas(ConstantAtlas):
            def sample(self,region,points,offset):
                values=np.tile([255,255,255],(len(points),1))
                values[1:]=[200,100,100]
                return values,np.ones(len(points),bool)
        args=(self.row,BorderAtlas(),[0,0],self.game.ctx.board,self.game.ctx.markers,self.rules,0,100)
        strict,budget=bind_candidate(*args,require_stable=True)
        self.assertIsNone(strict)
        row,budget=bind_candidate(*args,require_stable=True,allow_color_compromise=True)
        self.assertTrue(budget['allowed'])
        self.assertTrue(row['route_stability']['motion_passed'])
        self.assertTrue(row['route_stability']['samples_complete'])
        self.assertFalse(row['route_stability']['quality_preferred'])
        self.assertTrue(row['landing_uncertain'])
        self.assertFalse(row['landing_safe'])

    def test_color_compromise_still_requires_supported_pixels(self):
        class MissingAtlas(ConstantAtlas):
            def sample(self,region,points,offset):
                values,valid=super().sample(region,points,offset)
                valid[:]=False
                return values,valid
        row,budget=bind_candidate(self.row,MissingAtlas(),[0,0],self.game.ctx.board,
            self.game.ctx.markers,self.rules,0,100,require_stable=True,allow_color_compromise=True)
        self.assertIsNone(row)
        self.assertEqual(budget['reason'],'unsupported_endpoint')

    def test_unreachable_same_family_proposal_does_not_block_cross_family(self):
        invalid=dict(self.row,scale=1.01**-7.5,family_consistent=True)
        cross=dict(self.row,id=1,family_consistent=False)
        result=self.build([invalid,cross],ConstantAtlas())
        self.assertTrue(result['candidates'])
        self.assertTrue(result['candidates'][0]['cross_family_fallback'])
        self.assertFalse(result['candidates'][0]['accepted'])
        self.assertTrue(result['candidates'][0]['execution_budget']['allowed'])

    def test_empty_initial_search_still_searches_integer_translations(self):
        result=self.build([],ConstantAtlas())
        self.assertTrue(result['candidates'])
        self.assertEqual(result['candidates'][0]['execution_budget']['actions']['rotate'],0)
        self.assertEqual(result['candidates'][0]['execution_budget']['actions']['wheel'],0)

    def test_bound_candidates_keep_better_cross_family_endpoint_in_the_ranking(self):
        same=dict(self.row,id=0,colors=['#EEEEEE']*3,accepted=False,
                  family_consistent=True,maximum=20.,average=20.,
                  landing_safe=False,landing_maximum=50.)
        closer=dict(self.row,id=1,colors=['#DDDDEE']*3,accepted=False,
                    family_consistent=False,family_maximum=.1,
                    maximum=12.,average=12.,landing_safe=False,landing_maximum=13.)
        def binding(candidate,*args,**kwargs):
            return dict(candidate),dict(allowed=True,needed=4.,actions=dict(drag=1,rotate=0,wheel=0))
        with patch('atlas_live_adapter.bind_candidate',side_effect=binding):
            result=self.build([same,closer],ConstantAtlas())
        self.assertEqual([r['id'] for r in result['candidates']],[1,0])

    def test_translation_alternative_keeps_independently_bound_transform_routes(self):
        transform=dict(self.row,id=0,angle=8,scale=.9,dx=20,dy=0,
                       family_consistent=True,accepted=True)
        translation=dict(self.row,id=1,angle=0,scale=1,dx=8,dy=0,
                         family_consistent=True,accepted=False,colors=['#EEEEEE']*3)
        def binding(candidate,*args,**kwargs):
            row=dict(candidate,
                     route_stability=dict(quality_preferred=candidate.get('angle',0)==0),
                     execution_budget=dict(actions=dict(rotate=int(bool(candidate.get('angle',0))),
                                                        wheel=0,drag=1)))
            return row,dict(allowed=True,needed=4.,actions=row['execution_budget']['actions'])
        with patch('atlas_live_adapter.bind_candidate',side_effect=binding):
            result=self.build([transform,translation],ConstantAtlas())
        self.assertTrue(result['candidates'])
        self.assertIn(0,[row['id'] for row in result['candidates']])
        self.assertIn(1,[row['id'] for row in result['candidates']])
        self.assertFalse(result['search_diagnostics']['transform_routes_suppressed'])
        self.assertGreater(result['search_diagnostics']['stable_translation_count'],0)

    def test_rescoring_drops_old_neighbourhood_and_route_claims(self):
        previous=dict(self.row,landing_family_maximum=0,landing_family_safe=True,
            route_stability=dict(passed=True),cross_family_fallback=True,landing_uncertain=True)
        refreshed=rescore_candidate(ConstantAtlas(),[0,0],previous,np.eye(3),
            self.game.ctx.markers,self.game.ctx.board,self.rules,pose_source='test')
        for field in ('landing_family_maximum','landing_family_safe','route_stability',
                      'cross_family_fallback','landing_uncertain'):
            self.assertNotIn(field,refreshed)

    def test_mixed_fallback_scalar_vector_and_observed_order_agree(self):
        rng=np.random.default_rng(929)
        rows=[dict(id=i,exact_matches=int(rng.integers(3)),maximum=float(rng.uniform(2,70)),
                   average=float(rng.uniform(1,40)),exact_maximum=float(rng.uniform(1,60)),
                   exact_average=float(rng.uniform(1,30)),family_maximum=float(rng.choice([0,.1,1.])),
                   family_average=float(rng.uniform(0,1)),accepted=False,dx=i,dy=0,
                   cross_family_fallback=bool(i%2)) for i in range(60)]
        metric=lambda key:[r[key] for r in rows]
        order=candidate_order(metric('exact_matches'),metric('maximum'),metric('average'),
            metric('accepted'),False,metric('maximum'),metric('dx'),
            exact_maximum=metric('exact_maximum'),exact_average=metric('exact_average'),
            family_maximum=metric('family_maximum'),family_average=metric('family_average'))
        expected=[r['id'] for r in sorted(rows,key=candidate_rank)]
        self.assertEqual(order.tolist(),expected)
        self.assertEqual([r['id'] for r in sorted(rows,key=candidate_quality)],expected)

    def test_transient_registration_failure_can_recover_a_measured_pose(self):
        game=self.game;game.recovery_enabled=True;motion=game.motion
        calls=[]
        def transient(a,b):
            calls.append(1)
            if len(calls)==2:return None
            return motion(a,b)
        game.motion=transient
        batch=CandidateBatch([self.row],game.ctx,100,clock=lambda:0)
        result=execute_candidate(game,batch,batch.id,0,game.capture(),self.rules,clock=lambda:0)
        self.assertTrue(result['recovered']);self.assertTrue(result['pose_reliable'])
        np.testing.assert_allclose(result['actual_pose'],game.pose[:2])
        self.assertFalse(result['accepted'])
        self.assertEqual(len(game.actions),1)

    def test_persistent_registration_failure_does_not_invent_a_pose(self):
        game=self.game;game.recovery_enabled=True;motion=game.motion
        game.motion=lambda a,b:None if game.actions else motion(a,b)
        batch=CandidateBatch([self.row],game.ctx,100,clock=lambda:0)
        result=execute_candidate(game,batch,batch.id,0,game.capture(),self.rules,clock=lambda:0)
        self.assertTrue(result['recovered']);self.assertFalse(result['pose_reliable'])
        self.assertIsNone(result['actual_pose'])
        self.assertEqual(len(game.actions),1)

    def test_failed_initial_read_remeasures_from_reference_without_input(self):
        game=self.game;game.recovery_enabled=True;motion=game.motion;calls=[]
        def transient(a,b):
            calls.append(1)
            return None if len(calls)==1 else motion(a,b)
        game.motion=transient
        reference=game.capture()
        game.pose=np.array([[1,0,13],[0,1,7],[0,0,1.]])
        batch=CandidateBatch([self.row],game.ctx,100,clock=lambda:0)
        result=execute_candidate(game,batch,batch.id,0,reference,self.rules,clock=lambda:0)
        self.assertTrue(result['pose_reliable'])
        np.testing.assert_allclose(result['actual_pose'],game.pose[:2])
        self.assertEqual(game.actions,[])

    def test_f9_never_reads_or_retries_even_when_recovery_enabled(self):
        game=self.game;game.recovery_enabled=True;perform=game.perform_gesture
        def stop(gesture):perform(gesture);game.stop=True
        game.perform_gesture=stop
        batch=CandidateBatch([self.row],game.ctx,100,clock=lambda:0)
        with self.assertRaises(InterruptedError):
            execute_candidate(game,batch,batch.id,0,game.capture(),self.rules,clock=lambda:0)
        self.assertEqual(game.reads,0);self.assertEqual(len(game.actions),1)
        self.assertEqual(game.releases,1)

    def recovery_report(self):
        self.game.verified_frame=np.eye(3)
        return dict(adapter=self.game,batch=SimpleNamespace(),reference=np.eye(3),
            runtime=dict(atlas=ConstantAtlas(),capture_offset=[0,0]),
            board=self.game.ctx.board,markers=self.game.ctx.markers,
            selection_deadline=time.monotonic()+100)

    def test_registered_failure_prepares_translation_without_losing_checkpoint(self):
        recovered=dict(actual_pose=[[0,-1,100],[1,0,50]],verified=True,recovered=True,
            pose_reliable=True,accepted=False,maximum=150,average=150,family_maximum=9.)
        owner=SimpleNamespace(event=lambda *a,**k:None)
        report=self.recovery_report()
        with patch('atlas_live_adapter._execute_recorded',return_value=recovered), \
             patch('atlas_live_adapter.reachable_candidates',return_value=[self.row]), \
             patch('atlas_live_adapter.choice_current') as choice:
            self.assertIs(default_current(owner,report,self.row,self.rules),recovered)
        choice.assert_not_called()
        move=report['recovery_candidates'][0]
        self.assertNotEqual(move['id'],self.row['id'])
        self.assertNotIn('planned_route',move)
        np.testing.assert_allclose(move['matrix'],[[0,-1,120],[1,0,50]])
        self.assertEqual(report['actual_pose'],recovered['actual_pose'])

    def test_failed_recovery_search_keeps_current_measured_colors(self):
        recovered=dict(actual_pose=np.eye(3)[:2].tolist(),verified=True,recovered=True,
            pose_reliable=True,accepted=False,maximum=150,average=150,family_maximum=9.)
        owner=SimpleNamespace(event=lambda *a,**k:None)
        with patch('atlas_live_adapter._execute_recorded',return_value=recovered), \
             patch('atlas_live_adapter.reachable_candidates',side_effect=RuntimeError('search failed')), \
             patch('atlas_live_adapter.choice_current') as choice:
            self.assertIs(default_current(owner,self.recovery_report(),self.row,self.rules),recovered)
        choice.assert_not_called()


if __name__=='__main__':unittest.main()
