"""Single-use candidates and measured, bounded similarity execution.

No platform imports: the adapter supplies guarded capture/drag/OCR methods.
Nothing in this module confirms or cancels a dye.
"""
from copy import deepcopy
from dataclasses import dataclass
import threading
import time
import uuid
import numpy as np
from vision import accepted, error
from candidate_ranking import candidate_rank
from atlas_pose import candidate_pose, homogeneous, marker_errors, pose_fields, relative_candidate
from planner import decompose_gestures
from input_gestures import planned_gesture
from atlas_stage_budget import StageBudgetExceeded


# Below this screen-space marker displacement, integer mouse coordinates cannot
# provide a reliable feature-registration measurement.
MICRO_ROTATION_PIXELS = 3.0
POSITION_TOLERANCE = 1.0


class CandidateExpired(RuntimeError):
    pass


def _nearest_detent_translation(target,actual,fields,markers,zoom_tick):
    """Return an integer picker-aligned drag at a sufficiently close detent.

    Atlas scale levels are estimated from capture measurements, while live
    wheel detents can differ slightly. If one click has crossed the continuous
    target, accept the nearer detent only when it is within half a measured
    click and a shared translation can still put all markers within 1 pixel.
    Final game HEX verification remains mandatory.
    """
    scale_error=abs(float(np.log(fields['scale'])))
    if not np.isfinite(scale_error) or scale_error>float(zoom_tick)*.55:
        return None
    points=np.column_stack((markers,np.ones(len(markers))))
    shifts=points[:,:2]-(points@(actual@np.linalg.inv(target)).T)[:,:2]
    # Use the picker geometry rather than the unrelated board center.
    centers=[shifts.mean(axis=0),*shifts]
    centers.extend((a+b)/2 for i,a in enumerate(shifts) for b in shifts[i+1:])
    if len(shifts)==3:
        a=2*(shifts[1:]-shifts[0])
        if abs(np.linalg.det(a))>1e-10:
            centers.append(np.linalg.solve(a,(shifts[1:]**2).sum(axis=1)-(shifts[0]**2).sum()))
    moves=np.unique(np.concatenate([np.rint(c)+[[x,y] for x in (-1,0,1) for y in (-1,0,1)]
                                    for c in centers]),axis=0)
    best=int(np.argmin(np.linalg.norm(shifts[None]-moves[:,None],axis=2).max(axis=1)))
    dx,dy=moves[best]
    center_drag=homogeneous([[1,0,dx],[0,1,dy]])
    errors=marker_errors(target,center_drag@actual,markers)
    if not np.isfinite(errors).all() or float(np.max(errors))>1.:
        return None
    return dict(dx=float(dx),dy=float(dy),
                scale_error=scale_error,marker_errors=errors.tolist())


def _measured_motion(adapter, before, after, emit, phase, step=0):
    registration = adapter.motion(before, after)
    diagnostics = deepcopy(getattr(adapter, 'last_motion_diagnostics', None))
    emit('atlas_registration', dict(phase=phase, step=step,
                                   passed=registration is not None, diagnostics=diagnostics,
                                   measured=(np.asarray(registration['matrix']).tolist()
                                             if registration is not None and 'matrix' in registration else None)))
    if registration is None:
        reasons = {
            'insufficient_features': '可识别纹理特征不足',
            'insufficient_matches': '前后图像匹配点不足',
            'invalid_transform': '无法计算可靠位移',
            'insufficient_inliers': '一致纹理匹配点不足',
            'insufficient_material_overlap': '同材质重叠区域不足',
            'insufficient_region_overlap': '部分材质重叠区域不足',
            'material_rgb_mismatch': '同材质颜色校验未通过',
        }
        reason = reasons.get((diagnostics or {}).get('reason'), '前后图像配准未通过')
        raise CandidateExpired(f'无法验证色板位置：{reason}。已停止自动移动，请手动检查当前颜色。')
    return registration


