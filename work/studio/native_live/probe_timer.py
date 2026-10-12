"""Bounded visual hourglass anchoring for saved/current dye HUD frames."""
import functools,hashlib,json,math,re,sys,time
from pathlib import Path
import cv2,numpy as np
from PIL import Image
from vision import ocr

@functools.lru_cache(maxsize=1)
def _template():
    image=np.asarray(Image.open(Path(__file__).parent/'assets/dye_timer_hourglass.png').convert('RGB'))
    return np.all(image>=210,axis=2).astype('uint8')

def prepare_timer_assets(path=None):
    image_path=Path(path) if path is not None else Path(__file__).parent/'assets/dye_timer_hourglass.png'
    metadata=json.loads(image_path.with_suffix('.json').read_text(encoding='utf-8'))
    actual=hashlib.sha256(image_path.read_bytes()).hexdigest()
    if actual!=metadata.get('bitmap_sha256'):raise ValueError('Timer template checksum mismatch')
    image=Image.open(image_path).convert('RGB')
    if image.size!=(14,21):raise ValueError('Unexpected timer template size')
    if path is None:
        _template.cache_clear();_template()
        from .game_font_reader import prepare_game_font_assets
        prepare_game_font_assets()
    return dict(path=str(image_path),bitmap_sha256=actual,template_size=list(image.size),preloaded=path is None)

def locate_timer(image,*,deadline=None,clock=time.monotonic,check=lambda:None):
    def guard():
        check()
        if deadline is not None and (not math.isfinite(deadline) or clock()>=deadline):
            raise TimeoutError('Timer localization deadline expired')
    guard()
    if image.ndim!=3 or image.shape[2]!=3:raise ValueError('RGB timer frame required')
    h,w=image.shape[:2]
    # Search area is only a coarse HUD prior; crop coordinates come from pixels.
    region=image[:max(1,round(h*.25)),:max(1,round(w*.5))]
    mask=np.all(region>=210,axis=2).astype('uint8')
    _,labels,stats,_=cv2.connectedComponentsWithStats(mask)
    # White icon matching remains strict. The complete digit count must also
    # see dim antialiased strokes that the actual text reader can read.
    digit_stats=cv2.connectedComponentsWithStats(np.all(region>=170,axis=2).astype('uint8'))[2]
    template=_template();candidates=[]
    for index,(x,y,cw,ch,area) in enumerate(stats[1:],1):
        guard();x,y,cw,ch,area=map(int,(x,y,cw,ch,area))
        if not 7<=cw<=64 or not 10<=ch<=96 or not .45<cw/ch<.9:continue
        component=(labels[y:y+ch,x:x+cw]==index).astype('uint8')
        normalized=cv2.resize(component,(template.shape[1],template.shape[0]),interpolation=cv2.INTER_NEAREST)
        score=float(2*np.count_nonzero(normalized & template)/(np.count_nonzero(normalized)+np.count_nonzero(template)))
        if score<.86:continue
        digits=[]
        for dx,dy,dw,dh,da in digit_stats[1:]:
            if (x+cw+ch*.15<=dx<x+cw+ch*3 and .7*ch<=dh<=1.3*ch
                    and abs(float(dy+dh/2)-(y+ch/2))<ch*.2 and da>=ch):
                digits.append([int(dx),int(dy),int(dw),int(dh)])
        if not 1<=len(digits)<=3:continue
        digits.sort();first=digits[0]
        # The centered countdown caption leaves more icon-to-digit space when
        # it contains only one digit; rounding grows that gap at scaled sizes.
        if first[0]-(x+cw)>ch*(1.25 if len(digits)==1 else .85):continue
        if any(b[0]-(a[0]+a[2])>ch*.6 for a,b in zip(digits,digits[1:])):continue
        # A narrow leading 1 can start left of the old fixed icon ratio.
        # Crop around measured complete digits with margin for antialiasing.
        l=max(0,x+cw+1);r=min(w,round(x+cw*5))
        t=max(0,round(y-ch*.2857));b=min(h,round(y+ch*1.2381))
        if any(dx<l or dx+dw>r or dy<t or dy+dh>b for dx,dy,dw,dh in digits):continue
        candidates.append(dict(anchor_box=[x,y,cw,ch],digit_box=[l,t,r,b],shape_score=score,
                               digit_components=digits))
    guard()
    if len(candidates)!=1:raise ValueError('Timer anchor missing or ambiguous')
    return dict(candidates[0],source='measured_hourglass_component',
        search_region=[0,0,region.shape[1],region.shape[0]],
        scope='Template, top-left HUD prior and relative icon/digit layout; no arbitrary UI theme or live DPI guarantee')

