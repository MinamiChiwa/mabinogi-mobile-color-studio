"""Subpixel pick-ring geometry, independent of board colors or game HEX."""
import cv2
import numpy as np


def _fit_rim(gray, initial, width, threshold):
    # Exclude the upper connector. The OUTER white-to-background transition
    # remains visible when the selected color fills the entire circle white.
    angles=np.linspace(-np.pi/2+.5,3*np.pi/2-.5,128)
    directions=np.column_stack((np.cos(angles),np.sin(angles)))
    radii=np.arange(width*.065,width*.16,.05)
    center=np.asarray(initial,float)
    for _ in range(3):
        coords=center+directions[:,None,:]*radii[None,:,None]
        values=cv2.remap(gray,coords[:,:,0].astype('float32'),
                         coords[:,:,1].astype('float32'),cv2.INTER_LINEAR)
        points=[];used=[]
        for index,(ray,v) in enumerate(zip(directions,values)):
            falls=np.flatnonzero((v[:-1]>=threshold)&(v[1:]<threshold))
            if not len(falls):continue
            j=falls[np.argmin(abs(radii[falls]-width*.11))]
            radius=radii[j]+.05*(v[j]-threshold)/(v[j]-v[j+1])
            points.append(center+ray*radius);used.append(index)
        if len(points)<96:return None
        # An arc on only one side is not enough to establish a circle center.
        if min(np.bincount(np.array(used)//32,minlength=4))<16:return None
        points=np.array(points);params=np.r_[center,width*.11]
        for _ in range(12):
            delta=params[:2]-points;distance=np.linalg.norm(delta,axis=1)
            if np.any(distance<1e-6):return None
            residual=distance-params[2]
            jac=np.column_stack((delta/distance[:,None],-np.ones(len(points))))
            weight=np.sqrt(1/np.sqrt(1+(residual/.25)**2))
            params-=np.linalg.lstsq(jac*weight[:,None],residual*weight,rcond=None)[0]
        center=params[:2]
    residual=np.linalg.norm(points-center,axis=1)-params[2]
    if (not width*.09<params[2]<width*.14 or
            np.linalg.norm(center-initial)>max(2,width*.04) or
            np.sqrt(np.mean(residual**2))>max(.25,width*.004)):
        return None
    return center


def refine_marker_center(image, marker, card_width):
    """Fit a reliable outer rim or retain the coarse recognizer's location.

    Two brightness thresholds must agree. No fixed pixel correction and no
    target/color-card matching is used. Work on a tiny crop once per scene;
    the caller can reuse the center while the card geometry stays fixed.
    """
    x,y=map(float,marker);pad=int(np.ceil(card_width*.22))+2
    left=max(0,int(np.floor(x))-pad);top=max(0,int(np.floor(y))-pad)
    right=min(image.shape[1],int(np.ceil(x))+pad+1)
    bottom=min(image.shape[0],int(np.ceil(y))+pad+1)
    if right-left<card_width*.35 or bottom-top<card_width*.35:return tuple(marker)
    gray=np.min(image[top:bottom,left:right],axis=2).astype(np.float32)
    initial=np.array([x-left,y-top])
    low=_fit_rim(gray,initial,card_width,200)
    high=_fit_rim(gray,initial,card_width,230)
    if low is None or high is None or np.linalg.norm(low-high)>.3:return tuple(marker)
    center=(low+high)/2+[left,top]
    return tuple(map(float,center))
