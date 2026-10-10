"""Visual recognition only. Coordinates are physical client-image pixels."""
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import itertools, re, sys, os, shutil, subprocess, io, shlex, time
import unicodedata
from collections import Counter
import cv2
import numpy as np
import pytesseract
from PIL import Image
from marker_geometry import refine_marker_center

OCR_AVAILABLE = None
OCR_CONFIG = ''

def configure_ocr(strict=False):
    """Check the OCR executable and English data before a timed capture."""
    global OCR_AVAILABLE, OCR_CONFIG
    OCR_CONFIG = ''
    root=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))
    candidates=[root/'ocr/tesseract.exe',
                root/'bundle/ocr/tesseract.exe',
                Path(__file__).resolve().parents[2]/'outputs/dependencies/ocr/tesseract.exe']
    if os.environ.get('TESSERACT_HOME'):
        candidates.append(Path(os.environ['TESSERACT_HOME'])/'tesseract.exe')
    candidates.append(Path('C:/Program Files/Tesseract-OCR/tesseract.exe'))
    found=shutil.which('tesseract')
    if found:candidates.append(Path(found))
    found_candidate=False
    checked=set()
    for exe in candidates:
        try:
            resolved=exe.resolve()
            if resolved in checked or not exe.is_file():continue
        except OSError:
            continue
        checked.add(resolved);found_candidate=True
        try:
            data_dir=exe.parent/'tessdata'
            data_args=['--tessdata-dir',str(data_dir)] if (data_dir/'eng.traineddata').is_file() else []
            # --list-langs includes the installation path in its header, whose
            # encoding can follow the Windows locale. Only the ASCII language
            # identifiers matter; decoding that header as UTF-8 can reject a
            # working installation. Avoid pytesseract's process-global cache
            # too: a failed executable must not poison the next candidate.
            probe=subprocess.run([str(exe),'--list-langs',*data_args],
                capture_output=True,timeout=5,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if probe.returncode!=0 or b'eng' not in [line.strip() for line in probe.stdout.splitlines()]:continue
        except (OSError,subprocess.TimeoutExpired):
            continue
        pytesseract.pytesseract.tesseract_cmd=str(exe)
        OCR_CONFIG=f'--tessdata-dir "{data_dir}"' if data_args else ''
        OCR_AVAILABLE = True
        return True
    OCR_AVAILABLE = False
    if strict:
        message=('文字识别组件不可用，请修复 Tesseract 后再开始染色采样。'
                 if found_candidate else '文字识别组件缺失，请使用完整安装包。')
        raise RuntimeError(message)
    return False

def _check_ocr_deadline(deadline, clock, check):
    check()
    if deadline is None:return None
    if not np.isfinite(deadline):raise ValueError('OCR deadline must be finite')
    remaining=float(deadline)-clock()
    if remaining<=0:raise TimeoutError('OCR observation deadline expired')
    return remaining


def _ocr_text(image, *, lang='eng', config='', timeout=2,
              deadline=None, clock=time.monotonic, check=lambda:None):
    """Use binary pipes so OCR never depends on temporary-file path encoding."""
    if not isinstance(image, Image.Image):image=Image.fromarray(image)
    buffer=io.BytesIO()
    image.save(buffer,format='PNG')
    # Parse our internal options once, removing grouping quotes before Windows
    # serializes the argument list. Retained quotes become part of tessdata's
    # filename when passed through pytesseract's Windows config parser.
    args=[pytesseract.pytesseract.tesseract_cmd,'stdin','stdout','-l',lang]
    args.extend(shlex.split(config,posix=True))
    # Encoding and preprocessing use the same absolute allowance as the OCR
    # process. Recheck immediately before launching, not only at card entry.
    remaining=_check_ocr_deadline(deadline,clock,check)
    process_timeout=timeout if remaining is None else min(timeout,remaining)
    try:
        result=subprocess.run(args,input=buffer.getvalue(),capture_output=True,
            timeout=process_timeout,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    finally:
        _check_ocr_deadline(deadline,clock,check)
    if result.returncode:
        raise pytesseract.TesseractError(result.returncode,result.stderr.decode('utf-8',errors='replace'))
    return result.stdout.decode('utf-8',errors='replace')


def _tesseract(image, config, timeout=2, *,
               deadline=None, clock=time.monotonic, check=lambda:None):
    """Return OCR text, degrading to an empty result when Tesseract is absent."""
    global OCR_AVAILABLE
    if OCR_AVAILABLE is False:
        return ''
    try:
        budget={} if deadline is None else dict(deadline=deadline,clock=clock,check=check)
        text = _ocr_text(image, lang='eng', config=' '.join(filter(None,(OCR_CONFIG,config))), timeout=timeout,**budget).strip()
        OCR_AVAILABLE = True
        return text
    except TimeoutError:
        # Observation expiry is a stage outcome, not a missing OCR runtime.
        raise
    except (pytesseract.TesseractNotFoundError, OSError):
        OCR_AVAILABLE = False
        return ''
    except (pytesseract.TesseractError, UnicodeDecodeError, subprocess.TimeoutExpired):
        # An unreadable frame or localized subprocess diagnostic must not
        # disable every subsequent OCR attempt in this session.
        return ''
    except RuntimeError as exc:
        if 'timeout' not in str(exc).lower():raise
        return ''

def normalize_hex(value):
    s=value.strip().upper().lstrip('#')
    if not re.fullmatch('[0-9A-F]{6}',s): raise ValueError('颜色请输入六位 HEX，例如 #202020')
    return '#'+s

def rgb(value):
    s=normalize_hex(value)[1:]; return tuple(int(s[i:i+2],16) for i in (0,2,4))

def lab(rgb_values):
    arr=np.asarray(rgb_values,np.float32)/255
    return cv2.cvtColor(arr.reshape(1,-1,3),cv2.COLOR_RGB2LAB).reshape(-1,3)

def error(color,targets,exact):
    if exact: return min(max(abs(a-b) for a,b in zip(rgb(color),rgb(t))) for t in targets)
    return float(np.min(np.linalg.norm(lab([rgb(color)])-lab([rgb(t) for t in targets]),axis=1)))

def accepted(colors,rules):
    if len(colors)!=3 or len(rules)!=3 or not any(rule['enabled'] for rule in rules):return False
    return all(not rule['enabled'] or (color is not None and error(color,rule['colors'],rule['exact']) <= (0 if rule['exact'] else rule['tolerance'])) for color,rule in zip(colors,rules))

def ocr(im,whitelist,psm=7, *, deadline=None,clock=time.monotonic,check=lambda:None):
    if im.size==0:return ''
    h,w=im.shape[:2]; scale=max(2,40/max(h,1))
    im=cv2.resize(im,None,fx=scale,fy=scale,interpolation=cv2.INTER_CUBIC)
    budget={} if deadline is None else dict(deadline=deadline,clock=clock,check=check)
    return _tesseract(Image.fromarray(im), config=f'--psm {psm} -c tessedit_char_whitelist={whitelist}',**budget)

@dataclass
class Scene:
    cards:list
    markers:list
    board:tuple
    colors:list
    seconds:int|None
    button:tuple|None

def color_cards(image):
    h,w=image.shape[:2]
    mask=cv2.inRange(image,np.array([218]*3,np.uint8),np.array([255]*3,np.uint8))
    k=max(5,round(min(w,h)*.007)); k+=1-k%2
    mask=cv2.morphologyEx(mask,cv2.MORPH_OPEN,np.ones((k,k),np.uint8))
    candidates=[]
    for c in cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0]:
        x,y,cw,ch=cv2.boundingRect(c)
        if min(cw,ch)<min(w,h)*.045 or cw>w*.32 or not .7<cw/ch<1.45: continue
        if cv2.contourArea(c)<cw*ch*.45:continue
        candidates.append((x,y,cw,ch))
    for triple in itertools.combinations(candidates,3):
        a=sorted(triple)
        if max(t[1] for t in a)-min(t[1] for t in a)>min(t[3] for t in a)*.2:continue
        if max(t[2] for t in a)>min(t[2] for t in a)*1.25:continue
        if abs((a[1][0]-a[0][0])-(a[2][0]-a[1][0]))>a[0][2]*.3:continue
        if a[1][0]-a[0][0]<a[0][2]*1.05:continue
        return [(x,y,cw,cw) for x,y,cw,ch in a]
    return None

def _swatch_distance(value,samples):
    """Validate OCR text against direct or quantized linear-light rendering.

    Dark sRGB values can change several levels in an 8-bit linear render
    target (e.g. #080803 is displayed near #0D0D00). This is validation only:
    the swatch never supplies or corrects the returned text.
    """
    if samples is None:return 0.
    code=np.asarray(rgb(value),float)
    srgb=code/255
    linear=np.where(srgb<=.04045,srgb/12.92,((srgb+.055)/1.055)**2.4)
    linear=np.rint(linear*255)/255
    rendered=np.rint(255*np.where(linear<=.0031308,linear*12.92,1.055*linear**(1/2.4)-.055))
    return float(min(np.linalg.norm(code-samples),np.linalg.norm(rendered-samples)))


def read_codes(image,cards,markers=None,enabled=None, *,
               deadline=None,clock=time.monotonic,check=lambda:None,text_fallback=None,fallback_diagnostics=None):
    """Read actual HEX values within an optional shared observation deadline."""
    _check_ocr_deadline(deadline,clock,check)
    def read_text(reader,*args,**kwargs):
        _check_ocr_deadline(deadline,clock,check)
        if deadline is not None:kwargs.update(deadline=deadline,clock=clock,check=check)
        try:return reader(*args,**kwargs)
        finally:_check_ocr_deadline(deadline,clock,check)
    out=[]
    for index,(x,y,w,h) in enumerate(cards):
        if enabled is not None and not enabled[index]:
            out.append(None);continue
        crop=image[y+int(h*.72):y+int(h*.98),x+int(w*.06):x+int(w*.96)]
        tight=image[y+int(h*.77):y+int(h*.94),x+int(w*.08):x+int(w*.94)]
        variants=[tight]
        gray=cv2.cvtColor(tight,cv2.COLOR_RGB2GRAY)
        variants+=[np.where(gray<th,0,255).astype('uint8') for th in (180,155)]
        samples=None
        if markers:
            # Validate OCR against the large color swatch, never the tiny board
            # marker: a 3x3 median there discards single-pixel target colors.
            cx=x+round(w*.50);cy=y+round(h*.43);rad=max(2,round(w*.04))
            samples=np.median(image[cy-rad:cy+rad+1,cx-rad:cx+rad+1].reshape(-1,3),axis=0)
        candidates=[];hash_seen=False
        for var in variants:
            var=cv2.resize(var,None,fx=4,fy=4,interpolation=cv2.INTER_CUBIC)
            var=cv2.copyMakeBorder(var,15,15,15,15,cv2.BORDER_CONSTANT,value=255 if var.ndim==2 else (255,255,255))
            text=read_text(_tesseract,var, config='--psm 7 -c tessedit_char_whitelist=#0123456789ABCDEF')
            hash_seen |= text.lstrip().startswith('#')
            m=re.fullmatch(r'#?([0-9A-F]{6})',text.replace(' ',''))
            if not m:continue
            value='#'+m.group(1); distance=_swatch_distance(value,samples)
            candidates.append((distance,value))
            if samples is not None and distance<3:break
        if text_fallback is not None and (not candidates or min(c[0] for c in candidates)>=3):
            # Optional research text reader sees screenshot pixels only. Never
            # pass native expected HEX or use swatch RGB to generate characters.
            _check_ocr_deadline(deadline,clock,check)
            result=text_fallback(image,[x,y,w,h],deadline=deadline,clock=clock,check=check)
            _check_ocr_deadline(deadline,clock,check)
            value=result.get('hex')
            distance=_swatch_distance(value,samples) if isinstance(value,str) and re.fullmatch('#[0-9A-F]{6}',value) else None
            close=result.get('glyphs_unambiguous') is True and distance is not None and distance<3
            if fallback_diagnostics is not None:
                fallback_diagnostics.append(dict(card_index=index,**result,swatch_distance=distance,swatch_accepted=close))
            if close:candidates.append((distance,value))
        if not candidates or min(c[0] for c in candidates)>=3:
            # Small antialiased glyphs may merge before enlargement (6/E,
            # missing 0). Threshold AFTER enlarging as a bounded fallback.
            # These are still independently read text, never swatch-derived
            # replacement digits, and the same <3 swatch gate applies.
            gray=cv2.cvtColor(tight,cv2.COLOR_RGB2GRAY)
            for factor,threshold,psm in ((6,170,8),(3,200,7),(4,200,8),(4,None,8)):
                enlarged=cv2.resize(gray,None,fx=factor,fy=factor,interpolation=cv2.INTER_CUBIC)
                var=enlarged if threshold is None else np.uint8(enlarged>=threshold)*255
                var=cv2.copyMakeBorder(var,15,15,15,15,cv2.BORDER_CONSTANT,value=255)
                text=read_text(_tesseract,var,config=f'--psm {psm} -c tessedit_char_whitelist=#0123456789ABCDEF')
                m=re.fullmatch(r'#?([0-9A-F]{6})',text.replace(' ',''))
                if m:
                    value='#'+m.group(1);distance=_swatch_distance(value,samples)
                    candidates.append((distance,value))
                    if distance<3:break
        if not candidates or min(c[0] for c in candidates)>=3:
            text=read_text(ocr,crop,'#0123456789ABCDEF')
            m=re.fullmatch(r'#?([0-9A-F]{6})',text.replace(' ',''))
            if m:
                value='#'+m.group(1); distance=_swatch_distance(value,samples)
                candidates.append((distance,value))
        if not candidates or min(c[0] for c in candidates)>=3:
            # Tesseract merges repeated narrow glyphs (e.g. 7F7F7F).
            # Segment only when six complete glyph components are unambiguous.
            region=image[y+round(h*.76):y+round(h*.96),x+round(w*.10):x+round(w*.94)]
            gray=cv2.cvtColor(region,cv2.COLOR_RGB2GRAY)
            for threshold in (160,140):
                mask=(gray<threshold).astype(np.uint8)
                stats=cv2.connectedComponentsWithStats(mask)[2]
                boxes=sorted([tuple(map(int,s[:4])) for s in stats[1:] if s[3]>=region.shape[0]*.45 and s[2]>=3 and s[4]>=6])
                # Some native cards include the leading # in this crop. Only
                # omit it when line OCR independently observed that prefix.
                if len(boxes)==7 and hash_seen:boxes=boxes[1:]
                if len(boxes)!=6:continue
                chars=[];cache={}
                for bx,by,bw,bh in boxes:
                    glyph=(1-mask[by:by+bh,bx:bx+bw])*255
                    key=(glyph.shape,glyph.tobytes())
                    if key not in cache:
                        cache[key]=read_text(ocr,cv2.copyMakeBorder(glyph,5,5,5,5,cv2.BORDER_CONSTANT,value=255),'0123456789ABCDEF',10)
                    chars.append(cache[key])
                if all(re.fullmatch('[0-9A-F]',c) for c in chars):
                    value='#'+''.join(chars);distance=_swatch_distance(value,samples)
                    candidates.append((distance,value))
                    if distance<3:break
        candidates.sort()
        # Require a close swatch match; a plausible six-digit OCR string alone
        # must not turn a low-nibble misread into a successful HEX check.
        value=candidates[0][1] if candidates and candidates[0][0]<3 else None
        out.append(value)
    _check_ocr_deadline(deadline,clock,check)
    return out

def green_buttons(image):
    h,w=image.shape[:2]; hsv=cv2.cvtColor(image,cv2.COLOR_RGB2HSV)
    mask=cv2.inRange(hsv,np.array([65,90,85]),np.array([95,255,255]))
    mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((7,7),np.uint8))
    out=[]
    for c in cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0]:
        x,y,cw,ch=cv2.boundingRect(c)
        if y>h*.65 and cw>w*.2 and 2.5<cw/max(ch,1)<18 and ch>h*.025 and cv2.contourArea(c)>cw*ch*.6:
            out.append((x+cw//2,y+ch//2,cw,ch))
    return sorted(out,key=lambda a:a[1],reverse=True)

def result_colors(image):
    h,w=image.shape[:2]
    mask=cv2.inRange(image,np.array([218]*3,np.uint8),np.array([255]*3,np.uint8))
    mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((5,5),np.uint8))
    pills=[]
    for c in cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0]:
        x,y,cw,ch=cv2.boundingRect(c)
        if 2.3<cw/max(ch,1)<5 and cw>w*.07 and ch>h*.02 and y>h*.35:
            text=ocr(image[y+round(ch*.20):y+round(ch*.80),x+round(cw*.315):x+round(cw*.95)],'#0123456789ABCDEF')
            m=re.fullmatch('#?([0-9A-F]{6})',text.replace(' ',''))
            if m:pills.append((x,y,'#'+m.group(1)))
    # Result page: three bright new-color pills; original pills are dark.
    if len(pills)!=3:return None
    if max(p[0] for p in pills)-min(p[0] for p in pills)<w*.08:pills.sort(key=lambda p:p[1])
    elif max(p[1] for p in pills)-min(p[1] for p in pills)<h*.08:pills.sort(key=lambda p:p[0])
    else:return None
    return [p[2] for p in pills]


