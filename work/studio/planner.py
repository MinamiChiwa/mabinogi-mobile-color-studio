"""Shared 2D similarity-transform search; each region uses its own texture."""
import numpy as np
from vision import lab,rgb

def decompose_gestures(plan,board,markers):
    """Decompose x'=A*x+b into rotation/zoom about a safe mouse pivot, then drag.

    A pivot is a free choice, not another degree of freedom of the similarity
    transform. Choose it to reduce the residual drag, subject to gesture bounds.
    All points returned are physical client coordinates.
    """
    l,t,r,b=board;center=np.array([(l+r)/2,(t+b)/2])
    angle=np.radians(plan['angle']);scale=plan['scale']
    matrix=scale*np.array([[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]])
    offset=center+np.array([plan['dx'],plan['dy']])-matrix@center
    targets=np.asarray(markers,float)
    sources=(targets-offset)@np.linalg.inv(matrix).T
    margin=max(16,min(r-l,b-t)*.12)
    low=np.array([l+margin,t+margin]);high=np.array([r-margin,b-margin])
    candidates=[np.clip(p,low,high) for p in sources]
    candidates.append(np.clip(np.mean(sources,axis=0),low,high))
    fixed=np.eye(2)-matrix
    if np.linalg.cond(fixed)<1e8:
        candidates.append(np.clip(np.linalg.solve(fixed,offset),low,high))
    # Mouse pivots must be realizable integer pixels; account for rounding here.
    candidates=[np.rint(p) for p in candidates]
    pivot=min(candidates,key=lambda p:np.linalg.norm(offset-fixed@p))
    drag=offset-fixed@pivot
    return dict(rotation_anchor=pivot.tolist(),zoom_anchor=pivot.tolist(),
                drag=drag.tolist(),sources=sources.tolist())

