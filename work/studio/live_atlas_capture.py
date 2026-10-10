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
from vision import (recognize, green_buttons, measure_board_motion, configure_ocr,
                    timer_bar_signal)
from atlas_masks import board_texture_mask
from workflow_budget import WorkflowBudget
from atlas_capture_worker import CaptureWorker
from scan_settling import ScanSettlingObserver
from session_store import ACTIVE_MARKER


def _validated_long_countdown(observations):
    """Return a later full reading that safely corrects a clipped first one.

    A short first OCR result (``19`` for a visible ``119``) is never replaced
    by one coincidental high reading.  Before input starts we require two
    independent, complete three-digit readings whose decrease follows elapsed
    time and whose progress-bar endpoint does not grow.  This helper
    deliberately returns ``None`` when the bar is unavailable: the conservative
    initial deadline is safer than inferring extra time from OCR alone.
    """
    valid=[row for row in observations if row and row[0] is not None and
           getattr(row[0],'seconds',None) is not None]
    if not valid or not 1<=int(valid[0][0].seconds)<=30:return None
    rows=[row for row in valid[1:] if 100<=int(row[0].seconds)<=180]
    if len(rows)<2:return None
    # Distinct captures are required; callers already append one row per new
    # frame, but retaining this check prevents duplicated test/OCR rows from
    # becoming deadline evidence.
    if len({float(row[1]) for row in rows})<2:return None
    for row in rows:
        elapsed=max(0.,float(row[1])-float(valid[0][1]))
        expected=int(valid[0][0].seconds)+100-elapsed
        if abs(float(row[0].seconds)-expected)>2.0:return None
    previous=rows[0]
    for row in rows[1:]:
        before,after=previous,row
        dt=max(0.,float(after[1])-float(before[1]))
        drop=int(before[0].seconds)-int(after[0].seconds)
        # OCR and capture each have small scheduling jitter.  Reject both an
        # increase and a jump that cannot be explained by elapsed time.
        tolerance=max(2.0,dt*.75+1.0)
        if drop<0 or abs(float(drop)-dt)>tolerance:return None
        previous=row
    bars=[row[3].get('fill_end') if len(row)>3 and row[3] else None
          for row in [valid[0],*rows]]
    if any(value is None for value in bars):return None
    # The filled bar may jitter by a few pixels, but it must not grow while
    # the timer is counting down.
    if any(float(current)-float(before)>3.0
           for before,current in zip(bars,bars[1:])):return None
    return rows[-1]


def _choose_countdown_observation(observations):
    """Choose a timer reading using independent frames and elapsed time.

    OCR variants from one frame are correlated.  A short sequence of frames
    is therefore used as the confidence boundary: ordinary readings should
    decrease by roughly the elapsed seconds, while a large high/low conflict
    is treated as a clipped OCR result and keeps the complete high reading.
    A corrected first-frame value is returned only with independent temporal
    and bar evidence; the caller may replace its provisional deadline before
    input starts. All ordinary readings keep the initial hard deadline.
    """
    valid=[row for row in observations if row and row[0] is not None and
           getattr(row[0],'seconds',None) is not None]
    if not valid:return None
    anchor=valid[0];anchor_scene,anchor_at=anchor[:2]
    values=[int(row[0].seconds) for row in valid]
    maximum=max(values);minimum=min(values)
    # OCR may clip the leading digit on the first frame (for example ``19``
    # while the actual timer is ``119``).  Treat a later, repeated three-digit
    # reading as the authoritative anchor. The entry-only caller may then
    # replace the provisional clipped deadline, bounded by the missing hundred
    # seconds and both complete readings.
    corrected=_validated_long_countdown(observations)
    if corrected is not None:
        return corrected
    # With a short first frame, a single later three-digit reading is not
    # enough evidence to extend the deadline.  Keep the original anchor until
    # the caller has collected a second confirming frame.
    if int(anchor_scene.seconds)<100 and maximum>=100:
        return anchor
    if maximum>=90 and maximum-minimum>=30:
        # A 119->41 style result is a crop/OCR conflict, not a real one
        # second countdown. Prefer the complete high reading; the deadline
        # calculation below still clamps to the anchor and cannot add time.
        return max(valid,key=lambda row:int(row[0].seconds))
    scored=[]
    for row in valid:
        scene,at=row[:2]
        elapsed=max(0.,float(at-anchor_at))
        expected=max(1.,float(anchor_scene.seconds)-elapsed)
        value=float(scene.seconds)
        monotonic_penalty=0. if value<=float(anchor_scene.seconds)+1 else 120.
        bar_penalty=0.
        if len(row)>3 and row[3] and anchor[3]:
            current_end=row[3].get('fill_end');anchor_end=anchor[3].get('fill_end')
            if current_end is not None and anchor_end is not None:
                # The filled bar should contract as time passes.
                bar_penalty=max(0.,float(current_end)-float(anchor_end)-3.)
        scored.append((abs(value-expected)+monotonic_penalty+bar_penalty*2.,row))
    # When two readings fit the elapsed-time model equally well, prefer the
    # later frame.  It carries the freshest countdown while preserving the
    # anchor whenever the bar signal contradicts the apparent increase.
    return min(scored,key=lambda item:(item[0],-float(item[1][1])))[1]


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


