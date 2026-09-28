"""Dependency-injected atlas pipeline used by the formal Runner seam.

Platform callbacks own screenshots and input.  This module owns lifecycle
events and refuses to publish candidates until the builder reports a passed
quality gate.
"""
from dataclasses import dataclass
import time
import uuid
from atlas_execution import reposition_budget
from workflow_budget import earliest_deadline
from candidate_ranking import candidate_rank
from atlas_pose import relative_candidate


@dataclass
class AtlasCallbacks:
    acquire: object
    build: object
    default: object
    choice: object
    select: object=None


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


class AtlasService:
    def __init__(self, callbacks):
        self.callbacks=callbacks

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
            return None
        gate=report.get('quality_gate',{})
        if not gate.get('passed',False):
            emit('atlas_invalidated',reason='atlas_quality_failed',search_performed=False,
                 message=quality_failure_message(gate),quality_gate=gate)
            return None
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
        rows=report.get('candidates',[])
        raw_rows=list(rows)
        raw_accepted=[row for row in raw_rows if row.get('accepted')]
        compromise_rows=[row for row in raw_rows if row not in raw_accepted]
        best_compromise=min(compromise_rows,key=candidate_rank) if compromise_rows else None
        emit('atlas_search_summary',raw_count=len(raw_rows),
             predicted_accepted_count=len(raw_accepted),
             compromise_count=len(compromise_rows),
             best_compromise_max=best_compromise.get('maximum') if best_compromise else None,
             best_compromise_average=best_compromise.get('average') if best_compromise else None,
             search_diagnostics=report.get('search_diagnostics',{}))
        compromise_only=not bool(raw_accepted)
        if not rows:
            message='本轮搜索没有可测量的落点；无法生成自动或妥协方案。'
            emit('atlas_invalidated',reason='bounded_search_no_match',search_performed=True,message=message,
                 search_diagnostics=report.get('search_diagnostics',{}))
            return None
        rows=sorted(rows,key=candidate_rank)
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
            return None
        emit('atlas_candidates',batch_id=batch_id,candidates=rows,default_id=default['id'],
             compromise_only=compromise_only,
             message=('未找到满足所设目标的组合，正在定位最接近的妥协方案。'
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
            return None
        if not isinstance(result,dict):
            if batch is not None:batch.invalidate()
            emit('atlas_recovery_unavailable',
                 message='自动方案未返回可验证结果，已停止自动移动并保留游戏当前画面。',
                 detail='default callback returned no result', candidate_id=default.get('id'))
            return None
        result=dict(result, predicted_accepted=bool(default.get('accepted')),
                    compromise=compromise_only or not bool(default.get('accepted')),
                    candidate_id=default['id'])
        # Recovery is terminal unless the repeated frame proves that the
        # game reached a native zoom stop.  In that bounded case the measured
        # pose is still trustworthy, so the normal alternate-candidate path
        # may rebase from it without repeating the failed wheel input.
        if ((result.get('recovered') or result.get('positioning_complete') is False)
                and not result.get('pose_reliable')):
            if batch is not None:batch.invalidate()
            return result
        if not result.get('verified') or result.get('actual_pose') is None:
            if batch is not None:batch.invalidate()
            emit('atlas_recovery_unavailable',
                 message='自动方案未能完成位置复核，已停止自动移动并保留当前游戏画面。',
                 detail='missing verified pose', candidate_id=default.get('id'))
            return result if result.get('verified') else None
        attempted={default['id']}
        # A successful geometric move is not a successful color match. Try
        # other predicted candidates only after a complete, measured HEX read.
        # Input/registration/OCR failures propagate and never trigger a retry.
        while (result.get('verified') and not result.get('accepted') and
               (default.get('accepted') or result.get('recovered'))):
            emit('atlas_candidate_failed',**result)
            if result.get('actual_pose') is None:break
            next_move=None
            for candidate in rows:
                if candidate['id'] in attempted:continue
                if candidate.get('exact_matches',0)<result.get('exact_matches',0):continue
                try:
                    move=relative_candidate(candidate,result['actual_pose'],board)
                    budget=reposition_budget(move,time.monotonic(),deadline,board,markers=markers)
                except Exception as exc:
                    emit('atlas_candidate_unavailable',candidate_id=candidate.get('id'),detail=str(exc))
                    continue
                if budget['allowed']:
                    next_move=move;default=candidate;break
            if next_move is None:break
            attempted.add(default['id'])
            emit('atlas_status',message='当前候选实测未达标，正在定位并复核下一候选。')
            try:
                result=self.callbacks.choice(owner,report,next_move,rules,**context)
            except Exception as exc:
                if _is_safety_interrupt(exc):raise
                emit('atlas_recovery_unavailable',
                     message='备用方案未能可靠复核，已保留当前游戏画面。',
                     detail=str(exc), candidate_id=default.get('id'))
                if batch is not None:batch.invalidate()
                return result
            if not isinstance(result,dict):
                if batch is not None:batch.invalidate()
                emit('atlas_recovery_unavailable',
                     message='备用方案未返回可验证结果，已保留当前游戏画面。',
                     detail='choice callback returned no result', candidate_id=default.get('id'))
                return result
            result=dict(result, predicted_accepted=bool(default.get('accepted')),
                        compromise=not bool(default.get('accepted')),
                        candidate_id=default['id'])
            if result.get('recovered') and not result.get('pose_reliable'):
                if batch is not None:batch.invalidate()
                return result
            if not result.get('verified') or result.get('actual_pose') is None:
                if batch is not None:batch.invalidate()
                emit('atlas_recovery_unavailable',
                     message='备用方案未能完成位置复核，已保留当前游戏画面。',
                     detail='missing verified pose', candidate_id=default.get('id'))
                return result if result.get('verified') else None
        if result.get('recovered'):
            if batch is not None:batch.invalidate()
            return result
        if result.get('verified') and not result.get('accepted') and default.get('accepted'):
            if batch is not None:batch.invalidate()
            emit('atlas_verified',**result)
            return result
        # A compromise deliberately exceeds a configured target. Keep the
        # highest-ranked affordable proposal and enable choices instead of
        # walking through successively worse predictions.
        result=dict(result,compromise=not bool(result.get('accepted')))
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
            move=relative_candidate(candidate,result['actual_pose'],board)
            budget=(reposition_budget(move,time.monotonic(),deadline,board,markers=markers)
                    if board else {'allowed':False})
        except Exception as exc:
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
                 message='剩余时间不足，保持自动最佳方案。',budget=budget)
            return result
        try:
            choice=self.callbacks.choice(owner,report,move,rules,**context)
        except Exception as exc:
            if _is_safety_interrupt(exc):raise
            if batch is not None:batch.invalidate()
            emit('atlas_recovery_unavailable',
                 message='所选备用方案未能可靠复核，已保留自动方案。',
                 detail=str(exc), candidate_id=default.get('id'))
            return result
        if not isinstance(choice,dict):
            emit('atlas_recovery_unavailable',
                 message='所选方案未返回可验证结果，已保留自动方案。',
                 detail='choice callback returned no result', candidate_id=candidate.get('id'))
            return result
        if batch is not None:batch.invalidate()
        if not choice.get('verified') or choice.get('actual_pose') is None:
            emit('atlas_recovery_unavailable',
                 message='所选方案未能完成位置复核，已保留自动方案。',
                 detail='missing verified pose', candidate_id=candidate.get('id'))
            return result
        choice=dict(choice, predicted_accepted=bool(candidate.get('accepted')),
                    compromise=not bool(candidate.get('accepted')),
                    candidate_id=candidate['id'])
        emit('atlas_verified',**choice)
        return choice
