import unittest
import time
import numpy as np
from atlas_execution import CandidateBatch, Context, execute_candidate, CandidateExpired, reposition_budget
from atlas_pose import candidate_pose, homogeneous, marker_errors, relative_candidate


class SimilarityGame:
    def __init__(self):
        self.ctx=Context('test',(40,80,1280,960),(714,425,1212,923),
                         ((797,620),(963,800),(1129,660)))
        self.pose=np.eye(3);self.actions=[];self.releases=0;self.reads=0
        self.rotate_gain=.86;self.tick=np.log(1.01);self.stop=False
        self.codes=['#112233']*3;self.wheel_ticks=[]
    def check(self):
        if self.stop:raise InterruptedError('F9')
    def context(self):return self.ctx
    def capture(self):return self.pose.copy()
    def motion(self,a,b):return dict(matrix=(b@np.linalg.inv(a))[:2].tolist())
    def pause(self,s):self.check()
    def release(self):self.releases+=1
    def read_codes(self,frame):self.reads+=1;return self.codes.copy()
    def gesture(self,kind,angle,scale,anchor):
        l,t,r,b=self.ctx.board
        assert l<anchor[0]<r and t<anchor[1]<b, 'Anchor is not in client coordinates'
        pivot=np.array(anchor)-[l,t];a=np.radians(angle)
        matrix=scale*np.array([[np.cos(a),-np.sin(a)],[np.sin(a),np.cos(a)]])
        self.pose=homogeneous(np.column_stack((matrix,pivot-matrix@pivot)))@self.pose
        self.actions.append(kind)
    def rotate(self,angle,anchor):self.gesture('rotate',angle*self.rotate_gain,1,anchor)
    def wheel(self,steps,anchor):
        self.wheel_ticks.append(steps);self.gesture('wheel',0,np.exp(self.tick*steps),anchor)
    def drag(self,dx,dy):
        self.actions.append('drag')
        self.pose=homogeneous([[1,0,dx*.8],[0,1,dy*.8]])@self.pose


