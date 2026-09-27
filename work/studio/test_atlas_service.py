import unittest
import time
import threading
from atlas_service import AtlasService, AtlasCallbacks, quality_failure_message
from atlas_pose import candidate_pose, homogeneous
import numpy as np


class Owner:
    def __init__(self):self.events=[];self.stop=None;self.selection=None
    def event(self,kind,**data):self.events.append((kind,data))
    def wait_candidate_choice(self,batch_id,deadline):return self.selection


class ServiceTests(unittest.TestCase):
    def verified(self,owner,report,candidate,rules,**kwargs):
        pose=candidate_pose(candidate,report['board'])@homogeneous(report.get('current_pose',np.eye(3)))
        report['current_pose']=pose
        return dict(id=candidate['id'],candidate_id=candidate['id'],accepted=True,
                    verified=True,actual_pose=pose[:2].tolist())

    def callbacks(self,gate=True):
        return AtlasCallbacks(
            acquire=lambda *a,**k:'capture',
            build=lambda *a,**k:{'quality_gate':{'passed':gate},'candidates':[
                dict(id=0,dx=0,dy=0,accepted=True,maximum=0,average=0),
                dict(id=1,dx=12,dy=12,accepted=True,maximum=1,average=1)],'board':(0,0,900,900)},
            default=self.verified,choice=self.verified)

    def test_quality_gate_blocks_candidate_publication(self):
        owner=Owner();service=AtlasService(self.callbacks(False))
        self.assertIsNone(service.run(owner,[]))
        self.assertEqual([e[0] for e in owner.events],['atlas_status','atlas_invalidated'])
        self.assertFalse(owner.events[-1][1]['search_performed'])
        self.assertEqual(owner.events[-1][1]['reason'],'atlas_quality_failed')

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

    def test_choice_is_executed_after_default(self):
        owner=Owner();owner.selection=1;service=AtlasService(self.callbacks())
        result=service.run(owner,[],selection_deadline=time.monotonic()+30)
        self.assertEqual(result['id'],1)
        self.assertEqual(owner.events[-1][0],'atlas_verified')

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

    def test_automatic_candidate_prioritizes_exact_region_count_over_similar_error(self):
        owner=Owner();base=self.callbacks();selected=[]
        base.build=lambda *a,**k:{'quality_gate':{'passed':True},'candidates':[
            dict(id=0,dx=0,dy=0,accepted=False,maximum=30,average=20,
                 exact_matches=2,exact_total=2,exact_maximum=0,exact_average=0),
            dict(id=1,dx=1,dy=1,accepted=False,maximum=0,average=0,
                 exact_matches=1,exact_total=2,exact_maximum=0,exact_average=0)],
            'board':(0,0,900,900)}
        def compromise(owner,report,candidate,rules,**kwargs):
            selected.append(candidate['id'])
            return dict(self.verified(owner,report,candidate,rules),accepted=False)
        base.default=compromise
        result=AtlasService(base).run(owner,[],selection_deadline=time.monotonic()+30)
        self.assertEqual(selected,[0])
        self.assertEqual(result['candidate_id'],0)

    def test_overall_color_error_precedes_exact_region_error_on_match_count_tie(self):
        owner=Owner();base=self.callbacks();selected=[]
        base.build=lambda *a,**k:{'quality_gate':{'passed':True},'candidates':[
            dict(id=2,dx=0,dy=0,accepted=False,maximum=98.5834,average=33.8927,
                 exact_matches=1,exact_total=2,exact_maximum=3.0948,exact_average=1.5474),
            dict(id=7,dx=1,dy=1,accepted=False,maximum=39.6576,average=14.3465,
                 exact_matches=1,exact_total=2,exact_maximum=3.3818,exact_average=1.6909)],
            'board':(0,0,900,900)}
        def compromise(owner,report,candidate,rules,**kwargs):
            selected.append(candidate['id'])
            return dict(self.verified(owner,report,candidate,rules),accepted=False)
        base.default=compromise
        result=AtlasService(base).run(owner,[],selection_deadline=time.monotonic()+30)
        self.assertEqual(selected,[7])
        self.assertEqual(result['candidate_id'],7)
        candidates=next(data['candidates'] for kind,data in owner.events if kind=='atlas_candidates')
        self.assertEqual([row['id'] for row in candidates],[7,2])

    def test_failed_hex_automatically_tries_next_from_measured_pose(self):
        owner=Owner();base=self.callbacks();moves=[]
        def failed(owner,report,candidate,rules,**kw):
            result=self.verified(owner,report,candidate,rules)
            report['current_pose']=homogeneous([[1,0,.4],[0,1,-.2]])
            return dict(result,accepted=False,actual_pose=report['current_pose'][:2].tolist())
        def choice(owner,report,candidate,rules,**kw):
            moves.append(candidate);return self.verified(owner,report,candidate,rules)
        base.default=failed;base.choice=choice
        result=AtlasService(base).run(owner,[],selection_deadline=time.monotonic()+30)
        self.assertTrue(result['accepted']);self.assertEqual(result['id'],1)
        np.testing.assert_allclose([moves[0]['dx'],moves[0]['dy']],[11.6,12.2])
        kinds=[k for k,_ in owner.events]
        self.assertLess(kinds.index('atlas_candidate_failed'),kinds.index('atlas_default_verified'))

    def test_all_failed_hex_reports_last_actual_color_without_waiting(self):
        owner=Owner();base=self.callbacks();calls=[]
        def fail(owner,report,candidate,rules,**kw):
            calls.append(candidate['id'])
            return dict(self.verified(owner,report,candidate,rules),accepted=False)
        base.default=base.choice=fail
        owner.wait_candidate_choice=lambda *a: self.fail('Failed result cannot be called a successful default')
        result=AtlasService(base).run(owner,[],selection_deadline=time.monotonic()+30)
        self.assertEqual(calls,[0,1]);self.assertFalse(result['accepted'])
        self.assertEqual(owner.events[-1][0],'atlas_verified')
        self.assertNotIn('atlas_default_verified',[k for k,_ in owner.events])

    def test_registration_failure_never_triggers_another_candidate(self):
        base=self.callbacks();calls=[]
        def failed(*a,**kw):raise RuntimeError('registration')
        base.default=failed;base.choice=lambda *a,**kw:calls.append(1)
        with self.assertRaisesRegex(RuntimeError,'registration'):
            AtlasService(base).run(Owner(),[],selection_deadline=time.monotonic()+30)
        self.assertEqual(calls,[])

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
