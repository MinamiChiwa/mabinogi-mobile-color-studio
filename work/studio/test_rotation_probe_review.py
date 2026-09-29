import unittest
import numpy as np
from atlas_pose import pose_fields
from input_gestures import rotation_gesture
from rotation_probe_review import compare_responses


class ResponseReviewTests(unittest.TestCase):
    board=(1125,258,1826,959)
    markers=((1242,669),(1476,673),(1709,753))

    def sample(self):
        gesture=rotation_gesture(self.board,.4)
        return dict(step=1,name='synthetic',variant='legacy',repeat=0,anchor_name='center',
                    gesture=gesture.record(),registration_complete=True,
                    response=pose_fields(np.eye(3),self.board),
                    input_trace=[dict(slot=i,requested=list(p),actual_client=list(p),error=None)
                                 for i,p in enumerate(gesture.points)])

    def test_integer_arc_error_is_distinct_from_request_and_marker_error(self):
        row=self.sample();result=compare_responses([row],self.board,self.markers)
        value=result['observations'][0]
        self.assertNotEqual(value['request_error'],value['arc_error'])
        self.assertGreater(max(value['marker_errors']),1.)
        self.assertTrue(result['trace_complete'])
        self.assertEqual(result['trace_mismatches'],0)
        self.assertAlmostEqual(value['trace']['actual_cursor_arc_degrees'],value['arc_degrees'])
        self.assertFalse(result['response_model_installed'])

    def test_missing_failed_and_duplicate_trace_samples_do_not_pass(self):
        for mode in ('missing','failed','duplicate','invalid'):
            with self.subTest(mode=mode):
                row=self.sample()
                if mode=='missing':row['input_trace'].pop()
                if mode=='failed':row['input_trace'][0]['actual_client']=None
                if mode=='duplicate':row['input_trace'].append(row['input_trace'][0])
                if mode=='invalid':row['input_trace'][0]['slot']=-1
                result=compare_responses([row],self.board,self.markers)
                self.assertFalse(result['trace_complete'])
                self.assertIsNone(result['observations'][0]['trace']['actual_cursor_arc_degrees'])

    def test_coordinate_mismatch_and_incomplete_registration_are_visible(self):
        row=self.sample();row['input_trace'][-1]['actual_client'][0]+=1
        row['registration_complete']=False
        result=compare_responses([row],self.board,self.markers)
        self.assertEqual(result['trace_mismatches'],1)
        self.assertEqual(result['variants']['legacy']['measured'],0)
        self.assertEqual(result['variants']['legacy']['angle_error'],{'count':0})


if __name__=='__main__':unittest.main()
