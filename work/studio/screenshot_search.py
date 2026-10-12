"""Periodic proposals for user rules; only visible HEX is accepted as actual."""
import math,time
import numpy as np
from vision import accepted,error
from best_result import ranking
from screenshot_samples import distances
from screenshot_geometry import solve_joint

def proposal_rank(observed,rules,indices,residuals,cost):
    residuals=np.broadcast_to(residuals,(len(indices),))
    codes=['#'+''.join(f'{int(v):02X}' for v in value) for value in observed]
    deltas=[error(code,rules[i]['colors'],False) for code,i in zip(codes,indices)]
    hits=[bool(accepted([code,code],[rules[i],dict(rules[i],enabled=False)])) and residuals[n]<.8
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

def solve(sites,colors,period,markers,rules,current,time_budget=3,check=lambda:None):
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
    for limit in tiers:
        check();remaining=start+time_budget-time.monotonic()
        if remaining<=0:exhausted=True;break
        selected=[];rgb=[]
        for i in available:
            order=np.argsort(distances(colors[i],rules[i]),kind='stable')
            if limit=='matched':
                values=distances(colors[i],rules[i]);order=order[values[order]<=(0 if rules[i]['exact'] else rules[i]['tolerance'])]
            elif limit is not None:order=order[:limit]
            selected.append(np.asarray(sites[i])[order]);rgb.append(np.asarray(colors[i])[order])
        if any(not len(v) for v in selected):continue
        if len(available)==3:
            found=solve_joint(selected,period,markers[available],1,6,current,
                time_budget=min(remaining,1.2) if limit is not None else remaining,limit=32,check=check)
            rows=found['candidates'];exhausted|=found['exhausted']
        else:
            def rank(ids,cost):
                return proposal_rank([rgb[n][int(k)].tolist() for n,k in enumerate(ids)],
                    rules,available,[0]*len(available),cost)
            rows=_partial(selected,period,markers[available],current,start+time_budget,check,rank)
        for row in rows:
            observed=[rgb[n][int(k)].tolist() for n,k in enumerate(row['site_indices'])]
            deficits=[float(distances(np.array([value]),rules[i])[0]) for value,i in zip(observed,available)]
            row=dict(row,active_indices=available,observed_rgb=observed,
                proposal_only=True,actual_acceptance=False,
                proposal_score=row['max_residual']+.18*max(deficits,default=0)+.005*row['cost'],
                proposal_rank=proposal_rank(observed,rules,available,
                    row.get('residuals_screen',[row['max_residual']]*len(available)),row['cost']))
            proposals.append(row)
        if limit is None or (limit!='matched' and all(len(sites[i])<=limit for i in indices)):break
    proposals.sort(key=lambda v:v['proposal_rank'])
    unique=[]
    for row in proposals:
        if any(row['observed_rgb']==old['observed_rgb'] and
            np.linalg.norm(row['matrix'][:2,:2]-old['matrix'][:2,:2])<.00003 and
            np.linalg.norm(row['matrix'][:2,2]-old['matrix'][:2,2])<.05 for old in unique):continue
        unique.append(row)
    return dict(candidates=unique,exhausted=exhausted,elapsed_seconds=time.monotonic()-start,
        site_counts=[len(v) for v in sites],proposal_only=True)

def _partial(sites,period,markers,current,deadline,check,rank):
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
        if len(rows)>256:rows.sort(key=lambda v:rank(v['site_indices'],v['cost']));del rows[128:]
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
