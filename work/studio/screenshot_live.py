"""User-rule screenshot search. No memory reads, apply, start or cancel buttons."""
import itertools,time,traceback
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
from screenshot_refinement import local_candidates
from refinement_policy import compare_refinement
from screenshot_prediction import VisibleColorField,ObservedColorField
from screenshot_text import read_timer,timer_bar_signal

def _sampling_check(c):
    c.check()
    if c.owner.consume_retry_request():raise RetryRequested()
    if c.budget.work_remaining()<=3+c.return_cost():raise TimeEnded()

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
    if sum(bool(r['enabled']) for r in c.rules)==1:
        from screenshot_single import collect
        collect(c);return None
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
        started=time.monotonic()
        period,diagnostics=period_from_image(c.frame,c.scene,check=lambda:_sampling_check(c))
        c.budget.record_cost('period',time.monotonic()-started)
        c.write('period.json',dict(period=period,diagnostics=diagnostics))
        if period is None:
            # One more horizontal view can expose texture nominations hidden
            # by connector masks. A missing period does not claim no target.
            if not c.budget.can_input(c.return_cost()+2.5):return None
            c.drag([(c.scene.board[2]-c.scene.board[0])*.13,0],'period-view')
            period,diagnostics=period_from_image(c.frame,c.scene,check=lambda:_sampling_check(c))
        if period is None:return None
        old=c.pose.copy();old_known=c.pose_known
        c.reference=c.frame.copy();c.pose=np.eye(3);c.pose_known=True;c.period=period
        if c.best and c.best.get('matrix') is not None:
            c.best['matrix']=np.asarray(c.best['matrix'])@np.linalg.inv(old) if old_known else None
        samples=RawSamples(period,c.rules)
        c.samples=samples
    l,t,r,b=c.scene.board;masks=material_masks(c.scene)
    def add():
        if c.pose_known:
            started=time.monotonic()
            try:
                samples.add(c.frame[t:b,l:r],masks,c.pose,check=lambda:_sampling_check(c))
                if hasattr(samples,'visible_field'):
                    samples.visible_field.add_frame(c.frame[t:b,l:r],masks,c.pose,check=lambda:_sampling_check(c))
            finally:c.budget.record_cost('assembly',time.monotonic()-started)
    add()
    if samples.frames>5:
        # Retry uses the same canonical samples; new transform measurements
        # preserve its relation to the existing model instead of redoing a scan.
        c.progress('search','复用本局已采集的颜色，正在重新搜索。')
        return samples
    spacing=np.asarray(c.scene.markers)[1,0]-np.asarray(c.scene.markers)[0,0]
    for i in range(4):
        if c.budget.work_remaining()<c.return_cost()+max(8,c.collection_cost(samples)+7):break
        c.drag([spacing*.38,0],f'scan-min-{i}');add()
        c.progress('capture',current=i+1,total=4,message='正在覆盖重复色板，保留原始颜色点。')
    # Reserve actual positioning time rather than spend a short late entry on
    # a complete high-magnification sweep.
    if c.budget.work_remaining()>c.return_cost()+max(18,c.collection_cost(samples)+7):
        for i in range(5):
            if c.budget.work_remaining()<c.return_cost()+c.collection_cost(samples)+8:break
            c.wheel(20,f'magnify-{i}');add()
        for row in range(2):
            for i in range(7):
                if c.budget.work_remaining()<c.return_cost()+c.collection_cost(samples)+8:break
                c.drag([(r-l)*.2*(1 if row==0 else -1),0],f'scan-high-{row}-{i}');add()
                c.progress('capture',current=row*7+i+1,total=14,
                    message='正在放大采集细小颜色点，采集完成后会自动移动。')
            if row==0 and c.budget.work_remaining()>c.return_cost()+c.collection_cost(samples)+9:
                c.drag([0,(b-t)*.5],'scan-next-row');add()
    c.write('samples.json',dict(period=samples.period,frames=samples.frames,
        counts=[len(v) for v in samples.rows],scope='observed whole RGB; not actual game HEX'))
    try:
        if getattr(c,'evidence_writer',None) is not None:samples.save_background(c.folder/'raw-sites.npz',c.evidence_writer)
    except OSError:pass
    return samples

