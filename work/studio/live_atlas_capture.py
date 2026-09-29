"""Bounded, single-session capture for atlas research. Never confirms a dye.

The grid/probe workflows wait for the user to enter the timed dye screen
manually, then probe native zoom within a bounded step budget. The log records
whether a game zoom limit was actually observed. F9, focus/geometry changes and
the OCR-derived game deadline abort input. The nominal 60-second workflow
duration is recorded for performance review only and does not abort a run.
Raw frames remain local.
"""
import argparse
import ctypes as C
import json
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image, ImageGrab
from platform_win import Game, Interrupted, u
from window_target import WindowUnavailable, MultipleWindows
from vision import recognize, green_buttons, measure_board_motion, configure_ocr
from atlas_masks import board_texture_mask
from workflow_budget import WorkflowBudget
from atlas_capture_worker import CaptureWorker
from scan_settling import ScanSettlingObserver


def sampling_frame_is_safe(scene, shape, margin=8):
    """Whether a zoomed frame still contains the complete sampling geometry."""
    h, w = map(int, shape[:2])
    l, t, r, b = map(int, scene.board)
    if not (margin <= l < r <= w-margin and margin <= t < b <= h-margin):
        return False
    return all(l+margin <= int(x) < r-margin and t+margin <= int(y) < b-margin
               for x, y in scene.markers)


def zoom_sampling_steps(scales, safe, max_steps=48):
    """Choose the last safe frame from consecutive-frame scale ratios."""
    chosen = 0
    for index, (scale, ok) in enumerate(zip(scales, safe), 1):
        if index > max_steps or not ok or not np.isfinite(scale):
            break
        # A wheel notch that produces no measurable scale change is the game
        # limit; keep the previous frame rather than probing further.
        if abs(float(scale)-1.0) < .001:
            break
        chosen = index
    return chosen


class ZoomMotionTracker:
    """Reuse only the preceding immutable capture with identical geometry."""
    def __init__(self):
        self.features={}
        self.geometry=None
        self.mask=None

    def measure(self,before,after,scene):
        geometry=(tuple(scene.board),tuple(map(tuple,scene.markers)),
                  tuple(map(tuple,getattr(scene,'cards',()))))
        if geometry!=self.geometry:
            self.features.clear()
            self.mask=board_texture_mask(scene)
            self.geometry=geometry
        try:
            return measure_board_motion(before,after,scene.board,
                feature_cache=self.features,texture_mask=self.mask)
        finally:
            # measure_board_motion keeps source arrays alive to prevent ID
            # reuse. Retain only the current frame, including on failed fits;
            # a changed crop/mask cannot reuse features from old coordinates.
            for key in list(self.features):
                if key[0]!=id(after):del self.features[key]

    def clear(self):
        self.features.clear();self.mask=None;self.geometry=None


class CaptureGame(Game):
    def __init__(self,stop,target=None):
        super().__init__(stop,target=target)
        self.until=float('inf')  # Waiting never consumes the sampling budget.
        self.stage_until=float('inf')
    def check(self):
        if u.GetAsyncKeyState(0x78)&0x8000:self.stop.set()
        if time.monotonic()>=min(self.until,getattr(self,'stage_until',float('inf'))):raise Interrupted('游戏倒计时已到安全截止时间。')
        super().check()
    def pause(self,seconds):
        end=time.monotonic()+seconds
        while time.monotonic()<end:self.check();time.sleep(.025)
    def pause_until(self,end):
        """Scan-only absolute wait; other input/calibration pacing is unchanged."""
        while True:
            self.check()
            remaining=end-time.monotonic()
            if remaining<=0:break
            time.sleep(min(.025,remaining))
    def send(self,flags,dx=0,dy=0,data=0):
        # Base mouse paths contain short sleeps. Recheck at the final input
        # boundary so those sleeps cannot issue a new move/down past expiry.
        # Button releases must remain possible after F9, focus loss or expiry.
        if flags not in (4,16):
            self.check()
            scopes=tuple(getattr(self,'_input_scopes',()))
            for deadline,guard,expiry_factory in scopes:
                if time.monotonic()>=deadline:raise expiry_factory('输入阶段预留时间不足。')
                guard()
            # Guard callbacks may themselves consume time.
            self.check()
            for deadline,_guard,expiry_factory in scopes:
                if time.monotonic()>=deadline:raise expiry_factory('输入阶段预留时间不足。')
        return super().send(flags,dx,dy,data)

    @contextmanager
    def input_scope(self,deadline,guard,*,expiry_factory=Interrupted):
        """Bind an extra diagnostic guard to every final mouse input boundary.

        Releases remain possible during interruption. The scope never changes
        the preexisting game/workflow/stage deadlines and is removed on error.
        """
        if not np.isfinite(deadline) or not callable(guard) or not callable(expiry_factory):
            raise ValueError('Finite input deadline and guard callback required')
        if not hasattr(self,'_input_scopes'):self._input_scopes=[]
        self._input_scopes.append((float(deadline),guard,expiry_factory))
        try:
            yield
        finally:
            self._input_scopes.pop()


