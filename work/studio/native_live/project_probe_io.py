"""Existing ColorStudio Windows input and independent capture for research only."""
import ctypes,hashlib,json,math,re,sys,threading,time
from pathlib import Path
import numpy as np
from PIL import Image
from input_gestures import PointerGesture
from .dye_action_checkpoint import record_action_checkpoint, _binding
from vision import recognize,read_codes,_swatch_distance
from .probe_timer import read_timer
from dye_regions import region_count as validate_region_count
from .session_status import (PaletteEnded,SessionBindingChanged,SessionProbeUnstable,
    session_diagnostic,changed_token_fields)


class FrameReadTimeout(TimeoutError):
    """A local decoder allowance expired after the visual layout was found."""
    def __init__(self,message,partial_frame):
        super().__init__(message)
        self.partial_frame=partial_frame


def merge_native_hex(decoded, native_hex):
    """Fill only OCR omissions from the same checkpoint's native HEX."""
    if not isinstance(decoded, dict) or not isinstance(decoded.get('hex'), list) or len(decoded['hex']) not in (2,3):
        raise ValueError('Two or three screenshot HEX values required')
    if not isinstance(native_hex, (list, tuple)) or len(native_hex) != len(decoded['hex']):
        raise ValueError('Screenshot and native checkpoint region counts disagree')
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


def reread_conflicting_hex(image,decoded,native_hex,*,deadline,check=lambda:None,card_cache=None):
    """Resolve only conflicting cards with independently agreeing visible text.

    Expected HEX identifies a conflict but never enters the screenshot reader.
    A missing or still-conflicting read cannot supply a successful color proof.
    """
    from screenshot_text import read_visible
    decoded['hex']=list(decoded['hex'])
    diagnostics=decoded.setdefault('hex_conflict_reads',[])
    for index,(observed,expected) in enumerate(zip(decoded['hex'],native_hex)):
        if observed is None or observed==expected:continue
        check();card=decoded['cards'][index];x,y,w,h=card
        pixels=image[y:y+h,x:x+w];key=(pixels.shape,hashlib.sha256(pixels.tobytes()).hexdigest())
        if card_cache is not None:card_cache.pop(key,None)
        audit=dict(card_index=index,original_hex=observed,expected_hex=expected,
            method='independent_multithreshold_text',screenshot_hex_verified=False)
        diagnostics.append(audit)
        try:values,reads=read_visible(image,[card],deadline=deadline,check=check)
        except Exception as exc:
            audit['read_error']=type(exc).__name__+': '+str(exc)
            raise
        check();audit['text_reads']=reads
        value=values[0]
        cx=x+round(w*.50);cy=y+round(h*.43);rad=max(2,round(w*.04))
        sample=np.median(image[cy-rad:cy+rad+1,cx-rad:cx+rad+1].reshape(-1,3),axis=0)
        distance=_swatch_distance(value,sample) if isinstance(value,str) and re.fullmatch('#[0-9A-F]{6}',value) else None
        audit.update(reread_hex=value,swatch_distance=distance,swatch_accepted=distance is not None and distance<=3)
        if audit['swatch_accepted']:
            decoded['hex'][index]=value
            if 'hex_recognition_sources' in decoded:decoded['hex_recognition_sources'][index]='independent_multithreshold_text'
            if 'hex_cache_hits' in decoded:decoded['hex_cache_hits'][index]=False
            audit['screenshot_hex_verified']=value==expected
            if value==expected and card_cache is not None:
                card_cache[key]=value
                while len(card_cache)>96:card_cache.pop(next(iter(card_cache)))
    return decoded


def probe_layout_scale(width,height):
    """Validate physical image extent; the reference scale is not a UI mapping."""
    if any(type(v) is not int or not 1<=v<=16384 for v in (width,height)):
        raise ValueError('Invalid physical client extent')
    return min(width/1280,height/960)


