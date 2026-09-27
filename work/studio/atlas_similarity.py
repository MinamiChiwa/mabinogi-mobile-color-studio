"""Color-first periodic similarity proposals; no game input.

Two target-color points determine a positive similarity transform. All active
materials, including the third, are then sampled through that SAME transform.
Seed selection is bounded and spatially distributed; failure is not a proof
that no continuous solution exists. A proposal needs measured live execution
and game HEX verification before it can be considered a dye result.
"""
import itertools
import numpy as np
import cv2
from vision import lab, rgb
from candidate_ranking import candidate_rank,exact_priority,exact_fields


def _distances(values, rule):
    targets=np.asarray([rgb(v) for v in rule['colors']],np.uint8)
    if not len(targets):raise ValueError('Enabled region requires target colors')
    distances=np.full(len(values),np.inf)
    exact=np.zeros(len(values),bool)
    value_lab=lab(values)
    for target, target_lab in zip(targets,lab(targets)):
        distances=np.minimum(distances,np.linalg.norm(value_lab-target_lab,axis=1))
        exact |= (values==target).all(axis=1)
    passed=exact if rule.get('exact') else distances<=float(rule['tolerance'])
    return distances,passed


def _seeds(atlas, region, rule, limit, source_radius, include_compromises=False):
    colors,valid,_=atlas.maps(region=region); n=atlas.resolution
    distances,passes=_distances(colors.reshape(-1,3),rule)
    # Same four-pixel support requirement as atlas.sample, including seams.
    usable=valid&np.roll(valid,-1,0)&np.roll(valid,-1,1)&np.roll(np.roll(valid,-1,0),-1,1)
    ids=np.flatnonzero(usable.ravel()&passes)
    hit_count=len(ids)
    if not hit_count and include_compromises:
        ids=np.flatnonzero(usable.ravel())
        # No target hit: use a bounded pool of the closest supported colors.
        # This changes proposals only; acceptance always uses original rules.
        count=min(len(ids),max(limit,2048))
        if count and count<len(ids):ids=ids[np.argpartition(distances[ids],count-1)[:count]]
    if not len(ids):return np.empty((0,2)),np.empty(0),0
    pad=max(1,int(np.ceil(source_radius*n*np.abs(np.linalg.inv(atlas.basis)).sum(axis=1).max())))
    if pad>n:raise ValueError('Landing radius exceeds atlas period')
    field=np.where(usable.ravel(),distances,np.inf).reshape(n,n).astype(np.float32)
    padded=cv2.copyMakeBorder(field,pad,pad,pad,pad,cv2.BORDER_WRAP)
    worst=cv2.dilate(padded,np.ones((2*pad+1,2*pad+1),np.uint8))[pad:-pad,pad:-pad].ravel()
    order=ids[np.lexsort((ids,distances[ids],worst[ids]))]
    # First include a best hit per spatial bin, then fill by color/robustness.
    bins=max(2,int(np.sqrt(limit)))
    kept=[]; seen=set()
    for index in order:
        y,x=divmod(int(index),n); key=(x*bins//n,y*bins//n)
        if key not in seen:
            seen.add(key);kept.append(int(index))
        if len(kept)>=limit:break
    if len(kept)<limit:
        selected=set(kept)
        for index in order:
            if int(index) not in selected:
                kept.append(int(index));selected.add(int(index))
            if len(kept)>=limit:break
    kept=np.asarray(kept,int)
    y,x=np.divmod(kept,n)
    points=(np.column_stack((x,y))+.5)/n@atlas.basis.T+atlas.origin
    return points,worst[kept],hit_count


def _sample_transforms(atlas, markers, rules, multipliers, offsets, jitter=(0,0)):
    enabled=[i for i,r in enumerate(rules) if r['enabled']]
    usable=np.ones(len(multipliers),bool); passes=usable.copy()
    all_colors=[None]*3; all_distances=[None]*3
    delta=complex(*jitter)
    for region in enabled:
        source=(complex(*markers[region])+delta-offsets)/multipliers
        values,supported=atlas.sample(region,np.column_stack((source.real,source.imag)))
        values=np.rint(values).clip(0,255).astype(np.uint8)
        distances,passed=_distances(values,rules[region])
        usable &= supported; passes &= passed
        all_colors[region]=values; all_distances[region]=distances
    maximum=np.maximum.reduce([all_distances[i] for i in enabled])
    average=np.mean([all_distances[i] for i in enabled],axis=0)
    return usable&passes,maximum,average,all_colors,all_distances,usable


def similarity_candidates(atlas, markers, rules, current_translation, board_shape,
                          *, scale_bounds=(.65,1.), max_angle=180., limit=8,
                          seed_limit=128, cycle_radius=1, landing_radius=1.,
                          cancelled=lambda:False, diagnostics=None, scale_levels=None,
                          include_compromises=False):
    """Return unverified relative transforms in board-local coordinates.

    ``matrix`` maps the current capture to the proposed pose. dx/dy are the
    board-center displacement, compatible with planner.decompose_gestures.
    Atlas sampling uses unfolded source points and wraps each material on its
    measured period, so colors across opposite atlas edges remain candidates.
    """
    markers=np.asarray(markers,float); current=np.asarray(current_translation,float)
    bounds=np.asarray(scale_bounds,float); shape=np.asarray(board_shape,float)
    if (markers.shape!=(3,2) or current.shape!=(2,) or shape.shape!=(2,) or
        bounds.shape!=(2,) or not np.isfinite(np.r_[markers.ravel(),current,shape,bounds,max_angle,landing_radius]).all() or
        np.any(shape<=0) or not 0<bounds[0]<=bounds[1] or not 0<=max_angle<=180 or
        landing_radius<0 or len(rules)!=3 or not 1<=limit<=100 or not 1<=seed_limit<=512 or
        not 0<=cycle_radius<=2):
        raise ValueError('Invalid similarity search geometry or bounds')
    enabled=[i for i,r in enumerate(rules) if r['enabled']]
    if len(enabled)<2:return []
    levels=None if scale_levels is None else np.unique(np.asarray(scale_levels,float))
    if levels is not None and (levels.ndim!=1 or not len(levels) or
            not np.isfinite(levels).all() or np.any(levels<bounds[0]-1e-8) or np.any(levels>bounds[1]+1e-8)):
        raise ValueError('Invalid discrete scale levels')
    diag=diagnostics if diagnostics is not None else {}
    diag.update(search='bounded_color_seed_similarity',exhaustive=False,
                scale_bounds=bounds.tolist(),max_angle=float(max_angle),seed_limit=seed_limit,
                cycle_radius=cycle_radius,hit_counts={},seed_counts={},evaluated_transforms=0)
    diag['scale_levels']=None if levels is None else levels.tolist()
    diag['include_compromises']=bool(include_compromises)
    points={}; source_risk={}
    for region in enabled:
        if cancelled():raise InterruptedError('Calculation cancelled')
        points[region],source_risk[region],hits=_seeds(atlas,region,rules[region],seed_limit,
                                                     landing_radius/bounds[0],include_compromises)
        diag['hit_counts'][str(region+1)]=hits
        diag['seed_counts'][str(region+1)]=len(points[region])
    if any(not len(points[i]) for i in enabled):return []
    # Anchor exact regions first; similar targets cannot displace them merely
    # because their seed pool happens to be smaller.
    first,second=sorted(enabled,key=lambda i:(not rules[i].get('exact'),len(points[i])))[:2]
    q1=points[first][:,0]+1j*points[first][:,1]
    q2=points[second][:,0]+1j*points[second][:,1]
    p1=complex(*markers[first]); p2=complex(*markers[second])
    center=complex(shape[1]/2,shape[0]/2); current_z=complex(*current)
    inverse=np.linalg.inv(atlas.basis); pool=[]
    pair_risk=np.maximum(source_risk[first][:,None],source_risk[second][None,:])
    for ox,oy in itertools.product(range(-cycle_radius,cycle_radius+1),repeat=2):
        if cancelled():raise InterruptedError('Calculation cancelled')
        wrap=atlas.basis@np.array([ox,oy]); denominator=q2[None,:]+complex(*wrap)-q1[:,None]
        with np.errstate(divide='ignore',invalid='ignore'):
            a=(p2-p1)/denominator
        scales=np.abs(a); angles=np.degrees(np.angle(a))
        good=np.isfinite(a)&(scales>=bounds[0])&(scales<=bounds[1])&(np.abs(angles)<=max_angle)
        ii,jj=np.where(good)
        if not len(ii):continue
        a=a[ii,jj]
        if levels is not None:
            # A continuous solution can lie between wheel notches. Test the
            # nearest available scale and its neighbors, then resample ALL
            # regions; never keep the continuous solution's color scores.
            nearest=np.abs(np.log(np.abs(a)[:,None]/levels)).argmin(axis=1)
            ids=np.clip(nearest[:,None]+[-1,0,1],0,len(levels)-1)
            a=(a/np.abs(a))[:,None]*levels[ids]
            a=a.ravel();ii=np.repeat(ii,3);jj=np.repeat(jj,3)
            q2_wrapped=q2[jj]+complex(*wrap)
            b=(p1+p2-a*(q1[ii]+q2_wrapped))/2
            if rules[first].get('exact') and not rules[second].get('exact'):
                b=p1-a*q1[ii]
        else:b=p1-a*q1[ii]
        # Choose the shortest representative in the rotated/scaled period
        # lattice. Search neighbors too: a skewed basis needs more than round.
        displacement=(a*center+b-a*current_z-center)/a
        phase=np.column_stack((displacement.real,displacement.imag))@inverse.T
        phase-=np.rint(phase)
        best=np.full(len(a),np.inf); center_move=np.zeros(len(a),complex)
        for tx,ty in itertools.product((-1,0,1),repeat=2):
            unrotated=(phase+[tx,ty])@atlas.basis.T
            candidate=a*(unrotated[:,0]+1j*unrotated[:,1])
            better=np.abs(candidate)<best
            best[better]=np.abs(candidate[better]);center_move[better]=candidate[better]
        relative_offset=center_move+center-a*center
        absolute_offset=relative_offset+a*current_z
        passed,maximum,average,colors,distances,usable=_sample_transforms(atlas,markers,rules,a,absolute_offset)
        diag['evaluated_transforms']+=len(a)
        ids=np.flatnonzero(passed)
        # Keep a bounded pool for the more costly neighborhood check. Include
        # source-island quality so exact but brittle pixels cannot fill it.
        risk=pair_risk[ii,jj]
        ids=ids[np.lexsort((best[ids],average[ids],maximum[ids],risk[ids]))][:256]
        if include_compromises:
            rejected=np.flatnonzero(usable&~passed)
            hits,exact_max,exact_avg,_=exact_priority(colors,distances,rules)
            rejected=rejected[np.lexsort((best[rejected],risk[rejected],average[rejected],maximum[rejected],
                                           exact_avg[rejected],exact_max[rejected],-hits[rejected]))][:256]
            ids=np.r_[ids,rejected]
        for k in ids:
            pool.append((a[k],relative_offset[k],absolute_offset[k],center_move[k],
                         maximum[k],average[k]))
    if not pool:return []
    a=np.array([v[0] for v in pool]); absolute=np.array([v[2] for v in pool])
    passed,maximum,average,colors,distances,usable=_sample_transforms(atlas,markers,rules,a,absolute)
    hits,exact_max,exact_avg,exact_total=exact_priority(colors,distances,rules)
    stable=passed.copy(); worst=maximum.copy()
    neighborhood_supported=usable.copy()
    for x,y in ((-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)):
        if cancelled():raise InterruptedError('Calculation cancelled')
        good,loss,_,_,_,supported=_sample_transforms(atlas,markers,rules,a,absolute,
                                                   (x*landing_radius,y*landing_radius))
        stable &= good; worst=np.maximum(worst,loss)
        neighborhood_supported &= supported
    rows=[]
    for k,v in enumerate(pool):
        if not usable[k] or (not include_compromises and not passed[k]):continue
        multiplier,offset,absolute_offset,move,_,_=v
        hexes=['#%02X%02X%02X'%tuple(colors[i][k]) if i in enabled else None for i in range(3)]
        rows.append(dict(id=k,predicted=True,verified=False,accepted=bool(passed[k]),
            colors=hexes,deltas=[float(distances[i][k]) if i in enabled else None for i in range(3)],
            maximum=float(maximum[k]),average=float(average[k]),
            dx=float(move.real),dy=float(move.imag),angle=float(np.degrees(np.angle(multiplier))),
            scale=float(abs(multiplier)),matrix=[[float(multiplier.real),float(-multiplier.imag),float(offset.real)],
                                                [float(multiplier.imag),float(multiplier.real),float(offset.imag)]],
            landing_radius=float(landing_radius),landing_safe=bool(stable[k]),
            landing_maximum=float(worst[k]) if neighborhood_supported[k] else None,
            search_space='periodic_similarity',execution_verified=False))
        rows[-1].update(exact_fields(hits,exact_max,exact_avg,exact_total,k))
    result=[]; seen=set()
    for row in sorted(rows,key=candidate_rank):
        key=tuple(row['colors'])
        if key in seen:continue
        seen.add(key);row['id']=len(result);result.append(row)
        if len(result)>=limit:break
    diag['accepted_pool']=sum(row['accepted'] for row in rows)
    diag['compromise_pool']=sum(not row['accepted'] for row in rows)
    return result


def captured_scale_levels(log):
    """Estimate reachable wheel levels only over the observed capture range.

    Capture logs measure aggregate scaling, so these levels are proposals.
    Live execution must still measure every wheel response and reject drift.
    """
    zoom=next((r for r in reversed(log) if r.get('kind')=='sampling_zoom'),{})
    steps=int(zoom.get('steps',0));scale=float(zoom.get('scale',1))
    if not 0<steps<=48 or not np.isfinite(scale) or scale<=1:
        return [1.],None
    tick=float(np.log(scale)/steps)
    return np.exp(-tick*np.arange(steps+1)).tolist(),tick