def _timer_values(text):
    """Extract plausible countdown values from noisy timer OCR.

    The hourglass icon is adjacent to the digits and Tesseract may merge it
    with the first digit (for example ``4120`` for ``120``).  Keep the suffix
    candidates from a merged run so the icon cannot make an otherwise valid
    countdown disappear.  Zero is excluded because it is already past the
    safe input window.
    """
    values=[]
    # Keep every decimal digit and ignore the surrounding server-language
    # suffix/prefix (秒, 초, s, etc.).  ``\d`` is not enough here because OCR
    # engines can return full-width or other Unicode decimal digits.
    normalized=[];run=[]
    for char in str(text):
        if char.isdigit():
            try:run.append(str(unicodedata.digit(char)))
            except (TypeError,ValueError):run.append(char)
        elif run:
            normalized.append(''.join(run));run=[]
    if run:normalized.append(''.join(run))
    for run in normalized:
        # Keep the complete run and its short suffixes. A leading hourglass
        # glyph may be merged into a three-digit reading (``420`` for ``20``)
        # just as it may be merged into a four-digit reading (``4120``).
        # When the complete run is already a valid countdown, suffixes are
        # not alternative readings; adding them would let the final digit
        # outvote a clear value such as ``108``.  Suffixes remain available
        # for an icon-merged run such as ``420`` or ``4108`` whose complete
        # value is outside the countdown range.
        try:full_value=int(run)
        except ValueError:full_value=None
        if full_value is not None and 1<=full_value<=180:
            candidates=(run,)
        else:
            candidates=(run,)+tuple(run[-size:] for size in (3,2,1)
                                    if size<len(run))
        seen=set()
        for candidate in candidates:
            if candidate in seen:continue
            seen.add(candidate)
            try:value=int(candidate)
            except ValueError:continue
            if 1<=value<=180:values.append(value)
    return values


