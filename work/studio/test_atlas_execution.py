import unittest
import numpy as np
from atlas_execution import CandidateBatch,Context,CandidateExpired,execute_candidate,reposition_budget
from atlas_pose import homogeneous


class Fake:
    def perform_gesture(self, gesture):
        if gesture.kind=='drag':self.drag(*gesture.translation)
        elif gesture.kind=='wheel':self.wheel(gesture.wheel_steps,gesture.anchor)
        else:self.rotate(gesture.requested_angle,gesture.anchor)

    def __init__(self):
        self.pose=np.zeros(2);self.moves=[];self.released=False;self.scale=1;self.reads=0
        self.ctx=Context('one',(0,0,900,900),(0,0,900,900),((150,400),(450,400),(750,400)))
    def check(self):pass
    def context(self):return self.ctx
    def capture(self):return self.pose.copy()
    def motion(self,a,b):return dict(matrix=[[self.scale,0,b[0]-a[0]],[0,self.scale,b[1]-a[1]]],scale=self.scale,angle=0)
    def drag(self,dx,dy):self.moves.append((dx,dy));self.pose+=np.array([dx,dy])*.8
    def pause(self,s):pass
    def release(self):self.released=True
    def read_codes(self,frame):self.reads+=1;return ['#112233']*3


class WheelDetentFake(Fake):
    """Exact image-registration adapter with a measured wheel step differing from search."""
    def __init__(self, actual_log_step=.01016):
        super().__init__()
        self.ctx=Context('detent',(0,0,540,540),(0,0,540,540),
                         ((90,270),(270,270),(450,270)))
        self.pose=np.eye(3)
        self.actual_log_step=actual_log_step
        self.wheel_commands=[];self.drag_commands=[]
    def capture(self):return self.pose.copy()
    def motion(self,a,b):
        matrix=b@np.linalg.inv(a)
        scale=float(np.hypot(matrix[0,0],matrix[1,0]))
        angle=float(np.degrees(np.arctan2(matrix[1,0],matrix[0,0])))
        return dict(matrix=matrix[:2].tolist(),scale=scale,angle=angle)
    def drag(self,dx,dy):
        self.drag_commands.append((dx,dy))
        self.pose=homogeneous([[1,0,dx],[0,1,dy]])@self.pose
    def wheel(self,command,anchor):
        self.wheel_commands.append(command)
        scale=float(np.exp(command*self.actual_log_step))
        x,y=anchor
        gesture=homogeneous([[scale,0,x*(1-scale)],[0,scale,y*(1-scale)]])
        self.pose=gesture@self.pose


class FeedbackHexFake(Fake):
    """Initial HEX miss followed by an exact one-pixel neighbour."""

    def read_codes(self, frame):
        self.reads += 1
        key = tuple(np.rint(np.asarray(frame, dtype=float)).astype(int))
        code = '#112233' if key == (1, 0) else '#000000'
        return [code] * 3


class ReferenceMaterialMismatchFake(Fake):
    """Adapter whose first atlas comparison fails only its RGB gate."""
    def __init__(self, second_translation=(0.,0.)):
        super().__init__()
        self.motion_calls=0
        self.second_translation=np.asarray(second_translation,float)

    def motion(self,a,b):
        self.motion_calls+=1
        if self.motion_calls==1:
            self.last_motion_diagnostics={
                'reason':'material_rgb_mismatch',
                'matrix':[[1.,0.,0.],[0.,1.,0.]],
            }
            return None
        if self.motion_calls>2:
            return super().motion(a,b)
        translation=self.second_translation
        self.last_motion_diagnostics={
            'reason':'ok',
            'matrix':[[1.,0.,float(translation[0])],
                      [0.,1.,float(translation[1])]],
        }
        return dict(matrix=[[1.,0.,float(translation[0])],
                            [0.,1.,float(translation[1])]],
                    scale=1.,angle=0.)


