from test_support import read_local_fixture_text
from test_support import load_local_palette_session
import importlib
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from input_gestures import drag_gesture
from native_input_response import InputGeometry, InputSettings
from native_palette_scoring import load_session


class NativeInputAssessmentTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('native_input_assessment'),
                             'Conditional input endpoint scoring is missing')
        self.m=importlib.import_module('native_input_assessment')
        root=Path(__file__).parent/'fixtures/native_palette'
        name=json.loads(read_local_fixture_text(root/'manifest.json'))['snapshots'][1]
        self.session=load_local_palette_session(root/name)
        self.reference=self.session['initial_pose']
        self.geometry=InputGeometry((757,428,1287,958),(530,530))
        self.settings=InputSettings(.5,3,5,.1,.01)
        self.rules=[dict(enabled=True,exact=True,colors=[c],tolerance=0)
                    for c in ['#D7856D','#D0D2B4','#6D8354']]

    def test_replay_rescores_micro_drag_as_no_motion_and_does_not_certify(self):
        budget=dict(allowed=True,input_route=[drag_gesture(self.geometry.board,4,0).record()])
        result=self.m.assess_native_input_route(self.session,budget,self.reference,
                    self.geometry,self.settings,self.rules,sample_policy='all_recorded_points')
        self.assertEqual(result['input_prediction']['colors'],['#D7856D','#D0D2B4','#6D8354'])
        self.assertTrue(result['input_predicted_accepted'])
        self.assertTrue(result['plan_allowed'])
        self.assertFalse(result['execution_verified'])
        self.assertFalse(result['game_response_verified'])

    def test_budget_rejection_is_preserved_despite_exact_predicted_colors(self):
        result=self.m.assess_native_input_route(self.session,dict(allowed=False,input_route=[]),
                    self.reference,self.geometry,self.settings,self.rules,sample_policy='all_recorded_points')
        self.assertFalse(result['plan_allowed'])
        self.assertTrue(result['input_predicted_accepted'])

    def test_missing_route_is_not_treated_as_zero_motion(self):
        with self.assertRaises(ValueError):
            self.m.assess_native_input_route(self.session,dict(allowed=True),self.reference,
                self.geometry,self.settings,self.rules,sample_policy='all_recorded_points')

    def test_cancel_propagates(self):
        def stop():raise InterruptedError('F9')
        with self.assertRaises(InterruptedError):
            self.m.assess_native_input_route(self.session,dict(allowed=True,input_route=[]),
                self.reference,self.geometry,self.settings,self.rules,
                sample_policy='all_recorded_points',check=stop)

    def test_stepwise_entry_scores_replayed_endpoint_and_preserves_budget(self):
        self.assertTrue(hasattr(self.m, 'assess_native_compiled_action'))
        result=self.m.assess_native_compiled_action(self.session,self.reference,self.reference,
                    self.geometry,self.settings,self.rules, wheel_delta_per_step=1.,
                    sample_policy='all_recorded_points',now=0.,deadline=120.)
        self.assertTrue(result['plan_allowed'])
        self.assertTrue(result['input_predicted_accepted'])
        self.assertEqual(result['budget']['input_route'],[])
        self.assertEqual(result['replay']['final_pose'],result['budget']['final_pose'])
        self.assertFalse(result['game_response_verified'])

    def test_stepwise_entry_retains_exact_prediction_when_time_is_insufficient(self):
        self.assertTrue(hasattr(self.m, 'assess_native_compiled_action'))
        result=self.m.assess_native_compiled_action(self.session,self.reference,self.reference,
                    self.geometry,self.settings,self.rules, wheel_delta_per_step=1.,
                    sample_policy='all_recorded_points',now=0.,deadline=2.)
        self.assertFalse(result['plan_allowed'])
        self.assertTrue(result['input_predicted_accepted'])
        self.assertEqual(result['budget']['reason'],'insufficient_time')

    def test_stepwise_entry_does_not_certify_unreached_geometry(self):
        self.assertTrue(hasattr(self.m, 'assess_native_compiled_action'))
        target=dict(self.reference,position=[.25/530,0.])
        result=self.m.assess_native_compiled_action(self.session,target,self.reference,
                    self.geometry,self.settings,self.rules,wheel_delta_per_step=1.,
                    sample_policy='all_recorded_points',now=0.,deadline=120.)
        self.assertFalse(result['plan_allowed'])
        self.assertFalse(result['budget']['modelled_reached'])
        self.assertEqual(result['input_prediction']['native_pose'],self.reference)

    def test_stepwise_entry_charges_scoring_time_against_final_budget(self):
        self.assertTrue(hasattr(self.m, 'assess_native_compiled_action'))
        ticks=[0.]
        original=self.m.score_native_pose
        def score_and_advance(*args,**kwargs):
            prediction=original(*args,**kwargs)
            ticks[0]=2.
            return prediction
        with patch.object(self.m,'score_native_pose',side_effect=score_and_advance):
            result=self.m.assess_native_compiled_action(self.session,self.reference,self.reference,
                self.geometry,self.settings,self.rules,wheel_delta_per_step=1.,
                sample_policy='all_recorded_points',now=0.,deadline=5.,clock=lambda:ticks[0])
        self.assertTrue(result['input_predicted_accepted'])
        self.assertFalse(result['plan_allowed'])
        self.assertEqual(result['budget']['remaining'],3.)
        self.assertEqual(result['budget']['reason'],'insufficient_time')


if __name__=='__main__':unittest.main()
