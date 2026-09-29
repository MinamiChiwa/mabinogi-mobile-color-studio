import json
from pathlib import Path
import tempfile
import unittest
from gesture_replay import read_attempt, rotation_holdouts


class ReplayTests(unittest.TestCase):
    def test_stalled_response_is_preserved_without_becoming_training_success(self):
        data=dict(error='stalled rotation',events=[
            dict(kind='atlas_command',step=1,action='rotate',command=12,anchor=[249,249]),
            dict(kind='atlas_registration',phase='positioning',step=1,passed=True,
                 measured=[[1,0,0],[0,1,0]])])
        with tempfile.TemporaryDirectory() as directory:
            file=Path(directory)/'attempt-01.json'
            file.write_text(json.dumps(data),encoding='utf8')
            rows=read_attempt(file,(0,0,498,498),'session-a')
        self.assertEqual(rows[0]['status'],'measured_rejected')
        self.assertTrue(rows[0]['response']['no_angular_response'])
        self.assertEqual(rotation_holdouts(rows)['request']['fitted']['count'],0)

    def test_failed_unmeasured_command_is_retained(self):
        data=dict(error='registration failed',events=[dict(kind='atlas_command',step=1,
                  action='rotate',command=.01,anchor=[249,249])])
        with tempfile.TemporaryDirectory() as directory:
            file=Path(directory)/'attempt-01.json'
            file.write_text(json.dumps(data),encoding='utf8')
            rows=read_attempt(file,(0,0,498,498),'session-a')
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['status'],'unmeasured')
        self.assertEqual(rows[0]['attempt_error'],'registration failed')
        self.assertEqual(rows[0]['input_source'],'reconstructed_legacy_descriptor')
        self.assertFalse(rows[0]['input']['has_effect'])

    def test_fits_use_other_sessions_only(self):
        rows=[dict(session=s,action='rotate',status='measured',command=10,
                   input={'cursor_arc_degrees':10},response={'angle':angle})
              for s,angle in [('a',5),('b',10),('c',15)]]
        folds=rotation_holdouts(rows)['request']['folds']
        self.assertEqual(len(folds),3)
        for fold in folds:
            self.assertNotIn(fold['held_out_session'],fold['training_sessions'])
        self.assertAlmostEqual(folds[0]['gain'],1.25)
        self.assertAlmostEqual(folds[2]['gain'],.75)


if __name__=='__main__':unittest.main()
