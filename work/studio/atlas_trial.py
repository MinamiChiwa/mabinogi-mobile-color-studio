"""Experimental selection -> measured positioning -> twice-read game HEX.

Waits for the user to enter dye. Reuses a cached atlas ONLY after current-frame
texture and color validation. Never clicks entry, final dye, or cancel buttons.
"""
import argparse
import ctypes as C
import json
import queue
import threading
import time
import uuid
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
import pytesseract
from platform_win import u,Interrupted
from live_atlas_capture import CaptureGame
from vision import recognize,read_codes,ocr,measure_board_motion
from live_atlas_capture import sampling_frame_is_safe
from periodic_atlas import PeriodicAtlas,translation_candidates
from atlas_execution import (Context,CandidateBatch,execute_candidate,checked_translation,
                              reposition_budget,CandidateExpired)
from search_overlay import SearchOverlay
from atlas_runner import AtlasController
import customtkinter as ct


def timer(image):
    h,w=image.shape[:2]
    # Landscape timer independently validated against round-five native frames.
    if w<=h:raise RuntimeError('Trial currently requires a landscape window')
    text=ocr(image[round(h*.017):round(h*.065),round(w*.039):round(w*.074)],'0123456789')
    return int(text) if text.isdigit() and 1<=int(text)<=120 else None


def calculation_should_stop(stop,deadline,now,default_reserve=11.):
    """Stop only when the worst bounded default move can no longer be reserved."""
    return stop.is_set() or now>=deadline-default_reserve


def texture_mask(scene,shape):
    l,t,r,b=scene.board;h,w=b-t,r-l;y,x=np.mgrid[:h,:w]
    mask=(x>30)&(x<w-30)&(y>30)&(y<h-30)
    spacing=scene.markers[1][0]-scene.markers[0][0]
    for mx,my in scene.markers:mask &= abs(x-(mx-l))>max(36,spacing*.08)
    for border in (spacing,2*spacing):mask &= abs(x-border)>20
    return mask.astype(np.uint8)*255


def motion(a,b,scene):
    l,t,r,bottom=scene.board
    mask=texture_mask(scene,a.shape)
    detector=cv2.SIFT_create(nfeatures=2400)
    ka,da=detector.detectAndCompute(cv2.cvtColor(a[t:bottom,l:r],cv2.COLOR_RGB2GRAY),mask)
    kb,db=detector.detectAndCompute(cv2.cvtColor(b[t:bottom,l:r],cv2.COLOR_RGB2GRAY),mask)
    if da is None or db is None or len(db)<2:return None
    pairs=cv2.BFMatcher().knnMatch(da,db,k=2)
    good=[p[0] for p in pairs if len(p)==2 and p[0].distance<.7*p[1].distance]
    if len(good)<20:return None
    matrix,inliers=cv2.estimateAffinePartial2D(np.float32([ka[m.queryIdx].pt for m in good]),
                      np.float32([kb[m.trainIdx].pt for m in good]),method=cv2.RANSAC,ransacReprojThreshold=1.5)
    # Repeated tiles create multiple valid displacement clusters. Require enough
    # inliers plus independent same-material RGB agreement, not a majority vote.
    if matrix is None or inliers.sum()<40 or inliers.mean()<.3:return None
    yy,xx=np.where(mask[::8,::8]>0);xx=xx*8;yy=yy*8
    points=np.column_stack((xx,yy))@matrix[:,:2].T+matrix[:,2]
    px,py=points.T;w=r-l;h=bottom-t
    regions=len(scene.markers)
    good=(px>0)&(px<w-1)&(py>0)&(py<h-1)&(np.floor(xx/(w/regions))==np.floor(px/(w/regions)))
    good &= mask[np.clip(np.rint(py).astype(int),0,h-1),np.clip(np.rint(px).astype(int),0,w-1)]>0
    if good.sum()<200:return None
    actual=cv2.remap(b[t:bottom,l:r].astype(np.float32),px[good,None].astype(np.float32),py[good,None].astype(np.float32),cv2.INTER_LINEAR).reshape(-1,3)
    rgb_rmse=float(np.sqrt(np.mean((actual-a[t+yy[good],l+xx[good]])**2)))
    if rgb_rmse>10:return None
    return dict(matrix=matrix.tolist(),angle=float(np.degrees(np.arctan2(matrix[1,0],matrix[0,0]))),
                scale=float(np.hypot(matrix[0,0],matrix[1,0])),inliers=int(inliers.sum()),rgb_rmse=rgb_rmse)


