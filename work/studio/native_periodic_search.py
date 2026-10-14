"""Joint target search on a complete periodic domain, independent of UI routes.

Texture sample sites are finite. A completed site scan or pair enumeration
does not prove exhaustion of continuous bilinear color regions. Every returned
solution is checked by the original float32 CPU picker, never treated as live.
"""
from dye_regions import validate_region_rules
import heapq,itertools,math,time,hashlib
from collections import OrderedDict
import numpy as np
from native_palette_model import picker_view_uv,sample_cpu,color32,distort_uv
from native_palette_scoring import score_native_pose,_pose
from vision import rgb,lab
from region_priority import priority_components, priority_indices, vector_priority_components


def periodic_samples(session,index,fy,fx,*,check=lambda:None):
    """Session-bound original-resolution sample preprocessing, never a hit cache."""
    check();pixels=np.asarray(session['pixels'][index]);q=float(session['color_preserve_ratio'])
    digest=hashlib.sha256(pixels.tobytes()).digest()
    key=(index,pixels.shape,digest,q,float(fy),float(fx))
    cache=session.setdefault('_periodic_sample_cache',OrderedDict())
    if key in cache:
        cache.move_to_end(key);check();return cache[key]
    h,w=pixels.shape[:2];yy,xx=np.indices((h,w))
    uv=np.stack(((xx+.5+fx)/w,(h-yy-.5+fy)/h),axis=-1).reshape(-1,2).astype(np.float32)
    colors=color32(sample_cpu(pixels,uv,q)/np.float32(255));color_lab=lab(colors)
    check()
    for array in (uv,colors,color_lab):array.setflags(write=False)
    value=(uv,colors,color_lab);cache[key]=value
    while sum(sum(a.nbytes for a in row) for row in cache.values())>48*1024*1024 and len(cache)>1:
        cache.popitem(last=False)
    return value


def inverse_periodic_uv(uv):
    result=np.asarray(uv,np.float64).copy();k=12.566370964050293
    for _ in range(2):
        result[...,1]-=np.sin(k*result[...,0])/k
        result[...,0]-=np.sin(k*result[...,1])/k
    return result