def coverage_fill_positions(board):
    """Five row-aligned poses for full-width, full-height marker corridors.

    Use the same rounded base-grid steps as the scan, keeping every fill on
    row 0 or 2. Mask simulations cover both saved period pairs regardless of
    marker height; real color and registration checks remain required.
    """
    left, top, right, bottom = map(int, board)
    width, height = right-left, bottom-top
    sx = max(1, round(width*.20)); sy = max(1, round(height*.40))
    return [dict(x=round(sx*x),y=sy*y) for x,y in
            ((2.5,0),(.5,2),(1.25,2),(4.5,2),(6.5,2))]


def grid_scan_plan(board, columns=8, rows=5, holdout_every=6, row_stagger=0.,
                   marker_column_fill=True, coverage_fill=True):
    """Return a bounded snake scan with interleaved leave-out frames.

    The plan covers both axes instead of spending the whole timed dye round on
    one horizontal strip.  Commands are relative drags in board pixels.  A
    holdout is captured at the reached pose but is deliberately excluded from
    atlas training, so the analyzer can stop on measured prediction error.
    """
    l, t, r, b = map(int, board)
    w = r - l
    h = b - t
    if columns < 2 or rows < 2 or holdout_every < 1:
        raise ValueError('scan grid must have at least two rows and columns')
    if not np.isfinite(row_stagger) or not 0 <= row_stagger <= .1:
        raise ValueError('row_stagger must be between 0 and 0.1')
    # Use a fixed fraction of the viewport.  Dividing the viewport by the
    # number of columns would cap the accumulated span below one period.
    # The period can be larger than the visible board. Accumulate enough
    # displacement on both axes to force wrapped returns while staying inside
    # the bounded capture budget.
    sx = max(1, round(w * .20))
    sy = max(1, round(h * .40))
    out = []
    base_count = 0
    current_x=current_y=0
    previous_shift=0
    for row in range(rows):
        direction = 1 if row % 2 == 0 else -1
        # Keep alternate rows aligned for vertical period evidence. Shift the
        # others sideways to observe phases hidden by fixed marker/line masks.
        shift=round((r-l)*row_stagger)*(0,1,0,-1)[row%4]
        base_xs=([shift+col*sx for col in range(columns)] if direction>0
                 else [shift+(columns-1-col)*sx for col in range(columns)])
        visits=[dict(x=x,y=row*sy,row=row,column=col,base=True,kind='base')
                for col,x in enumerate(base_xs)]
        # The full-height connector mask removes fixed screen columns. These
        # four intermediate poses break the 100px phase aliases measured in
        # the saved run, while keeping every horizontal drag at or below the
        # original step size. They add geometry coverage only; real pixels
        # still have to pass registration and held-out color checks.
        if marker_column_fill and row in (0,2):
            fractions=(.10,.90,1.30) if row==0 else (.50,)
            for fraction in fractions:
                column=round(fraction*w/sx,3)
                visits.append(dict(x=shift+round(fraction*w),y=row*sy,row=row,
                                   column=column,base=False,kind='marker_column_fill'))
        if coverage_fill:
            for pose in coverage_fill_positions((l,t,r,b)):
                target_row=min(range(rows),key=lambda candidate:abs(pose['y']-candidate*sy))
                if target_row==row:
                    visits.append(dict(x=pose['x'],y=pose['y'],row=row,
                                       column=round(pose['x']/sx,3),base=False,
                                       kind='coverage_fill'))
        visits.sort(key=lambda item:item['x'],reverse=direction<0)
        for visit in visits:
            if visit['base'] and row==0 and visit['column']==0:
                current_x,current_y=visit['x'],visit['y']
                continue
            dx=visit['x']-current_x;dy=visit['y']-current_y
            if visit['base']:
                base_count+=1
                holdout=base_count%holdout_every==0
            else:
                holdout=False
            out.append(dict(dx=dx,dy=dy,holdout=holdout,row=row,
                            column=visit['column'],supplemental=not visit['base'],
                            supplemental_kind=visit['kind']))
            current_x,current_y=visit['x'],visit['y']
        previous_shift=shift
    return out