def _recognize_native_layout(image,board,region_count=3):
    """Search actual pixels near a measured native board, then restore origin."""
    region_count=validate_region_count(region_count)
    h,w=image.shape[:2]
    if (not isinstance(board,(list,tuple)) or len(board)!=4
            or any(type(v) not in (int,float) or not math.isfinite(v) for v in board)):
        raise ValueError('Invalid native board geometry')
    l,t,r,b=board;side=r-l
    if (not 0<=l<r<=w or not 0<=t<b<=h or abs(side-(b-t))>max(2,side*.02)):
        raise ValueError('Native board must be visible and square')
    # Cards are directly above the actual equal board columns. Restrict the
    # detector's scale priors to this measured UI region, not the whole client;
    # a large desktop can still contain small, fully visible cards.
    left=max(0,math.floor(l-side*.06));top=max(0,math.floor(t-side*.30))
    right=min(w,math.ceil(r+side*.06));bottom=min(h,math.ceil(b+side*.03))
    scene=recognize(image[top:bottom,left:right],with_ocr=False,region_count=region_count)
    scene.cards=[(x+left,y+top,cw,ch) for x,y,cw,ch in scene.cards]
    scene.markers=[(x+left,y+top) for x,y in scene.markers]
    vl,vt,vr,vb=scene.board;scene.board=(vl+left,vt+top,vr+left,vb+top)
    centers=[c[0]+c[2]/2 for c in scene.cards]
    tolerance=4*max(1.,side/499.2)
    if len(centers)!=region_count or max(abs(x-(l+(i+.5)*side/region_count)) for i,x in enumerate(centers))>tolerance:
        raise ValueError('Visual cards disagree with native board')
    if max(abs(a-v) for a,v in zip(board,scene.board))>max(6.,side*.025):
        raise ValueError('Visual board disagrees with native board')
    return scene


def read_probe_frame(image,*,deadline,check=lambda:None,clock=time.monotonic,previous_timer=None,captured_at=None,hex_fallback=None,
        timer_mode='required',card_cache=None,native_board=None,region_count=3,read_colors=True):
    def guard():
        check()
        if deadline is not None and clock()>=deadline:raise TimeoutError('Frame read deadline expired')
    guard()
    if image.ndim!=3 or image.shape[2]!=3 or image.dtype!=np.uint8:raise ValueError('RGB uint8 probe frame required')
    h,w=image.shape[:2];probe_layout_scale(w,h)
    region_count=validate_region_count(region_count)
    scene=recognize(image,with_ocr=False,region_count=region_count) if native_board is None else _recognize_native_layout(image,native_board,region_count)
    guard()
    fallback_reads=[];codes=[None]*len(scene.cards);cache_hits=[False]*len(scene.cards);keys=[];samples=[]
    def frame_record(**extra):
        return dict(hex=codes,region_count=region_count,hex_fallback_reads=fallback_reads,hex_cache_hits=cache_hits,
            hex_recognition_sources=['exact_card_pixels_cache' if hit else 'screenshot_text' if code is not None else 'unresolved'
                for hit,code in zip(cache_hits,codes)],
            timer_layout_assumption='measured_anchor_with_top_left_HUD_prior',
            cards=scene.cards,markers=scene.markers,visual_board=scene.board,**extra)
    if not read_colors:
        # Planning needs a visible, correctly bound board and picker layout.
        # Do not spend final-result OCR time decoding unrelated initial colors.
        # Empty screenshot HEX remains explicitly unverified when native data
        # is merged by the caller; it never enters the screenshot-card cache.
        guard()
        return frame_record(remaining_seconds=None,timer_confidence='not_read_for_planning',
            observation_scope='planning_layout')
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
                if isinstance(value,str) and re.fullmatch('#[0-9A-F]{6}',value) and _swatch_distance(value,sample)<=3:
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
                # A complete agreeing two-threshold text read can survive the
                # exact RGB-distance boundary (e.g. 125% rendering 250,244,244
                # for the independently decoded #F9F6F6). Ordinary OCR retains
                # its strict gate in read_codes; no swatch generates HEX text.
                accepted=result.get('glyphs_unambiguous') is True and distance is not None and distance<=3
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
                if isinstance(code,str) and re.fullmatch('#[0-9A-F]{6}',code) and _swatch_distance(code,sample)<=3:
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
        timer_deadline=deadline if timer_mode=='required' else clock()+1.
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


