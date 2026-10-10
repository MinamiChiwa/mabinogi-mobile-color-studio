"""Existing ColorStudio Windows input and independent capture for research only."""
import ctypes,hashlib,json,math,re,sys,threading,time
from pathlib import Path
import numpy as np
from PIL import Image
from input_gestures import PointerGesture
from .dye_action_checkpoint import record_action_checkpoint, _binding
from vision import recognize,read_codes,_swatch_distance
from .probe_timer import read_timer


class FrameReadTimeout(TimeoutError):
    """A local decoder allowance expired after the visual layout was found."""
    def __init__(self,message,partial_frame):
        super().__init__(message)
        self.partial_frame=partial_frame


def merge_native_hex(decoded, native_hex):
    """Fill only OCR omissions from the same checkpoint's native HEX."""
    if not isinstance(decoded, dict) or not isinstance(decoded.get('hex'), list) or len(decoded['hex']) != 3:
        raise ValueError('Three screenshot HEX values required')
    if not isinstance(native_hex, (list, tuple)) or len(native_hex) != 3:
        raise ValueError('Three native checkpoint HEX values required')
    values=list(decoded['hex']);sources=[]
    for index,(observed,native) in enumerate(zip(values,native_hex)):
        if observed is None:
            if not isinstance(native,str):raise ValueError('Missing native checkpoint HEX')
            values[index]=native;sources.append('native_checkpoint')
        else:
            if observed != native:raise ValueError('Screenshot and checkpoint HEX disagree')
            sources.append('screenshot')
    return dict(decoded,hex=values,hex_source=sources,
                screenshot_hex=list(decoded['hex']),
                screenshot_hex_verified=all(v is not None for v in decoded['hex']))


def probe_layout_scale(width,height):
    """Validate physical image extent; the reference scale is not a UI mapping."""
    if any(type(v) is not int or not 1<=v<=16384 for v in (width,height)):
        raise ValueError('Invalid physical client extent')
    return min(width/1280,height/960)


def _recognize_native_layout(image,board):
    """Search actual pixels near a measured native board, then restore origin."""
    h,w=image.shape[:2]
    if (not isinstance(board,(list,tuple)) or len(board)!=4
            or any(type(v) not in (int,float) or not math.isfinite(v) for v in board)):
        raise ValueError('Invalid native board geometry')
    l,t,r,b=board;side=r-l
    if (not 0<=l<r<=w or not 0<=t<b<=h or abs(side-(b-t))>max(2,side*.02)):
        raise ValueError('Native board must be visible and square')
    # Cards are directly above the three equal board columns. Restrict the
    # detector's scale priors to this measured UI region, not the whole client;
    # a large desktop can still contain small, fully visible cards.
    left=max(0,math.floor(l-side*.06));top=max(0,math.floor(t-side*.30))
    right=min(w,math.ceil(r+side*.06));bottom=min(h,math.ceil(b+side*.03))
    scene=recognize(image[top:bottom,left:right],with_ocr=False)
    scene.cards=[(x+left,y+top,cw,ch) for x,y,cw,ch in scene.cards]
    scene.markers=[(x+left,y+top) for x,y in scene.markers]
    vl,vt,vr,vb=scene.board;scene.board=(vl+left,vt+top,vr+left,vb+top)
    centers=[c[0]+c[2]/2 for c in scene.cards]
    tolerance=4*max(1.,side/499.2)
    if max(abs(x-(l+(i+.5)*side/3)) for i,x in enumerate(centers))>tolerance:
        raise ValueError('Visual cards disagree with native board')
    if max(abs(a-v) for a,v in zip(board,scene.board))>max(6.,side*.025):
        raise ValueError('Visual board disagrees with native board')
    return scene