def summarize_zoom_calibration(measurements, current_scale=None):
    """Summarize one-notch directional zoom measurements.

    ``measurements`` contains the direct registration result for each wheel
    notch.  Keep the fitted affine matrix intact: callers that need to replay
    a pose can use it instead of reconstructing a transform from a rounded
    scalar.  The returned log steps are therefore derived from one notch,
    rather than from a multi-notch burst divided by its step count.
    """
    by_direction={int(row.get('steps', 0)): row.get('motion')
                  for row in measurements
                  if isinstance(row, dict)}
    down=by_direction.get(-1)
    up=by_direction.get(1)
    def measured(motion):
        try:
            if not isinstance(motion,dict):return None
            matrix=np.asarray(motion.get('matrix'),float)
            if matrix.shape!=(2,3) or not np.isfinite(matrix).all():return None
            linear=matrix[:,:2]
            if not np.allclose(linear,[[linear[0,0],-linear[1,0]],
                                       [linear[1,0],linear[0,0]]],atol=1e-6):return None
            scale=float(np.hypot(linear[0,0],linear[1,0]))
            angle=float(np.degrees(np.arctan2(linear[1,0],linear[0,0])))
            return dict(scale=scale,angle=angle,matrix=matrix)
        except (TypeError, ValueError):
            return None
    down_measurement=measured(down);up_measurement=measured(up)
    passed=bool(down_measurement and up_measurement and
                0<down_measurement['scale']<.998 and up_measurement['scale']>1.002 and
                abs(down_measurement['angle'])<.25 and
                abs(up_measurement['angle'])<.25)
    result=dict(passed=passed, measurements=list(measurements))
    if not passed:
        result.update(down_log_step=None, up_log_step=None,
                      current_scale=None)
        return result
    # These are the observed one-notch log responses.  They are deliberately
    # not extrapolated from a +/-4 burst.
    # The scalar in measure_board_motion is rounded for diagnostics.  Using
    # it as the detent spacing magnifies that rounding over long routes.
    # Derive the planning values from the retained affine matrices instead.
    down_scale=down_measurement['scale'];up_scale=up_measurement['scale']
    net_matrix=(np.vstack((up_measurement['matrix'],[0.,0.,1.]))@
                np.vstack((down_measurement['matrix'],[0.,0.,1.])))[:2]
    net_scale=float(np.hypot(net_matrix[0,0],net_matrix[1,0]))
    result.update(
        down_log_step=abs(float(np.log(down_scale))),
        up_log_step=abs(float(np.log(up_scale))),
        down_scale=down_scale,up_scale=up_scale,
        scale_source='measured_affine_matrix',net_matrix=net_matrix.tolist(),
        current_scale=None if current_scale is None else float(current_scale)*net_scale,
        net_scale=net_scale,
    )
    return result


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


def open_capture_game(stop, target=None, activate=False, *, log=lambda *a,**k:None, emit=None):
    """Wait for a game window without sending dye-entry input."""
    g=None
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
    return g


