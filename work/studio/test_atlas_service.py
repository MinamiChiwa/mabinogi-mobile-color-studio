import unittest
import time
import threading
from unittest.mock import patch
from atlas_service import AtlasService, AtlasCallbacks, quality_failure_message
from atlas_pose import candidate_pose, homogeneous, pose_fields
from atlas_execution import reposition_budget
import numpy as np


class Owner:
    def __init__(self):self.events=[];self.stop=None;self.selection=None
    def event(self,kind,**data):self.events.append((kind,data))
    def wait_candidate_choice(self,batch_id,deadline):return self.selection


class ServiceTests(unittest.TestCase):
    def verified(self,owner,report,candidate,rules,**kwargs):
        pose=candidate_pose(candidate,report['board'])@homogeneous(report.get('current_pose',np.eye(3)))
        report['current_pose']=pose
        scores={k:candidate[k] for k in ('maximum','average','exact_maximum','exact_average',
                'exact_matches','family_maximum','family_average') if k in candidate}
        return dict(id=candidate['id'],candidate_id=candidate['id'],accepted=True,
                    verified=True,actual_pose=pose[:2].tolist(),**scores)

    def prepare(self,owner,report,candidate,rules,**kwargs):
        budget=reposition_budget(candidate,time.monotonic(),kwargs['selection_deadline'],report['board'])
        if not budget['allowed']:return None,budget
        row=dict(candidate,**pose_fields(budget['planned_pose'],report['board']),
                 route_stability=dict(passed=True,response_profile_verified=False))
        return row,budget

    def callbacks(self,gate=True):
        return AtlasCallbacks(
            acquire=lambda *a,**k:'capture',
            build=lambda *a,**k:{'quality_gate':{'passed':gate},'candidates':[
                dict(id=0,dx=0,dy=0,accepted=True,maximum=0,average=0),
                dict(id=1,dx=12,dy=12,accepted=True,maximum=1,average=1)],'board':(0,0,900,900)},
            default=self.verified,choice=self.verified,prepare=self.prepare)

    def test_quality_gate_blocks_candidate_publication(self):
        owner=Owner();service=AtlasService(self.callbacks(False))
        self.assertIsNone(service.run(owner,[]))
        self.assertEqual([e[0] for e in owner.events],['atlas_status','atlas_invalidated'])
        self.assertFalse(owner.events[-1][1]['search_performed'])
        self.assertEqual(owner.events[-1][1]['reason'],'atlas_quality_failed')

    def test_optional_current_observation_runs_after_plain_early_exits(self):
        for mode in ('build_error','quality','no_rows','budget','default_error','default_none','default_missing_pose'):
            with self.subTest(mode=mode):
                owner=Owner();callbacks=self.callbacks();captured={'game':'test-game','scene':'test-scene'}
                callbacks.acquire=lambda *a,**k:captured
                calls=[]
                def observed(_owner,artifact,_rules,**context):
                    self.assertIs(artifact,captured);calls.append(context)
                    return dict(verified=True,actual_colors=['#112233']*3,
                        actual_deltas=[4.]*3,maximum=4.,average=4.,observed_accepted=False,
                        predicted_colors=[None]*3,predicted_deltas=[None]*3)
                callbacks.observe_current=observed
                if mode=='build_error':callbacks.build=lambda *a,**k:(_ for _ in ()).throw(ValueError('atlas'))
                elif mode=='quality':callbacks.build=lambda *a,**k:dict(quality_gate={'passed':False})
                elif mode=='no_rows':callbacks.build=lambda *a,**k:dict(quality_gate={'passed':True},candidates=[])
                elif mode=='budget':
                    callbacks.build=lambda *a,**k:dict(quality_gate={'passed':True},
                        candidates=[dict(id=0,dx=1e8,dy=0.,accepted=False,maximum=4.,average=4.)],board=(0,0,900,900))
                elif mode=='default_error':callbacks.default=lambda *a,**k:(_ for _ in ()).throw(RuntimeError('ocr'))
                elif mode=='default_none':callbacks.default=lambda *a,**k:None
                elif mode=='default_missing_pose':callbacks.default=lambda *a,**k:dict(verified=True,actual_pose=None)
                result=AtlasService(callbacks).run(owner,[],selection_deadline=time.monotonic()+30.)
                self.assertEqual(len(calls),1)
                self.assertTrue(result['verified']);self.assertFalse(result['accepted'])
                self.assertTrue(result['early_exit']);self.assertFalse(result['best_result_current'])
                self.assertIsNone(result['candidate_id']);self.assertIsNone(result['actual_pose'])
                self.assertFalse(result['pose_reliable']);self.assertFalse(result['positioning_complete'])
                self.assertEqual(owner.events[-1][0],'atlas_recovery')
                self.assertNotIn('atlas_default_verified',[kind for kind,_ in owner.events])

    def test_current_observation_is_never_fabricated_after_acquire_error_or_safety_stop(self):
        for mode in ('acquire_error','build_stop','observation_stop'):
            with self.subTest(mode=mode):
                owner=Owner();callbacks=self.callbacks(False);calls=[]
                def observe(*a,**k):calls.append(True);raise InterruptedError('F9')
                callbacks.observe_current=observe
                if mode=='acquire_error':callbacks.acquire=lambda *a,**k:(_ for _ in ()).throw(ValueError('capture'))
                elif mode=='build_stop':callbacks.build=lambda *a,**k:(_ for _ in ()).throw(InterruptedError('focus'))
                if mode=='acquire_error':
                    self.assertIsNone(AtlasService(callbacks).run(owner,[]));self.assertEqual(calls,[])
                else:
                    with self.assertRaises(InterruptedError):AtlasService(callbacks).run(owner,[])
                    self.assertEqual(len(calls),int(mode=='observation_stop'))

    def test_current_observation_plain_failure_keeps_unknown_without_global_error(self):
        owner=Owner();callbacks=self.callbacks(False)
        callbacks.observe_current=lambda *a,**k:(_ for _ in ()).throw(ValueError('ocr unavailable'))
        self.assertIsNone(AtlasService(callbacks).run(owner,[]))
        self.assertEqual(owner.events[-1][0],'atlas_recovery_unavailable')
        self.assertIn('ocr unavailable',owner.events[-1][1]['detail'])

    def test_failed_map_validation_is_distinguished_from_color_delta(self):
        message=quality_failure_message({'thresholds':{'max_rgb_rmse':8},'regions':[
            {'region':2,'required':True,'passed':False,'heldout_rgb_rmse':8.6224}]})
        self.assertIn('RGB RMSE 8.62',message)
        self.assertIn('尚未搜索',message)

    def test_default_without_choice_keeps_default(self):
        owner=Owner();service=AtlasService(self.callbacks())
        result=service.run(owner,[],selection_deadline=time.monotonic()+30)
        self.assertEqual(result['id'],0)
        self.assertEqual([e[0] for e in owner.events],
                         ['atlas_status','atlas_ready','atlas_search_summary','atlas_candidates','atlas_default_verified','atlas_selection_expired'])

    def test_progressive_search_is_opt_in_and_uses_staged_candidates(self):
        owner=Owner();callbacks=self.callbacks()
        callbacks.progressive=lambda owner,captured,report,rules,**context:[
            dict(id=10,dx=1,dy=0,accepted=True,maximum=2,average=1,total=3,
                 exact_matches=0,action_cost=1,action_risk=1),
            dict(id=11,dx=2,dy=0,accepted=True,maximum=2,average=1,total=3,
                 exact_matches=1,action_cost=8,action_risk=1)]
        result=AtlasService(callbacks).run(owner,[],progressive_search=True,
                                           selection_deadline=time.monotonic()+30)
        self.assertEqual(result['candidate_id'],11)
        event=next(data for kind,data in owner.events if kind=='atlas_candidates')
        self.assertEqual(event['candidates'][0]['exact_matches'],1)

    def test_progressive_failure_falls_back_to_complete_candidates(self):
        owner=Owner();callbacks=self.callbacks()
        callbacks.progressive=lambda *a,**k:(_ for _ in ()).throw(RuntimeError('staged'))
        result=AtlasService(callbacks).run(owner,[],progressive_search=True,
                                           selection_deadline=time.monotonic()+30)
        self.assertEqual(result['candidate_id'],0)
        self.assertIn('atlas_progressive_unavailable',[kind for kind,_ in owner.events])

    def test_empty_progressive_result_falls_back_to_complete_candidates(self):
        owner=Owner();callbacks=self.callbacks()
        callbacks.progressive=lambda *a,**k:[]
        result=AtlasService(callbacks).run(owner,[],progressive_search=True,
                                           selection_deadline=time.monotonic()+30)
        self.assertEqual(result['candidate_id'],0)
        self.assertIn('atlas_progressive_unavailable',[kind for kind,_ in owner.events])

    def test_feedback_best_not_restored_is_terminal_and_keeps_current_hex_separate(self):
        owner=Owner();base=self.callbacks()
        base.build=lambda *a,**k:{'quality_gate':{'passed':True},'candidates':[
            dict(id=0,dx=0,dy=0,accepted=False,maximum=50,average=50,
                 colors=['#FFFFFF']*3,deltas=[50]*3)],'board':(0,0,900,900)}
        best=dict(candidate_id=0,actual_colors=['#112233']*3,
                  actual_deltas=[0.,0.,0.],maximum=0.,average=0.,
                  accepted=True,verified=True,actual_pose=[[1,0,1],[0,1,0]])
        base.default=lambda *a,**k:dict(candidate_id=0,
            predicted_colors=['#FFFFFF']*3,predicted_deltas=[50]*3,
            actual_colors=['#000000']*3,actual_deltas=[50.,50.,50.],
            maximum=50.,average=50.,accepted=False,verified=True,
            actual_pose=[[1,0,0],[0,1,0]],feedback_best_available=True,
            best_result_current=False,best_result=best)
        result=AtlasService(base).run(owner,[],selection_deadline=time.monotonic()+30)
        self.assertEqual(result['actual_colors'],['#000000']*3)
        self.assertEqual(result['best_result']['actual_colors'],['#112233']*3)
        self.assertFalse(result['best_result_current'])
        self.assertEqual(owner.events[-1][0],'atlas_best_not_restored')
        self.assertNotIn('atlas_default_verified',[kind for kind,_ in owner.events])

    def test_unreachable_scale_is_filtered_before_publication_and_input(self):
        owner=Owner();base=self.callbacks();calls=[]
        base.build=lambda *a,**k:{'quality_gate':{'passed':True},'candidates':[
            dict(id=0,dx=20,dy=10,angle=0,scale=1.01**-7.5,
                 accepted=True,maximum=0,average=0),
            dict(id=1,dx=12,dy=12,accepted=False,maximum=9,average=9)],
            'board':(0,0,900,900)}
        def default(owner,report,candidate,rules,**kwargs):
            calls.append(candidate['id'])
            return self.verified(owner,report,candidate,rules)
        base.default=default
        AtlasService(base).run(owner,[],selection_deadline=time.monotonic()+120)
        published=next(data for kind,data in owner.events if kind=='atlas_candidates')
        self.assertEqual([row['id'] for row in published['candidates']],[1])
        self.assertEqual(calls,[1])

    def test_stability_rejection_is_not_reported_as_no_color_match(self):
        owner=Owner();base=self.callbacks()
        base.build=lambda *a,**k:{'quality_gate':{'passed':True},
            'candidates':[], 'board':(0,0,900,900),
            'search_diagnostics':{'stability_required':True,'stable_route_count':0}}
        result=AtlasService(base).run(owner,[],selection_deadline=time.monotonic()+30)
        self.assertIsNone(result)
        event=owner.events[-1]
        self.assertEqual(event[0],'atlas_invalidated')
        self.assertEqual(event[1]['reason'],'stable_route_unavailable')
        self.assertIn('稳定可达',event[1]['message'])

    def test_choice_is_executed_after_default(self):
        owner=Owner();owner.selection=1;service=AtlasService(self.callbacks())
        result=service.run(owner,[],selection_deadline=time.monotonic()+30)
        self.assertEqual(result['id'],1)
        self.assertEqual(owner.events[-1][0],'atlas_verified')

    def test_choice_keeps_fresh_endpoint_prediction_instead_of_old_list_flag(self):
        owner=Owner();owner.selection=1;base=self.callbacks()
        def choice(*args,**kwargs):
            result=self.verified(*args,**kwargs)
            return dict(result,predicted_accepted=False)
        base.choice=choice
        result=AtlasService(base).run(owner,[],selection_deadline=time.monotonic()+30)
        self.assertFalse(result['predicted_accepted'])
        self.assertTrue(result['accepted'])
        self.assertFalse(result['compromise'])

    def test_default_is_not_published_without_safe_execution_budget(self):
        owner=Owner();calls=[];base=self.callbacks()
        callbacks=AtlasCallbacks(base.acquire,base.build,
            lambda *a,**k:calls.append('default'),base.choice)
        result=AtlasService(callbacks).run(owner,[],selection_deadline=time.monotonic()+.1)
        self.assertIsNone(result)
        self.assertEqual(calls,[])
        self.assertEqual([kind for kind,_ in owner.events],
                         ['atlas_status','atlas_ready','atlas_search_summary','atlas_default_unavailable'])

    def test_choice_without_enough_time_keeps_verified_default(self):
        owner=Owner();owner.selection=1
        base=self.callbacks()
        base.build=lambda *a,**k:{'quality_gate':{'passed':True},'candidates':[
            dict(id=0,dx=0,dy=0,accepted=True,maximum=0,average=0),
            dict(id=1,dx=500,dy=0,accepted=False,maximum=2,average=2)],
            'board':(0,0,900,900)}
        choice_calls=[]
        base.choice=lambda *a,**k:choice_calls.append('choice')
        result=AtlasService(base).run(owner,[],selection_deadline=time.monotonic()+6)
        self.assertEqual(result['id'],0)
        self.assertEqual(choice_calls,[])
        self.assertEqual(owner.events[-1][0],'atlas_choice_rejected')
        self.assertIn('保持',owner.events[-1][1]['message'])

    def test_stop_while_waiting_keeps_default_and_invalidates_choice(self):
        owner=Owner();owner.stop=threading.Event();owner.stop.set()
        result=AtlasService(self.callbacks()).run(owner,[],selection_deadline=time.monotonic()+30)
        self.assertEqual(result['id'],0)
        self.assertEqual(owner.events[-1][0],'interrupted')

    def test_mixed_modes_keep_compromises_after_predicted_matches(self):
        owner=Owner();base=self.callbacks()
        base.build=lambda *a,**k:{'quality_gate':{'passed':True},'candidates':[
            dict(id=0,dx=0,dy=0,accepted=False,maximum=8.1,average=8.1),
            dict(id=1,dx=12,dy=12,accepted=True,maximum=8,average=4)],
            'board':(0,0,900,900)}
        result=AtlasService(base).run(owner,[],selection_deadline=time.monotonic()+30)
        self.assertEqual(result['id'],1)
        rows=next(data['candidates'] for kind,data in owner.events if kind=='atlas_candidates')
        self.assertEqual([row['id'] for row in rows],[1,0])
        self.assertFalse(next(data for kind,data in owner.events if kind=='atlas_candidates')['compromise_only'])


    def test_any_tolerance_with_no_match_auto_positions_best_compromise(self):
        owner=Owner();base=self.callbacks();calls=[]
        base.build=lambda *a,**k:{'quality_gate':{'passed':True},'candidates':[
            dict(id=0,dx=0,dy=0,accepted=False,maximum=12,average=8,exact_matches=0),
            dict(id=1,dx=12,dy=12,accepted=False,maximum=13,average=9,exact_matches=0)],
            'board':(0,0,900,900)}
        base.build=lambda *a,**k:{'quality_gate':{'passed':True},'candidates':[
            dict(id=0,dx=40,dy=0,accepted=False,maximum=14,average=8),
            dict(id=1,dx=5,dy=2,accepted=False,maximum=9,average=7),
            dict(id=2,dx=7,dy=2,accepted=False,maximum=11,average=5)],
            'board':(0,0,900,900)}
        def default(owner,report,candidate,rules,**kwargs):
            calls.append(('default',candidate['id']))
            return dict(self.verified(owner,report,candidate,rules),accepted=False)
        def choice(owner,report,candidate,rules,**kwargs):
            calls.append(('choice',candidate['id']))
            return dict(self.verified(owner,report,candidate,rules),accepted=False)
        base.default=default;base.choice=choice
        result=AtlasService(base).run(owner,[],selection_deadline=time.monotonic()+30)
        self.assertEqual(calls,[('default',1)])
        self.assertFalse(result['accepted'])
        self.assertEqual(result['candidate_id'],1)
        self.assertTrue(result['compromise'])
        event=next(data for kind,data in owner.events if kind=='atlas_candidates')
        self.assertTrue(event['compromise_only'])
        self.assertIn('妥协',event['message'])
        self.assertEqual([r['id'] for r in event['candidates']],[1,2,0])
        summary=next(data for kind,data in owner.events if kind=='atlas_search_summary')
        self.assertEqual(summary['raw_count'],3)
        self.assertEqual(summary['predicted_accepted_count'],0)
        self.assertEqual((summary['best_compromise_max'],summary['best_compromise_average']),(9,7))
        self.assertEqual(owner.events[-1][0],'atlas_selection_expired')

    def test_compromise_stays_available_for_user_selection(self):
        owner=Owner();owner.selection=1;base=self.callbacks();build=base.build
        def changed(*a,**kw):
            report=build(*a,**kw)
            for row in report['candidates']:row.update(accepted=False,maximum=row['id']+10,average=9)
            return report
        def failed(*a,**kw):return dict(self.verified(*a,**kw),accepted=False)
        base.build=changed;base.default=base.choice=failed
        result=AtlasService(base).run(owner,[],selection_deadline=time.monotonic()+30)
        self.assertEqual(result['candidate_id'],1)
        self.assertEqual(owner.events[-1][0],'atlas_verified')

    def test_compromise_that_loses_color_family_tries_a_better_family_candidate(self):
        owner=Owner();base=self.callbacks();calls=[]
        rows=[dict(id=i,dx=i*5,dy=0,accepted=False,maximum=20+i,average=10+i,
                   family_consistent=True,family_maximum=0,family_average=0) for i in range(2)]
        base.build=lambda *args,**kwargs:dict(quality_gate={'passed':True},candidates=rows,board=(0,0,900,900))
        def default(*args,**kwargs):
            calls.append('default')
            return dict(self.verified(*args,**kwargs),accepted=False,maximum=71,average=30,
                        family_consistent=False,family_maximum=.8,family_average=.26)
        def choice(*args,**kwargs):
            calls.append('choice')
            return dict(self.verified(*args,**kwargs),accepted=False,maximum=22,average=12,
                        family_consistent=True,family_maximum=0,family_average=0)
        base.default=default;base.choice=choice
        result=AtlasService(base).run(owner,[],selection_deadline=time.monotonic()+30)
        self.assertEqual(calls,['default','choice'])
        self.assertTrue(result['family_consistent'])
        self.assertEqual(result['candidate_id'],1)

    def test_no_family_consistent_candidate_is_explicitly_identified(self):
        owner=Owner();base=self.callbacks();build=base.build
        def changed(*args,**kwargs):
            report=build(*args,**kwargs)
            for row in report['candidates']:
                row.update(accepted=False,family_consistent=False,family_maximum=.5,family_average=.2)
            return report
        base.build=changed
        AtlasService(base).run(owner,[],selection_deadline=time.monotonic()+30)
        event=next(data for kind,data in owner.events if kind=='atlas_candidates')
        self.assertTrue(event['family_unavailable'])
        self.assertIn('色系',event['message'])

    def test_replanned_compromise_that_loses_exact_white_tries_better_candidate(self):
        owner=Owner();base=self.callbacks();calls=[]
        rows=[dict(id=i,dx=i*5,dy=0,accepted=False,maximum=32+i,average=21+i,
                   exact_maximum=0,exact_average=0,exact_matches=1,
                   family_consistent=True,family_maximum=0,family_average=0) for i in range(2)]
        base.build=lambda *a,**kw:dict(quality_gate={'passed':True},candidates=rows,board=(0,0,900,900))
        def default(*a,**kw):
            calls.append('default')
            return dict(self.verified(*a,**kw),accepted=False,maximum=46.7,average=33.3,
                        exact_maximum=14.11,exact_average=14.11,exact_matches=0,
                        family_consistent=True,family_maximum=0,family_average=0,replanned=True)
        def choice(*a,**kw):
            calls.append('choice')
            return dict(self.verified(*a,**kw),accepted=False,maximum=33,average=22,
                        exact_maximum=0,exact_average=0,exact_matches=1,
                        family_consistent=True,family_maximum=0,family_average=0)
        base.default=default;base.choice=choice
        result=AtlasService(base).run(owner,[],selection_deadline=time.monotonic()+30)
        self.assertEqual(calls,['default','choice'])
        self.assertEqual(result['candidate_id'],1)
        self.assertEqual(result['exact_maximum'],0)

    def test_same_family_similar_error_regression_tries_only_better_candidates(self):
        for alternative,expected in ((35,[0,1]),(60,[0])):
            with self.subTest(alternative=alternative):
                owner=Owner();base=self.callbacks();calls=[]
                rows=[dict(id=i,dx=i*5,dy=0,accepted=False,maximum=err,average=err,
                           family_maximum=0,family_average=0) for i,err in enumerate((30,alternative))]
                base.build=lambda *a,**kw:dict(quality_gate={'passed':True},candidates=rows,board=(0,0,900,900))
                def execute(owner,report,candidate,rules,**kw):
                    calls.append(candidate['id']);err=50 if candidate['id']==0 else alternative
                    return dict(self.verified(owner,report,candidate,rules),accepted=False,
                                maximum=err,average=err,family_maximum=0,family_average=0)
                base.default=base.choice=execute
                AtlasService(base).run(owner,[],selection_deadline=time.monotonic()+30)
                self.assertEqual(calls,expected)

    def test_unreachable_choice_does_not_claim_time_was_insufficient(self):
        owner=Owner();owner.selection=1;base=self.callbacks()
        prepare=base.prepare
        def unreachable(owner,report,candidate,rules,**context):
            if candidate['id']==1:
                return None,dict(allowed=False,reason='no_measurable_motion',remaining=23.45,needed=11.35)
            return prepare(owner,report,candidate,rules,**context)
        base.prepare=unreachable
        AtlasService(base).run(owner,[],selection_deadline=time.monotonic()+30)
        event=owner.events[-1]
        self.assertEqual(event[0],'atlas_choice_rejected')
        self.assertNotIn('时间不足',event[1]['message'])
        self.assertIn('无法完成路线复核',event[1]['message'])

    def test_automatic_candidate_balances_regions_before_exact_hits(self):
        owner=Owner();base=self.callbacks();selected=[]
        base.build=lambda *a,**k:{'quality_gate':{'passed':True},'candidates':[
            dict(id=0,dx=0,dy=0,accepted=False,maximum=30,average=20,
                 exact_matches=2,exact_total=2,exact_maximum=0,exact_average=0),
            dict(id=1,dx=1,dy=1,accepted=False,maximum=2,average=1,
                 exact_matches=1,exact_total=2,exact_maximum=2,exact_average=1)],
            'board':(0,0,900,900)}
        def compromise(owner,report,candidate,rules,**kwargs):
            selected.append(candidate['id'])
            return dict(self.verified(owner,report,candidate,rules),accepted=False)
        base.default=compromise
        result=AtlasService(base).run(owner,[],selection_deadline=time.monotonic()+30)
        self.assertEqual(selected,[1])
        self.assertEqual(result['candidate_id'],1)

    def test_family_boundary_does_not_override_lower_overall_error(self):
        owner=Owner();base=self.callbacks();selected=[]
        base.build=lambda *a,**k:{'quality_gate':{'passed':True},'candidates':[
            dict(id=2,dx=0,dy=0,accepted=False,maximum=35,average=12,
                 exact_matches=1,exact_total=2,exact_maximum=35,exact_average=17.5,
                 family_maximum=1.,family_average=.5),
            dict(id=7,dx=1,dy=1,accepted=False,maximum=40,average=16,
                 exact_matches=0,exact_total=2,exact_maximum=5,exact_average=4)],
            'board':(0,0,900,900)}
        def compromise(owner,report,candidate,rules,**kwargs):
            selected.append(candidate['id'])
            return dict(self.verified(owner,report,candidate,rules),accepted=False)
        base.default=compromise
        result=AtlasService(base).run(owner,[],selection_deadline=time.monotonic()+30)
        self.assertEqual(selected,[2])
        self.assertEqual(result['candidate_id'],2)
        candidates=next(data['candidates'] for kind,data in owner.events if kind=='atlas_candidates')
        self.assertEqual([row['id'] for row in candidates],[2,7])

    def test_failed_hex_automatically_tries_next_from_measured_pose(self):
        owner=Owner();base=self.callbacks();moves=[]
        def failed(owner,report,candidate,rules,**kw):
            result=self.verified(owner,report,candidate,rules)
            report['current_pose']=homogeneous([[1,0,.4],[0,1,-.2]])
            return dict(result,accepted=False,maximum=20,average=20,
                        actual_pose=report['current_pose'][:2].tolist())
        def choice(owner,report,candidate,rules,**kw):
            moves.append(candidate);return self.verified(owner,report,candidate,rules)
        base.default=failed;base.choice=choice
        result=AtlasService(base).run(owner,[],selection_deadline=time.monotonic()+30)
        self.assertTrue(result['accepted']);self.assertEqual(result['id'],1)
        np.testing.assert_allclose([moves[0]['dx'],moves[0]['dy']],[12,12])
        kinds=[k for k,_ in owner.events]
        self.assertLess(kinds.index('atlas_candidate_failed'),kinds.index('atlas_default_verified'))

    def test_retry_compares_overall_error_when_exact_hit_counts_match(self):
        for measured_error,expected_ids in ((50,[0,1]),(2,[0])):
            with self.subTest(measured_error=measured_error):
                owner=Owner();base=self.callbacks();calls=[]
                base.build=lambda *a,**k:{'quality_gate':{'passed':True},'candidates':[
                    dict(id=0,dx=0,dy=0,accepted=True,maximum=0,average=0,
                         exact_matches=2,exact_total=2,exact_maximum=0,exact_average=0),
                    dict(id=1,dx=1,dy=1,accepted=False,maximum=40,average=16,
                         exact_matches=0,exact_total=2,exact_maximum=5,exact_average=4)],
                    'board':(0,0,900,900)}
                def failed(owner,report,candidate,rules,**kwargs):
                    calls.append(candidate['id'])
                    return dict(self.verified(owner,report,candidate,rules),accepted=False,
                                exact_matches=0,exact_maximum=measured_error,
                                exact_average=measured_error/2,maximum=measured_error,average=measured_error/3)
                def choice(owner,report,candidate,rules,**kwargs):
                    calls.append(candidate['id'])
                    return dict(self.verified(owner,report,candidate,rules),accepted=False,
                                exact_matches=0,exact_maximum=5,exact_average=4,maximum=40,average=16)
                base.default=failed;base.choice=choice
                AtlasService(base).run(owner,[],selection_deadline=time.monotonic()+30)
                self.assertEqual(calls,expected_ids)

    def test_worse_alternate_restores_first_observation_and_stops_trials(self):
        owner=Owner();base=self.callbacks();calls=[]
        def fail(owner,report,candidate,rules,**kw):
            calls.append(candidate['id'])
            return dict(self.verified(owner,report,candidate,rules),accepted=False,
                        maximum=20+candidate['id'],average=20+candidate['id'])
        base.default=base.choice=fail
        result=AtlasService(base).run(owner,[],selection_deadline=time.monotonic()+30)
        self.assertEqual(calls,[0,1,0]);self.assertFalse(result['accepted'])
        self.assertEqual(result['candidate_id'],0)
        self.assertTrue(result['restored_best'])
        self.assertTrue(result['best_result_current'])

    def protection_case(self,actual_errors,*,accepted=False):
        owner=Owner();base=self.callbacks();calls=[]
        # These fixtures isolate error improvement within one acceptance tier.
        rows=[dict(id=i,dx=i*5,dy=0,accepted=accepted,maximum=i,average=i) for i in range(4)]
        base.build=lambda *a,**kw:dict(quality_gate={'passed':True},candidates=rows,board=(0,0,900,900))
        def execute(owner,report,candidate,rules,**kwargs):
            calls.append(candidate['id'])
            err=actual_errors[candidate['id']]
            return dict(self.verified(owner,report,candidate,rules),accepted=accepted,
                        maximum=err,average=err)
        base.default=base.choice=execute
        return owner,base,calls

    def test_accepted_measurement_never_auto_leaves_even_if_family_prediction_changed(self):
        owner,base,calls=self.protection_case([20,10,5,4],accepted=True)
        execute=base.default
        base.default=lambda *a,**kw:dict(execute(*a,**kw),family_maximum=.1)
        AtlasService(base).run(owner,[],selection_deadline=time.monotonic()+60)
        self.assertEqual(calls,[0])

    def test_better_actual_result_never_tries_equal_or_worse_predictions(self):
        owner,base,calls=self.protection_case([.5,10,5,4])
        AtlasService(base).run(owner,[],selection_deadline=time.monotonic()+60)
        self.assertEqual(calls,[0])

    def test_rebinding_must_still_improve_over_measured_result(self):
        owner,base,calls=self.protection_case([20,10,5,4]);prepare=base.prepare
        def changed(*a,**kw):
            row,budget=prepare(*a,**kw)
            return dict(row,maximum=21,average=21),budget
        base.prepare=changed
        AtlasService(base).run(owner,[],selection_deadline=time.monotonic()+60)
        self.assertEqual(calls,[0])

    def test_no_return_route_or_no_binding_callback_keeps_first_result(self):
        for mode in ('return','callback'):
            with self.subTest(mode=mode):
                owner,base,calls=self.protection_case([20,10,5,4]);prepare=base.prepare
                def unavailable(owner,report,candidate,rules,**kwargs):
                    if candidate['id']==0:return None,dict(allowed=False,reason='unreachable')
                    return prepare(owner,report,candidate,rules,**kwargs)
                base.prepare=unavailable if mode=='return' else None
                AtlasService(base).run(owner,[],selection_deadline=time.monotonic()+60)
                self.assertEqual(calls,[0])

    def test_trial_reserves_time_for_full_verified_return(self):
        owner,base,calls=self.protection_case([20,10,5,4])
        AtlasService(base).run(owner,[],selection_deadline=time.monotonic()+8)
        self.assertEqual(calls,[0])

    def test_unverified_transform_cannot_replace_measured_result(self):
        owner,base,calls=self.protection_case([20,10,5,4]);prepare=base.prepare
        def transform(*a,**kw):
            row,budget=prepare(*a,**kw)
            return row,dict(budget,actions=dict(rotate=1,wheel=2,drag=0))
        base.prepare=transform
        AtlasService(base).run(owner,[],selection_deadline=time.monotonic()+60)
        self.assertEqual(calls,[0])

    def test_regression_returns_to_best_observed_pose_not_original_proposal(self):
        owner,base,calls=self.protection_case([20,10,30,2]);execute=base.default
        seen=[]
        def first(owner,report,candidate,rules,**kwargs):
            # Execution replanning reached a different pose from row 0.
            return execute(owner,report,dict(candidate,dx=3),rules,**kwargs)
        def choice(owner,report,candidate,rules,**kwargs):
            seen.append(candidate)
            return execute(owner,report,candidate,rules,**kwargs)
        base.default=first;base.choice=choice
        result=AtlasService(base).run(owner,[],selection_deadline=time.monotonic()+60)
        self.assertEqual(calls,[0,1,2,1])
        self.assertEqual(result['candidate_id'],1)
        self.assertEqual(result['maximum'],10)
        np.testing.assert_allclose(result['actual_pose'],[[1,0,5],[0,1,0]])
        self.assertTrue(all(row['protect_observed_result'] for row in seen))

    def test_return_uses_replanned_first_pose(self):
        owner,base,calls=self.protection_case([20,30,5,4]);execute=base.default
        base.default=lambda owner,report,candidate,rules,**kw:execute(
            owner,report,dict(candidate,dx=3),rules,**kw)
        result=AtlasService(base).run(owner,[],selection_deadline=time.monotonic()+60)
        self.assertEqual(calls,[0,1,0])
        np.testing.assert_allclose(result['actual_pose'],[[1,0,3],[0,1,0]])

    def test_untrusted_worse_result_does_not_send_return_or_show_old_result_as_current(self):
        owner,base,calls=self.protection_case([20,30,5,4]);execute=base.choice
        def failed(*a,**kw):
            return dict(execute(*a,**kw),actual_pose=None,recovered=True,pose_reliable=False)
        base.choice=failed
        result=AtlasService(base).run(owner,[],selection_deadline=time.monotonic()+60)
        self.assertEqual(calls,[0,1])
        self.assertEqual(result['maximum'],30)
        self.assertEqual(result['best_result']['maximum'],20)
        self.assertFalse(result['best_result_current'])
        self.assertFalse(result['restore_attempted'])
        self.assertEqual(owner.events[-1][0],'atlas_best_not_restored')

    def test_failed_return_ends_trials_and_keeps_historical_result_separate(self):
        owner,base,calls=self.protection_case([20,30,5,4]);execute=base.choice
        def failed(*a,**kw):
            result=execute(*a,**kw)
            return dict(result,maximum=25,average=25) if result['candidate_id']==0 else result
        base.choice=failed
        result=AtlasService(base).run(owner,[],selection_deadline=time.monotonic()+60)
        self.assertEqual(calls,[0,1,0])
        self.assertEqual(result['maximum'],25)
        self.assertEqual(result['best_result']['maximum'],20)
        self.assertFalse(result['best_result_current'])

    def test_preparation_interrupt_is_not_swallowed_as_unavailable_candidate(self):
        owner,base,calls=self.protection_case([20,10,5,4])
        def interrupted(*a,**kw):raise InterruptedError('F9')
        base.prepare=interrupted
        with self.assertRaises(InterruptedError):
            AtlasService(base).run(owner,[],selection_deadline=time.monotonic()+60)
        self.assertEqual(calls,[0])

    def test_partial_callback_result_does_not_enable_speculative_trial(self):
        owner,base,calls=self.protection_case([20,10,5,4]);execute=base.default
        base.default=lambda *a,**kw:dict(execute(*a,**kw),maximum=None)
        AtlasService(base).run(owner,[],selection_deadline=time.monotonic()+60)
        self.assertEqual(calls,[0])

    def test_registration_failure_never_triggers_another_candidate(self):
        base=self.callbacks();calls=[];owner=Owner()
        def failed(*a,**kw):raise RuntimeError('registration')
        base.default=failed;base.choice=lambda *a,**kw:calls.append(1)
        result=AtlasService(base).run(owner,[],selection_deadline=time.monotonic()+30)
        self.assertIsNone(result)
        self.assertEqual(calls,[])
        self.assertEqual(owner.events[-1][0],'atlas_recovery_unavailable')

    def test_recovered_default_is_terminal_when_pose_is_untrusted(self):
        owner=Owner();base=self.callbacks();calls=[]
        def recovered(*a,**kw):
            calls.append('default')
            return dict(candidate_id=0,verified=True,recovered=True,
                        positioning_complete=False,pose_reliable=False,
                        actual_pose=None,accepted=False)
        base.default=recovered;base.choice=lambda *a,**kw:calls.append('choice')
        result=AtlasService(base).run(owner,[],selection_deadline=time.monotonic()+30)
        self.assertTrue(result['recovered'])
        self.assertEqual(calls,['default'])
        self.assertNotIn('atlas_default_verified',[kind for kind,_ in owner.events])
        self.assertNotIn('atlas_selection_expired',[kind for kind,_ in owner.events])

    def test_native_zoom_recovery_can_rebase_to_another_candidate(self):
        owner=Owner();base=self.callbacks();calls=[]
        def recovered(owner,report,candidate,rules,**kwargs):
            calls.append(('default',candidate['id']))
            return dict(candidate_id=candidate['id'],verified=True,recovered=True,
                        positioning_complete=False,pose_reliable=True,
                        actual_pose=[[1,0,0],[0,1,0]],accepted=False,
                        exact_matches=0,maximum=20,average=20)
        def alternate(owner,report,candidate,rules,**kwargs):
            calls.append(('choice',candidate['id']))
            return dict(candidate_id=candidate['id'],verified=True,accepted=True,
                        actual_pose=[[1,0,0],[0,1,0]],maximum=0,average=0)
        base.default=recovered;base.choice=alternate;owner.selection=None
        result=AtlasService(base).run(owner,[],selection_deadline=time.monotonic()+30)
        self.assertEqual(calls,[('default',0),('choice',1)])
        self.assertTrue(result['accepted'])

    def test_capture_or_build_fault_is_reported_as_recovery(self):
        owner=Owner();base=self.callbacks()
        base.acquire=lambda *a,**k: (_ for _ in ()).throw(RuntimeError('capture fault'))
        self.assertIsNone(AtlasService(base).run(owner,[]))
        self.assertEqual(owner.events[-1][0],'atlas_recovery_unavailable')
        owner=Owner();base=self.callbacks()
        base.build=lambda *a,**k: (_ for _ in ()).throw(RuntimeError('build fault'))
        self.assertIsNone(AtlasService(base).run(owner,[]))
        self.assertEqual(owner.events[-1][0],'atlas_recovery_unavailable')

    def test_shorter_candidate_is_used_when_best_does_not_fit_game_time(self):
        base=self.callbacks();build=base.build
        def changed(*a,**kw):
            report=build(*a,**kw);report['candidates'][0].update(angle=170,scale=.7)
            return report
        base.build=changed
        result=AtlasService(base).run(Owner(),[],selection_deadline=time.monotonic()+10)
        self.assertEqual(result['id'],1)

    def test_best_recorded_pose_is_not_rejected_by_conservative_pivot_count(self):
        owner=Owner();base=self.callbacks();chosen=[]
        board=(714,425,1212,923)
        markers=((797,796),(963,559),(1129,825))
        base.build=lambda *a,**k:{'quality_gate':{'passed':True},'board':board,
            'markers':markers,'candidates':[
                dict(id=0,dx=91.8756414247431,dy=143.19034613660173,
                     angle=-113.5565384840377,scale=.6274353854671727,
                     zoom_log_step=.009917331588195072,
                     accepted=False,maximum=91.15,average=31.41,
                     exact_matches=1,exact_maximum=3.0948,exact_average=1.5474),
                dict(id=1,dx=278.15625718353186,dy=119.79798282338616,
                     angle=44.95477616213706,scale=.9803607496401302,
                     zoom_log_step=.009917331588195072,
                     accepted=False,maximum=98.58,average=33.89,
                     exact_matches=1,exact_maximum=3.0948,exact_average=1.5474)]}
        def default(owner,report,candidate,rules,**kwargs):
            chosen.append(candidate['id'])
            return dict(self.verified(owner,report,candidate,rules),accepted=False)
        base.default=default
        result=AtlasService(base).run(owner,[],selection_deadline=time.monotonic()+38.7)
        self.assertEqual(chosen,[0])
        self.assertEqual(result['candidate_id'],0)


if __name__=='__main__':unittest.main()
