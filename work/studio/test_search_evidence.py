"""Evidence cannot infer missing reads or erase expensive stage samples."""
import json
import math
import unittest
import numpy as np

from search_evidence import RoundEvidence


class EvidenceTests(unittest.TestCase):
    def ledger(self):
        rules = [dict(enabled=True, exact=True, colors=['#FFFFFF'], tolerance=0),
                 dict(enabled=False), dict(enabled=False)]
        return RoundEvidence('round', 'source', rules, 120., ready_at=0.)

    def test_sparse_cost_estimates_use_observed_maximum_and_default_floor(self):
        evidence = self.ledger()
        for seconds in (.1, .2, 4.):
            evidence.record_duration('registration', seconds)
        self.assertEqual(evidence.estimate_seconds('registration'), 4.)
        self.assertGreater(evidence.estimate_seconds('ocr'), 0.)

    def test_p95_is_reported_but_not_confused_with_a_guarantee(self):
        evidence = self.ledger()
        for seconds in range(1, 21):
            evidence.record_duration('registration', seconds)
        report = evidence.report(30.)['durations']['registration']
        self.assertAlmostEqual(report['p95_seconds'], 19.05)
        self.assertEqual(report['mean_seconds'], 10.5)
        self.assertEqual(report['total_seconds'], 210.)
        self.assertEqual(report['estimate_source'], 'p95_with_default_floor')

    def test_one_frame_does_not_become_a_verified_result(self):
        evidence = self.ledger()
        row = evidence.record_observation(['#FFFFFF', None, None], frame_ids=('same', 'same'),
            pose=None, pose_epoch=0, verified=True, now=10.)
        self.assertFalse(row['verified'])
        self.assertIsNone(evidence.report(10.)['first_usable_elapsed_seconds'])

    def test_missing_enabled_hex_keeps_unknown_error_and_cannot_be_best(self):
        evidence = self.ledger()
        row = evidence.record_observation([None, None, None], frame_ids=('a', 'b'),
            pose=None, pose_epoch=0, verified=True, now=10.)
        self.assertFalse(row['verified'])
        self.assertIsNone(row['maximum'])
        self.assertIsNone(evidence.report(10.)['best_observed'])
        json.dumps(evidence.report(10.), allow_nan=False)

    def test_near_white_is_compromise_and_read_only_is_not_positioned(self):
        evidence = self.ledger()
        row = evidence.record_observation(['#FFFEFE', '#FFFFFF', '#FFFFFF'],
            frame_ids=('a', 'b'), pose=None, pose_epoch=0, verified=True, now=10.)
        self.assertTrue(row['verified'])
        self.assertFalse(row['accepted'])
        self.assertTrue(row['compromise'])
        self.assertEqual(row['codes'], ['#FFFEFE', None, None])
        self.assertIsNone(evidence.report(10.)['first_usable_elapsed_seconds'])

    def test_later_worse_sample_does_not_replace_verified_best(self):
        evidence = self.ledger()
        pose = [[1, 0, 0], [0, 1, 0]]
        for at, color in ((10., '#FFFEFE'), (20., '#777777')):
            evidence.record_observation([color, None, None], frame_ids=(f'{at}-a', f'{at}-b'),
                pose=pose, pose_epoch=0, verified=True, now=at, positioned=True)
        report = evidence.report(21.)
        self.assertEqual(report['best_observed']['codes'][0], '#FFFEFE')
        self.assertEqual(report['current_observation']['codes'][0], '#777777')
        self.assertEqual(report['first_usable_elapsed_seconds'], 10.)
        self.assertEqual(report['final_remaining_seconds'], 99.)
        self.assertEqual(report['remaining_source'], 'monotonic_game_deadline')

    def test_invalid_duration_cannot_become_zero_cost(self):
        evidence = self.ledger()
        for seconds in (None, -1., math.inf, math.nan, True):
            with self.subTest(seconds=seconds), self.assertRaises(ValueError):
                evidence.record_duration('registration', seconds)
        with self.assertRaises(ValueError):
            evidence.record_duration('invented_stage', .1)

    def test_invalid_pose_never_becomes_a_positioned_result(self):
        evidence = self.ledger()
        with self.assertRaises(ValueError):
            evidence.record_observation(['#FFFFFF', None, None], frame_ids=('a', 'b'),
                pose=[[1, 0, math.nan], [0, 1, 0]], pose_epoch=0,
                verified=True, now=10., positioned=True)

    def test_runtime_evidence_requires_two_independent_matching_capture_reads(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from atlas_runtime import Adapter
        evidence=self.ledger()
        image=np.zeros((20,20,3),np.uint8)
        game=SimpleNamespace(capture=lambda:image.copy(),check=lambda:None)
        scene=SimpleNamespace(cards=[(0,0,5,5)],markers=[(2,10)])
        adapter=Adapter(game,scene,'capture')
        adapter.evidence=evidence;adapter.enabled=[True]
        with patch('atlas_runtime.read_codes',return_value=['#FFFFFF']):
            first=adapter.capture();adapter.read_codes(first)
            adapter.read_codes(first)
            self.assertEqual(adapter.confirmed_frame_ids(['#FFFFFF']),())
            second=adapter.capture();adapter.read_codes(second)
        self.assertEqual(len(adapter.confirmed_frame_ids(['#FFFFFF'])),2)
        self.assertEqual(evidence.report(10.)['durations']['capture']['count'],2)
        self.assertEqual(evidence.report(10.)['durations']['ocr']['count'],3)

    def test_soft_cpu_cutoff_preserves_completed_pool_and_hard_stop_propagates(self):
        from analyze_live_atlas import budgeted_candidate_search
        from atlas_stage_budget import StageBudgetExceeded
        previous=[dict(id=0)]
        def soft():raise StageBudgetExceeded('return reserve')
        extra,reason=budgeted_candidate_search(lambda:[dict(id=1)],soft)
        self.assertEqual(previous+extra,previous)
        self.assertEqual(reason,'return reserve')
        def hard():raise InterruptedError('F9')
        with self.assertRaises(InterruptedError):
            budgeted_candidate_search(lambda:[],hard)

    def test_final_runner_report_uses_exit_time_without_accessing_game_after_f9(self):
        import tempfile
        from unittest.mock import patch
        from engine import Runner
        from platform_win import Interrupted
        events=[]
        def interrupted(owner,*args,**kwargs):
            owner.round_evidence=self.ledger()
            raise Interrupted('F9')
        with tempfile.TemporaryDirectory() as folder,patch('engine.configure_ocr'), \
             patch('engine.time.monotonic',return_value=121.):
            runner=Runner(lambda kind,data:events.append((kind,data)),folder,atlas_runner=interrupted)
            runner.launch([],strategy='atlas')
        reports=[data for kind,data in events if kind=='round_evidence']
        self.assertEqual(len(reports),1)
        self.assertEqual(reports[0]['final_remaining_seconds'],0.)
        self.assertIsNone(reports[0]['current_observation'])



if __name__ == '__main__':
    unittest.main()
