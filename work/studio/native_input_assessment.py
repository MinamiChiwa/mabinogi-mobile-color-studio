"""Rescore existing offline input routes with conditional native event replay."""
from native_input_response import replay_native_route
from native_palette_scoring import score_native_pose
import time


def assess_native_input_route(session, budget, reference, geometry, settings, rules, *,
                              sample_policy, sample_indices=None,
                              wheel_delta_per_step=None, check=lambda: None):
    """Keep timing eligibility separate from predicted event-endpoint colors.

    Caller validates reference belongs to the saved session. No timing budget
    is recalculated here and no execution/settled-pose guarantee is supplied.
    Missing routes fail closed rather than becoming a false identity result.
    """
    check()
    if 'input_route' not in budget:
        raise ValueError('An explicit compiled input route is required')
    replay = replay_native_route(reference, budget['input_route'], geometry, settings,
                sample_policy=sample_policy, sample_indices=sample_indices,
                wheel_delta_per_step=wheel_delta_per_step, check=check)
    prediction = score_native_pose(session, replay['final_pose'], rules, check=check)
    prediction['prediction_pose_source'] = 'conditional_native_input_event_replay'
    check()
    return dict(input_prediction=prediction, replay=replay,
                plan_allowed=bool(budget.get('allowed', False)),
                input_predicted_accepted=bool(prediction['predicted_accepted']),
                execution_verified=False, game_response_verified=False,
                capture_id=session['capture_id'],
                reference_freshness='caller_must_validate_same_session_current_pose')


def assess_native_compiled_action(session, target, reference, geometry, settings, rules, *,
                                  wheel_delta_per_step, sample_policy, now, deadline,
                                  clock=time.monotonic, check=lambda: None, **compile_options):
    """Opt-in offline stepwise compilation, replay and CPU endpoint scoring.

    Geometry tolerance and exact color acceptance are separate. Rejected
    routes are retained for diagnosis only. No live consumer is connected.
    Caller must validate the supplied reference/session/geometry binding.
    """
    from native_input_compile import compile_native_route
    check()
    started = clock()
    l, t, r, b = geometry.board
    markers = [[l+uv[0]*(r-l), b-uv[1]*(b-t)] for uv in session['picker_uv']]
    budget = compile_native_route(target, reference, geometry, settings, markers,
                wheel_delta_per_step=wheel_delta_per_step, sample_policy=sample_policy,
                now=now, deadline=deadline, clock=clock, check=check, **compile_options)
    result = assess_native_input_route(session, budget, reference, geometry, settings, rules,
                sample_policy=sample_policy, wheel_delta_per_step=wheel_delta_per_step, check=check)
    elapsed = max(0., clock()-started)
    budget['assessment_elapsed_seconds'] = elapsed
    budget['remaining'] = max(0., deadline-now-elapsed)
    if budget['allowed'] and budget['remaining'] < budget['needed']:
        budget['allowed'] = False
        budget['reason'] = 'insufficient_time'
    result['plan_allowed'] = budget['allowed']
    result['budget'] = budget
    check()
    return result
