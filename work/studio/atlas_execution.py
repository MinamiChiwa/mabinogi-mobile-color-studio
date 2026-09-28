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


# Below this screen-space marker displacement, integer mouse coordinates cannot
# provide a reliable feature-registration measurement.
MICRO_ROTATION_PIXELS = 3.0


class CandidateExpired(RuntimeError):
    pass


def _nearest_detent_translation(target,actual,fields,markers,zoom_tick):
    """Return a center drag if the nearest wheel detent is safely close.

    Atlas scale levels are estimated from capture measurements, while live
    wheel detents can differ slightly. If one click has crossed the continuous
    target, accept the nearer detent only when it is within half a measured
    click and a center translation can still put all markers within 1 pixel.
    Final game HEX verification remains mandatory.
    """
    scale_error=abs(float(np.log(fields['scale'])))
    if not np.isfinite(scale_error) or scale_error>float(zoom_tick)*.55:
        return None
    center_drag=homogeneous([[1,0,fields['dx']],[0,1,fields['dy']]])
    errors=marker_errors(target,center_drag@actual,markers)
    if not np.isfinite(errors).all() or float(np.max(errors))>1.:
        return None
    return dict(dx=float(fields['dx']),dy=float(fields['dy']),
                scale_error=scale_error,marker_errors=errors.tolist())


def _measured_motion(adapter, before, after, emit, phase, step=0):
    registration = adapter.motion(before, after)
    diagnostics = deepcopy(getattr(adapter, 'last_motion_diagnostics', None))
    emit('atlas_registration', dict(phase=phase, step=step,
                                   passed=registration is not None, diagnostics=diagnostics))
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
    translation_steps=0
    last_zoom_direction=0
    if not np.isfinite(zoom_tick) or zoom_tick<1e-5:
        zoom_tick=float(np.log(1.01))

    for step in range(max_steps+1):
        errors=marker_errors(target,actual,local_markers)
        if float(np.max(errors))<=.65:
            return dict(steps=step,actions=actions,reachable=True)
        if step>=max_steps:
            break
        residual=target@np.linalg.inv(actual)
        fields=pose_fields(residual,board)
        gestures=decompose_gestures(fields,board,markers)
        anchor=None
        if abs(np.radians(fields['angle']))*radius>.3:
            kind='rotate'
            command=float(np.clip(fields['angle'],-12,12))
            theta=np.radians(command)
            scale=1.
            anchor=np.asarray(gestures['rotation_anchor'],float)-[l,t]
        elif abs(np.log(fields['scale']))*radius>.3:
            kind='wheel'
            direction=1 if fields['scale']>1 else -1
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
                actions[kind]+=1
                actual=homogeneous(np.column_stack((np.eye(2),command)))@actual
                continue
            last_zoom_direction=direction
            command=direction*min(4,max(1,int(abs(np.log(fields['scale']))/zoom_tick+.1)))
            theta=0.
            scale=np.exp(command*zoom_tick)
            anchor=np.asarray(gestures['zoom_anchor'],float)-[l,t]
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
    plan=_estimate_candidate_motion(candidate,board,markers,max_steps)
    actions=plan['actions'];steps=plan['steps']
    if step_seconds is None:
        movement=(actions['rotate']*1.2+actions['wheel']*.5+
                  actions['drag']*1.05)
    else:
        movement=steps*float(step_seconds)
    needed=movement+float(verify_seconds)+float(safety_seconds)
    remaining=float(deadline-now)
    allowed=plan['reachable'] and steps<=max_steps and remaining>=needed
    if allowed:reason='ok'
    elif not plan['reachable']:reason=plan.get('reason','unreachable')
    else:reason='insufficient_time'
    return dict(allowed=allowed,reason=reason,steps=steps,actions=actions,
                needed=needed,remaining=remaining)


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
    if len(actual)!=3 or any(r['enabled'] and actual[i] is None for i,r in enumerate(rules)):
        raise RuntimeError('Game HEX could not be read reliably')
    deltas=[error(actual[i],r['colors'],False) if r['enabled'] else None for i,r in enumerate(rules)]
    prediction_errors=[error(actual[i],[candidate['colors'][i]],False) if r['enabled'] else None for i,r in enumerate(rules)]
    values=[v for v in deltas if v is not None]
    exact_regions=[i for i,r in enumerate(rules) if r['enabled'] and r.get('exact')]
    exact_matches=sum(actual[i].upper() in [c.upper() for c in rules[i]['colors']] for i in exact_regions)
    return dict(candidate_id=candidate['id'],predicted_colors=candidate['colors'],
                predicted_deltas=candidate['deltas'],actual_colors=actual,actual_deltas=deltas,
                prediction_errors=prediction_errors,maximum=max(values),average=float(np.mean(values)),
                accepted=accepted(actual,rules),verified=True,
                exact_matches=exact_matches,exact_total=len(exact_regions))