def joint_plan(image,scene,rules):
    l,t,r,b=scene.board;w=r-l;h=b-t;third=w/3;center=np.array([w/2,h/2])
    texture=lab(image[t:b,l:r].reshape(-1,3)).reshape(h,w,3)
    maps=[];factors=[]
    for i,rule in enumerate(rules):
        if not rule['enabled']:continue
        targets=lab([rgb(v) for v in rule['colors']])
        distances=np.full((h,w),np.inf,np.float32)
        for target in targets:distances=np.minimum(distances,np.linalg.norm(texture-target,axis=2))
        factor=max(.6 if rule['exact'] else rule['tolerance'],.001);factors.append(factor)
        distances/=factor
        yy,xx=np.mgrid[:h,:w];mx,my=np.array(scene.markers[i])-[l,t]
        mask=(xx>i*third+5)&(xx<(i+1)*third-5)&(yy>8)&(yy<h-8)
        mask&=~((abs(xx-mx)<=3)&(yy<=my))
        mask&=((xx-mx)**2+(yy-my)**2>(max(6,round(third*.055))+3)**2)
        distances[~mask]=np.inf;maps.append((np.array([mx,my]),distances))
    if len(maps)<2:return None
    # Two source/target point pairs determine a shared similarity transform.
    # This avoids stepping over small islands between angle/scale grid values.
    candidates=[]
    for marker,cost in maps:
        y,x=np.where(cost<=1)
        if not len(x):candidates=[];break
        order=np.argsort(cost[y,x],kind='stable')
        # Keep both best-color pixels and spatially distributed alternatives.
        keep=np.unique(np.concatenate((order[:384],np.linspace(0,len(x)-1,min(640,len(x))).astype(int))))
        candidates.append((x[keep]+1j*y[keep],cost[y[keep],x[keep]]))
    geometric=None
    if candidates:
        z1,c1=candidates[0];z2,c2=candidates[1]
        p1=complex(*maps[0][0]);p2=complex(*maps[1][0]);pivot=complex(*center)
        denominator=z2[None,:]-z1[:,None]
        with np.errstate(divide='ignore',invalid='ignore'):
            a=(p2-p1)/denominator;offset=p1-a*z1[:,None]
            scales=abs(a);angles=np.degrees(np.angle(a));translation=offset-pivot+a*pivot
            valid=np.isfinite(a)&(scales>.65)&(scales<1.5)&(abs(angles)<60)&(abs(translation.real)<w*.65)&(abs(translation.imag)<h*.65)
            worst=np.maximum(c1[:,None],c2[None,:]);raw_worst=np.maximum(c1[:,None]*factors[0],c2[None,:]*factors[1]);raw_total=c1[:,None]*factors[0]+c2[None,:]*factors[1]
            for fi,(marker,cost) in enumerate(maps[2:],2):
                source=(complex(*marker)-offset)/a
                sx=np.rint(np.nan_to_num(source.real,nan=-999,posinf=-999,neginf=-999)).astype(int)
                sy=np.rint(np.nan_to_num(source.imag,nan=-999,posinf=-999,neginf=-999)).astype(int)
                valid&=(sx>=0)&(sx<w)&(sy>=0)&(sy<h)
                values=cost[np.clip(sy,0,h-1),np.clip(sx,0,w-1)]
                worst=np.maximum(worst,values);raw_worst=np.maximum(raw_worst,values*factors[fi]);raw_total+=values*factors[fi]
            rank=raw_worst+raw_total*.000001+(worst>1)*1000
            rank[~valid]=np.inf
            if np.isfinite(rank).any():
                j=np.unravel_index(np.argmin(rank),rank.shape)
                geometric=dict(cost=float(rank[j]),score=float(worst[j]),dx=float(translation.real[j]),dy=float(translation.imag[j]),angle=float(angles[j]),scale=float(scales[j]))
                if geometric['score']<=1:return geometric
    def evaluate(angle,scale,dx,dy):
        a=np.radians(angle);inverse=np.array([[np.cos(a),np.sin(a)],[-np.sin(a),np.cos(a)]])/scale
        shifts=np.column_stack((dx,dy));worst=np.zeros(len(dx));total=np.zeros(len(dx));raw_worst=np.zeros(len(dx))
        for fi,(marker,cost) in enumerate(maps):
            src=np.rint((marker-center-shifts)@inverse.T+center).astype(int)
            inside=(src[:,0]>=0)&(src[:,0]<w)&(src[:,1]>=0)&(src[:,1]<h)
            values=cost[np.clip(src[:,1],0,h-1),np.clip(src[:,0],0,w-1)].copy();values[~inside]=np.inf
            worst=np.maximum(worst,values);total+=values*factors[fi];raw_worst=np.maximum(raw_worst,values*factors[fi])
        # Every region must pass. Mean distance only breaks ties.
        rank=(worst>1)*1000+raw_worst+total*.000001;j=int(np.argmin(rank))
        return float(worst[j]),int(dx[j]),int(dy[j]),float(rank[j])
    yy,xx=np.mgrid[-int(h*.65):int(h*.65)+1:4,-int(w*.35):int(w*.35)+1:4]
    dx,dy=xx.ravel(),yy.ravel();best=None
    seeds=[]
    for scale in (1.,.85,.925,1.075,1.15,1.225):
        for angle in (0.,-10.,10.,-20.,20.,-30.,30.,-40.,40.):
            score,x,y,cost=evaluate(angle,scale,dx,dy)
            if np.isfinite(score):seeds.append(dict(score=score,cost=cost,dx=x,dy=y,angle=angle,scale=scale))
            if np.isfinite(score) and (best is None or cost<best['cost']):
                best=dict(score=score,cost=cost,dx=x,dy=y,angle=angle,scale=scale)
    if best is None:return None
    # Retain several basins: sharp color islands make a single coarse winner unreliable.
    for seed in sorted(seeds,key=lambda p:p['cost'])[:6]:
        yy,xx=np.mgrid[seed['dy']-8:seed['dy']+9:2,seed['dx']-8:seed['dx']+9:2]
        for scale in np.arange(seed['scale']-.04,seed['scale']+.041,.01):
            for angle in np.arange(seed['angle']-5,seed['angle']+5.1,1.):
                score,x,y,cost=evaluate(angle,scale,xx.ravel(),yy.ravel())
                if cost<best['cost']:best=dict(score=score,cost=cost,dx=x,dy=y,angle=float(angle),scale=float(scale))
    yy,xx=np.mgrid[best['dy']-4:best['dy']+5,best['dx']-4:best['dx']+5]
    score,x,y,cost=evaluate(best['angle'],best['scale'],xx.ravel(),yy.ravel())
    best.update(score=score,cost=cost,dx=x,dy=y)
    return geometric if geometric is not None and geometric['cost']<best['cost'] else best