class SimilarityExecutionTests(unittest.TestCase):
    def setUp(self):
        self.game=SimilarityGame()
        self.rules=[dict(enabled=True,colors=['#112233'],exact=False,tolerance=8)]*3
        self.row=dict(id=0,dx=85,dy=-45,angle=43,scale=1.01**-7,
                      accepted=True,maximum=0,average=0,colors=['#112233']*3,deltas=[0]*3)
    def run_row(self,row=None,**kwargs):
        row=self.row if row is None else row
        self.batch=CandidateBatch([row],self.game.ctx,1000,clock=lambda:0)
        return execute_candidate(self.game,self.batch,self.batch.id,row['id'],
                                 self.game.capture(),self.rules,clock=lambda:0,**kwargs)
    def test_measured_rotation_zoom_and_translation_converge_at_three_markers(self):
        self.row.update(dx=180,dy=-145)
        result=self.run_row()
        self.assertTrue(result['accepted']);self.assertEqual(self.game.reads,2)
        self.assertLessEqual(max(result['marker_errors']),1)
        self.assertEqual(set(self.game.actions),{'rotate','wheel','drag'})
        np.testing.assert_allclose(result['actual_pose'],self.game.pose[:2])
        self.assertEqual(self.game.releases,1)
    def test_between_notch_scale_stops_instead_of_oscillating(self):
        self.row.update(angle=0,scale=1.01**-7.5)
        with self.assertRaisesRegex(RuntimeError,'between wheel steps'):self.run_row()
        self.assertEqual(sum(abs(v) for v in self.game.wheel_ticks),8)
        self.assertLessEqual(max(map(abs,self.game.wheel_ticks)),4)
        self.assertEqual(self.game.reads,0);self.assertEqual(self.game.releases,1)
    def test_stalled_rotation_and_wheel_stop_after_one_input(self):
        for kind in ('rotate','wheel'):
            with self.subTest(kind=kind):
                self.setUp()
                if kind=='rotate':self.game.rotate_gain=0
                else:self.row['angle']=0;self.game.tick=0
                with self.assertRaisesRegex(RuntimeError,'stalled'):self.run_row()
                self.assertEqual(self.game.actions,[kind]);self.assertEqual(self.game.releases,1)
    def test_wrong_pivot_cannot_be_hidden_by_center_displacement(self):
        rotate=self.game.rotate
        self.game.rotate=lambda angle,anchor:rotate(angle,np.array(anchor)+[0,40])
        with self.assertRaisesRegex(RuntimeError,'pivot'):self.run_row()
        self.assertEqual(self.game.reads,0)
    def test_f9_releases_input_during_joint_execution(self):
        rotate=self.game.rotate
        def cancel(angle,anchor):rotate(angle,anchor);self.game.stop=True
        self.game.rotate=cancel
        with self.assertRaises(InterruptedError):self.run_row()
        self.assertEqual(self.game.actions,['rotate']);self.assertEqual(self.game.releases,1)
    def test_unregistered_motion_never_continues(self):
        motion=self.game.motion
        self.game.motion=lambda a,b:None if self.game.actions else motion(a,b)
        with self.assertRaises(CandidateExpired):self.run_row()
        self.assertEqual(len(self.game.actions),1)
    def test_rebase_rotated_pose_includes_measured_residual(self):
        first=self.run_row()
        original=self.game.pose.copy()
        next_row=dict(self.row,id=1,dx=-20,dy=55,angle=-12,scale=1.01**-4)
        relative=relative_candidate(next_row,first['actual_pose'],self.game.ctx.board)
        result=self.run_row(relative)
        local_markers=np.array(self.game.ctx.markers)-self.game.ctx.board[:2]
        self.assertLess(max(marker_errors(candidate_pose(next_row,self.game.ctx.board),self.game.pose,local_markers)),1.5)
        np.testing.assert_allclose(homogeneous(result['actual_pose'])@original,self.game.pose,atol=1e-9)
    def test_hex_failure_is_verified_but_never_accepted(self):
        self.game.codes=['#FFFFFF']*3
        result=self.run_row();self.assertFalse(result['accepted']);self.assertTrue(result['verified'])
    def test_budget_accounts_for_joint_inputs_and_real_hex_time(self):
        budget=reposition_budget(self.row,0,5,self.game.ctx.board)
        self.assertFalse(budget['allowed']);self.assertGreater(budget['needed'],5)
        self.assertGreater(sum(budget['actions'].values()),0)
        self.assertTrue(reposition_budget(self.row,0,100,self.game.ctx.board)['allowed'])

    def test_budget_matches_the_recorded_best_candidate_route(self):
        row=dict(id=0,dx=91.8756414247431,dy=143.19034613660173,
                 angle=-113.5565384840377,scale=.6274353854671727,
                 zoom_log_step=.009917331588195072)
        board=(714,425,1212,923)
        markers=((797,796),(963,559),(1129,825))
        budget=reposition_budget(row,0,38.731,board,markers=markers)
        self.assertTrue(budget['allowed'],budget)
        self.assertEqual(budget['actions'],dict(rotate=10,wheel=12,drag=0))
        self.assertLess(budget['needed'],38.731)

    def test_budget_rebases_the_recorded_candidate_from_default_pose(self):
        from atlas_pose import relative_candidate
        # Real run had 26.984s left; this used to estimate 46 steps/55.6s.
        candidate=dict(id=0,dx=91.8756414247431,dy=143.19034613660173,
                       angle=-113.5565384840377,scale=.6274353854671727,
                       zoom_log_step=.009917331588195072)
        actual=[[.6944738095820773,-.6920101812723443,526.4273444792099],
                [.6920101812723444,.6944738095820774,23.05672798000537]]
        row=relative_candidate(candidate,actual,(714,425,1212,923))
        markers=((797,796),(963,559),(1129,825))
        budget=reposition_budget(row,0,26.984,(714,425,1212,923),markers=markers)
        self.assertTrue(budget['allowed'],budget)
        self.assertEqual(budget['actions'],dict(rotate=14,wheel=12,drag=0))

    def test_live_callbacks_and_service_rebase_from_verified_frame_and_pose(self):
        from atlas_live_adapter import default_current,choice_current
        from atlas_service import AtlasService,AtlasCallbacks
        from test_atlas_service import Owner
        second=dict(self.row,id=1,dx=-20,dy=55,angle=-12,scale=1.01**-4,maximum=1)
        deadline=time.monotonic()+1000
        batch=CandidateBatch([self.row,second],self.game.ctx,deadline)
        report=dict(quality_gate={'passed':True},candidates=[self.row,second],
                    batch=batch,batch_id=batch.id,board=self.game.ctx.board,adapter=self.game,
                    reference=self.game.capture(),selection_deadline=deadline)
        owner=Owner();owner.selection=1
        service=AtlasService(AtlasCallbacks(lambda *a,**k:None,lambda *a,**k:report,
                                           default_current,choice_current))
        result=service.run(owner,self.rules)
        self.assertTrue(result['accepted']);self.assertEqual(result['candidate_id'],1)
        np.testing.assert_allclose(result['actual_pose'],self.game.pose[:2],atol=1e-9)
        self.assertEqual(self.game.reads,4)

    def test_manual_movement_during_selection_does_not_get_a_fresh_reference(self):
        from atlas_live_adapter import default_current,choice_current
        from test_atlas_service import Owner
        deadline=time.monotonic()+1000
        batch=CandidateBatch([self.row],self.game.ctx,deadline)
        report=dict(batch=batch,adapter=self.game,reference=self.game.capture(),selection_deadline=deadline)
        default_current(Owner(),report,self.row,self.rules)
        self.game.drag(20,0);actions=len(self.game.actions)
        relative=relative_candidate(self.row,report['actual_pose'],self.game.ctx.board)
        with self.assertRaises(CandidateExpired):choice_current(Owner(),report,relative,self.rules)
        self.assertEqual(len(self.game.actions),actions)


if __name__=='__main__':unittest.main()
