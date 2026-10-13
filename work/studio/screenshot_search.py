"""Periodic proposals for user rules; only visible HEX is accepted as actual."""
import math,time
import numpy as np
from vision import accepted,error
from best_result import ranking
from screenshot_samples import distances,select_site_indices
from screenshot_geometry import solve_joint

def _residual_tolerances(rules,indices,anchor_exact=False):
    fixed=anchor_exact and len(indices)==3 and sum(bool(rules[i]['exact']) for i in indices)==2
    return np.array([1e-7 if fixed and rules[i]['exact'] else .8 for i in indices])

def proposal_rank(observed,rules,indices,residuals,cost,*,anchor_exact=False):
    residuals=np.broadcast_to(residuals,(len(indices),))
    codes=['#'+''.join(f'{int(v):02X}' for v in value) for value in observed]
    deltas=[error(code,rules[i]['colors'],False) for code,i in zip(codes,indices)]
    tolerances=_residual_tolerances(rules,indices,anchor_exact)
    hits=[bool(accepted([code,code],[rules[i],dict(rules[i],enabled=False)])) and residuals[n]<tolerances[n]
        for n,(code,i) in enumerate(zip(codes,indices))]
    order=sorted(range(len(indices)),key=lambda n:rules[indices[n]].get('priority',indices[n]+1))
    # Site RGB is only a proposal. A point many pixels away from its marker
    # does not earn a predicted hit even when its original sample matched.
    if any('priority' in rule for rule in rules):
        from region_priority import PRIORITY_DELTA_E_BIN
        losses=[float(deltas[n]+residuals[n]*3) for n in range(len(indices))]
        ordered=[]
        for n in order:
            ordered.extend((int(not hits[n]),0 if hits[n] else math.floor(losses[n]/PRIORITY_DELTA_E_BIN)))
        return (int(not all(hits)),*ordered,max(losses,default=0),
            float(np.mean(losses)) if losses else 0.,float(max(residuals,default=0)),float(cost))
    return (int(not all(hits)),*[int(not hits[n]) for n in order],
        *[float(deltas[n]+residuals[n]*3) for n in order],float(max(residuals,default=0)),float(cost))

def actual_result(colors,rules):
    complete=len(colors)==len(rules) and all(not r['enabled'] or c is not None for c,r in zip(colors,rules))
    return dict(actual_colors=list(colors),actual_deltas=[error(c,r['colors'],False) if r['enabled'] and c else None for c,r in zip(colors,rules)],
        verified=bool(complete),screenshot_verified=bool(complete),accepted=bool(complete and accepted(colors,rules)),
        rank=ranking(colors,rules))


def _quality_function(rgb,rules,indices,*,anchor_exact=False):
    """Same proposal order before geometry retention; no late quality loss."""
    from region_priority import PRIORITY_DELTA_E_BIN
    colors=[np.asarray(values) for values in rgb]
    deltas=[distances(values,dict(rules[i],exact=False)) for values,i in zip(colors,indices)]
    base_hits=[]
    for values,delta,i in zip(colors,deltas,indices):
        if rules[i]['exact']:
            from vision import rgb as color_rgb
            targets=np.array([color_rgb(c) for c in rules[i]['colors']])
            base_hits.append(np.any(np.all(values[:,None,:]==targets,axis=2),axis=1))
        else:base_hits.append(delta<=rules[i]['tolerance'])
    order=sorted(range(len(indices)),key=lambda n:rules[indices[n]].get('priority',indices[n]+1))
    prioritized=any('priority' in rule for rule in rules)
    def quality(ids,residuals,cost):
        losses=np.column_stack([deltas[n][ids[:,n]] for n in range(len(indices))])+residuals*3
        hits=np.column_stack([base_hits[n][ids[:,n]] for n in range(len(indices))])&(residuals<_residual_tolerances(rules,indices,anchor_exact))
        parts=[~np.all(hits,axis=1)]
        if prioritized:
            for n in order:parts.extend((~hits[:,n],np.where(hits[:,n],0,np.floor(losses[:,n]/PRIORITY_DELTA_E_BIN))))
            parts.extend((losses.max(axis=1),losses.mean(axis=1)))
        else:
            parts.extend([~hits[:,n] for n in order]);parts.extend([losses[:,n] for n in order])
        parts.extend((residuals.max(axis=1),cost))
        return np.column_stack(parts)
    return quality

