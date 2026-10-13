"""Measured screenshot similarity and repeated-texture period. No process data."""
import cv2
import numpy as np
from functools import lru_cache
from atlas_masks import board_texture_mask,material_masks,_geometry_key
from atlas_runtime import _remap_points


def _bilinear(image,points):
    x=np.clip(points[:,0],0,image.shape[1]-1.000001)
    y=np.clip(points[:,1],0,image.shape[0]-1.000001)
    ix=x.astype(int);iy=y.astype(int);fx=x-ix;fy=y-iy
    return ((1-fx)*(1-fy))[:,None]*image[iy,ix]+(fx*(1-fy))[:,None]*image[iy,ix+1]+\
           ((1-fx)*fy)[:,None]*image[iy+1,ix]+(fx*fy)[:,None]*image[iy+1,ix+1]


@lru_cache(maxsize=4)
def _alignment_masks(key):
    scene=dict(zip(('board','markers','cards'),key))
    masks=tuple(cv2.erode(np.uint8(mask),np.ones((9,9),np.uint8)).astype(bool)
                for mask in material_masks(scene))
    for mask in masks:mask.setflags(write=False)
    texture=board_texture_mask(scene).astype(np.uint8)*255;texture.setflags(write=False)
    return texture,masks


def refine_similarity(before,after,scene,seed,check=lambda:None,*,smoothed=None):
    """Refine an established match on same-material texture; never find a pose."""
    from scipy.optimize import least_squares
    l,t,r,b=scene.board;first=before[t:b,l:r];second=after[t:b,l:r]
    seed=np.asarray(seed,float)
    _,masks=_alignment_masks(_geometry_key(scene))
    # Smooth just for alignment. Source RGB samples and game HEX stay original.
    if smoothed is None:
        first=cv2.GaussianBlur(first.astype(np.float32),(0,0),.6)
        second=cv2.GaussianBlur(second.astype(np.float32),(0,0),.6)
    else:first,second=smoothed
    gray=cv2.cvtColor(second,cv2.COLOR_RGB2GRAY)
    gx=cv2.Sobel(gray,cv2.CV_32F,1,0,ksize=3);gy=cv2.Sobel(gray,cv2.CV_32F,0,1,ksize=3)
    gradient=np.hypot(gx,gy)
    coords=[]
    for mask in masks:
        check()
        interior=mask
        y,x=np.where(interior & (gradient>8))
        if not len(x):continue
        points=np.column_stack((x,y)).astype(float)
        inverse=np.linalg.inv(seed)
        mapped=points@inverse[:2,:2].T+inverse[:2,2]
        ix=np.rint(mapped[:,0]).astype(int);iy=np.rint(mapped[:,1]).astype(int)
        valid=(ix>=4)&(ix<mask.shape[1]-4)&(iy>=4)&(iy<mask.shape[0]-4)
        ix=np.clip(ix,0,mask.shape[1]-1);iy=np.clip(iy,0,mask.shape[0]-1)
        valid&=interior[iy,ix]
        points=points[valid]
        # Uniform traversal across the image avoids estimating rotation using
        # a tiny feature cluster. Count bounds CPU only, not search positions.
        if len(points)>1800:points=points[np.linspace(0,len(points)-1,1800,dtype=int)]
        if len(points):coords.append(points)
    diagnostics=dict(improved=False,points=sum(map(len,coords)))
    if diagnostics['points']<120:return seed,dict(diagnostics,reason='insufficient_texture')
    points=np.concatenate(coords)
    # Compare destination pixel centers with the once-interpolated source.
    # Sampling the destination again biases small motions towards zero.
    fixed=_bilinear(second,points)
    held_out=np.arange(len(points))%5==0
    # Rotation/scale corrections about image center keep parameters comparable
    # to pixel translation. Refinement stays within two pixels of the seed.
    center=np.array([(r-l)/2,(b-t)/2]);radius=max(r-l,b-t)/2
    inverse=np.linalg.inv(seed)
    def mapped(parameters):
        theta=parameters[3]/radius;factor=np.exp(parameters[2]/radius)
        linear=factor*np.array([[np.cos(theta),-np.sin(theta)],[np.sin(theta),np.cos(theta)]])
        reference=(points-center-parameters[:2])@np.linalg.inv(linear).T+center
        return reference@inverse[:2,:2].T+inverse[:2,2]
    def residual(parameters):
        check()
        return _bilinear(first,mapped(parameters))-fixed
    zero=np.zeros(4);initial=residual(zero)
    result=least_squares(lambda p:residual(p)[~held_out].reshape(-1),zero,bounds=(-2.,2.),loss='soft_l1',f_scale=8.,
        max_nfev=18,diff_step=.002,ftol=1e-5,xtol=1e-5,gtol=1e-4)
    optimized=residual(result.x)
    old=float(np.median(np.abs(initial[held_out])));new=float(np.median(np.abs(optimized[held_out])))
    diagnostics.update(before_error=old,after_error=new,parameters=result.x.tolist(),evaluations=result.nfev,
        held_out_points=int(held_out.sum()),train_before_error=float(np.median(np.abs(initial[~held_out]))),
        train_after_error=float(np.median(np.abs(optimized[~held_out]))))
    if not np.isfinite(result.x).all() or new>=old or old-new<.015:
        return seed,dict(diagnostics,reason='no_photometric_improvement')
    theta=result.x[3]/radius;factor=np.exp(result.x[2]/radius)
    correction=np.eye(3);correction[:2,:2]=factor*np.array([[np.cos(theta),-np.sin(theta)],[np.sin(theta),np.cos(theta)]])
    correction[:2,2]=center+result.x[:2]-correction[:2,:2]@center
    diagnostics['improved']=True
    return correction@seed,diagnostics

