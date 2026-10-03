"""Translation search and neighboring detent routes from a measured pose."""
import numpy as np
import time
from atlas_pose import homogeneous, pose_fields, candidate_pose, relative_candidate
from periodic_atlas import translation_candidates
from candidate_ranking import candidate_rank


class MeasuredAtlas:
    def __init__(self, atlas, pose, capture_offset):
        self.atlas=atlas
        self.pose=homogeneous(pose)
        self.inverse=np.linalg.inv(self.pose)
        self.capture_offset=np.asarray(capture_offset,float)
        self.basis=self.pose[:2,:2]@atlas.basis
        self.resolution=atlas.resolution

    def sample(self, region, points):
        source=(np.asarray(points)-self.pose[:2,2])@self.inverse[:2,:2].T
        return self.atlas.sample(region,source,self.capture_offset)


def reachable_candidates(atlas, capture_offset, actual_pose, markers, board, rules,
                         candidate_id, check=lambda:None, reference_pose=None,
                         limit=32, max_move=None):
    """Keep measured angle/scale; search real integer mouse translations.

    actual_pose is relative to the execution reference. reference_pose maps
    the capture frame to that reference, including after a user selection.
    All three material masks and the existing colour ranking remain in use.
    """
    actual=homogeneous(actual_pose)
    reference=np.eye(3) if reference_pose is None else homogeneous(reference_pose)
    view=MeasuredAtlas(atlas,actual@reference,capture_offset)
    local=np.asarray(markers,float)-np.asarray(board[:2])
    def cancelled():
        check()
        return False
    rows=translation_candidates(view,local,rules,integer_moves=True,
                                landing_radius=1.,cancelled=cancelled,
                                limit=limit,max_move=max_move)
    result=[]
    for row in rows:
        shift=homogeneous([[1,0,row['dx']],[0,1,row['dy']]])
        result.append(dict(row,**pose_fields(shift@actual,board),
                           id=candidate_id,search_space='measured_pose_translation',
                           replanned=True,remaining_translation=[row['dx'],row['dy']]))
    return result


def nearby_zoom_detent_proposals(candidate, actual_pose, board, markers, rules, *,
                                 wheel_direction=0, check=lambda:None):
    """Keep target source points near integer detents from the measured pose.

    A newly measured wheel response can put an old target between detents.
    Enumerate the neighboring integer counts from the actual scale rather
    than treating that old continuous scale as the only admissible target.
    These are geometric proposals only: every endpoint must be bound and
    rescored against the atlas before it is eligible for input.
    """
    check()
    actual=homogeneous(actual_pose);target=candidate_pose(candidate,board)
    points=np.asarray(markers,float)-np.asarray(board[:2],float)
    active=[i for i,r in enumerate(rules) if r.get('enabled')]
    if (points.shape!=(3,2) or not np.isfinite(points).all() or
            len(rules)!=3 or not active or wheel_direction not in (-1,0,1)):
        raise ValueError('Invalid zoom detent geometry')
    start_scale=float(np.hypot(actual[0,0],actual[1,0]))
    target_scale=float(np.hypot(target[0,0],target[1,0]))
    relative_log=float(np.log(target_scale/start_scale))
    direction=1 if relative_log>0 else -1
    def measured_tick(direction):
        try:
            value=abs(float(candidate.get('zoom_log_step_up') if direction>0 else
                            candidate.get('zoom_log_step')))
        except (TypeError,ValueError):
            raise ValueError('Invalid measured directional wheel response') from None
        if not np.isfinite(value) or not 1e-5<value<.15:
            raise ValueError('Invalid measured directional wheel response')
        return value
    tick=measured_tick(direction)
    count=relative_log/tick
    counts={0,int(np.floor(count)),int(np.ceil(count)),int(np.rint(count))}
    counts.update((int(np.floor(count))-1,int(np.ceil(count))+1))
    counts=sorted(n for n in counts if abs(n)<=48 and
                  (not wheel_direction or not n or np.sign(n)==wheel_direction))
    source=(points-target[:2,2])@np.linalg.inv(target[:2,:2]).T
    orientation=target[:2,:2]/target_scale
    proposals=[]
    for steps in counts:
        check()
        # Each count uses its own directional observation. No inverse UP
        # assumption and no reverse tick to chase the old scale are allowed.
        step_tick=measured_tick(1 if steps>0 else -1)
        scale=start_scale*float(np.exp(steps*step_tick))
        linear=scale*orientation
        offsets=points-source@linear.T
        # Balance all enabled regions, then retain anchor alternatives for
        # narrow islands. Color ranking decides between freshly scored routes.
        centres=[offsets[active].mean(axis=0),*offsets[active]]
        centres.extend((offsets[a]+offsets[b])/2
                       for j,a in enumerate(active) for b in active[j+1:])
        for offset in np.unique(np.asarray(centres),axis=0):
            matrix=homogeneous(np.column_stack((linear,offset)))
            row=dict(candidate,**pose_fields(matrix,board),
                     search_space='measured_zoom_detent',replanned=True,
                     scale_source='measured_pose_and_directional_ticks',
                     detent_start_scale=start_scale,detent_wheel_steps=steps,
                     previous_target_scale=target_scale)
            for name in ('planned_route','input_route','execution_budget'):
                row.pop(name,None)
            proposals.append(row)
    return proposals