def solve(sites,colors,period,markers,rules,current,time_budget=3,check=lambda:None,*,sample_at=None):
    start=time.monotonic();indices=[i for i,r in enumerate(rules) if r['enabled']]
    if not indices:return dict(candidates=[],exhausted=False)
    available=[i for i in indices if len(sites[i])]
    if not available:
        return dict(candidates=[],exhausted=False,active_indices=[],
                    missing_indices=list(indices))
    markers=np.asarray(markers,float);current=np.asarray(current,float);proposals=[];exhausted=False
    # Expand through all retained samples if time permits. A timeout is a
    # search limit, never evidence that the game palette has no solution.
    tiers=('matched',64,256,1024,None) if len(indices)==3 else ('matched',256,1024,None)
    exact=[n for n,i in enumerate(available) if rules[i]['exact']]
    fixed_pair=tuple(sorted(exact)) if len(available)==3 and len(exact)==2 else None
    def endpoint_quality(points,scales,ids,residuals,cost):
        observed,valid,offsets=sample_at(points,available)
        # Endpoint samples need to be close to their own coordinates. The
        # fitted target site's residual is not the endpoint color error.
        uncertainties=offsets*scales[:,None]
        uncertainties=np.where(valid,uncertainties,1000.)
        q=_quality_function([observed[:,n] for n in range(len(available))],rules,available)
        return np.column_stack((~np.all(valid,axis=1),
            q(np.tile(np.arange(len(points))[:,None],(1,len(available))),uncertainties,cost)))
    if fixed_pair is not None:
        jobs=[]
        matched_counts=[int(np.sum(distances(colors[i],rules[i])<=
            (0 if rules[i]['exact'] else rules[i]['tolerance']))) for i in available]
        for cap in (64,256,1024,None):
            if all(matched_counts[n] for n in fixed_pair) and (cap==64 or any(matched_counts[n]>(cap//4 if cap else 1024) for n in fixed_pair)):
                if all(matched_counts):jobs.append((True,cap,fixed_pair))
                # Keep exact anchors available when the third region only has
                # compromise samples, and compare its full raw-color pool.
                jobs.append(('anchors',cap,fixed_pair))
            jobs.append((False,cap,None))
    else:jobs=[(limit=='matched',64 if limit=='matched' else limit,None) for limit in tiers]
    for matched,limit,anchors in jobs:
        check();remaining=start+time_budget-time.monotonic()
        if remaining<=0:exhausted=True;break
        selected=[];rgb=[]
        for n,i in enumerate(available):
            # The third-color tree is inexpensive: retain every matching third
            # site even when the anchor pairs need gradual timed expansion.
            cap=None if anchors is not None and n not in anchors else limit
            filter_matched=bool(matched) and not (matched=='anchors' and n not in anchors)
            order=select_site_indices(sites[i],colors[i],rules[i],period,
                cap,matched=filter_matched)
            selected.append(np.asarray(sites[i])[order]);rgb.append(np.asarray(colors[i])[order])
        if any(not len(v) for v in selected):continue
        if len(available)==3:
            found=solve_joint(selected,period,markers[available],1,6,current,
                time_budget=min(remaining,1.2) if limit is not None else remaining,limit=32,check=check,
                fixed_pair=anchors,candidate_quality=_quality_function(rgb,rules,available,anchor_exact=fixed_pair is not None),
                endpoint_quality=endpoint_quality if sample_at is not None else None)
            rows=found['candidates'];exhausted|=found['exhausted']
        else:
            def rank(ids,cost):
                return proposal_rank([rgb[n][int(k)].tolist() for n,k in enumerate(ids)],
                    rules,available,[0]*len(available),cost)
            def endpoint_rank(matrix,ids,cost):
                source=(markers[available]-matrix[:2,2])@np.linalg.inv(matrix[:2,:2]).T
                observed,valid,offsets=sample_at(source[None,...],available)
                residuals=np.where(valid[0],offsets[0]*np.hypot(matrix[0,0],matrix[1,0]),1000.)
                return (int(not np.all(valid)),*proposal_rank(observed[0],rules,available,residuals,cost))
            rows=_partial(selected,period,markers[available],current,start+time_budget,check,rank,
                endpoint_rank=endpoint_rank if sample_at is not None else None)
        for row in rows:
            observed=[rgb[n][int(k)].tolist() for n,k in enumerate(row['site_indices'])]
            planning_residuals=row.get('residuals_screen',[row['max_residual']]*len(available))
            if sample_at is not None:
                source=(markers[available]-row['matrix'][:2,2])@np.linalg.inv(row['matrix'][:2,:2]).T
                actual,valid,offsets=sample_at(source[None,...],available)
                if not np.all(valid):continue
                row=dict(row,selected_site_rgb=observed,endpoint_sampled=True,
                    endpoint_source_points=source,endpoint_offsets=offsets[0])
                observed=actual[0].tolist();planning_residuals=offsets[0]*row['scale_factor']
            deficits=[float(distances(np.array([value]),rules[i])[0]) for value,i in zip(observed,available)]
            row=dict(row,active_indices=available,observed_rgb=observed,
                proposal_only=True,actual_acceptance=False,
                proposal_score=row['max_residual']+.18*max(deficits,default=0)+.005*row['cost'],
                proposal_rank=proposal_rank(observed,rules,available,
                    planning_residuals,row['cost'],
                    anchor_exact=fixed_pair is not None and sample_at is None))
            proposals.append(row)
        if not matched and (limit is None or all(len(sites[i])<=limit for i in available)):break
    proposals.sort(key=lambda v:v['proposal_rank'])
    unique=[]
    for row in proposals:
        if any(row['observed_rgb']==old['observed_rgb'] and
            np.linalg.norm(row['matrix'][:2,:2]-old['matrix'][:2,:2])<.00003 and
            np.linalg.norm(row['matrix'][:2,2]-old['matrix'][:2,2])<.05 for old in unique):continue
        unique.append(row)
    return dict(candidates=unique,exhausted=exhausted,elapsed_seconds=time.monotonic()-start,
        site_counts=[len(v) for v in sites],proposal_only=True,
        fixed_exact_pair=[available[n] for n in fixed_pair] if fixed_pair is not None else None)

def _partial(sites,period,markers,current,deadline,check,rank,*,endpoint_rank=None):
    a=complex(current[0,0],current[1,0]);b=complex(*current[:2,2]);m=markers[:,0]+1j*markers[:,1]
    source=[v[:,0]+1j*v[:,1] for v in sites];rows=[]
    def retain(alpha,beta,q,ids):
        common=(beta-b)/(alpha*period)
        common=round(common.real)+1j*round(common.imag)
        q=np.asarray(q)+period*common;beta-=alpha*period*common
        matrix=np.array([[alpha.real,-alpha.imag,beta.real],[alpha.imag,alpha.real,beta.imag],[0,0,1.]])
        rows.append(dict(matrix=matrix,site_indices=ids,lifted_sites=np.column_stack((q.real,q.imag)),
            scale_factor=abs(alpha),angle_degrees=math.degrees(np.angle(alpha)),max_residual=0.,
            cost=float(abs(np.log(abs(alpha/a)))+abs(np.angle(alpha/a))+abs(beta-b)/(period*abs(a)))))
        if len(rows)>256:
            rows.sort(key=lambda v:rank(v['site_indices'],v['cost']) if endpoint_rank is None else
                endpoint_rank(v['matrix'],v['site_indices'],v['cost']))
            del rows[128:]
    if len(sites)==1:
        for i,q in enumerate(source[0]):
            if i%64==0:check()
            if time.monotonic()>deadline:break
            retain(a,m[0]-a*q,[q],[i])
    else:
        dm=m[1]-m[0];extent=int(np.ceil(abs(dm)/period))+1
        for liftx in range(-extent,extent+1):
            for lifty in range(-extent,extent+1):
                for i,first in enumerate(source[0]):
                    check()
                    if time.monotonic()>deadline:return rows
                    difference=source[1]+period*complex(liftx,lifty)-first
                    valid=(np.abs(difference)>=abs(dm)/6)&(np.abs(difference)<=abs(dm))
                    for slot,j in enumerate(np.flatnonzero(valid)):
                        if slot%32==0:
                            check()
                            if time.monotonic()>deadline:return rows
                        alpha=dm/difference[j]
                        retain(alpha,m[0]-alpha*first,[first,first+difference[j]],[i,int(j)])
    return rows