def _estimate_candidate_motion(candidate, board, markers, max_steps):
    """Simulate the same rotate/zoom/drag order used by execute_candidate.

    Input descriptors are exact. Rotation uses the grouped integer arc, with
    limited live evidence, and zoom uses this session's directional estimate.
    The result still needs measured feedback and final-pose colour scoring.

    The previous budget estimate added a separate worst-case pivot translation
    to the rotation and zoom counts. In practice decompose_gestures chooses a
    pivot specifically to absorb most of that translation, so the estimate
    could reject a candidate that needs about half as many measured operations.
    """
    l,t,r,b=map(float,board)
    if markers is None:
        # Only for non-live callers without scene geometry. Production callers
        # pass the three captured markers so this plan matches execution.
        markers=((l+(r-l)/6,t+(b-t)/2),
                 (l+(r-l)/2,t+(b-t)/2),
                 (l+5*(r-l)/6,t+(b-t)/2))
    markers=np.asarray(markers,float)
    local_markers=markers-[l,t]
    target=candidate_pose(candidate,board)
    actual=np.eye(3)
    center=np.array([(r-l)/2,(b-t)/2])
    cap=np.array([r-l,b-t])*.16
    radius=max(1.,float(np.max(np.linalg.norm(
        local_markers-local_markers.mean(axis=0),axis=1))))
    zoom_tick=abs(float(candidate.get('zoom_log_step',np.log(1.01))))
    actions=dict(rotate=0,wheel=0,drag=0)
    input_route=[]
    def compile_input(kind,command,anchor=None):
        gesture=planned_gesture(kind,board,command,anchor)
        input_route.append(gesture.record())
        return gesture
    translation_steps=0
    last_zoom_direction=0
    if not np.isfinite(zoom_tick) or zoom_tick<1e-5:
        zoom_tick=float(np.log(1.01))
    zoom_ticks={-1:zoom_tick,1:float(candidate.get('zoom_log_step_up',zoom_tick))}

    for step in range(max_steps+1):
        errors=marker_errors(target,actual,local_markers)
        if float(np.max(errors))<=POSITION_TOLERANCE:
            # Finish at the best neighbouring integer translation, including
            # a valid no-op. A continuous proposal inside the final tolerance
            # must not be rejected because its rounded residual is zero.
            points=np.column_stack((local_markers,np.ones(len(local_markers))))
            shifts=points[:,:2]-(points@(actual@np.linalg.inv(target)).T)[:,:2]
            centres=[shifts.mean(axis=0),*shifts]
            moves=np.unique(np.concatenate([np.rint(c)+[[x,y] for x in (-1,0,1)
                                                       for y in (-1,0,1)] for c in centres]),axis=0)
            move_errors=np.linalg.norm(shifts[None]-moves[:,None],axis=2).max(axis=1)
            best=int(np.argmin(move_errors));move=moves[best]
            if (np.any(move) and step<max_steps and translation_steps<10 and
                    move_errors[best]<float(np.max(errors))-1e-9):
                gesture=compile_input('drag',move)
                actual=homogeneous(np.column_stack((np.eye(2),gesture.translation)))@actual
                actions['drag']+=1;translation_steps+=1
                continue
            return dict(steps=step,actions=actions,reachable=True,
                        actual_pose=actual[:2].tolist(),marker_errors=errors.tolist(),
                        input_route=input_route,
                        response_model='grouped_integer_arc_and_directional_zoom',
                        game_response_verified=False)
        if step>=max_steps:
            break
        residual=target@np.linalg.inv(actual)
        fields=pose_fields(residual,board)
        gestures=decompose_gestures(fields,board,markers)
        anchor=None
        if abs(np.radians(fields['angle']))*radius>.3:
            kind='rotate'
            command=float(np.clip(fields['angle'],-12,12))
            gesture=compile_input(kind,command,gestures['rotation_anchor'])
            if not gesture.has_effect:
                return dict(steps=step,actions=actions,reachable=False,
                            reason='rotation_quantized',input_route=input_route)
            # Controlled comparisons support this geometric forecast for the
            # sampled grouped arcs, not an arbitrary-angle response guarantee.
            # The requested angle is never substituted for the integer arc.
            theta=np.radians(gesture.arc_degrees)
            scale=1.
            anchor=np.asarray(gesture.anchor,float)-[l,t]
        elif abs(np.log(fields['scale']))*radius>.3:
            kind='wheel'
            direction=1 if fields['scale']>1 else -1
            zoom_tick=zoom_ticks[direction]
            if last_zoom_direction and direction!=last_zoom_direction:
                detent=_nearest_detent_translation(target,actual,fields,local_markers,
                                                    zoom_tick)
                if detent is None:
                    return dict(steps=step+1,actions=actions,reachable=False,
                                reason='unreachable_scale')
                kind='drag'
                remaining=np.array([detent['dx'],detent['dy']])
                command=np.rint(remaining/max(1.,float(np.max(abs(remaining)/cap))))
                if not np.any(command):
                    return dict(steps=step,actions=actions,reachable=False,
                                reason='no_measurable_motion')
                if translation_steps>=10:
                    return dict(steps=max_steps+1,actions=actions,reachable=False,
                                reason='translation_limit')
                translation_steps+=1
                gesture=compile_input(kind,command)
                command=np.asarray(gesture.translation)
                actions[kind]+=1
                actual=homogeneous(np.column_stack((np.eye(2),command)))@actual
                continue
            last_zoom_direction=direction
            command=direction*min(4,max(1,int(abs(np.log(fields['scale']))/zoom_tick+.1)))
            gesture=compile_input(kind,command,gestures['zoom_anchor'])
            command=gesture.wheel_steps
            theta=0.
            scale=np.exp(command*zoom_tick)
            anchor=np.asarray(gesture.anchor,float)-[l,t]
        else:
            kind='drag'
            remaining=residual[:2,:2]@center+residual[:2,2]-center
            if np.any(cap<2):
                return dict(steps=max_steps+1,actions=actions,reachable=False,
                            reason='board_too_small')
            command=np.rint(remaining/max(1.,float(np.max(abs(remaining)/cap))))
            if not np.any(command):
                return dict(steps=step,actions=actions,reachable=False,
                            reason='no_measurable_motion')
            if translation_steps>=10:
                return dict(steps=max_steps+1,actions=actions,reachable=False,
                            reason='translation_limit')
            translation_steps+=1
            gesture=compile_input(kind,command)
            command=np.asarray(gesture.translation)
            actions[kind]+=1
            measured=homogeneous(np.column_stack((np.eye(2),command)))
            actual=measured@actual
            continue

        matrix=scale*np.array([[np.cos(theta),-np.sin(theta)],
                               [np.sin(theta),np.cos(theta)]])
        measured=homogeneous(np.column_stack((matrix,anchor-matrix@anchor)))
        actions[kind]+=1
        actual=measured@actual
    return dict(steps=max_steps+1,actions=actions,reachable=False,
                reason='step_limit')


