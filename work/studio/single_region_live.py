"""Windows IO for fast current-board search. Never applies a dye."""
import time
from dataclasses import replace
from pathlib import Path
import numpy as np

from atlas_runtime import motion
from execution_diagnostics import execution_diagnostics
from live_atlas_capture import open_capture_game, wait_for_dye_board
from result_history import describe_result
from session_store import ACTIVE_MARKER
from single_region_search import QuickSearchLimits, run_single_region
from vision import configure_ocr, read_codes


def result_fields(result, rules):
    measured=describe_result(result.get('actual_colors') or [None]*3,rules)
    return dict(result,actual_deltas=[row['delta'] for row in measured['regions']],
                maximum=measured['maximum'],average=measured['average'])


class SingleRegionIO:
    def __init__(self, owner, game, scene, folder, rules):
        self.owner,self.g,self.scene,self.folder,self.rules=owner,game,scene,Path(folder),rules
        self.last_frame=self.best_frame=None
        self.move_count=0
        self.code_cache={}
        self.motion_action=None
        # SIFT descriptors for the latest board frames are reused by the next
        # drag/zoom registration.  The cache is identity-safe and bounded in
        # atlas_runtime.motion; it never changes the registration gates.
        self.motion_feature_cache={}
        self.code_read_stats=dict(calls=0,ocr_passes=0,reused_cards=0)

    def check(self):self.g.check()
    def clock(self):return time.monotonic()
    def pause(self,seconds):self.g.pause(seconds)

    def capture(self):
        self.check()
        # Keep the cursor outside the game client while sampling.  Moving it
        # over the HUD can change the tooltip/overlay and invalidate a native
        # pixel candidate, especially on compact or resized windows.
        self.g.move_to((-20, -20))
        self.last_frame=self.g.capture()
        return self.last_frame

    def read(self,image,*,enabled,deadline):
        self.check()
        self.code_read_stats['calls']+=1
        if self.clock()>=deadline:return [None]*3
        output=[None]*3;needed=list(enabled);cards={}
        for index,(x,y,w,h) in enumerate(self.scene.cards):
            if not enabled[index]:continue
            pixels=image[y:y+h,x:x+w,:3]
            geometry=(tuple(image.shape),str(image.dtype),(x,y,w,h))
            complete=pixels.shape==(h,w,3) and w>0 and h>0
            cached=self.code_cache.get(index)
            if complete and cached is not None and cached[0]==geometry and np.array_equal(pixels,cached[1]):
                output[index]=cached[2];needed[index]=False
                self.code_read_stats['reused_cards']+=1
            else:cards[index]=(geometry,pixels,complete)
        if any(needed):
            fresh=read_codes(image,self.scene.cards,self.scene.markers,needed,
                             deadline=deadline,check=self.check)
            self.code_read_stats['ocr_passes']+=1
            for index,(geometry,pixels,complete) in cards.items():
                output[index]=fresh[index]
                if complete and fresh[index] is not None:
                    self.code_cache[index]=(geometry,pixels.copy(),fresh[index])
                else:self.code_cache.pop(index,None)
        self.check()
        return output

    def drag(self,board,dx,dy):
        self.check()
        self.move_count+=1
        self.motion_action='drag'
        return self.g.drag(board,int(dx),int(dy))

    def wheel(self,board,steps,anchor=None):
        self.check()
        self.move_count+=1
        self.motion_action='wheel'
        return self.g.wheel(board,int(steps),anchor=anchor)

    def measure(self,before,after,scene):
        self.check()
        diagnostics={}
        measured=motion(before,after,scene,diagnostics,
                        feature_cache=self.motion_feature_cache)
        # Zoom resampling legitimately changes RGB values even when SIFT has
        # a strong affine fit.  Keep that geometry for pose tracking so a
        # saved verified result can still be restored; retain the strict
        # material-RGB gate for ordinary drags where a mismatch indicates an
        # unsafe registration.  The fallback is only used for the action that
        # was explicitly marked as a wheel input and is never inferred from a
        # caller-provided frame pair.
        if (measured is None and self.motion_action=='wheel' and
                diagnostics.get('reason')=='material_rgb_mismatch'):
            for attempt in reversed(diagnostics.get('attempts') or []):
                matrix=attempt.get('matrix')
                if matrix is None:continue
                try:
                    raw=np.asarray(matrix,float)
                    if raw.shape!=(2,3) or not np.isfinite(raw).all():continue
                    measured=dict(matrix=raw.tolist(), origin=list(scene.board[:2]),
                                  geometry_only=True)
                    diagnostics['geometry_only']=True
                    break
                except (TypeError,ValueError):
                    continue
        self.motion_action=None
        self.check()
        self.owner.event('single_registration',step=self.move_count,
                         measured=measured,diagnostics=diagnostics)
        execution_diagnostics.submit(self.folder,'step-%02d'%self.move_count,
            dict(measured=measured,diagnostics=diagnostics),
            {'step-%02d-before.png'%self.move_count:before,
             'step-%02d-after.png'%self.move_count:after})
        return measured

    def emit(self,kind,**data):
        if kind=='single_best':self.best_frame=self.last_frame
        if kind=='single_verified':data=result_fields(data,self.rules)
        self.owner.event(kind,**data)