def bind_nearby_zoom_detents(candidate, actual_pose, atlas, capture_offset, board,
                             markers, rules, now, deadline, *, reference_pose=None,
                             wheel_direction=0, check=lambda:None,
                             require_stable=True, allow_color_compromise=True,
                             clock=time.monotonic):
    """Return the best freshly scored integer route from the measured pose.

    ``candidate`` and ``actual_pose`` share the current execution reference.
    ``reference_pose`` maps the acquisition frame to that reference. The
    returned route is relative to ``actual_pose``, ready for _adopt_bound_route.
    The caller retains all positioning, return-budget and observation guards.
    """
    from atlas_bound_route import bind_candidate
    from atlas_execution import reposition_budget
    started=clock()
    def current_time():return float(now)+max(0.,clock()-started)
    actual=homogeneous(actual_pose)
    reference=np.eye(3) if reference_pose is None else homogeneous(reference_pose)
    proposals=nearby_zoom_detent_proposals(candidate,actual,board,markers,rules,
                                         wheel_direction=wheel_direction,check=check)
    prepared=[];rejected=[]
    for proposal in proposals:
        check()
        if current_time()>=deadline:
            rejected.append('deadline');break
        move=relative_candidate(proposal,actual,board)
        row,budget=bind_candidate(move,atlas,capture_offset,board,markers,rules,
                                 current_time(),deadline,reference_pose=actual@reference,
                                 check=check,require_stable=require_stable,
                                 allow_color_compromise=allow_color_compromise)
        if row is None:
            rejected.append(budget.get('reason'));continue
        # Binding may finish within the existing geometric tolerance at an
        # adjacent detent. Record the actual compiled count, not the proposal.
        row['wheel_steps']=sum(int(record['wheel_steps'])
            for record in row['planned_route']['inputs'] if record['kind']=='wheel')
        row['detent_rescored']=True
        prepared.append((row,budget))
    # Scoring several alternatives consumes part of the same live deadline.
    # Reprice the retained route after the search, including HEX verification,
    # rather than returning an already stale pre-scoring budget.
    repriced=[]
    for row,_ in prepared:
        check()
        budget=reposition_budget(row,current_time(),deadline,board,markers=markers)
        if budget['allowed']:
            row['execution_budget']={k:v for k,v in budget.items() if k!='input_route'}
            repriced.append((row,budget))
        else:rejected.append(budget['reason'])
    prepared=repriced
    if not prepared:
        return None,dict(allowed=False,reason='no_supported_zoom_detent',
                         rejected_reasons=sorted(set(rejected)),proposals=len(proposals))
    return min(prepared,key=lambda item:candidate_rank(item[0]))
