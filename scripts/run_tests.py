"""Run a bounded regression profile without changing production search budgets."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / 'work' / 'studio'
PROFILES = ('quick', 'release', 'research', 'full')

# Stable current contracts: settings/UI, native IO, DPI geometry and safe return.
QUICK_MODULES = frozenset('''
test_app_data test_build_info test_core test_dpi_layout test_display_geometry
test_hotkeys test_input_gestures test_window_target test_platform_dpi
test_runtime_i18n_coverage test_ui_i18n test_ui_performance
test_native_ui_completion test_native_ui_hit_testing test_responsive_geometry
test_overlay_native test_runner_strategy test_native_live_layout
test_native_live_presentation test_native_live_ui test_native_live_runner
test_native_live_service test_native_live_timer_policy test_native_live_session_budget
test_native_protected_io test_native_refinement_controller test_native_mapped_preflight
test_native_preflight_target
test_native_dpi_input test_native_dpi_controller test_native_high_dpi_window
test_native_window_mapping test_native_cursor_diagnostic_integration
test_native_mouse_diagnostic test_native_portable_backend test_native_portable_diagnostics
test_native_scaled_board_mapping test_native_screen_hwnd test_native_unity_module_path
test_native_variable_layout test_native_input_response test_native_input_compile
test_native_route_continuation test_code_read_cache test_ocr_setup
test_vision_stage_deadline test_native_probe_card_cache test_native_probe_glyph_first
test_native_runtime_bridge test_native_runtime_discovery test_native_runtime_geometry
test_native_runtime_observation test_native_runtime_adapter
test_native_periodic_scale_compile
'''.split())

# Add a current feature here once its tests have been reviewed for this profile.
# Unclassified new test modules are also included automatically, so additions
# such as preset/priority/resize regressions cannot silently disappear.
EXTRA_CURRENT_MODULES = frozenset(('test_profile_store', 'test_profile_ui',
                                   'test_region_priority', 'test_priority_search_paths',
                                   'test_native_frame_budget_recovery'))

# These are retained, runnable historical/search-matrix suites. They are not
# deleted or disabled in unittest discovery; quick intentionally does not repeat
# every recorded global search and every legacy image-atlas route on each edit.
RESEARCH_MODULES = frozenset('''
test_analyze_quality_gate test_app_atlas test_atlas_adapter test_atlas_bound_route
test_atlas_budget_review test_atlas_capture_worker test_atlas_checkpoint_recovery
test_atlas_compromise_recovery test_atlas_end_to_end test_atlas_execution
test_atlas_feedback_adaptive test_atlas_live_adapter test_atlas_mask_route_review
test_atlas_masks test_atlas_pose_scoring test_atlas_registration test_atlas_replan
test_atlas_resampling test_atlas_runner test_atlas_runtime test_atlas_service
test_atlas_similarity_execution test_atlas_similarity test_atlas_snapshot
test_atlas_stage_budget test_atlas_trial test_best_result test_candidate_diversity
test_candidate_ranking test_capture_color_check test_color_family
test_entry_picker test_execution_diagnostics test_execution_return_guard test_exploration
test_gesture_evidence test_gesture_replay test_gesture_response_probe
test_hex_feedback_search test_hex_refinement test_input_response test_large_motion_review
test_live_atlas_capture test_marker_geometry test_micro_registration_review
test_micro_return_adapter test_micro_return_probe test_native_action_refine
test_native_action_search test_native_input_assessment test_native_input_diversity
test_native_input_pipeline_policy test_native_input_pipeline test_native_input_pivot_refine
test_native_input_route_search test_native_live_compromise test_native_live_controller
test_native_live_package test_native_live_recovery test_native_live_refinement
test_native_palette_actions test_native_palette_model test_native_palette_pose
test_native_palette_provider test_native_palette_refine test_native_palette_scoring
test_native_palette_search test_native_periodic_black test_native_periodic_route
test_native_periodic_search test_native_picker_coordinates test_native_refinement_rc12
test_native_refinement_recorded test_native_refinement_status test_native_search_pipeline
test_native_target_pipeline test_native_target_seeds test_native_transform_matrix
test_native_triple_black test_ocr_transport test_periodic_atlas test_planner
test_point_sampling_probe test_product test_registration_precision_methods
test_registration_uncertainty_audit test_rotation_comparison test_rotation_probe_review
test_scan_route_review test_scan_settling_review test_scan_settling test_screen_mapping
test_search_overlay_atlas test_session_store test_single_region_search
test_single_region_zoom_bands test_single_region_zoom test_startup_performance
test_translation_ranking_subset test_visual test_wheel_micro_model test_workflow_budget
test_zoom_detent_replan test_zoom_matrix_calibration
'''.split())

QUICK_TEST_IDS = (
    'test_native_live_controller.NativeControllerTests.test_early_missing_and_119_to13_readings_do_not_block_planning',
    'test_native_live_controller.NativeControllerTests.test_native_filled_ocr_omissions_cannot_certify_a_precise_target',
    'test_native_live_controller.NativeControllerTests.test_startup_grace_does_not_hide_session_failures',
    'test_native_live_controller.NativeControllerTests.test_startup_timeout_never_extends_engineering_limit',
    'test_native_live_controller.NativeControllerTests.test_bad_visual_and_low_time_send_no_input',
    'test_native_live_controller.NativeControllerTests.test_cancellation_and_action_limit_are_not_bypassed',
    'test_native_live_recovery.RecoveryTests.test_unknown_input_completion_never_retries_input',
    'test_native_live_compromise.NativeCompromiseTests.test_quality_uses_actual_delta_e_and_balances_all_enabled_regions',
    'test_native_live_compromise.NativeCompromiseTests.test_neighborhood_risk_breaks_an_equal_center_quality_tie',
    'test_native_live_compromise.NativeCompromiseTests.test_center_average_precedes_uncalibrated_neighborhood_risk',
    'test_native_live_compromise.NativeCompromiseTests.test_expired_compromise_never_sends_input',
)

QUICK_EXCLUDED_TEST_IDS = frozenset((
    'test_native_periodic_scale_compile.PeriodicScaleCompileTests.test_recorded_three_white_similar_targets_remain_reachable_in_bounded_plan',
    'test_native_periodic_scale_compile.PeriodicScaleCompileTests.test_recorded_similarity_route_finishes_with_measured_action_allowance',
))

# Release includes independent recorded double/triple targets, a complete
# protected improvement/return, exact/compromise reporting, and the legacy path.
RELEASE_TEST_IDS = (
    'test_native_periodic_black.PeriodicBlackTests.test_rc8_failed_session_reaches_double_black_with_the_production_entry',
    'test_native_live_refinement.RecordedRc12RefinementTests.test_triple_exact_basin_is_found_with_finer_angle_and_pivot_routes',
    'test_native_live_refinement.RecordedRc11RefinementTests.test_saved_rc11_improves_with_two_rotations_and_no_wheel_inverse_assumption',
    'test_native_refinement_recorded.RecordedRefinementTests.test_actual_perturbed_trial_recovers_from_actual_pose_with_real_solver',
    'test_native_live_recovery.RecoveryTests.test_large_model_error_rebases_instead_of_stopping_an_authorized_route',
    'test_native_live_recovery.ServiceIntegrationTests.test_exact_route_reaches_real_runner_event_and_saved_result',
    'test_native_live_recovery.ServiceIntegrationTests.test_two_enabled_regions_compromise_reaches_real_runner_event',
    'test_native_live_controller.NativeControllerTests.test_verified_exact_suffix_finishes_without_switching_global_target',
    'test_native_live_controller.NativeControllerTests.test_user_tolerance_and_disabled_regions_are_preserved',
    'test_atlas_end_to_end.AtlasEndToEndTests.test_runner_to_service_default_path',
    'test_atlas_end_to_end.AtlasEndToEndTests.test_runner_converts_unexpected_atlas_fault_to_recovery_state',
    *QUICK_EXCLUDED_TEST_IDS,
)

DESKTOP_TEST_PREFIXES = (
    'test_two_region_ui.',
    'test_resize_surface.',
    'test_profile_ui.',
    'test_native_ui_hit_testing.',
    'test_responsive_geometry.ResponsiveGeometryTests.',
    'test_overlay_native.NativeOverlayWorkerTests.',
)

QUICK_DESKTOP_TEST_IDS = frozenset((
    'test_resize_surface.ResizeSurfaceTests.test_sizing_surface_restores_live_controls_at_latest_width',
    'test_profile_ui.ProfileUITests.test_current_settings_autosave_including_incomplete_input',
    'test_native_ui_hit_testing.NativeUIHitTestingTests.test_native_finished_releases_main_hit_regions_and_next_run_reopens_overlay',
))


def flatten(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from flatten(test)
        else:
            yield test


def discover_tests():
    for path in (STUDIO, ROOT / 'scripts'):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    loader = unittest.TestLoader()
    suites = [loader.discover(str(STUDIO), pattern='test_*.py')]
    suites.append(loader.loadTestsFromName('test_run_tests'))
    return list(flatten(unittest.TestSuite(suites)))


def select_tests(tests, profile, *, no_desktop=False):
    if profile not in PROFILES:
        raise ValueError(f'Unknown test profile: {profile}')
    selected = []
    seen = set()
    desktop_omitted = []
    quick_ids = set(QUICK_TEST_IDS)
    release_ids = set(RELEASE_TEST_IDS)
    quick_excluded = set(QUICK_EXCLUDED_TEST_IDS)
    new_modules = set()
    for test in tests:
        name = test.id()
        if name in seen:
            continue
        seen.add(name)
        module = name.split('.')[0]
        current = module in QUICK_MODULES or module in EXTRA_CURRENT_MODULES
        unclassified = (module not in QUICK_MODULES and module not in RESEARCH_MODULES
                        and module not in EXTRA_CURRENT_MODULES)
        if unclassified:
            new_modules.add(module)
        desktop = name.startswith(DESKTOP_TEST_PREFIXES)
        quick = ((current or unclassified or name in quick_ids) and name not in quick_excluded
                 and (not desktop or name in QUICK_DESKTOP_TEST_IDS))
        include = (profile == 'full' or (profile == 'quick' and quick)
                   or (profile == 'release' and (quick or name in release_ids or desktop))
                   or (profile == 'research' and not quick and not desktop))
        if not include:
            continue
        if no_desktop and name.startswith(DESKTOP_TEST_PREFIXES):
            desktop_omitted.append(name)
            continue
        selected.append(test)
    return selected, {
        'profile': profile,
        'selected_count': len(selected),
        'discovered_count': len(seen),
        'desktop_omitted_count': len(desktop_omitted),
        'desktop_omitted': desktop_omitted,
        'unclassified_current_modules': sorted(new_modules),
        'modules': sorted({test.id().split('.')[0] for test in selected}),
    }


class TimedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records = []
        self._status = {}
        self._started = {}

    def startTest(self, test):
        self._started[test.id()] = time.perf_counter()
        self._status[test.id()] = 'passed'
        super().startTest(test)

    def addFailure(self, test, err):
        self._status[test.id()] = 'failed'
        super().addFailure(test, err)

    def addError(self, test, err):
        self._status[test.id()] = 'error'
        super().addError(test, err)

    def addSkip(self, test, reason):
        case = getattr(test, 'test_case', test)
        if self._status.get(case.id()) not in ('failed', 'error'):
            self._status[case.id()] = 'skipped'
        super().addSkip(test, reason)

    def addExpectedFailure(self, test, err):
        self._status[test.id()] = 'expected_failure'
        super().addExpectedFailure(test, err)

    def addUnexpectedSuccess(self, test):
        self._status[test.id()] = 'unexpected_success'
        super().addUnexpectedSuccess(test)

    def addSubTest(self, test, subtest, err):
        if err is not None:
            self._status[test.id()] = ('failed' if issubclass(err[0], test.failureException) else 'error')
        super().addSubTest(test, subtest, err)

    def stopTest(self, test):
        self.records.append({
            'id': test.id(), 'status': self._status[test.id()],
            'seconds': round(time.perf_counter() - self._started[test.id()], 6),
        })
        super().stopTest(test)


def result_summary(result):
    statuses = [row['status'] for row in result.records]
    counts = {
        'run': result.testsRun, 'passed': statuses.count('passed'),
        'skipped': statuses.count('skipped'), 'failed': statuses.count('failed'),
        'errors': statuses.count('error'), 'expected_failures': statuses.count('expected_failure'),
        'unexpected_successes': statuses.count('unexpected_success'),
    }
    return {
        'counts': counts, 'skip_events': len(result.skipped),
        'success': result.wasSuccessful(), 'tests': result.records,
        'slowest': sorted(result.records, key=lambda row: row['seconds'], reverse=True)[:10],
        'failures': [{'id': test.id(), 'traceback': detail} for test, detail in result.failures],
        'errors': [{'id': test.id(), 'traceback': detail} for test, detail in result.errors],
        'skips': [{'id': test.id(), 'reason': reason} for test, reason in result.skipped],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', choices=PROFILES, default='quick')
    parser.add_argument('--list', action='store_true', help='List selected test IDs without running them')
    parser.add_argument('--json', type=Path, help='Write a complete selection/result/duration report')
    parser.add_argument('--no-desktop', action='store_true', help='Omit actual Tk/foreground/capture checks; not a release verdict')
    parser.add_argument('--verbose', action='store_true')
    args = parser.parse_args(argv)
    began = time.perf_counter()
    tests = discover_tests()
    known_ids = {test.id() for test in tests}
    missing = (set(QUICK_TEST_IDS) | set(RELEASE_TEST_IDS) | set(QUICK_DESKTOP_TEST_IDS)) - known_ids
    if missing:
        parser.error('Required profile contracts are missing: ' + ', '.join(sorted(missing)))
    selected, selection = select_tests(tests, args.suite, no_desktop=args.no_desktop)
    report = {
        'generated_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'offline regression; no game input or consumable item',
        'selection': selection, 'list_only': args.list,
        'release_complete': False,
    }
    print(f"Suite {args.suite}: {len(selected)} selected / {selection['discovered_count']} discovered"
          + (f"; {selection['desktop_omitted_count']} desktop checks omitted" if args.no_desktop else ''))
    if args.list:
        for test in selected:
            print(test.id())
        report['test_ids'] = [test.id() for test in selected]
        status = 0
    else:
        result = unittest.TextTestRunner(
            stream=sys.stdout, verbosity=2 if args.verbose else 1, resultclass=TimedResult,
        ).run(unittest.TestSuite(selected))
        report.update(result_summary(result))
        report['release_complete'] = (args.suite == 'release' and not args.no_desktop
                                      and result.wasSuccessful())
        counts = report['counts']
        print(f"Passed {counts['passed']}; skipped {counts['skipped']}; failed {counts['failed']}; "
              f"errors {counts['errors']}; expected failures {counts['expected_failures']}; "
              f"unexpected successes {counts['unexpected_successes']}")
        if report['skip_events'] != counts['skipped']:
            print(f"Skip events: {report['skip_events']} (includes individual subtests)")
        print('Slowest checks:')
        for row in report['slowest']:
            print(f"  {row['seconds']:7.3f}s  {row['id']}")
        status = 0 if result.wasSuccessful() else 1
    report['elapsed_seconds'] = round(time.perf_counter() - began, 6)
    print(f"Total elapsed: {report['elapsed_seconds']:.3f}s")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'Report: {args.json.resolve()}')
    return status


if __name__ == '__main__':
    raise SystemExit(main())