def run_live_single_region(owner,rules,*,target=None,activate=False,**_context):
    """Use the shared countdown entry, then search without atlas acquisition."""
    configure_ocr(strict=True)
    folder=Path(owner.folder)/'single_search'
    folder.mkdir(parents=True,exist_ok=True)
    marker=Path(owner.folder)/ACTIVE_MARKER
    try:marker.write_text('active',encoding='ascii')
    except OSError:pass
    started=time.monotonic();game=None;io=None;result=None
    touched=started
    def keep_active():
        nonlocal touched
        now=time.monotonic()
        if now-touched<30:return
        try:marker.touch()
        except OSError:pass
        touched=now
    def log(kind,**data):
        owner.event('single_entry_'+kind,elapsed_seconds=time.monotonic()-started,**data)
        if kind=='waiting':owner.event('waiting',message=data['message'],seconds=None)
    def snap(name,scene):
        image=game.capture()
        execution_diagnostics.submit(folder,name,dict(board=scene.board,markers=scene.markers),
                                     {name+'.png':image})
        return image
    try:
        owner.event('single_progress',stage='waiting')
        game=open_capture_game(owner.stop,target,activate,log=log,emit=owner.event)
        ready=wait_for_dye_board(game,owner.stop,started=started,log=log,snap=snap,
                                keep_active=keep_active,
                                emit=lambda _kind,**data:owner.event('single_progress',**data),
                                progress_stage='observe')
        io=SingleRegionIO(owner,game,ready['scene'],folder,rules)
        # Real rounds need an explicit tail for final positioning plus two
        # consecutive HEX reads.  Keep this policy at the live boundary so
        # deterministic/offline callers can continue to control their own
        # synthetic deadline budget.
        live_limits = replace(QuickSearchLimits(), finish_reserve_seconds=15.)
        result=run_single_region(io,ready['scene'],rules,game_deadline=ready['budget'].deadline,
                                 search_started_at=ready['ready_at'], limits=live_limits)
        result=result_fields(result,rules)
        result['code_read_stats']=dict(io.code_read_stats)
        result['elapsed_seconds']=time.monotonic()-started
        owner.event('single_summary',**result)
        return result
    finally:
        # Releases remain valid after F9, geometry/focus loss or deadline.
        if game is not None:
            for flag in (4,16):
                try:game.send(flag)
                except (RuntimeError,OSError):pass
        if io is not None:
            frames={}
            if io.last_frame is not None:frames['final.png']=io.last_frame
            if io.best_frame is not None:frames['best.png']=io.best_frame
            execution_diagnostics.submit(folder,'result',dict(result=result,rules=rules,
                elapsed_seconds=time.monotonic()-started,stop_requested=owner.stop.is_set()),frames)
        try:marker.unlink(missing_ok=True)
        except OSError:pass