def detect_timer_track(image, *, unit=None):
    """Locate the bright horizontal countdown track in a game frame.

    The timer digits are rendered immediately before the track on the game's
    HUD.  A fixed right edge is fragile when the client is resized, so this
    helper looks for the longest compact, bright horizontal component in the
    upper HUD band.  It returns the track geometry and a safe right edge for
    a timer OCR crop, or ``None`` when no plausible track is visible.  No OCR
    is performed here; callers can keep their existing textual fallbacks.

    Coordinates use the image convention (left, top, right, bottom), with
    ``right`` and ``bottom`` exclusive.  ``timer_right`` leaves a small gap
    before the track so the first OCR crop cannot include its digits.
    """
    arr=np.asarray(image)
    if arr.ndim==2:
        gray=arr.astype(np.uint8,copy=False)
    elif arr.ndim==3 and arr.shape[2]>=3:
        # HSV V preserves bright coloured tracks that have lower luminance
        # than white text while still allowing the confidence gate below to
        # reject dim textured game content.
        rgb_arr=np.asarray(arr[...,:3],dtype=np.uint8)
        gray=cv2.cvtColor(rgb_arr,cv2.COLOR_RGB2GRAY)
        value=cv2.cvtColor(rgb_arr,cv2.COLOR_RGB2HSV)[...,2]
    else:
        return None
    h,w=gray.shape[:2]
    if h<12 or w<32:return None
    # The track is in the top HUD, but keep enough room for high-DPI layouts.
    band_h=max(12,min(h,round(max(h*.30,float(unit or 0)*3.0))))
    band=gray[:band_h]
    if 'value' in locals(): band_v=value[:band_h]
    else: band_v=band
    # A fixed 220 threshold misses coloured tracks.  The adaptive floor keeps
    # dark frames from turning a bright background patch into a candidate.
    high=max(145.0,min(230.0,float(np.percentile(band_v,90))))
    mask=(band_v>=high).astype(np.uint8)*255
    # Close tiny anti-aliased gaps along the horizontal track, without
    # connecting vertically separated HUD elements.
    close_w=max(3,min(31,round(max(3,float(unit or 0)*.10))))
    mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,
                          np.ones((3,close_w),np.uint8))
    contours=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0]
    candidates=[]
    min_width=max(32,round(w*.18),round(float(unit or 0)*3.0))
    for contour in contours:
        x,y,cw,ch=cv2.boundingRect(contour)
        if cw<min_width or ch<2 or ch>max(18,round(h*.035)):continue
        if y>=band_h or y+ch>round(h*.30):continue
        area=float(cv2.contourArea(contour))
        density=area/max(1.0,cw*ch)
        # A true bar remains bright over most of its rectangle.  This rejects
        # long text baselines and isolated bright UI strokes.
        patch=band_v[y:y+ch,x:x+cw]
        fill=float(np.mean(patch>=high)) if patch.size else 0.0
        if fill<.55 or density<.45:continue
        # Prefer the longest bar, then the most compact/bright one.  The
        # score avoids selecting a one-pixel decorative line over the track.
        score=float(cw)*(0.55+0.45*min(1.0,fill))*(0.75+0.25*min(1.0,ch/6.0))
        candidates.append((score,x,y,cw,ch,fill,density))
    if not candidates:return None
    _,x,y,cw,ch,fill,density=max(candidates,key=lambda c:(c[0],c[5],c[3]))
    # Keep OCR clear of the antialiased track edge; the gap scales with the
    # card/unit size but is bounded for tiny and very large clients.
    margin=max(2,round(max(1.0,float(unit or min(w,h)*.08))*.05))
    timer_right=max(1,x-margin)
    track_right=int(x+cw)
    track_bottom=int(y+ch)
    return {'track':(int(x),int(y),track_right,track_bottom),
            'left':int(x), 'top':int(y), 'right':track_right,
            'bottom':track_bottom,
            # ``fill_end`` is deliberately the observed bright endpoint.
            # It is used only as a monotonic cross-check; OCR remains the
            # source of the countdown value.
            'fill_end':track_right,
            'timer_right':int(timer_right),
            'center_y':float(y+ch/2),
            'width':int(cw),
            'height':int(ch),
            'fill':round(float(fill),3),
            'confidence':round(float(min(1.0,fill*.7+density*.3)),3)}