def wait_for_dye_board(g, stop, *, started=None, log=lambda *a,**k:None,
                      snap=None, emit=None, keep_active=lambda:None,
                      verify_countdown=True, progress_stage="zoom"):
    """Shared read-only entry and temporal countdown confirmation. No zoom."""
    started=time.monotonic() if started is None else started
    if snap is None:snap=lambda _name,_scene:g.capture()
    log('waiting',message='等待用户手动进入倒计时染色界面')
    scene=None;im=None
    while True:
        keep_active()
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
    waiting_image=im
    log('ready',board=scene.board,markers=scene.markers,cards=scene.cards,
        recognition_seconds=recognition_seconds,
        frame_elapsed_seconds=waiting_frame_at-started)
    original_at=time.monotonic()
    im=snap('original',scene)
    if verify_countdown:
        timed_scene=None
        timer_source='temporal'
        timer_attempts=4
        timer_recognition_seconds=0.
        # Pair the first OCR value with the frame/timestamp that produced it;
        # the later saved "original" frame may already be several seconds
        # newer on a slower machine.
        timer_observations=[(scene,waiting_frame_at,waiting_image,
                             timer_bar_signal(waiting_image))]
        # Every recheck
        # must capture a new frame; re-running OCR on ``im`` would only
        # duplicate the same pixels and could falsely satisfy the
        # two-observation confidence boundary (the source of the old
        # 119 -> 41 regression).
        for attempt in range(1,timer_attempts+1):
            if stop.wait(.25):raise Interrupted('已停止，鼠标已释放。')
            g.check()
            original_at=time.monotonic()
            im=snap('timer_recheck_%02d'%attempt,scene)
            # Snapshot encoding/IO can be slower than capture. Use the time
            # before capturing, so a delayed writer cannot grant extra input.
            observed_at=original_at
            recognition_started=time.monotonic()
            try:observed_scene=recognize(im,with_ocr=True,previous=scene,read_colors=False)
            except (ValueError,RuntimeError):observed_scene=None
            timer_recognition_seconds+=time.monotonic()-recognition_started
            if observed_scene is not None and observed_scene.seconds is not None:
                timer_observations.append((observed_scene,observed_at,im,
                                           timer_bar_signal(im)))
            valid_count=sum(row[0] is not None and row[0].seconds is not None
                            for row in timer_observations)
            log('timer_recheck',attempt=attempt,attempts=timer_attempts,
                recognized=bool(observed_scene is not None and
                                observed_scene.seconds is not None),
                seconds=None if observed_scene is None else observed_scene.seconds,
                valid_observations=valid_count)
            # Two independent frames are the normal confidence boundary.  A
            # suspicious short first reading (for example 19) needs two later
            # complete readings with temporal/bar evidence before it can be
            # replaced; one coincidental 119 must keep the conservative short
            # deadline.
            suspicious_short=(scene.seconds is not None and 1<=int(scene.seconds)<=30)
            high_conflict=any(int(row[0].seconds)>=100 for row in timer_observations[1:])
            if valid_count>=2 and not (suspicious_short and high_conflict):break
            if suspicious_short and _validated_long_countdown(timer_observations) is not None:
                break
            if emit:emit('atlas_progress',stage=progress_stage,message='正在复核倒计时识别')
        selected=_choose_countdown_observation(timer_observations)
        if selected is None or selected[0] is None or selected[0].seconds is None:
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
                emit('atlas_progress',stage=progress_stage,
                     message='倒计时复核暂时不可用，沿用首次识别结果')
            game_deadline=initial_game_deadline
        else:
            timed_scene,selected_at=selected[:2]
            corrected=_validated_long_countdown(timer_observations)
            if corrected is not None:
                # No game input has been issued in this read-only entry
                # helper. Replace a proven clipped first deadline only here,
                # with the earlier bound of every complete frame and the
                # recovered first value. Later input deadlines never extend.
                complete=[row for row in timer_observations
                          if row[0] is not None and int(row[0].seconds)>=100]
                game_deadline=min(initial_game_deadline+100,
                    *(float(row[1])+int(row[0].seconds) for row in complete))
                timer_source='corrected_clipped_first_frame'
            else:
                game_deadline=min(initial_game_deadline,selected_at+timed_scene.seconds)
        scene=timed_scene
        if game_deadline is None:
            game_deadline=initial_game_deadline
        budget=WorkflowBudget(ready_at,game_deadline)
        g.until=budget.deadline
        g.stage_until=budget.sampling_deadline
        g.check()
        log('timer',seconds=timed_scene.seconds,source=timer_source,
            recognition_seconds=timer_recognition_seconds,attempts=attempt,
            deadline_elapsed_seconds=game_deadline-started,
            workflow_deadline_elapsed_seconds=budget.workflow_deadline-started,
            effective_deadline_elapsed_seconds=budget.deadline-started,
            sampling_deadline_elapsed_seconds=budget.sampling_deadline-started,
            workflow_seconds=60)
    else:
        game_deadline=initial_game_deadline
        budget=WorkflowBudget(ready_at,game_deadline)
    return dict(scene=scene,image=im,game_deadline=game_deadline,
                ready_at=ready_at,budget=budget)