def _near_site_pool(uv, losses, limit=32):
    """Keep lowest-error sites and best representatives across the full tile.

    This finite proposal pool is not an exhaustion certificate. Original
    rules still score every joint pose, including bilinear colors between
    sites. Half the pool favors color, half prevents a single basin from
    consuming all proposals.
    """
    order = np.argsort(losses, kind='stable')
    cells = np.minimum((uv * 4).astype(int), 3)
    cell_ids = cells[:, 1] * 4 + cells[:, 0]
    _, positions = np.unique(cell_ids[order], return_index=True)
    diverse = order[np.sort(positions)]
    selected = list(dict.fromkeys([*order[:limit//2], *diverse, *order[:limit]]))[:limit]
    return inverse_periodic_uv(uv[selected]) % 1.


def search_periodic_targets(session,rules,*,minimum_scale,maximum_scale,
        reference=None,subpixel_fractions=(0.,),top_k=32,time_budget_seconds=5.,
        clock=time.monotonic,check=lambda:None):
    """Solve two target sites for scale/angle; validate all enabled pickers.

    All matching sites on the supplied subpixel lattice are retained. No
    eight-pixel or local-pose cutoff applies. Relative tile lifts follow the
    picker distance and scale range; common lifts choose the nearest periodic
    representative to the reference pose. Time exhaustion is explicit.
    """
    if (not all(math.isfinite(v) for v in (minimum_scale,maximum_scale,time_budget_seconds))
        or not 0<minimum_scale<=maximum_scale or time_budget_seconds<=0
        or type(top_k) is not int or not 1<=top_k<=256):raise ValueError('Invalid periodic search bounds')
    fractions=tuple(float(v) for v in subpixel_fractions)
    if not fractions or len(fractions)>8 or any(not math.isfinite(v) or not 0<=v<1 for v in fractions):
        raise ValueError('Invalid sample fractions')
    count=validate_region_rules(session,rules)
    reference=_pose(session['initial_pose'] if reference is None else reference)
    start=clock();end=start+time_budget_seconds
    result=dict(candidates=[],domain=dict(translation='one_full_canonical_period',
        canonical_uv_bounds=[[0.,1.],[0.,1.]],scale=[minimum_scale,maximum_scale],
        rotation_degrees=[-180.,180.]),target_sites_per_region=[0]*count,
        sample_fractions=list(fractions),site_scan_complete=False,pair_lattice_complete=False,
        continuous_complete=False,stop_reason='not_started',pair_proposals=0,cpu_evaluations=0,
        cpu_pool_complete=False,peak_pair_block_size=0,
        execution_verified=False,coverage='All matching sites on finite subpixel lattice; continuous regions not exhausted')
    enabled_regions=[i for i,r in enumerate(rules) if r['enabled']]
    prioritized=priority_indices(rules)
    result['enabled_regions']=enabled_regions
    nearest=None
    nearest_key=None
    class Expired(Exception):pass
    def guard():
        check()
        if clock()>=end:raise Expired()
    sites={};near_sites={};near_samples={};retained={};evaluated_poses=set();nearest_rows={}
    def retained_rank(row):
        if prioritized is None:return (row['model_cost'],)
        prediction=row['prediction']
        ordered=priority_components(prediction['colors'],rules,prediction['deltas'])
        values=[prediction['deltas'][i] for i in enabled_regions]
        return (not prediction['predicted_accepted'],*ordered,max(values),sum(values)/len(values),row['model_cost'])
    def offer(anchor,z,scale,angle):
        nonlocal nearest,nearest_key
        guard()
        theta=math.radians(angle);rotation=np.array([[math.cos(theta),-math.sin(theta)],
                                                   [math.sin(theta),math.cos(theta)]])
        ref_uv=picker_view_uv(anchor,count,session['picker_uv'][anchor][1],reference['position'],scale,angle)
        lift=np.rint(ref_uv-z)
        position=np.asarray(session['picker_uv'][anchor])-.5-scale*(rotation@(z+lift))
        pose=_pose(dict(position=position,scale=scale,rotation_degrees=angle))
        key=(*pose['position'],pose['scale'],pose['rotation_degrees'])
        if key in evaluated_poses:return
        prediction=score_native_pose(session,pose,rules,check=guard);result['cpu_evaluations']+=1
        evaluated_poses.add(key)
        cost=float(np.linalg.norm(np.asarray(pose['position'])-reference['position']))+abs(math.log(scale/reference['scale']))
        cost+=abs((angle-reference['rotation_degrees']+180)%360-180)/180
        values=[float(prediction['deltas'][i]) for i in enabled_regions
                if prediction['deltas'][i] is not None]
        exact_hits=sum(prediction['colors'][i] in rules[i]['colors']
                       for i in enabled_regions if rules[i]['exact'])
        ordered=priority_components(prediction['colors'],rules,prediction['deltas'])
        quality=((*((not prediction['predicted_accepted'],*ordered) if ordered is not None else ()),
                  max(values,default=float('inf')),sum(values)/len(values) if values else float('inf'),-exact_hits,cost))
        row=dict(native_pose=pose,prediction=prediction,model_cost=cost,
                 source='joint_periodic_nearest',execution_verified=False,input_reachability='unverified')
        nearest_rows[key]=(quality,row)
        if len(nearest_rows)>top_k:
            del nearest_rows[max(nearest_rows,key=lambda k:nearest_rows[k][0])]
        if nearest is None or quality<nearest_key:
            nearest_key=quality
            nearest=row
        if not prediction['predicted_accepted']:return
        retained[key]=dict(native_pose=pose,prediction=prediction,model_cost=cost,
            source='joint_periodic_target_sites',execution_verified=False,input_reachability='unverified')
        if len(retained)>top_k:
            del retained[max(retained,key=lambda k:retained_rank(retained[k]))]
    try:
        enabled=([i for i,r in enumerate(rules) if r['enabled']] if prioritized is None else prioritized)
        for i in enabled:
            guard();pixels=session['pixels'][i];h,w=pixels.shape[:2]
            matched=[];sampled_uv=[];sampled_losses=[]
            for fy,fx in itertools.product(fractions,repeat=2):
                guard()
                uv,colors,color_lab=periodic_samples(session,i,fy,fx,check=guard)
                mask=np.zeros(len(colors),bool);rule=rules[i]
                losses=np.full(len(colors),np.inf)
                for target in rule['colors']:
                    guard();target_rgb=np.asarray(rgb(target))
                    delta=np.linalg.norm(color_lab-lab([target_rgb])[0],axis=1)
                    losses=np.minimum(losses,delta)
                    if rule['exact']:mask|=np.all(colors==target_rgb,axis=1)
                    else:mask|=delta<=rule['tolerance']
                matched.append(inverse_periodic_uv(uv[mask])%1.)
                sampled_uv.append(uv);sampled_losses.append(losses)
            guard();sites[i]=np.unique(np.concatenate(matched),axis=0)
            result['target_sites_per_region'][i]=len(sites[i])
            if not len(sites[i]):
                near_samples[i]=(np.concatenate(sampled_uv),np.concatenate(sampled_losses))
                near_sites[i]=_near_site_pool(*near_samples[i])
        result['site_scan_complete']=True
        missing=[i for i in enabled if not len(sites[i])]
        result['missing_target_regions']=missing
        result['near_sites_per_region']=[len(near_sites.get(i,())) for i in range(count)]
        # Missing material targets participate through near sites; none of
        # these sites changes an acceptance target or becomes an exact hit.
        for i in missing:sites[i]=near_sites[i]
        available=[i for i in enabled if len(sites[i])]
        result['near_expansion_tiers']=[32] if missing else []
        def expand_near(limit):
            guard();changed=False
            for i in missing:
                uv,losses=near_samples[i]
                proposed=_near_site_pool(uv,losses,min(limit,len(uv)))
                merged=np.unique(np.concatenate((sites[i],proposed)),axis=0)
                changed|=len(merged)>len(sites[i]);sites[i]=merged
                result['near_sites_per_region'][i]=len(merged)
            if changed:result['near_expansion_tiers'].append(limit)
            return changed
        initial=score_native_pose(session,reference,rules,check=guard)
        if initial['predicted_accepted']:
            retained[tuple((*reference['position'],reference['scale'],reference['rotation_degrees']))]=dict(
                native_pose=reference,prediction=initial,model_cost=0.,source='current_periodic_reference',
                execution_verified=False,input_reachability='unverified')
            result['stop_reason']='current_target_accepted'
        elif not available:
            result['stop_reason']='target_not_present_on_sample_lattice'
        elif len(available)==1:
            i=available[0]
            ref=picker_view_uv(i,count,session['picker_uv'][i][1],**reference)
            tiers=(32,128,512,len(near_samples[i][0])) if i in missing else (32,)
            for tier in dict.fromkeys(tiers):
                if tier!=32 and not expand_near(tier):continue
                distances=np.linalg.norm((sites[i]-ref+.5)%1.-.5,axis=1)
                for z in sites[i][np.argsort(distances)]:
                    offer(i,z,reference['scale'],reference['rotation_degrees'])
                    if len(retained)>=top_k:break
            result['stop_reason']=('target_not_present_on_sample_lattice' if missing else
                'solutions_found' if retained else 'site_lattice_exhausted')
        else:
            pair_pool_complete=[]
            def scan_pair(a,b):
                delta=np.asarray(session['picker_uv'][b])-session['picker_uv'][a]
                length=np.linalg.norm(delta)
                bound=math.ceil(length/minimum_scale+1.)
                offsets=sorted(itertools.product(range(-bound,bound+1),repeat=2),key=lambda v:v[0]*v[0]+v[1]*v[1])
                proposals=[];near_proposals=[];serial=0;pool_size=max(256,top_k*8)
                third=next((i for i in enabled if i not in (a,b)),None)
                if third is not None:
                    d3=np.asarray(session['picker_uv'][third])-session['picker_uv'][a]
                    third_ratio=complex(*d3)/complex(*delta)
                def offer_heap(heap,quality,slot,qa,scales,angles,capacity):
                    nonlocal serial
                    serial+=1
                    reverse=(tuple(-float(v) for v in quality) if isinstance(quality,tuple) else -float(quality))
                    row=(reverse,serial,qa[slot].copy(),float(scales[slot]),float(angles[slot]))
                    if len(heap)<capacity:heapq.heappush(heap,row)
                    elif reverse > heap[0][0]:heapq.heapreplace(heap,row)
                def heap_quality(row):
                    reverse=row[0]
                    return tuple(-v for v in reverse) if isinstance(reverse,tuple) else -reverse
                def verify_pool():
                    # Verify as soon as a block produces proposals. A deadline
                    # during later enumeration must not discard already found
                    # targets. Keep scanning the full lattice for better routes.
                    for negative_cost,_,qa,scale,angle in sorted(proposals,key=lambda row:-row[0]):
                        if (prioritized is None and len(retained)>=top_k and
                                -negative_cost>=max(row['model_cost'] for row in retained.values())):
                            break
                        offer(a,qa,scale,angle)
                        if abs((angle-reference['rotation_degrees']+180)%360-180)<.1:
                            offer(a,qa,scale,reference['rotation_degrees'])
                for offset in offsets:
                    for first in range(0,len(sites[a]),32):
                        guard();anchors=sites[a][first:first+32]
                        for other_first in range(0,len(sites[b]),1024):
                            guard();others=sites[b][other_first:other_first+1024]
                            difference=others[None,:,:]+offset-anchors[:,None,:]
                            distance=np.linalg.norm(difference,axis=2)
                            mask=(distance>0)&(distance>=length/maximum_scale)&(distance<=length/minimum_scale)
                            ia,ib=np.nonzero(mask)
                            result['pair_proposals']+=distance.size
                            result['peak_pair_block_size']=max(result['peak_pair_block_size'],distance.size)
                            if not len(ia):continue
                            selected=difference[ia,ib]
                            angles=(np.degrees(np.arctan2(delta[1],delta[0])-np.arctan2(selected[:,1],selected[:,0]))+180)%360-180
                            scales=length/distance[ia,ib];theta=np.radians(angles)
                            c,s=np.cos(theta),np.sin(theta)
                            screen=np.asarray(session['picker_uv'][a])-.5-reference['position']
                            ref_z=np.column_stack((c*screen[0]+s*screen[1],-s*screen[0]+c*screen[1]))/scales[:,None]
                            qa=anchors[ia]
                            lifted=qa+np.rint(ref_z-qa)
                            positions=np.asarray(session['picker_uv'][a])-.5-scales[:,None]*np.column_stack(
                                (c*lifted[:,0]-s*lifted[:,1],s*lifted[:,0]+c*lifted[:,1]))
                            costs=np.linalg.norm(positions-reference['position'],axis=1)+np.abs(np.log(scales/reference['scale']))
                            costs+=np.abs((angles-reference['rotation_degrees']+180)%360-180)/180
                            if third is not None:
                                # Screen the third picker before geometry-cost
                                # pruning. Vector arithmetic is only a broad
                                # screen; every retained pose still uses the
                                # original scalar float32 picker for acceptance.
                                z3=qa+np.column_stack((third_ratio.real*selected[:,0]-third_ratio.imag*selected[:,1],
                                                      third_ratio.imag*selected[:,0]+third_ratio.real*selected[:,1]))
                                channels=sample_cpu(session['pixels'][third],distort_uv(z3),session['color_preserve_ratio'])
                                colors=color32(channels/np.float32(255));rule=rules[third]
                                target_colors=np.asarray([rgb(code) for code in rule['colors']])
                                losses=np.min(np.linalg.norm(lab(colors)[:,None,:]-lab(target_colors)[None,:,:],axis=2),axis=1)
                                if rule['exact']:
                                    screen=np.any(np.max(np.abs(channels[:,None,:]-target_colors[None,:,:]),axis=2)<=1.,axis=1)
                                else:screen=losses<=rule['tolerance']+1.
                                result['third_screened_pairs']=result.get('third_screened_pairs',0)+len(colors)
                                result['third_screen_survivors']=result.get('third_screen_survivors',0)+int(np.sum(screen))
                                # Preserve low-error nonexact targets as route
                                # seeds, instead of exporting them only as logs.
                                if prioritized is None:
                                    near_quality=losses+costs*1e-6
                                    indices=np.flatnonzero(near_quality < -near_proposals[0][0]) if len(near_proposals)==top_k else np.arange(len(costs))
                                    if len(indices)>top_k:
                                        indices=indices[np.argpartition(near_quality[indices],top_k-1)[:top_k]]
                                    for slot in indices:offer_heap(near_proposals,near_quality[slot],slot,qa,scales,angles,top_k)
                                else:
                                    # Screen every material before pruning this
                                    # nearest pool. A low-priority third loss
                                    # must not discard a higher-priority hit.
                                    all_colors=[None]*count;all_losses=[None]*count
                                    for region in enabled:
                                        guard()
                                        ratio=complex(*(np.asarray(session['picker_uv'][region])-session['picker_uv'][a]))/complex(*delta)
                                        z=qa+np.column_stack((ratio.real*selected[:,0]-ratio.imag*selected[:,1],
                                                            ratio.imag*selected[:,0]+ratio.real*selected[:,1]))
                                        vals=color32(sample_cpu(session['pixels'][region],distort_uv(z),
                                            session['color_preserve_ratio'])/np.float32(255))
                                        targets=np.asarray([rgb(code) for code in rules[region]['colors']])
                                        all_colors[region]=vals
                                        all_losses[region]=np.min(np.linalg.norm(lab(vals)[:,None,:]-lab(targets)[None,:,:],axis=2),axis=1)
                                    priority=vector_priority_components(all_colors,all_losses,rules)
                                    accepted=np.all(priority[:,::2]==0,axis=1)
                                    maximum=np.maximum.reduce([all_losses[i] for i in enabled])
                                    average=np.mean([all_losses[i] for i in enabled],axis=0)
                                    quality=np.column_stack((~accepted,priority,maximum,average,costs))
                                    indices=np.lexsort(tuple(quality[:,j] for j in range(quality.shape[1]-1,-1,-1)))[:top_k]
                                    for slot in indices:offer_heap(near_proposals,tuple(quality[slot]),slot,qa,scales,angles,top_k)
                                viable=np.flatnonzero(screen)
                            else:viable=np.arange(len(costs))
                            if len(proposals)==pool_size:viable=viable[costs[viable] < -proposals[0][0]]
                            if len(viable)>pool_size:
                                viable=viable[np.argpartition(costs[viable],pool_size-1)[:pool_size]]
                            guard()
                            for slot in viable:
                                offer_heap(proposals,float(costs[slot]),slot,qa,scales,angles,pool_size)
                            result['candidate_pool_retained']=len(proposals)
                            verify_pool()
                            if near_proposals:
                                for _,_,anchor,scale,angle in sorted(near_proposals,key=heap_quality)[:2]:
                                    offer(a,anchor,scale,angle)
                result['candidate_pool_retained']=len(proposals)
                verify_pool()
                result['cpu_pool_complete']=len(retained)<top_k
                for _,_,qa,scale,angle in sorted(near_proposals,key=heap_quality):offer(a,qa,scale,angle)
                pair_pool_complete.append(result['cpu_pool_complete'])
            result['pair_lattice_complete']=False
            # An absent target on one material cannot suppress joint poses for
            # the others. Score every pose with all original rules: partial hits
            # remain ranked compromises, never accepted full-target candidates.
            pairs=list(itertools.combinations(sorted(available,key=lambda i:len(sites[i]))
                                             if prioritized is None else available,2))
            tiers=(32,128,512,max(len(near_samples[i][0]) for i in missing)) if missing else (32,)
            for tier in dict.fromkeys(tiers):
                if tier!=32 and not expand_near(tier):continue
                for a,b in pairs:
                    guard();scan_pair(a,b)
                    result['pairs_completed']=result.get('pairs_completed',0)+1
            result['pair_lattice_complete']=True
            result['cpu_pool_complete']=all(pair_pool_complete)
            result['stop_reason']=('target_not_present_on_sample_lattice' if missing else
                'solutions_found' if retained else 'no_verified_solution_in_retained_pool')
    except Expired:result['stop_reason']='deadline'
    check()
    result['candidates']=sorted(retained.values(),key=retained_rank)[:top_k]
    result['nearest_candidate']=nearest
    result['nearest_prediction']=nearest['prediction'] if nearest else None
    result['nearest_pose']=nearest['native_pose'] if nearest else None
    result['nearest_candidates']=[row for _,row in sorted(nearest_rows.values(),key=lambda value:value[0])]
    result['elapsed_seconds']=max(0.,clock()-start)
    return result