def reposition_budget(candidate, now, deadline, board, step_seconds=None,
                      verify_seconds=3., safety_seconds=.5, max_steps=80,
                      markers=None):
    """Estimate the actual control sequence before HEX verification.

    Timing defaults use recent measured per-action costs (rotation 1.2s, wheel
    0.5s, drag 1.05s), plus a 3s HEX read and a 0.5s boundary margin. The real
    executor still checks the game deadline before every input and verification.
    """
    if deadline <= now:return dict(allowed=False,reason='deadline')
    if candidate.get('planned_route') is not None:
        from atlas_bound_route import bound_motion
        plan=bound_motion(candidate,board,markers,max_steps)
    else:
        plan=_estimate_candidate_motion(candidate,board,markers,max_steps)
    actions=plan['actions'];steps=plan['steps']
    if step_seconds is None:
        movement=(actions['rotate']*1.2+actions['wheel']*.5+
                  actions['drag']*1.05)
        movement=max(movement,sum(g['input_seconds']+.15 for g in plan.get('input_route',[])))
    else:
        movement=steps*float(step_seconds)
    needed=movement+float(verify_seconds)+float(safety_seconds)
    remaining=float(deadline-now)
    allowed=plan['reachable'] and steps<=max_steps and remaining>=needed
    if allowed:reason='ok'
    elif not plan['reachable']:reason=plan.get('reason','unreachable')
    else:reason='insufficient_time'
    return dict(allowed=allowed,reason=reason,steps=steps,actions=actions,
                needed=needed,remaining=remaining,
                input_route=plan.get('input_route',[]),
                response_model=plan.get('response_model','unverified'),
                game_response_verified=False,
                planned_pose=plan.get('actual_pose'),
                planned_marker_errors=plan.get('marker_errors'))


@dataclass(frozen=True)
class Context:
    session: str
    geometry: tuple
    board: tuple
    markers: tuple


class CandidateBatch:
    def __init__(self, candidates, context, deadline, clock=time.monotonic):
        self.id=uuid.uuid4().hex;self.context=context;self.deadline=deadline
        self._clock=clock;self._rows={r['id']:deepcopy(r) for r in candidates}
        if len(self._rows)!=len(candidates):raise ValueError('Duplicate candidate IDs')
        self._lock=threading.Lock();self.used=False
        self.default_id=None;self.choice_id=None
        self.default_executed=False
        self.actual_pose=None

    def _check(self,batch_id,context):
        if (self.used or batch_id!=self.id or context!=self.context
                or self._clock()>=self.deadline):
            raise CandidateExpired('Candidate expired or no longer matches the session')

    def best(self):
        """Return the deterministic lowest-error executable candidate."""
        if not self._rows: raise CandidateExpired('Candidate batch is empty')
        return deepcopy(min(self._rows.values(),key=candidate_rank))

    def claim_default(self,batch_id,context):
        """Reserve the automatic best candidate without consuming the batch."""
        with self._lock:
            self._check(batch_id,context)
            if self.default_id is not None:
                raise CandidateExpired('Default candidate already reserved')
            row=self.best();self.default_id=row['id'];return row

    def claim_choice(self,batch_id,candidate_id,context):
        """Reserve one user choice after the automatic candidate is known."""
        with self._lock:
            self._check(batch_id,context)
            if self.default_id is None or not self.default_executed:
                raise CandidateExpired('Default candidate must be executed first')
            if self.choice_id is not None or candidate_id not in self._rows:
                raise CandidateExpired('Candidate choice already made or unknown')
            self.choice_id=candidate_id;return deepcopy(self._rows[candidate_id])

    def commit(self,batch_id,candidate_id,context):
        """Execute a reservation; default execution keeps the batch open."""
        with self._lock:
            self._check(batch_id,context)
            if candidate_id not in (self.default_id,self.choice_id):
                raise CandidateExpired('Candidate was not reserved for execution')
            if candidate_id==self.choice_id:
                if not self.default_executed:
                    raise CandidateExpired('Default candidate must be executed before a choice')
                self.used=True
            elif self.default_executed:
                raise CandidateExpired('Default candidate was already executed')
            else:
                self.default_executed=True
            return deepcopy(self._rows[candidate_id])

    def commit_default(self,batch_id,context,candidate_id=None):
        """Reserve if needed, then commit the automatic best candidate once."""
        with self._lock:
            self._check(batch_id,context)
            if self.default_id is None:
                self.default_id=self.best()['id'] if candidate_id is None else candidate_id
                if self.default_id not in self._rows:raise CandidateExpired('Unknown default candidate')
            if candidate_id is not None and candidate_id!=self.default_id:
                raise CandidateExpired('Requested candidate is not the automatic default')
            if self.default_executed:
                raise CandidateExpired('Default candidate was already executed')
            self.default_executed=True
            return deepcopy(self._rows[self.default_id])

    def commit_choice(self,batch_id,candidate_id,context):
        """Commit a post-default choice as a displacement from that default."""
        with self._lock:
            self._check(batch_id,context)
            if self.default_id is None or not self.default_executed:
                raise CandidateExpired('Automatic default must be executed before a choice')
            if self.choice_id is None:
                if candidate_id not in self._rows:
                    raise CandidateExpired('Unknown candidate')
                self.choice_id=candidate_id
            elif self.choice_id!=candidate_id:
                raise CandidateExpired('A different candidate choice is already reserved')
            self.used=True
            row=deepcopy(self._rows[self.choice_id])
            if self.actual_pose is None:
                raise CandidateExpired('Measured default pose is unavailable')
            return relative_candidate(row,self.actual_pose,self.context.board)

    def claim(self,batch_id,candidate_id,context):
        with self._lock:
            self._check(batch_id,context)
            if candidate_id not in self._rows:
                raise CandidateExpired('Candidate expired or no longer matches the session')
            self.used=True
            return deepcopy(self._rows[candidate_id])

    def invalidate(self):
        with self._lock:self.used=True


