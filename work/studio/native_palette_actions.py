"""Assess predicted input endpoints offline; never send input or verify HEX."""
import math
import numpy as np
from atlas_pose import pose_fields
from atlas_execution import reposition_budget
from native_palette_pose import relative_board_pose, score_board_pose
from native_palette_scoring import score_native_pose


def assess_native_action(session, target, reference, board, markers, rules, *,
                         now, deadline, check=lambda: None):
    """Compile the existing action model and separately rescore its endpoint.

    ``reference`` must describe the current texture pose in the same session.
    This offline helper cannot establish its freshness. Eligibility means
    suitable for subsequent live validation, never authorization to execute.
    """
    if not all(math.isfinite(v) for v in (now, deadline)):
        raise ValueError('Finite timing values required')
    points = np.asarray(markers, dtype=float)
    if points.shape != (3, 2) or not np.isfinite(points).all():
        raise ValueError('Three finite screen marker positions required')
    check()
    proposal = score_native_pose(session, target, rules, check=check)
    relative = relative_board_pose(target, reference, board)
    candidate = pose_fields(relative, board)
    check()
    budget = reposition_budget(candidate, now, deadline, board, markers=points)
    check()
    planned = None
    if budget.get('planned_pose') is not None:
        planned = score_board_pose(session, budget['planned_pose'], reference, board, rules, check=check)
    plan_allowed = bool(budget.get('allowed', False))
    predicted_ok = bool(planned and planned['predicted_accepted'])
    return dict(proposal_prediction=proposal, planned_prediction=planned,
                budget=budget, relative_candidate=candidate, plan_allowed=plan_allowed,
                planned_predicted_accepted=predicted_ok,
                eligible_for_live_validation=plan_allowed and predicted_ok,
                execution_verified=False, game_response_verified=False,
                capture_id=session['capture_id'],
                reference_freshness='caller_must_validate_same_session_current_pose')
