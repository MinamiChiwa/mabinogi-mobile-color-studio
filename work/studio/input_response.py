"""Conservative evidence for unresponsive input, independent of search scoring."""
from dataclasses import dataclass
import numpy as np

@dataclass(frozen=True)
class Response:
    state:str  # changed / static / uncertain / small
    reason:str

def assess_response(before,after,scene,next_scene,action,motion):
    # A unchanged color is normal on a large color island. Motion alone suffices.
    if motion is not None:
        matrix=np.asarray(motion['matrix'],float)
        l,t,r,b=scene.board
        points=np.array([[0,0],[r-l,0],[0,b-t],[r-l,b-t]],float)
        displacements=points@matrix[:,:2].T+matrix[:,2]-points
        if np.median(np.linalg.norm(displacements,axis=1))>=1:
            return Response('changed','texture_motion')
    if any(a is not None and b is not None and a!=b for a,b in zip(scene.colors,next_scene.colors)):
        return Response('changed','game_codes')
    if 'wheel' in action:return Response('uncertain','zoom_boundary_possible')
    if abs(action.get('dx',0))+abs(action.get('dy',0))<8 and abs(action.get('rotate',0))<3:
        return Response('small','micro_adjustment')
    l,t,r,b=scene.board
    if before.shape!=after.shape:return Response('uncertain','geometry_changed')
    a=before[t:b,l:r,:3];z=after[t:b,l:r,:3]
    if a.size==0:return Response('uncertain','empty_board')
    yy,xx=np.mgrid[t:b,l:r];mask=(xx>l+8)&(xx<r-8)&(yy>t+8)&(yy<b-8)
    radius=max(9,round((r-l)/3*.055)+4)
    for mx,my in scene.markers:
        mask&=~(((xx-mx)**2+(yy-my)**2<=radius**2)|((abs(xx-mx)<=4)&(yy<=my)))
    if np.count_nonzero(mask)<100:return Response('uncertain','insufficient_texture_area')
    delta=np.max(np.abs(a.astype(np.int16)-z.astype(np.int16)),axis=2)[mask]
    # Sparse islands moving are significant even if the board-wide mean is tiny.
    if np.mean(delta>4)>=.002 or float(np.mean(delta))>=.8:
        return Response('changed','local_pixels')
    texture=np.mean(a,axis=2)[mask]
    if np.percentile(texture,90)-np.percentile(texture,10)<6:
        return Response('uncertain','flat_color_island')
    return Response('static','textured_board_unchanged')

class ResponseGuard:
    def __init__(self):self.reset()
    def reset(self):
        self.failures=0;self.first=None;self.directions=set()
    def observe(self,response,action,now):
        if response.state=='changed':self.reset();return False
        if response.state!='static':return False
        self.failures+=1
        if self.first is None:self.first=now
        dx,dy=action.get('dx',0),action.get('dy',0)
        direction=('drag',int(np.sign(dx)),int(np.sign(dy))) if 'dx' in action else ('rotate',int(np.sign(action.get('rotate',0))))
        self.directions.add(direction)
        return self.failures>=4 and len(self.directions)>=2 and now-self.first>=2
