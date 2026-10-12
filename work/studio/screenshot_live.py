"""User-rule screenshot search. No memory reads, apply, start or cancel buttons."""
import time,traceback
import numpy as np
from platform_win import Game,Interrupted
from window_target import WindowUnavailable,resolve_target
from vision import recognize
from dye_regions import bind_region_rules
from atlas_masks import material_masks
from screenshot_control import Controller,Budget,TimeEnded,PaletteEnded,RetryRequested,serial,fine_pair_count
from screenshot_registration import period_from_image
from screenshot_samples import RawSamples
from screenshot_search import solve,actual_result
from screenshot_text import read_timer,timer_bar_signal

def _sampling_check(c):
    c.check()
    if c.owner.consume_retry_request():raise RetryRequested()
    if c.budget.remaining()<=3:raise TimeEnded()

def _wait_board(owner,game_factory,target,activate,*,server=None):
    owner.event('screenshot_progress',stage='waiting',
        message='截图寻色已就绪，可进入染色，也可直接识别已打开的色板。F9 可停止。')
    game=None;notice=0
    while not owner.stop.is_set():
        try:
            if game is None:
                selected=resolve_target(target,server=server) if server is not None else target
                game=game_factory(owner.stop,target=selected)
                if activate:
                    try:game.focus()
                    except RuntimeError:pass
            image=game.capture_waiting()
            if image is not None:
                scene=recognize(image,with_ocr=False,read_colors=False)
                # Recognition through a dark tutorial overlay is not ready.
                if all(np.median(image[y:y+h,x:x+w])>180 for x,y,w,h in scene.cards):
                    return game,image,scene
        except WindowUnavailable as exc:
            if target is not None:raise
            game=None
        except ValueError:pass
        if time.monotonic()>notice:
            owner.event('screenshot_progress',stage='waiting',
                message='等待游戏色板显示完整；可以先进入染色，再启动截图寻色。F9 可停止。')
            notice=time.monotonic()+5
        owner.stop.wait(.2)
    raise Interrupted('已停止，鼠标已释放。')

