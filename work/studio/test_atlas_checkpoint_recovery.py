"""Checkpoint protection after measured recovery and incomplete user choices."""
from copy import deepcopy
import unittest
from unittest.mock import patch

import numpy as np

from atlas_execution import reposition_budget
from atlas_pose import candidate_pose, homogeneous, pose_fields
from atlas_service import AtlasCallbacks, AtlasService
import test_atlas_service as service_fixtures


class CheckpointRecoveryTests(unittest.TestCase):
    board = (0, 0, 900, 900)
    now = 1000.0

    def measured(self, candidate_id, pose, maximum, *, recovered=False, family=.5):
        return dict(candidate_id=candidate_id, verified=True, accepted=False,
            actual_pose=homogeneous(pose)[:2].tolist(), maximum=maximum, average=maximum,
            actual_colors=['#556677'] * 3, actual_deltas=[maximum] * 3,
            predicted_colors=[None] * 3, predicted_deltas=[None] * 3,
            exact_matches=0, exact_maximum=0., exact_average=0.,
            family_maximum=family, family_average=family, family_consistent=family == 0,
            recovered=recovered, pose_reliable=True, positioning_complete=not recovered)

    def recovery_case(self, *, remaining=60., family=.5):
        # The failed original route reached a rotated/scaled pose. Recovery
        # translations are global targets; trial and return must stay local.
        angle=np.radians(17.); scale=.83
        checkpoint=homogeneous([[scale*np.cos(angle),-scale*np.sin(angle),31.],
                                [scale*np.sin(angle),scale*np.cos(angle),-27.]])
        translated=homogeneous([[1.,0.,20.],[0.,1.,0.]]) @ checkpoint
        original=dict(id=0,dx=12.,dy=0.,accepted=False,maximum=30.,average=30.,
                      exact_matches=0,family_maximum=family,family_average=family)
        fallback=dict(original,id=1,maximum=20.,average=20.,
                      **pose_fields(translated,self.board))
        state=dict(quality_gate={'passed':True},candidates=[original],board=self.board)
        observation=self.measured(0,checkpoint,30.,recovered=True,family=family)
        calls=[]; preparations=[]
        owner=service_fixtures.Owner()

        def start(_owner, report, _candidate, _rules, **_context):
            report['current_pose']=checkpoint.copy()
            report['recovery_candidates']=[fallback]
            return deepcopy(observation)

        def prepare(_owner, _report, candidate, _rules, **context):
            budget=reposition_budget(candidate,self.now,context['selection_deadline'],self.board)
            preparations.append((candidate['id'],deepcopy(budget),deepcopy(context)))
            return dict(candidate,route_stability=dict(passed=True,samples_complete=True,
                quality_preferred=family == 0,response_profile_verified=False)),budget

        def choose(_owner, report, candidate, _rules, **context):
            local=candidate_pose(candidate,self.board)
            np.testing.assert_allclose(local[:2,:2],np.eye(2),atol=1e-12)
            calls.append((candidate['id'],context['selection_deadline']))
            report['current_pose']=local @ report['current_pose']
            maximum=40. if candidate['id']==1 else 30.
            return self.measured(candidate['id'],report['current_pose'],maximum,family=family)

        callbacks=AtlasCallbacks(lambda *a,**k:None,lambda *a,**k:state,start,choose,
                                 prepare=prepare)
        with patch('atlas_service.time.monotonic',return_value=self.now):
            result=AtlasService(callbacks).run(owner,[],selection_deadline=self.now+remaining)
        return result,owner,state,calls,preparations,checkpoint,observation

    def test_worse_recovery_candidate_restores_original_measured_checkpoint(self):
        result,owner,state,calls,preparations,checkpoint,observation=self.recovery_case(family=0.)
        self.assertEqual([candidate_id for candidate_id,_ in calls],[1,0])
        self.assertLess(calls[0][1],self.now+60.)
        self.assertEqual(calls[1][1],self.now+60.)
        np.testing.assert_allclose(state['current_pose'],checkpoint,atol=1e-12)
        np.testing.assert_allclose(result['actual_pose'],checkpoint[:2],atol=1e-12)
        self.assertEqual(result['maximum'],observation['maximum'])
        self.assertTrue(result['restored_best'])
        self.assertTrue(result['best_result_current'])
        self.assertFalse(result['recovered'])
        published=[data for kind,data in owner.events if kind=='atlas_candidates']
        self.assertEqual([row['id'] for row in published[-1]['candidates']],[1,0])
        self.assertTrue(all(budget['actions']['rotate']==0 and budget['actions']['wheel']==0
                            for _,budget,_ in preparations))

    def test_insufficient_round_trip_time_sends_no_recovery_input(self):
        result,owner,state,calls,preparations,checkpoint,observation=self.recovery_case(remaining=8.)
        self.assertEqual(calls,[])
        self.assertGreaterEqual(len(preparations),2)
        self.assertTrue(all(budget['allowed'] for _,budget,_ in preparations))
        self.assertGreater(sum(budget['needed'] for _,budget,_ in preparations[:2]),8.)
        np.testing.assert_allclose(state['current_pose'],checkpoint)
        self.assertEqual(result['actual_colors'],observation['actual_colors'])
        self.assertTrue(result['recovered'])
        kind,final_event=owner.events[-1]
        self.assertEqual(kind,'atlas_recovery')
        self.assertEqual(final_event,result)
        self.assertEqual(final_event['actual_colors'],observation['actual_colors'])
        self.assertEqual(final_event['actual_deltas'],observation['actual_deltas'])
        self.assertEqual(final_event['maximum'],observation['maximum'])
        np.testing.assert_allclose(final_event['actual_pose'],observation['actual_pose'])

    def test_cross_family_checkpoint_allows_pure_translation_return(self):
        result,_owner,_state,calls,preparations,checkpoint,_observation=self.recovery_case()
        self.assertEqual([candidate_id for candidate_id,_ in calls],[1,0])
        self.assertFalse(result['family_consistent'])
        self.assertTrue(result['restored_best'])
        self.assertTrue(result['best_result_current'])
        np.testing.assert_allclose(result['actual_pose'],checkpoint[:2],atol=1e-12)
        returns=[budget for candidate_id,budget,_ in preparations if candidate_id==0]
        self.assertTrue(returns)
        self.assertTrue(all(budget['actions']==dict(rotate=0,wheel=0,drag=1) for budget in returns))

    def manual_failure_case(self, mode):
        owner=service_fixtures.Owner(); owner.selection=1
        original=dict(id=0,dx=0.,dy=0.,accepted=True,maximum=0.,average=0.)
        selected=dict(id=1,dx=20.,dy=0.,accepted=False,maximum=5.,average=5.)
        state=dict(quality_gate={'passed':True},candidates=[original,selected],board=self.board)
        old=self.measured(0,np.eye(3),0.,family=0.)
        old.update(accepted=True,actual_colors=['#FFFFFF']*3)
        calls=[]

        def start(_owner,report,_candidate,_rules,**_context):
            report['current_pose']=np.eye(3)
            return deepcopy(old)

        def choose(_owner,report,candidate,_rules,**_context):
            # Motion occurs before the callback fails or loses its pose.
            calls.append(candidate['id'])
            report['current_pose']=candidate_pose(candidate,self.board) @ report['current_pose']
            if mode=='raise':raise RuntimeError('verification failed after movement')
            if mode=='none':return None
            return dict(self.measured(1,report['current_pose'],35.,recovered=True),
                        actual_pose=None,pose_reliable=False,actual_colors=['#223344']*3)

        callbacks=AtlasCallbacks(lambda *a,**k:None,lambda *a,**k:state,start,choose)
        with patch('atlas_service.time.monotonic',return_value=self.now):
            result=AtlasService(callbacks).run(owner,[],selection_deadline=self.now+60.)
        self.assertEqual(calls,[1])
        np.testing.assert_allclose(state['current_pose'],[[1,0,20],[0,1,0],[0,0,1]])
        self.assertFalse(result['best_result_current'])
        self.assertFalse(result['restore_attempted'])
        self.assertIsNone(result['actual_pose'])
        self.assertEqual(result['candidate_id'],1)
        self.assertEqual(result['best_result']['actual_colors'],old['actual_colors'])
        self.assertNotEqual(result.get('actual_colors'),old['actual_colors'])
        self.assertEqual(owner.events[-1][0],'atlas_best_not_restored')
        self.assertNotIn('atlas_verified',[kind for kind,_ in owner.events])
        return result

    def test_manual_choice_raises_after_movement_does_not_report_old_current_colors(self):
        result=self.manual_failure_case('raise')
        self.assertFalse(result['verified'])
        self.assertIn('verification failed',result['detail'])

    def test_manual_choice_returns_none_after_movement_does_not_report_old_current_colors(self):
        result=self.manual_failure_case('none')
        self.assertFalse(result['verified'])

    def test_manual_choice_without_pose_preserves_new_hex_as_current_observation(self):
        result=self.manual_failure_case('missing_pose')
        self.assertEqual(result['actual_colors'],['#223344']*3)
        self.assertEqual(result['maximum'],35.)
        self.assertEqual(result['best_result']['maximum'],0.)

    def test_known_pose_can_return_after_color_observation_budget_expires(self):
        owner=service_fixtures.Owner()
        best=self.measured(0,np.eye(3),8.,family=0.)
        current=dict(verified=False,recovered=True,positioning_complete=False,
                     pose_reliable=True,actual_pose=[[1,0,12],[0,1,0]])
        target=dict(id=0,dx=0,dy=0,maximum=8.,average=8.)
        calls=[]
        def prepare(_owner,_report,row,_rules,**context):
            return dict(row,route_stability=dict(passed=True,samples_complete=True)), \
                   dict(allowed=True,actions=dict(drag=1,rotate=0,wheel=0))
        def choose(*args,**kwargs):
            calls.append('return')
            return deepcopy(best)
        service=AtlasService(AtlasCallbacks(None,None,None,choose,prepare=prepare))
        result=service._restore_observed(owner,dict(board=self.board),current,best,target,[],{})
        self.assertEqual(calls,['return'])
        self.assertTrue(result['restored_best'])
        self.assertEqual(result['actual_colors'],best['actual_colors'])

    def test_unknown_pose_cannot_return_using_stale_measured_colors(self):
        owner=service_fixtures.Owner()
        best=self.measured(0,np.eye(3),8.)
        current=dict(verified=False,recovered=True,pose_reliable=False,
                     actual_pose=[[1,0,12],[0,1,0]])
        def unexpected(*args,**kwargs):raise AssertionError('unsafe return')
        service=AtlasService(AtlasCallbacks(None,None,None,unexpected,prepare=unexpected))
        result=service._restore_observed(owner,dict(board=self.board),current,best,
                                         dict(id=0,dx=0,dy=0),[],{})
        self.assertFalse(result['best_result_current'])
        self.assertFalse(result['verified'])


if __name__=='__main__':
    unittest.main()
