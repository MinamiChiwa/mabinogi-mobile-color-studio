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
from candidate_ranking import candidate_rank,candidate_order,exact_priority,exact_fields
from region_priority import vector_priority_components, priority_fields, priority_indices
from color_family import family_penalties,family_priority,family_fields


def select_color_candidates(rows, rules, limit, *, preserve_routes=False):
    """Keep the balanced default and distinct nearest-exact alternatives.

    Reserve separate tail slots only when no proposal hits every exact
    region. A one-row result always remains the best balanced proposal.
    This selection is also applied after route binding, where colors change.
    """
    ranked=[];seen=set()
    if preserve_routes:
        # Similarity search runs before live route binding. Keep a bounded set
        # of distinct input geometries for each colour tuple so an attractive
        # but unbindable micro-rotation cannot hide a reachable translation.
        # The live builder applies the normal colour de-duplication again after
        # binding and rescoring, so this only widens the pre-bind evidence pool.
        best_colors=select_color_candidates(rows,rules,limit)
        by_color={tuple(row['colors']):[] for row in best_colors}
        for row in sorted(rows,key=candidate_rank):
            colors=tuple(row.get('colors',()))
            if colors not in by_color:continue
            route_key=(colors,
                       round(float(row.get('dx',0.) or 0.),3),
                       round(float(row.get('dy',0.) or 0.),3),
                       round(float(row.get('angle',0.) or 0.),3),
                       round(float(row.get('scale',1.) or 1.),5))
            if route_key in seen:continue
            seen.add(route_key);by_color[colors].append(row)
        def operation_class(row):
            return (abs(float(row.get('angle',0.) or 0.))>1e-6,
                    abs(float(row.get('scale',1.) or 1.)-1.)>1e-6)
        for options in by_color.values():
            selected=[];classes=set()
            # First keep one representative for each operation class, then
            # fill spare slots from the original balanced ordering.
            for row in options:
                kind=operation_class(row)
                if kind in classes:continue
                classes.add(kind);selected.append(row)
            selected.extend(row for row in options if row not in selected)
            ranked.extend(selected[:4])
        return sorted(ranked,key=candidate_rank)
    for row in sorted(rows,key=candidate_rank):
        key=tuple(row['colors'])
        if key in seen:continue
        seen.add(key);ranked.append(row)
    selected=ranked[:limit]
    exact=[i for i,r in enumerate(rules) if r.get('enabled') and r.get('exact')]
    if len(selected)<2 or not exact:return selected
    all_exact=any(all(row['colors'][i] is not None and
        row['colors'][i].upper() in [c.upper() for c in rules[i]['colors']]
        for i in exact) for row in ranked)
    if all_exact:return selected
    # With explicit region priorities, the lexicographic candidate rank is the
    # user's requested compromise policy. The historical per-exact-region tail
    # slot can replace a lower-ranked row with a lower-priority hit and thereby
    # violate that policy. Keep the ranked shortlist intact; the legacy path
    # below remains unchanged for profiles without priority metadata.
    if priority_indices(rules) is not None:
        return selected
    reserved=set();slot=len(selected)-1
    for region in exact:
        options=[row for row in ranked if row.get('deltas',[None]*3)[region] is not None]
        if not options:continue
        nearest=min(options,key=lambda row:(float(row['deltas'][region]),candidate_rank(row)))
        key=tuple(nearest['colors'])
        if key in {tuple(r['colors']) for r in selected}:
            reserved.add(key);continue
        while slot>0 and tuple(selected[slot]['colors']) in reserved:slot-=1
        if slot<=0:break
        selected[slot]=nearest;reserved.add(key);slot-=1
    return sorted(selected,key=candidate_rank)


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
    family=family_penalties(colors.reshape(-1,3),rule)
    # Same four-pixel support requirement as atlas.sample, including seams.
    usable=valid&np.roll(valid,-1,0)&np.roll(valid,-1,1)&np.roll(np.roll(valid,-1,0),-1,1)
    ids=np.flatnonzero(usable.ravel()&passes)
    hit_count=len(ids)
    if not hit_count and include_compromises:
        ids=np.flatnonzero(usable.ravel())
        # Do not truncate by center error before evaluating neighborhood
        # risk: a narrow low-error stripe could crowd out every broad island.
    if not len(ids):return np.empty((0,2)),np.empty(0),0
    pad=max(1,int(np.ceil(source_radius*n*np.abs(np.linalg.inv(atlas.basis)).sum(axis=1).max())))
    if pad>n:raise ValueError('Landing radius exceeds atlas period')
    field=np.where(usable.ravel(),distances,np.inf).reshape(n,n).astype(np.float32)
    padded=cv2.copyMakeBorder(field,pad,pad,pad,pad,cv2.BORDER_WRAP)
    worst=cv2.dilate(padded,np.ones((2*pad+1,2*pad+1),np.uint8))[pad:-pad,pad:-pad].ravel()
    order=ids[np.lexsort((ids,family[ids],distances[ids],worst[ids]))]
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
    if include_compromises:
        # A hit in a small island must not exclude every other location. Two
        # exact islands can have an unreachable separation while one exact
        # hit plus a nearby color elsewhere is the best feasible compromise.
        # Add one best supported point per bin across the FULL period, with a
        # separate, bounded allowance; preserve the original exact seeds.
        fallback_bins=max(2,int(np.sqrt(min(limit,64))))
        available=np.flatnonzero(usable.ravel())
        y,x=np.divmod(available,n)
        bins_xy=(y*fallback_bins//n)*fallback_bins+x*fallback_bins//n
        order=np.lexsort((available,family[available],distances[available],worst[available],bins_xy))
        ordered_bins=bins_xy[order]
        first=np.r_[True,ordered_bins[1:]!=ordered_bins[:-1]]
        selected=set(kept)
        kept.extend(int(v) for v in available[order[first]] if int(v) not in selected)
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
    diag['exact_fallback_pool']=0
    points={}; source_risk={}
    for region in enabled:
        if cancelled():raise InterruptedError('Calculation cancelled')
        points[region],source_risk[region],hits=_seeds(atlas,region,rules[region],seed_limit,
                                                     landing_radius/bounds[0],include_compromises)
        diag['hit_counts'][str(region+1)]=hits
        diag['seed_counts'][str(region+1)]=len(points[region])
    if any(not len(points[i]) for i in enabled):return []
    # Evaluate every enabled pair. Exact priority belongs to the resulting
    # three-region score, not to a fixed pair that can have zero reachable
    # separations and prevent all other proposals from being considered.
    center=complex(shape[1]/2,shape[0]/2); current_z=complex(*current)
    inverse=np.linalg.inv(atlas.basis); pool=[]
    prioritized=priority_indices(rules)
    ordered=(sorted(enabled,key=lambda i:(not rules[i].get('exact'),len(points[i])))
             if prioritized is None else prioritized)
    diag['pair_evaluated_transforms']={}
    for first,second in itertools.combinations(ordered,2):
        pair_key=f'{first+1}-{second+1}'
        diag['pair_evaluated_transforms'][pair_key]=0
        q1=points[first][:,0]+1j*points[first][:,1]
        q2=points[second][:,0]+1j*points[second][:,1]
        p1=complex(*markers[first]); p2=complex(*markers[second])
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
                # Snapping scale can move either target off its seed. Score
                # midpoint and each exact anchor separately; preserving one
                # exact region is preferable to losing both at a midpoint.
                offsets=[b]
                if rules[first].get('exact'):offsets.append(p1-a*q1[ii])
                if rules[second].get('exact'):offsets.append(p2-a*q2_wrapped)
                b=np.concatenate(offsets)
                a=np.tile(a,len(offsets));ii=np.tile(ii,len(offsets));jj=np.tile(jj,len(offsets))
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
            diag['pair_evaluated_transforms'][pair_key]+=len(a)
            ids=np.flatnonzero(passed)
            # Keep a bounded pool for the joint neighborhood check. Pair seed
            # risk is a screening score only, not a full three-region bound.
            risk=pair_risk[ii,jj]
            hits,exact_max,exact_avg,exact_total=exact_priority(colors,distances,rules)
            family_max,family_avg,_=family_priority(colors,rules)
            priority=vector_priority_components(colors,distances,rules)
            ids=ids[candidate_order(hits[ids],maximum[ids],average[ids],passed[ids],False,
                                    risk[ids],best[ids],exact_maximum=exact_max[ids],
                                    exact_average=exact_avg[ids],family_maximum=family_max[ids],
                                    family_average=family_avg[ids],
                                    region_priority=None if priority is None else priority[ids])][:256]
            if include_compromises:
                rejected=np.flatnonzero(usable&~passed)
                rejected=rejected[candidate_order(hits[rejected],maximum[rejected],average[rejected],
                                    passed[rejected],False,risk[rejected],best[rejected],
                                    exact_maximum=exact_max[rejected],exact_average=exact_avg[rejected],
                                    family_maximum=family_max[rejected],family_average=family_avg[rejected],
                                    region_priority=None if priority is None else priority[rejected])][:256]
                ids=np.r_[ids,rejected]
                # If no candidate in this transform batch contains any exact
                # hit, keep a separate nearest-exact slice before the bounded
                # overall-quality pool is discarded.  A narrow dark (or
                # otherwise exact) island can have a poor joint score while
                # still being the only useful compromise for that selected
                # exact region.  This slice is never marked accepted: the
                # strict RGB exact gate remains unchanged.
                if exact_total and not np.any(hits[usable] > 0):
                    exact_pool=np.flatnonzero(usable)
                    exact_pool=exact_pool[np.lexsort((
                        exact_pool,
                        average[exact_pool],
                        maximum[exact_pool],
                        exact_avg[exact_pool],
                        exact_max[exact_pool]))]
                    fallback_ids=exact_pool[:64]
                    diag['exact_fallback_pool']+=int(len(fallback_ids))
                    ids=np.r_[ids,fallback_ids]
            for k in np.unique(ids):
                pool.append((a[k],relative_offset[k],absolute_offset[k],center_move[k],
                             maximum[k],average[k]))
    if not pool:return []
    a=np.array([v[0] for v in pool]); absolute=np.array([v[2] for v in pool])
    passed,maximum,average,colors,distances,usable=_sample_transforms(atlas,markers,rules,a,absolute)
    hits,exact_max,exact_avg,exact_total=exact_priority(colors,distances,rules)
    family_max,family_avg,family_losses=family_priority(colors,rules)
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
        rows[-1].update(family_fields(family_max,family_avg,family_losses,k))
        rows[-1].update(priority_fields(hexes,rows[-1]['deltas'],rules))
    result=[]
    # Keep the normal balanced ranking first so the automatic default is not
    # replaced by a single-region compromise.  When no exact transform exists
    # at all, reserve one public slot per exact region for its nearest
    # supported compromise; otherwise a narrow dark/bright island can be
    # pushed out by candidates with a slightly better joint average.
    for row in select_color_candidates(rows,rules,limit,preserve_routes=True):
        row['id']=len(result);result.append(row)
        if len(result)>=max(int(limit),int(limit)*4):break
    diag['accepted_pool']=sum(row['accepted'] for row in rows)
    diag['compromise_pool']=sum(not row['accepted'] for row in rows)
    diag['family_consistent_pool']=sum(row['family_consistent'] for row in rows)
    return result


def captured_scale_levels(log):
    """Use measured DOWN ticks, never the inverse of an UP measurement.

    Without a directional calibration only the current scale is supported.
    The live executor still verifies every input response against images.
    """
    zoom=next((r for r in reversed(log) if r.get('kind')=='sampling_zoom'),{})
    calibration=next((r for r in reversed(log) if r.get('kind')=='zoom_calibration'),{})
    steps=int(zoom.get('steps',0));tick=calibration.get('down_log_step');up=calibration.get('up_log_step')
    if (not calibration.get('passed') or tick is None or
            up is None or not np.isfinite(up) or not 0<float(up)<.15 or
            not 0<steps<=48 or not np.isfinite(tick) or not 0<float(tick)<.15):
        return [1.],None
    tick=float(tick)
    scale=calibration.get('current_scale',zoom.get('scale',1.))
    if scale is None or not np.isfinite(scale) or scale<=1:return [1.],None
    # A full down/up calibration need not return to the original scale.
    # Stay inside the range actually observed during this capture.
    steps=min(steps,int(np.floor(np.log(scale)/tick)))
    return np.exp(-tick*np.arange(steps+1)).tolist(),tick
