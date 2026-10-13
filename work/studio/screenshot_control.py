"""Screenshot feedback, ordinary mouse inputs and actual-result checkpoints."""
import math,time,json
from pathlib import Path
from dataclasses import replace
import cv2,numpy as np
from PIL import Image
from platform_win import Interrupted,u
from vision import recognize,normalize_hex
from input_gestures import wheel_gesture,GestureTiming
from screenshot_registration import register
from screenshot_text import read_visible,read_timer,timer_bar_signal
from screenshot_search import actual_result
from best_result import ranking

class TimeEnded(Exception):pass
class PaletteEnded(Exception):pass
class RetryRequested(Exception):pass

def serial(value):
    if isinstance(value,np.ndarray):return value.tolist()
    if isinstance(value,np.generic):return value.item()
    if isinstance(value,Path):return str(value)
    raise TypeError(type(value).__name__)

class Budget:
    def __init__(self,seconds,fraction,now=None):
        self.started=time.monotonic() if now is None else now
        # A full bright bar contradicts a lost leading hundreds digit. A
        # genuinely late entry has a short bar and retains its actual timer.
        valid=type(seconds) is int and 0<seconds<=120
        fraction=fraction if fraction is not None and fraction>0 else None
        self.initial=seconds if valid and not (seconds<30 and fraction is not None and fraction>.25) else 120
        self.deadline=self.started+self.initial
        self.last_seconds=seconds if valid else None
        self.last_observed=None
        self.bar_rate=fraction/self.initial if fraction is not None and (valid or fraction>.25) else None
    def remaining(self,now=None):return max(0,self.deadline-(time.monotonic() if now is None else now))
    def can_input(self,seconds=0,now=None):return self.remaining(now)>3+max(0,seconds)
    def observe(self,seconds,fraction=None,now=None):
        now=time.monotonic() if now is None else now
        if type(seconds) is not int or not 0<seconds<=120:return 'unreadable'
        if now-self.started<30:return 'early_grace'
        fraction=fraction if fraction is not None and fraction>0 else None
        previous=self.last_observed;self.last_observed=(seconds,now,fraction)
        if fraction is None:return 'missing_bar'
        if self.bar_rate is None:
            consistent=(previous is not None and previous[2] is not None and
                abs((previous[0]-seconds)-(now-previous[1]))<=2.5 and seconds<30 and fraction<.25)
            if not consistent:return 'awaiting_bar_calibration'
            self.bar_rate=fraction/seconds
        if abs(fraction/self.bar_rate-seconds)>3:return 'bar_disagrees'
        self.deadline=min(self.started+120,now+seconds)
        return 'text_and_bar_agree'

def scale_seconds(factor):
    up=max(0,math.ceil(math.log(factor)/math.log(1.01)))
    remainder=factor/1.01**up
    down=max(0,int(math.log(remainder)/math.log(.99)))
    remainder/= .99**down
    pairs=max(0,math.ceil(math.log(remainder)/math.log(.9999)))
    batches=math.ceil(up/32)+math.ceil(down/32)+math.ceil(pairs/120)
    return (up+down)*.045+pairs*.13+batches*.7

def fine_proposal(board,shift):
    l,t,r,b=board;first=np.rint([(l+r)/2,(t+b)/2]).astype(int)
    second=np.rint(first+100*np.asarray(shift,float)).astype(int)
    if any(not(l+8<x<r-8 and t+8<y<b-8) for x,y in (first,second)):
        raise ValueError('Fine wheel pivot outside board')
    return np.array([first,second])

def fine_pair_count(board,shift):
    l,t,r,b=board;maximum=np.array([r-l,b-t])/200-.1
    return max(1,int(np.ceil(np.max(np.abs(shift)/maximum))))

def marker_radius(markers):
    points=np.asarray(markers,float).reshape(-1,2)
    return max(1.,float(np.max(np.linalg.norm(points-points.mean(axis=0),axis=1)))) if len(points) else 350.