def read_probe_frame(image,*,deadline,check=lambda:None,clock=time.monotonic,previous_timer=None,captured_at=None,hex_fallback=None,
        timer_mode='required',card_cache=None,native_board=None):
    def guard():
        check()
        if deadline is not None and clock()>=deadline:raise TimeoutError('Frame read deadline expired')
    guard()
    if image.ndim!=3 or image.shape[2]!=3 or image.dtype!=np.uint8:raise ValueError('RGB uint8 probe frame required')
    h,w=image.shape[:2];probe_layout_scale(w,h)
    scene=recognize(image,with_ocr=False) if native_board is None else _recognize_native_layout(image,native_board)
    guard()
    fallback_reads=[];codes=[None]*len(scene.cards);cache_hits=[False]*len(scene.cards);keys=[];samples=[]
    def frame_record(**extra):
        return dict(hex=codes,hex_fallback_reads=fallback_reads,hex_cache_hits=cache_hits,
            hex_recognition_sources=['exact_card_pixels_cache' if hit else 'screenshot_text' if code is not None else 'unresolved'
                for hit,code in zip(cache_hits,codes)],
            timer_layout_assumption='measured_anchor_with_top_left_HUD_prior',
            cards=scene.cards,markers=scene.markers,visual_board=scene.board,**extra)
    def read_unresolved(text_fallback=None):
        # Commit each independent card result before another card can use up
        # the local OCR allowance; keep the full scene and swatch validation.
        for index,code in enumerate(codes):
            if code is not None:continue
            enabled=[i==index for i in range(len(codes))]
            kwargs={} if text_fallback is None else dict(text_fallback=text_fallback)
            one=read_codes(image,scene.cards,scene.markers,enabled=enabled,
                deadline=deadline,clock=clock,check=check,**kwargs)
            if one[index] is not None:codes[index]=one[index]
    try:
        for index,card in enumerate(scene.cards):
            guard();x,y,cw,ch=card;cx=x+round(cw*.50);cy=y+round(ch*.43);rad=max(2,round(cw*.04))
            sample=np.median(image[cy-rad:cy+rad+1,cx-rad:cx+rad+1].reshape(-1,3),axis=0);samples.append(sample)
            key=None
            if card_cache is not None:
                pixels=image[y:y+ch,x:x+cw]
                key=(pixels.shape,hashlib.sha256(pixels.tobytes()).hexdigest())
                value=card_cache.get(key)
                if isinstance(value,str) and re.fullmatch('#[0-9A-F]{6}',value) and _swatch_distance(value,sample)<3:
                    codes[index]=value;cache_hits[index]=True
            keys.append(key);guard()
        if hex_fallback is None:
            if card_cache is None:
                if scene.cards:read_unresolved()
                else:codes=read_codes(image,scene.cards,scene.markers,deadline=deadline,clock=clock,check=check)
            elif any(code is None for code in codes):
                read_unresolved()
        else:
            glyph_results={}
            for index,card in enumerate(scene.cards):
                guard()
                if cache_hits[index]:continue
                result=hex_fallback(image,card,deadline=deadline,clock=clock,check=check)
                guard()
                glyph_results[tuple(card)]=result
                sample=samples[index]
                value=result.get('hex')
                distance=_swatch_distance(value,sample) if isinstance(value,str) and re.fullmatch('#[0-9A-F]{6}',value) else None
                accepted=result.get('glyphs_unambiguous') is True and distance is not None and distance<3
                fallback_reads.append(dict(card_index=index,**result,swatch_distance=distance,swatch_accepted=accepted))
                if accepted:codes[index]=value
            if any(code is None for code in codes):
                # Only unresolved screenshot text needs expensive OCR.
                def cached_glyphs(image,card,**unused):return glyph_results[tuple(card)]
                read_unresolved(cached_glyphs)
        guard()
        if card_cache is not None:
            for key,code,sample in zip(keys,codes,samples):
                guard()
                if isinstance(code,str) and re.fullmatch('#[0-9A-F]{6}',code) and _swatch_distance(code,sample)<3:
                    # Native-filled omissions never reach this screenshot cache.
                    card_cache.pop(key,None);card_cache[key]=code
                    while len(card_cache)>96:card_cache.pop(next(iter(card_cache)))
    except TimeoutError as exc:
        # The caller's check owns the real session/input deadline and F9. Only
        # a decoder-local timeout can preserve already read screenshot text.
        check()
        raise FrameReadTimeout(str(exc),frame_record(remaining_seconds=None,
            timer_confidence='unknown',hex_error=str(exc),local_frame_timeout=True)) from exc
    if timer_mode not in ('required','advisory','skip'):raise ValueError('Invalid timer mode')
    timer=dict(remaining_seconds=None,timer_confidence='startup_skipped' if timer_mode=='skip' else 'unknown')
    if timer_mode!='skip':
        timer_deadline=deadline if timer_mode=='required' else clock()+.75
        if timer_mode=='advisory' and deadline is not None:timer_deadline=min(deadline,timer_deadline)
        try:
            if timer_mode=='advisory' and clock()>=timer_deadline:
                raise TimeoutError('Timer advisory allowance exhausted')
            timer=read_timer(image,deadline=timer_deadline,
                clock=clock,check=check,previous=previous_timer,captured_at=captured_at)
        except (TimeoutError,ValueError) as exc:
            if timer_mode=='required':raise
            # A late advisory timer cannot discard the completed HEX read.
            # The external check still enforces the actual session deadline.
            check();timer['timer_error']=str(exc)
    if timer_mode=='advisory':check()
    else:guard()
    return frame_record(**timer)


