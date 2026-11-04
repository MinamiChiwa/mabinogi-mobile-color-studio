"""Local screenshot proposals around the measured pose; no input or game reads."""
import math
import numpy as np
from scipy.spatial import cKDTree
from screenshot_search import proposal_rank
from refinement_policy import RefinementPolicy


def prefer_reachable_scale(candidate,current,markers,rules,sample_at,check=lambda:None):
    """Avoid fine wheel routes only when sampled joint colours do not regress."""
    from screenshot_control import scale_seconds
    from refinement_policy import compare_refinement
    if sample_at is None:return candidate
    indices=candidate.get('active_indices',[i for i,r in enumerate(rules) if r['enabled']])
    if len(candidate.get('observed_rgb',[]))!=len(indices):return candidate
    def codes(values):
        result=[None]*len(rules)
        for i,value in zip(indices,values):result[i]='#'+''.join(f'{int(v):02X}' for v in value)
        return result
    baseline=codes(candidate['observed_rgb'])
    matrix=np.asarray(candidate['matrix']);markers=np.asarray(markers)
    current_scale=float(np.hypot(current[0,0],current[1,0]))
    wanted=float(np.hypot(matrix[0,0],matrix[1,0]));factor=wanted/current_scale
    best=candidate;cost=scale_seconds(factor)
    pivot=markers[min(indices,key=lambda i:rules[i].get('priority',i+1))]
    ratio=1.01 if factor>=1 else .99
    ticks=math.log(factor)/math.log(ratio)
    for count in sorted({max(0,math.floor(ticks)),max(0,math.ceil(ticks))}):
        check();scale=current_scale*ratio**count
        if not 1<=scale<=6:continue
        new_cost=scale_seconds(scale/current_scale)
        if new_cost>=cost-.01:continue
        delta=np.diag([scale/wanted,scale/wanted,1.]);delta[:2,2]=pivot*(1-scale/wanted)
        pose=delta@matrix
        points=(markers[indices]-pose[:2,2])@np.linalg.inv(pose[:2,:2]).T
        values,valid,offsets=sample_at(points[None,...],indices)
        if not np.all(valid) or np.max(offsets[0]*scale)>.8:continue
        if not compare_refinement(codes(values[0]),baseline,rules)['not_worse']:continue
        best=dict(candidate,matrix=pose,observed_rgb=values[0].tolist(),
            signature=tuple(np.round(pose[:2].ravel(),5)),
            scale_alternative=dict(requested=wanted,selected=scale,saved_seconds=scale_seconds(factor)-new_cost))
        cost=new_cost
    return best


def _sample_index(samples):
    version=(samples.frames,tuple(id(row) for row in samples.rows))
    cached=getattr(samples,'_refinement_index',None)
    if cached is not None and cached[0]==version:return cached[1]
    result=[]
    for row in samples.rows:
        tree=cKDTree(np.mod(row['point'],samples.period),boxsize=samples.period) if len(row) else None
        result.append((tree,row))
    samples._refinement_index=(version,result)
    return result


def local_candidates(samples,markers,rules,current,*,step=.4,limit=8,exclude=(),check=lambda:None,baseline=None):
    """Rank small joint adjustments using original RGB at measured phase sites."""
    markers=np.asarray(markers,float);current=np.asarray(current,float)
    indices=[i for i,r in enumerate(rules) if r['enabled']]
    field=getattr(samples,'visible_field',getattr(samples,'color_field',None))
    index=_sample_index(samples) if field is None else None
    if not indices or field is None and any(index[i][0] is None for i in indices):return []
    if field is not None and hasattr(field,'prepare'):field.prepare(check)
    pivot=markers[min(indices,key=lambda i:rules[i].get('priority',i+1))]
    policy=RefinementPolicy(rules,baseline) if baseline is not None else None
    radius=max(1.,float(np.max(np.linalg.norm(markers-pivot,axis=1))))
    transforms=[]
    # The direction and size are chosen from sampled color response, then
    # re-evaluated after every actual gesture; requested shifts never accumulate.
    for size in (step,step/2):
        for x,y in ((size,0),(-size,0),(0,size),(0,-size)):
            delta=np.eye(3);delta[:2,2]=[x,y];transforms.append(('translate',delta))
        for sign in (-1,1):
            angle=sign*size/radius
            delta=np.eye(3);delta[:2,:2]=[[math.cos(angle),-math.sin(angle)],[math.sin(angle),math.cos(angle)]]
            delta[:2,2]=pivot-delta[:2,:2]@pivot;transforms.append(('rotate',delta))
            delta=np.diag([math.exp(sign*size/radius)]*2+[1.])
            delta[:2,2]=pivot-delta[:2,:2]@pivot;transforms.append(('scale',delta))
    proposals=[];visited=set(exclude)
    for kind,delta in transforms:
        check();pose=delta@current
        if not 1-1e-9<=np.hypot(pose[0,0],pose[1,0])<=6+1e-9:continue
        signature=tuple(np.round(pose[:2].ravel(),5))
        if signature in visited:continue
        points=(markers-pose[:2,2])@np.linalg.inv(pose[:2,:2]).T
        observed=[];residuals=[];margin=[]
        scale=float(np.hypot(pose[0,0],pose[1,0]))
        if field is not None:
            values,valid,offsets=field(points[None,indices,:],indices)
            if not np.all(valid):continue
            observed=values[0].tolist();residuals=(offsets[0]*scale).tolist();margin=[0.]
        for i in indices:
            if field is not None:break
            tree,row=index[i];distance,slot=tree.query(np.mod(points[i],samples.period))
            observed.append(row['rgb'][slot].tolist());residuals.append(float(distance)*scale)
            margin.append(float(row['margin'][slot]) if 'margin' in row.dtype.names else 0.)
        cost=float(np.max(np.linalg.norm(markers@delta[:2,:2].T+delta[:2,2]-markers,axis=1)))
        rank=proposal_rank(observed,rules,indices,residuals,cost)
        if policy is not None:
            codes=[None]*len(rules)
            for i,value in zip(indices,observed):codes[i]='#'+''.join(f'{int(v):02X}' for v in value)
            decision=policy.assess(codes)
            if not decision['improved']:continue
            rank=(*decision['rank'],max(residuals,default=0.),cost)
        proposals.append(dict(matrix=pose,kind=kind,rank=rank,signature=signature,
            observed_rgb=observed,residuals_screen=residuals,margin=min(margin),proposal_only=True))
    proposals.sort(key=lambda row:(row['rank'],-row['margin']))
    return proposals[:limit]
