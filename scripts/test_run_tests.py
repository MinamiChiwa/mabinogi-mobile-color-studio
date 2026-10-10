"""Contracts for the regression profile selector and machine-readable result."""
import importlib.util
import io
from pathlib import Path
import unittest


class RegressionEntryTests(unittest.TestCase):
    def module(self):
        path = Path(__file__).with_name('run_tests.py')
        self.assertTrue(path.is_file(), 'The profiled test entry point is missing')
        spec = importlib.util.spec_from_file_location('profile_runner_contract', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    @staticmethod
    def case(name):
        class NamedTest(unittest.TestCase):
            def runTest(self):
                pass
            def id(self):
                return name
        return NamedTest()

    def fixtures(self):
        m = self.module()
        ids = [
            'test_core.CoreTests.test_rule',
            'test_new_presets.PresetTests.test_round_trip',
            'test_atlas_execution.ExecutionTests.test_old_route',
            m.RELEASE_TEST_IDS[0],
            'test_native_ui_hit_testing.NativeUIHitTestingTests.test_native_finished_releases_main_hit_regions_and_next_run_reopens_overlay',
        ]
        return m, [self.case(name) for name in ids]

    def test_quick_keeps_current_core_and_new_modules(self):
        m, cases = self.fixtures()
        selected, _ = m.select_tests(cases, 'quick')
        ids = {test.id() for test in selected}
        self.assertIn(cases[0].id(), ids)
        self.assertIn(cases[1].id(), ids)
        self.assertNotIn(cases[2].id(), ids)

    def test_release_adds_explicit_recorded_or_legacy_contracts(self):
        m, cases = self.fixtures()
        quick, _ = m.select_tests(cases, 'quick')
        release, _ = m.select_tests(cases, 'release')
        self.assertLess(len(quick), len(release))
        self.assertIn(m.RELEASE_TEST_IDS[0], {test.id() for test in release})

    def test_release_and_research_cover_full_without_losing_cases(self):
        m, cases = self.fixtures()
        release, _ = m.select_tests(cases, 'release')
        research, _ = m.select_tests(cases, 'research')
        full, _ = m.select_tests(cases, 'full')
        q = {test.id() for test in release}
        r = {test.id() for test in research}
        self.assertEqual(q | r, {test.id() for test in full})

    def test_quick_runs_three_desktop_smokes_while_release_retains_matrix(self):
        m = self.module()
        selected_ids = (
            'test_resize_surface.ResizeSurfaceTests.test_sizing_surface_restores_live_controls_at_latest_width',
            'test_profile_ui.ProfileUITests.test_current_settings_autosave_including_incomplete_input',
            'test_native_ui_hit_testing.NativeUIHitTestingTests.test_native_finished_releases_main_hit_regions_and_next_run_reopens_overlay',
        )
        matrix_ids = (
            'test_resize_surface.ResizeSurfaceTests.test_capture_failure_retains_normal_layout',
            'test_profile_ui.ProfileUITests.test_language_switch_updates_existing_preset_placeholder',
            'test_overlay_native.NativeOverlayWorkerTests.test_worker_capture_and_ui_policy_refresh_complete_without_focus_change',
            'test_responsive_geometry.ResponsiveGeometryTests.test_one_two_and_three_column_layouts_keep_standard_card_width',
        )
        pure = 'test_resize_surface_faults.ResizeSurfaceFaultTests.test_overlay_mount_failure_restores_hidden_live_page'
        cases = [self.case(name) for name in (*selected_ids, *matrix_ids, pure)]
        quick, _ = m.select_tests(cases, 'quick')
        release, _ = m.select_tests(cases, 'release')
        research, _ = m.select_tests(cases, 'research')
        self.assertEqual({test.id() for test in quick}, {*selected_ids, pure})
        self.assertEqual({test.id() for test in release}, set(selected_ids + matrix_ids + (pure,)))
        self.assertFalse(set(matrix_ids) & {test.id() for test in research})

    def test_unknown_profile_fails_instead_of_running_a_different_suite(self):
        m, cases = self.fixtures()
        with self.assertRaisesRegex(ValueError, 'Unknown'):
            m.select_tests(cases, 'relase')

    def test_duplicate_names_are_run_once(self):
        m, cases = self.fixtures()
        selected, _ = m.select_tests(cases + [cases[0]], 'full')
        self.assertEqual(len(selected), len(cases))

    def test_expensive_scale_sessions_are_release_only_while_scale_contracts_stay_quick(self):
        m = self.module()
        prefix = 'test_native_periodic_scale_compile.PeriodicScaleCompileTests.'
        ids = [prefix + suffix for suffix in (
            'test_sub_notch_scale_has_complete_replayed_route',
            'test_fine_scale_at_game_upper_limit_uses_unclipped_order',
            'test_recorded_three_white_similar_targets_remain_reachable_in_bounded_plan',
            'test_recorded_similarity_route_finishes_with_measured_action_allowance',
        )]
        cases = [self.case(name) for name in ids]
        quick, _ = m.select_tests(cases, 'quick')
        release, _ = m.select_tests(cases, 'release')
        research, _ = m.select_tests(cases, 'research')
        full, _ = m.select_tests(cases, 'full')
        self.assertEqual([test.id() for test in quick], ids[:2])
        self.assertEqual([test.id() for test in release], ids)
        self.assertEqual([test.id() for test in research], ids[2:])
        self.assertEqual([test.id() for test in full], ids)

    def test_no_desktop_excludes_real_ui_but_keeps_core(self):
        m, cases = self.fixtures()
        selected, info = m.select_tests(cases, 'quick', no_desktop=True)
        self.assertIn(cases[0].id(), {test.id() for test in selected})
        self.assertNotIn(cases[-1].id(), {test.id() for test in selected})
        self.assertEqual(info['desktop_omitted_count'], 1)

    def test_result_separates_pass_skip_failure_and_records_duration(self):
        m = self.module()
        class Examples(unittest.TestCase):
            def test_pass(self):
                pass
            def test_skip(self):
                self.skipTest('optional fixture')
            def test_fail(self):
                self.fail('controlled runner contract failure')
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(Examples)
        result = m.TimedResult(io.StringIO(), descriptions=False, verbosity=0)
        suite.run(result)
        summary = m.result_summary(result)
        self.assertEqual(summary['counts'], {
            'run': 3, 'passed': 1, 'skipped': 1, 'failed': 1,
            'errors': 0, 'expected_failures': 0, 'unexpected_successes': 0,
        })
        self.assertFalse(summary['success'])
        self.assertEqual(len(summary['tests']), 3)
        self.assertTrue(all(row['seconds'] >= 0 for row in summary['tests']))

    def test_failed_subtests_count_as_one_failed_case(self):
        m = self.module()
        class Examples(unittest.TestCase):
            def test_many(self):
                for number in range(2):
                    with self.subTest(number=number):
                        self.fail('controlled subtest failure')
        result = m.TimedResult(io.StringIO(), descriptions=False, verbosity=0)
        unittest.defaultTestLoader.loadTestsFromTestCase(Examples).run(result)
        counts = m.result_summary(result)['counts']
        self.assertEqual(counts['run'], 1)
        self.assertEqual(counts['failed'], 1)
        self.assertEqual(counts['passed'], 0)

    def test_missing_fixture_subtests_do_not_count_as_fully_passed_case(self):
        m = self.module()
        class Examples(unittest.TestCase):
            def test_many(self):
                for number in range(2):
                    with self.subTest(number=number):
                        self.skipTest('missing recorded fixture')
        result = m.TimedResult(io.StringIO(), descriptions=False, verbosity=0)
        unittest.defaultTestLoader.loadTestsFromTestCase(Examples).run(result)
        summary = m.result_summary(result)
        self.assertEqual(summary['counts']['run'], 1)
        self.assertEqual(summary['counts']['skipped'], 1)
        self.assertEqual(summary['counts']['passed'], 0)
        self.assertEqual(summary['skip_events'], 2)


if __name__ == '__main__':
    unittest.main()
