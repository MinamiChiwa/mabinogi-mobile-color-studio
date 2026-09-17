import time,json,threading,traceback
from pathlib import Path
import numpy as np
import cv2
from PIL import Image
from platform_win import Game,Interrupted
from vision import recognize,accepted,candidate_shift,configure_ocr,green_buttons,result_colors,measure_board_motion,error
from planner import joint_plan,decompose_gestures
from best_result import BestResult,proximity

def local_offsets(radius=2):
    """Visit nearby integer offsets without ever issuing a zero displacement."""
    points=[]
    for r in range(1,radius+1):
        points.extend([(x,-r) for x in range(-r,r+1)])
        points.extend([(r,y) for y in range(-r+1,r+1)])
        points.extend([(x,r) for x in range(r-1,-r-1,-1)])
        points.extend([(-r,y) for y in range(r-1,-r,-1)])
    return points

def exploration_shift(board,index):
    directions=[(.45,0),(0,.50),(-.60,-.35),(.35,-.55),(.60,.45),(-.45,.60)]
    fx,fy=directions[index%len(directions)];l,t,r,b=board
    # Increase coverage on later passes, within the safe held-drag bounds.
    scale=min(1.8,1+.2*(index//len(directions)))
    return round((r-l)*np.clip(fx*scale,-.65,.65)),round((b-t)*np.clip(fy*scale,-.65,.65))

def safe_anchor(board,point):
    l,t,r,b=board;margin=max(16,min(r-l,b-t)*.12)
    return [round(np.clip(point[0],l+margin,r-margin)),round(np.clip(point[1],t+margin,b-margin))]

def actual_score(colors,rules):
    values=[]
    for color,rule in zip(colors,rules):
        if not rule['enabled']:continue
        if color is None:return float('inf')
        distance=error(color,rule['colors'],rule['exact'])
        values.append(distance/max(1 if rule['exact'] else rule['tolerance'],.001))
    return max(values,default=float('inf'))

def perfect_match(colors,rules):
    enabled=[(c,r) for c,r in zip(colors,rules) if r['enabled']]
    return bool(enabled) and all(c is not None and c.upper() in [v.upper() for v in r['colors']] for c,r in enabled)

def reconcile_deadline(deadline,seconds,now):
    """Reject OCR digit loss; the monotonic countdown remains authoritative."""
    if seconds is None or abs(seconds-(deadline-now))>4:return deadline
    return min(deadline,now+seconds)

def exact_zoom_candidate(image,scene,rules,excluded=()):
    """Find a near-color island in its own region, before marker occlusion."""
    options=[]
    for i,rule in enumerate(rules):
        if not rule['enabled'] or not rule['exact']:continue
        isolated=[dict(r,enabled=j==i) for j,r in enumerate(rules)]
        move=candidate_shift(image,scene,isolated,excluded=excluded)
        if move is not None and 0 < move[2]*.6<=12:
            mx,my=scene.markers[i]
            options.append((move[2],i,[int(mx-move[0]),int(my-move[1])]))
    return min(options,key=lambda p:p[0]) if options else None

def transform_points(points,motion):
    if motion is None:return []
    matrix=np.asarray(motion['matrix']);origin=np.asarray(motion['origin'])
    return [(region,*((np.asarray([x,y])-origin)@matrix[:,:2].T+matrix[:,2]+origin)) for region,x,y in points]

def local_stagnation(previous,current,failures):
    # Only a meaningful improvement in actual game colors earns another attempt.
    return 0 if current[0]<previous[0]-.15 else failures+1

def bounded_zoom(ticks,current,best):
    """Keep multi-region exploration within 48 ticks of entry and best pose."""
    low=max(-48,best-48);high=min(48,best+48)
    target=np.clip(current+ticks,low,high)
    return int(np.clip(round(target-current),-32,32))

class Runner:
    def __init__(self,emit,folder):
        self.emit=emit; self.stop=threading.Event(); self.folder=Path(folder); self.trace=[]
    def event(self,kind,**data):
        entry={'time':round(time.time(),3),'kind':kind,**data}
        self.trace.append(entry); self.emit(kind,data)
        with (self.folder/'events.jsonl').open('a',encoding='utf-8') as log:
            log.write(json.dumps(entry,ensure_ascii=False)+'\n')
    def snapshot(self,g,label):
        im=g.capture(); Image.fromarray(im).save(self.folder/f'{label}.png'); return im
    def wait_for_board(self,g,im,require_timer=True,timeout=60):
        deadline=time.monotonic()+timeout;next_notice=0
        while True:
            if self.stop.is_set():raise Interrupted('已停止，鼠标已释放。')
            try:
                if im is not None:
                    scene=recognize(im)
                    if not require_timer or scene.seconds is not None:
                        g.check()
                        return im,scene
            except ValueError:
                pass
            except Interrupted:
                if self.stop.is_set():raise
            except RuntimeError as e:
                if 'timeout' not in str(e).lower():raise
            now=time.monotonic()
            if now>=deadline:
                raise TimeoutError('等待染色界面超时，尚未开始寻色。请打开染色界面、完成教学后再按 F8。')
            if now>=next_notice:
                self.event('waiting',message='正在等待染色界面，请打开普通染色并完成教学。按 F9 可取消。',seconds=max(1,int(np.ceil(deadline-now))))
                next_notice=now+5
            if self.stop.wait(min(.5,deadline-now)):raise Interrupted('已停止，鼠标已释放。')
            try:im=g.capture_waiting()
            except Interrupted:
                if self.stop.is_set():raise
                im=None
    def launch(self,rules,mode='search',auto=False):
        self.folder.mkdir(parents=True,exist_ok=True)
        try:
            configure_ocr(); g=Game(self.stop); g.focus(); im=self.snapshot(g,'start')
            self.event('config',rules=rules,auto_apply=auto,dpi=int(__import__('platform_win').u.GetDpiForWindow(g.hwnd)))
            result=result_colors(im)
            if result is not None:
                if mode=='search' and auto and accepted(result,rules):return self.apply_result(g,im,result)
                return self.event('done',message='当前在结果页，颜色未满足目标或自动套用已关闭，未操作。',colors=result)
            # Wait without mouse input; the dye countdown starts independently.
            im,scene=self.wait_for_board(g,im,require_timer=mode not in ('read','capture'))
            self.event('scene',colors=scene.colors,seconds=scene.seconds,board=scene.board,markers=scene.markers,size=list(im.shape[:2]))
            if mode=='read':return self.event('done',message='已读取当前色码。',colors=scene.colors)
            if mode in ('capture','recovery_test'):
                if any(c is None for c in scene.colors):raise RuntimeError('三个色码尚未完整识别，未替换目标。')
                verify=recognize(g.capture(),previous=scene)
                if verify.colors!=scene.colors:raise RuntimeError('色码复核不一致，未替换目标。')
                self.event('targets',colors=scene.colors)
                if mode=='capture':return self.event('done',message='已将当前三色设为目标，保留各区匹配模式与容差。')
                rules=[dict(enabled=True,colors=[c],exact=False,tolerance=4) for c in scene.colors]
                self.event('test_targets',rules=rules)
                baseline=self.snapshot(g,'baseline')
                anchor=safe_anchor(scene.board,scene.markers[0])
                g.rotate(scene.board,12,anchor=anchor);time.sleep(.2)
                rotated=self.snapshot(g,'test-rotation')
                self.event('test_rotation',anchor=anchor,command=12,motion=measure_board_motion(baseline,rotated,scene.board))
                g.wheel(scene.board,-8,anchor=anchor);time.sleep(.2)
                zoomed=self.snapshot(g,'test-zoom')
                self.event('test_zoom',anchor=anchor,ticks=-8,motion=measure_board_motion(rotated,zoomed,scene.board))
                g.drag(scene.board,40,30);time.sleep(.2)
                im=self.snapshot(g,'disturbed');scene=recognize(im,previous=scene)
                self.event('disturbed',colors=scene.colors,motion=measure_board_motion(zoomed,im,scene.board))
            if scene.seconds is None:raise RuntimeError('未能可靠读取倒计时，已停止。请在教学结束后再按 F8。')
            deadline=time.monotonic()+scene.seconds
            if mode=='diagnostic':return self.diagnostic(g,im,scene,deadline)
            self.best=BestResult(rules)
            visited=[]; no_change=0; misses=0; explore_index=0; explore_remaining=0; gain=np.ones(2); rotation_gain=1.0
            step=-1; zoom_index=0; last_refine=-20; zoom_blocked_direction=0; pending=None; track_attempts=0; locked=None; lock_steps=0
            local=[];local_at=(0,0);local_cooldown=0
            zoom_burst=0;zoom_cooldown=0;zoom_hold_until=0
            excluded=[]
            multi=sum(bool(r['enabled']) for r in rules)>1
            search_zoom=0.;best_zoom=0.;joint_stalls=0
            magnify_started=None;magnify_attempts=0;magnify_ticks=0;zoom_out_remaining=0;wide_explore=0
            while True:
                step+=1
                g.check()
                self.event('scene',colors=scene.colors,seconds=scene.seconds)
                if self.best.observe(im,scene):
                    best_zoom=search_zoom
                    Image.fromarray(im).save(self.folder/'best-observed.png')
                    self.event('best',colors=scene.colors,delta=self.best.score[0])
                if perfect_match(scene.colors,rules):
                    time.sleep(.18); verify=recognize(g.capture(),previous=scene)
                    if perfect_match(verify.colors,rules):
                        self.snapshot(g,'matched'); self.event('match',colors=verify.colors)
                        if not auto:return self.event('done',message='寻色完成：全部目标已匹配并复核。请返回游戏确认使用。',colors=verify.colors,popup=True,outcome='matched')
                        return self.submit(g,verify,rules)
                if time.monotonic()>=deadline-30:
                    return self.restore_best(g,im,scene,rules,deadline)
                # A tolerance hit is a saved candidate, not the end of search.
                if accepted(scene.colors,rules):
                    pending=None;locked=None;local=[];explore_remaining=max(explore_remaining,1)
                if magnify_started is not None and (magnify_attempts>=3 or time.monotonic()-magnify_started>=12):
                    zoom_out_remaining=max(32,magnify_ticks)
                    magnify_started=None;magnify_attempts=0;magnify_ticks=0
                    pending=None;locked=None;local=[];visited=[];zoom_hold_until=0
                    self.event('explore',message='局部多次未命中，正在缩小色板并重新探索。')
                before=im
                move=pending if pending is not None else candidate_shift(im,scene,rules,visited,excluded=excluded)
                tracking=pending is not None;pending=None
                threshold=1.0
                enabled=[i for i,rule in enumerate(rules) if rule['enabled']]
                plan=None
                zoom_target=None
                if not multi and not zoom_out_remaining and not wide_explore and magnify_attempts==0 and zoom_burst<2 and not tracking and locked is None and step>=zoom_cooldown and zoom_blocked_direction!=1 and time.monotonic()<deadline-42:
                    zoom_target=exact_zoom_candidate(im,scene,rules,excluded=excluded)
                if accepted(scene.colors,rules):move=None;tracking=False
                if locked is not None and not local:
                    targets=np.array([scene.markers[i] for i in enabled],np.float32)
                    matrix,_=cv2.estimateAffinePartial2D(locked.astype(np.float32),targets,method=cv2.LMEDS)
                    if matrix is not None:
                        center=np.array([(scene.board[0]+scene.board[2])/2,(scene.board[1]+scene.board[3])/2])
                        delta=matrix[:,:2]@center+matrix[:,2]-center
                        plan=dict(score=0.,dx=float(delta[0]),dy=float(delta[1]),angle=float(np.degrees(np.arctan2(matrix[1,0],matrix[0,0]))),scale=float(np.hypot(matrix[0,0],matrix[1,0])))
                elif len(enabled)>1 and not accepted(scene.colors,rules) and not tracking and not local and step>=local_cooldown and (move is None or move[2]>threshold):
                    plan=joint_plan(im,scene,rules)
                    if plan is not None:self.event('plan',**plan)
                # Planning can be expensive: do not start another gesture after
                # it consumes the time reserved for restoring the best pose.
                if time.monotonic()>=deadline-30:
                    return self.restore_best(g,im,scene,rules,deadline)
                if multi and plan is not None and plan['score']<=1:
                    requested=round(np.log(plan['scale'])/np.log(1.01))
                    remaining=search_zoom+requested
                    if (remaining < max(-48,best_zoom-48) or remaining > min(48,best_zoom+48)
                            or (requested and np.sign(requested)==zoom_blocked_direction)):
                        plan=None;locked=None;local_cooldown=step+4;wide_explore=max(wide_explore,2)
                misses=misses+1 if move is None or move[2]>threshold else 0
                if move is None or misses>=2:
                    explore_remaining=max(explore_remaining,3 if misses==2 or move is None else 0)
                    misses=0
                if move is not None and move[2]<=threshold:
                    explore_remaining=0
                refine=not tracking and move is not None and 0<move[2]<=threshold and len(enabled)==1 and step-last_refine>=12
                exact_near=move is not None and len(enabled)==1 and rules[enabled[0]]['exact'] and move[2]*.6<=12
                if magnify_started is not None and move is not None:explore_remaining=0
                if exact_near and step<zoom_hold_until:explore_remaining=0
                promising=move is not None and move[2]<=threshold
                if plan is not None and plan['score']<=1 and abs(plan['angle'])<=1 and abs(plan['scale']-1)<=.01 and np.hypot(plan['dx'],plan['dy'])<2.5:
                    local=local_offsets(1)[:2];local_at=(0,0);locked=None;pending=None;plan=None
                    self.event('local_refine',message='候选已接近，逐点读取三个实际色码进行微调。')
                if zoom_out_remaining:
                    anchor=safe_anchor(scene.board,scene.markers[enabled[0]])
                    ticks=-min(32,zoom_out_remaining)
                    g.wheel(scene.board,ticks,anchor=anchor)
                    action={'wheel':ticks,'zoom_anchor':anchor,'zoom_reset':True}
                    zoom_out_remaining+=ticks
                    if not zoom_out_remaining:
                        wide_explore=2;zoom_burst=0;zoom_cooldown=step+3
                    visited=[];pending=None;locked=None;local=[]
                elif wide_explore:
                    dx,dy=exploration_shift(scene.board,explore_index)
                    g.drag(scene.board,dx,dy)
                    action={'explore':True,'dx':dx,'dy':dy,'wide_search':True}
                    explore_index+=1;wide_explore-=1;visited=[];pending=None;locked=None;local=[]
                elif zoom_target is not None:
                    if magnify_started is None:magnify_started=time.monotonic()
                    _,region,anchor=zoom_target
                    g.wheel(scene.board,32,anchor=anchor)
                    action={'wheel':32,'zoom_anchor':anchor,'exact_magnify':True,'region':region}
                    self.event('magnifying',message=f'发现区域 {region+1} 的接近颜色，正在放大寻找纯色。')
                    visited=[];local=[];pending=None;explore_remaining=0;zoom_burst+=1
                    zoom_hold_until=step+8
                elif local and magnify_started is None:
                    if actual_score(scene.colors,rules)<=3:
                        im,scene=self.refine_actual(g,im,scene,rules,min(deadline-30,time.monotonic()+3))
                        local=[];pending=None;locked=None;local_cooldown=step+4;explore_remaining=2
                        continue
                    destination=local.pop(0);tx=destination[0]-local_at[0];ty=destination[1]-local_at[1];local_at=destination
                    g.drag(scene.board,tx,ty);action={'dx':tx,'dy':ty,'local_refine':True}
                    pending=None;locked=None
                    if not local:local_cooldown=step+4;explore_remaining=2
                elif plan is not None and plan['score']<=1:
                    gestures=decompose_gestures(plan,scene.board,[scene.markers[i] for i in enabled])
                    self.event('gestures',**gestures,angle=plan['angle'],scale=plan['scale'])
                    if locked is None:
                        locked=np.array(gestures['sources'])
                        lock_steps=0
                    if abs(plan['angle'])>1:
                        command=float(np.clip(plan['angle']/rotation_gain,-120,120))
                        g.rotate(scene.board,command,anchor=gestures['rotation_anchor']);action={'rotate':command,'rotation_anchor':gestures['rotation_anchor'],'desired_rotation':plan['angle'],'joint':True}
                    elif abs(plan['scale']-1)>.01:
                        ticks=int(np.clip(round(np.log(plan['scale'])/np.log(1.01)),-32,32))
                        if multi:ticks=bounded_zoom(ticks,search_zoom,best_zoom)
                        g.wheel(scene.board,ticks,anchor=gestures['zoom_anchor']);action={'wheel':ticks,'zoom_anchor':gestures['zoom_anchor'],'joint':True}
                    else:
                        tx=round(np.clip(plan['dx']/gain[0],-(scene.board[2]-scene.board[0])*.65,(scene.board[2]-scene.board[0])*.65))
                        ty=round(np.clip(plan['dy']/gain[1],-(scene.board[3]-scene.board[1])*.65,(scene.board[3]-scene.board[1])*.65))
                        g.drag(scene.board,tx,ty);move=(plan['dx'],plan['dy'],plan['score'])
                        action={'dx':tx,'dy':ty,'predicted_delta':plan['score'],'joint':True}
                    visited=[]
                elif refine and zoom_blocked_direction!=1 and magnify_started is None:
                    mx,my=scene.markers[enabled[0]];anchor=(mx-move[0],my-move[1])
                    g.wheel(scene.board,20,anchor=anchor)
                    action={'wheel':20,'zoom_anchor':list(anchor),'refine':True};visited=[];last_refine=step
                elif magnify_started is None and step and step%7==0 and not promising and not (exact_near and step<zoom_hold_until):
                    angle=30 if (step//7)%2 else -45
                    command=float(np.clip(angle/rotation_gain,-120,120))
                    anchor=safe_anchor(scene.board,scene.markers[enabled[(step//7)%len(enabled)]])
                    g.rotate(scene.board,command,anchor=anchor); action={'rotate':command,'rotation_anchor':list(anchor),'desired_rotation':angle}; visited=[]
                elif magnify_started is None and step and step%5==0 and not promising and step>=zoom_hold_until:
                    direction=(-20,-20,24,24,-24,20)[zoom_index%6];zoom_index+=1
                    if np.sign(direction)==zoom_blocked_direction:direction=-direction
                    if multi:
                        limited=bounded_zoom(direction,search_zoom,best_zoom)
                        direction=limited if limited else bounded_zoom(-direction,search_zoom,best_zoom)
                    anchor=safe_anchor(scene.board,scene.markers[enabled[zoom_index%len(enabled)]])
                    g.wheel(scene.board,direction,anchor=anchor); action={'wheel':direction,'zoom_anchor':list(anchor)}; visited=[]
                elif explore_remaining:
                    dx,dy=exploration_shift(scene.board,explore_index)
                    self.event('explore',message='当前范围没有合适候选，正在拖动色板探索新颜色。')
                    g.drag(scene.board,dx,dy);action={'explore':True,'dx':dx,'dy':dy}
                    explore_index+=1;explore_remaining-=1;visited=[]
                elif move:
                    dx,dy,score=move
                    limit=(scene.board[2]-scene.board[0])*.65
                    tx,ty=round(np.clip(dx/gain[0],-limit,limit)),round(np.clip(dy/gain[1],-limit,limit))
                    g.drag(scene.board,tx,ty); action={'dx':tx,'dy':ty,'predicted_delta':score}; visited.append((dx,dy))
                else:
                    # A valid board without a candidate is an exploration opportunity.
                    dx,dy=exploration_shift(scene.board,explore_index)
                    self.event('explore',message='当前范围没有合适候选，正在拖动色板探索新颜色。')
                    g.drag(scene.board,dx,dy);action={'explore':True,'dx':dx,'dy':dy};visited=[];explore_index+=1
                self.best.expect(dict(action,rotation_gain=rotation_gain))
                time.sleep(.10 if 'wheel' in action else .15); im=g.capture(); Image.fromarray(im).save(self.folder/f'step-{step+1:02d}.png',compress_level=1); next_scene=recognize(im,previous=scene,enabled=[r['enabled'] for r in rules])
                motion=measure_board_motion(before,im,scene.board)
                if multi and 'wheel' in action:
                    actual_ticks=np.log(motion['scale'])/np.log(1.01) if motion is not None and motion['scale']>0 else action['wheel']
                    search_zoom+=float(np.clip(actual_ticks,-32,32))
                    action['search_zoom_ticks']=round(search_zoom,2)
                self.best.expect(dict(action,rotation_gain=rotation_gain,measured_motion=motion))
                excluded=transform_points(excluded,motion)[-24:]
                if action.get('exact_magnify'):
                    # Follow the chosen island through zoom, then land it at the
                    # actual marker center instead of selecting another island.
                    if len(enabled)==1 and motion is not None:
                        region=action['region']
                        source=transform_points([(region,*action['zoom_anchor'])],motion)[0]
                        residual=np.rint(np.asarray(scene.markers[region])-source[1:]).astype(int)
                        if np.any(residual):pending=(int(residual[0]),int(residual[1]),zoom_target[0]);track_attempts=0
                    effective=round(np.log(motion['scale'])/np.log(1.01)) if motion is not None and motion['scale']>0 else 32
                    magnify_ticks+=max(0,min(32,effective))
                elif magnify_started is not None:
                    magnify_attempts=local_stagnation(proximity(scene.colors,rules),proximity(next_scene.colors,rules),magnify_attempts)
                l,t,r,b=scene.board; change=float(np.mean(np.abs(im[t:b,l:r].astype(float)-before[t:b,l:r].astype(float))))
                if action.get('joint') and locked is not None:
                    joint_stalls=joint_stalls+1 if motion is None or ('wheel' in action and abs(motion['scale']-1)<.005) or ('rotate' in action and abs(motion['angle'])<.5) else 0
                    if motion is None:locked=None
                    else:
                        matrix=np.array(motion['matrix']);origin=np.array(motion['origin'])
                        locked=(locked-origin)@matrix[:,:2].T+matrix[:,2]+origin;lock_steps+=1
                        action['tracked_candidates']=locked.round(2).tolist()
                        if lock_steps>=4 or joint_stalls>=2:locked=None
                    if locked is None:
                        local_cooldown=step+4;wide_explore=max(wide_explore,2);joint_stalls=0
                elif locked is not None:locked=None
                if 'rotate' in action:
                    action['measured_motion']=motion
                    if motion is None or abs(motion['angle'])<2 or abs(motion['scale']-1)>.08:
                        self.event('rotation_unverified',message='本次右键动作未能证实有效旋转，继续平移搜索。')
                    elif .2<motion['angle']/action['rotate']<2:
                        rotation_gain=.3*rotation_gain+.7*motion['angle']/action['rotate']
                        action['rotation_gain']=round(rotation_gain,3)
                if 'wheel' in action:
                    action['measured_motion']=motion
                    if action.get('zoom_reset') and motion is not None and abs(motion['scale']-1)<.005:
                        zoom_out_remaining=0;wide_explore=2;zoom_burst=0;zoom_cooldown=step+3
                    if motion is not None:
                        zoom_blocked_direction=int(np.sign(action['wheel'])) if abs(motion['scale']-1)<.005 else 0
                        if action.get('exact_magnify') and zoom_blocked_direction==1:
                            zoom_cooldown=step+10;zoom_hold_until=step+8;zoom_burst=0
                if 'predicted_delta' in action:
                    if motion is not None and not action.get('joint') and (move[2]<=1 or (len(enabled)==1 and rules[enabled[0]]['exact'] and move[2]*.6<=12)) and track_attempts<2:
                        matrix=np.array(motion['matrix']);origin=np.array(motion['origin'])
                        points=np.array([scene.markers[i] for i in enabled],float)
                        sources=points-np.array(move[:2])
                        transformed=(sources-origin)@matrix[:,:2].T+matrix[:,2]+origin
                        residual=np.mean(points-transformed,axis=0)
                        if np.max(np.linalg.norm(points-transformed-residual,axis=1))<3:
                            rx,ry=np.rint(residual).astype(int)
                            if abs(rx)+abs(ry)>0:
                                pending=(int(rx),int(ry),move[2]);track_attempts+=1
                                action['tracked_residual']=[int(rx),int(ry)]
                    if pending is None:
                        if len(enabled)==1 and not accepted(next_scene.colors,rules) and motion is not None:
                            region=enabled[0];mx,my=scene.markers[region]
                            excluded.extend(transform_points([(region,mx-move[0],my-move[1])],motion))
                        track_attempts=0
                    if pending is None and move[2]<=1 and not action.get('joint') and not accepted(next_scene.colors,rules) and step>=local_cooldown:
                        local=local_offsets(1)[:2];local_at=(0,0)
                        self.event('local_refine',message='平移候选已接近，保留当前范围并验证邻近色码。')
                    old=cv2.cvtColor(before[t:b,l:r],cv2.COLOR_RGB2GRAY).astype(np.float32)
                    new=cv2.cvtColor(im[t:b,l:r],cv2.COLOR_RGB2GRAY).astype(np.float32)
                    shift,confidence=cv2.phaseCorrelate(old,new)
                    if confidence>.25:
                        for axis,key in enumerate(('dx','dy')):
                            commanded=action[key]
                            if abs(commanded)>=8 and .3<shift[axis]/commanded<2:
                                gain[axis]=.3*gain[axis]+.7*shift[axis]/commanded
                    action['measured_shift']=[round(v,2) for v in shift]
                    action['input_gain']=[round(v,3) for v in gain]
                # A zoom boundary is not failed mouse input; reverse on next zoom.
                substantial=abs(action.get('dx',0))+abs(action.get('dy',0))>=8 or 'rotate' in action
                no_change=no_change+1 if change<1.5 and substantial else 0
                self.event('action',step=step+1,change=round(change,2),before=scene.colors,after=next_scene.colors,**action)
                if no_change>=2:raise RuntimeError('连续两次输入后色板未变化。已停止，请检查游戏是否接受模拟鼠标输入。')
                deadline=reconcile_deadline(deadline,next_scene.seconds,time.monotonic())
                scene=next_scene
        except TimeoutError as e:self.event('wait_timeout',message=str(e))
        except Interrupted as e:self.event('interrupted',message=str(e))
        except Exception as e:self.event('error',message=str(e),detail=traceback.format_exc())
        finally:
            (self.folder/'trace.json').write_text(json.dumps(self.trace,ensure_ascii=False,indent=2),encoding='utf-8')
            self.emit('finished',{})
    def refine_actual(self,g,im,scene,rules,deadline):
        """Bound local trials; retain best globally and leave on no improvement."""
        trials=[('drag',(1,0)),('drag',(0,1))]
        for index,(kind,value) in enumerate(trials):
            if time.monotonic()>=deadline or perfect_match(scene.colors,rules):break
            old_score=proximity(scene.colors,rules)
            enabled=[i for i,r in enumerate(rules) if r['enabled']]
            best_region=min(enabled,key=lambda i:actual_score([scene.colors[i]],[rules[i]]))
            anchor=safe_anchor(scene.board,scene.markers[best_region])
            if kind=='drag':g.drag(scene.board,*value)
            elif kind=='rotate':g.rotate(scene.board,value,anchor=anchor)
            else:g.wheel(scene.board,value,anchor=anchor)
            if hasattr(self,'best'):self.best.expect({'dx':value[0],'dy':value[1]} if kind=='drag' else {'rotate':value,'rotation_anchor':anchor} if kind=='rotate' else {'wheel':value,'zoom_anchor':anchor})
            time.sleep(.2);im=self.snapshot(g,f'local-{time.time_ns()}');next_scene=recognize(im,previous=scene)
            score=proximity(next_scene.colors,rules)
            if hasattr(self,'best'):self.best.observe(im,next_scene)
            self.event('local_trial',operation=kind,value=value,anchor=anchor,before=scene.colors,after=next_scene.colors,score=score,improved=score<old_score)
            if score<old_score:
                scene=next_scene;continue
            # Do not spend exploration time undoing unproductive pixel trials.
            # The global best pose is retained for the reserved restoration phase.
            return im,next_scene
        return im,scene
    def restore_best(self,g,im,scene,rules,deadline):
        self.event('restoring',message='剩余约 30 秒，正在回到本轮最接近的已观察颜色。',colors=self.best.colors)
        restored=False
        offsets=iter(local_offsets(2));last_offset=(0,0)
        for attempt in range(18):
            g.check()
            if self.best.colors is not None and proximity(scene.colors,rules)<=self.best.score:
                verify=recognize(g.capture(),previous=scene)
                if proximity(verify.colors,rules)<=self.best.score:
                    scene=verify;restored=True;break
            if time.monotonic()>deadline-3:break
            matrix=self.best.restoration(im,scene.board)
            if matrix is None:break
            l,t,r,b=scene.board;center=np.array([(l+r)/2,(t+b)/2]);delta=matrix[:2,:2]@center+matrix[:2,2]-center
            plan=dict(angle=float(np.degrees(np.arctan2(matrix[1,0],matrix[0,0]))),scale=float(np.hypot(matrix[0,0],matrix[1,0])),dx=float(delta[0]),dy=float(delta[1]))
            gestures=decompose_gestures(plan,scene.board,scene.markers)
            zoom_ticks=int(np.clip(round(np.log(plan['scale'])/np.log(1.01)),-32,32))
            if abs(zoom_ticks)>=3:
                value=zoom_ticks;g.wheel(scene.board,value,anchor=gestures['zoom_anchor']);kind='zoom'
                self.best.expect({'wheel':value,'zoom_anchor':gestures['zoom_anchor']})
            elif abs(plan['angle'])>.5:
                value=float(np.clip(plan['angle'],-90,90));g.rotate(scene.board,value,anchor=gestures['rotation_anchor']);kind='rotate'
                self.best.expect({'rotate':value,'rotation_anchor':gestures['rotation_anchor']})
            elif abs(round(np.log(plan['scale'])/np.log(1.01)))>=1:
                value=zoom_ticks;g.wheel(scene.board,value,anchor=gestures['zoom_anchor']);kind='zoom'
                self.best.expect({'wheel':value,'zoom_anchor':gestures['zoom_anchor']})
            else:
                dx,dy=np.rint(delta).astype(int)
                if dx==0 and dy==0:
                    dest=next(offsets,(0,0));dx,dy=dest[0]-last_offset[0],dest[1]-last_offset[1];last_offset=dest
                g.drag(scene.board,int(dx),int(dy));kind='drag'
                self.best.expect({'dx':int(dx),'dy':int(dy)})
            time.sleep(.15);im=self.snapshot(g,f'restore-{attempt+1}');scene=recognize(im,previous=scene)
            self.best.observe(im,scene)
            self.event('restore_action',operation=kind,colors=scene.colors,seconds=scene.seconds)
        matched=accepted(scene.colors,rules)
        message=('寻色完成：已回到本轮最接近结果。' if restored else '寻色结束：未能可靠恢复本轮最佳颜色，已停止操作。')
        message+=(' 当前颜色已达到目标。' if matched else ' 当前为妥协颜色，未达到设定目标。')
        message+=' 未自动套用，请返回游戏决定使用或取消。'
        self.event('done',message=message,colors=scene.colors,best_colors=self.best.colors,popup=True,outcome='matched' if matched else 'compromise',restored=restored)
    def diagnostic(self,g,im,scene,deadline):
        initial=scene.colors
        anchor=safe_anchor(scene.board,scene.markers[0])
        for label,action in [('left',lambda:g.drag(scene.board,round((scene.board[2]-scene.board[0])*.10),0)),('right',lambda:g.rotate(scene.board,35,anchor=anchor)),('wheel',lambda:g.wheel(scene.board,-3,anchor=anchor))]:
            if time.monotonic()>deadline:raise RuntimeError('剩余时间不足，停止输入校准。')
            before=im; old=scene.colors; action(); time.sleep(.25); im=self.snapshot(g,label); scene=recognize(im,previous=scene)
            l,t,r,b=scene.board; delta=float(np.mean(np.abs(im[t:b,l:r].astype(float)-before[t:b,l:r].astype(float))))
            motion=measure_board_motion(before,im,scene.board) if label in ('right','wheel') else None
            self.event('action',action=label,change=round(delta,2),before=old,after=scene.colors,measured_motion=motion)
            if label=='right' and (motion is None or abs(motion['angle'])<2 or abs(motion['scale']-1)>.08):
                raise RuntimeError('右键动作未能证实色板旋转，不能判定旋转校准通过。')
            if label=='wheel' and (motion is None or abs(motion['scale']-1)<.005):
                raise RuntimeError('未测得明确缩放倍率，不能判定缩放校准通过。')
            if delta<1.5:raise RuntimeError(f'{label} 输入后色板没有可确认的变化，校准未通过。')
        self.event('done',message='输入校准完成：平移、旋转、缩放均引起画面变化；未套用颜色。',colors=scene.colors)
    def submit(self,g,scene,rules):
        # Submit only on an identified active board. Final apply requires result re-recognition.
        if scene.button is None:raise RuntimeError('已匹配，但未识别到游戏确认按钮。请手动确认。')
        g.click(scene.button)
        for _ in range(12):
            time.sleep(.25); im=g.capture(); colors=result_colors(im)
            if colors is not None:break
        else:raise RuntimeError('已提交，但结果页未能可靠识别，未点击套用。请在游戏中确认。')
        Image.fromarray(im).save(self.folder/'result.png')
        if not accepted(colors,rules):raise RuntimeError('结果色码与目标不符，已停止套用。请取消本次结果。')
        return self.apply_result(g,im,colors)
    def apply_result(self,g,im,colors):
        # Color pills appear before the final button during the result animation.
        # Wait for both, and recheck the same colors before any irreversible click.
        for attempt in range(17):
            g.check()
            buttons=green_buttons(im)
            if len(buttons)==1 and result_colors(im)==colors:break
            if attempt==16:raise RuntimeError('结果页按钮在等待后仍无法可靠定位，未套用。')
            time.sleep(.25);im=g.capture()
        Image.fromarray(im).save(self.folder/'result-ready.png')
        g.click(buttons[0][:2]);time.sleep(.8);after=self.snapshot(g,'applied')
        if result_colors(after) is not None:raise RuntimeError('确认点击后结果页仍在，未确认套用成功。')
        self.event('done',message='染色完成：目标色已通过结果页复核并套用。',colors=colors,popup=True,outcome='applied')
    def reject(self,g,scene):
        if scene.button is None:raise RuntimeError('未找到目标且无法定位结束按钮，请手动选择不使用。')
        g.click(scene.button)
        for _ in range(12):
            time.sleep(.25);im=g.capture()
            if result_colors(im) is not None:break
        else:raise RuntimeError('未识别到结果页，请手动选择不使用本次染色。')
        g.escape();time.sleep(.5);im=self.snapshot(g,'cancel-dialog');buttons=green_buttons(im)
        # Cancellation dialog must dim the result pills and expose exactly one button.
        if result_colors(im) is not None or len(buttons)!=1:raise RuntimeError('取消确认窗口未能可靠识别，请手动取消。')
        g.click(buttons[0][:2]);time.sleep(.5);self.snapshot(g,'rejected')
        self.event('done',message='本轮未找到全部目标，已取消结果并保留原色。本次消耗 1 个染色剂。')
