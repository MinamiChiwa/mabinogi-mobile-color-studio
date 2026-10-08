"""Keep test cleanup from silently dropping current safety coverage."""
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from run_tests import discover_tests, profile_for, select_tests


class SuiteProfileTests(unittest.TestCase):
    def test_current_safety_paths_stay_in_production(self):
        for module in ('test_single_region_search', 'test_single_region_zoom',
                       'test_atlas_service', 'test_execution_return_guard',
                       'test_atlas_checkpoint_recovery', 'test_live_atlas_capture',
                       'test_hotkeys', 'test_candidate_ranking'):
            with self.subTest(module=module):
                self.assertEqual(profile_for(module, 'SafetyTests', 'test_stop'),
                                 'production')

    def test_mixed_files_keep_shared_features_without_old_search_policy(self):
        self.assertEqual(profile_for('test_exploration', 'ExplorationTests',
            'test_accepted_similarity_keeps_exploring_instead_of_finishing'), 'legacy')
        self.assertEqual(profile_for('test_exploration', 'ExplorationTests',
            'test_preview_exact_set_and_unique_colors'), 'production')
        self.assertEqual(profile_for('test_best_result', 'BestResultTests',
            'test_eyedropper_uses_frozen_pixel_and_clamps_edges'), 'production')
        self.assertEqual(profile_for('test_product', 'ProductTests',
            'test_disabled_cards_do_not_run_ocr'), 'production')

    def test_missing_archive_checks_are_visible_in_the_fixture_profile(self):
        self.assertEqual(profile_for('test_visual', 'CapturedSceneTests',
                                    'test_result_page'), 'fixtures')
        self.assertEqual(profile_for('test_atlas_runtime', 'ArchivedExecutionMotionTests',
                                    'test_sparse_real_drag_retries_existing_frames_and_keeps_quality_gates'),
                         'fixtures')
        self.assertEqual(profile_for('test_atlas_runtime', 'RuntimeMotionTests',
                                    'test_material_motion'), 'production')

    def test_experimental_estimator_is_not_production_validation(self):
        self.assertEqual(profile_for('test_registration_precision_methods',
                                    'RegistrationMethodTests', 'test_ecc'), 'diagnostics')

    def test_available_visual_case_is_not_blocked_by_an_unrelated_missing_capture(self):
        discover_tests()  # Make the existing studio import root available.
        import test_visual
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / 'sessions/20260917-102739/start.png'
            path.parent.mkdir(parents=True)
            path.touch()  # Availability only; no synthetic image is game evidence.
            with patch.object(test_visual, 'FIXTURE_ROOT', root):
                case = test_visual.CapturedSceneTests('test_white_marker')
                case.setUp()
                self.assertEqual(test_visual.fixture_path('sessions/20260917-102739/start.png'), path)
                with self.assertRaises(unittest.SkipTest):
                    test_visual.CapturedSceneTests('test_repeated_narrow_hex_glyphs').setUp()

    def test_every_discovered_case_has_exactly_one_profile_and_all_keeps_it(self):
        cases = discover_tests()
        ids = {case.id() for case in cases}
        self.assertEqual(len(ids), len(cases), 'Duplicate discovery must not inflate counts')
        partitions = [select_tests(cases, name) for name in
                      ('production', 'diagnostics', 'legacy', 'fixtures')]
        combined = [case.id() for group in partitions for case in group]
        self.assertEqual(len(combined), len(set(combined)))
        self.assertEqual(set(combined), ids)
        self.assertEqual({case.id() for case in select_tests(cases, 'all')}, ids)
        self.assertTrue(all(partitions), 'An empty group may indicate a broken selector')


if __name__ == '__main__':
    unittest.main()