def checked_translation(motion):
    if motion is None:raise CandidateExpired('无法验证色板位置：前后图像配准未通过。')
    matrix=np.asarray(motion['matrix'],float)
    if matrix.shape!=(2,3) or not np.isfinite(matrix).all():
        raise CandidateExpired('Invalid image registration')
    if (abs(motion.get('angle',0))>.25 or abs(motion.get('scale',1)-1)>.003
            or np.max(abs(matrix[:,:2]-np.eye(2)))>.006):
        raise CandidateExpired('Scale or rotation changed; recompute candidates')
    return matrix[:,2].copy()


def verify_result(candidate,actual,rules):
    from color_family import family_priority, family_fields
    from vision import rgb
    if len(actual)!=3 or any(r['enabled'] and actual[i] is None for i,r in enumerate(rules)):
        raise RuntimeError('Game HEX could not be read reliably')
    deltas=[error(actual[i],r['colors'],False) if r['enabled'] else None for i,r in enumerate(rules)]
    prediction_errors=[error(actual[i],[candidate['colors'][i]],False)
                       if r['enabled'] and candidate['colors'][i] is not None else None
                       for i,r in enumerate(rules)]
    values=[v for v in deltas if v is not None]
    exact_regions=[i for i,r in enumerate(rules) if r['enabled'] and r.get('exact')]
    exact_matches=sum(actual[i].upper() in [c.upper() for c in rules[i]['colors']] for i in exact_regions)
    family=family_priority([[rgb(actual[i])] if r['enabled'] else None for i,r in enumerate(rules)],rules)
    return dict(candidate_id=candidate['id'],predicted_colors=candidate['colors'],
                predicted_deltas=candidate['deltas'],actual_colors=actual,actual_deltas=deltas,
                prediction_errors=prediction_errors,maximum=max(values),average=float(np.mean(values)),
                accepted=accepted(actual,rules),verified=True,**family_fields(*family,0),
                exact_matches=exact_matches,exact_total=len(exact_regions),
                exact_maximum=max((deltas[i] for i in exact_regions),default=0.),
                exact_average=float(np.mean([deltas[i] for i in exact_regions])) if exact_regions else 0.)


def _refresh_prediction(adapter,candidate,actual,rules,emit):
    rescore=getattr(adapter,'rescore',None)
    if not callable(rescore):return candidate
    proposal_colors=deepcopy(candidate['colors'])
    failure=None
    try:
        refreshed=rescore(actual,candidate,rules)
    except Exception as exc:
        if exc.__class__.__name__ in ('Interrupted','InterruptedError'):
            raise
        # Atlas diagnostics must not discard a successful two-frame game HEX
        # observation. Missing predictions remain explicitly unavailable.
        refreshed=None;failure=str(exc)
    adapter.check()
    if refreshed is None:
        candidate=dict(candidate,colors=[None]*3,deltas=[None]*3,
                       accepted=False,prediction_pose=None,
                       prediction_pose_source=('rescore_failed' if failure else 'unsupported_measured_pose'))
    else:candidate=refreshed
    emit('atlas_prediction_updated',dict(candidate_id=candidate['id'],
         candidate=candidate if refreshed is not None else None,
         proposal_colors=proposal_colors,colors=candidate['colors'],
         deltas=candidate['deltas'],error=failure,
         prediction_pose_source=candidate.get('prediction_pose_source'),
         measured_pose=actual[:2].tolist()))
    return candidate


