"""Dependency-injected atlas pipeline used by the formal Runner seam.

Platform callbacks own screenshots and input.  This module owns lifecycle
events and refuses to publish candidates until the builder reports a passed
quality gate.
"""
from dataclasses import dataclass
from copy import deepcopy
import math
import time
import uuid
from atlas_execution import reposition_budget
from workflow_budget import earliest_deadline
from candidate_ranking import candidate_rank,progressive_candidate_rank,candidate_quality
from atlas_pose import relative_candidate, candidate_pose, homogeneous, pose_fields


@dataclass
class AtlasCallbacks:
    acquire: object
    build: object
    default: object
    choice: object
    select: object=None
    prepare: object=None
    observe_current: object=None
    # Optional experimental path: a callback may collect a few anchors,
    # generate joint candidates, and perform local refinement.  It is never
    # called unless ``progressive_search`` is explicitly enabled in context
    # (or the builder marks the report as progressive).
    progressive: object=None


def quality_failure_message(gate):
    failed=[r for r in gate.get('regions',[]) if r.get('required',True) and not r.get('passed')]
    details=[]
    thresholds=gate.get('thresholds',{})
    for row in failed:
        details.append('区域 %s 留出 RGB RMSE %.2f（上限 %.2f）' %
                       (row['region'],row.get('heldout_rgb_rmse',float('inf')),
                        thresholds.get('max_rgb_rmse',8.)))
    suffix='：'+'；'.join(details) if details else ''
    return ('大图重建校验未通过'+suffix+'。尚未搜索目标组合，不能据此判断没有满足目标的方案。')


def _is_safety_interrupt(exc):
    """Keep explicit user/window safety stops on the interrupt path."""
    return exc.__class__.__name__ in ('Interrupted','InterruptedError')


def _measured_quality(result):
    """Incomplete observations cannot justify leaving a measured result."""
    if not result.get('verified'):return None
    try:quality=candidate_quality(result)
    except (TypeError,ValueError):return None
    return quality if all(math.isfinite(value) for value in quality) else None


def _protected_route(row,budget):
    """Publication permits measured feedback; an optional trial needs more.

    Do not risk an existing HEX result on an uncalibrated transform, even if
    its nominal endpoint passed the ordinary candidate publication gate.
    """
    stability=row.get('route_stability',{})
    actions=budget.get('actions',{})
    transforms=actions.get('rotate',0) or actions.get('wheel',0)
    return (budget.get('allowed',False) and stability.get('passed',False) and
            stability.get('samples_complete',True) and
            (not transforms or stability.get('response_profile_verified',False)))


def _enabled_region_count(rules):
    """Return the number of enabled regions participating in this search."""
    try:
        return sum(1 for rule in rules if isinstance(rule,dict) and rule.get('enabled'))
    except TypeError:
        return 0


def _has_exact_region(rules):
    """Whether at least one enabled region uses byte-exact matching."""
    try:
        return any(isinstance(rule,dict) and rule.get('enabled') and rule.get('exact')
                   for rule in rules)
    except TypeError:
        return False


