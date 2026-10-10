"""Guard endpoint ranking, atomic wheel pairs and bounded offline search."""
from test_support import read_local_fixture_text
from test_support import load_local_palette_session
import importlib, importlib.util, json, unittest
from pathlib import Path
from native_input_response import InputGeometry, InputSettings, replay_native_route
from native_palette_scoring import load_session, score_native_pose
from input_gestures import wheel_gesture


class NativeInputRouteSearchTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('native_input_route_search'),
                             'Endpoint color route search is missing')
        self.m=importlib.import_module('native_input_route_search')
        root=Path(__file__).parent/'fixtures/native_palette'
        self.session=load_local_palette_session(root/json.loads(read_local_fixture_text(root/'manifest.json'))['snapshots'][1])
        self.reference=self.session['initial_pose']
        self.geometry=InputGeometry((757,428,1287,958),(624,624))
        self.settings=InputSettings(.5,3,5,.1,.01)
        self.rules=[dict(enabled=True,exact=True,colors=[c],tolerance=0)
                    for c in ['#D8866E','#D0D2B4','#768A60']]

    def search(self,routes,**kw):
        return self.m.search_native_input_routes(self.session,routes,self.reference,self.geometry,
            self.settings,self.rules,sample_policy='all_recorded_points',wheel_delta_per_step=1.,
            now=0.,deadline=120.,**kw)

    def test_atomic_pair_can_hit_colors_when_first_wheel_moves_away(self):
        result=self.search([[]],max_depth=1,max_candidates=300,time_budget_seconds=5.)
        best=result['candidates'][0]
        self.assertEqual(best['prediction']['colors'],['#D8866E','#D0D2B4','#768A60'])
        self.assertTrue(best['prediction']['predicted_accepted'])
        self.assertEqual([g['kind'] for g in best['input_route']],['wheel','wheel'])
        self.assertAlmostEqual(best['final_pose']['scale'],.9998999834,places=9)
        self.assertTrue(best['model_budget_allowed'])
        self.assertFalse(result['execution_verified'])
        seed_rank=score_native_pose(self.session,self.reference,self.rules)['rank']
        first_pose=best['history'][-1]['trace'][0]['pose']
        first_rank=score_native_pose(self.session,first_pose,self.rules)['rank']
        self.assertGreater(first_rank,seed_rank)
        whole=replay_native_route(self.reference,best['input_route'],self.geometry,self.settings,
                       sample_policy='all_recorded_points',wheel_delta_per_step=1.)
        self.assertEqual(whole['final_pose'],best['final_pose'])

    def test_seed_best_and_input_records_are_retained_without_mutation(self):
        route=[wheel_gesture(self.geometry.board,1,(1022,693)).record(),
               wheel_gesture(self.geometry.board,-1,(1054,693)).record()]
        before=json.dumps(route,sort_keys=True)
        result=self.search([[],route],max_depth=0)
        self.assertTrue(result['candidates'][0]['prediction']['predicted_accepted'])
        self.assertEqual(json.dumps(route,sort_keys=True),before)

    def test_duplicates_choose_shorter_route_to_same_endpoint(self):
        zero=wheel_gesture(self.geometry.board,0).record()
        result=self.search([[zero],[]],max_depth=0)
        self.assertEqual(result['candidates'][0]['input_route'],[])
        self.assertGreater(result['duplicate_endpoints'],0)

    def test_expired_and_insufficient_time_never_return_allowed_routes(self):
        result=self.m.search_native_input_routes(self.session,[[]],self.reference,self.geometry,
            self.settings,self.rules,sample_policy='all_recorded_points',wheel_delta_per_step=1.,
            now=5.,deadline=5.)
        self.assertEqual(result['candidates'],[])
        self.assertEqual(result['stop_reason'],'deadline')
        self.assertEqual(self.m.search_native_input_routes(self.session,[[]],self.reference,self.geometry,
            self.settings,self.rules,sample_policy='all_recorded_points',wheel_delta_per_step=1.,
            now=0.,deadline=2.)['candidates'],[])

    def test_candidate_limit_and_cancel(self):
        result=self.search([[]],max_candidates=1)
        self.assertEqual(result['evaluated'],1)
        self.assertEqual(result['stop_reason'],'candidate_limit')
        def stop():raise InterruptedError('F9')
        with self.assertRaises(InterruptedError):self.search([[]],check=stop)

    def test_missing_routes_and_noninitial_reference_fail_closed(self):
        with self.assertRaises(ValueError):self.search([])
        other=dict(self.reference,position=[.01,0.])
        with self.assertRaises(ValueError):
            self.m.search_native_input_routes(self.session,[[]],other,self.geometry,self.settings,
                self.rules,sample_policy='all_recorded_points',wheel_delta_per_step=1.,now=0.,deadline=120.)

    def test_sparse_sampling_and_invalid_limits_are_rejected(self):
        for kw in (dict(max_depth=-1),dict(beam_width=0),dict(max_candidates=0),dict(time_budget_seconds=0)):
            with self.assertRaises(ValueError):self.search([[]],**kw)
        with self.assertRaises(ValueError):
            self.m.search_native_input_routes(self.session,[[]],self.reference,self.geometry,self.settings,
                self.rules,sample_policy='explicit_indices',wheel_delta_per_step=1.,now=0.,deadline=120.)

    def test_scoring_elapsed_rejects_seed_without_execution_reserve(self):
        tick=[0.]
        calls=[0]
        def check():
            calls[0]+=1
            # Consume execution budget during seed replay/scoring.
            if calls[0]>=8:tick[0]=119.
        result=self.search([[]],max_depth=0,time_budget_seconds=120.,check=check,clock=lambda:tick[0])
        self.assertEqual(result['candidates'],[])
        self.assertGreaterEqual(result['rejected_budget']+result['expired_after_search'],1)

    def test_picker_at_edge_does_not_make_macro_generation_abort(self):
        session=dict(self.session,picker_uv=[[1/6,0.],[.5,1.],[5/6,0.]])
        result=self.m.search_native_input_routes(session,[[]],self.reference,self.geometry,self.settings,
            self.rules,sample_policy='all_recorded_points',wheel_delta_per_step=1.,now=0.,deadline=120.,
            max_depth=1,max_candidates=300)
        self.assertGreater(result['evaluated'],1)

    def test_outside_seed_points_are_rejected(self):
        route=[wheel_gesture(self.geometry.board,1).record()]
        route[0]['points']=[(0,0)]
        with self.assertRaises(ValueError):self.search([route],max_depth=0)

    def test_stalled_endpoint_is_not_expanded_again_each_layer(self):
        settings=InputSettings(.5,3,1e6,1e6,0.)
        result=self.m.search_native_input_routes(self.session,[[]],self.reference,self.geometry,settings,
            self.rules,sample_policy='all_recorded_points',wheel_delta_per_step=1.,now=0.,deadline=120.,
            max_depth=4,max_candidates=1000)
        self.assertEqual(result['layers_completed'],1)
        self.assertEqual(result['stop_reason'],'no_new_endpoints')
        self.assertEqual(result['expanded_endpoints'],1)


if __name__=='__main__':unittest.main()
