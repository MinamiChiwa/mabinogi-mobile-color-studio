import json
from pathlib import Path
import tempfile
import unittest
from gesture_evidence import capture_evidence,condition_summary


class EvidenceTests(unittest.TestCase):
    def test_only_last_frame_pair_is_available_and_matrix_scale_keeps_precision(self):
        with tempfile.TemporaryDirectory() as directory:
            capture=Path(directory)/'session-a'/'atlas_capture'
            execution=capture/'execution';execution.mkdir(parents=True)
            (capture/'log.json').write_text(json.dumps([
                dict(kind='ready',board=[0,0,500,500]),
                dict(kind='frame',geometry=[0,0,1280,960]),
                dict(kind='zoom_calibration',passed=True,measurements=[
                    dict(steps=4,motion=dict(scale=1.04,matrix=[[1.040567,0,0],[0,1.040567,0]]))])]),encoding='utf8')
            (execution/'before.png').touch();(execution/'after.png').touch()
            (execution/'attempt-01.json').write_text(json.dumps(dict(
                events=[dict(kind='atlas_registration',phase='positioning',step=1),
                        dict(kind='atlas_registration',phase='hex_verification',step=0)],
                motion_frames=dict(before='before.png',after='after.png'))),encoding='utf8')
            result=capture_evidence(capture)
        self.assertIsNone(result['dpi'])
        self.assertEqual(len(result['execution_pairs']),1)
        self.assertEqual(result['execution_pairs'][0]['phase'],'hex_verification')
        self.assertAlmostEqual(result['calibration'][0]['scale'],1.040567)
        self.assertFalse(result['calibration'][0]['raw_frame_pair_available'])

    def test_conditions_keep_unmeasured_and_rejected_responses(self):
        base=dict(board=[0,0,500,500],session='a',action='rotate',command=.1)
        rows=[dict(base,status='unmeasured'),dict(base,status='measured_rejected',
              response=dict(request_error=-.1,cursor_arc_error=0,no_angular_response=True))]
        group=condition_summary(rows)[0]
        self.assertEqual(group['samples'],2)
        self.assertEqual(group['statuses'],dict(unmeasured=1,measured_rejected=1))
        self.assertEqual(group['no_angular_response'],1)
        self.assertEqual(group['request_residual_degrees']['count'],1)


if __name__=='__main__':unittest.main()
