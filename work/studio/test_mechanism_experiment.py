import unittest
from mechanism_experiment import MechanismExperimentRecorder, record_probe_event

class MechanismRecorderTests(unittest.TestCase):
    def test_explicit_consumption_and_evidence_groups(self):
        r = MechanismExperimentRecorder(started_at=10.0)
        clock = lambda: 12.5
        r.set_consumption(True)
        b = r.baseline(frame='max_sampling', hexes=['#010203'] * 3, countdown_seconds=118.0, clock=clock)
        a = r.action(name='drag+1', direction='drag', step=1, frame_before='max_sampling', frame_after='settled', hex_first=['#010203'] * 3, hex_settled=['#010204'] * 3, countdown_before=117.0, countdown_after=115.0, registration_seconds=0.2, clock=clock)
        f = r.finish(status='observed', final_hexes=['#010204'] * 3, countdown_seconds=114.0, return_success=True, clock=clock)
        self.assertEqual(b['kind'], 'mechanism_baseline')
        self.assertEqual(a['action_index'], 1)
        self.assertEqual(f['action_count'], 1)
        report = r.report()
        self.assertEqual(report['dye_consumed'], True)
        self.assertEqual(len(report['observed']), 2)
        self.assertEqual(report['inferred'], [])

    def test_consumption_never_inferred_and_type_checked(self):
        r = MechanismExperimentRecorder(started_at=0.0)
        self.assertIsNone(r.dye_consumed)
        with self.assertRaises(TypeError):
            r.set_consumption(1)
        row = r.finish(status='unknown', clock=lambda: 1.0)
        self.assertIsNone(row['dye_consumed'])

    def test_report_summary_uses_explicit_measurements_only(self):
        r = MechanismExperimentRecorder(started_at=0.0)
        r.action(name='a', delta_e=[1.0, 3.0, 2.0], hit_count=2,
                 input_seconds=1.0, registration_seconds=2.0,
                 clock=lambda: 1.0)
        r.action(name='b', delta_e=[2.0, 4.0, 6.0], hit_count=1,
                 input_seconds=3.0, registration_seconds=4.0,
                 clock=lambda: 2.0)
        r.finish(status='observed', countdown_seconds=10.0,
                 return_success=True, double_frame_confirmed=True,
                 first_usable_elapsed_seconds=4.0, clock=lambda: 3.0)
        summary = r.report()['summary']
        self.assertEqual(summary['max_delta_e'], 6.0)
        self.assertEqual(summary['mean_delta_e'], 3.0)
        self.assertEqual(summary['precise_hit_count'], 2.0)
        self.assertEqual(summary['input_seconds_total'], 4.0)
        self.assertEqual(summary['registration_seconds_total'], 6.0)
        self.assertEqual(summary['registration_seconds_p95'], 3.9)
        self.assertEqual(summary['final_remaining_seconds'], 10.0)
        self.assertTrue(summary['double_frame_confirmed'])
        unknown = MechanismExperimentRecorder(started_at=0.0).report()['summary']
        self.assertIsNone(unknown['max_delta_e'])
        self.assertIsNone(unknown['registration_seconds_p95'])

    def test_probe_bridge_preserves_measured_action_fields(self):
        r = MechanismExperimentRecorder(started_at=0.0)
        record_probe_event(r, 'response_probe_plan', {
            'protocol': 'baseline', 'markers': [[1, 2]],
            'actions': [{'name': 'center_r0_a+1'}],
            'hex_before': ['#010203'],
        }, clock=lambda: 1.0)
        record_probe_event(r, 'response_probe_measurement', {
            'name': 'center_r0_a+1', 'reference': 'max_sampling',
            'settled': 'response_01_settled',
            'gesture': {'kind': 'rotate', 'requested_angle': 1.0},
            'hex_before': ['#010203'], 'hex_after': ['#040506'],
            'hex_first': ['#040506'], 'hex_settled': ['#040506'],
            'input_elapsed_seconds': .25,
            'countdown_before': 118., 'countdown_after': 117.,
            'registration_seconds': .5,
            'registration_complete': True,
            'measurements': {'forward': {'matrix': [[1, 0], [0, 1]]}},
        }, clock=lambda: 2.0)
        action = r.events[-1]
        self.assertEqual(action['hex_before'], ['#010203'])
        self.assertEqual(action['hex_after'], ['#040506'])
        self.assertEqual(action['input_seconds'], .25)
        self.assertEqual(action['countdown_before'], 118.)
        self.assertEqual(action['countdown_after'], 117.)

if __name__ == '__main__':
    unittest.main()
