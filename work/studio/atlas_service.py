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


class AtlasService:
    def __init__(self, callbacks):
        self.callbacks=callbacks

    def run(self, owner, rules, **context):
        emit=owner.event
        emit('atlas_status',message='正在采集本局颜色板。')
        captured=self.callbacks.acquire(owner,rules,**context)
        report=self.callbacks.build(captured,rules,**context)
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
            budget=(reposition_budget(row,time.monotonic(),deadline,board,markers=markers)
                    if deadline is not None and board else {'allowed':False})
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
        result=self.callbacks.default(owner,report,default,rules,**context)
        result=dict(result, predicted_accepted=bool(default.get('accepted')),
                    compromise=compromise_only or not bool(default.get('accepted')),
                    candidate_id=default['id'])
        if not result.get('verified') or result.get('actual_pose') is None:
            raise RuntimeError('Candidate execution did not return measured pose and HEX verification')
        attempted={default['id']}
        # A successful geometric move is not a successful color match. Try
        # other predicted candidates only after a complete, measured HEX read.
        # Input/registration/OCR failures propagate and never trigger a retry.
        while result.get('verified') and not result.get('accepted') and default.get('accepted'):
            emit('atlas_candidate_failed',**result)
            if result.get('actual_pose') is None:break
            next_move=None
            for candidate in rows:
                if candidate['id'] in attempted:continue
                if candidate.get('exact_matches',0)<result.get('exact_matches',0):continue
                move=relative_candidate(candidate,result['actual_pose'],board)
                budget=reposition_budget(move,time.monotonic(),deadline,board,markers=markers)
                if budget['allowed']:
                    next_move=move;default=candidate;break
            if next_move is None:break
            attempted.add(default['id'])
            emit('atlas_status',message='当前候选实测未达标，正在定位并复核下一候选。')
            result=self.callbacks.choice(owner,report,next_move,rules,**context)
            result=dict(result, predicted_accepted=bool(default.get('accepted')),
                        compromise=not bool(default.get('accepted')),
                        candidate_id=default['id'])
            if not result.get('verified') or result.get('actual_pose') is None:
                raise RuntimeError('Candidate execution did not return measured pose and HEX verification')
        if result.get('verified') and not result.get('accepted') and default.get('accepted'):
            if batch is not None:batch.invalidate()
            emit('atlas_verified',**result)
            return result
        # A compromise deliberately exceeds a configured target. Keep the
        # highest-ranked affordable proposal and enable choices instead of
        # walking through successively worse predictions.
        result=dict(result,compromise=not bool(result.get('accepted')))
        emit('atlas_default_verified',**result)
        if self.callbacks.select:
            selected=self.callbacks.select(owner,batch_id,deadline,
                                           **{k:v for k,v in context.items() if k!='selection_deadline'})
        else:
            selected=owner.wait_candidate_choice(batch_id,deadline)
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
        move=relative_candidate(candidate,result['actual_pose'],board)
        budget=(reposition_budget(move,time.monotonic(),deadline,board,markers=markers)
                if board else {'allowed':False})
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
        choice=self.callbacks.choice(owner,report,move,rules,**context)
        if batch is not None:batch.invalidate()
        if not choice.get('verified') or choice.get('actual_pose') is None:
            raise RuntimeError('Candidate execution did not return measured pose and HEX verification')
        choice=dict(choice, predicted_accepted=bool(candidate.get('accepted')),
                    compromise=not bool(candidate.get('accepted')),
                    candidate_id=candidate['id'])
        emit('atlas_verified',**choice)
        return choice
