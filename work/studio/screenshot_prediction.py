"""Whole RGB endpoint observations. Nearby target pixels are not endpoint colors."""
import numpy as np
from scipy.spatial import cKDTree
from screenshot_compute import cooperative_compute

class VisibleColorField:
    def __init__(self,image,masks):
        self.image=np.asarray(image);self.masks=np.asarray(masks)

    def __call__(self,points,indices):
        points=np.asarray(points);xy=np.rint(points).astype(int)
        height,width=self.image.shape[:2]
        valid=(xy[...,0]>=0)&(xy[...,0]<width)&(xy[...,1]>=0)&(xy[...,1]<height)
        x=np.clip(xy[...,0],0,width-1);y=np.clip(xy[...,1],0,height-1)
        for n,i in enumerate(indices):valid[:,n]&=self.masks[i,y[:,n],x[:,n]]
        return self.image[y,x].copy(),valid,np.linalg.norm(points-xy,axis=2)

class ObservedColorField:
    """Accumulated nonperiodic RGB observations for the visible fallback."""
    def __init__(self,period):self.period=float(period);self.rows=[];self.trees=None
    def add_frame(self,image,masks,pose,check=lambda:None):
        self.trees=None
        inverse=np.linalg.inv(pose)
        if not self.rows:self.rows=[[] for _ in range(len(masks))]
        for i,mask in enumerate(masks):
            check();y,x=np.where(mask)
            if len(x):
                points=np.column_stack((x,y))@inverse[:2,:2].T+inverse[:2,2]
                self.rows[i].append((points.astype(np.float32),image[y,x].copy(),float(np.hypot(pose[0,0],pose[1,0]))))
        self.trees=None
    def prepare(self,check=lambda:None):
        if self.trees is None:
            trees=[]
            for chunks in self.rows:
                check()
                def build(chunks=tuple(chunks)):
                    points=np.concatenate([c[0] for c in chunks]) if chunks else np.empty((0,2))
                    colors=np.concatenate([c[1] for c in chunks]) if chunks else np.empty((0,3),np.uint8)
                    if len(points):
                        scales=np.concatenate([np.full(len(c[0]),c[2]) for c in chunks])
                        keys=np.floor(points*4).astype(np.int64)
                        order=np.lexsort((-scales,keys[:,1],keys[:,0]))
                        keys=keys[order];keep=np.r_[True,np.any(keys[1:]!=keys[:-1],axis=1)]
                        points=points[order][keep];colors=colors[order][keep]
                    return (cKDTree(points),colors) if len(points) else (None,colors)
                trees.append(cooperative_compute(build,check))
            self.trees=trees
    def __call__(self,points,indices):
        self.prepare();points=np.asarray(points);rgb=np.full((*points.shape[:2],3),255,np.uint8)
        valid=np.zeros(points.shape[:2],bool);offsets=np.full(points.shape[:2],np.inf)
        for n,i in enumerate(indices):
            tree,colors=self.trees[i]
            if tree is None:continue
            distance,slot=tree.query(points[:,n]);rgb[:,n]=colors[slot];valid[:,n]=distance<=.75;offsets[:,n]=distance
        return rgb,valid,offsets

FIELD_DTYPE=np.dtype([('key','i8'),('point','f4',(2,)),('rgb','u1',(3,)),('scale','f4')])