def load_atlas(path):
    with np.load(path,allow_pickle=False) as saved:
        colors=saved['colors'].astype(float);valid=saved['valid'];count=saved['count']*valid
        atlas=PeriodicAtlas(saved['basis'],saved['origin'],colors.shape[1],regions=colors.shape[0])
        atlas.count=count;atlas.total=colors*count[...,None]
        atlas.squared=(colors**2+saved['rmse'][...,None]**2)*count[...,None]
    return atlas


def load_reference_frame(archive):
    """Load the native reference frame from legacy or grid capture archives."""
    archive = Path(archive)
    # The current workflow is captured at the game's maximum safe zoom.
    # Keep legacy frames only as a final fallback for old archives.
    candidates = [archive / 'max_sampling.png', archive / 'low_0.png']
    candidates.extend(sorted(archive.glob('grid_*.png')))
    candidates.extend(sorted(archive.glob('scan_*.png')))
    for path in candidates:
        if path.exists():
            return np.array(Image.open(path).convert('RGB'))
    raise FileNotFoundError(f'No reference capture frame found in {archive}')


def zoom_to_safe_maximum(g, scene, initial, deadline, max_notches=48):
    """Reach the native zoom limit with bounded captures.

    Four wheel notches are tested per capture to avoid spending most of the
    round on screenshots. The final partial probe refines the last safe frame.
    """
    frame = initial
    previous = frame
    scale_total = 1.0
    steps = 0
    remaining = max_notches
    while remaining:
        if time.monotonic() >= deadline - 8:
            raise RuntimeError('剩余时间不足以完成最大倍率采样')
        probe = min(4, remaining)
        g.wheel(scene.board, probe)
        g.pause(.035)
        candidate_im = g.capture()
        try:
            candidate = recognize(candidate_im, with_ocr=False, previous=scene)
        except (ValueError, RuntimeError):
            g.wheel(scene.board, -probe); g.pause(.06)
            break
        if not sampling_frame_is_safe(candidate, candidate_im.shape):
            g.wheel(scene.board, -probe); g.pause(.06)
            break
        measured = measure_board_motion(previous, candidate_im, scene.board)
        if measured is None or not np.isfinite(float(measured['scale'])):
            g.wheel(scene.board, -probe); g.pause(.06)
            break
        scale = float(measured['scale'])
        if abs(scale - 1.0) < .001:
            g.wheel(scene.board, -probe); g.pause(.06)
            break
        scene = candidate
        frame = previous = candidate_im
        scale_total *= scale
        steps += probe
        remaining -= probe
    return scene, frame, steps, scale_total


class Adapter:
    def perform_gesture(self, gesture):
        self.g.perform_gesture(gesture)
        self.g.move_to((int(self.g.initial[2]*.5),int(self.g.initial[3]*.15)))

    def __init__(self,g,scene,session):self.g=g;self.scene=scene;self.session=session
    def check(self):self.g.check()
    def context(self):
        return Context(self.session,tuple(self.g.geometry()),tuple(self.scene.board),tuple(map(tuple,self.scene.markers)))
    def capture(self):return self.g.capture()
    def motion(self,a,b):return motion(a,b,self.scene)
    def drag(self,dx,dy):
        self.g.drag(self.scene.board,dx,dy)
        self.g.move_to((int(self.g.initial[2]*.5),int(self.g.initial[3]*.15)))
    def pause(self,s):self.g.pause(s)
    def read_codes(self,image):return read_codes(image,self.scene.cards,self.scene.markers)
    def release(self):self.g.send(4);self.g.send(16)