def _collect(c,samples=None):
    c.progress('capture','正在缩小画板并采集原始颜色，随后会自动寻找目标。')
    def can_shrink(steps):
        if not c.pose_known and not c.relocalize():return False
        factor=.99**abs(steps)
        l,t,r,b=c.scene.board;center=np.array([(r-l)/2,(b-t)/2])
        zoom=np.diag([factor,factor,1.]);zoom[:2,2]=center*(1-factor)
        return c.budget.can_input(abs(steps)*.045+.7+c.return_cost(from_matrix=zoom@c.pose))
    def reuse():
        c.progress('search',('剩余时间用于当前画板搜索，保留回到较好结果的时间。' if samples is None else
            '复用本局已采集的颜色，保留回到较好结果的时间。'))
        return samples
    # No pauses for OCR between batches. Measured screenshots verify the
    # response, and the already observed current colors are retained.
    minimum=False
    for steps in (-25,-25,-25,-3):
        if not can_shrink(steps):return reuse()
        before=c.pose.copy();known=c.pose_known
        c.wheel(steps,'minimum')
        if known and c.pose_known:
            response=c.pose@np.linalg.inv(before)
            if np.hypot(response[0,0],response[1,0])>.998:
                minimum=True;break
    while not minimum and c.budget.can_input(2):
        if not can_shrink(-25):return reuse()
        before=c.pose.copy();known=c.pose_known
        c.wheel(-25,'minimum-confirm')
        if known and c.pose_known:
            response=c.pose@np.linalg.inv(before)
            if np.hypot(response[0,0],response[1,0])>.998:break
        elif not c.relocalize():break
    if samples is None:
        period,diagnostics=period_from_image(c.frame,c.scene)
        c.write('period.json',dict(period=period,diagnostics=diagnostics))
        if period is None:
            # One more horizontal view can expose texture nominations hidden
            # by connector masks. A missing period does not claim no target.
            if not c.budget.can_input(c.return_cost()+2.5):return None
            c.drag([(c.scene.board[2]-c.scene.board[0])*.13,0],'period-view')
            period,diagnostics=period_from_image(c.frame,c.scene)
        if period is None:return None
        old=c.pose.copy();old_known=c.pose_known
        c.reference=c.frame.copy();c.pose=np.eye(3);c.pose_known=True;c.period=period
        if c.best and c.best.get('matrix') is not None:
            c.best['matrix']=np.asarray(c.best['matrix'])@np.linalg.inv(old) if old_known else None
        samples=RawSamples(period,c.rules)
        c.samples=samples
    l,t,r,b=c.scene.board;masks=material_masks(c.scene)
    def add():
        if c.pose_known:samples.add(c.frame[t:b,l:r],masks,c.pose,check=lambda:_sampling_check(c))
    add()
    if samples.frames>5:
        # Retry uses the same canonical samples; new transform measurements
        # preserve its relation to the existing model instead of redoing a scan.
        c.progress('search','复用本局已采集的颜色，正在重新搜索。')
        return samples
    spacing=np.asarray(c.scene.markers)[1,0]-np.asarray(c.scene.markers)[0,0]
    for i in range(4):
        if c.budget.remaining()<c.return_cost()+18:break
        c.drag([spacing*.38,0],f'scan-min-{i}');add()
        c.progress('capture',current=i+1,total=4,message='正在覆盖重复色板，保留原始颜色点。')
    # Reserve actual positioning time rather than spend a short late entry on
    # a complete high-magnification sweep.
    if c.budget.remaining()>c.return_cost()+38:
        for i in range(5):
            c.wheel(20,f'magnify-{i}');add()
        for row in range(2):
            for i in range(7):
                if c.budget.remaining()<c.return_cost()+23:break
                c.drag([(r-l)*.2*(1 if row==0 else -1),0],f'scan-high-{row}-{i}');add()
                c.progress('capture',current=row*7+i+1,total=14,
                    message='正在放大采集细小颜色点，采集完成后会自动移动。')
            if row==0 and c.budget.remaining()>c.return_cost()+25:
                c.drag([0,(b-t)*.5],'scan-next-row');add()
    c.write('samples.json',dict(period=samples.period,frames=samples.frames,
        counts=[len(v) for v in samples.arrays()[0]],scope='observed whole RGB; not actual game HEX'))
    try:samples.save(c.folder/'raw-sites.npz')
    except OSError:pass
    return samples

def _refine(c):
    center=c.preview();best_preview=center;offset=np.zeros(2)
    protected=c.best
    for point in ((0,.4),(0,-.4),(.4,0),(-.4,0),(1,0),(-1,0),(0,1),(0,-1)):
        shift=np.asarray(point)-offset;count=fine_pair_count(c.scene.board,shift)
        predicted=c.pose.copy();predicted[:2]*=.9999**count
        if not c.budget.can_input(c.return_cost(protected,from_matrix=predicted)+count*.8+3.5):break
        c.fine_shift(shift,'refine-translate');offset=np.asarray(point)
        value=c.preview()
        # Read improved previews immediately so a later probe cannot erase an
        # unrecorded real result as happened in the research round five.
        if value['rank']<best_preview['rank']:
            best_preview=value;c.observe('refine-actual')
            if c.current['accepted']:return
        c.progress('refinement','正在微调颜色，并保留已经实测的较好结果。',
            current_colors=(c.current or c.best or {}).get('actual_colors'),
            current_deltas=(c.current or c.best or {}).get('actual_deltas'),
            verified=c.current is not None and c.current.get('verified',False),
            screenshot_verified=c.current is not None and c.current.get('verified',False))
    if c.budget.can_input(c.return_cost()+3.5):
        c.move_to(best_preview['matrix'],'local-return',local=True);c.observe('local-return-actual')
    if not c.current or c.current['accepted']:return
    anchor_index=min((i for i,r in enumerate(c.rules) if r['enabled']),
        key=lambda i:c.current['actual_deltas'][i] if c.current['actual_deltas'][i] is not None else float('inf'))
    anchor=np.rint(c.scene.markers[anchor_index]).astype(int)
    for angle in (.35,-.70,.35):
        if not c.budget.can_input(c.return_cost()+4.2):break
        c.rotate(angle,'refine-rotation',anchor);value=c.observe('rotation-actual')
        if value['accepted']:return
    for steps in (1,-2,1):
        predicted=c.pose.copy();predicted[:2]*=1.01**steps if steps>0 else .99**-steps
        if not c.budget.can_input(c.return_cost(from_matrix=predicted)+abs(steps)*.045+4.2):break
        c.wheel(steps,'refine-scale',anchor);value=c.observe('scale-actual')
        if value['accepted']:return

