"""Rank observed game HEX values and retain a recoverable texture pose."""
import numpy as np
from vision import error,measure_board_motion,accepted
import cv2

def proximity(colors,rules):
    values=[]
    for color,rule in zip(colors,rules):
        if not rule['enabled']:continue
        if color is None:return (float('inf'),float('inf'))
        values.append(error(color,rule['colors'],False))
    return (max(values),sum(values)/len(values)) if values else (float('inf'),float('inf'))

def ranking(colors,rules):
    """Feasible combinations first, then minimax actual Delta E and mean."""
    return (0 if accepted(colors,rules) else 1,*proximity(colors,rules))


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
        self.records=[];self.frames={};self.frame_bytes=0;self.memory_limit=64*1024*1024
        self.best_index=None;self.target_index=None;self.route_cursor=None
        self.rank=(2,float('inf'),float('inf'));self.uncertainty=0
        self.rotation_gain=1.;self.wheel_log_gain=np.log(1.01)
        self.last_route='direct';self.recovering=False;self.epoch=0
    def expect(self,action):self.action=dict(action)
    def observe(self,image,scene):
        if image is self.previous:return False
        action=self.action
        motion=None
        if self.previous is not None:
            motion=self.action['measured_motion'] if self.action is not None and 'measured_motion' in self.action else measure_board_motion(self.previous,image,scene.board)
            transform=global_matrix(motion) if motion is not None else commanded_matrix(self.action,scene.board) if self.action is not None else None
            if motion is None and transform is not None:
                self.estimated_steps+=1;self.uncertainty+=1
            if motion is not None and action:
                if action.get('rotate') and .2<motion.get('angle',0)/action['rotate']<2:
                    self.rotation_gain=.3*self.rotation_gain+.7*motion['angle']/action['rotate']
                if action.get('wheel') and motion.get('scale',1)>0:
                    gain=np.log(motion.get('scale',1))/action['wheel']
                    if .001<gain<.05:self.wheel_log_gain=.3*self.wheel_log_gain+.7*gain
            self.pose=transform@self.pose if transform is not None and self.pose is not None else None
        self.action=None
        score=proximity(scene.colors,self.rules);rank=ranking(scene.colors,self.rules);improved=np.isfinite(score[0]) and rank<self.rank
        if improved:
            self.score=score;self.rank=rank;self.image=image.copy();self.colors=list(scene.colors)
            if self.pose is None:self.pose=np.eye(3);self.epoch+=1
            self.best_pose=self.pose.copy()
        index=len(self.records)
        self.records.append(dict(colors=list(scene.colors),rank=rank,seconds=scene.seconds,
            pose=None if self.pose is None else self.pose.copy(),action=action,
            measured=motion is not None,uncertainty=self.uncertainty,epoch=self.epoch))
        # Grayscale texture keyframes need no PNG encoding in the timed loop.
        if improved or index%3==0:
            frame=cv2.cvtColor(image,cv2.COLOR_RGB2GRAY)
            if frame.nbytes<=self.memory_limit//2:self.frames[index]=frame;self.frame_bytes+=frame.nbytes
        if improved:
            self.best_index=index
            if not self.recovering:self.target_index=index
        protected={self.best_index,self.target_index}
        top=sorted(self.frames,key=lambda i:self.records[i]['rank'])[:4]
        protected.update(top)
        while self.frame_bytes>self.memory_limit or len(self.frames)>32:
            choices=[i for i in self.frames if i not in protected]
            if not choices:choices=[i for i in self.frames if i not in {self.best_index,self.target_index}]
            if not choices:break
            victim=choices[0];self.frame_bytes-=self.frames.pop(victim).nbytes
        self.previous=image
        return improved
    def begin_restore(self):
        self.recovering=True;self.target_index=self.best_index;self.route_cursor=len(self.records)

    def target_rank(self):
        return self.records[self.target_index]['rank'] if self.target_index is not None else self.rank

    def next_target(self):
        options=[i for i in self.frames if np.isfinite(self.records[i]['rank'][1]) and i!=self.target_index
                 and i not in getattr(self,'attempted_targets',set())]
        if not hasattr(self,'attempted_targets'):self.attempted_targets=set()
        self.attempted_targets.add(self.target_index)
        options=[i for i in options if i not in self.attempted_targets]
        if not options:return False
        self.target_index=min(options,key=lambda i:self.records[i]['rank'])
        self.route_cursor=len(self.records);return True

    def restoration(self,image,board,waypoints=False):
        if self.image is None:return None
        target=self.target_index if self.target_index is not None else self.best_index
        target_image=self.image if target==self.best_index else self.frames[target]
        direct=None if waypoints else measure_board_motion(image,target_image,board)
        if direct is not None:
            self.last_route='direct';return global_matrix(direct)
        target_pose=self.records[target]['pose'] if target is not None else self.best_pose
        # A long chain of unmeasured commands is not a reliable position.
        target_uncertainty=self.records[target]['uncertainty'] if target is not None else 0
        if not waypoints and self.pose is not None and target_pose is not None and self.records[target]['epoch']==self.epoch and abs(self.uncertainty-target_uncertainty)<=2:
            self.last_route='pose';return target_pose@np.linalg.inv(self.pose)
        # Match an earlier overlapping checkpoint, then continue backwards.
        cursor=self.route_cursor if self.route_cursor is not None else len(self.records)
        options=[i for i in self.frames if target<i<cursor]
        for i in sorted(options,reverse=True)[:8]:
            frame=self.frames[i]
            motion=measure_board_motion(image,frame,board)
            if motion is None:continue
            matrix=global_matrix(motion)
            if np.linalg.norm(matrix[:2,:2]-np.eye(2))<.015 and np.linalg.norm(matrix[:2,2])<2:
                self.route_cursor=i
                self.pose=self.records[i]['pose'];self.uncertainty=self.records[i]['uncertainty'];self.epoch=self.records[i]['epoch']
                continue
            self.last_route='checkpoint';return matrix
        return None