class ExecutionTests(unittest.TestCase):
    def test_reposition_budget_keeps_default_when_time_is_short(self):
        row=dict(dx=300,dy=-50)
        ok=reposition_budget(row,0,1,(0,0,900,900))
        self.assertFalse(ok['allowed'])
        self.assertEqual(ok['reason'],'insufficient_time')
        ok=reposition_budget(row,0,100,(0,0,900,900))
        self.assertTrue(ok['allowed'])

    def setUp(self):
        self.adapter=Fake()
        self.row=dict(id=0,dx=300,dy=-50,angle=0,scale=1,colors=['#112233']*3,deltas=[0]*3)
        self.rules=[dict(enabled=True,colors=['#112233'],exact=True,tolerance=0)]*3
        self.batch=CandidateBatch([self.row],self.adapter.ctx,100,clock=lambda:0)
    def execute(self):
        return execute_candidate(self.adapter,self.batch,self.batch.id,0,np.zeros(2),self.rules,clock=lambda:0)
    def test_measured_feedback_corrects_undertravel_and_verifies_twice(self):
        result=self.execute()
        self.assertTrue(result['accepted']);self.assertTrue(result['verified'])
        self.assertEqual(self.adapter.reads,2);self.assertTrue(self.adapter.released)
        np.testing.assert_allclose(self.adapter.pose,[300,-50],atol=1)
        self.assertTrue(all(max(abs(x),abs(y))<=144 for x,y in self.adapter.moves))

    def test_execute_candidate_wires_measured_hex_feedback_after_prediction_miss(self):
        adapter = FeedbackHexFake()
        row = dict(id=0, dx=0, dy=0, angle=0, scale=1,
                   colors=['#112233'] * 3, deltas=[0] * 3)
        rules = [dict(enabled=True, colors=['#112233'], exact=False,
                      tolerance=1)] * 3
        batch = CandidateBatch([row], adapter.ctx, 100, clock=lambda: 0)
        result = execute_candidate(adapter, batch, batch.id, 0, np.zeros(2),
                                   rules, clock=lambda: 0)
        self.assertTrue(result['accepted'], result)
        self.assertTrue(result['feedback_refined'])
        self.assertEqual(result['actual_colors'], ['#112233'] * 3)
        self.assertEqual(adapter.moves, [(1, 0)])
    def test_old_batch_and_duplicate_selection_never_drag(self):
        with self.assertRaises(CandidateExpired):self.batch.claim('wrong',0,self.adapter.ctx)
        self.assertEqual(self.adapter.moves,[])
        self.execute();count=len(self.adapter.moves)
        with self.assertRaises(CandidateExpired):self.execute()
        self.assertEqual(len(self.adapter.moves),count)
    def test_manual_motion_or_zoom_invalidates_before_drag(self):
        self.adapter.pose[0]=10
        with self.assertRaises(CandidateExpired):self.execute()
        self.assertEqual(self.adapter.moves,[]);self.assertTrue(self.adapter.released)
        self.setUp();self.adapter.scale=1.1
        with self.assertRaises(CandidateExpired):self.execute()
        self.assertEqual(self.adapter.moves,[])
    def test_expiry_and_context_mismatch(self):
        self.batch.deadline=-1
        with self.assertRaises(CandidateExpired):self.execute()
        self.assertEqual(self.adapter.moves,[])
        self.setUp();self.adapter.ctx=Context('two',(),(),())
        with self.assertRaises(CandidateExpired):self.execute()
        self.assertEqual(self.adapter.moves,[])
    def test_unknown_motion_and_missing_ocr_never_claim_verified(self):
        self.adapter.motion=lambda a,b:None
        with self.assertRaises(CandidateExpired):self.execute()
        self.setUp();self.adapter.read_codes=lambda image:[None]*3
        with self.assertRaises(RuntimeError):self.execute()
        self.assertTrue(self.adapter.released)

    def test_material_only_initial_mismatch_rebases_before_sending_input(self):
        adapter=ReferenceMaterialMismatchFake()
        batch=CandidateBatch([self.row],adapter.ctx,100,clock=lambda:0)
        events=[]
        result=execute_candidate(adapter,batch,batch.id,0,adapter.capture(),self.rules,
                                 clock=lambda:0,emit=lambda k,d:events.append((k,d)))
        self.assertTrue(result['verified'])
        self.assertTrue(result['accepted'])
        self.assertTrue(any(k=='atlas_reference_rebased' for k,_ in events))
        # The extra captures/registration happen before the first drag; no
        # input is sent while the reference is being rebuilt.
        self.assertGreaterEqual(adapter.motion_calls,2)
        self.assertTrue(adapter.moves)

    def test_material_mismatch_with_real_initial_motion_keeps_safe_failure(self):
        adapter=ReferenceMaterialMismatchFake(second_translation=(0.,0.))
        # Replace the first diagnostic with a non-identity transform.  The
        # material mismatch is then not eligible for reference rebuilding.
        original=adapter.motion
        def moved_first(a,b):
            if adapter.motion_calls==0:
                adapter.motion_calls+=1
                adapter.last_motion_diagnostics={
                    'reason':'material_rgb_mismatch',
                    'matrix':[[1.,0.,4.],[0.,1.,0.]],
                }
                return None
            return original(a,b)
        adapter.motion=moved_first
        batch=CandidateBatch([self.row],adapter.ctx,100,clock=lambda:0)
        with self.assertRaisesRegex(CandidateExpired,'同材质颜色校验未通过'):
            execute_candidate(adapter,batch,batch.id,0,adapter.capture(),self.rules,clock=lambda:0)
        self.assertEqual(adapter.moves,[])

    def test_unstable_reference_recheck_keeps_safe_failure(self):
        adapter=ReferenceMaterialMismatchFake(second_translation=(3.,0.))
        batch=CandidateBatch([self.row],adapter.ctx,100,clock=lambda:0)
        with self.assertRaisesRegex(CandidateExpired,'同材质颜色校验未通过'):
            execute_candidate(adapter,batch,batch.id,0,adapter.capture(),self.rules,clock=lambda:0)
        self.assertEqual(adapter.moves,[])

    def test_failed_first_motion_records_command_and_failure_before_stopping(self):
        original=self.adapter.motion;events=[]
        def measure(a,b):
            if not self.adapter.moves:return original(a,b)
            self.adapter.last_motion_diagnostics={'passed':False,'reason':'insufficient_inliers'}
            return None
        self.adapter.motion=measure
        with self.assertRaisesRegex(CandidateExpired,'一致纹理匹配点不足'):
            execute_candidate(self.adapter,self.batch,self.batch.id,0,np.zeros(2),self.rules,
                              clock=lambda:0,emit=lambda k,d:events.append((k,d)))
        self.assertEqual([e[0] for e in events],['atlas_registration','atlas_command','atlas_registration'])
        np.testing.assert_array_equal(events[1][1]['command'],self.adapter.moves[0])
        self.assertEqual(events[2][1]['phase'],'positioning')
        self.assertFalse(events[2][1]['passed'])
        self.assertEqual(len(self.adapter.moves),1)
        self.assertEqual(self.adapter.reads,0)
        self.assertTrue(self.adapter.released);self.assertTrue(self.batch.used)

    def test_single_enabled_region_uses_only_that_hex_for_acceptance(self):
        self.setUp()
        self.rules=[dict(enabled=False,colors=[],exact=False,tolerance=8),
                    dict(enabled=False,colors=[],exact=False,tolerance=8),
                    dict(enabled=True,colors=['#112233'],exact=False,tolerance=8)]
        self.adapter.read_codes=lambda image:['#FFFFFF',None,'#112233']
        result=self.execute()
        self.assertTrue(result['accepted'])
        self.assertEqual(result['actual_deltas'],[None,None,0.0])
        self.assertEqual(result['maximum'],0.0)
    def test_stalled_input_aborts_without_blind_retry(self):
        self.adapter.drag=lambda dx,dy:self.adapter.moves.append((dx,dy))
        with self.assertRaisesRegex(RuntimeError,'no measurable'):self.execute()
        self.assertEqual(len(self.adapter.moves),1)

    def test_between_wheel_detents_translates_and_finishes_hex_verification(self):
        adapter=WheelDetentFake()
        target_scale=float(np.exp(-13*adapter.actual_log_step+.002))
        row=dict(id=0,dx=50,dy=-20,angle=0,scale=target_scale,
                 zoom_log_step=.01,colors=['#112233']*3,deltas=[0]*3)
        batch=CandidateBatch([row],adapter.ctx,100,clock=lambda:0)
        events=[]
        result=execute_candidate(adapter,batch,batch.id,0,adapter.capture(),self.rules,
                                 clock=lambda:0,emit=lambda kind,data:events.append((kind,data)))
        self.assertTrue(result['verified'])
        self.assertEqual(adapter.reads,2)
        self.assertEqual(adapter.wheel_commands,[-4,-4,-4,-1])
        self.assertGreaterEqual(len(adapter.drag_commands),1)
        self.assertTrue(any(kind=='atlas_scale_detent' for kind,_ in events))
        self.assertLessEqual(max(result['marker_errors']),1.)
        plan=reposition_budget(row,0,100,adapter.ctx.board,markers=adapter.ctx.markers)
        self.assertTrue(plan['allowed'],plan)

    def test_default_then_late_user_choice_preserves_two_phase_batch(self):
        second=dict(id=1,dx=10,dy=10,angle=0,scale=1,colors=['#112233']*3,
                    deltas=[0,0,0],accepted=True,maximum=0,average=0)
        batch=CandidateBatch([self.row,second],self.adapter.ctx,100,clock=lambda:0)
        default=batch.claim_default(batch.id,self.adapter.ctx)
        self.assertEqual(default['id'],1)
        batch.commit_default(batch.id,self.adapter.ctx,default['id'])
        choice=batch.claim_choice(batch.id,1,self.adapter.ctx)
        self.assertEqual(choice['id'],1)
        committed=batch.commit(batch.id,1,self.adapter.ctx)
        self.assertEqual(committed['id'],1)
        with self.assertRaises(CandidateExpired):batch.commit(batch.id,0,self.adapter.ctx)

    def test_default_execution_keeps_batch_open_for_user_choice(self):
        second=dict(id=1,dx=10,dy=10,angle=0,scale=1,colors=['#112233']*3,
                    deltas=[0,0,0],accepted=True,maximum=0,average=0)
        batch=CandidateBatch([self.row,second],self.adapter.ctx,100,clock=lambda:0)
        default=batch.claim_default(batch.id,self.adapter.ctx)
        batch.commit(batch.id,default['id'],self.adapter.ctx)
        choice=batch.claim_choice(batch.id,1,self.adapter.ctx)
        self.assertEqual(batch.commit(batch.id,choice['id'],self.adapter.ctx)['id'],1)

    def test_execute_default_reservation_does_not_close_batch(self):
        batch=CandidateBatch([self.row],self.adapter.ctx,100,clock=lambda:0)
        result=execute_candidate(self.adapter,batch,batch.id,None,np.zeros(2),self.rules,
                                 clock=lambda:0,reservation='default')
        self.assertTrue(result['verified'])
        self.assertFalse(batch.used)

    def test_controller_and_executor_share_reservations_and_rebase_choice(self):
        from atlas_runner import AtlasController
        base=dict(self.row,accepted=True,maximum=0,average=0)
        alternative=dict(base,id=1,dx=320,dy=-10,maximum=1,average=1)
        batch=CandidateBatch([base,alternative],self.adapter.ctx,100,clock=lambda:0)
        controller=AtlasController(batch,self.adapter.ctx.board,lambda:0)
        default=controller.begin_default().data['candidate']
        result=execute_candidate(self.adapter,batch,batch.id,default['id'],np.zeros(2),self.rules,
                                 clock=lambda:0,reservation='default')
        controller.default_verified(result)
        event=controller.choose(1)
        np.testing.assert_allclose([event.data['candidate']['dx'],event.data['candidate']['dy']],
                                   np.array([320,-10])-self.adapter.pose)
        reference=self.adapter.capture()
        result=execute_candidate(self.adapter,batch,batch.id,1,reference,self.rules,
                                 clock=lambda:0,reservation='choice')
        controller.choice_verified(result)
        self.assertTrue(result['verified'])
        np.testing.assert_allclose(self.adapter.pose,[320,-10],atol=1)

    def test_default_is_deterministic_and_choice_requires_it(self):
        batch=CandidateBatch([self.row],self.adapter.ctx,100,clock=lambda:0)
        with self.assertRaises(CandidateExpired):batch.claim_choice(batch.id,0,self.adapter.ctx)
        self.assertEqual(batch.best()['id'],0)

    def test_execution_uses_the_same_neighborhood_quality_as_search(self):
        exact=dict(self.row,accepted=True,maximum=0,average=0,landing_safe=False,landing_maximum=20)
        robust=dict(self.row,id=1,accepted=True,maximum=2,average=2,landing_safe=True,landing_maximum=3)
        batch=CandidateBatch([exact,robust],self.adapter.ctx,100,clock=lambda:0)
        self.assertEqual(batch.best()['id'],1)
        self.assertEqual(batch.commit_default(batch.id,self.adapter.ctx,1)['id'],1)


if __name__=='__main__':unittest.main()