def register(before,after,scene,*,cache=None,check=lambda:None):
    check()
    l,t,r,b=scene.board
    mask,_=_alignment_masks(_geometry_key(scene))
    sift=cv2.SIFT_create(nfeatures=3600,contrastThreshold=.02)
    def features(image):
        # Controller frames are immutable. Retaining the image reference also
        # prevents an array id from being reused for a different screenshot.
        if cache is not None:
            for entry in cache:
                if entry[0] is image and entry[1]==_geometry_key(scene):return entry[2:]
        crop=image[t:b,l:r];gray=cv2.cvtColor(crop,cv2.COLOR_RGB2GRAY)
        keys,desc=sift.detectAndCompute(gray,mask)
        smooth=cv2.GaussianBlur(crop.astype(np.float32),(0,0),.6)
        if cache is not None:
            cache.append((image,_geometry_key(scene),keys,desc,smooth));del cache[:-3]
        return keys,desc,smooth
    ka,da,smooth_a=features(before)
    kb,db,smooth_b=features(after)
    diag=dict(features=[len(ka),len(kb)])
    if da is None or db is None:return None,dict(diag,reason='missing_features')
    pairs=cv2.BFMatcher().knnMatch(da,db,k=2)
    good=[p[0] for p in pairs if len(p)==2 and p[0].distance<.72*p[1].distance]
    if len(good)<10:return None,dict(diag,reason='few_matches')
    src=np.float32([ka[p.queryIdx].pt for p in good]);dst=np.float32([kb[p.trainIdx].pt for p in good])
    matrix,inliers=cv2.estimateAffinePartial2D(src,dst,method=cv2.RANSAC,
        ransacReprojThreshold=1.2,maxIters=4000,confidence=.999)
    if matrix is None or inliers is None:return None,dict(diag,reason='no_matrix')
    good=inliers.ravel().astype(bool)
    if good.sum()<12 or good.mean()<.15 or not np.isfinite(matrix).all():
        return None,dict(diag,reason='uncertain_similarity')
    residual=np.linalg.norm(src@matrix[:,:2].T+matrix[:,2]-dst,axis=1)
    result=np.eye(3);result[:2]=matrix
    diag.update(matrix=matrix.tolist(),inliers=int(good.sum()),
        median_inlier_pixels=float(np.median(residual[good])),
        scale=float(np.hypot(matrix[0,0],matrix[1,0])),
        angle=float(np.degrees(np.arctan2(matrix[1,0],matrix[0,0]))))
    result,precise=refine_similarity(before,after,scene,result,check,smoothed=(smooth_a,smooth_b))
    diag['subpixel']=precise
    diag.update(scale=float(np.hypot(result[0,0],result[1,0])),
                angle=float(np.degrees(np.arctan2(result[1,0],result[0,0]))),matrix=result[:2].tolist())
    return result,diag

