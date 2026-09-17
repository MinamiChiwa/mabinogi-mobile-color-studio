"""Enumerate the exact 8-bit sRGB set accepted by the CIE76 matcher."""
import math
from functools import lru_cache
import numpy as np
from PIL import Image
from vision import lab,rgb

@lru_cache(maxsize=6)
def allowed_colors(target,tolerance):
    base=lab([rgb(target)])[0]
    gb=np.indices((256,256),dtype=np.uint16).reshape(2,-1).T
    chunk=np.empty((65536,3),np.uint8);chunk[:,1:]=gb
    matches=[]
    for red in range(256):
        chunk[:,0]=red
        distance=np.linalg.norm(lab(chunk)-base,axis=1)
        found=chunk[distance<=tolerance]
        if len(found):matches.append(found.copy())
    values=np.concatenate(matches)
    distance=np.linalg.norm(lab(values)-base,axis=1)
    order=np.lexsort((values[:,2],values[:,1],values[:,0],distance))
    values=values[order];values.setflags(write=False)
    return values

def mosaic(colors,width=240,height=64,page=0):
    """Single-page radial layout; input ordered by target Delta E.

    Overflow is sampled across the entire ordered set, never blended. Return
    one page for compatibility; the UI explicitly labels a density preview.
    """
    pixels=np.asarray(colors,dtype=np.uint8);capacity=width*height
    if len(pixels)==1:return Image.new('RGB',(width,height),tuple(map(int,pixels[0]))),1
    size=max(1,min(height,width,int(math.sqrt(capacity/min(len(pixels),capacity)))))
    while (width//size)*(height//size)<min(len(pixels),capacity):size-=1
    cols=math.ceil(width/size);rows=math.ceil(height/size)
    cy,cx=np.mgrid[:rows,:cols]
    radius=((cx-cols//2)/max(cols/2,1))**2+((cy-rows//2)/max(rows/2,1))**2
    order=np.argsort(radius.ravel(),kind='stable')
    selected=np.rint(np.linspace(0,len(pixels)-1,len(order))).astype(int)
    cells=np.empty((rows*cols,3),np.uint8)
    rings=np.floor(np.sqrt(radius)*min(rows,cols)/2).astype(int).ravel()
    angles=np.arctan2(cy-rows//2,cx-cols//2).ravel()
    chosen=pixels[selected];offset=0;base=lab(pixels[:1])[0]
    for ring in np.unique(rings):
        slots=np.flatnonzero(rings==ring);slots=slots[np.argsort(angles[slots],kind='stable')]
        group=chosen[offset:offset+len(slots)];offset+=len(slots)
        if ring==0:
            cells[slots[np.argsort(radius.ravel()[slots],kind='stable')]]=group
            continue
        delta=lab(group)-base;hue=np.arctan2(delta[:,2],delta[:,1])
        # Group neighboring hues, then walk lightness continuously within each
        # sector. Sorting by exact hue interleaves unrelated lightness values.
        sector=np.floor((hue+np.pi)/(2*np.pi)*24).astype(int)
        light=np.where(sector%2, -delta[:,0],delta[:,0])
        group=group[np.lexsort((hue,light,sector))]
        cells[slots]=group
    arr=np.repeat(np.repeat(cells.reshape(rows,cols,3),size,axis=0),size,axis=1)[:height,:width]
    return Image.fromarray(arr),1

def overview(colors,width=240,height=64):
    """A legible low-density overview; every displayed cell is an allowed RGB."""
    pixels=np.asarray(colors,np.uint8)
    if len(pixels)<=128:return mosaic(pixels,width,height)[0]
    sample=pixels[np.linspace(0,len(pixels)-1,min(len(pixels),8192)).astype(int)]
    space=lab(sample);base=lab(pixels[:1])[0];delta=space-base
    distance=np.linalg.norm(delta,axis=1);extent=float(distance.max())
    cols,rows=60,16;y,x=np.mgrid[:rows,:cols]
    nx=(x-cols//2)/(cols/2);ny=(y-rows//2)/(rows/2)
    radius=np.minimum(1,np.hypot(nx,ny)/np.sqrt(2));angle=np.arctan2(ny,nx)
    direction=np.stack((.65*np.sin(angle),np.cos(angle),np.sin(angle)),axis=-1)
    direction/=np.linalg.norm(direction,axis=-1,keepdims=True)
    desired=(direction*radius[...,None]*extent).reshape(-1,3)
    found=[]
    for chunk in np.array_split(desired,16):
        cost=np.sum((chunk[:,None,:]-delta[None,:,:])**2,axis=2)
        # Distance shells enforce the center-to-outside visual hierarchy.
        want=np.linalg.norm(chunk,axis=1)
        cost+=4*(want[:,None]-distance[None,:])**2
        found.extend(np.argmin(cost,axis=1))
    arr=sample[np.array(found)].reshape(rows,cols,3);arr[rows//2,cols//2]=pixels[0]
    return Image.fromarray(arr).resize((width,height),Image.Resampling.NEAREST)

def full_atlas(colors):
    """No subsampling: allocate at least one pixel for every allowed RGB."""
    n=len(colors);width=max(240,math.ceil(math.sqrt(n*1.6)));height=max(150,math.ceil(n/width))
    return mosaic(colors,width,height)[0]
