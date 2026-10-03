import unittest
import numpy as np
from atlas_execution import CandidateBatch,execute_candidate
from test_atlas_execution import Fake
from test_atlas_similarity_execution import SimilarityGame
from atlas_bound_route import bind_candidate,bound_motion,forecast_gesture
from test_atlas_bound_route import ConstantAtlas


class ExecutionReturnGuardTests(unittest.TestCase):
    def setUp(self):
        self.adapter=Fake()
        self.row=dict(id=0,dx=300,dy=-50,angle=0,scale=1,
                      colors=['#112233']*3,deltas=[0.]*3)
        self.rules=[dict(enabled=True,colors=['#112233'],exact=True,tolerance=0)]*3
        self.batch=CandidateBatch([self.row],self.adapter.ctx,100,clock=lambda:0)
        self.events=[]

    def execute(self):
        return execute_candidate(self.adapter,self.batch,self.batch.id,0,np.zeros(2),
            self.rules,clock=lambda:0,emit=lambda k,d:self.events.append((k,d)))

    def test_rejected_return_budget_prevents_the_first_input(self):
        calls=[]
        def guard(actual,upcoming):
            calls.append((actual.copy(),upcoming))
            return dict(allowed=False,reason='insufficient_return_time')
        self.adapter.return_guard=guard
        with self.assertRaisesRegex(RuntimeError,'Return reserve'):
            self.execute()
        self.assertEqual(self.adapter.moves,[])
        self.assertTrue(self.adapter.released)
        np.testing.assert_array_equal(calls[0][0],np.eye(3))
        self.assertGreaterEqual(calls[0][1],1.75)
        blocked=next(d for k,d in self.events if k=='atlas_return_reserved')
        self.assertFalse(blocked['input_sent'])

    def test_guard_rechecks_after_each_observed_action_and_keeps_measured_pose(self):
        calls=[]
        def guard(actual,upcoming):
            calls.append(actual.copy())
            return dict(allowed=len(calls)==1,reason='insufficient_return_time')
        self.adapter.return_guard=guard
        self.adapter.recovery_enabled=True
        result=self.execute()
        self.assertEqual(len(self.adapter.moves),1)
        self.assertEqual(len(calls),2)
        np.testing.assert_allclose(calls[1][:2,2],self.adapter.pose)
        np.testing.assert_allclose(result['actual_pose'],calls[1][:2])
        self.assertTrue(result['recovered'])
        self.assertTrue(result['pose_reliable'])
        self.assertFalse(result['positioning_complete'])
        self.assertTrue(self.adapter.released)

    def test_f9_in_guard_cannot_trigger_input_or_recovery(self):
        def stop(actual,upcoming):raise InterruptedError('F9')
        self.adapter.return_guard=stop
        self.adapter.recovery_enabled=True
        with self.assertRaises(InterruptedError):self.execute()
        self.assertEqual(self.adapter.moves,[])
        self.assertEqual(self.adapter.reads,0)
        self.assertTrue(self.adapter.released)

    def test_projected_pose_uses_down_direction_for_first_bound_wheel(self):
        adapter=SimilarityGame()
        row=dict(id=0,dx=0.,dy=0.,angle=0.,scale=np.exp(-.013*4),
                 zoom_log_step=.013,zoom_log_step_up=.008,
                 colors=['#112233']*3,deltas=[0.]*3)
        rules=[dict(enabled=True,colors=['#112233'],exact=False,tolerance=8)]*3
        row,budget=bind_candidate(row,ConstantAtlas(),[0,0],adapter.ctx.board,
                                 adapter.ctx.markers,rules,0,100)
        self.assertIsNotNone(row,budget)
        gesture=bound_motion(row,adapter.ctx.board,adapter.ctx.markers)['gestures'][0]
        self.assertEqual(gesture.kind,'wheel')
        self.assertEqual(gesture.wheel_steps,-4)
        batch=CandidateBatch([row],adapter.ctx,100,clock=lambda:0)
        received=[]
        def guard(actual,upcoming,projected_pose=None):
            received.append(projected_pose.copy())
            return dict(allowed=False,reason='test')
        adapter.return_guard=guard
        with self.assertRaisesRegex(RuntimeError,'Return reserve'):
            execute_candidate(adapter,batch,batch.id,0,adapter.capture(),rules,
                              clock=lambda:0)
        self.assertEqual(len(received),1)
        # The first wheel action is negative; its projection must use the
        # measured DOWN tick, even though last_zoom_direction is still zero.
        expected=forecast_gesture(gesture,adapter.ctx.board,.013,.008)
        np.testing.assert_allclose(received[0],expected@np.eye(3),atol=1e-10)
        self.assertLess(received[0][0,0],.96)
        self.assertEqual(adapter.actions,[])
        self.assertEqual(adapter.releases,1)


if __name__=='__main__':unittest.main()