def select_timer_candidate(values,*,digit_count=None,previous=None,captured_at=None):
    candidates={v for v in values if type(v) is int and 1<=v<=120}
    confidence='two_pass_agree' if len(candidates)==1 and len([v for v in values if v is not None])>=2 else 'single_pass'
    if previous is not None:
        seconds,when=previous
        elapsed=max(0.,captured_at-when)
        plausible={v for v in candidates if seconds-math.ceil(elapsed)-3<=v<=seconds+1}
        if plausible!=candidates:confidence='temporal_selected'
        candidates=plausible
    if len(candidates)>1 and digit_count is not None:
        matching={v for v in candidates if len(str(v))==digit_count}
        if len(matching)==1:candidates=matching;confidence='digit_count_selected'
    if len(candidates)==1 and digit_count is not None and len(str(next(iter(candidates))))<digit_count:
        candidates=set()
    return (next(iter(candidates)),confidence) if len(candidates)==1 else (None,'unknown')

def read_timer(image,*,deadline,clock=time.monotonic,check=lambda:None,previous=None,captured_at=None):
    located=locate_timer(image,deadline=deadline,clock=clock,check=check)
    from .game_font_reader import read_countdown
    font_read=read_countdown(image,located,deadline=deadline,clock=clock,check=check)
    if font_read.get('remaining_seconds') is not None:
        value=font_read['remaining_seconds']
        seconds,confidence=select_timer_candidate([value,value],digit_count=len(located['digit_components']),
            previous=previous,captured_at=captured_at)
        return dict(remaining_seconds=seconds,timer_confidence=confidence,timer_font_read=font_read,
            timer_ocr_variants=[],timer_segmented_variants=[],timer_segmented_psm_fallbacks=[],
            timer_ocr_methods=[],timer_localization=located)
    l,t,r,b=located['digit_box'];gray=cv2.cvtColor(image[t:b,l:r],cv2.COLOR_RGB2GRAY)
    values=[]
    for threshold,psm in ((170,7),(200,8)):
        check();variant=np.where(gray>=threshold,0,255).astype('uint8')
        scale=128/max(gray.shape[0],1)
        enlarged=cv2.resize(variant,None,fx=scale,fy=scale,interpolation=cv2.INTER_NEAREST)
        enlarged=cv2.copyMakeBorder(enlarged,16,16,16,16,cv2.BORDER_CONSTANT,value=255)
        text=ocr(enlarged,'0123456789',psm=psm,deadline=deadline,clock=clock,check=check).strip()
        values.append(int(text) if re.fullmatch(r'[0-9]{1,3}',text) and 1<=int(text)<=120 else None)
    seconds,confidence=select_timer_candidate(values,digit_count=len(located['digit_components']),
        previous=previous,captured_at=captured_at)
    segmented=[];segmented_fallbacks=[]
    for threshold in (() if seconds is not None else (170,200)):
        chars=[]
        for x,y,w,h in located['digit_components']:
            check();crop=image[y:y+h,x:x+w]
            gray_char=cv2.cvtColor(crop,cv2.COLOR_RGB2GRAY)
            variant=np.where(gray_char>=threshold,0,255).astype('uint8')
            enlarged=cv2.resize(variant,None,fx=8,fy=8,interpolation=cv2.INTER_NEAREST)
            enlarged=cv2.copyMakeBorder(enlarged,20,20,20,20,cv2.BORDER_CONSTANT,value=255)
            text=ocr(enlarged,'0123456789',psm=10,deadline=deadline,clock=clock,check=check).strip()
            if not re.fullmatch(r'[0-9]',text):
                text=ocr(enlarged,'0123456789',psm=8,deadline=deadline,clock=clock,check=check).strip()
                segmented_fallbacks.append(dict(threshold=threshold,component=[x,y,w,h],psm=8))
            chars.append(text if re.fullmatch(r'[0-9]',text) else '')
        text=''.join(chars)
        segmented.append(int(text) if all(chars) and re.fullmatch(r'[0-9]{1,3}',text) and 1<=int(text)<=120 else None)
    if seconds is None and len(segmented)==2 and segmented[0] is not None and segmented[0]==segmented[1]:
        seconds,confidence=select_timer_candidate(segmented,digit_count=len(located['digit_components']),previous=previous,captured_at=captured_at)
        if seconds is not None:confidence='segmented_selected'
    return dict(remaining_seconds=seconds,timer_ocr_variants=values,timer_segmented_variants=segmented,
        timer_segmented_psm_fallbacks=segmented_fallbacks,
        timer_confidence=confidence,timer_font_read=font_read,
        timer_ocr_methods=[dict(threshold=170,psm=7),dict(threshold=200,psm=8)],timer_localization=located)
