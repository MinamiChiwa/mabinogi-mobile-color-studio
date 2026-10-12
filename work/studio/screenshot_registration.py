"""Measured screenshot similarity and repeated-texture period. No process data."""
import cv2
import numpy as np
from atlas_masks import board_texture_mask,material_masks

def register(before,after,scene,*,cache=None):
    l,t,r,b=scene.board
    mask=board_texture_mask(scene).astype(np.uint8)*255
    sift=cv2.SIFT_create(nfeatures=3600,contrastThreshold=.02)
    def features(image):
        # Controller frames are immutable. Retaining the image reference also
        # prevents an array id from being reused for a different screenshot.
        if cache is not None:
            for saved,saved_scene,keys,desc in cache:
                if saved is image and saved_scene is scene:return keys,desc
        keys,desc=sift.detectAndCompute(cv2.cvtColor(image[t:b,l:r],cv2.COLOR_RGB2GRAY),mask)
        if cache is not None:
            cache.append((image,scene,keys,desc));del cache[:-3]
        return keys,desc
    ka,da=features(before)
    kb,db=features(after)
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
    return result,diag

def period_from_image(image,scene):
    l,t,r,b=scene.board;crop=image[t:b,l:r];votes=[]
    sift=cv2.SIFT_create(nfeatures=6000,contrastThreshold=.012)
    for mask in material_masks(scene):
        keys,desc=sift.detectAndCompute(cv2.cvtColor(crop,cv2.COLOR_RGB2GRAY),mask.astype(np.uint8)*255)
        if desc is None or len(desc)<2:continue
        vectors=[]
        for i,matches in enumerate(cv2.BFMatcher().knnMatch(desc,desc,k=min(10,len(desc)))):
            for match in matches[1:]:
                vector=np.asarray(keys[match.trainIdx].pt)-keys[i].pt
                if match.distance>85 or abs(vector[0])>3 or abs(vector[1])<30:continue
                vectors.append(abs(vector[1]))
        if not vectors:continue
        vectors=np.asarray(vectors);bins=np.rint(vectors/3).astype(int)
        ids,counts=np.unique(bins,return_counts=True)
        source=crop.astype(np.float32);y,x=np.where(mask);x=x[::4];y=y[::4]
        for index in np.argsort(counts)[::-1][:8]:
            near=np.abs(vectors-ids[index]*3)<4
            if near.sum()<20:continue
            period=float(np.median(vectors[near]));py=y+period;iy=np.floor(py).astype(int)
            valid=iy<crop.shape[0]-1;valid&=mask[np.clip(iy,0,crop.shape[0]-1),x]
            if valid.sum()<80:continue
            actual=cv2.remap(source,x[valid,None].astype(np.float32),py[valid,None].astype(np.float32),cv2.INTER_LINEAR).reshape(-1,3)
            rmse=float(np.sqrt(np.mean((actual-source[y[valid],x[valid]])**2)))
            if rmse<14:votes.append(dict(period=period,votes=int(near.sum()),rmse=rmse))
    if not votes:return None,dict(reason='period_not_observed')
    # The shortest strongly repeating distance is the base period; a twofold
    # repetition is not a different palette. Use its agreeing nominations.
    shortest=min(v['period'] for v in votes)
    accepted=[v for v in votes if abs(v['period']-shortest)<3]
    return float(np.median([v['period'] for v in accepted])),dict(votes=votes)