def _settle_refinement(c,value,anchor):
    """Keep a componentwise gain, otherwise return to the actual anchor."""
    decision=compare_refinement(value['actual_colors'],anchor['actual_colors'],c.rules)
    if value.get('verified') and decision['not_worse']:
        if decision['improved']:
            c.refinement_anchor=c.best
        return True
    # Observation must not have promoted a trade. Preserve the snapshot even
    # when an adapter failed between observing and committing its best result.
    c.best=anchor;c.refinement_anchor=anchor
    c.progress('refinement',refinement_status='restoring',
        current_colors=value['actual_colors'],current_deltas=value['actual_deltas'],
        verified=value.get('verified',False),screenshot_verified=value.get('verified',False),
        retained_colors=anchor['actual_colors'],retained_deltas=anchor['actual_deltas'])
    recovered=c.restore()
    return bool(recovered and recovered.get('verified') and compare_refinement(
        recovered['actual_colors'],anchor['actual_colors'],c.rules)['not_worse'])


def _refine_visible(c):
    for shift in ((0,.4),(0,-.4),(.4,0),(-.4,0),(1,0),(-1,0),(0,1),(0,-1)):
        count=fine_pair_count(c.scene.board,shift)
        predicted=c.pose.copy();predicted[:2]*=.9999**count
        if not c.budget.can_input(c.return_cost(c.best,from_matrix=predicted)+count*.8+
                max(3.5,c.budget.estimate('verify',1.5))):break
        reference=c.best;c.fine_shift(shift,'refine-translate')
        value=c.observe('refine-actual')
        improved=compare_refinement(value['actual_colors'],reference['actual_colors'],c.rules)['improved']
        c.progress('refinement','正在微调颜色，并保留已经实测的较好结果。',
            current_colors=value['actual_colors'],current_deltas=value['actual_deltas'],
            verified=value['verified'],screenshot_verified=value['verified'],
            refinement_status='retained' if improved else 'trial',
            retained_colors=c.best['actual_colors'],retained_deltas=c.best['actual_deltas'])
        if not _settle_refinement(c,value,reference):return
        if c.current['accepted']:return
    if not c.current or c.current['accepted']:return
    anchor_index=min((i for i,r in enumerate(c.rules) if r['enabled']),
        key=lambda i:c.rules[i].get('priority',i+1))
    anchor=np.rint(c.scene.markers[anchor_index]).astype(int)
    # Each unsuccessful probe now returns to its measured anchor, so probe
    # opposite offsets directly instead of replaying an accumulated sequence.
    for angle in (.35,-.35):
        if not c.budget.can_input(c.return_cost()+4.2):break
        reference=c.best;c.rotate(angle,'refine-rotation',anchor);value=c.observe('rotation-actual')
        if not _settle_refinement(c,value,reference):return
        if c.current and c.current['accepted']:return
    for steps in (1,-1):
        predicted=c.pose.copy();predicted[:2]*=1.01**steps if steps>0 else .99**-steps
        if not c.budget.can_input(c.return_cost(from_matrix=predicted)+abs(steps)*.045+4.2):break
        reference=c.best;c.wheel(steps,'refine-scale',anchor);value=c.observe('scale-actual')
        if not _settle_refinement(c,value,reference):return
        if c.current and c.current['accepted']:return

def _refine(c,max_rounds=None):
    if not c.current or not c.current.get('verified') or not c.best:return
    c.refinement_anchor=c.best
    if not compare_refinement(c.current['actual_colors'],c.best['actual_colors'],c.rules)['not_worse']:
        if not _settle_refinement(c,c.current,c.best):return
    if c.samples is None:return _refine_visible(c)
    attempted=set();step=.4;unchanged=0;rows=[]
    markers=np.asarray(c.scene.markers)-c.scene.board[:2]
    for round_number in itertools.count():
        if max_rounds is not None and round_number>=max_rounds:break
        c.check()
        if c.owner.consume_retry_request():raise RetryRequested()
        if c.current and c.current['accepted']:return
        if not c.relocalize():break
        reference=c.best
        candidates=local_candidates(c.samples,markers,c.rules,c.pose,step=step,
            exclude=attempted,check=lambda:_sampling_check(c),baseline=reference['actual_colors'])
        candidate=None
        for row in candidates:
            cost=c.return_cost(dict(matrix=row['matrix']))
            recovery=c.return_cost(reference,from_matrix=row['matrix'])
            if c.budget.can_input(cost+recovery+1.5):candidate=row;break
        if candidate is None:break
        attempted.add(candidate.get('signature',tuple(np.round(candidate['matrix'][:2].ravel(),5))))
        measured=c.pose.copy()
        if not c.move_to(candidate['matrix'],'refine-measured',local=True):break
        value=c.observe('refine-measured-actual',reuse_frame=True)
        decision=compare_refinement(value['actual_colors'],reference['actual_colors'],c.rules)
        improved=value['verified'] and decision['improved']
        rows.append(dict(round=round_number,reference=measured,desired=candidate['matrix'],
            measured=c.pose.copy(),kind=candidate['kind'],improved=improved,
            actual_colors=value['actual_colors'],actual_deltas=value['actual_deltas'],comparison=decision))
        c.write('refinement.json',rows)
        c.progress('refinement','正在微调颜色，并保留已经实测的较好结果。',
            current_colors=value['actual_colors'],current_deltas=value['actual_deltas'],
            verified=value['verified'],screenshot_verified=value['verified'],
            refinement_status='retained' if improved else 'trial',
            retained_colors=c.best['actual_colors'],retained_deltas=c.best['actual_deltas'])
        if not _settle_refinement(c,value,reference):break
        if c.current and c.current['accepted']:return
        unchanged=0 if improved else unchanged+1
        if unchanged>=4:
            step=step/2 if step>.08 else .8;unchanged=0
    if c.best and (c.current is None or not compare_refinement(
            c.current['actual_colors'],c.best['actual_colors'],c.rules)['not_worse']):c.restore()


