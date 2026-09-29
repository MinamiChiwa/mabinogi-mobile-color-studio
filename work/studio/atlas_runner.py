"""Platform-independent controller for the per-session atlas flow.

The controller owns candidate lifetime and timing policy; a platform adapter
performs capture, motion and HEX verification.  It never sends game input.
"""
from dataclasses import dataclass
from atlas_execution import CandidateBatch, CandidateExpired, reposition_budget
from atlas_pose import homogeneous, relative_candidate


class AtlasPhase:
    WAITING = 'waiting'
    DEFAULT_POSITIONING = 'default_positioning'
    CHOOSING = 'choosing'
    CHOICE_POSITIONING = 'choice_positioning'
    KEEP_DEFAULT = 'keep_default'
    COMPLETE = 'complete'
    INVALIDATED = 'invalidated'


@dataclass(frozen=True)
class AtlasEvent:
    kind: str
    data: dict


class AtlasController:
    def __init__(self, batch: CandidateBatch, board, clock):
        self.batch = batch
        self.board = tuple(board)
        self.clock = clock
        self.phase = AtlasPhase.WAITING
        self.default = None
        self.choice = None

    def begin_default(self):
        if self.phase != AtlasPhase.WAITING:
            raise CandidateExpired('Atlas session is not ready for default positioning')
        self.default = self.batch.claim_default(self.batch.id, self.batch.context)
        self.phase = AtlasPhase.DEFAULT_POSITIONING
        return AtlasEvent('atlas_default', dict(candidate=self.default,
                                                batch_id=self.batch.id))

    def default_verified(self, result):
        if self.phase != AtlasPhase.DEFAULT_POSITIONING:
            raise CandidateExpired('Default candidate is not being positioned')
        if not self.batch.default_executed or not result.get('verified',False):
            raise CandidateExpired('Automatic default must be positioned and verified first')
        if result.get('actual_pose') is None:
            raise CandidateExpired('Measured default pose is unavailable')
        self.batch.actual_pose=homogeneous(result['actual_pose'])
        self.phase = AtlasPhase.CHOOSING
        return AtlasEvent('atlas_default_verified', dict(result=result))

    def choose(self, candidate_id):
        if self.phase != AtlasPhase.CHOOSING:
            raise CandidateExpired('Candidate selection is no longer open')
        candidate = self.batch.claim_choice(self.batch.id, candidate_id,
                                             self.batch.context)
        if self.batch.actual_pose is None:
            raise CandidateExpired('Measured default pose is unavailable')
        move=relative_candidate(candidate,self.batch.actual_pose,self.board)
        budget = reposition_budget(move, self.clock(), self.batch.deadline,
                                   self.board,markers=self.batch.context.markers)
        if not budget['allowed']:
            self.phase = AtlasPhase.KEEP_DEFAULT
            return AtlasEvent('atlas_choice_rejected', dict(candidate_id=candidate_id,
                default_id=self.default['id'],budget=budget,
                message=('剩余时间不足，保持自动最佳方案。'
                         if budget.get('reason') in ('deadline','insufficient_time') else
                         '所选方案无法从当前位置可靠到达，已保留当前颜色。')))
        self.choice = move
        self.phase = AtlasPhase.CHOICE_POSITIONING
        return AtlasEvent('atlas_choice', dict(candidate=move,
                                               batch_id=self.batch.id,
                                               budget=budget))

    def selection_expired(self):
        if self.phase != AtlasPhase.CHOOSING:
            raise CandidateExpired('Candidate selection is not open')
        self.phase = AtlasPhase.KEEP_DEFAULT
        return AtlasEvent('atlas_selection_expired',
                          dict(message='未选择其他方案，保持自动最佳方案。'))

    def choice_verified(self, result):
        if self.phase != AtlasPhase.CHOICE_POSITIONING:
            raise CandidateExpired('User choice is not being positioned')
        if not result.get('verified',False):
            raise CandidateExpired('User choice must be verified before completion')
        self.phase = AtlasPhase.COMPLETE
        return AtlasEvent('atlas_verified', dict(result=result))

    def invalidate(self, message):
        self.batch.invalidate()
        self.phase = AtlasPhase.INVALIDATED
        return AtlasEvent('atlas_invalidated', dict(message=message))
