"""Preserve observed whole RGB samples and their periodic fractional phase."""
import cv2,numpy as np
from vision import rgb,lab
from color_matching import matching_distances,has_chromatic_target

SAMPLE_DTYPE=np.dtype([('key','i8'),('point','f8',(2,)),('rgb','u1',(3,)),('score','f8'),('margin','f4')])
SAMPLE_CHUNK=65536

def distances(values,rule):
    values=np.asarray(values).reshape(-1,3)
    if not len(values):return np.empty(0)
    targets=np.array([rgb(c) for c in rule['colors']],np.int16)
    if rule['exact']:
        result=np.full(len(values),np.inf)
        signed=values.astype(np.int16)
        for target in targets:result=np.minimum(result,np.max(np.abs(signed-target),axis=1))
        return result
    actual=lab(values);result=np.full(len(values),np.inf)
    for target in lab(targets):result=np.minimum(result,np.linalg.norm(actual-target,axis=1))
    return result


def sample_metrics(values,rule):
    """Share Lab conversion; acceptance never consumes preference scores."""
    values=np.asarray(values).reshape(-1,3)
    if not len(values):return np.empty(0),np.empty(0)
    actual=lab(values)
    if rule['exact']:
        targets=np.array([rgb(c) for c in rule['colors']],np.int16)
        delta=np.full(len(values),np.inf)
        for target in targets:delta=np.minimum(delta,np.max(np.abs(values.astype(np.int16)-target),axis=1))
    else:
        delta=np.full(len(values),np.inf)
        for target in lab([rgb(c) for c in rule['colors']]):delta=np.minimum(delta,np.linalg.norm(actual-target,axis=1))
    quality=(matching_distances(values,rule,color_lab=actual,
                              base_distances=None if rule['exact'] else delta)
             if has_chromatic_target(rule) else delta)
    return delta,quality


def select_site_indices(points,colors,rule,period,limit,*,matched=False):
    """Explore different phases before dense tied scan lines; never erase sites."""
    points=np.asarray(points);values,quality=sample_metrics(colors,rule)
    hits=values<=(0 if rule['exact'] else rule['tolerance'])
    order=np.lexsort((quality,~hits))
    if matched:order=order[values[order]<=(0 if rule['exact'] else rule['tolerance'])]
    if limit is None or len(order)<=limit:return order
    # Input order breaks equal-color ties using measured plateau interior.
    # One best site from each spatial cell gives the first tier broad coverage.
    side=max(2,int(np.ceil(np.sqrt(limit))))
    cells=np.floor(np.mod(points[order],period)*side/period).astype(int)
    keys=cells[:,0]*side+cells[:,1]
    _,first=np.unique(keys,return_index=True)
    representatives=order[np.sort(first)]
    chosen=representatives[:limit]
    if len(chosen)<limit:
        remainder=order[~np.isin(order,chosen)]
        chosen=np.r_[chosen,remainder[:limit-len(chosen)]]
    return chosen

