"""Visual recognition only. Coordinates are physical client-image pixels."""
from dataclasses import dataclass
from pathlib import Path
import itertools, re, sys, os, shutil, subprocess, io, shlex
import cv2
import numpy as np
import pytesseract
from PIL import Image

OCR_AVAILABLE = None
OCR_CONFIG = ''

def configure_ocr(strict=False):
    """Check the OCR executable and English data before a timed capture."""
    global OCR_AVAILABLE, OCR_CONFIG
    OCR_CONFIG = ''
    root=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))
    candidates=[root/'ocr/tesseract.exe',
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

def _ocr_text(image, *, lang='eng', config='', timeout=2):
    """Use binary pipes so OCR never depends on temporary-file path encoding."""
    if not isinstance(image, Image.Image):image=Image.fromarray(image)
    buffer=io.BytesIO()
    image.save(buffer,format='PNG')
    # Parse our internal options once, removing grouping quotes before Windows
    # serializes the argument list. Retained quotes become part of tessdata's
    # filename when passed through pytesseract's Windows config parser.
    args=[pytesseract.pytesseract.tesseract_cmd,'stdin','stdout','-l',lang]
    args.extend(shlex.split(config,posix=True))
    result=subprocess.run(args,input=buffer.getvalue(),capture_output=True,
        timeout=timeout,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:
        raise pytesseract.TesseractError(result.returncode,result.stderr.decode('utf-8',errors='replace'))
    return result.stdout.decode('utf-8',errors='replace')


def _tesseract(image, config, timeout=2):
    """Return OCR text, degrading to an empty result when Tesseract is absent."""
    global OCR_AVAILABLE
    if OCR_AVAILABLE is False:
        return ''
    try:
        text = _ocr_text(image, lang='eng', config=' '.join(filter(None,(OCR_CONFIG,config))), timeout=timeout).strip()
        OCR_AVAILABLE = True
        return text
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

def ocr(im,whitelist,psm=7):
    if im.size==0:return ''
    h,w=im.shape[:2]; scale=max(2,40/max(h,1))
    im=cv2.resize(im,None,fx=scale,fy=scale,interpolation=cv2.INTER_CUBIC)
    return _tesseract(Image.fromarray(im), config=f'--psm {psm} -c tessedit_char_whitelist={whitelist}')

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


def read_codes(image,cards,markers=None,enabled=None):
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
        candidates=[]
        for var in variants:
            var=cv2.resize(var,None,fx=4,fy=4,interpolation=cv2.INTER_CUBIC)
            var=cv2.copyMakeBorder(var,15,15,15,15,cv2.BORDER_CONSTANT,value=255 if var.ndim==2 else (255,255,255))
            text=_tesseract(var, config='--psm 7 -c tessedit_char_whitelist=#0123456789ABCDEF')
            m=re.fullmatch(r'#?([0-9A-F]{6})',text.replace(' ',''))
            if not m:continue
            value='#'+m.group(1); distance=_swatch_distance(value,samples)
            candidates.append((distance,value))
            if samples is not None and distance<3:break
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
                text=_tesseract(var,config=f'--psm {psm} -c tessedit_char_whitelist=#0123456789ABCDEF')
                m=re.fullmatch(r'#?([0-9A-F]{6})',text.replace(' ',''))
                if m:
                    value='#'+m.group(1);distance=_swatch_distance(value,samples)
                    candidates.append((distance,value))
                    if distance<3:break
        if not candidates or min(c[0] for c in candidates)>=3:
            text=ocr(crop,'#0123456789ABCDEF')
            m=re.fullmatch(r'#?([0-9A-F]{6})',text.replace(' ',''))
            if m:
                value='#'+m.group(1); distance=_swatch_distance(value,samples)
                candidates.append((distance,value))
        if not candidates or min(c[0] for c in candidates)>=3:
            # Tesseract merges repeated narrow glyphs (e.g. 7F7F7F).
            # Segment only when six complete glyph components are unambiguous.
            region=image[y+round(h*.76):y+round(h*.96),x+round(w*.10):x+round(w*.94)]
            gray=cv2.cvtColor(region,cv2.COLOR_RGB2GRAY);mask=(gray<160).astype(np.uint8)
            stats=cv2.connectedComponentsWithStats(mask)[2]
            boxes=sorted([tuple(map(int,s[:4])) for s in stats[1:] if s[3]>=region.shape[0]*.45 and s[2]>=3 and s[4]>=6])
            if len(boxes)==6:
                chars=[];cache={}
                for bx,by,bw,bh in boxes:
                    glyph=(1-mask[by:by+bh,bx:bx+bw])*255
                    key=(glyph.shape,glyph.tobytes())
                    if key not in cache:
                        cache[key]=ocr(cv2.copyMakeBorder(glyph,5,5,5,5,cv2.BORDER_CONSTANT,value=255),'0123456789ABCDEF',10)
                    chars.append(cache[key])
                if all(re.fullmatch('[0-9A-F]',c) for c in chars):
                    value='#'+''.join(chars);distance=_swatch_distance(value,samples)
                    candidates.append((distance,value))
        candidates.sort()
        # Require a close swatch match; a plausible six-digit OCR string alone
        # must not turn a low-nibble misread into a successful HEX check.
        value=candidates[0][1] if candidates and candidates[0][0]<3 else None
        out.append(value)
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

def recognize(image,with_ocr=True,previous=None,enabled=None):
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
        markers.append((cx,best[1]))
    spacing=markers[1][0]-markers[0][0]
    left=max(0,round(markers[0][0]-spacing*.5)); right=min(w,round(markers[2][0]+spacing*.5))
    top=max(c[1]+c[3] for c in cards)+round(cards[0][2]*.25)
    bottom=min(h-3,top+(right-left))
    # Board interior is square in both portrait and landscape layouts.
    if any(not(top<my<bottom) for mx,my in markers):raise ValueError('色板定位不完整，已停止以避免误操作。')
    colors=read_codes(image,cards,markers,enabled=enabled) if with_ocr else [None]*3
    seconds=None
    if with_ocr:
        unit=cards[0][2]
        # Timer sits at upper-left; keep crop independent of aspect ratio.
        portrait=w<h
        if portrait:
            roi=image[round(h*.05):round(h*.095),round(unit*.68):min(w,round(unit*1.35))]
        else:
            # Exclude the hourglass and bar; retain all three timer digits.
            roi=image[round(unit*.225):round(unit*.675),round(unit*.77):min(w,round(unit*1.49))]
        text=ocr(roi,'0123456789',psm=7 if not portrait else 6)
        values=[int(v) for v in re.findall(r'\d{1,3}',text) if 0<=int(v)<=120]
        seconds=values[0] if len(values)==1 else None
    buttons=green_buttons(image)
    return Scene(cards,markers,(left,top,right,bottom),colors,seconds,buttons[0][:2] if buttons else None)

def measure_board_motion(before,after,board,feature_cache=None,texture_mask=None):
    """Fit texture motion, rejecting weak matches and static UI features."""
    l,t,r,b=board
    if texture_mask is not None:
        texture_mask=(np.asarray(texture_mask,dtype=bool)*255).astype(np.uint8)
        if texture_mask.shape!=(b-t,r-l):
            raise ValueError('Texture mask must match the board crop')
    mask_key=None if texture_mask is None else texture_mask.tobytes()
    detector=cv2.SIFT_create(nfeatures=1800)
    def features(image):
        key=(id(image),tuple(board),mask_key)
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
    if da is None or db is None or len(db)<2:return None
    pairs=cv2.BFMatcher().knnMatch(da,db,k=2)
    good=[p[0] for p in pairs if len(p)==2 and p[0].distance<.7*p[1].distance]
    if len(good)<20:return None
    src=np.float32([ka[m.queryIdx].pt for m in good]);dst=np.float32([kb[m.trainIdx].pt for m in good])
    matrix,inliers=cv2.estimateAffinePartial2D(src,dst,method=cv2.RANSAC,ransacReprojThreshold=2)
    if matrix is None or int(inliers.sum())<20 or float(inliers.mean())<.5:return None
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
    ymin=max(my-(b-9) for mx,my in enabled)
    ymax=min(my-(t+9) for mx,my in enabled)
    yy,xx=np.mgrid[ymin:ymax+1,-int(third*.5):int(third*.5)+1]
    dx,dy=xx.ravel(),yy.ravel(); scores=np.zeros(dx.shape,float); valid=np.ones(dx.shape,bool)
    active=0;raw_worst=np.zeros(dx.shape);raw_total=np.zeros(dx.shape);feasible=np.ones(dx.shape,bool)
    for i,((mx,my),rule) in enumerate(zip(scene.markers,rules)):
        if not rule['enabled']:continue
        active+=1; sx=mx-dx; sy=my-dy
        good=(sx>l+i*third+5)&(sx<l+(i+1)*third-5)&(sy>t+8)&(sy<b-8)
        sx=np.clip(sx,0,image.shape[1]-1); sy=np.clip(sy,0,image.shape[0]-1)
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