def _search(c,samples):
    if sum(bool(r['enabled']) for r in c.rules)==1:
        from screenshot_single import search
        return search(c)
    sample_at=None
    if samples is None:
        c.progress('observe','未能测得完整重复周期，正在使用当前截图寻找较接近的颜色。')
        # Local fallback contains only actually visible samples. A large
        # artificial boundary avoids introducing a repeated tile assumption.
        l,t,r,b=c.scene.board;period=max(r-l,b-t)*8
        samples=RawSamples(period,c.rules)
        samples.add(c.frame[t:b,l:r],material_masks(c.scene),np.eye(3),check=lambda:_sampling_check(c))
        sample_at=VisibleColorField(c.frame[t:b,l:r],material_masks(c.scene))
        samples.visible_field=ObservedColorField(samples.period)
        samples.visible_field.add_frame(c.frame[t:b,l:r],material_masks(c.scene),np.eye(3),check=lambda:_sampling_check(c))
        old=c.pose.copy();old_known=c.pose_known
        c.pose=np.eye(3);c.reference=c.frame.copy();c.pose_known=True
        if c.best and c.best.get('matrix') is not None:
            c.best['matrix']=np.asarray(c.best['matrix'])@np.linalg.inv(old) if old_known else None
        c.period=None
    c.progress('search','正在计算平移、旋转与缩放方案；最终颜色以游戏实际色码为准。')
    started=time.monotonic()
    try:sites,colors=samples.arrays(check=lambda:_sampling_check(c))
    finally:c.budget.record_cost('export',time.monotonic()-started)
    markers=np.asarray(c.scene.markers)-c.scene.board[:2]
    def check():
        _sampling_check(c)
    if sample_at is None and hasattr(samples,'color_field'):
        sample_at=getattr(samples,'visible_field',samples.color_field)
        if hasattr(sample_at,'prepare'):
            if c.budget.work_remaining()<=c.return_cost()+c.tree_cost(samples)+3:return samples
            started=time.monotonic()
            try:sample_at.prepare(lambda:_sampling_check(c))
            finally:c.budget.record_cost('tree',time.monotonic()-started)
    remaining=c.budget.work_remaining();search_time=min(7,max(.05,(remaining-c.return_cost()-6)*.16))
    found=solve(sites,colors,samples.period,markers,c.rules,c.pose,search_time,check,sample_at=sample_at)
    c.samples=samples
    c.write('proposals.json',found)
    if not found['candidates']:return samples
    for candidate in found['candidates']:
        if c.owner.consume_retry_request():raise RetryRequested()
        estimate=c.return_cost(dict(matrix=candidate['matrix']))
        if c.budget.remaining()<estimate+c.return_cost(from_matrix=candidate['matrix'])+5:continue
        # A new global candidate may make the user's priority-ordered trade;
        # final-polish retention starts afresh only after its measured landing.
        c.refinement_anchor=None
        positioned=c.move_to(candidate['matrix']);result=c.observe('candidate-actual')
        if not positioned:
            c.progress('observe','当前位置尚未完成图像定位，正在保留游戏实际颜色。')
            break
        if result['accepted']:
            confirm=c.observe('match-confirmation')
            if confirm['accepted']:break
        _refine(c)
        if (c.current and c.current['accepted'] and
                (c.refinement_anchor is None or c.at_least_best(c.current,c.best))):
            confirmed=c.observe('refinement-confirmation')
            if confirmed['accepted'] and (c.refinement_anchor is None or c.at_least_best(confirmed,c.best)):break
        recovered=c.restore()
        if c.best:
            retained=bool(recovered and recovered.get('verified'))
            if retained:
                retained=(compare_refinement(recovered['actual_colors'],c.best['actual_colors'],c.rules)['not_worse']
                    if getattr(c,'refinement_anchor',None) is not None else recovered['rank']<=c.best['rank'])
            if not retained:break
        if c.budget.remaining()<c.return_cost()+7:break
    return samples

