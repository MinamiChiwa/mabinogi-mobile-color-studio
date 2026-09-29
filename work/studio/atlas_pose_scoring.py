"""Resample a concrete final pose without reusing a proposal's colour scores.

Geometry/input reachability and colour acceptance are separate. Callers must
provide the provenance of the pose; this module never certifies game response.
"""
from copy import deepcopy
import numpy as np
from atlas_pose import homogeneous, pose_fields
from atlas_similarity import _distances
from candidate_ranking import exact_priority, exact_fields
from color_family import family_penalties, family_priority, family_fields


def score_pose(atlas, capture_offset, pose, markers, board, rules, *,
               screen_offsets=((0.,0.),), check=lambda:None):
    """Score centre and explicitly supplied screen-space uncertainty samples.

    pose maps the acquisition reference to the proposed screen. Offsets are
    supplied by the caller's response evidence, not an invented error bound.
    Unsupported centre samples reject the candidate; missing neighbourhood
    samples remain an explicit uncertainty, never a zero-error fallback.
    """
    transform=homogeneous(pose)
    points=np.asarray(markers,float)-np.asarray(board[:2],float)
    offsets=np.asarray(screen_offsets,float)
    capture_offset=np.asarray(capture_offset,float)
    if (points.shape!=(3,2) or capture_offset.shape!=(2,) or
            offsets.ndim!=2 or offsets.shape[1]!=2 or not len(offsets) or
            not np.isfinite(np.r_[points.ravel(),offsets.ravel(),capture_offset]).all() or
            not np.array_equal(offsets[0],[0,0]) or len(rules)!=3):
        raise ValueError('Invalid pose sampling geometry')
    enabled=[i for i,r in enumerate(rules) if r.get('enabled')]
    if not enabled:return None
    inverse=np.linalg.inv(transform[:2,:2])
    colors=[None]*3;distances=[None]*3
    sample_family_losses=[None]*3
    supported=np.ones(len(offsets),bool);passed=supported.copy()
    for region in enabled:
        check()
        source=(points[region]+offsets-transform[:2,2])@inverse.T
        values,valid=atlas.sample(region,source,capture_offset)
        values=np.rint(values).clip(0,255).astype(np.uint8)
        loss,accepted=_distances(values,rules[region])
        colors[region]=values;distances[region]=loss
        sample_family_losses[region]=family_penalties(values,rules[region])
        supported &= valid;passed &= valid & accepted
    if not supported[0]:return None
    maximum=np.maximum.reduce([distances[i] for i in enabled])
    average=np.mean([distances[i] for i in enabled],axis=0)
    hits,exact_max,exact_average,exact_total=exact_priority(colors,distances,rules)
    family_max,family_avg,family_losses=family_priority(colors,rules)
    result=dict(predicted=True,verified=False,execution_verified=False,
                colors=['#%02X%02X%02X'%tuple(colors[i][0]) if i in enabled else None for i in range(3)],
                deltas=[float(distances[i][0]) if i in enabled else None for i in range(3)],
                maximum=float(maximum[0]),average=float(average[0]),accepted=bool(passed[0]),
                **exact_fields(hits,exact_max,exact_average,exact_total,0))
    result.update(family_fields(family_max,family_avg,family_losses,0))
    # A compromise may be outside the user's configured Delta-E tolerance and
    # still be a safe landing when its small landing neighbourhood remains in
    # the same colour family. Keep this separate from ``accepted`` so the
    # stable-route gate does not discard every usable compromise.
    sample_family_max=np.maximum.reduce([sample_family_losses[i] for i in enabled])
    sample_family_ok=supported & (sample_family_max<=1e-7)
    result['pose_samples']=dict(offsets=offsets.tolist(),supported=supported.tolist(),
        accepted=passed.tolist(),maximum=[float(v) if good else None for v,good in zip(maximum,supported)],
        complete=bool(supported.all()),all_accepted=bool((supported&passed).all()),
        family_consistent=sample_family_ok.tolist(),
        all_family_consistent=bool(sample_family_ok.all()),
        worst_maximum=float(maximum.max()) if supported.all() else None,
        worst_family_maximum=float(sample_family_max.max()) if supported.all() else None,
        exact_worst_maximum=float(exact_max.max()) if supported.all() else None)
    return result


def rescore_candidate(atlas, capture_offset, candidate, final_pose, markers,
                      board, rules, *, pose_source, reference_pose=None,
                      screen_offsets=((0.,0.),), check=lambda:None):
    """Return fresh scores for a final pose relative to the active reference.

    reference_pose maps acquisition to the active execution reference. This
    matters after selecting another candidate from a previously reached pose.
    """
    pose=homogeneous(final_pose)
    reference=np.eye(3) if reference_pose is None else homogeneous(reference_pose)
    score=score_pose(atlas,capture_offset,pose@reference,markers,board,rules,
                     screen_offsets=screen_offsets,check=check)
    if score is None:return None
    row=deepcopy(candidate)
    # These fields described a different centre or neighbourhood and must not
    # survive a pose change. They are recomputed below only when sampled.
    for name in ('landing_safe','landing_maximum','landing_radius','phase',
                 'remaining_translation','planned_route','input_route',
                 'execution_budget','landing_family_safe','landing_family_maximum',
                 'route_stability','landing_uncertain','cross_family_fallback'):
        row.pop(name,None)
    row.update(score)
    row.update(pose_fields(pose,board))
    row['prediction_pose_source']=str(pose_source)
    row['prediction_pose']=(pose@reference)[:2].tolist()
    if len(screen_offsets)>1:
        row.update(landing_safe=score['pose_samples']['all_accepted'],
                   landing_maximum=score['pose_samples']['worst_maximum'],
                   landing_family_safe=score['pose_samples']['all_family_consistent'],
                   landing_family_maximum=score['pose_samples']['worst_family_maximum'])
    return row