def _search(c,samples):
    if samples is None:
        c.progress('observe','未能测得完整重复周期，正在使用当前截图寻找较接近的颜色。')
        # Local fallback contains only actually visible samples. A large
        # artificial boundary avoids introducing a repeated tile assumption.
        l,t,r,b=c.scene.board;period=max(r-l,b-t)*8
        samples=RawSamples(period,c.rules)
        samples.add(c.frame[t:b,l:r],material_masks(c.scene),np.eye(3),check=lambda:_sampling_check(c))
        old=c.pose.copy();old_known=c.pose_known
        c.pose=np.eye(3);c.reference=c.frame.copy();c.pose_known=True
        if c.best and c.best.get('matrix') is not None:
            c.best['matrix']=np.asarray(c.best['matrix'])@np.linalg.inv(old) if old_known else None
        c.period=None
    c.progress('search','正在计算平移、旋转与缩放方案；最终颜色以游戏实际色码为准。')
    sites,colors=samples.arrays();markers=np.asarray(c.scene.markers)-c.scene.board[:2]
    remaining=c.budget.remaining();search_time=min(7,max(.05,(remaining-c.return_cost()-6)*.16))
    def check():
        c.check()
        if c.owner.consume_retry_request():raise RetryRequested()
    found=solve(sites,colors,samples.period,markers,c.rules,c.pose,search_time,check)
    c.write('proposals.json',found)
    if not found['candidates']:return samples
    for candidate in found['candidates']:
        if c.owner.consume_retry_request():raise RetryRequested()
        estimate=c.return_cost(dict(matrix=candidate['matrix']))
        if c.budget.remaining()<estimate+c.return_cost(from_matrix=candidate['matrix'])+5:continue
        positioned=c.move_to(candidate['matrix']);result=c.observe('candidate-actual')
        if not positioned:
            c.progress('observe','当前位置尚未完成图像定位，正在保留游戏实际颜色。')
            break
        if result['accepted']:
            confirm=c.observe('match-confirmation')
            if confirm['accepted']:break
        _refine(c)
        if c.current and c.current['accepted']:
            if c.observe('refinement-confirmation')['accepted']:break
        c.restore()
        if c.budget.remaining()<c.return_cost()+7:break
    return samples

def _publish(c,reason=None):
    result=dict(c.current or actual_result([None]*len(c.rules),c.rules))
    historical=c.best or {}
    result.update(region_count=len(c.rules),rules=c.rules,
        best_actual_colors=historical.get('actual_colors'),
        best_current=bool(result.get('verified') and historical and result['rank']<=historical['rank']),
        stop_reason=reason,backend='screenshot',actions=len(c.actions),actual_reads=len(c.observations),
        no_apply=True,no_game_memory=True,remaining_seconds=c.budget.remaining())
    result['outcome']='matched' if result['accepted'] else 'compromise' if result['verified'] else 'unverified'
    result.pop('matrix',None);result.pop('frame',None)
    c.write('result.json',result);c.owner.event('screenshot_result',**result)
    return result