def _publish(c,reason=None):
    if c.current and c.current.get('accepted') and not c.current.get('confirmed'):
        try:
            c.observe('final-match-confirmation')
            if (getattr(c,'refinement_anchor',None) is not None and c.best and
                    not c.at_least_best(c.current,c.best)):
                settled=_settle_refinement(c,c.current,c.best)
                if settled and c.current and c.current.get('accepted') and not c.current.get('confirmed'):
                    c.observe('returned-match-confirmation')
        except (PaletteEnded,Interrupted) as exc:
            c.current=None
            reason=reason or ('palette_ended' if isinstance(exc,PaletteEnded) else 'stopped')
            recovery=c.safe_restore(reason,interruption=exc)
            if recovery['verified'] and c.current and c.current.get('accepted'):
                try:c.observe('recovered-final-confirmation')
                except (PaletteEnded,Interrupted,TimeEnded):c.current=None
        except Exception as exc:
            c.write('final-confirmation-error.json',dict(error=str(exc),traceback=traceback.format_exc()))
            c.current=None;reason=reason or 'verification_error'
    result=dict(c.current or actual_result([None]*len(c.rules),c.rules))
    result['accepted']=bool(result.get('accepted') and result.get('confirmed'))
    historical=c.best or {}
    result.update(region_count=len(c.rules),rules=c.rules,
        best_actual_colors=historical.get('actual_colors'),
        best_current=bool(result.get('verified') and historical and (
            compare_refinement(result['actual_colors'],historical['actual_colors'],c.rules)['not_worse']
            if getattr(c,'refinement_anchor',None) is not None else result['rank']<=historical['rank'])),
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
                c.current=None;c.single_retry=True
                samples=c.samples or samples
                continue
            except TimeEnded:
                reason='time_used'
                try:c.restore()
                except TimeEnded:pass
                except RetryRequested:
                    if c.budget.can_input(5):
                        owner.event('native_retry_reset',status='zooming',backend='screenshot')
                        c.current=None;c.single_retry=True;samples=c.samples or samples
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
                        c.current=None;c.single_retry=True;break
                    owner.event('native_retry_reset',status='rejected',reason='insufficient_retry_time',backend='screenshot')
                    owner.event('native_retry_available',enabled=False,waiting_for_retry=True,backend='screenshot')
                if owner.stop.wait(.15):c.check()
                previous_frame=c.frame;c.capture('waiting-retry',save=False)
                # Passive readiness polling must not silently advance the
                # unregistered pose reference. The next action measures it.
                c.frame=previous_frame
            else:return result
    except PaletteEnded as exc:
        if c:
            c.current=None;c.safe_restore('palette_ended',interruption=exc)
            return _publish(c,'palette_ended')
        raise
    except Interrupted as exc:
        if c:
            c.current=None
            recovery=c.safe_restore('interrupted',interruption=exc)
            result=_publish(c,'interrupted')
            if recovery['verified']:return result
        raise
    except Exception as exc:
        if c:
            c.write('error.json',dict(error=str(exc),traceback=traceback.format_exc()))
            reason='processing_error';recovery=dict(attempted=False)
            try:
                c.check()
                # Processing failure after completed capture/registration can
                # leave a worse zoomed position. Use the measured best return;
                # a failed gesture with unknown completion cannot authorize it.
                if not c.input_in_progress and c.best:
                    recovery['attempted']=True;c.restore()
                if c.current is None:c.observe('error-current-actual')
            except (Interrupted,PaletteEnded) as stopped:
                c.current=None;reason='interrupted' if isinstance(stopped,Interrupted) else 'palette_ended'
            except Exception as restore_error:
                recovery['error']=type(restore_error).__name__+': '+str(restore_error)
                try:c.observe('error-current-actual')
                except (Interrupted,PaletteEnded) as stopped:
                    c.current=None;reason='interrupted' if isinstance(stopped,Interrupted) else 'palette_ended'
                except Exception:c.current=None
            recovery['verified']=bool(c.current and c.current['verified'])
            c.write('error-recovery.json',recovery)
            return _publish(c,reason)
        raise
    finally:
        if game is not None:game.release()
        if c is not None:c.close()