class AtlasService:
    def __init__(self, callbacks):
        self.callbacks=callbacks

    def _prepare_route(self,owner,report,target,source_pose,rules,context,*,user_selected=False):
        if not callable(self.callbacks.prepare):return None
        move=relative_candidate(target,source_pose,report['board'])
        row,budget=self.callbacks.prepare(owner,report,move,rules,
            **dict({k:v for k,v in context.items() if k!='return_guard'},reference_pose=source_pose))
        stability=row.get('route_stability',{}) if row is not None else {}
        eligible=(budget.get('allowed',False) and stability.get('passed',False) and
                  stability.get('samples_complete',True))
        if row is None or not (eligible if user_selected else _protected_route(row,budget)):
            owner.event('atlas_trial_route_unavailable',candidate_id=target['id'],
                budget={k:v for k,v in budget.items() if k!='input_route'},
                route_stability=row.get('route_stability') if row is not None else None)
            return None
        # Rebinding may correct the same endpoint, but cannot replace it with
        # a new search result while an observed checkpoint is at risk.
        return dict(row,protect_observed_result=True,
                    **({'user_selected_route':True} if user_selected else {})),budget

    def _observe_early_exit(self, owner, captured, rules, context, reason):
        """Read the unchanged board after a non-safety search early exit.

        This callback is deliberately read-only and optional.  It must never
        turn a failed atlas build into a claimed candidate or best result; a
        successful double-read is reported as the current observation only.
        """
        callback=getattr(self.callbacks,'observe_current',None)
        if not callable(callback):return None
        try:
            observed=callback(owner,captured,rules,reason=reason,**context)
        except Exception as exc:
            if _is_safety_interrupt(exc):raise
            owner.event('atlas_recovery_unavailable',
                        message='当前动作未能可靠复核，已停止自动移动并保留游戏当前画面。',
                        detail=str(exc),reason=reason)
            return None
        if not isinstance(observed,dict):return None
        observed=dict(observed,early_exit=True,recovery_reason=reason,
                      candidate_id=None,actual_pose=None,pose_reliable=False,
                      accepted=False,recovered=True,best_result_current=False,positioning_complete=False)
        owner.event('atlas_recovery',**observed)
        return observed

    def _prepare_protected(self,owner,report,target,source_pose,rules,context):
        return self._prepare_route(owner,report,target,source_pose,rules,context)

    def _return_guard(self,owner,report,target,rules,context):
        """Reserve a freshly bound return from the latest global observation.

        The return budget already includes final HEX verification and safety
        time. The executor adds only its upcoming input and observation cost.
        The callback belongs in execution context, never candidate diagnostics.
        """
        context={k:v for k,v in context.items() if k!='return_guard'}
        deadline=context.get('selection_deadline')
        def guard(actual_pose,upcoming_seconds=0.,projected_pose=None):
            details=dict(allowed=False,reason='return_route_unavailable',needed=None,
                         remaining=None,return_needed=None,upcoming_seconds=upcoming_seconds,
                         checkpoint_candidate_id=target['id'])
            try:
                upcoming=float(upcoming_seconds)
                if not math.isfinite(upcoming) or upcoming<0:raise ValueError('Invalid action duration')
                measured=homogeneous(actual_pose)
                if not all(math.isfinite(value) for value in measured.flat):
                    raise ValueError('Invalid measured pose')
                # Price the return from the predicted post-action pose when
                # available.  This prevents a rotation/zoom input from being
                # approved solely because the current pose is cheap to undo.
                return_pose = measured if projected_pose is None else homogeneous(projected_pose)
                returning=self._prepare_protected(owner,report,target,measured[:2].tolist(),rules,context)
                if projected_pose is not None:
                    projected=self._prepare_protected(owner,report,target,return_pose[:2].tolist(),rules,context)
                    if projected is None:
                        return dict(details,reason='projected_return_unavailable')
                    returning=projected
                if returning is None:
                    return dict(details,reason='return_route_unavailable')
                budget=returning[1]
                return_needed=float(budget['needed'])
                remaining=float(deadline)-time.monotonic()
                needed=return_needed+upcoming
                if not math.isfinite(needed) or needed<0:raise ValueError('Invalid return duration')
                allowed=remaining>needed
                return dict(details,allowed=allowed,
                    reason=None if allowed else 'insufficient_return_time',needed=needed,
                    remaining=remaining,return_needed=return_needed,upcoming_seconds=upcoming,
                    actions=budget.get('actions',{}))
            except Exception as exc:
                if _is_safety_interrupt(exc):raise
                return dict(details,detail=str(exc))
        return guard

    def _restore_observed(self,owner,report,current,best,target,rules,context):
        """Keep historical HEX distinct from the actual board after a trial."""
        result=current;attempted=False;detail=None
        reliable=((current.get('verified') or current.get('pose_reliable')) and current.get('actual_pose') is not None and
                  (not (current.get('recovered') or current.get('positioning_complete') is False)
                   or current.get('pose_reliable')))
        if reliable:
            try:
                prepared=self._prepare_protected(owner,report,target,current['actual_pose'],rules,context)
                if prepared is not None:
                    owner.event('atlas_status',message='正在恢复本轮已实测的最佳方案。')
                    attempted=True
                    restored=self.callbacks.choice(owner,report,prepared[0],rules,**context)
                    result=(restored if isinstance(restored,dict) else
                            dict(verified=False,actual_pose=None,candidate_id=best['candidate_id']))
                    quality=_measured_quality(result)
                    if (quality is not None and quality<=_measured_quality(best) and
                            result.get('actual_pose') is not None and not result.get('recovered') and
                            result.get('positioning_complete') is not False):
                        return dict(result,best_result_current=True,restored_best=True)
            except Exception as exc:
                if _is_safety_interrupt(exc):raise
                detail=str(exc)
                if attempted:
                    result=dict(verified=False,actual_pose=None,candidate_id=best['candidate_id'])
        result=dict(result,best_result=deepcopy(best),best_result_current=False,
                    restore_attempted=attempted,restore_detail=detail)
        owner.event('atlas_best_not_restored',**result)
        return result

    def run(self, owner, rules, **context):
        emit=owner.event
        emit('atlas_status',message='正在采集本局颜色板。')
        try:
            captured=self.callbacks.acquire(owner,rules,**context)
        except Exception as exc:
            if _is_safety_interrupt(exc):raise
            emit('atlas_recovery_unavailable',
                 message='颜色板采集未能完成，已停止自动移动并保留游戏当前画面。',
                 detail=str(exc))
            return None
        try:
            report=self.callbacks.build(captured,rules,**context)
        except Exception as exc:
            if _is_safety_interrupt(exc):raise
            emit('atlas_recovery_unavailable',
                 message='颜色板校验未能完成，已停止自动移动并保留游戏当前画面。',
                 detail=str(exc))
            return self._observe_early_exit(owner,captured,rules,context,'atlas_build_failed')
        gate=report.get('quality_gate',{})
        if not gate.get('passed',False):
            if report.get('alignment_error'):
                # Capture already stopped at the first bad frame.  Surface
                # that fact directly instead of presenting a generic atlas
                # quality failure while the UI appears frozen at N/48.
                emit('atlas_recovery_unavailable',
                     message='颜色板采集在第 %s 步对齐失败，已停止自动移动并读取当前游戏色码。' %
                             (report.get('alignment_frames') or '?'),
                     detail=str(report.get('alignment_error')),
                     reason='atlas_capture_alignment_failed')
                return self._observe_early_exit(owner,captured,rules,context,
                                                'atlas_capture_alignment_failed')
            emit('atlas_invalidated',reason='atlas_quality_failed',search_performed=False,
                 message=quality_failure_message(gate),quality_gate=gate)
            return self._observe_early_exit(owner,captured,rules,context,'atlas_quality_failed')
        batch=report.get('batch')
        deadline=earliest_deadline(context.get('selection_deadline'),report.get('selection_deadline'),
                                   batch.deadline if batch is not None else None)
        if deadline is not None and time.monotonic()>=deadline:
            if batch is not None:batch.invalidate()
            emit('atlas_invalidated',message='游戏倒计时已截止，未发布候选。')
            return None
        report['selection_deadline']=deadline
        context=dict(context,selection_deadline=deadline)
        if batch is not None and deadline is not None:batch.deadline=deadline
        emit('atlas_ready',quality_gate=gate)
        progressive = bool(context.get('progressive_search') or
                           report.get('search_mode') == 'progressive')
        # The staged path is deliberately opt-in.  A callback returns either
        # a candidate list or a report fragment containing ``candidates``;
        # malformed/failed staged searches fall back to the complete atlas
        # result and are surfaced as diagnostics, never as a hard failure.
        if progressive and callable(getattr(self.callbacks, 'progressive', None)):
            complete_candidates=list(report.get('candidates',[]))
            try:
                staged=self.callbacks.progressive(owner,captured,report,rules,**context)
                if isinstance(staged,dict):
                    report.update(staged)
                elif isinstance(staged,list):
                    report['candidates']=staged
                else:
                    raise ValueError('progressive callback returned no candidate report')
                if not report.get('candidates'):
                    # An empty anchor/refinement result is an unavailable
                    # staged search. Preserve the already-built full atlas so
                    # the explicit experiment switch cannot turn a recoverable
                    # search into a false no-candidate result.
                    report['candidates']=complete_candidates
                    raise ValueError('progressive callback returned no candidates')
                report['search_mode']='progressive'
            except Exception as exc:
                if _is_safety_interrupt(exc):raise
                report['candidates']=complete_candidates
                emit('atlas_progressive_unavailable',detail=str(exc),
                     message='渐进候选搜索未完成，回退完整颜色板候选。')
                progressive=False
        rank_fn=progressive_candidate_rank if progressive else candidate_rank
        rows=report.get('candidates',[])
        raw_rows=list(rows)
        raw_accepted=[row for row in raw_rows if row.get('accepted')]
        compromise_rows=[row for row in raw_rows if row not in raw_accepted]
        best_compromise=min(compromise_rows,key=rank_fn) if compromise_rows else None
        emit('atlas_search_summary',raw_count=len(raw_rows),
             family_consistent_count=sum(row.get('family_consistent',False) for row in raw_rows),
             predicted_accepted_count=len(raw_accepted),
             compromise_count=len(compromise_rows),
             best_compromise_max=best_compromise.get('maximum') if best_compromise else None,
             best_compromise_average=best_compromise.get('average') if best_compromise else None,
             search_diagnostics=report.get('search_diagnostics',{}))
        compromise_only=not bool(raw_accepted)
        # Exact mode is a preference for ranking and acceptance, not a reason
        # to abandon a usable round.  In particular, a multi-region exact
        # target may have no jointly exact sample even though the atlas has a
        # safe, measured near match.  Keep that candidate in the normal route
        # and verification pipeline so the player gets the closest measured
        # result instead of paying for a dye with no positioned result.  The
        # compromise_only flag below is carried through the candidate event,
        # result payload, and UI; no dye confirmation is sent automatically.
        compromise_fallback = compromise_only and _enabled_region_count(rules) >= 2
        strict_exact_fallback = _has_exact_region(rules)
        if compromise_fallback:
            search_diagnostics=report.get('search_diagnostics',{})
            family_count=sum(bool(row.get('family_consistent')) for row in raw_rows)
            emit('atlas_status',
                 message=('未找到所有启用区域共同精准命中，正在定位综合色差最小的妥协方案；不会自动确认染色。'
                          if strict_exact_fallback else
                          '未找到所有启用区域共同达标方案，正在定位综合色差最小的妥协方案；不会自动确认染色。'),
                 reason='no_joint_candidate',candidate_count=len(raw_rows),
                 family_consistent_count=family_count,
                 strict_exact=strict_exact_fallback,
                 exact_target_availability=search_diagnostics.get('exact_target_availability',{}))
        if not rows:
            diagnostics=report.get('search_diagnostics',{})
            stable_count=diagnostics.get('stable_route_count',0)
            message=('本轮没有在预测阶段确认稳定可达的方案，未发送自动移动。'
                     if diagnostics.get('stability_required') else
                     '本轮搜索没有可测量的落点；无法生成自动或妥协方案。')
            emit('atlas_invalidated',reason=('stable_route_unavailable' if diagnostics.get('stability_required')
                                             else 'bounded_search_no_match'),search_performed=True,message=message,
                 stable_route_count=stable_count,
                 search_diagnostics=report.get('search_diagnostics',{}))
            return self._observe_early_exit(owner,captured,rules,context,'no_executable_candidate')
        rows=sorted(rows,key=rank_fn)
        batch_id=report.get('batch_id') or (batch.id if batch is not None else uuid.uuid4().hex)
        board=report.get('board')
        markers=(batch.context.markers if batch is not None else report.get('markers'))
        available=[]
        for row in rows:
            try:
                budget=(reposition_budget(row,time.monotonic(),deadline,board,markers=markers)
                        if deadline is not None and board else {'allowed':False})
            except Exception as exc:
                emit('atlas_candidate_unavailable',candidate_id=row.get('id'),detail=str(exc))
                budget={'allowed':False,'reason':'invalid_candidate'}
            if budget['allowed']:available.append((row,budget))
        default,default_budget=available[0] if available else (rows[0],{'allowed':False})
        if not default_budget['allowed']:
            if batch is not None:batch.invalidate()
            emit('atlas_default_unavailable',message='剩余时间不足以安全定位并复核自动最佳方案，未发送定位操作。',budget=default_budget)
            return self._observe_early_exit(owner,captured,rules,context,'default_budget_unavailable')
        # Only publish routes that passed the complete motion simulation and
        # fit the remaining game time. Raw search results stay in diagnostics.
        rows=[row for row,_budget in available]
        family_unavailable=all(row.get('family_consistent') is False for row in rows)
        emit('atlas_candidates',batch_id=batch_id,candidates=rows,default_id=default['id'],
             compromise_only=compromise_only,
             compromise_fallback=compromise_fallback,
             strict_exact=strict_exact_fallback,
             family_unavailable=family_unavailable,
             message=('本轮可执行方案均有区域偏离目标色系，以下按综合色差与落点稳定性排序；不会自动确认染色。'
                      if family_unavailable and compromise_fallback else
                      '本轮可执行方案均有区域偏离目标色系，以下按综合色差与落点稳定性排序。'
                      if family_unavailable else
                      ('未找到所有启用区域共同精准命中，正在定位综合色差最小的妥协方案；不会自动确认染色。'
                       if strict_exact_fallback else
                       '未找到所有启用区域共同达标方案，正在定位综合色差最小的妥协方案；不会自动确认染色。')
                      if compromise_fallback else
                      '未找到满足所设目标的组合，正在定位最接近的妥协方案。'
                      if compromise_only else None))
        try:
            result=self.callbacks.default(owner,report,default,rules,**context)
        except Exception as exc:
            if _is_safety_interrupt(exc):raise
            # An input or verification fault after the session has started is
            # a recoverable execution outcome.  The callback has already
            # released the mouse; keep the current game frame and finish the
            # session without turning the fault into the global error dialog.
            if batch is not None:batch.invalidate()
            emit('atlas_recovery_unavailable',
                 message='当前动作未能可靠复核，已停止自动移动并保留游戏当前画面。',
                 detail=str(exc), candidate_id=default.get('id'))
            return self._observe_early_exit(owner,captured,rules,context,'default_execution_failed')
        if not isinstance(result,dict):
            if batch is not None:batch.invalidate()
            emit('atlas_recovery_unavailable',
                 message='自动方案未返回可验证结果，已停止自动移动并保留游戏当前画面。',
                 detail='default callback returned no result', candidate_id=default.get('id'))
            return self._observe_early_exit(owner,captured,rules,context,'default_result_unavailable')
        result=dict(result, predicted_accepted=result.get('predicted_accepted',bool(default.get('accepted'))),
                    compromise=compromise_only or not bool(default.get('accepted')),
                    candidate_id=default['id'])
        # A local HEX feedback probe may have measured a better sample but
        # failed to return to it before the deadline.  That payload is a
        # terminal, explicitly split observation: the current game pose stays
        # authoritative and ``best_result`` is historical only.  Do not feed
        # it into the ordinary candidate loop or present it as a verified
        # automatic result.
        if result.get('feedback_best_available') and not result.get('best_result_current'):
            if batch is not None:batch.invalidate()
            emit('atlas_best_not_restored',**result)
            return result
        # A recovery can continue only from a newly registered pose. The
        # alternate-candidate path keeps that observation as its checkpoint
        # and does not repeat the failed transform.
        if ((result.get('recovered') or result.get('positioning_complete') is False)
                and not result.get('pose_reliable')):
            if batch is not None:batch.invalidate()
            if result.get('recovered'):emit('atlas_recovery',**result)
            return result
        if not result.get('verified') or result.get('actual_pose') is None:
            if batch is not None:batch.invalidate()
            emit('atlas_recovery_unavailable',
                 message='自动方案未能完成位置复核，已停止自动移动并保留当前游戏画面。',
                 detail='missing verified pose', candidate_id=default.get('id'))
            observed=self._observe_early_exit(owner,captured,rules,context,
                                              'default_observation_unavailable')
            # If no observer is wired, retain the historical verified payload;
            # a wired observer supersedes it with a fresh double-read that has
            # no candidate/pose claim.
            return observed if observed is not None else (result if result.get('verified') else None)
        # Keep the original recovered HEX as the checkpoint. Newly searched
        # translation alternatives participate in the same bound trial/return
        # logic as ordinary candidates, rather than executing inside a callback.
        recovery_rows=report.pop('recovery_candidates',[])
        if recovery_rows:
            rows=sorted(rows+recovery_rows,key=rank_fn)
            emit('atlas_candidates',batch_id=batch_id,candidates=rows,default_id=default['id'],
                 compromise_only=not any(row.get('accepted') for row in rows),
                 family_unavailable=all(row.get('family_consistent') is False for row in rows))
        attempted={default['id']}
        best_result=deepcopy(result);best_candidate=default
        def checkpoint_target():
            # Restore the measured endpoint, which may differ from the
            # originally published candidate after execution replanning.
            return dict(best_candidate,**pose_fields(best_result['actual_pose'],board))
        while not (result.get('accepted') or result.get('observed_accepted')):
            best_quality=_measured_quality(best_result)
            if best_quality is None:break
            next_move=None
            for candidate in rows:
                if candidate['id'] in attempted:continue
                if candidate_quality(candidate)>=best_quality:continue
                try:
                    prepared=self._prepare_protected(owner,report,candidate,result['actual_pose'],rules,context)
                    if prepared is None:continue
                    move,budget=prepared
                    # The fresh endpoint, not the old list prediction, must
                    # improve on the best observed game HEX.
                    if candidate_quality(move)>=best_quality:continue
                    endpoint=(candidate_pose(move,board)@homogeneous(result['actual_pose']))[:2].tolist()
                    returning=self._prepare_protected(owner,report,checkpoint_target(),endpoint,rules,context)
                    if returning is None:continue
                    if time.monotonic()+budget['needed']+returning[1]['needed']>=deadline:continue
                except Exception as exc:
                    if _is_safety_interrupt(exc):raise
                    emit('atlas_candidate_unavailable',candidate_id=candidate.get('id'),detail=str(exc))
                    continue
                next_move=move;default=candidate
                trial_deadline=deadline-returning[1]['needed']
                trial_guard=self._return_guard(owner,report,checkpoint_target(),rules,context)
                break
            if next_move is None:break
            emit('atlas_candidate_failed',**result)
            attempted.add(default['id'])
            emit('atlas_best_observed',**best_result)
            emit('atlas_status',message='当前候选实测未达标，正在定位并复核下一候选。')
            try:
                trial=self.callbacks.choice(owner,report,next_move,rules,
                    **dict(context,selection_deadline=trial_deadline,return_guard=trial_guard))
            except Exception as exc:
                if _is_safety_interrupt(exc):raise
                if batch is not None:batch.invalidate()
                return self._restore_observed(owner,report,dict(candidate_id=default['id'],
                    verified=False,actual_pose=None,detail=str(exc)),best_result,
                    checkpoint_target(),rules,context)
            if not isinstance(trial,dict):
                if batch is not None:batch.invalidate()
                return self._restore_observed(owner,report,dict(candidate_id=default['id'],
                    verified=False,actual_pose=None,detail='choice callback returned no result'),
                    best_result,checkpoint_target(),rules,context)
            result=dict(trial, predicted_accepted=trial.get('predicted_accepted',bool(default.get('accepted'))),
                        compromise=compromise_only or not bool(trial.get('accepted')),
                        candidate_id=default['id'])
            quality=_measured_quality(result)
            if quality is not None and quality<best_quality:
                best_result=deepcopy(result);best_candidate=default
            else:
                # One regression ends exploration. Only a newly bound return
                # from a trusted measured pose may restore the checkpoint.
                result=self._restore_observed(owner,report,result,best_result,
                    checkpoint_target(),rules,context)
                if result.get('best_result_current'):
                    default=best_candidate
                    best_result=deepcopy(result)
                    break
                if batch is not None:batch.invalidate()
                return result
            if result.get('recovered') and not result.get('pose_reliable'):
                if batch is not None:batch.invalidate()
                return dict(result,best_result=deepcopy(best_result),best_result_current=True)
            if not result.get('verified') or result.get('actual_pose') is None:
                if batch is not None:batch.invalidate()
                emit('atlas_recovery_unavailable',
                     message='备用方案未能完成位置复核，已保留当前游戏画面。',
                     detail='missing verified pose', candidate_id=default.get('id'))
                return result if result.get('verified') else None
        if result.get('recovered'):
            if batch is not None:batch.invalidate()
            # Replanning may have replaced the observation with progress or
            # candidate UI. End on the actual measured colours, not a busy
            # screen that the final event would label as interrupted.
            emit('atlas_recovery',**result)
            return result
        # A compromise deliberately exceeds a configured target. Keep the
        # highest-ranked affordable proposal and enable choices instead of
        # walking through successively worse predictions.
        result=dict(result,compromise=compromise_only or not bool(result.get('accepted')),
                    best_result=deepcopy(best_result),best_result_current=True)
        emit('atlas_default_verified',**result)
        try:
            if self.callbacks.select:
                selected=self.callbacks.select(owner,batch_id,deadline,
                                               **{k:v for k,v in context.items() if k!='selection_deadline'})
            else:
                selected=owner.wait_candidate_choice(batch_id,deadline)
        except Exception as exc:
            if _is_safety_interrupt(exc):raise
            if batch is not None:batch.invalidate()
            emit('atlas_recovery_unavailable',
                 message='候选选择未能完成，已保持自动方案。',detail=str(exc))
            return result
        if selected is None or selected==default['id']:
            if getattr(owner,'stop',None) is not None and owner.stop.is_set():
                if batch is not None:batch.invalidate()
                emit('interrupted',message='已停止，保留自动最佳方案。')
                return result
            if batch is not None:batch.invalidate()
            emit('atlas_selection_expired',message='未选择其他方案，保持自动最佳方案。')
            return result
        candidate=next((row for row in rows if row['id']==selected),None)
        if candidate is None:
            if batch is not None:batch.invalidate()
            emit('atlas_choice_rejected',candidate_id=selected,default_id=default['id'],
                 message='候选已失效，保持自动最佳方案。')
            return result
        if result.get('actual_pose') is None:
            if batch is not None:batch.invalidate()
            emit('atlas_choice_rejected',candidate_id=selected,default_id=default['id'],
                 message='缺少当前姿态测量，未执行切换，保持当前颜色。')
            return result
        try:
            prepared=self._prepare_route(owner,report,candidate,result['actual_pose'],rules,context,
                                         user_selected=True)
            if prepared is None:
                if batch is not None:batch.invalidate()
                emit('atlas_choice_rejected',candidate_id=selected,default_id=default['id'],
                     message='所选方案无法完成路线复核，已保留当前实测结果。')
                return result
            move,budget=prepared
            endpoint=(candidate_pose(move,board)@homogeneous(result['actual_pose']))[:2].tolist()
            target=checkpoint_target()
            returning=self._prepare_protected(owner,report,target,endpoint,rules,context)
            if returning is None:
                if batch is not None:batch.invalidate()
                emit('atlas_choice_rejected',candidate_id=selected,default_id=default['id'],
                     message='所选方案的返回路线尚未完成验证，已保留当前实测结果。')
                return result
            return_needed=returning[1]['needed']
            needed=budget['needed']+return_needed
            remaining=deadline-time.monotonic()
            budget=dict(budget,allowed=remaining>needed,
                        reason=None if remaining>needed else 'insufficient_return_time',
                        needed=needed,remaining=remaining,return_needed=return_needed)
        except Exception as exc:
            if _is_safety_interrupt(exc):raise
            if batch is not None:batch.invalidate()
            emit('atlas_choice_rejected',candidate_id=selected,default_id=default['id'],
                 message='所选方案无法生成安全操作，保持自动最佳方案。',detail=str(exc))
            return result
        if not budget['allowed']:
            if batch is not None:batch.invalidate()
            emit('atlas_choice_rejected',candidate_id=selected,default_id=default['id'],
                 predicted_colors=candidate.get('colors'),
                 predicted_deltas=candidate.get('deltas'),
                 predicted_maximum=candidate.get('maximum'),
                 predicted_average=candidate.get('average'),
                 exact_matches=candidate.get('exact_matches'),
                 message=('剩余时间不足以完成切换、返回与颜色复核，已保留当前实测结果。'
                          if budget.get('reason') in ('deadline','insufficient_time','insufficient_return_time') else
                          '所选方案无法从当前位置可靠到达，已保留当前颜色。'),budget=budget)
            return result
        def incomplete_choice(observation):
            if batch is not None:batch.invalidate()
            restored=self._restore_observed(owner,report,observation,best_result,
                checkpoint_target(),rules,context)
            if restored.get('best_result_current'):emit('atlas_verified',**restored)
            return restored
        try:
            choice=self.callbacks.choice(owner,report,move,rules,
                **dict(context,selection_deadline=deadline-return_needed,
                       return_guard=self._return_guard(owner,report,target,rules,context)))
        except Exception as exc:
            if _is_safety_interrupt(exc):raise
            return incomplete_choice(dict(candidate_id=candidate['id'],verified=False,
                                          actual_pose=None,detail=str(exc)))
        if not isinstance(choice,dict):
            return incomplete_choice(dict(candidate_id=candidate['id'],verified=False,
                actual_pose=None,detail='choice callback returned no result'))
        if batch is not None:batch.invalidate()
        if (not choice.get('verified') or choice.get('actual_pose') is None or
                choice.get('recovered') or choice.get('positioning_complete') is False):
            return incomplete_choice(dict(choice,candidate_id=candidate['id']))
        choice=dict(choice, predicted_accepted=choice.get('predicted_accepted',bool(candidate.get('accepted'))),
                    compromise=compromise_only or not bool(choice.get('accepted')),
                    candidate_id=candidate['id'])
        emit('atlas_verified',**choice)
        return choice