def _recover_current_result(adapter, candidate, rules, actual, markers, target,
                            emit, reason, pose_frame=None, stage_budget=None, pose_current=False):
    """Read the colour currently under the picker without sending input.

    A live action can fail after the game has accepted part of the gesture.
    The recovery reads two HEX frames and attempts registration against the
    last known pose. Only a newly registered pose can support a later trial.
    This observation remains incomplete and is never presented as successful
    positioning of the original candidate.
    """
    if candidate is None or not getattr(adapter, 'recovery_enabled', False):
        return None
    def pose_only():
        return dict(candidate_id=candidate['id'],actual_pose=actual[:2].tolist(),
            marker_errors=marker_errors(target,actual,markers).tolist(),
            verified=False,accepted=False,pose_reliable=True,recovered=True,
            positioning_complete=False,recovery_reason=str(reason),
            actual_colors=[None]*3,actual_deltas=[None]*3,
            predicted_colors=[None]*3,predicted_deltas=[None]*3)
    pose_observation=None
    if pose_current and actual is not None and pose_frame is not None:
        pose_observation=pose_only()
        adapter.verified_frame=pose_frame
    try:
        adapter.check()
        if stage_budget is not None:stage_budget.check_observation()
        frame = adapter.capture()
        # Measure first. OCR can exhaust its soft budget, but a registered
        # reference still permits a newly checked return to the checkpoint.
        if actual is not None and pose_frame is not None:
            registration=adapter.motion(pose_frame,frame)
            emit('atlas_registration',dict(phase='recovery',step=0,
                passed=registration is not None,
                diagnostics=deepcopy(getattr(adapter,'last_motion_diagnostics',None))))
            if registration is not None:
                actual=homogeneous(registration['matrix'])@actual
                pose_frame=frame
                pose_observation=pose_only()
                adapter.verified_frame=frame
        if stage_budget is not None:stage_budget.check_observation()
        first = adapter.read_codes(frame)
        if stage_budget is not None:stage_budget.check_observation()
        adapter.pause(.2)
        if stage_budget is not None:stage_budget.check_observation()
        second_frame = adapter.capture()
        second = adapter.read_codes(second_frame)
        adapter.check()
        if stage_budget is not None:stage_budget.check_observation()
        if any(r['enabled'] and (first[i] is None or second[i] is None or
                                 first[i] != second[i]) for i,r in enumerate(rules)):
            return pose_observation
        # The interrupted route did not reach the proposal. Its colours cannot
        # be used as a prediction of this read-only recovery observation.
        observation=dict(candidate,colors=[None]*3,deltas=[None]*3)
        result = verify_result(observation, second, rules)
        result.update(proposal_colors=deepcopy(candidate['colors']),
                      prediction_pose_source='unverified_recovery_pose')
        # Recover the actual response, including partial or delayed gestures.
        # The requested transform is never evidence of the current pose.
        pose_reliable = False
        if actual is not None and pose_frame is not None:
            # Re-observe from the last registered frame. A failed gesture or
            # transient reading does not invalidate a newly measured pose.
            # Never substitute the requested motion for this measurement.
            registration=adapter.motion(pose_frame,second_frame)
            emit('atlas_registration',dict(phase='recovery',step=0,
                passed=registration is not None,
                diagnostics=deepcopy(getattr(adapter,'last_motion_diagnostics',None))))
            if registration is not None:
                actual=homogeneous(registration['matrix'])@actual
                pose_reliable=True
        pose = actual[:2].tolist() if pose_reliable else None
        errors = (marker_errors(target, actual, markers).tolist()
                  if actual is not None else None)
        # A recovery is a safe observation, not proof that the requested pose
        # was reached.  Keep it available for the UI and manual confirmation.
        observed_accepted=bool(result.get('accepted'))
        result.update(actual_pose=pose, marker_errors=errors, verified=True,
                      # The colour read is reliable, but the requested pose
                      # was not confirmed.  Never let this path count as a
                      # successful automatic candidate.
                      accepted=False, observed_accepted=observed_accepted,
                      pose_reliable=pose_reliable,
                      positioning_complete=False, recovered=True,
                      recovery_reason=str(reason))
        # Keep the event self-contained.  The overlay can therefore render a
        # recovery even when the error happened before a complete positioning
        # result was assembled.
        emit('atlas_recovery', dict(
            candidate_id=candidate['id'], reason=str(reason),
            actual_pose=pose, marker_errors=errors,
            predicted_colors=result.get('predicted_colors', [None] * 3),
            predicted_deltas=result.get('predicted_deltas', [None] * 3),
            actual_colors=result.get('actual_colors', [None] * 3),
            actual_deltas=result.get('actual_deltas', [None] * 3),
            prediction_errors=result.get('prediction_errors', [None] * 3),
            maximum=result.get('maximum'), average=result.get('average'),
            accepted=False, observed_accepted=observed_accepted, verified=True,
            recovered=True, pose_reliable=pose_reliable,
            positioning_complete=False))
        adapter.verified_frame = second_frame
        return result
    except Exception as exc:
        # F9, focus loss, geometry changes and the game deadline are safety
        # interrupts.  Do not convert one that arrives during read-only
        # recovery into an ordinary execution fault.
        if exc.__class__.__name__ in ('Interrupted','InterruptedError'):
            raise
        if isinstance(exc,StageBudgetExceeded) and pose_observation is not None:
            emit('atlas_recovery',dict(pose_observation,reason=str(exc)))
            return pose_observation
        return None


def _adopt_bound_route(replacement,actual,context,max_steps):
    """Lift a route bound at the measured pose into the execution reference.

    Inputs and their local binding stay unchanged. Target and expected poses
    must include all motion already performed in this execution attempt.
    """
    from atlas_bound_route import bound_motion
    bound=bound_motion(replacement,context.board,context.markers,max_steps)
    target=candidate_pose(replacement,context.board)@actual
    bound['expected_poses']=[pose@actual for pose in bound['expected_poses']]
    candidate=dict(replacement,**pose_fields(target,context.board),
        rebound_route=dict(start_pose=actual[:2].tolist(),route=replacement['planned_route']))
    candidate.pop('planned_route',None);candidate.pop('execution_budget',None)
    return candidate,target,bound


