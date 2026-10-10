"""Offline-only prototype: bounded pattern search using verified game HEX.

No live adapter is wired here. The injected adapter must implement guarded
check/context/marker_points/capture/motion/nudge/read_codes/pause/release.
``marker_points`` returns three points in the motion matrix's coordinate frame.
``nudge`` requests
a displacement; only registered images establish actual position. A future
live adapter needs independent subpixel and return-to-pose validation.
"""
from dataclasses import dataclass
import math
import time
import numpy as np
from atlas_execution import checked_translation
from vision import accepted, error, normalize_hex


@dataclass(frozen=True)
class RefinementLimits:
    steps: tuple = (.25, .125)
    max_trials: int = 12
    max_seek_moves: int = 6
    max_command: float = .5
    max_radius: float = 2.
    pose_tolerance: float = .035
    minimum_motion: float = .005
    trial_seconds: float = 5.
    return_seconds: float = 3.
    verify_seconds: float = 4.

    def __post_init__(self):
        numeric=(self.max_command,self.max_radius,self.pose_tolerance,self.minimum_motion,
                 self.trial_seconds,self.return_seconds,self.verify_seconds,*self.steps)
        if not self.steps or any(not math.isfinite(v) or v<=0 for v in numeric):
            raise ValueError('Refinement limits must be finite and positive')
        if self.max_trials<1 or self.max_seek_moves<1:
            raise ValueError('Refinement needs positive bounded trial and move counts')


def refinement_translation(motion,points,tolerance):
    """Reject affine drift that a broad scale threshold hides at the markers.

    A small matrix coefficient can still move separated markers differently.
    The explicit points must use the same coordinate frame as the matrix.
    """
    checked_translation(motion)
    matrix=np.asarray(motion['matrix'],float)
    displacements=np.asarray(points)@(matrix[:,:2]-np.eye(2)).T+matrix[:,2]
    mean=displacements.mean(axis=0)
    if np.max(np.linalg.norm(displacements-mean,axis=1))>tolerance:
        raise RuntimeError('Affine drift exceeds the three-marker translation tolerance')
    return mean


def score_codes(codes, rules):
    """Rank all enabled regions, retaining exact/tolerance acceptance rules."""
    if len(rules)!=3 or len(codes)!=3 or not any(r['enabled'] for r in rules):
        raise ValueError('Exactly three rules and at least one enabled region are required')
    actual=[];deltas=[];normalized=[];violations=[]
    for code,rule in zip(codes,rules):
        if not rule['enabled']:
            actual.append(code);deltas.append(None);continue
        if code is None:raise ValueError('Game HEX could not be read reliably')
        color=normalize_hex(code);targets=rule['colors']
        if not targets:raise ValueError('Enabled region has no target')
        delta=error(color,targets,False)
        exact=bool(rule['exact']);tolerance=0. if exact else float(rule['tolerance'])
        if not math.isfinite(tolerance) or tolerance<0:raise ValueError('Invalid tolerance')
        distance=error(color,targets,exact)
        # Exact channels use channel-distance only for ranking; zero remains
        # the sole acceptance threshold, including very dark colors.
        normalized.append(distance/max(tolerance,1. if exact else .001))
        violations.append(distance>tolerance)
        actual.append(color);deltas.append(delta)
    ok=accepted(actual,rules)
    from region_priority import priority_components
    ordered=priority_components(actual,rules,deltas)
    rank=(not ok,*(ordered or ()),max(normalized),sum(violations),float(np.mean(normalized)))
    target_exact=all(not r['enabled'] or error(actual[i],r['colors'],True)==0
                     for i,r in enumerate(rules))
    return dict(colors=actual,deltas=deltas,accepted=ok,target_exact=target_exact,rank=rank)