def _observation_region_count(observation):
    token=observation.get('session_token')
    fingerprints=token[5] if isinstance(token,(list,tuple)) and len(token)>=6 else None
    count=observation.get('region_count')
    if count is None:count=len(fingerprints) if isinstance(fingerprints,(list,tuple)) else 3
    count=validate_region_count(count)
    if isinstance(fingerprints,(list,tuple)) and len(fingerprints)!=count:
        raise ValueError('Bound palette region counts disagree')
    return count


class ProjectProbeIO:
    def __init__(self,backend,baseline,folder,*,game=None,stop=None,f9_pressed=None):
        self.backend=backend;self.reference=baseline;self.folder=Path(folder);self.folder.mkdir(parents=True,exist_ok=True)
        self.stop=stop or threading.Event();self.sent_any=False;self.deadline=baseline['session_deadline_monotonic'];self.previous_timer=None
        self.accepted_session_deadline=baseline['session_deadline_monotonic']
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
        self.last_session_diagnostic=None;self.session_status_label='session_check'
        if 'timer_grace_until' in baseline or 'session_first_seen_monotonic' in baseline:
            from .session_deadline import verified_timer_grace_until
            self.timer_grace_until=verified_timer_grace_until(baseline,
                session_token=baseline['baseline']['session_token'],process_identity=baseline['baseline']['process_identity'],
                now=time.monotonic())

    def _session_stop(self,error_type,observed,stage,*,expected=None,changed_fields=None,error=None):
        expected=self.reference['baseline'] if expected is None else expected
        diagnostic=session_diagnostic(expected,observed,error_type=error_type,stage=stage,
            observed_monotonic=time.monotonic(),changed_fields=changed_fields,error=error)
        diagnostic['inputs_sent']=getattr(self,'input_attempts',int(self.sent_any))
        self.last_session_diagnostic=diagnostic
        label=getattr(self,'session_status_label','session_check')
        if not isinstance(label,str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,63}',label):label='session_check'
        path=self.folder/(label+'.session-status.json');diagnostic['diagnostic_file']=str(path)
        try:path.write_text(json.dumps(diagnostic,indent=2,allow_nan=False),encoding='utf-8')
        except (OSError,ValueError,TypeError) as exc:diagnostic['diagnostic_write_error']=type(exc).__name__+': '+str(exc)
        message=('Bound palette is no longer active' if error_type is PaletteEnded else
            'Bound palette session identity changed' if error_type is SessionBindingChanged else
            'Bound palette observation stayed inconsistent')
        raise error_type(message,diagnostic)

    def _check_observed_session(self,observed,stage,*,expected=None,full_binding=False):
        expected=self.reference['baseline'] if expected is None else expected
        self._input_guard()
        identity=self.backend.process_identity()
        if json.dumps(identity)!=json.dumps(expected['process_identity']):
            self._session_stop(SessionBindingChanged,dict(observed,process_identity=identity),stage,
                expected=expected,changed_fields=['process_identity'])
        identity=observed.get('process_identity',identity)
        observed=dict(observed,process_identity=identity)
        if json.dumps(identity)!=json.dumps(expected['process_identity']):
            self._session_stop(SessionBindingChanged,observed,stage,expected=expected,changed_fields=['process_identity'])
        if observed.get('active') is False:
            self._session_stop(PaletteEnded,observed,stage,expected=expected)
        if observed.get('active') is not True:
            self._session_stop(SessionProbeUnstable,observed,stage,expected=expected,changed_fields=['active'])
        if json.dumps(observed.get('session_token'))!=json.dumps(expected['session_token']):
            self._session_stop(SessionBindingChanged,observed,stage,expected=expected,
                changed_fields=changed_token_fields(expected['session_token'],observed.get('session_token')))
        if full_binding and _binding(observed)!=_binding(expected):
            first,last=json.loads(_binding(expected)),json.loads(_binding(observed))
            fields=[name for index,name in ((2,'motion_binding'),(3,'input_settings'),(4,'window_context')) if first[index]!=last[index]]
            self._session_stop(SessionBindingChanged,observed,stage,expected=expected,changed_fields=fields)

    def _input_guard(self):
        focus_end=min(self.deadline,time.monotonic()+5.)
        while True:
            if self.stop.is_set() or self.f9_pressed():self.stop.set();raise InterruptedError('F9/stop requested')
            if time.monotonic()>=self.deadline:raise TimeoutError('Probe deadline expired')
            retry_check=getattr(self,'retry_check',None)
            if retry_check is not None:retry_check()
            try:
                self.original_game_check();return
            except Exception as exc:
                focus_lost='游戏失去焦点' in str(exc)
                if not focus_lost or self._performing_input or time.monotonic()>=focus_end:
                    raise InterruptedError(str(exc)) from exc
                time.sleep(min(.1,max(0.,focus_end-time.monotonic())))

    def check(self,deadline):
        self.deadline=min(deadline,getattr(self,'accepted_session_deadline',self.reference['session_deadline_monotonic']));self._input_guard()
        identity=self.backend.process_identity()
        if list(identity)!=list(self.reference['baseline']['process_identity']):
            self._session_stop(SessionBindingChanged,dict(process_identity=identity),
                'before_probe',changed_fields=['process_identity'])
        for attempt in range(3):
            try:
                state=self.backend.probe(self.reference['instance_address'],self.deadline,self._input_guard)
                break
            except (InterruptedError,TimeoutError):raise
            except (ValueError,OSError) as exc:
                self._input_guard()
                identity=self.backend.process_identity()
                if list(identity)!=list(self.reference['baseline']['process_identity']):
                    self._session_stop(SessionBindingChanged,dict(process_identity=identity),
                        'during_probe',changed_fields=['process_identity'],error=exc)
                if not isinstance(exc,ValueError) or str(exc)!='Palette changed during probe':raise
                if attempt==2:
                    self._session_stop(SessionProbeUnstable,dict(process_identity=identity),
                        'probe',changed_fields=[],error=exc)
                time.sleep(min(.05,max(0.,self.deadline-time.monotonic())))
        self._check_observed_session(state,'probe')
        # Independent cheap closing evidence; do not replace the checkpoint's
        # full observation or authorize input from this session-only probe.
        self.last_checked_state=state
        self.last_checked_process_identity=list(identity)
        self.last_checked_monotonic=time.monotonic()

    def set_verified_session_deadline(self,deadline,evidence):
        """Accept only the collector-bound timer pair, preserving its fixed cap."""
        from .session_deadline import verified_timer_extension
        if not isinstance(evidence,dict) or evidence.get('timer_grace_until')!=getattr(self,'timer_grace_until',None):
            raise ValueError('Unbound timer extension evidence')
        if evidence.get('checkpoint',{}).get('binding')!=_binding(self.last_observation):
            raise ValueError('Timer extension checkpoint binding changed')
        self.check(getattr(self,'accepted_session_deadline',self.reference['session_deadline_monotonic']))
        approved=verified_timer_extension(evidence.get('checkpoint'),evidence.get('frames'),
            initial_engineering_deadline=self.reference['session_deadline_monotonic'],
            current_deadline=getattr(self,'accepted_session_deadline',self.reference['session_deadline_monotonic']),
            extension=self.reference.get('timer_deadline_extension'),timer_grace_until=self.timer_grace_until,
            now=time.monotonic())
        if approved is None or approved['deadline']!=deadline:raise ValueError('Unapproved timer extension')
        self.accepted_session_deadline=deadline

    def checkpoint(self,label,deadline):
        self.session_status_label=label
        self.check(deadline)
        reference=dict(self.reference,session_deadline_monotonic=self.deadline)
        record=record_action_checkpoint(self.backend,reference,label,timeout_seconds=min(5,max(.01,deadline-time.monotonic())),
            check=self._input_guard)
        path=self.folder/(label+'.checkpoint.json')
        try:path.write_text(json.dumps(record,indent=2),encoding='utf-8')
        except OSError as exc:
            if record.get('checkpoint_valid') is True:raise
            record['diagnostic_write_error']=type(exc).__name__+': '+str(exc)
        if record.get('checkpoint_valid') is not True:
            failed=record.get('failed_observation')
            if isinstance(failed,dict):self._check_observed_session(failed,'checkpoint',full_binding=True)
            raise ValueError('Checkpoint failed: '+record['stop_reason'])
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

    def frames(self,label,deadline,*,read_colors=True):
        self.session_status_label=label
        frames=[]
        for index in range(2):
            self.check(deadline);image=self.game.capture();captured=time.monotonic()
            expected=self.last_observation['window_context']['window']['client_size_physical']
            if [image.shape[1],image.shape[0]]!=list(expected):raise ValueError('Captured physical client extent mismatch')
            path=self.folder/(label+'_frame'+str(index)+'.png');Image.fromarray(image).save(path)
            board=self.last_observation['window_mapping_candidate']['client_board_candidate']
            region_count=_observation_region_count(self.last_observation)
            try:
                decoded=read_probe_frame(image,deadline=min(deadline,time.monotonic()+5),check=self._input_guard,
                    previous_timer=self.previous_timer,captured_at=captured,hex_fallback=getattr(self,'hex_fallback',None),
                    timer_mode='advisory',card_cache=self.card_cache,
                    native_board=board,region_count=region_count,read_colors=read_colors)
            except FrameReadTimeout as exc:
                self._input_guard()
                decoded=exc.partial_frame
                if self.last_client_hex is None and any(code is None for code in decoded['hex']):raise
            if self.last_client_hex is not None:
                if any(code is not None and code!=native for code,native in zip(decoded['hex'],self.last_client_hex)):
                    # Repeating a capture with the same single-pass OCR can
                    # repeat A/8 or B/8 indefinitely. Use another pixel/text
                    # path only for the conflict, and save evidence even when
                    # it remains unresolved or the read is interrupted.
                    try:
                        decoded=reread_conflicting_hex(image,decoded,self.last_client_hex,
                            deadline=min(deadline,time.monotonic()+5.),check=self._input_guard,card_cache=self.card_cache)
                    finally:
                        try:
                            path.with_suffix('.decoded.json').write_text(json.dumps(dict(decoded,
                                captured_monotonic=captured,file=str(path),checkpoint_hex=self.last_client_hex,
                                screenshot_hex_verified=False),indent=2),encoding='utf-8')
                        except OSError as exc:
                            # Optional conflict diagnostics must not replace
                            # F9 or the real session-deadline exception.
                            decoded['diagnostic_write_error']=type(exc).__name__+': '+str(exc)
                decoded=merge_native_hex(decoded,self.last_client_hex)
            if decoded['remaining_seconds'] is not None:self.previous_timer=(decoded['remaining_seconds'],captured)
            # Visually observed card centers should follow the actual native
            # equal columns; this detects a gross wrong screen/viewport.
            l,t,r,b=board
            centers=[c[0]+c[2]/2 for c in decoded['cards']]
            if len(centers)!=region_count or max(abs(x-(l+(i+.5)*(r-l)/region_count)) for i,x in enumerate(centers))>4*max(1.,(r-l)/499.2):
                raise ValueError('Visual cards disagree with native board')
            frame=dict(decoded,captured_monotonic=captured,file=str(path))
            path.with_suffix('.json').write_text(json.dumps(frame,indent=2),encoding='utf-8')
            frames.append(frame)
            self._input_guard()
        return frames

    def perform(self,action,deadline):
        self.session_status_label=action.get('label','probe_input')
        self.check(deadline)
        fresh=self.backend.observe_motion(self.reference['instance_address'],deadline,self._input_guard,
            include_geometry=True,include_window=True)
        self._check_observed_session(fresh,'pre_input',expected=self.last_observation,full_binding=True)
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
            errors=[]
            for flag in (4,16):
                try:self.game.send(flag)
                except Exception as exc:errors.append(str(exc))
            if errors:raise RuntimeError('; '.join(errors))
