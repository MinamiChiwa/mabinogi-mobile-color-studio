import copy
import unittest
import numpy as np
from atlas_pose import homogeneous, candidate_pose
from atlas_pose_scoring import score_pose, rescore_candidate
from atlas_execution import CandidateBatch, execute_candidate, reposition_budget
from test_atlas_similarity_execution import SimilarityGame


class CoordinateAtlas:
    """Independent analytic colours for checking coordinate conventions."""
    def __init__(self):self.calls=[]
    def sample(self,region,points,offset):
        self.calls.append(region)
        source=np.asarray(points)-offset
        colors=np.c_[source,np.full(len(source),30+region)]
        return colors,(source[:,0]>=0)&(source[:,1]>=0)


class PoseScoringTests(unittest.TestCase):
    def setUp(self):
        self.board=(100,200,400,500)
        self.markers=[[150,260],[170,280],[190,300]]
        self.rules=[dict(enabled=True,exact=i<2,colors=['#FFFFFF'],tolerance=200)
                    for i in range(3)]
        self.atlas=CoordinateAtlas()
        self.row=dict(id=9,dx=0,dy=0,colors=['#FFFFFF']*3,deltas=[0]*3,
                      accepted=True,exact_matches=2,exact_maximum=0,
                      landing_safe=True,landing_maximum=0,landing_radius=1,
                      input_route=[{'obsolete':True}],execution_budget={'old':True})

    def test_changed_pose_recomputes_colors_exact_metrics_and_clears_old_route(self):
        original=copy.deepcopy(self.row)
        pose=homogeneous([[1,0,10],[0,1,20]])
        row=rescore_candidate(self.atlas,[5,7],self.row,pose,self.markers,
                              self.board,self.rules,pose_source='measured_final_pose')
        self.assertEqual(row['colors'],['#23211E','#37351F','#4B4920'])
        self.assertEqual(row['exact_matches'],0)
        self.assertGreater(row['exact_maximum'],0)
        self.assertFalse(row['accepted'])
        self.assertFalse(row['verified'])
        self.assertEqual(self.row,original)
        for key in ('landing_safe','landing_maximum','landing_radius','input_route','execution_budget'):
            self.assertNotIn(key,row)

    def test_rotated_scaled_reference_composes_in_execution_order(self):
        reference=homogeneous([[0,-2,100],[2,0,0]])
        final=homogeneous([[1,0,10],[0,1,20]])
        row=rescore_candidate(self.atlas,[5,7],self.row,final,self.markers,
                              self.board,self.rules,pose_source='test',reference_pose=reference)
        self.assertEqual(row['colors'],['#0F171E','#190D1F','#230320'])
        np.testing.assert_array_equal(row['prediction_pose'],(final@reference)[:2])
        np.testing.assert_array_equal(candidate_pose(row,self.board),final)

    def test_unsupported_neighbour_is_not_accepted_or_assigned_zero_error(self):
        self.rules[1]['enabled']=False;self.rules[2]['enabled']=False
        self.rules[0].update(exact=False,tolerance=200)
        score=score_pose(self.atlas,[0,0],np.eye(3),self.markers,self.board,
                         self.rules,screen_offsets=((0,0),(-100,0)))
        self.assertEqual(self.atlas.calls,[0])
        self.assertEqual(score['pose_samples']['supported'],[True,False])
        self.assertEqual(score['pose_samples']['accepted'],[True,False])
        self.assertIsNone(score['pose_samples']['maximum'][1])
        self.assertIsNone(score['pose_samples']['worst_maximum'])
        self.assertFalse(score['pose_samples']['complete'])
        self.assertIsNone(score['colors'][1])

    def test_unsupported_centre_and_all_disabled_return_no_prediction(self):
        self.assertIsNone(score_pose(self.atlas,[500,0],np.eye(3),self.markers,
                                     self.board,self.rules))
        for rule in self.rules:rule['enabled']=False
        self.assertIsNone(score_pose(self.atlas,[0,0],np.eye(3),self.markers,
                                     self.board,self.rules))

    def test_invalid_geometry_and_cancellation(self):
        with self.assertRaises(ValueError):
            score_pose(self.atlas,[0,0],np.eye(3),self.markers,self.board,self.rules,
                       screen_offsets=((1,0),))
        def stop():raise InterruptedError('F9')
        with self.assertRaises(InterruptedError):
            score_pose(self.atlas,[0,0],np.eye(3),self.markers,self.board,self.rules,check=stop)

    def test_budget_endpoint_is_exposed_without_certifying_game_response(self):
        budget=reposition_budget(dict(dx=5.4,dy=0),0,100,self.board,markers=self.markers)
        self.assertTrue(budget['allowed'])
        np.testing.assert_array_equal(budget['planned_pose'],[[1,0,5],[0,1,0]])
        self.assertEqual(budget['response_model'],'grouped_integer_arc_and_directional_zoom')
        self.assertFalse(budget['game_response_verified'])

    def test_executor_uses_final_measured_pose_and_game_hex_remains_authoritative(self):
        game=SimilarityGame();observed=[];events=[]
        row=dict(self.row,dx=5,dy=0,angle=0,scale=1)
        rules=[dict(enabled=True,colors=['#112233'],exact=False,tolerance=8)]*3
        def rescore(actual,current,active_rules):
            observed.append(actual.copy())
            return dict(current,colors=['#000000']*3,deltas=[50]*3,accepted=False,
                        prediction_pose_source='measured_final_pose')
        game.rescore=rescore
        batch=CandidateBatch([row],game.ctx,100,clock=lambda:0)
        result=execute_candidate(game,batch,batch.id,9,game.capture(),rules,clock=lambda:0,
                                 emit=lambda k,d:events.append((k,d)))
        np.testing.assert_allclose(observed[0],game.pose)
        self.assertEqual(result['predicted_colors'],['#000000']*3)
        self.assertEqual(result['actual_colors'],['#112233']*3)
        self.assertTrue(result['accepted'])
        self.assertFalse(result['predicted_accepted'])
        self.assertEqual(game.reads,2)
        self.assertEqual(len([k for k,d in events if k=='atlas_prediction_updated']),1)

    def test_executor_does_not_reuse_prediction_when_measured_pose_has_no_support(self):
        game=SimilarityGame();game.rescore=lambda *a:None
        row=dict(self.row,dx=0,dy=0,angle=0,scale=1)
        rules=[dict(enabled=True,colors=['#112233'],exact=False,tolerance=8)]*3
        batch=CandidateBatch([row],game.ctx,100,clock=lambda:0)
        result=execute_candidate(game,batch,batch.id,9,game.capture(),rules,clock=lambda:0)
        self.assertEqual(result['predicted_colors'],[None]*3)
        self.assertEqual(result['prediction_errors'],[None]*3)
        self.assertTrue(result['accepted'])
        self.assertEqual(game.releases,1)

    def test_rescore_failure_preserves_game_hex_but_f9_still_propagates(self):
        for interrupt in (False,True):
            with self.subTest(interrupt=interrupt):
                game=SimilarityGame()
                def fail(*args):
                    if interrupt:raise InterruptedError('F9')
                    raise ValueError('unavailable atlas')
                game.rescore=fail
                row=dict(self.row,dx=0,dy=0,angle=0,scale=1)
                rules=[dict(enabled=True,colors=['#112233'],exact=False,tolerance=8)]*3
                batch=CandidateBatch([row],game.ctx,100,clock=lambda:0)
                def execute():
                    return execute_candidate(game,batch,batch.id,9,game.capture(),rules,clock=lambda:0)
                if interrupt:
                    with self.assertRaises(InterruptedError):execute()
                else:
                    result=execute()
                    self.assertTrue(result['accepted'])
                    self.assertEqual(result['prediction_pose_source'],'rescore_failed')
                    self.assertEqual(result['predicted_colors'],[None]*3)
                self.assertEqual(game.releases,1)

    def test_incomplete_route_recovery_never_compares_with_unreached_colors(self):
        game=SimilarityGame();game.recovery_enabled=True;game.tick=0
        row=dict(self.row,dx=0,dy=0,angle=0,scale=.9)
        rules=[dict(enabled=True,colors=['#112233'],exact=False,tolerance=8)]*3
        batch=CandidateBatch([row],game.ctx,100,clock=lambda:0)
        result=execute_candidate(game,batch,batch.id,9,game.capture(),rules,clock=lambda:0)
        self.assertTrue(result['recovered'])
        self.assertEqual(result['predicted_colors'],[None]*3)
        self.assertEqual(result['prediction_errors'],[None]*3)
        self.assertEqual(result['proposal_colors'],['#FFFFFF']*3)
        self.assertEqual(result['actual_colors'],['#112233']*3)
        self.assertFalse(result['accepted'])

    def test_live_callback_uses_capture_offset_and_previous_verified_reference(self):
        from atlas_live_adapter import _execute_recorded
        from unittest.mock import patch
        game=SimilarityGame()
        game.ctx=type(game.ctx)(game.ctx.session,game.ctx.geometry,self.board,tuple(map(tuple,self.markers)))
        previous=homogeneous([[0,-2,100],[2,0,0]])
        report=dict(adapter=game,actual_pose=previous[:2].tolist(),
                    runtime=dict(atlas=self.atlas,capture_offset=[5,7]))
        batch=CandidateBatch([self.row],game.ctx,100,clock=lambda:0)
        final=homogeneous([[1,0,10],[0,1,20]])
        with patch('atlas_live_adapter.execute_candidate',return_value={}) as execute:
            _execute_recorded(type('Owner',(),{'event':lambda *a,**k:None})(),
                              report,self.row,self.rules,batch,np.eye(3))
            refreshed=game.rescore(final,self.row,self.rules)
        self.assertEqual(refreshed['colors'],['#0F171E','#190D1F','#230320'])
        self.assertEqual(refreshed['prediction_pose_source'],'measured_final_pose')
        self.assertEqual(execute.call_count,1)


if __name__=='__main__':unittest.main()