class Controller:
    def __init__(self,owner,game,scene,rules,budget):
        self.owner=owner;self.game=game;self.scene=scene;self.rules=rules;self.budget=budget
        self.pose=np.eye(3);self.pose_known=True;self.frame=None;self.reference=None
        self.period=None;self.best=None;self.current=None;self.actions=[];self.observations=[]
        self.folder=Path(owner.folder)/'screenshot';self.folder.mkdir(parents=True,exist_ok=True)
        (self.folder/'screenshots').mkdir(exist_ok=True)
        self.failed_board_frames=0;self.registration=None;self.samples=None;self.last_timer=0
        self.timer_observations=[]
        self.feature_cache=[]
        self._completed_restore=None

    def register(self,before,after):
        return register(before,after,self.scene,cache=self.feature_cache,check=self.check)

    def check(self):
        if self.owner.stop.is_set() or u.GetAsyncKeyState(0x78)&0x8000:raise Interrupted('已停止，鼠标已释放。')
        self.game.check()

    def progress(self,stage,message=None,**data):
        self.owner.event('screenshot_progress',stage=stage,message=message,
            seconds=int(self.budget.remaining()),**data)

    def write(self,name,value):
        try:(self.folder/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,default=serial),encoding='utf8')
        except OSError:pass

    def capture(self,label,validate=True):
        self._completed_restore=None
        self.check();frame=self.game.capture()
        if validate:
            try:
                scene=recognize(frame,with_ocr=False,read_colors=False,previous=self.scene)
                if len(scene.cards)!=len(self.scene.cards):raise ValueError('Changed board')
                if max(abs(a-b) for old,new in zip(scene.cards,self.scene.cards) for a,b in zip(old,new))>3:
                    raise PaletteEnded('染色界面布局已变化，请重新开始截图寻色。')
                self.failed_board_frames=0
            except ValueError:
                self.failed_board_frames+=1
                self.current=None
                raise PaletteEnded('染色界面已关闭或结束，已停止自动操作。')
        self.frame=frame
        try:Image.fromarray(frame).save(self.folder/'screenshots'/f'{len(self.actions):03}-{label}.png',compress_level=1)
        except OSError:pass
        return frame

    def record_motion(self,matrix,diagnostics):
        self.registration=diagnostics
        if matrix is not None and self.pose_known:self.pose=matrix@self.pose
        elif matrix is None:self.pose_known=False

    def relocalize(self):
        if self.pose_known:return True
        if self.reference is None:return False
        matrix,diagnostics=self.register(self.reference,self.frame)
        if matrix is None:return False
        self.pose=matrix;self.pose_known=True;self.registration=diagnostics
        return True

    def act(self,label,perform,seconds=.8,receipt=None):
        self.check()
        if self.owner.consume_retry_request():raise RetryRequested()
        if not self.budget.can_input(seconds):raise TimeEnded()
        before=self.frame
        self.current=None
        self._completed_restore=None
        try:perform()
        finally:self.game.release()
        self.check()
        l,t,r,b=self.scene.board
        self.game.move_to((max(1,l-30),max(1,b-12)));time.sleep(.12)
        frame=self.capture(label)
        matrix,diagnostics=self.register(before,frame)
        self.record_motion(matrix,diagnostics)
        if not self.pose_known:self.relocalize()
        row=dict(name=label,elapsed=time.monotonic()-self.budget.started,
            remaining=self.budget.remaining(),pose=self.pose if self.pose_known else None,
            registration=diagnostics,command=receipt,
            gesture=None if receipt is not None else getattr(self.game,'last_gesture',None).record()
                if getattr(self.game,'last_gesture',None) else None)
        self.actions.append(row);self.write('actions.json',self.actions)
        self.current=None
        return matrix

    def wheel(self,steps,label='wheel',anchor=None):
        l,t,r,b=self.scene.board;anchor=anchor if anchor is not None else ((l+r)/2,(t+b)/2)
        steps=int(steps)
        while steps:
            batch=int(np.clip(steps,-32,32))
            gesture=replace(wheel_gesture(self.scene.board,batch,anchor),
                timing=GestureTiming(point_interval=.045,after_wheel=.12))
            self.act(label,lambda:self.game.perform_gesture(gesture),abs(batch)*.045+.35)
            steps-=batch

    def drag(self,shift,label='drag'):
        shift=np.rint(shift).astype(int);l,t,r,b=self.scene.board
        batches=max(1,int(np.ceil(max(abs(shift))/((r-l)*.6))))
        sent=np.zeros(2,int)
        for i in range(batches):
            total=np.rint(shift*(i+1)/batches).astype(int);part=total-sent
            if part.any():self.act(label,lambda part=part:self.game.drag(self.scene.board,*part),.9)
            sent=total

    def fine_shift(self,shift,label='fine'):
        l,t,r,b=self.scene.board;shift=np.asarray(shift,float)
        count=fine_pair_count(self.scene.board,shift)
        sent=np.zeros(2);result=None
        for i in range(count):
            total=np.round(shift*(i+1)/count,2);part=total-sent
            high=self.pose_known and np.hypot(self.pose[0,0],self.pose[1,0])>5.85
            pivots=fine_proposal(self.scene.board,-part if high else part)
            order=(-120,120) if high else (120,-120)
            def perform(pivots=pivots,order=order):
                for anchor,data in zip(pivots,order):
                    self.game.move_to(anchor);self.check();self.game.send(0x800,data=data);time.sleep(.065)
            result=self.act(label,perform,.6,dict(kind='two_pivot_whole_wheel',anchors=pivots,deltas=order))
            sent=total
        return result

    def pairs(self,count,label='fine-scale'):
        l,t,r,b=self.scene.board;anchor=((l+r)/2,(t+b)/2)
        scale=np.hypot(self.pose[0,0],self.pose[1,0]);order=(-120,120) if scale>5.85 else (120,-120)
        def perform():
            self.game.move_to(anchor)
            for _ in range(count):
                for data in order:self.check();self.game.send(0x800,data=data);time.sleep(.065)
        return self.act(label,perform,count*.13+.35,dict(kind='paired_whole_wheel',pairs=count,deltas=order))

    def rotate(self,angle,label='rotate',anchor=None):
        return self.act(label,lambda:self.game.rotate(self.scene.board,angle,anchor=anchor),1.2)

    def return_cost(self,target=None,from_matrix=None):
        if target is None:target=self.best
        if not target:return 0.
        if not self.pose_known or target.get('matrix') is None:return float('inf')
        source=self.pose if from_matrix is None else np.asarray(from_matrix)
        delta=np.asarray(target['matrix'])@np.linalg.inv(source)
        factor=np.hypot(delta[0,0],delta[1,0]);angle=abs(np.degrees(np.arctan2(delta[1,0],delta[0,0])))
        radius=marker_radius(self.scene.markers)
        scale_work=scale_seconds(factor) if abs(math.log(factor))*radius>=.08 else 0.
        rotation_work=math.ceil(angle/60)*1.25 if math.radians(angle)*radius>=.08 else 0.
        return scale_work+rotation_work+1.4+1.5

    def move_to(self,desired,label='position',local=False):
        desired=np.asarray(desired,float)
        if not self.relocalize():return False
        self.progress('position' if label!='return-best' else 'restore')
        markers=np.asarray(self.scene.markers,float).reshape(-1,2)-self.scene.board[:2]
        radius=marker_radius(markers)
        precision=.08 if label.startswith('return-') else .12
        tolerance=precision/radius
        for _ in range(8):
            delta=desired@np.linalg.inv(self.pose);factor=float(np.hypot(delta[0,0],delta[1,0]))
            if abs(math.log(factor))<tolerance:break
            if factor>1:
                if label.startswith('return-') and not self.budget.can_input(scale_seconds(factor)+2):break
                self.wheel(min(32,max(1,math.ceil(math.log(factor)/math.log(1.01)))),label+'-scale')
            else:
                ticks=int(math.log(factor)/math.log(.99))
                if ticks:self.wheel(-min(32,ticks),label+'-scale')
                else:
                    count=min(120,max(1,round(math.log(factor)/math.log(.9999))))
                    before=self.pose.copy();self.pairs(count,label+'-fine-scale')
                    response=self.pose@np.linalg.inv(before)
                    if abs(math.log(float(np.hypot(response[0,0],response[1,0]))))<.00003:break
            if not self.relocalize():return False
        for _ in range(5):
            delta=desired@np.linalg.inv(self.pose);angle=math.degrees(math.atan2(delta[1,0],delta[0,0]))
            if abs(math.radians(angle))*radius<precision:break
            response=self.rotate(float(np.clip(angle,-60,60)),label+'-rotate')
            if response is not None and abs(math.degrees(math.atan2(response[1,0],response[0,0])))<.01:break
            if not self.relocalize():return False
        if not len(markers):return True
        for _ in range(2):
            source=(markers-self.pose[:2,2])@np.linalg.inv(self.pose[:2,:2]).T
            shift=np.mean(source@desired[:2,:2].T+desired[:2,2]-markers,axis=0)
            if self.period:
                lattice=desired[:2,:2]*self.period
                shift-=lattice@np.rint(np.linalg.solve(lattice,shift))
            if np.linalg.norm(shift)<.07:break
            if max(abs(shift))<2.5:self.fine_shift(shift,label+'-fine-translate')
            else:self.drag(shift,label+'-translate')
            if not self.relocalize():return False
        return True

    def observe(self,label='actual',*,reuse_frame=False):
        previous=self.current
        self.progress('verify')
        if reuse_frame:self.check()
        else:self.capture(label)
        if time.monotonic()-self.last_timer>5 and self.budget.remaining()>8:
            signal=timer_bar_signal(self.frame,unit=self.scene.cards[0][2])
            diagnostics={};before=self.budget.remaining()
            seconds=read_timer(self.frame,self.scene.cards[0][2],self.check,
                deadline=self.budget.deadline-3,diagnostics=diagnostics)
            fraction=signal['width']/self.frame.shape[1] if signal else None
            decision=self.budget.observe(seconds,fraction);self.last_timer=time.monotonic()
            self.timer_observations.append(dict(label=label,elapsed=self.last_timer-self.budget.started,
                seconds=seconds,bar_fraction=fraction,decision=decision,before=before,
                remaining=self.budget.remaining(),text=diagnostics))
            self.write('timer.json',self.timer_observations)
        deadline=min(time.monotonic()+3.5,self.budget.deadline-.3)
        active=[i for i,rule in enumerate(self.rules) if rule['enabled']]
        try:
            if len(active)==1:
                # A disabled card must not spend the single-region search's
                # OCR budget or erase a correctly verified active region.
                index=active[0]
                values,diagnostics=read_visible(self.frame,[self.scene.cards[index]],deadline=deadline,check=self.check)
                colors=[None]*len(self.rules);colors[index]=values[0]
                diagnostics=[dict(row,region=index) for row in diagnostics]
            else:colors,diagnostics=read_visible(self.frame,self.scene.cards,deadline=deadline,check=self.check)
        except TimeoutError:colors=[None]*len(self.rules);diagnostics=[dict(reason='text_time_used')]
        result=actual_result(colors,self.rules)
        result['confirmed']=bool(result['accepted'] and not reuse_frame and previous
            and previous.get('accepted'))
        result.update(label=label,matrix=self.pose.copy() if self.pose_known else None,
            elapsed=time.monotonic()-self.budget.started,text=diagnostics)
        self.current=result;self.observations.append(result);self.write('actual-hex.json',self.observations)
        self.owner.event('scene',colors=colors,seconds=int(self.budget.remaining()))
        if result['verified'] and (self.best is None or result['rank']<self.best['rank']):
            self.best=dict(result);self.best['frame']=self.frame.copy()
            self.owner.event('best',colors=colors,delta=max(v for v in result['actual_deltas'] if v is not None))
        return result

    def preview(self):
        values=[]
        for x,y,w,h in self.scene.cards:
            cx=x+round(w*.5);cy=y+round(h*.43);radius=max(2,round(w*.04))
            value=np.median(self.frame[cy-radius:cy+radius+1,cx-radius:cx+radius+1].reshape(-1,3),axis=0)
            values.append('#'+''.join(f'{round(v):02X}' for v in value))
        return dict(rank=ranking(values,self.rules),colors=values,matrix=self.pose.copy(),proposal_only=True)

    def restore(self):
        if not self.best:return self.current
        target=self.best
        if self.current is not None and self.current['verified'] and self.current['rank']<=target['rank']:
            return self.current
        previous=self._completed_restore
        if previous is not None:
            best,best_matrix,current,frame,actions,pose,known=previous
            if (target is best and self.current is current and self.frame is frame
                and len(self.actions)==actions and self.pose_known==known and np.array_equal(self.pose,pose)
                and np.array_equal(target.get('matrix'),best_matrix)):
                # Nested callers share one completed recovery. A new frame,
                # input, retry or best target automatically invalidates it.
                self.check()
                return self.current
        for _ in range(3):
            # Reanchor every correction to the measured best image, including
            # when a previous read was incomplete. Do not probe away from it.
            direct,_=self.register(self.frame,target['frame'])
            if direct is not None and target.get('matrix') is not None:
                self.pose=np.linalg.inv(direct)@np.asarray(target['matrix']);self.pose_known=True
            desired=direct@self.pose if direct is not None and self.pose_known else target.get('matrix')
            before_actions=len(self.actions)
            if desired is not None and self.budget.can_input(.6):
                try:self.move_to(desired,'return-best',local=True)
                except TimeEnded:pass
            result=self.observe('return-best-actual')
            if result['verified'] and result['rank']<=target['rank']:return result
            if result['verified'] and len(self.actions)==before_actions:
                # The controller found no correction to send. Another full
                # OCR loop cannot improve this readable, unchanged position.
                self._completed_restore=(target,np.array(target.get('matrix'),copy=True),
                    self.current,self.frame,len(self.actions),
                    self.pose.copy(),self.pose_known)
                break
            if not self.budget.can_input(2):break
        return result
