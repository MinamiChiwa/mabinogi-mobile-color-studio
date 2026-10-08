"""Run offline tests by purpose; no game input is sent by this entry point."""
import argparse
from collections import Counter
from pathlib import Path
import os
import sys
import unittest

ROOT = Path(__file__).resolve().parent
PROFILES = ('production', 'diagnostics', 'legacy', 'fixtures', 'all')

# These suites cover opt-in experiment/report tools, not normal dye searching.
# Input-safety tests in live_atlas_capture remain in production even when they
# exercise diagnostic entry points. New, unclassified tests default to production.
DIAGNOSTIC_MODULES = frozenset({
    'test_atlas_budget_review', 'test_capture_color_check',
    'test_gesture_evidence', 'test_gesture_replay', 'test_gesture_response_probe',
    'test_large_motion_review', 'test_mechanism_experiment',
    'test_micro_registration_review', 'test_micro_return_adapter',
    'test_micro_return_probe', 'test_point_sampling_probe',
    'test_registration_precision_methods', 'test_registration_uncertainty_audit',
    'test_rotation_comparison', 'test_rotation_probe_review',
    'test_scan_route_review', 'test_scan_settling_review',
})
LEGACY_MODULES = frozenset({'test_best_result', 'test_entry_picker', 'test_input_response'})
LEGACY_METHODS = {
    'test_exploration': frozenset({
        'test_hex_local_refinement_stops_only_after_all_regions_pass',
        'test_failed_local_trial_exits_without_spending_time_on_undo',
        'test_local_refinement_covers_neighborhood_without_zero_moves',
        'test_apply_waits_for_result_animation', 'test_apply_never_clicks_if_result_changes',
        'test_missing_candidate_causes_multiple_real_drag_calls',
        'test_accepted_similarity_keeps_exploring_instead_of_finishing',
        'test_distant_candidate_triggers_exploration',
        'test_exploration_keeps_rotation_and_zoom_available',
    }),
    'test_product': frozenset({
        'test_wait_accepts_delayed_board_only_after_timer_appears',
        'test_wait_timeout_is_explicit_and_sends_no_input',
        'test_wait_survives_hidden_window_and_ocr_timeout',
        'test_wait_can_be_cancelled_with_stop_event',
        'test_unlimited_wait_survives_more_than_sixty_seconds',
        'test_search_bypasses_focus_capture_and_result_page_before_waiting',
        'test_multi_zoom_stays_close_to_entry_and_best',
        'test_multi_search_does_not_repeat_unresponsive_joint_zoom',
        'test_local_improvement_resets_failures_but_noise_does_not',
        'test_failed_island_memory_moves_with_texture',
        'test_timer_digit_loss_does_not_trigger_early_fallback',
        'test_exact_visible_target_is_moved_before_magnification',
        'test_zoom_limit_exits_after_three_failed_attempts',
        'test_zoom_tracks_original_island_before_reset_and_wide_search',
        'test_exact_magnification_uses_source_island_not_marker',
    }),
    'test_core': frozenset({
        'test_joint_translation_respects_independent_thirds',
        'test_white_target_is_not_filtered_as_ui',
        'test_single_pixel_target_on_large_board_far_from_marker',
    }),
    'test_planner': frozenset({
        'test_recovers_shared_rotation_scale_and_translation',
        'test_two_matching_regions_do_not_hide_bad_third',
    }),
}
FIXTURE_CLASSES = frozenset({
    ('test_atlas_runtime', 'ArchivedExecutionMotionTests'),
    ('test_atlas_trial', 'TrialCaptureTests'),
})
FIXTURE_METHODS = {
    'test_atlas_registration': frozenset({
        'test_newest_saved_sparse_pair_recovers_without_lowering_match_threshold'}),
    'test_ocr_setup': frozenset({'test_archived_heldout_hex_including_four_previous_misses'}),
    'test_planner': frozenset({'test_real_three_region_candidate_between_coarse_angles'}),
}


def profile_for(module, class_name, method):
    module = module.rsplit('.', 1)[-1]
    if (module == 'test_visual' or (module, class_name) in FIXTURE_CLASSES or
            method in FIXTURE_METHODS.get(module, ())):
        return 'fixtures'
    if module in DIAGNOSTIC_MODULES:
        return 'diagnostics'
    if module == 'test_best_result' and method == 'test_eyedropper_uses_frozen_pixel_and_clamps_edges':
        return 'production'
    if module in LEGACY_MODULES or method in LEGACY_METHODS.get(module, ()):
        return 'legacy'
    return 'production'


def flatten(suite):
    for case in suite:
        if isinstance(case, unittest.TestSuite):
            yield from flatten(case)
        else:
            yield case


def discover_tests():
    # Use distinct loaders: unittest caches its top-level directory, while
    # these two existing layouts intentionally have independent import roots.
    for path in (ROOT, ROOT / 'work/studio'):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    return [case for folder in ('work/studio', 'tests')
            for case in flatten(unittest.TestLoader().discover(str(ROOT / folder), 'test_*.py'))]


def case_profile(case):
    module, class_name, method = case.id().rsplit('.', 2)
    return profile_for(module, class_name, method)


def select_tests(cases, profile):
    if profile not in PROFILES:
        raise ValueError('Unknown test profile: ' + profile)
    return [case for case in cases if profile == 'all' or case_profile(case) == profile]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=PROFILES, default='production')
    parser.add_argument('--list', action='store_true', help='List selected test IDs without running them')
    args = parser.parse_args(argv)
    os.chdir(ROOT)  # Existing fixture paths are relative to the repository.
    cases = discover_tests()
    counts = Counter(case_profile(case) for case in cases)
    selected = select_tests(cases, args.profile)
    print('Discovered: ' + ', '.join(f'{name}={counts[name]}' for name in PROFILES[:-1]), flush=True)
    print(f'Profile: {args.profile}; selected={len(selected)}; excluded={len(cases)-len(selected)}', flush=True)
    if not selected:
        parser.error('No tests selected')
    if args.list:
        for case in selected:
            print(case.id())
        return 0
    result = unittest.TextTestRunner(verbosity=1).run(unittest.TestSuite(selected))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