def _recover_current_result(adapter, candidate, rules, actual, markers, target,
                            emit, reason):
    """Read the colour currently under the picker without sending input.

    A live action can fail after the game has accepted part of the gesture.
    Retrying from an unverified pose is unsafe, so the recovery path only
    captures and performs the existing two-frame HEX check.  The result is
    deliberately marked incomplete; callers may display it and offer a new
    candidate, but it can never be presented as a successful positioning.
    """
    if candidate is None or not getattr(adapter, 'recovery_enabled', False):
        return None
    try:
        adapter.check()
        frame = adapter.capture()
        first = adapter.read_codes(frame)
        adapter.pause(.2)
        second_frame = adapter.capture()
        second = adapter.read_codes(second_frame)
        adapter.check()
        if any(r['enabled'] and (first[i] is None or second[i] is None or
                                 first[i] != second[i]) for i,r in enumerate(rules)):
            return None
        result = verify_result(candidate, second, rules)
        # A repeated frame after a wheel command is a known, bounded native
        # zoom stop.  The pose accumulated before that command remains valid,
        # so the service may safely rebase one of the other measured
        # candidates from it.  Other failures leave the pose untrusted.
        pose_reliable = actual is not None and 'native zoom limit' in str(reason).lower()
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
        return None


def execute_candidate(adapter,batch,batch_id,candidate_id,reference,rules,emit=lambda *args:None,
                      clock=time.monotonic,max_steps=80,reservation='legacy',
                      verified_kind='atlas_verified'):
    """Adapter: check/context/capture/motion/drag/read_codes/pause/release.

    Reference is the image used to publish this batch, not an old atlas image.
    Once claimed, failures invalidate the batch permanently; never blind retry.
    """
    candidate=None; actual=None; target=None; markers=None
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
        before=adapter.capture()
        registration=_measured_motion(adapter,reference,before,emit,'reference')
        moved=checked_translation(registration)
        if np.linalg.norm(moved)>1:
            raise CandidateExpired('Board moved while choosing; recompute candidates')
        actual=homogeneous(registration['matrix'])
        l,t,r,b=batch.context.board
        markers=np.asarray(batch.context.markers,float)-[l,t]
        if np.max(marker_errors(np.eye(3),actual,markers))>1:
            raise CandidateExpired('Board moved while choosing; recompute candidates')
        center=np.array([(r-l)/2,(b-t)/2])
        radius=max(1.,float(np.max(np.linalg.norm(markers-markers.mean(axis=0),axis=1))))
        cap=np.array([r-l,b-t])*.16
        if np.any(cap<2):raise ValueError('Board too small')
        last_zoom_direction=0; translation_steps=0
        zoom_tick=abs(float(candidate.get('zoom_log_step',np.log(1.01))))
        if not np.isfinite(zoom_tick) or zoom_tick<1e-5:raise ValueError('Invalid wheel scale estimate')
        for step in range(max_steps):
            adapter.check()
            if adapter.context()!=batch.context:raise CandidateExpired('Session geometry changed')
            if clock()>=batch.deadline:raise CandidateExpired('Insufficient execution time')
            if np.max(marker_errors(target,actual,markers))<=.65:break
            residual=target@np.linalg.inv(actual)
            fields=pose_fields(residual,batch.context.board)
            gestures=decompose_gestures(fields,batch.context.board,batch.context.markers)
            anchor=None
            if abs(np.radians(fields['angle']))*radius>.3:
                kind='rotate'; command=float(np.clip(fields['angle'],-12,12))
                anchor=gestures['rotation_anchor']
            elif abs(np.log(fields['scale']))*radius>.3:
                kind='wheel'; direction=1 if fields['scale']>1 else -1
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
            emit('atlas_command',dict(step=step+1,action=kind,command=np.asarray(command).tolist(),
                                     anchor=None if anchor is None else np.asarray(anchor).tolist()))
            if kind=='drag':adapter.drag(*command)
            elif kind=='rotate':adapter.rotate(command,anchor)
            else:adapter.wheel(command,anchor)
            adapter.pause(.15)
            after=adapter.capture()
            registration=_measured_motion(adapter,before,after,emit,'positioning',step+1)
            measured=homogeneous(registration['matrix'])
            response=pose_fields(measured,batch.context.board)
            if kind=='drag':
                shift=checked_translation(registration)
                if np.linalg.norm(shift)<.2:raise RuntimeError('Drag produced no measurable motion')
                if np.dot(shift,command)<=0 or np.linalg.norm(shift)>np.linalg.norm(command)*2+2:
                    raise RuntimeError('Unexpected image displacement')
            else:
                anchor=np.array(gestures['rotation_anchor' if kind=='rotate' else 'zoom_anchor'])-[l,t]
                if np.linalg.norm(measured[:2,:2]@anchor+measured[:2,2]-anchor)>3:
                    raise RuntimeError('Gesture pivot moved unexpectedly')
                if kind=='rotate':
                    stalled = (response['angle']*command<=0 or abs(response['angle'])<.025 or
                               abs(response['angle'])>abs(command)*2+.3 or abs(response['scale']-1)>.003)
                    if stalled:
                        # A final arc can be smaller than one screen pixel after
                        # integer coordinate rounding. Accept only this bounded
                        # identity measurement and carry the commanded pose
                        # forward; larger stalled rotations remain failures.
                        marker_pixels=abs(np.radians(command))*radius
                        identity=(abs(response['angle'])<.025 and
                                  abs(response['scale']-1)<=.003)
                        if not (identity and marker_pixels<=MICRO_ROTATION_PIXELS):
                            raise RuntimeError('Unexpected or stalled rotation')
                        theta=np.radians(command)
                        pivot=np.asarray(gestures['rotation_anchor'],float)-[l,t]
                        matrix=np.array([[np.cos(theta),-np.sin(theta)],
                                         [np.sin(theta),np.cos(theta)]])
                        measured=homogeneous(np.column_stack((matrix,pivot-matrix@pivot)))
                        response=pose_fields(measured,batch.context.board)
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
                        retry_registration=_measured_motion(adapter,after,retry_after,
                                                           emit,'positioning_recheck',step+1)
                        retry_measured=homogeneous(retry_registration['matrix'])
                        retry_response=pose_fields(retry_measured,batch.context.board)
                        if (abs(retry_response['angle']) <= .25 and
                                abs(retry_response['scale']-1) < .0005):
                            raise RuntimeError('Unexpected or stalled wheel response (native zoom limit)')
                        measured=retry_measured
                        response=retry_response
                    else:
                        raise RuntimeError('Unexpected or stalled wheel response')
                if kind=='wheel':zoom_tick=abs(np.log(response['scale'])/command)
            actual=measured@actual;before=after
            emit('atlas_positioning',dict(step=step+1,action=kind,command=np.asarray(command).tolist(),
                 measured=measured[:2].tolist(),actual_pose=actual[:2].tolist(),
                 marker_errors=marker_errors(target,actual,markers).tolist()))
        errors=marker_errors(target,actual,markers)
        if np.max(errors)>1:raise RuntimeError('Positioning did not converge at all three markers')
        adapter.check()
        if clock()>=batch.deadline:raise CandidateExpired('No time for HEX verification')
        emit('atlas_progress',dict(stage='verify'))
        first=adapter.read_codes(before)
        adapter.pause(.2)
        verified_frame=adapter.capture()
        second=adapter.read_codes(verified_frame)
        adapter.check()
        if clock()>=batch.deadline:raise CandidateExpired('HEX verification exceeded the deadline')
        if any(r['enabled'] and first[i]!=second[i] for i,r in enumerate(rules)):
            raise RuntimeError('Game HEX changed between verification frames')
        final_motion=_measured_motion(adapter,before,verified_frame,emit,'hex_verification')
        checked_translation(final_motion)
        final_pose=homogeneous(final_motion['matrix'])@actual
        if np.max(marker_errors(actual,final_pose,markers))>1:
            raise CandidateExpired('Board moved during HEX verification')
        actual=final_pose;errors=marker_errors(target,actual,markers)
        if np.max(errors)>1:raise CandidateExpired('Marker alignment changed during verification')
        adapter.check()
        if clock()>=batch.deadline:raise CandidateExpired('HEX verification exceeded the deadline')
        result=verify_result(candidate,second,rules)
        result.update(actual_pose=actual[:2].tolist(),marker_errors=errors.tolist())
        adapter.verified_frame=verified_frame
        if reservation=='choice':
            batch.actual_pose=actual@homogeneous(batch.actual_pose)
        else:batch.actual_pose=actual
        if verified_kind:emit(verified_kind,result)
        return result
    except Exception as exc:
        recovered=_recover_current_result(adapter,candidate,rules,actual,markers,target,emit,exc)
        if recovered is not None:
            return recovered
        batch.invalidate()
        raise
    finally:
        adapter.release()
