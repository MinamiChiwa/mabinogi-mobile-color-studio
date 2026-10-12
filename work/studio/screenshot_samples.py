"""Preserve observed whole RGB samples and their periodic fractional phase."""
import numpy as np
from vision import rgb,lab

SAMPLE_DTYPE=np.dtype([('key','i8'),('point','f8',(2,)),('rgb','u1',(3,)),('score','f8')])
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

class RawSamples:
    def __init__(self,period,rules):
        if not np.isfinite(period) or period<=0:raise ValueError('Measured positive image period required')
        self.period=float(period);self.rules=rules
        self.rows=[np.empty(0,SAMPLE_DTYPE) for _ in rules];self.frames=0

    @property
    def storage_bytes(self):return sum(row.nbytes for row in self.rows)

    def add(self,image,masks,pose,check=lambda:None):
        check()
        inverse=np.linalg.inv(np.asarray(pose,float))
        if np.asarray(masks).shape!=(len(self.rules),*image.shape[:2]):raise ValueError('Actual region masks required')
        width=image.shape[1];flat_image=image.reshape(-1,3)
        phase_width=int(np.ceil(self.period*4))
        for index,(mask,rule) in enumerate(zip(masks,self.rules)):
            if not rule['enabled']:continue
            chunks=[];minimum=float('inf');flat_mask=mask.reshape(-1)
            for start in range(0,len(flat_mask),SAMPLE_CHUNK):
                check()
                pixels=np.flatnonzero(flat_mask[start:start+SAMPLE_CHUNK])+start
                if not len(pixels):continue
                values=flat_image[pixels];score=distances(values,rule)
                if not len(score):continue
                minimum=min(minimum,float(score.min()))
                selected=score<=max(minimum+24,16)
                pixels,values,score=pixels[selected],values[selected],score[selected]
                points=np.mod(np.column_stack((pixels%width,pixels//width))@inverse[:2,:2].T+inverse[:2,2],self.period)
                keys=np.floor(points*4).astype(np.int64)
                rows=np.empty(len(points),SAMPLE_DTYPE)
                rows['key']=keys[:,0]*phase_width+keys[:,1]
                rows['point']=points;rows['rgb']=values;rows['score']=score
                chunks.append(rows)
            if not chunks:continue
            check()
            fresh=np.concatenate(chunks)
            fresh=fresh[fresh['score']<=max(minimum+24,16)]
            # Compact arrays retain whole observed RGB and all distinct phases.
            # Sorting keeps the closest raw observation per phase; ties keep
            # the older observation, with no channel mixing or point thinning.
            merged=np.concatenate((self.rows[index],fresh))
            check()
            order=np.lexsort((merged['score'],merged['key']))
            merged=merged[order]
            selected=np.r_[True,merged['key'][1:]!=merged['key'][:-1]]
            check()
            self.rows[index]=merged[selected]
        self.frames+=1

    def sites(self,index):
        rows=self.rows[index]
        order=np.argsort(rows['score'],kind='stable');rows=rows[order]
        return rows['point'].copy(),rows['rgb'].copy(),rows['score'].copy()

    def arrays(self):
        rows=[self.sites(i) for i in range(len(self.rules))]
        return [v[0] for v in rows],[v[1] for v in rows]

    def save(self,path):
        rows=[self.sites(i) for i in range(len(self.rules))]
        np.savez_compressed(path,period=self.period,
            **{f'points_{i}':row[0] for i,row in enumerate(rows)},
            **{f'rgb_{i}':row[1] for i,row in enumerate(rows)})