class _PhasePage:
    """Stable phase slots; only incoming keys touch previously observed RGB."""
    size=16384
    def __init__(self):
        self.slots=None;self.keys=np.empty(0,np.int64);self.indices=np.empty(0,np.int32)
        self.data=np.empty(0,FIELD_DTYPE);self.count=0

    def update(self,row):
        local=row['key']%self.size
        if self.slots is not None:slots=self.slots[local]
        else:
            slots=np.full(len(row),-1,np.int32)
            positions=np.searchsorted(self.keys,local);valid=positions<len(self.keys)
            positions=np.minimum(positions,max(0,len(self.keys)-1))
            if len(self.keys):
                valid&=self.keys[positions]==local;slots[valid]=self.indices[positions[valid]]
        existing=slots>=0
        if existing.any():
            incoming=row[existing];destination=slots[existing]
            better=incoming['scale']>self.data['scale'][destination]
            self.data[destination[better]]=incoming[better]
        new=row[~existing];n=len(new)
        if not n:return
        end=self.count+n
        if end>len(self.data):
            data=np.empty(min(self.size,max(end,max(32,len(self.data)*2))),FIELD_DTYPE)
            data[:self.count]=self.data[:self.count];self.data=data
        self.data[self.count:end]=new
        new_keys=new['key']%self.size;new_indices=np.arange(self.count,end,dtype=np.int32)
        if self.slots is not None:self.slots[new_keys]=new_indices
        else:
            keys=np.concatenate((self.keys,new_keys));indices=np.concatenate((self.indices,new_indices))
            if end>=2048:
                self.slots=np.full(self.size,-1,np.int32);self.slots[keys]=indices
                self.keys=np.empty(0,np.int64);self.indices=np.empty(0,np.int32)
            else:
                order=np.argsort(keys);self.keys=keys[order];self.indices=indices[order]
        self.count=end

class PeriodicColorField:
    def __init__(self,period,count):
        self.period=period;self.pages=[{} for _ in range(count)]
        self.trees=None;self._rows=None

    @property
    def rows(self):
        return self.export_rows()

    def export_rows(self,check=lambda:None):
        if self._rows is None:
            rows=[]
            for pages in self.pages:
                parts=[]
                for key in sorted(pages):
                    check()
                    page=pages[key];row=page.data[:page.count]
                    parts.append(row[np.argsort(row['key'],kind='stable')])
                rows.append(np.concatenate(parts) if parts else np.empty(0,FIELD_DTYPE))
            self._rows=rows
        return self._rows

    def add(self,image,masks,pose,check=lambda:None):
        self.trees=None;self._rows=None
        inverse=np.linalg.inv(pose);phase_width=int(np.ceil(self.period*4))
        for i,mask in enumerate(masks):
            check();y,x=np.where(mask)
            if not len(x):continue
            points=np.mod(np.column_stack((x,y))@inverse[:2,:2].T+inverse[:2,2],self.period)
            row=np.empty(len(x),FIELD_DTYPE);keys=np.floor(points*4).astype(np.int64)
            row['key']=keys[:,0]*phase_width+keys[:,1];row['point']=points;row['rgb']=image[y,x]
            row['scale']=np.hypot(pose[0,0],pose[1,0])
            check()
            # Within this frame scale is constant. First source pixel wins
            # tied keys exactly as the old stable lexsort did. Old equal-scale
            # observations keep their RGB; a finer frame replaces whole rows.
            _,first=np.unique(row['key'],return_index=True)
            row=row[first];page_ids=row['key']//_PhasePage.size
            boundaries=np.r_[0,np.flatnonzero(page_ids[1:]!=page_ids[:-1])+1,len(row)]
            for start,end in zip(boundaries[:-1],boundaries[1:]):
                check();key=int(page_ids[start]);page=self.pages[i].get(key)
                if page is None:page=self.pages[i][key]=_PhasePage()
                page.update(row[start:end])
        self.trees=None

    def prepare(self,check=lambda:None):
        if self.trees is None:
            trees=[]
            for row in self.export_rows(check):
                check();trees.append(cooperative_compute(
                    lambda row=row:cKDTree(np.mod(row['point'].astype(float),self.period),boxsize=self.period),check) if len(row) else None)
            self.trees=trees

    def __call__(self,points,indices):
        self.prepare();points=np.mod(points,self.period)
        rgb=np.full((*points.shape[:2],3),255,np.uint8)
        offsets=np.full(points.shape[:2],np.inf);valid=np.zeros(points.shape[:2],bool)
        for n,i in enumerate(indices):
            tree=self.trees[i]
            if tree is None:continue
            distance,slot=tree.query(points[:,n])
            rgb[:,n]=self.rows[i]['rgb'][slot];offsets[:,n]=distance;valid[:,n]=True
        return rgb,valid,offsets