class RawSamples:
    def __init__(self,period,rules):
        if not np.isfinite(period) or period<=0:raise ValueError('Measured positive image period required')
        self.period=float(period);self.rules=rules
        self.rows=[np.empty(0,SAMPLE_DTYPE) for _ in rules];self.frames=0
        from screenshot_prediction import PeriodicColorField
        self.color_field=PeriodicColorField(self.period,len(rules))

    @property
    def storage_bytes(self):return sum(row.nbytes for row in self.rows)

    def add(self,image,masks,pose,check=lambda:None):
        check()
        inverse=np.linalg.inv(np.asarray(pose,float))
        if np.asarray(masks).shape!=(len(self.rules),*image.shape[:2]):raise ValueError('Actual region masks required')
        width=image.shape[1];flat_image=image.reshape(-1,3)
        phase_width=int(np.ceil(self.period*4))
        target_masks={}
        for index,(mask,rule) in enumerate(zip(masks,self.rules)):
            if not rule['enabled']:continue
            targets=tuple(rule['colors'])
            if targets not in target_masks:
                target_pixels=np.zeros(image.shape[:2],bool)
                for target in targets:target_pixels|=np.all(image==rgb(target),axis=2)
                target_masks[targets]=target_pixels
            target_pixels=target_masks[targets]
            # A higher interior margin survives subpixel placement better.
            # It changes traversal only, never RGB or acceptance rules.
            interior=cv2.distanceTransform(np.uint8(target_pixels & mask),cv2.DIST_L2,5)
            scale=max(1e-12,float(np.hypot(pose[0,0],pose[1,0])))
            chunks=[];minimum=float('inf');raw_minimum=float('inf');flat_mask=mask.reshape(-1)
            for start in range(0,len(flat_mask),SAMPLE_CHUNK):
                check()
                pixels=np.flatnonzero(flat_mask[start:start+SAMPLE_CHUNK])+start
                if not len(pixels):continue
                values=flat_image[pixels];raw,quality=sample_metrics(values,rule)
                # A valid target survives preference pruning even with a wide
                # user tolerance. Other sites use the shared hue-aware score.
                hit=raw<=(0 if rule['exact'] else rule['tolerance'])
                score=np.where(hit,0.,quality)
                if not len(score):continue
                minimum=min(minimum,float(score.min()))
                raw_minimum=min(raw_minimum,float(raw.min()))
                selected=(score<=max(minimum+24,16)) | (raw<=max(raw_minimum+24,16))
                pixels,values,score=pixels[selected],values[selected],score[selected]
                points=np.mod(np.column_stack((pixels%width,pixels//width))@inverse[:2,:2].T+inverse[:2,2],self.period)
                keys=np.floor(points*4).astype(np.int64)
                rows=np.empty(len(points),SAMPLE_DTYPE)
                rows['key']=keys[:,0]*phase_width+keys[:,1]
                rows['point']=points;rows['rgb']=values;rows['score']=score
                rows['margin']=interior.reshape(-1)[pixels]/scale
                chunks.append(rows)
            if not chunks:continue
            check()
            fresh=np.concatenate(chunks)
            # Both the traditional and identity-aware seeds remain available.
            # The complete original-color field below retains all observed
            # sites for endpoint scoring; this is not an exhaustion filter.
            # Compact arrays retain whole observed RGB and all distinct phases.
            # Sorting keeps the closest raw observation per phase; ties keep
            # the older observation, with no channel mixing or point thinning.
            merged=np.concatenate((self.rows[index],fresh))
            check()
            from screenshot_compute import cooperative_compute
            order=cooperative_compute(lambda merged=merged:np.lexsort(
                (-merged['margin'],merged['score'],merged['key'])),check)
            merged=merged[order]
            selected=np.r_[True,merged['key'][1:]!=merged['key'][:-1]]
            check()
            self.rows[index]=merged[selected]
        self.color_field.add(image,masks,pose,check)
        self.frames+=1

    def sites(self,index,check=None):
        rows=self.rows[index]
        def export():
            ordered=rows[np.lexsort((-rows['margin'],rows['score']))]
            return ordered['point'].copy(),ordered['rgb'].copy(),ordered['score'].copy()
        if check is None:return export()
        from screenshot_compute import cooperative_compute
        return cooperative_compute(export,check)

    def arrays(self,check=None):
        rows=[self.sites(i,check) for i in range(len(self.rules))]
        return [v[0] for v in rows],[v[1] for v in rows]

    def save(self,path):
        rows=[self.sites(i) for i in range(len(self.rules))]
        np.savez_compressed(path,period=self.period,
            **{f'points_{i}':row[0] for i,row in enumerate(rows)},
            **{f'rgb_{i}':row[1] for i,row in enumerate(rows)})

    def save_background(self,path,writer):
        # Current row arrays are owned snapshots, replaced by later additions.
        # Sort/compress diagnostics on the writer, outside the game deadline.
        rows=tuple(self.rows);period=self.period
        def save():
            ordered=[row[np.lexsort((-row['margin'],row['score']))] for row in rows]
            np.savez_compressed(path,period=period,
                **{f'points_{i}':row['point'] for i,row in enumerate(ordered)},
                **{f'rgb_{i}':row['rgb'] for i,row in enumerate(ordered)})
        writer.submit_task(save)