def preflight(folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    result=dict(input_sent=False,passed=False,guards={},errors=[])
    try:
        configure_ocr(strict=True)
        result['ocr_available']=True
    except RuntimeError as exc:
        result['ocr_available']=False;result['errors'].append(str(exc))
    try:
        stop=threading.Event();g=CaptureGame(stop)
        # No focus change or input. A desktop capture may contain occlusion,
        # so retain foreground state and the PNG for the user's inspection.
        def readonly_capture():
            x,y,w,h=g.geometry()
            return np.array(ImageGrab.grab(bbox=(x,y,x+w,y+h),all_screens=True).convert('RGB'))
        im=readonly_capture();Image.fromarray(im).save(folder/'preparation.png')
        result.update(geometry=g.geometry(),dpi=int(u.GetDpiForWindow(g.hwnd)),
                      foreground=(u.GetForegroundWindow()==g.hwnd),
                      screenshot_size=[im.shape[1],im.shape[0]])
        results=result['guards']
        # A focus failure must not masquerade as a working stop/F9 guard.
        with patch.object(u,'GetForegroundWindow',return_value=g.hwnd), \
             patch.object(u,'GetAsyncKeyState',return_value=0):
            g.check();results['baseline_simulated']=True
            stop.set()
            try:g.check();results['stop_event']=False
            except Interrupted:results['stop_event']=True
            stop.clear()
            with patch.object(u,'GetAsyncKeyState',return_value=-32768):
                try:g.check();results['f9_guard_simulated']=False
                except Interrupted:results['f9_guard_simulated']=True
            stop.clear()
            with patch.object(u,'GetForegroundWindow',return_value=0):
                try:g.check();results['focus_guard_simulated']=False
                except Interrupted:results['focus_guard_simulated']=True
            x,y,w,h=g.initial
            with patch.object(g,'geometry',return_value=(x+1,y,w,h)):
                try:g.check();results['geometry_guard_simulated']=False
                except Interrupted:results['geometry_guard_simulated']=True
        elapsed=[]
        for _ in range(3):
            start=time.monotonic();readonly_capture();elapsed.append(time.monotonic()-start)
        result.update(capture_seconds=elapsed,green_buttons=green_buttons(im))
        result['passed']=result['ocr_available'] and all(results.values())
    except (Interrupted,RuntimeError,ValueError,OSError) as exc:
        result['errors'].append(str(exc))
    (folder/'preflight.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
    return result


def acquire(folder,entry=None,strategy='legacy',stop=None,target=None,activate=False,entry_size=None,emit=None,row_stagger=0.,response_protocol='baseline',settling_probes=False):
    if not np.isfinite(row_stagger) or not 0 <= row_stagger <= .1:
        raise ValueError('row_stagger must be between 0 and 0.1')
    if response_protocol not in ('baseline','rotation_compare') or (response_protocol!='baseline' and strategy!='response'):
        raise ValueError('Comparison protocol requires response diagnostics')
    stop=stop or threading.Event();g=None
    folder.mkdir(parents=True,exist_ok=False)
    started=time.monotonic();records=[];game_deadline=None;session_scene=None;final_image=None
    input_started=False;worker=None
    def log(kind,**data):
        row=dict(elapsed_seconds=time.monotonic()-started,kind=kind,**data)
        records.append(row)
        (folder/'log.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
        if kind=='waiting':
            try:print(data['message'],flush=True)
            except (UnicodeError,OSError,ValueError):pass  # Optional console output.
            if emit:emit('atlas_status',message=data['message'])
        if emit:
            if kind=='waiting':emit('atlas_progress',stage='waiting')
            elif kind=='ready':emit('atlas_progress',stage='zoom')
            elif kind=='timer':emit('atlas_progress',stage='zoom',remaining=data['seconds'])
            elif kind=='grid_plan':emit('atlas_progress',stage='capture',current=0,total=39+data.get('supplemental_moves',0))
            elif kind=='frame' and data.get('name','').startswith('grid_'):
                emit('atlas_progress',stage='capture',current=int(data['name'].split('_')[1]),total=48)
        return row
    def snap(name,scene=None,command=None,sample=None):
        if sample is None:
            capture_started=time.monotonic();im=g.capture();captured_at=time.monotonic()
        else:
            im=sample.image;capture_started=sample.capture_started;captured_at=sample.captured_at
        if worker is not None:
            record=log('frame',name=name,geometry=g.geometry(),captured_elapsed_seconds=captured_at-started,
                       capture_seconds=captured_at-capture_started,png_seconds=None,
                       png_compression=1,storage_error=None,background=True,
                       scan_timing=sample.timing if sample is not None else None)
            worker.submit(name,im,scene.board,record,command,g.check,
                          probes=sample.probes if sample is not None else ())
            return im
        # Lower compression changes PNG size/CPU cost, never RGB values.
        Image.fromarray(im).save(folder/(name+'.png'),compress_level=1)
        if scene is not None:
            l,t,r,b=scene.board
            Image.fromarray(im[t:b,l:r]).save(folder/(name+'_board.png'),compress_level=1)
        log('frame',name=name,geometry=g.geometry(),captured_elapsed_seconds=captured_at-started,
            capture_seconds=captured_at-capture_started,png_seconds=time.monotonic()-captured_at,
            png_compression=1)
        return im
    try:
        # Check before telling the user that manual entry can begin. Legacy
        # coordinates must never bypass the OCR precondition.
        if strategy in ('grid','probe','response'):
            configure_ocr(strict=True)
        next_window_notice=0.
        while g is None:
            if stop.is_set() or u.GetAsyncKeyState(0x78)&0x8000:
                stop.set();raise Interrupted('已停止，鼠标已释放。')
            try:g=CaptureGame(stop,target=target)
            except WindowUnavailable as exc:
                # Auto-detection may start before the game. Keep the session
                # cancellable while waiting; an ambiguous selection needs an
                # explicit choice and cannot resolve itself by waiting.
                if target is not None or isinstance(exc,MultipleWindows):raise
                if time.monotonic()>=next_window_notice:
                    log('waiting_window',message=str(exc))
                    if emit:emit('waiting',message=str(exc),seconds=None)
                    next_window_notice=time.monotonic()+5
                if stop.wait(.5):raise Interrupted('已停止，鼠标已释放。')
        if activate:
            try:g.focus()
            except RuntimeError as exc:
                message='未能自动切回游戏。请点击游戏窗口，程序会继续等待识别，无需再次开始。'
                log('activation',message=message,detail=str(exc))
                if emit:emit('activation',message=message)
        if entry is not None or entry_size is not None:
            log('legacy_entry_ignored',message='入口坐标参数已忽略；等待用户手动进入倒计时染色界面')
        log('waiting',message='等待用户手动进入倒计时染色界面')
        scene=None;im=None
        while True:
            # Launching the batch file temporarily focuses Explorer/console.
            # Waiting is read-only, so tolerate that focus loss until the user
            # brings the game forward; input guards remain strict after ready.
            if stop.is_set() or u.GetAsyncKeyState(0x78)&0x8000:
                stop.set(); raise Interrupted('已停止，鼠标已释放。')
            if stop.wait(.25):raise Interrupted('已停止，鼠标已释放。')
            try:
                waiting_frame_at=time.monotonic()
                im=g.capture_waiting()
                if im is None:continue
                recognition_started=time.monotonic()
                candidate=recognize(im,with_ocr=True,read_colors=False)
                recognition_seconds=time.monotonic()-recognition_started
                if candidate.seconds is not None:
                    scene=candidate;break
            except WindowUnavailable:
                if g.manual_target is not None:raise
                continue
            except (ValueError,RuntimeError):
                continue
        ready_at=time.monotonic()
        initial_game_deadline=waiting_frame_at+scene.seconds
        log('ready',board=scene.board,markers=scene.markers,cards=scene.cards,
            recognition_seconds=recognition_seconds,
            frame_elapsed_seconds=waiting_frame_at-started)
        original_at=time.monotonic()
        im=snap('original',scene)
        if strategy in ('grid','probe','response'):
            timed_scene=None
            timer_source='ocr'
            timer_attempts=4
            timer_recognition_seconds=0.
            for attempt in range(timer_attempts):
                if attempt:
                    if stop.wait(.25):raise Interrupted('已停止，鼠标已释放。')
                    g.check()
                    original_at=time.monotonic()
                    im=snap('timer_recheck_%02d'%attempt,scene)
                recognition_started=time.monotonic()
                try:timed_scene=recognize(im,with_ocr=True,previous=scene,read_colors=False)
                except (ValueError,RuntimeError):timed_scene=None
                timer_recognition_seconds+=time.monotonic()-recognition_started
                if timed_scene is not None and timed_scene.seconds is not None:break
                log('timer_recheck',attempt=attempt+1,attempts=timer_attempts,recognized=False)
                if emit:emit('atlas_progress',stage='zoom',message='正在复核倒计时识别')
            if timed_scene is None or timed_scene.seconds is None:
                # The waiting frame already provided a valid countdown and
                # established the hard deadline. A later frame may hide the
                # timer behind a transient animation or produce an OCR miss;
                # that is not a reason to abort the session before input.
                # Keep the conservative initial deadline and continue only
                # after the normal CaptureGame guard has passed.
                timed_scene=scene
                timer_source='initial'
                log('timer_recheck_fallback',seconds=scene.seconds,
                    message='倒计时复核暂时不可用，沿用首次识别结果；未延长安全截止时间。')
                if emit:
                    emit('atlas_progress',stage='zoom',
                         message='倒计时复核暂时不可用，沿用首次识别结果')
                game_deadline=initial_game_deadline
            else:
                game_deadline=min(initial_game_deadline,original_at+timed_scene.seconds)
            scene=timed_scene
            if game_deadline is None:
                game_deadline=initial_game_deadline
            budget=WorkflowBudget(ready_at,game_deadline)
            g.until=budget.deadline
            g.stage_until=budget.sampling_deadline
            g.check()
            log('timer',seconds=timed_scene.seconds,source=timer_source,
                recognition_seconds=timer_recognition_seconds,attempts=attempt+1,
                deadline_elapsed_seconds=game_deadline-started,
                workflow_deadline_elapsed_seconds=budget.workflow_deadline-started,
                effective_deadline_elapsed_seconds=budget.deadline-started,
                sampling_deadline_elapsed_seconds=budget.sampling_deadline-started,
                workflow_seconds=60)
            # Probe the game's own zoom limit in short bursts.  Capturing and
            # recognizing every single notch made acquisition unnecessarily
            # slow.  A burst is committed only when its final frame is safe;
            # if it crosses the native limit, the whole burst is reverted and
            # the previous safe frame remains the sampling reference.
            zoomed=0;previous_scale=1.0;last=im;remaining=48
            zoom_stop_reason='step_limit'
            zoom_tracker=ZoomMotionTracker()
            zoom_timing=dict(input_wait_seconds=0.,capture_seconds=0.,
                             recognition_seconds=0.,registration_seconds=0.)
            input_started=True
            while remaining:
                probe=min(4,remaining)
                tick=time.monotonic()
                g.wheel(scene.board,probe);g.pause(.035)
                zoom_timing['input_wait_seconds']+=time.monotonic()-tick
                tick=time.monotonic()
                candidate_im=g.capture()
                zoom_timing['capture_seconds']+=time.monotonic()-tick
                tick=time.monotonic()
                try:candidate=recognize(candidate_im,with_ocr=False,previous=scene)
                except (ValueError,RuntimeError):
                    zoom_timing['recognition_seconds']+=time.monotonic()-tick
                    zoom_stop_reason='recognition_failed'
                    g.wheel(scene.board,-probe);g.pause(.06);break
                zoom_timing['recognition_seconds']+=time.monotonic()-tick
                if not sampling_frame_is_safe(candidate,candidate_im.shape):
                    zoom_stop_reason='unsafe_geometry'
                    g.wheel(scene.board,-probe);g.pause(.06);break
                tick=time.monotonic()
                motion=zoom_tracker.measure(last,candidate_im,scene)
                zoom_timing['registration_seconds']+=time.monotonic()-tick
                if motion is None:
                    zoom_stop_reason='registration_failed'
                    g.wheel(scene.board,-probe);g.pause(.06);break
                scale=float(motion['scale'])
                if not np.isfinite(scale) or abs(scale-1.0)<.001:
                    zoom_stop_reason='no_scale_change' if np.isfinite(scale) else 'invalid_scale'
                    g.wheel(scene.board,-probe);g.pause(.06);break
                scene=candidate;im=candidate_im;last=im
                previous_scale*=scale;zoomed+=probe;remaining-=probe
            log('sampling_zoom',steps=zoomed,scale=previous_scale,stop_reason=zoom_stop_reason,
                game_limit_observed=(zoom_stop_reason=='no_scale_change'),timing=zoom_timing)
            if strategy in ('grid','response') and zoomed>=4:
                # The game's up/down ticks are not reciprocal (about 1.01
                # and .99). Measure both before generating any joint route.
                calibration=[]
                for ticks in (-4,4):
                    g.wheel(scene.board,ticks);g.pause(.035)
                    observed=g.capture()
                    measurement_error=None
                    try:
                        motion=zoom_tracker.measure(im,observed,scene)
                    except Interrupted:raise
                    except Exception as exc:
                        motion=None;measurement_error=str(exc)
                    calibration.append(dict(steps=ticks,motion=motion,error=measurement_error))
                    im=observed
                down,up=(row['motion'] for row in calibration)
                passed=bool(down and up and 0<down['scale']<.998 and up['scale']>1.002 and
                            abs(down.get('angle',0))<.25 and abs(up.get('angle',0))<.25)
                log('zoom_calibration',passed=passed,measurements=calibration,
                    down_log_step=abs(float(np.log(down['scale'])/4)) if passed else None,
                    up_log_step=abs(float(np.log(up['scale'])/4)) if passed else None,
                    current_scale=previous_scale*down['scale']*up['scale'] if passed else None)
            zoom_tracker.clear()
            log('sampling_ready',board=scene.board,markers=scene.markers,cards=scene.cards)
            session_scene=scene
            # The last zoom probe leaves the cursor over the palette. Park it
            # outside the board before the reference frame so the captured
            # cursor sprite cannot be stitched into the periodic atlas.
            g.move_to((int(g.initial[2]*.5),int(g.initial[3]*.15)));g.pause(.16)
            if strategy=='grid':
                worker=CaptureWorker(folder,dict(board=list(scene.board),
                                     markers=[list(p) for p in scene.markers]))
            final_image=snap('max_sampling',scene)
            if strategy=='response':
                from gesture_response_probe import run_response_probe
                try:g.response_probe_dpi=int(u.GetDpiForWindow(g.hwnd)) or None
                except (AttributeError,TypeError,ValueError,OSError):g.response_probe_dpi=None
                final_image,outcome=run_response_probe(g,scene,final_image,snap,log,protocol=response_protocol)
                log('CAPTURE_COMPLETE',strategy='response',outcome=outcome)
                return dict(folder=folder,deadline=budget.deadline,game_deadline=game_deadline,
                    workflow_deadline=budget.workflow_deadline,ready_at=ready_at,
                    game=g,scene=scene,image=final_image,geometry=tuple(g.geometry()),outcome=outcome)
            if strategy=='probe':
                from point_sampling_probe import run_point_probe
                # Dedicated diagnostic budget, still bounded by the earlier
                # OCR-derived deadline and all CaptureGame guards.
                g.stage_until=min(g.stage_until,time.monotonic()+25)
                final_image=run_point_probe(g,scene,final_image,snap,log)
                log('CAPTURE_COMPLETE',strategy='probe',
                    message='Point sampling diagnostic complete; no dye confirmation or cancel click sent.')
                return dict(folder=folder,deadline=min(g.until,g.stage_until),game_deadline=game_deadline,
                            workflow_deadline=budget.workflow_deadline,ready_at=ready_at,game=g,scene=scene,
                            image=final_image,geometry=tuple(g.geometry()))
            plan=grid_scan_plan(scene.board,row_stagger=row_stagger)
            settling=ScanSettlingObserver(scene,observe=settling_probes)
            log('grid_plan',columns=8,rows=5,row_stagger=row_stagger,
                marker_column_fill=True,coverage_fill=True,
                marker_column_fill_moves=sum(a['supplemental_kind']=='marker_column_fill' for a in plan),
                coverage_fill_moves=sum(a['supplemental_kind']=='coverage_fill' for a in plan),
                supplemental_moves=sum(a['supplemental'] for a in plan))
            for index,action in enumerate(plan,1):
                sample=settling.capture_step(g,scene,action,final_image)
                final_image=snap('grid_%03d'%index,scene,command=action,sample=sample)
                log('command',dx=action['dx'],dy=action['dy'],holdout=action['holdout'],
                    row=action['row'],column=action['column'],
                    supplemental=action['supplemental'],
                    supplemental_kind=action['supplemental_kind'])
            g.check()
            processing_started=time.monotonic()
            prepared=worker.close()
            log('capture_processing',wait_seconds=time.monotonic()-processing_started,
                alignment_seconds=worker.alignment.seconds,alignment_error=worker.error)
            log('scan_settling_summary',**settling.summary())
            log('CAPTURE_COMPLETE',strategy='grid',message='No dye confirmation or cancel click sent. Inspect and cancel next.')
            # Only the completed sampling stage ends. The workflow's shared
            # deadline stays unchanged through building, default and choice.
            g.stage_until=float('inf')
            return dict(folder=folder,deadline=budget.deadline,game_deadline=game_deadline,
                        workflow_deadline=budget.workflow_deadline,ready_at=ready_at,game=g,scene=session_scene,
                            image=final_image,geometry=tuple(g.geometry()),prepared=prepared)
        g.until=time.monotonic()+90
        input_started=True
        for i in range(70):
            g.wheel(scene.board,-1);g.pause(.065)
        g.move_to((int(g.initial[2]*.5),int(g.initial[3]*.15)));g.pause(.6)
        snap('low_0',scene)
        l,t,r,b=scene.board
        # Overlapping shifts; no presumed 710-pixel period and no rotation.
        dx=round((r-l)*.16);dy=round((b-t)*.11)
        for i in range(1,9):
            g.drag(scene.board,dx,0)
            g.move_to((int(g.initial[2]*.5),int(g.initial[3]*.15)));g.pause(.30)
            snap('scan_%02d'%i,scene);log('command',dx=dx,dy=0)
        g.drag(scene.board,0,dy)
        g.move_to((int(g.initial[2]*.5),int(g.initial[3]*.15)));g.pause(.3)
        snap('heldout_y',scene);log('command',dx=0,dy=dy)
        g.drag(scene.board,round(dx*.43),round(dy*.37))
        g.move_to((int(g.initial[2]*.5),int(g.initial[3]*.15)));g.pause(.3)
        snap('heldout_xy',scene);log('command',dx=round(dx*.43),dy=round(dy*.37))
        log('CAPTURE_COMPLETE',message='No dye confirmation or cancel click sent. Inspect and cancel next.')
    except Exception as e:
        log('ABORTED',message=str(e));raise
    finally:
        if input_started:g.send(4);g.send(16)
        if worker is not None:worker.close()
    print(json.dumps(records[-1],indent=2))
    return dict(folder=folder,deadline=game_deadline,game=g,scene=session_scene,
                image=final_image,geometry=tuple(g.geometry()))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['preflight','acquire']);parser.add_argument('folder',type=Path)
    parser.add_argument('--entry',nargs=2,type=int)
    parser.add_argument('--strategy',choices=['legacy','grid','probe','response'],default='legacy')
    parser.add_argument('--response-protocol',choices=['baseline','rotation_compare'],default='baseline')
    parser.add_argument('--row-stagger',type=float,default=0.,choices=(0.,.05),
                        help='Optional 5%% row offset for the next capture-only calibration')
    parser.add_argument('--settling-probes',action='store_true',
                        help='Record extra early scan frames for offline settling diagnostics')
    args=parser.parse_args()
    kernel=C.windll.kernel32
    kernel.CreateMutexW.argtypes=[C.c_void_p,C.c_bool,C.c_wchar_p];kernel.CreateMutexW.restype=C.c_void_p
    kernel.CloseHandle.argtypes=[C.c_void_p]
    mutex=kernel.CreateMutexW(None,False,'Local\\MabinogiDyeScanV2')
    if not mutex or kernel.GetLastError()==183:raise RuntimeError('Another capture process or historical experiment is active')
    try:
        if args.mode=='preflight':
            if not preflight(args.folder)['passed']:raise SystemExit(1)
        else:acquire(args.folder,args.entry,args.strategy,row_stagger=args.row_stagger,
                     response_protocol=args.response_protocol,settling_probes=args.settling_probes)
    finally:kernel.CloseHandle(mutex)
