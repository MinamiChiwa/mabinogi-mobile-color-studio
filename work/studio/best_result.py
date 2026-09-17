"""Rank observed game HEX values and retain a recoverable texture pose."""
import numpy as np
from vision import error,measure_board_motion

def proximity(colors,rules):
    values=[]
    for color,rule in zip(colors,rules):
        if not rule['enabled']:continue
        if color is None:return (float('inf'),float('inf'))
        values.append(error(color,rule['colors'],False))
    return (max(values),sum(values)/len(values)) if values else (float('inf'),float('inf'))

def global_matrix(motion):
    matrix=np.eye(3);matrix[:2]=motion['matrix'];origin=np.array(motion['origin'])
    matrix[:2,2]+=origin-matrix[:2,:2]@origin
    return matrix

def commanded_matrix(action,board):
    """Fallback pose estimate only; game HEX still decides restoration success."""
    l,t,r,b=board;matrix=np.eye(3)
    if 'rotate' in action:
        angle=np.radians(action['rotate']*action.get('rotation_gain',1.0));scale=1.
        anchor=action.get('rotation_anchor',[(l+r)/2,(t+b)/2])
    elif 'wheel' in action:
        angle=0.;scale=1.01**int(np.clip(action['wheel'],-32,32))
        anchor=action.get('zoom_anchor',[(l+r)/2,(t+b)/2])
    elif 'dx' in action:
        matrix[:2,2]=[int(np.clip(action['dx'],-(r-l)*.65,(r-l)*.65)),int(np.clip(action['dy'],-(b-t)*.65,(b-t)*.65))]
        return matrix
    else:return None
    matrix[:2,:2]=scale*np.array([[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]])
    matrix[:2,2]=np.array(anchor)-matrix[:2,:2]@np.array(anchor)
    return matrix

class BestResult:
    def __init__(self,rules):
        self.rules=rules;self.previous=None;self.pose=np.eye(3)
        self.image=None;self.colors=None;self.best_pose=None;self.score=(float('inf'),float('inf'))
        self.action=None;self.estimated_steps=0
    def expect(self,action):self.action=dict(action)
    def observe(self,image,scene):
        if self.previous is not None and image is not self.previous:
            motion=self.action['measured_motion'] if self.action is not None and 'measured_motion' in self.action else measure_board_motion(self.previous,image,scene.board)
            transform=global_matrix(motion) if motion is not None else commanded_matrix(self.action,scene.board) if self.action is not None else None
            if motion is None and transform is not None:self.estimated_steps+=1
            self.pose=transform@self.pose if transform is not None and self.pose is not None else None
        self.action=None
        score=proximity(scene.colors,self.rules);improved=score<self.score
        if improved:
            self.score=score;self.image=image.copy();self.colors=list(scene.colors)
            if self.pose is None:self.pose=np.eye(3)
            self.best_pose=self.pose.copy()
        self.previous=image
        return improved
    def restoration(self,image,board):
        if self.image is None:return None
        direct=measure_board_motion(image,self.image,board)
        if direct is not None:return global_matrix(direct)
        if self.pose is not None and self.best_pose is not None:return self.best_pose@np.linalg.inv(self.pose)
        return None