def acquire(folder,entry=None,strategy='legacy',stop=None,target=None,activate=False,entry_size=None,emit=None,row_stagger=0.,response_protocol='baseline',settling_probes=False,probe_cycles=3,probe_anchors=None,rules=None):
    if not np.isfinite(row_stagger) or not 0 <= row_stagger <= .1:
        raise ValueError('row_stagger must be between 0 and 0.1')
    if (response_protocol not in ('baseline','rotation_compare','zoom_reversibility') or
            (response_protocol!='baseline' and strategy!='response')):
        raise ValueError('Comparison protocol requires response diagnostics')
    if isinstance(probe_cycles, bool) or int(probe_cycles) != probe_cycles or int(probe_cycles) < 1:
        raise ValueError('Probe cycles must be a positive integer')
    probe_cycles = int(probe_cycles)
    stop=stop or threading.Event();g=None
    folder.mkdir(parents=True,exist_ok=False)
    active_marker=folder/ACTIVE_MARKER
    try:active_marker.write_text('active',encoding='ascii')
    except OSError:active_marker=None
    started=time.monotonic();records=[];game_deadline=None;session_scene=None;final_image=None
    input_started=False;worker=None
    active_touched=started
    def keep_active(force=False):
        nonlocal active_touched
        if active_marker is None:return
        now=time.monotonic()
        if not force and now-active_touched<30:return
        try:
            active_marker.touch()
            active_touched=now
        except OSError:pass
    def log(kind,**data):
        row=dict(elapsed_seconds=time.monotonic()-started,kind=kind,**data)
        records.append(row)
        (folder/'log.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
        keep_active(force=True)
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
        g=open_capture_game(stop,target,activate,log=log,emit=emit)
        if entry is not None or entry_size is not None:
            log('legacy_entry_ignored',message='入口坐标参数已忽略；等待用户手动进入倒计时染色界面')
        ready=wait_for_dye_board(g,stop,started=started,log=log,snap=snap,
            emit=emit,keep_active=keep_active,
            verify_countdown=strategy in ("grid","probe","response"))
        scene=ready["scene"];im=ready["image"];game_deadline=ready["game_deadline"]
        ready_at=ready["ready_at"];budget=ready["budget"]
        if rules is not None:
            from copy import deepcopy
            from dye_regions import region_count,bind_region_rules
            count=region_count(len(scene.cards))
            effective=deepcopy(list(rules[:count]))
            if emit:emit('region_layout',region_count=count,available_regions=[i<count for i in range(3)],rules=effective)
            log('region_binding',region_count=count,available_regions=list(range(count)),rules=effective)
            if not any(rule.get('enabled') for rule in effective):
                raise ValueError('本局没有已启用的可用区域，请启用区域 1 或 2。')
            rules=bind_region_rules(rules,count)
        detected_count=len(scene.cards) if len(scene.cards) in (2,3) else None
        if strategy in ("grid","probe","response"):
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
                try:candidate=recognize(candidate_im,with_ocr=False,previous=scene,region_count=detected_count)
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
                # and .99). Measure one native notch in each direction. A
                # multi-notch burst divided by its count hides quantization
                # and state-dependent response, while the affine matrix from
                # this single frame is directly usable by later analysis.
                calibration=[]
                for ticks in (-1,1):
                    g.wheel(scene.board,ticks);g.pause(.035)
                    observed=g.capture()
                    measurement_error=None
                    try:
                        motion=zoom_tracker.measure(im,observed,scene)
                    except Interrupted:raise
                    except Exception as exc:
                        motion=None;measurement_error=str(exc)
                    calibration.append(dict(steps=ticks,motion=motion,error=measurement_error,
                                            direction='down' if ticks<0 else 'up'))
                    im=observed
                summary=summarize_zoom_calibration(
                    calibration, previous_scale)
                # Keep a direct per-notch affine matrix in the event record;
                # scale/angle are convenient summaries, not replacements for
                # the measured transform.
                log('zoom_calibration',**summary)
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
                final_image,outcome=run_response_probe(
                    g,scene,final_image,snap,log,protocol=response_protocol,
                    probe_cycles=probe_cycles,probe_anchors=probe_anchors)
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
        if active_marker is not None:
            try:active_marker.unlink(missing_ok=True)
            except OSError:pass
    print(json.dumps(records[-1],indent=2))
    return dict(folder=folder,deadline=game_deadline,game=g,scene=session_scene,
                image=final_image,geometry=tuple(g.geometry()))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['preflight','acquire']);parser.add_argument('folder',type=Path)
    parser.add_argument('--entry',nargs=2,type=int)
    parser.add_argument('--strategy',choices=['legacy','grid','probe','response'],default='legacy')
    parser.add_argument('--response-protocol',choices=['baseline','rotation_compare','zoom_reversibility'],default='baseline')
    parser.add_argument('--probe-cycles',type=int,default=3,
                        help='Number of paired one-notch zoom cycles per anchor')
    parser.add_argument('--probe-anchors',nargs='+',choices=['center','offset','edge'],
                        default=None,help='Anchors for zoom reversibility diagnostics')
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
                     response_protocol=args.response_protocol,settling_probes=args.settling_probes,
                     probe_cycles=args.probe_cycles,probe_anchors=args.probe_anchors)
    finally:kernel.CloseHandle(mutex)
