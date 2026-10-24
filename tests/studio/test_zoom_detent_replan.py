import unittest
from unittest.mock import patch
import numpy as np
from atlas_replan import nearby_zoom_detent_proposals,bind_nearby_zoom_detents
from atlas_bound_route import bind_candidate
from atlas_bound_route import bound_motion
from atlas_execution import reposition_budget
from atlas_pose import homogeneous,candidate_pose,relative_candidate
from atlas_pose_scoring import score_pose


class TargetColorAtlas:
    """Smooth gray islands centered at the old target's three source points."""
    def __init__(self,source):self.source=source
    def sample(self,region,points,offset):
        distance=np.linalg.norm(np.asarray(points)-self.source[region],axis=1)
        values=np.tile([128.,128.,128.],(len(points),1))
        values[:,0]+=np.minimum(120.,distance*10)
        return values,np.ones(len(points),bool)


class ZoomDetentReplanTests(unittest.TestCase):
    def setUp(self):
        self.board=(10,15,550,555)
        self.markers=np.array([[100.,285.],[280.,285.],[460.,285.]])
        self.rules=[dict(enabled=True,exact=False,colors=['#808080'],tolerance=8)]*3
        self.offset=[5.,10.]
        self.actual_tick=.010016135034727867
        actual_scale=np.exp(-4*self.actual_tick)
        self.actual=homogeneous([[actual_scale,0,270*(1-actual_scale)],
                                 [0,actual_scale,270*(1-actual_scale)]])
        self.candidate=dict(id=9,dx=25,dy=-10,angle=0,
            scale=.7817544337900164,zoom_log_step=self.actual_tick,
            zoom_log_step_up=.00962292514825616,
            colors=['#FFFFFF']*3,deltas=[0.]*3,accepted=True,maximum=0.,average=0.)
        target=candidate_pose(self.candidate,self.board)
        source=(self.markers-self.board[:2]-target[:2,2])@np.linalg.inv(target[:2,:2]).T
        self.atlas=TargetColorAtlas(source)

    def test_changed_wheel_response_binds_and_rescores_an_actual_neighbor(self):
        old=reposition_budget(relative_candidate(self.candidate,self.actual,self.board),
            0,100,self.board,markers=self.markers)
        self.assertFalse(old['allowed'])
        self.assertEqual(old['reason'],'unreachable_scale')
        row,budget=bind_nearby_zoom_detents(self.candidate,self.actual,self.atlas,
            self.offset,self.board,self.markers,self.rules,0,100,
            wheel_direction=-1,clock=lambda:0)
        self.assertIsNotNone(row,budget)
        self.assertTrue(budget['allowed'])
        self.assertTrue(row['detent_rescored'])
        self.assertEqual(row['prediction_pose_source'],'bound_integer_route_forecast')
        self.assertNotEqual(row['colors'],self.candidate['colors'])
        gestures=bound_motion(row,self.board,self.markers)['gestures']
        wheel=[g.wheel_steps for g in gestures if g.kind=='wheel']
        self.assertTrue(wheel)
        self.assertTrue(all(-4<=steps<0 for steps in wheel),wheel)
        self.assertEqual(row['wheel_steps'],sum(wheel))
        endpoint=candidate_pose(row,self.board)@self.actual
        self.assertAlmostEqual(np.hypot(endpoint[0,0],endpoint[1,0]),
            np.hypot(self.actual[0,0],self.actual[1,0])*
            np.exp(row['wheel_steps']*self.actual_tick),places=12)
        score=score_pose(self.atlas,self.offset,endpoint,self.markers,self.board,self.rules)
        self.assertEqual(row['colors'],score['colors'])
        self.assertEqual(row['deltas'],score['deltas'])

    def test_rebased_choice_prediction_samples_acquisition_coordinates(self):
        theta=.3
        reference=homogeneous([[np.cos(theta),-np.sin(theta),9],
                               [np.sin(theta),np.cos(theta),-5]])
        row,budget=bind_nearby_zoom_detents(self.candidate,self.actual,self.atlas,
            self.offset,self.board,self.markers,self.rules,0,100,
            reference_pose=reference,wheel_direction=-1,clock=lambda:0)
        self.assertTrue(budget['allowed'])
        endpoint=candidate_pose(row,self.board)@self.actual@reference
        score=score_pose(self.atlas,self.offset,endpoint,self.markers,self.board,self.rules)
        self.assertEqual(row['colors'],score['colors'])
        np.testing.assert_allclose(row['prediction_pose'],endpoint[:2])

    def test_previous_wheel_direction_forbids_reverse_detent_proposals(self):
        candidate=dict(self.candidate,scale=1.02)
        rows=nearby_zoom_detent_proposals(candidate,self.actual,self.board,
            self.markers,self.rules,wheel_direction=-1)
        self.assertTrue(rows)
        self.assertTrue(all(r['detent_wheel_steps']==0 for r in rows))
        self.assertTrue(all(r['search_space']=='measured_zoom_detent' for r in rows))
        self.assertTrue(all('planned_route' not in r for r in rows))

    def test_cancellation_does_not_compile_or_send_a_route(self):
        def stop():raise InterruptedError('F9')
        with patch('atlas_bound_route.bind_candidate') as bind, \
             self.assertRaises(InterruptedError):
            bind_nearby_zoom_detents(self.candidate,self.actual,self.atlas,
                self.offset,self.board,self.markers,self.rules,0,100,check=stop)
        bind.assert_not_called()

    def test_scoring_time_is_repriced_before_returning_a_route(self):
        current=[0.]
        def slow_bind(*args,**kwargs):
            result=bind_candidate(*args,**kwargs)
            current[0]=100.
            return result
        with patch('atlas_bound_route.bind_candidate',side_effect=slow_bind):
            row,budget=bind_nearby_zoom_detents(self.candidate,self.actual,self.atlas,
                self.offset,self.board,self.markers,self.rules,0,100,
                wheel_direction=-1,clock=lambda:current[0])
        self.assertIsNone(row)
        self.assertIn('deadline',budget['rejected_reasons'])

    def test_missing_measured_response_has_clear_validation_error(self):
        candidate=dict(self.candidate,zoom_log_step=None)
        with self.assertRaisesRegex(ValueError,'measured directional wheel response'):
            nearby_zoom_detent_proposals(candidate,self.actual,self.board,
                                         self.markers,self.rules,wheel_direction=-1)


if __name__=='__main__':unittest.main()