def run(args):
    pytesseract.pytesseract.tesseract_cmd=str(args.ocr.resolve())
    # Check the component before any game input.
    pytesseract.get_tesseract_version()
    atlas=load_atlas(args.archive/'analysis/expanded/atlas.npz')
    reference=load_reference_frame(args.archive)
    reference_scene=recognize(reference,False)
    args.output.mkdir(parents=True,exist_ok=False)
    events=queue.Queue();choices=queue.Queue();stop=threading.Event();session=uuid.uuid4().hex
    def emit(kind,data):
        with (args.output/'events.jsonl').open('a',encoding='utf-8') as f:
            f.write(json.dumps(dict(time=time.time(),kind=kind,**data),ensure_ascii=False)+'\n')
        events.put((kind,data))
    def worker():
        batch=None;g=None
        try:
            g=CaptureGame(stop);g.until=time.monotonic()+args.wait_seconds
            emit('trial_status',dict(title='等待本局染色界面',message='请进入普通染色；教学结束后自动验证颜色板。F9停止。'))
            while True:
                if stop.is_set() or time.monotonic()>g.until:raise Interrupted('Waiting cancelled or expired')
                im=g.capture_waiting()
                if im is None:
                    stop.wait(.2);continue
                try:
                    # Use the scene OCR crop as a second timer path; the
                    # teaching overlay can obscure the narrow legacy crop.
                    scene=recognize(im,True);seconds=scene.seconds or timer(im)
                    if seconds is not None and seconds>=90:break
                except ValueError:pass
                stop.wait(.4)
            deadline=time.monotonic()+seconds-15;g.until=deadline
            emit('trial_status',dict(title='正在放大并采样本局颜色板',message='使用游戏内缩放逐步放大到最大安全倍率，再拼接多个周期。'))
            # Probe the game's native zoom limit one notch at a time.  The
            # last frame that remains fully recognized and inside the window
            # is the sampling reference; never use a fixed shrink-to-fit loop.
            scene,current,zoomed,previous_scale = zoom_to_safe_maximum(
                g,scene,im,deadline)
            emit('sampling_zoom',dict(steps=zoomed,scale=previous_scale,board=scene.board))
            g.move_to((int(g.initial[2]*.5),int(g.initial[3]*.15)));g.pause(.5)
            current=g.capture();scene=recognize(current,False)
            if tuple(scene.board)!=tuple(reference_scene.board):
                raise RuntimeError('Board geometry differs from cached atlas; a fresh capture is required')
            try:
                displacement=checked_translation(motion(reference,current,scene))
            except CandidateExpired as exc:
                raise RuntimeError(
                    '本局最大倍率与归档采样倍率无法对齐，配色方案不能安全复用；请用本局最大倍率重新采集颜色板。'
                ) from exc
            l,t,r,b=scene.board;mask=texture_mask(scene,current.shape)>0
            y,x=np.where(mask[::9,::9]);x=x*9;y=y*9
            checks=[]
            for region in range(len(scene.markers)):
                bank=(x>(r-l)*region/len(scene.markers)+25)&(x<(r-l)*(region+1)/len(scene.markers)-25)
                points=np.column_stack((x[bank],y[bank]))
                predicted,valid=atlas.sample(region,points,displacement)
                actual=current[t+y[bank],l+x[bank]]
                rmse=float(np.sqrt(np.mean((predicted[valid]-actual[valid])**2))) if valid.any() else float('inf')
                checks.append(dict(region=region+1,coverage=float(valid.mean()),rgb_rmse=rmse))
                if valid.mean()<.75 or rmse>8:raise RuntimeError('Cached material colors do not match this session')
            emit('atlas_revalidated',dict(checks=checks,translation=displacement.tolist()))
            Image.fromarray(current).save(args.output/'known-reachable.png')
            codes=read_codes(current,scene.cards,scene.markers)
            g.pause(.2)
            if any(c is None for c in codes) or codes!=read_codes(g.capture(),scene.cards,scene.markers):
                raise RuntimeError('Known reachable game colors could not be read twice')
            rules=[dict(enabled=True,colors=[c],exact=False,tolerance=4) for c in codes]
            # Move away before publishing candidates, so the trial exercises real
            # positioning rather than selecting a zero-motion current pose.
            adapter=Adapter(g,scene,session);adapter.drag(120,90);g.pause(.2)
            moved=g.capture();displacement+=checked_translation(motion(current,moved,scene))
            emit('trial_status',dict(title='计算可选方案',message='目标使用本局刚读取的已知可达颜色。'))
            candidates=translation_candidates(atlas,np.array(scene.markers)-[l,t],rules,displacement,
                                               cancelled=lambda:calculation_should_stop(stop,deadline,time.monotonic()))
            g.check()
            if not candidates:raise RuntimeError('No supported candidates')
            reference_choice=g.capture()
            if np.linalg.norm(checked_translation(motion(moved,reference_choice,scene)))>1:
                raise RuntimeError('Board moved during calculation')
            batch=CandidateBatch(candidates,adapter.context(),deadline)
            controller=AtlasController(batch,scene.board,time.monotonic)
            default_event=controller.begin_default();default=default_event.data['candidate']
            default_budget=reposition_budget(default,time.monotonic(),deadline,scene.board,
                                             markers=scene.markers)
            if not default_budget['allowed']:
                batch.invalidate()
                emit('atlas_default_unavailable',dict(message='剩余时间不足以安全定位并复核自动最佳方案，未发送定位操作。',
                                                       budget=default_budget))
                return
            emit('atlas_candidates',dict(batch_id=batch.id,candidates=candidates,
                                         default_id=default['id'],seconds=int(deadline-time.monotonic())-12))
            result=execute_candidate(adapter,batch,batch.id,None,reference_choice,rules,emit,
                                     reservation='default')
            Image.fromarray(g.capture()).save(args.output/'default-verified.png')
            controller.default_verified(result)
            emit('atlas_default_verified',result)
            # The default pose is already safe.  A late or absent choice keeps
            # it; only a choice with enough time for repositioning and HEX
            # verification starts a second, guarded execution.
            while True:
                g.check()
                if time.monotonic()>=deadline-12:
                    event=controller.selection_expired();emit(event.kind,event.data)
                    break
                try:chosen_batch,chosen_id=choices.get(timeout=.05)
                except queue.Empty:continue
                if chosen_batch!=batch.id:continue
                event=controller.choose(chosen_id)
                if event.kind=='atlas_choice_rejected':
                    emit(event.kind,event.data)
                    break
                try:
                    reference_choice=g.capture()
                    result=execute_candidate(adapter,batch,batch.id,chosen_id,reference_choice,rules,emit,
                                             reservation='choice')
                    controller.choice_verified(result)
                    Image.fromarray(g.capture()).save(args.output/'verified.png')
                except CandidateExpired as exc:
                    emit('atlas_choice_rejected',dict(message=str(exc)))
                break
            (args.output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        except Exception as e:
            emit('atlas_invalidated',dict(message=str(e)))
        finally:
            if batch:batch.invalidate()
            if g:g.send(4);g.send(16)
    root=ct.CTk();root.withdraw()
    def end():stop.set();root.after(300,root.destroy)
    overlay=SearchOverlay(root,end,lambda b,c:choices.put((b,c)))
    overlay.title('Color Studio live atlas trial');overlay.deiconify()
    def poll():
        if u.GetAsyncKeyState(0x78)&0x8000:stop.set()
        while not events.empty():
            kind,data=events.get()
            if kind=='trial_status':overlay.render(data['title'],data['message'])
            else:overlay.handle(kind,data)
        root.after(50,poll)
    root.after(50,poll);threading.Thread(target=worker,daemon=True).start();root.mainloop()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--ocr',type=Path,required=True)
    parser.add_argument('--wait-seconds',type=int,default=180,
                        help='Maximum time to wait for the dye screen before exiting (default: 180)')
    args=parser.parse_args()
    if args.wait_seconds < 1:parser.error('--wait-seconds must be positive')
    kernel=C.windll.kernel32
    kernel.CreateMutexW.argtypes=[C.c_void_p,C.c_bool,C.c_wchar_p];kernel.CreateMutexW.restype=C.c_void_p
    kernel.CloseHandle.argtypes=[C.c_void_p]
    mutex=kernel.CreateMutexW(None,False,'Local\\MabinogiDyeScanV2')
    if not mutex or kernel.GetLastError()==183:raise RuntimeError('Another dye input process is running')
    try:run(args)
    finally:kernel.CloseHandle(mutex)