class ProjectProbeIO:
    def __init__(self,backend,baseline,folder,*,game=None,stop=None,f9_pressed=None):
        self.backend=backend;self.reference=baseline;self.folder=Path(folder);self.folder.mkdir(parents=True,exist_ok=True)
        self.stop=stop or threading.Event();self.sent_any=False;self.deadline=baseline['session_deadline_monotonic'];self.previous_timer=None
        if game is None:
            from platform_win import Game
            from window_target import WindowTarget
            window=baseline['baseline']['window_context']['window']
            game=Game(self.stop,target=WindowTarget(window['hwnd'],window['pid'],'Bound game','MabinogiMobile.exe'))
        self.game=game;self.original_game_check=game.check;self.game.capture_input_trace=True
        self.last_client_hex=None;self.card_cache={}
        self._performing_input=False
        if f9_pressed is None:
            u=ctypes.WinDLL('user32');u.GetAsyncKeyState.argtypes=[ctypes.c_int];u.GetAsyncKeyState.restype=ctypes.c_short
            f9_pressed=lambda:bool(u.GetAsyncKeyState(0x78)&0x8000)
        self.f9_pressed=f9_pressed
        self.game.check=lambda:self._input_guard()
        self.original_binding=_binding(baseline['baseline']);self.last_observation=baseline['baseline']

    def _input_guard(self):
        focus_end=min(self.deadline,time.monotonic()+5.)
        while True:
            if self.stop.is_set() or self.f9_pressed():self.stop.set();raise InterruptedError('F9/stop requested')
            if time.monotonic()>=self.deadline:raise TimeoutError('Probe deadline expired')
            try:
                self.original_game_check();return
            except Exception as exc:
                focus_lost='游戏失去焦点' in str(exc)
                if not focus_lost or self._performing_input or time.monotonic()>=focus_end:
                    raise InterruptedError(str(exc)) from exc
                time.sleep(min(.1,max(0.,focus_end-time.monotonic())))

    def check(self,deadline):
        self.deadline=min(deadline,self.reference['session_deadline_monotonic']);self._input_guard()
        if list(self.backend.process_identity())!=list(self.reference['baseline']['process_identity']):raise ValueError('Process identity changed')
        state=self.backend.probe(self.reference['instance_address'],self.deadline,self._input_guard)
        if state.get('active') is not True or json.dumps(state['session_token'])!=json.dumps(self.reference['baseline']['session_token']):
            raise ValueError('Active palette session changed')

    def checkpoint(self,label,deadline):
        self.check(deadline)
        record=record_action_checkpoint(self.backend,self.reference,label,timeout_seconds=min(5,max(.01,deadline-time.monotonic())),
            check=self._input_guard)
        path=self.folder/(label+'.checkpoint.json');path.write_text(json.dumps(record,indent=2),encoding='utf-8')
        if record.get('checkpoint_valid') is not True:raise ValueError('Checkpoint failed: '+record['stop_reason'])
        self._input_guard()
        observation=record['observation'];self.last_observation=observation
        cache=observation['geometry_diagnostic']['rect']['cache'];comparison=record['capture']['cpu_comparison']
        self.last_client_hex=list(comparison['client_float_hex'])
        checkpoint=dict(checkpoint_valid=True,label=label,checkpoint_file=str(path),pose=observation['motion']['pose'],
            client_hex=comparison['client_float_hex'],cpu_matches=comparison['client_float_hex_equal'] and comparison['float_within_tolerance'],
            binding=_binding(observation),board=observation['window_mapping_candidate']['client_board_candidate'],local_size=cache['cached_local_rect'][2:])
        mapping=observation['window_mapping_candidate'].get('pixel_mapping')
        if mapping is not None:checkpoint['pixel_mapping']=mapping
        return checkpoint

    def frames(self,label,deadline):
        frames=[]
        for index in range(2):
            self.check(deadline);image=self.game.capture();captured=time.monotonic()
            expected=self.last_observation['window_context']['window']['client_size_physical']
            if [image.shape[1],image.shape[0]]!=list(expected):raise ValueError('Captured physical client extent mismatch')
            path=self.folder/(label+'_frame'+str(index)+'.png');Image.fromarray(image).save(path)
            board=self.last_observation['window_mapping_candidate']['client_board_candidate']
            try:
                decoded=read_probe_frame(image,deadline=min(deadline,time.monotonic()+5),check=self._input_guard,
                    previous_timer=self.previous_timer,captured_at=captured,hex_fallback=getattr(self,'hex_fallback',None),
                    timer_mode='skip' if captured<getattr(self,'timer_grace_until',0.) else 'advisory',card_cache=self.card_cache,
                    native_board=board)
            except FrameReadTimeout as exc:
                self._input_guard()
                decoded=exc.partial_frame
                if self.last_client_hex is None and any(code is None for code in decoded['hex']):raise
            if self.last_client_hex is not None:
                decoded=merge_native_hex(decoded,self.last_client_hex)
            if decoded['remaining_seconds'] is not None:self.previous_timer=(decoded['remaining_seconds'],captured)
            # Visually observed card centers should follow the native three
            # equal columns; this detects a gross wrong screen/viewport.
            l,t,r,b=board
            centers=[c[0]+c[2]/2 for c in decoded['cards']]
            if max(abs(x-(l+(i+.5)*(r-l)/3)) for i,x in enumerate(centers))>4*max(1.,(r-l)/499.2):
                raise ValueError('Visual cards disagree with native board')
            frame=dict(decoded,captured_monotonic=captured,file=str(path))
            path.with_suffix('.json').write_text(json.dumps(frame,indent=2),encoding='utf-8')
            frames.append(frame)
            self._input_guard()
        return frames

    def perform(self,action,deadline):
        self.check(deadline)
        fresh=self.backend.observe_motion(self.reference['instance_address'],deadline,self._input_guard,
            include_geometry=True,include_window=True)
        if (fresh.get('active') is not True or _binding(fresh)!=_binding(self.last_observation)
                or fresh['motion']['pose']!=self.last_observation['motion']['pose']
                or fresh['geometry_diagnostic']!=self.last_observation['geometry_diagnostic']
                or fresh['window_mapping_candidate']!=self.last_observation['window_mapping_candidate']
                or fresh['motion']['animators_done'] is not True):
            raise ValueError('Pre-input motion/geometry binding changed')
        points=action['points'];kind=action['kind']
        if kind not in ('drag','wheel') or not points or len(points)>8:raise ValueError('Unsupported probe gesture')
        l,t,r,b=self.last_observation['window_mapping_candidate']['client_board_candidate']
        if any(len(p)!=2 or any(type(v) is not int for v in p) or not l+12<p[0]<r-12 or not t+12<p[1]<b-12 for p in points):
            raise ValueError('Probe point outside safe board')
        if kind=='drag' and (len(points)>6 or points[-1][0]-points[0][0] not in (3,4,5) or any(p[1]!=points[0][1] for p in points)):
            raise ValueError('Only 3/4/5px horizontal probe drags')
        if kind=='wheel' and (len(points)!=1 or action.get('steps') not in (-1,1)):
            raise ValueError('Only single-step wheel probe')
        gesture=PointerGesture(kind,tuple(tuple(p) for p in points),absolute=True,
            wheel_steps=action.get('steps',0))
        started=time.monotonic();self.sent_any=True
        receipt=dict(input_source='project_windows_sendinput',gesture=gesture.record(),started_monotonic=started,completed=False)
        try:
            receipt['completed']=bool(self.game.perform_gesture(gesture))
            return receipt
        finally:
            receipt.update(finished_monotonic=time.monotonic(),actual_trace=self.game.last_input_trace)
            (self.folder/(action['label']+'.input.json')).write_text(json.dumps(receipt,indent=2),encoding='utf-8')

    def release(self):
        if self.sent_any:
            self.game.send(4);self.game.send(16)
