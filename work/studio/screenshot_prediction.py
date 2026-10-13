"""Whole RGB endpoint observations. Nearby target pixels are not endpoint colors."""
import numpy as np
from scipy.spatial import cKDTree

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
                points=np.concatenate([c[0] for c in chunks]) if chunks else np.empty((0,2))
                colors=np.concatenate([c[1] for c in chunks]) if chunks else np.empty((0,3),np.uint8)
                if len(points):
                    scales=np.concatenate([np.full(len(c[0]),c[2]) for c in chunks])
                    keys=np.floor(points*4).astype(np.int64)
                    order=np.lexsort((-scales,keys[:,1],keys[:,0]))
                    keys=keys[order];keep=np.r_[True,np.any(keys[1:]!=keys[:-1],axis=1)]
                    points=points[order][keep];colors=colors[order][keep]
                trees.append((cKDTree(points),colors) if len(points) else (None,colors))
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

class PeriodicColorField:
    def __init__(self,period,count):
        self.period=period;self.rows=[np.empty(0,FIELD_DTYPE) for _ in range(count)]
        self.trees=None

    def add(self,image,masks,pose,check=lambda:None):
        self.trees=None
        inverse=np.linalg.inv(pose);phase_width=int(np.ceil(self.period*4))
        for i,mask in enumerate(masks):
            check();y,x=np.where(mask)
            if not len(x):continue
            points=np.mod(np.column_stack((x,y))@inverse[:2,:2].T+inverse[:2,2],self.period)
            row=np.empty(len(x),FIELD_DTYPE);keys=np.floor(points*4).astype(np.int64)
            row['key']=keys[:,0]*phase_width+keys[:,1];row['point']=points;row['rgb']=image[y,x]
            row['scale']=np.hypot(pose[0,0],pose[1,0])
            merged=np.concatenate((self.rows[i],row));check()
            # A finer observed image wins within a quarter-pixel phase cell.
            # Each RGB remains one complete captured pixel; no averaging.
            order=np.lexsort((-merged['scale'],merged['key']));merged=merged[order]
            self.rows[i]=merged[np.r_[True,merged['key'][1:]!=merged['key'][:-1]]]
        self.trees=None

    def prepare(self,check=lambda:None):
        if self.trees is None:
            trees=[]
            for row in self.rows:
                check();trees.append(cKDTree(np.mod(row['point'].astype(float),self.period),boxsize=self.period) if len(row) else None)
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