# Descriptive alias used by diagnostics and future callers.
locate_timer_track=detect_timer_track


def timer_bar_signal(image, *, unit=None):
    """Return the compact timer-bar observation used by live capture.

    Keep this small compatibility wrapper separate from ``timer_seconds`` so
    a missing or stylized progress bar never makes OCR fail.  The returned
    mapping is either ``None`` or the geometry produced by
    :func:`detect_timer_track`, including ``fill_end`` for temporal scoring.
    """
    return detect_timer_track(image, unit=unit)


def timer_seconds(image, unit=None, previous=None):
    """Read the upper-left game countdown across window sizes and UI themes.

    The timer is not anchored to the colour cards: on the standard 1280x960
    client it sits near x=30..110 while the cards begin around x=750.  The
    former crop used only a card-relative 37-pixel strip and could therefore
    miss the digits during the post-entry recheck.  These bounded crops keep
    the timer local, enlarge it for OCR, and use the previous reading to
    reject an icon-only or progress-bar digit.
    """
    h,w=image.shape[:2]
    ref=float(unit or max(24,min(w,h)*.08))
    portrait=w<h
    if portrait:
        # Preserve the established portrait location while allowing more
        # vertical margin for font rendering at 100% and high DPI.
        boxes=[(round(ref*.55),round(h*.035),
                min(w,round(ref*1.65)),min(h,round(h*.13))),
               (0,0,min(w,round(ref*2.2)),min(h,round(h*.16)))]
    else:
        # The timer glyphs occupy a short, bright cluster immediately to the
        # right of the hourglass.  The progress bar starts just after that
        # cluster and is itself a long bright component; including it in the
        # OCR crop produced false readings such as ``66`` for a visible
        # ``108``.  The dimensions below are proportional to the 1280x960
        # client and therefore follow DPI/window scaling.
        scale=max(.55,min(3.,min(w,h)/960.))
        focus_left=round(20*scale)
        focus_top=round(10*scale)
        # Keep the compact crop between the timer and the progress bar.  The
        # old 90 px edge cut through the third digit at 1280x960, turning a
        # visible 119 into readings such as 41.  112 px includes the complete
        # three-digit glyph while retaining a margin before the bar (the
        # proportional value follows the client scale).
        focus_right=round(112*scale)
        focus_bottom=round(46*scale)
        suffix_right=round(145*scale)
        # Use the HUD bar as a layout anchor when it is visible.  The bar is
        # drawn immediately after the timer digits and scales with the game
        # viewport, so its left edge is more reliable than a client-specific
        # pixel constant on resized/high-DPI windows.  Keep a generous
        # preceding span for the hourglass and localized prefix, while
        # stopping OCR before the bright bar itself.
        track=detect_timer_track(image,unit=unit)
        if track is not None and track.get('confidence',0.)>=.55:
            track_left=int(track.get('left',track['track'][0]))
            track_right=int(track.get('timer_right',track_left))
            span=max(round(90*scale),round(ref*1.15))
            focus_left=max(0,track_left-span)
            focus_right=max(focus_left+1,min(w,track_right))
            focus_top=max(0,int(track.get('top',round(10*scale)))-round(20*scale))
            focus_bottom=min(h,int(track.get('bottom',round(46*scale)))+round(7*scale))
            # A short suffix crop remains useful for language labels, but do
            # not run it across the full bright bar, which creates spurious
            # digit-shaped OCR contours.
            suffix_right=min(w,focus_right+round(20*scale))
        # The number is followed by localized text on some servers.  Keep the
        # same upper-left anchor, but let the OCR crop include that suffix;
        # the digit whitelist and _timer_values discard the language itself.
        # Keep the left edge at the window edge.  On the 1280x960 client the
        # hourglass begins around x=32 and the first digit around x=48; the
        # former x=52 crop could cut the first digit and turn ``119`` into
        # ``19`` or ``20``.  The timer is the only numeric HUD element in
        # this bounded upper-left region, so the wider anchor is safe.
        boxes=[(focus_left,focus_top,min(w,focus_right),
                min(h,focus_bottom)),
               # A slightly wider crop covers a localized suffix when it is
               # rendered directly after the digits.  It is lower priority
               # because its right edge can overlap the progress bar.
               (focus_left,focus_top,min(w,suffix_right),
                min(h,focus_bottom)),
               # Broad fallback: retain the old large crop for layouts where
               # the timer is shifted, while keeping it lower priority than
               # the two focused crops above.
               (0,0,min(w,round(max(ref*5.0,480))),
                min(h,round(max(ref*1.9,110))))]
    jobs=[]
    for left,top,right,bottom in boxes:
        left=max(0,min(w-1,left));top=max(0,min(h-1,top))
        right=max(left+1,min(w,right));bottom=max(top+1,min(h,bottom))
        crop=image[top:bottom,left:right]
        gray=cv2.cvtColor(crop,cv2.COLOR_RGB2GRAY) if crop.ndim==3 else crop
        # Grayscale avoids the coloured pill background suppressing white
        # glyphs. One raw and one high-contrast variant cover anti-aliasing.
        variants=[gray,np.where(gray>=170,255,0).astype('uint8')]
        jobs.append([(variant,psm) for variant in variants for psm in (6,11)])
    def read(job):
        variant,psm=job
        return _timer_values(ocr(variant,'0123456789',psm=psm))
    values=[]
    sources=[]
    flat=[(box_index,job) for box_index,group in enumerate(jobs)
          for job in group]
    if previous is not None:
        # Rechecks require every crop/variant to disambiguate short or merged
        # digits. Two independent OCR processes overlap that work without
        # weakening selection, changing task order, or using more workers on
        # machines with many cores. Initial detection retains its early exit.
        with ThreadPoolExecutor(max_workers=2,thread_name_prefix='timer-ocr') as pool:
            for (box_index,_),found in zip(flat,pool.map(read,[job for _,job in flat])):
                values.extend(found);sources.extend([box_index]*len(found))
    else:
        # Initial recognition must inspect the broad crop as well.  A narrow
        # crop can read the trailing ``19`` of a real ``119`` and the old
        # early return treated that as the complete countdown, cutting a long
        # session short.  Read all bounded variants before choosing a value;
        # the final crop is still limited to the timer's upper-left area and
        # candidates remain constrained to the known 1..180 second range.
        # Tesseract calls are independent and bounded to two workers, just as
        # in the recheck path.  This keeps the broader initial verification
        # from adding several seconds to the game countdown.
        with ThreadPoolExecutor(max_workers=2,thread_name_prefix='timer-ocr') as pool:
            for (box_index,_),found in zip(flat,pool.map(read,[job for _,job in flat])):
                values.extend(found);sources.extend([box_index]*len(found))
    if not values:return None
    # Prefer the tight timer crop.  OCR from the broad fallback may contain
    # the progress bar or another HUD number, while independent variants of
    # the focused crop normally agree on the actual countdown.  A frequency
    # tie is resolved toward the larger reading on the initial frame so a
    # clipped leading digit cannot shorten the workflow.
    focused=[v for v,s in zip(values,sources) if s==0]
    if focused:
        counts=Counter(focused)
        best=max(counts, key=lambda value:(counts[value],value))
        fallback=[v for v,s in zip(values,sources) if s>=1]
        fallback_high=[v for v in fallback if v>=100]
        # If the tight crop captured an incomplete/incorrect value, a high
        # three-digit reading repeated by the wider timer crops is stronger
        # evidence.  This covers both a short suffix (20 -> 119) and a
        # clipped first crop (41 -> 119), while requiring agreement between
        # at least two fallback readings when the focused value is plausible.
        fallback_sources={s for v,s in zip(values,sources) if s>=1 and v>=100}
        if fallback_high and (best < 90 or len(fallback_sources)>=2):
            high_counts=Counter(fallback_high)
            high=max(high_counts,key=lambda value:(high_counts[value],value))
            # A previous value below 90 is still in the suspicious clipped
            # range; permit the complete three-digit correction before the
            # ordinary non-increasing countdown guard is applied.
            if previous is None or int(previous)<90 or high<=int(previous)+1:
                return high
        if previous is None:return best
        # On a recheck, retain the monotonic countdown rule.  If the focused
        # crop only saw an icon or an incomplete suffix, fall through to the
        # combined candidates below.
        if int(previous)<=30:
            high=[v for v in focused if v>=100]
            if len(high)>=2:return max(high)
        ordered=[v for v in focused if v<=int(previous)+1]
        if ordered:return min(ordered,key=lambda v:abs(v-int(previous)))
    if previous is not None:
        # A first-frame partial crop can establish an erroneously short value
        # such as 20 while a subsequent frame clearly shows 119.  Permit a
        # correction only for that suspiciously short range and only when the
        # long value is repeated or comes from the broad timer crop.  This
        # preserves the non-increasing countdown guard for ordinary readings.
        if int(previous)<=30:
            high=[v for v,s in zip(values,sources) if v>=100]
            if high and (len(high)>=2 or any(s>=2 and v>=100
                                             for v,s in zip(values,sources))):
                return max(high)
        # A countdown can only stay the same or decrease between frames.
        ordered=[v for v in values if v<=int(previous)+1]
        if ordered:return min(ordered,key=lambda v:abs(v-int(previous)))
    return max(values)