def period_from_image(image,scene,*,check=lambda:None):
    check()
    l,t,r,b=scene.board;crop=image[t:b,l:r];votes=[]
    sift=cv2.SIFT_create(nfeatures=6000,contrastThreshold=.012)
    gray=cv2.cvtColor(crop,cv2.COLOR_RGB2GRAY)
    source=crop.astype(np.float32);aligned=cv2.GaussianBlur(source,(0,0),1.)
    for mask in material_masks(scene):
        check()
        keys,desc=sift.detectAndCompute(gray,mask.astype(np.uint8)*255)
        check()
        if desc is None or len(desc)<2:continue
        vectors=[]
        for i,matches in enumerate(cv2.BFMatcher().knnMatch(desc,desc,k=min(10,len(desc)))):
            if i%128==0:check()
            for match in matches[1:]:
                vector=np.asarray(keys[match.trainIdx].pt)-keys[i].pt
                if match.distance>85 or abs(vector[0])>3 or abs(vector[1])<30:continue
                vectors.append(abs(vector[1]))
        if not vectors:continue
        vectors=np.asarray(vectors);bins=np.rint(vectors/3).astype(int)
        ids,counts=np.unique(bins,return_counts=True)
        # Compact windows resample the same tile at fractional screen pixels.
        # Raw pixel RMSE then penalizes genuine repetition. Smooth alignment
        # evidence only; color samples and game HEX remain untouched.
        y,x=np.where(mask);x=x[::4];y=y[::4]
        for index in np.argsort(counts)[::-1][:8]:
            check()
            near=np.abs(vectors-ids[index]*3)<4
            if near.sum()<20:continue
            period=float(np.median(vectors[near]));py=y+period;iy=np.floor(py).astype(int)
            valid=iy<crop.shape[0]-1;valid&=mask[np.clip(iy,0,crop.shape[0]-1),x]
            if valid.sum()<80:continue
            actual=_remap_points(source,x[valid],py[valid],check=check)
            rmse=float(np.sqrt(np.mean((actual-source[y[valid],x[valid]])**2)))
            aligned_actual=_remap_points(aligned,x[valid],py[valid],check=check)
            aligned_source=aligned[y[valid],x[valid]]
            aligned_rmse=float(np.sqrt(np.mean((aligned_actual-aligned_source)**2)))
            correlation=float(np.corrcoef(aligned_actual.ravel(),aligned_source.ravel())[0,1])
            if rmse<14 or (aligned_rmse<14 and correlation>.96):
                votes.append(dict(period=period,votes=int(near.sum()),rmse=rmse,
                    alignment_rmse=aligned_rmse,alignment_correlation=correlation))
    check()
    if not votes:return None,dict(reason='period_not_observed')
    # The shortest strongly repeating distance is the base period; a twofold
    # repetition is not a different palette. Use its agreeing nominations.
    shortest=min(v['period'] for v in votes)
    accepted=[v for v in votes if abs(v['period']-shortest)<3]
    return float(np.median([v['period'] for v in accepted])),dict(votes=votes)