def run_screenshot_search(owner,rules,mode='search',auto=False,activate=False,target=None,
    game_factory=Game,wait_for_retry=True,server=None,**context):
    game=None;c=None;samples=None
    try:
        game,image,scene=_wait_board(owner,game_factory,target,activate,server=server)
        rules=bind_region_rules(rules,len(scene.cards))
        owner.event('region_layout',region_count=len(rules),rules=rules)
        owner.event('window_bound',title=game.target.title,hwnd=int(game.hwnd),pid=int(game.target.pid))
        started=time.monotonic();signal=timer_bar_signal(image,unit=scene.cards[0][2])
        fraction=signal['width']/image.shape[1] if signal else None
        timer_diagnostics={}
        seconds=read_timer(image,scene.cards[0][2],game.check,diagnostics=timer_diagnostics)
        c=Controller(owner,game,scene,rules,Budget(seconds,fraction,now=started));c.frame=image;c.reference=image
        c.write('initial-timer.json',timer_diagnostics)
        c.write('geometry.json',dict(board=scene.board,markers=scene.markers,cards=scene.cards,client=game.geometry(),rules=rules))
        c.observe('baseline')
        owner.event('native_retry_available',enabled=c.budget.can_input(5),backend='screenshot')
        while True:
            reason=None
            owner.event('native_retry_reset',status='searching',backend='screenshot')
            owner.event('native_retry_available',enabled=c.budget.can_input(5),backend='screenshot')
            try:
                if c.current and c.current['accepted']:
                    c.observe('baseline-confirmation')
                if not (c.current and c.current['accepted']):
                    samples=_collect(c,samples)
                    samples=_search(c,samples)
                    c.restore()
            except RetryRequested:
                owner.event('native_retry_reset',status='zooming',backend='screenshot')
                c.current=None
                samples=c.samples or samples
                continue
            except TimeEnded:
                reason='time_used'
                try:c.restore()
                except TimeEnded:pass
                except RetryRequested:
                    if c.budget.can_input(5):
                        owner.event('native_retry_reset',status='zooming',backend='screenshot')
                        c.current=None;samples=c.samples or samples
                        continue
                    owner.event('native_retry_reset',status='rejected',reason='insufficient_retry_time',backend='screenshot')
                    try:c.restore()
                    except TimeEnded:pass
            result=_publish(c,reason)
            if not wait_for_retry:return result
            owner.event('native_retry_available',enabled=c.budget.can_input(5),waiting_for_retry=True,
                verified=result['verified'],screenshot_verified=result['verified'],
                current_colors=result['actual_colors'],current_deltas=result['actual_deltas'],backend='screenshot')
            while c.budget.remaining()>3:
                c.check()
                if owner.consume_retry_request():
                    owner.event('native_retry_reset',status='zooming',backend='screenshot')
                    if c.budget.can_input(5):
                        c.current=None;break
                    owner.event('native_retry_reset',status='rejected',reason='insufficient_retry_time',backend='screenshot')
                    owner.event('native_retry_available',enabled=False,waiting_for_retry=True,backend='screenshot')
                if owner.stop.wait(.15):c.check()
                try:recognize(game.capture(),with_ocr=False,read_colors=False,previous=scene)
                except ValueError:raise PaletteEnded('染色界面已关闭或结束，已停止自动操作。')
            else:return result
    except PaletteEnded as exc:
        if c:
            c.current=None;return _publish(c,'palette_ended')
        raise
    except Interrupted:
        if c:
            c.current=None;_publish(c,'interrupted')
        raise
    except Exception as exc:
        if c:
            c.write('error.json',dict(error=str(exc),traceback=traceback.format_exc()))
            # Ordinary processing errors do not erase a freshly readable game
            # result. Final result distinguishes it from an old best frame.
            try:c.observe('error-current-actual')
            except (Interrupted,PaletteEnded):c.current=None
            except Exception:c.current=None
            return _publish(c,'processing_error')
        raise
    finally:
        if game is not None:game.release()