def recognize(image,with_ocr=True,previous=None,enabled=None,*,read_colors=True):
    cards=color_cards(image)
    if cards is None:raise ValueError('未识别到染色小游戏的三张色码卡片。请先进入限时染色界面。')
    h,w=image.shape[:2]; white=np.min(image,axis=2)>210
    markers=[]
    stable=previous is not None and len(previous.cards)==3 and all(max(abs(a-b) for a,b in zip(old,new))<=2 for old,new in zip(previous.cards,cards))
    for index,(x,y,cw,ch) in enumerate(cards):
        if stable:
            markers.append(previous.markers[index]);continue
        cx=x+cw//2; start=y+ch; rows=np.any(white[start:,max(0,cx-2):cx+3],axis=1)
        last=-1; gap=0
        for i,on in enumerate(rows):
            gap=0 if on else gap+1
            if on:last=i
            if gap>max(5,int(cw*.10)):break
        if last<cw*.5: raise ValueError('色码卡片下方点位尚不可见，可能正在显示教学或结果窗口。')
        radius=max(4,round(cw*.10)); guess=start+last+radius
        # Find the white circular rim, not an interrupted vertical stem.
        ys=np.arange(start+round(cw*.55),min(h-15,start+round(cw*7)))
        best=(-1,guess)
        angles=np.arange(0,2*np.pi,2*np.pi/24)
        for rad in range(max(3,round(cw*.075)),max(5,round(cw*.13))+1):
            px=np.clip(np.rint(cx+rad*np.cos(angles)).astype(int),0,w-1)
            py=np.clip(np.rint(ys[:,None]+rad*np.sin(angles)).astype(int),0,h-1)
            score=np.mean(white[py,px],axis=1)
            # White target colors can fill the ring; do not reject a bright center.
            j=int(np.argmax(score))
            if score[j]>best[0]:best=(score[j],int(ys[j]))
        if best[0]<.60:raise ValueError('无法可靠识别颜色点位。请放大游戏窗口后重试。')
        markers.append(refine_marker_center(image,(cx,best[1]),cw))
    # Board bounds are card-layout geometry. A subpixel ring refinement must
    # not move the crop or its coordinate origin by a rounding pixel.
    card_centers=[x+cw//2 for x,y,cw,ch in cards]
    spacing=card_centers[1]-card_centers[0]
    left=max(0,round(card_centers[0]-spacing*.5)); right=min(w,round(card_centers[2]+spacing*.5))
    top=max(c[1]+c[3] for c in cards)+round(cards[0][2]*.25)
    bottom=min(h-3,top+(right-left))
    # Board interior is square in both portrait and landscape layouts.
    if any(not(top<my<bottom) for mx,my in markers):raise ValueError('色板定位不完整，已停止以避免误操作。')
    colors=read_codes(image,cards,markers,enabled=enabled) if with_ocr and read_colors else [None]*3
    seconds=None
    if with_ocr:
        unit=cards[0][2]
        seconds=timer_seconds(image,unit=unit,
                              previous=None if previous is None else previous.seconds)
    buttons=green_buttons(image)
    return Scene(cards,markers,(left,top,right,bottom),colors,seconds,buttons[0][:2] if buttons else None)

def measure_board_motion(before,after,board,feature_cache=None,texture_mask=None,
                         contrast_threshold=.04,diagnostics=None):
    """Fit texture motion, rejecting weak matches and static UI features."""
    l,t,r,b=board
    if texture_mask is not None:
        texture_mask=(np.asarray(texture_mask,dtype=bool)*255).astype(np.uint8)
        if texture_mask.shape!=(b-t,r-l):
            raise ValueError('Texture mask must match the board crop')
    mask_key=None if texture_mask is None else texture_mask.tobytes()
    diagnostics={} if diagnostics is None else diagnostics
    diagnostics.clear()
    diagnostics.update(contrast_threshold=float(contrast_threshold),passed=False)
    detector=cv2.SIFT_create(nfeatures=1800,contrastThreshold=float(contrast_threshold))
    def features(image):
        key=(id(image),tuple(board),mask_key,float(contrast_threshold))
        if feature_cache is not None and key in feature_cache:
            return feature_cache[key][1]
        crop=image[t:b,l:r]
        found=detector.detectAndCompute(cv2.cvtColor(crop,cv2.COLOR_RGB2GRAY) if crop.ndim==3 else crop,texture_mask)
        if feature_cache is not None:
            # Keep the image alive so object IDs cannot be reused in this cache.
            # The caller owns a per-analysis cache of immutable captured frames.
            feature_cache[key]=(image,found)
        return found
    ka,da=features(before);kb,db=features(after)
    diagnostics.update(features_before=len(ka),features_after=len(kb))
    if da is None or db is None or len(db)<2:
        diagnostics['reason']='insufficient_features';return None
    pairs=cv2.BFMatcher().knnMatch(da,db,k=2)
    good=[p[0] for p in pairs if len(p)==2 and p[0].distance<.7*p[1].distance]
    diagnostics['matches']=len(good)
    if len(good)<20:
        diagnostics['reason']='insufficient_matches';return None
    src=np.float32([ka[m.queryIdx].pt for m in good]);dst=np.float32([kb[m.trainIdx].pt for m in good])
    matrix,inliers=cv2.estimateAffinePartial2D(src,dst,method=cv2.RANSAC,ransacReprojThreshold=2)
    if matrix is None or inliers is None or not np.isfinite(matrix).all():
        diagnostics['reason']='invalid_transform';return None
    diagnostics.update(inliers=int(inliers.sum()),inlier_ratio=float(inliers.mean()))
    if int(inliers.sum())<20 or float(inliers.mean())<.5:
        diagnostics['reason']='insufficient_inliers';return None
    diagnostics.update(passed=True,reason='ok')
    return {'angle':round(float(np.degrees(np.arctan2(matrix[1,0],matrix[0,0]))),3),
            'scale':round(float(np.hypot(matrix[0,0],matrix[1,0])),4),'inliers':int(inliers.sum()),
            'matrix':matrix.tolist(),'origin':[l,t]}

def candidate_shift(image,scene,rules,visited=(),excluded=()):
    """Score shared translations using each third's own visible texture."""
    l,t,r,b=scene.board; third=(r-l)/3
    # Native-pixel sampling: a one-pixel pure dye must not fall between grid rows.
    # Cover the full visible height, including points near the board's edges.
    enabled=[p for p,rule in zip(scene.markers,rules) if rule['enabled']]
    if not enabled:return None
    ymin=int(np.ceil(max(my-(b-9) for mx,my in enabled)))
    ymax=int(np.floor(min(my-(t+9) for mx,my in enabled)))
    yy,xx=np.mgrid[ymin:ymax+1,-int(third*.5):int(third*.5)+1]
    dx,dy=xx.ravel(),yy.ravel(); scores=np.zeros(dx.shape,float); valid=np.ones(dx.shape,bool)
    active=0;raw_worst=np.zeros(dx.shape);raw_total=np.zeros(dx.shape);feasible=np.ones(dx.shape,bool)
    for i,((mx,my),rule) in enumerate(zip(scene.markers,rules)):
        if not rule['enabled']:continue
        active+=1; sx=mx-dx; sy=my-dy
        good=(sx>l+i*third+5)&(sx<l+(i+1)*third-5)&(sy>t+8)&(sy<b-8)
        sx=np.rint(np.clip(sx,0,image.shape[1]-1)).astype(int)
        sy=np.rint(np.clip(sy,0,image.shape[0]-1)).astype(int)
        pixels=image[sy,sx]; colors=lab(pixels)
        distances=np.min(np.linalg.norm(colors[:,None,:]-lab([rgb(c) for c in rule['colors']])[None,:,:],axis=2),axis=1)
        # Exclude UI geometry, not white dye. Pure white is a valid target.
        stem=(np.abs(sx-mx)<=3)&(sy<=my)
        radius=max(6,round(third*.055))
        marker=(sx-mx)**2+(sy-my)**2<=(radius+3)**2
        good &= ~(stem|marker)
        for region,px,py in excluded:
            if region==i:good &= (sx-px)**2+(sy-py)**2>16
        raw_worst=np.maximum(raw_worst,distances);raw_total+=distances
        feasible &= np.any(np.all(pixels[:,None,:]==np.array([rgb(c) for c in rule['colors']])[None,:,:],axis=2),axis=1) if rule['exact'] else distances<=rule['tolerance']
        scores=np.maximum(scores,distances/max(.6 if rule['exact'] else rule['tolerance'],.001)); valid &=good
    valid &= (np.abs(dx)+np.abs(dy)>0)
    for vx,vy in visited:valid &= (dx!=vx)|(dy!=vy)
    if not active or not valid.any():return None
    scores[~valid]=np.inf
    ids=np.flatnonzero(valid)
    winner=ids[np.lexsort((raw_total[ids],raw_worst[ids],~feasible[ids]))[0]]
    best=float(scores[winner]); candidates=np.flatnonzero(valid & (feasible==feasible[winner]) & (raw_worst==raw_worst[winner]) & (raw_total==raw_total[winner]))
    # Equal-color candidates are not equally robust: land inside an island,
    # away from antialiased edges, before preferring a shorter translation.
    mask=np.zeros(valid.shape,np.uint8);mask[candidates]=1;mask=mask.reshape(xx.shape)
    interior=cv2.distanceTransform(np.pad(mask,1),cv2.DIST_L2,5)[1:-1,1:-1].ravel()
    order=np.lexsort((dx[candidates]**2+dy[candidates]**2,-interior[candidates]))
    j=int(candidates[order[0]])
    return int(dx[j]),int(dy[j]),float(scores[j])