def refine_hex(adapter, rules, deadline, *, clock=time.monotonic, limits=None):
    """Explore a small measured neighborhood, then return and reverify best.

    Guard/OCR/registration failure stops immediately without a blind return.
    A failed or unverified return never claims the best historical pose is
    current. Timing estimates are offline assumptions, not measured live costs.
    """
    limits=limits or RefinementLimits()
    if not math.isfinite(deadline):raise ValueError('Deadline must be finite')
    trials=0;moves=0;history=[];best=None;current=None;context=None;reference=None
    last_known_pose=None;reason='not_started';failure=None;points=None

    def guard():
        adapter.check()
        if clock()>=deadline:raise RuntimeError('Refinement deadline expired')
        if context is not None and adapter.context()!=context:
            raise RuntimeError('Session geometry changed')

    def pose_of(frame):
        position=refinement_translation(adapter.motion(reference,frame),points,limits.pose_tolerance)
        if np.max(abs(position))>limits.max_radius+limits.pose_tolerance:
            raise RuntimeError('Measured motion left the local search radius')
        return position

    def observe():
        nonlocal current,last_known_pose
        current=None
        guard();a=adapter.capture();guard();p=pose_of(a)
        first=adapter.read_codes(a);guard()
        adapter.pause(.2);guard();b=adapter.capture();guard();q=pose_of(b)
        if np.max(abs(q-p))>limits.pose_tolerance:
            raise RuntimeError('Board moved during HEX verification')
        second=adapter.read_codes(b);guard()
        if len(first)!=3 or len(second)!=3:
            raise RuntimeError('Three game HEX readings are required')
        if any(rule['enabled'] and first[i]!=second[i] for i,rule in enumerate(rules)):
            raise RuntimeError('Game HEX changed between verification frames')
        scored=score_codes(second,rules)
        last_known_pose=q
        current=dict(pose=q.tolist(),**scored)
        history.append(current)
        return current

    def seek(target):
        nonlocal current,last_known_pose,moves
        target=np.asarray(target,float)
        if np.max(abs(target))>limits.max_radius:raise RuntimeError('Target outside local search radius')
        for _ in range(limits.max_seek_moves):
            guard();before=adapter.capture();guard();p=pose_of(before)
            remaining=target-p
            if np.max(abs(remaining))<=limits.pose_tolerance:
                last_known_pose=p;return
            command=remaining/max(1.,float(np.max(abs(remaining)))/limits.max_command)
            guard();current=None;moves+=1
            adapter.nudge(*command);guard()
            after=adapter.capture();guard()
            measured=refinement_translation(adapter.motion(before,after),points,limits.pose_tolerance);q=pose_of(after)
            last_known_pose=q
            if np.linalg.norm(measured)<limits.minimum_motion:
                raise RuntimeError('Nudge produced no measurable motion')
            if (np.dot(measured,command)<=0 or
                    np.linalg.norm(measured)>np.linalg.norm(command)*2+limits.pose_tolerance):
                raise RuntimeError('Unexpected measured displacement')
            if np.max(abs((q-p)-measured))>limits.pose_tolerance:
                raise RuntimeError('Local and reference registration disagree')
            if np.max(abs(target-q))<=limits.pose_tolerance:return
        raise RuntimeError('Measured positioning did not converge')

    def same_pose(a,b):
        return a is not None and b is not None and np.max(abs(np.array(a['pose'])-b['pose']))<=limits.pose_tolerance

    try:
        # Validate rules before any movement.
        score_codes([r['colors'][0] if r['enabled'] and r.get('colors') else None for r in rules],rules)
        guard();context=adapter.context();points=np.asarray(adapter.marker_points(),float)
        if points.shape!=(3,2) or not np.isfinite(points).all():
            raise ValueError('Three finite marker points in motion coordinates are required')
        reference=adapter.capture();guard()
        best=observe()
        if best['target_exact']:reason='already_exact'
        else:
            reason='trial_limit'
            for step in limits.steps:
                improved=True
                while improved and trials<limits.max_trials and not best['target_exact']:
                    improved=False
                    for direction in ((1,0),(-1,0),(0,1),(0,-1)):
                        if trials>=limits.max_trials:break
                        guard()
                        reserve=limits.trial_seconds+limits.return_seconds+limits.verify_seconds
                        if deadline-clock()<reserve:
                            reason='return_reserve';break
                        target=np.array(best['pose'])+step*np.array(direction)
                        if np.max(abs(target))>limits.max_radius:continue
                        if any(np.max(abs(target-np.array(h['pose'])))<=limits.pose_tolerance for h in history):continue
                        trials+=1;seek(target);sample=observe()
                        if sample['rank']<best['rank']:
                            best=sample;improved=True
                            if best['target_exact']:reason='target_exact';break
                    if reason=='return_reserve':break
                if reason=='return_reserve' or best['target_exact']:break
            if not best['target_exact'] and trials<limits.max_trials and reason!='return_reserve':
                reason='neighborhood_exhausted'
            if not same_pose(current,best):
                guard()
                if deadline-clock()<limits.return_seconds+limits.verify_seconds:
                    raise RuntimeError('Insufficient time to restore and verify best pose')
                seek(best['pose']);restored=observe()
                if any(r['enabled'] and restored['colors'][i]!=best['colors'][i] for i,r in enumerate(rules)):
                    raise RuntimeError('Restored pose did not reproduce best HEX')
        guard()
    except Exception as exc:
        reason='stopped';failure=str(exc);current=None
    finally:
        adapter.release()
    return dict(reason=reason,error=failure,trials=trials,moves=moves,history=history,
                best_observed=best,current=current,current_verified=current is not None,
                kept_best=bool(same_pose(current,best) and current['colors']==best['colors']) if current is not None else False,
                accepted=bool(current and current['accepted']),
                last_measured_pose=None if last_known_pose is None else last_known_pose.tolist(),
                live_validated=False)