def execute_candidate(adapter,batch,batch_id,candidate_id,reference,rules,emit=lambda *args:None,
                      clock=time.monotonic,max_steps=80,reservation='legacy',
                      verified_kind='atlas_verified',stage_budget=None):
    """Adapter: check/context/capture/motion/drag/read_codes/pause/release.

    Reference is the image used to publish this batch, not an old atlas image.
    Once claimed, failures invalidate the batch permanently; never blind retry.
    """
    candidate=None; actual=None; target=None; markers=None; before=None;pose_current=False
    try:
        adapter.check()
        context=adapter.context()
        if reservation=='default':
            candidate=batch.commit_default(batch_id,context,candidate_id)
        elif reservation=='choice':
            candidate=batch.commit_choice(batch_id,candidate_id,context)
        else:
            candidate=batch.claim(batch_id,candidate_id,context)
        target=candidate_pose(candidate,batch.context.board)
        markers=np.asarray(batch.context.markers,float)-np.asarray(batch.context.board[:2])
        bound=None;route_index=0;route_replan=False;route_rebinds=0
        original_target=target.copy();last_rebind_error=None
        if candidate.get('planned_route') is not None:
            from atlas_bound_route import bound_motion
            bound=bound_motion(candidate,batch.context.board,batch.context.markers,max_steps)
        before=adapter.capture()
        registration=_measured_motion(adapter,reference,before,emit,'reference')
        actual=homogeneous(registration['matrix'])
        pose_current=True
        moved=checked_translation(registration)
        if np.linalg.norm(moved)>1:
            raise CandidateExpired('Board moved while choosing; recompute candidates')
        l,t,r,b=batch.context.board
        markers=np.asarray(batch.context.markers,float)-[l,t]
        if np.max(marker_errors(np.eye(3),actual,markers))>1:
            raise CandidateExpired('Board moved while choosing; recompute candidates')
        if bound is not None and np.max(marker_errors(np.eye(3),actual,markers))>.65:
            route_replan=True
        center=np.array([(r-l)/2,(b-t)/2])
        radius=max(1.,float(np.max(np.linalg.norm(markers-markers.mean(axis=0),axis=1))))
        cap=np.array([r-l,b-t])*.16
        if np.any(cap<2):raise ValueError('Board too small')
        last_zoom_direction=0; translation_steps=0;pose_replanned=False;rotation_quantized=False
        linear_move=not np.allclose(target[:2,:2],np.eye(2),atol=1e-6)
        zoom_tick=abs(float(candidate.get('zoom_log_step',np.log(1.01))))
        if not np.isfinite(zoom_tick) or zoom_tick<1e-5:raise ValueError('Invalid wheel scale estimate')
        zoom_ticks={-1:zoom_tick,1:float(candidate.get('zoom_log_step_up',zoom_tick))}
        if any(not np.isfinite(v) or v<1e-5 for v in zoom_ticks.values()):
            raise ValueError('Invalid wheel scale estimate')
        for step in range(max_steps):
            adapter.check()
            if adapter.context()!=batch.context:raise CandidateExpired('Session geometry changed')
            if clock()>=batch.deadline:raise CandidateExpired('Insufficient execution time')
            if (np.max(marker_errors(target,actual,markers))<=POSITION_TOLERANCE and
                    (bound is None or route_index>=len(bound['gestures']))):break
            if stage_budget is not None:stage_budget.check_input()
            residual=target@np.linalg.inv(actual)
            fields=pose_fields(residual,batch.context.board)
            replan=getattr(adapter,'replan',None)
            if bound is not None and (route_replan or route_index>=len(bound['gestures'])):
                # Remaining inputs were tied to a forecast that no longer
                # agrees with the observed pose. Never replay them blindly.
                emit('atlas_route_discarded',dict(candidate_id=candidate['id'],
                     completed=route_index,remaining=len(bound['gestures'])-route_index,
                     actual_pose=actual[:2].tolist()))
                emit('atlas_progress',dict(stage='search'))
                # Small accumulated drift invalidates the old inputs, not
                # necessarily the target. Recompile from the observed pose,
                # rescore that integer endpoint, and keep measuring each step.
                # Never retry a stalled rotation or reverse the wheel to chase
                # an unreachable detent. Allow a longer route to rebind again
                # only after multiple measured actions made fresh progress;
                # a fixed two-correction cap discards healthy long rotations.
                rebind=getattr(adapter,'rebind',None)
                rebound=None
                progress_error=float(np.max(marker_errors(original_target,actual,markers)))
                progressing=(route_index>=2 and last_rebind_error is not None and
                             progress_error<last_rebind_error-.65)
                if callable(rebind) and (route_rebinds<2 or progressing) and not rotation_quantized:
                    route_rebinds+=1
                    proposal=dict(candidate,zoom_log_step=zoom_ticks[-1],zoom_log_step_up=zoom_ticks[1])
                    rebound=rebind(actual,proposal,rules)
                    adapter.check()
                if rebound is not None:
                    from atlas_bound_route import bound_motion
                    fresh=bound_motion(rebound,batch.context.board,batch.context.markers,max_steps-step)
                    reversing=any(g.kind=='wheel' and last_zoom_direction and
                                  np.sign(g.wheel_steps)!=last_zoom_direction for g in fresh['gestures'])
                    if not reversing:
                        original=candidate
                        candidate,target,bound=_adopt_bound_route(rebound,actual,batch.context,max_steps-step)
                        route_index=0;route_replan=False;pose_replanned=True
                        last_rebind_error=progress_error
                        emit('atlas_route_rebound',dict(candidate_id=candidate['id'],
                            correction=route_rebinds,remaining=len(bound['gestures']),
                            actual_pose=actual[:2].tolist(),candidate=candidate,
                            measured_target_error=progress_error,progress_extension=route_rebinds>2))
                        emit('atlas_replanned',dict(candidate_id=candidate['id'],
                            original_colors=original['colors'],candidate=candidate,
                            measured_pose=actual[:2].tolist()))
                        continue
                replacement=replan(actual,candidate,rules) if callable(replan) else None
                adapter.check()
                if replacement is None:
                    raise RuntimeError('No measured-pose fallback after route response changed')
                original=candidate
                if replacement.get('planned_route') is not None:
                    candidate,target,bound=_adopt_bound_route(replacement,actual,batch.context,max_steps-step)
                else:
                    candidate=replacement;target=candidate_pose(candidate,batch.context.board);bound=None
                route_index=0;route_replan=False;pose_replanned=True;rotation_quantized=True
                original_target=target.copy();last_rebind_error=None;route_rebinds=0;translation_steps=0
                emit('atlas_replanned',dict(candidate_id=candidate['id'],
                     original_colors=original['colors'],candidate=candidate,
                     measured_pose=actual[:2].tolist()))
                continue
            angular_ready=rotation_quantized or abs(np.radians(fields['angle']))*radius<=.3
            crossing=(last_zoom_direction and (1 if fields['scale']>1 else -1)!=last_zoom_direction)
            if (bound is None and linear_move and callable(replan) and not pose_replanned and angular_ready and
                    (crossing or abs(np.log(fields['scale']))*radius<=.3)):
                # The measured linear transform is reachable. Search the
                # original atlas at that scale/angle, then translate only.
                emit('atlas_progress',dict(stage='search'))
                replacement=replan(actual,candidate,rules)
                adapter.check()
                if replacement is not None:
                    original=candidate
                    if replacement.get('planned_route') is not None:
                        candidate,target,bound=_adopt_bound_route(replacement,actual,batch.context,max_steps-step)
                    else:
                        candidate=replacement;target=candidate_pose(candidate,batch.context.board)
                    route_index=0;route_replan=False;translation_steps=0
                    original_target=target.copy();last_rebind_error=None;route_rebinds=0
                    pose_replanned=True
                    emit('atlas_replanned',dict(candidate_id=candidate['id'],
                         original_colors=original['colors'],candidate=candidate,
                         measured_pose=actual[:2].tolist()))
                    continue
            gestures=(decompose_gestures(fields,batch.context.board,batch.context.markers)
                      if bound is None else None)
            anchor=None
            if bound is not None:
                gesture=bound['gestures'][route_index]
                kind=gesture.kind
                command=(np.asarray(gesture.translation) if kind=='drag' else
                         gesture.wheel_steps if kind=='wheel' else gesture.requested_angle)
                anchor=gesture.anchor if kind!='drag' else None
            elif not rotation_quantized and abs(np.radians(fields['angle']))*radius>.3:
                kind='rotate'; command=float(np.clip(fields['angle'],-12,12))
                anchor=gestures['rotation_anchor']
            elif abs(np.log(fields['scale']))*radius>.3:
                kind='wheel'; direction=1 if fields['scale']>1 else -1
                zoom_tick=zoom_ticks[direction]
                if last_zoom_direction and direction!=last_zoom_direction:
                    detent=_nearest_detent_translation(target,actual,fields,markers,zoom_tick)
                    if detent is None:
                        raise RuntimeError('Requested scale falls between wheel steps and no detent meets marker tolerance')
                    emit('atlas_scale_detent',dict(step=step+1,
                         residual_log_scale=detent['scale_error'],zoom_log_step=zoom_tick,
                         marker_errors=detent['marker_errors']))
                    kind='drag'
                    remaining=np.array([detent['dx'],detent['dy']])
                    command=np.rint(remaining/max(1,float(np.max(abs(remaining)/cap))))
                    if not np.any(command):break
                    if translation_steps>=10:raise RuntimeError('Translation did not converge')
                    translation_steps+=1
                else:
                    last_zoom_direction=direction
                    # The capture already uses four-notch bursts. Keep that cap,
                    # measure every burst and approach the target one notch at a
                    # time. CaptureGame still checks F9/deadline before EACH tick.
                    command=direction*min(4,max(1,int(abs(np.log(fields['scale']))/zoom_tick+.1)))
                    anchor=gestures['zoom_anchor']
            else:
                kind='drag'; remaining=residual[:2,:2]@center+residual[:2,2]-center
                command=np.rint(remaining/max(1,float(np.max(abs(remaining)/cap))))
                if not np.any(command):break
                if translation_steps>=10:raise RuntimeError('Translation did not converge')
                translation_steps+=1
            if bound is None:
                gesture=planned_gesture(kind,batch.context.board,command,anchor)
            if kind=='rotate' and not gesture.has_effect:
                # No right-button down for a rounded arc with no angular motion.
                # Keep the measured pose and enter the existing atlas replan.
                rotation_quantized=True
                emit('atlas_micro_rotation',dict(step=step+1,command=float(command),
                     marker_pixels=float(abs(np.radians(command))*radius),
                     input_sent=False,gesture=gesture.record()))
                continue
            if kind=='drag':command=np.asarray(gesture.translation)
            elif kind=='wheel':command=gesture.wheel_steps
            if anchor is not None:anchor=gesture.anchor
            emit('atlas_command',dict(step=step+1,action=kind,command=np.asarray(command).tolist(),
                                     anchor=anchor,gesture=gesture.record()))
            if stage_budget is not None:stage_budget.check_input()
            pose_current=False
            adapter.perform_gesture(gesture)
            adapter.pause(.15)
            after=adapter.capture()
            registration=_measured_motion(adapter,before,after,emit,'positioning',step+1)
            measured=homogeneous(registration['matrix'])
            # Registration establishes the observed pose independently of
            # whether the game followed the requested gesture. Retain it
            # before response checks can fail or exhaust the recovery budget.
            actual=measured@actual;before=after;pose_current=True
            response=pose_fields(measured,batch.context.board)
            if kind=='drag':
                shift=checked_translation(registration)
                if np.linalg.norm(shift)<.2:raise RuntimeError('Drag produced no measurable motion')
                if np.dot(shift,command)<=0 or np.linalg.norm(shift)>np.linalg.norm(command)*2+2:
                    raise RuntimeError('Unexpected image displacement')
            else:
                anchor=np.array(gesture.anchor)-[l,t]
                if np.linalg.norm(measured[:2,:2]@anchor+measured[:2,2]-anchor)>3:
                    raise RuntimeError('Gesture pivot moved unexpectedly')
                if kind=='rotate':
                    stalled = (response['angle']*command<=0 or abs(response['angle'])<.025 or
                               abs(response['angle'])>abs(command)*2+.3 or abs(response['scale']-1)>.003)
                    if stalled:
                        # A final arc can be smaller than one screen pixel after
                        # integer coordinate rounding. Accept only this bounded
                        # identity measurement for replanning; larger stalled
                        # rotations remain failures.
                        marker_pixels=abs(np.radians(command))*radius
                        identity=(abs(response['angle'])<.025 and
                                  abs(response['scale']-1)<=.003)
                        if not (identity and (marker_pixels<=MICRO_ROTATION_PIXELS or
                                             (bound is not None and callable(replan)))):
                            raise RuntimeError('Unexpected or stalled rotation')
                        # Do not replace a measured identity with a requested
                        # rotation. The live replan uses the actual angle.
                        rotation_quantized=True
                        emit('atlas_micro_rotation',dict(step=step+1,command=float(command),
                                                         marker_pixels=float(marker_pixels)))
                elif (np.log(response['scale'])*command<=0 or abs(response['scale']-1)<.0005 or
                        abs(response['angle'])>.25 or abs(np.log(response['scale']))>abs(command)*.15):
                    # A wheel burst can reach the game's native zoom stop.
                    # Give the final frame one longer, read-only observation
                    # before treating it as a failed input.  If it remains
                    # identical, the recovery path records the current colour
                    # instead of raising a user-facing workflow error.
                    if (abs(response['angle']) <= .25 and
                            abs(response['scale']-1) < .0005):
                        adapter.pause(.35)
                        retry_after=adapter.capture()
                        pose_current=False
                        retry_registration=_measured_motion(adapter,after,retry_after,
                                                           emit,'positioning_recheck',step+1)
                        retry_measured=homogeneous(retry_registration['matrix'])
                        actual=retry_measured@actual;before=retry_after;pose_current=True
                        retry_response=pose_fields(retry_measured,batch.context.board)
                        if (abs(retry_response['angle']) <= .25 and
                                abs(retry_response['scale']-1) < .0005):
                            raise RuntimeError('Unexpected or stalled wheel response (native zoom limit)')
                        measured=retry_measured@measured
                        response=pose_fields(measured,batch.context.board)
                        after=retry_after
                    else:
                        raise RuntimeError('Unexpected or stalled wheel response')
                if kind=='wheel':
                    zoom_tick=abs(np.log(response['scale'])/command)
                    zoom_ticks[1 if command>0 else -1]=zoom_tick
                    last_zoom_direction=1 if command>0 else -1
            route_errors=None
            if bound is not None:
                route_errors=marker_errors(bound['expected_poses'][route_index],actual,markers)
                route_index+=1
                # Existing positioning tolerance, not the .09 px error seen
                # in one probe and not a universal response confidence bound.
                route_replan=bool(np.max(route_errors)>.65 or rotation_quantized)
            emit('atlas_positioning',dict(step=step+1,action=kind,command=np.asarray(command).tolist(),
                 gesture=gesture.record(),
                 measured=measured[:2].tolist(),actual_pose=actual[:2].tolist(),
                 bound_route_marker_errors=route_errors.tolist() if route_errors is not None else None,
                 marker_errors=marker_errors(target,actual,markers).tolist()))
        errors=marker_errors(target,actual,markers)
        if np.max(errors)>POSITION_TOLERANCE:raise RuntimeError('Positioning did not converge at all three markers')
        adapter.check()
        if clock()>=batch.deadline:raise CandidateExpired('No time for HEX verification')
        emit('atlas_progress',dict(stage='verify'))
        if stage_budget is not None:stage_budget.check_observation()
        first=adapter.read_codes(before)
        if stage_budget is not None:stage_budget.check_observation()
        adapter.pause(.2)
        if stage_budget is not None:stage_budget.check_observation()
        verified_frame=adapter.capture()
        second=adapter.read_codes(verified_frame)
        adapter.check()
        if clock()>=batch.deadline:raise CandidateExpired('HEX verification exceeded the deadline')
        if any(r['enabled'] and first[i]!=second[i] for i,r in enumerate(rules)):
            raise RuntimeError('Game HEX changed between verification frames')
        pose_current=False
        final_motion=_measured_motion(adapter,before,verified_frame,emit,'hex_verification')
        previous_actual=actual
        actual=homogeneous(final_motion['matrix'])@actual
        before=verified_frame;pose_current=True
        checked_translation(final_motion)
        if np.max(marker_errors(previous_actual,actual,markers))>POSITION_TOLERANCE:
            raise CandidateExpired('Board moved during HEX verification')
        errors=marker_errors(target,actual,markers)
        if np.max(errors)>POSITION_TOLERANCE:raise CandidateExpired('Marker alignment changed during verification')
        adapter.check()
        if clock()>=batch.deadline:raise CandidateExpired('HEX verification exceeded the deadline')
        # The controller accepts a small alignment residual and may replan at
        # a measured detent. Neither case preserves the old predicted colours.
        # Resample at the final registered pose, independently of game HEX.
        candidate=_refresh_prediction(adapter,candidate,actual,rules,emit)
        if stage_budget is not None:stage_budget.check_observation()
        if clock()>=batch.deadline:raise CandidateExpired('HEX verification exceeded the deadline')
        result=verify_result(candidate,second,rules)
        result.update(actual_pose=actual[:2].tolist(),marker_errors=errors.tolist(),
                      replanned=pose_replanned,predicted_accepted=bool(candidate.get('accepted')),
                      prediction_pose_source=candidate.get('prediction_pose_source','proposal'),
                      prediction_pose=candidate.get('prediction_pose'))
        adapter.verified_frame=verified_frame
        if reservation=='choice':
            batch.actual_pose=actual@homogeneous(batch.actual_pose)
        else:batch.actual_pose=actual
        if verified_kind:emit(verified_kind,result)
        return result
    except Exception as exc:
        # User/window/countdown interrupts must never trigger recovery reads.
        if exc.__class__.__name__ in ('Interrupted','InterruptedError'):
            batch.invalidate()
            raise
        # Before the first successful registration, the acquisition/choice
        # reference itself is the known identity pose. Recovery can measure
        # from it again; an unsuccessful first read need not end the session.
        recovery_actual=np.eye(3) if actual is None and candidate is not None else actual
        recovery_frame=reference if actual is None else before
        recovered=_recover_current_result(adapter,candidate,rules,recovery_actual,markers,target,
            emit,exc,pose_frame=recovery_frame,stage_budget=stage_budget,pose_current=pose_current)
        if recovered is not None:
            return recovered
        batch.invalidate()
        raise
    finally:
        adapter.release()
