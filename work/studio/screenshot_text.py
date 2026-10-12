"""Screenshot-only research text reader with explicit independent agreement."""
import re,time
import cv2,numpy as np
from vision import _tesseract,_swatch_distance,_timer_values,timer_bar_signal as _timer_bar_signal

def timer_bar_signal(image,*,unit=None):
    signal=_timer_bar_signal(image,unit=unit)
    if signal is not None:return signal
    # The shared detector needs a long bar. Late screenshot feedback also
    # needs the short, bright segment immediately after the countdown text.
    h,w=image.shape[:2];unit=float(unit or min(w,h)*.08)
    band_h=min(h,max(16,round(unit*.85),round(h*.09)))
    gray=cv2.cvtColor(image[:band_h],cv2.COLOR_RGB2GRAY)
    mask=np.uint8(gray>=220)*255
    mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((2,max(3,round(unit*.04))),np.uint8))
    candidates=[]
    for contour in cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0]:
        x,y,cw,ch=cv2.boundingRect(contour)
        if not (unit*.8<x<w*.45 and cw>=max(16,unit*.2) and 2<=ch<=max(10,unit*.22)):
            continue
        fill=float(np.mean(gray[y:y+ch,x:x+cw]>=220))
        if cw/ch<3 or fill<.7:continue
        candidates.append((cw,x,y,ch,fill))
    if not candidates:return None
    cw,x,y,ch,fill=max(candidates)
    right=x+cw;bottom=y+ch
    return dict(track=(x,y,right,bottom),left=x,top=y,right=right,bottom=bottom,
        fill_end=right,timer_right=max(1,x-max(2,round(unit*.05))),center_y=y+ch/2,
        width=cw,height=ch,fill=fill,confidence=fill)

def read_timer(image,unit,check=lambda:None,deadline=None,diagnostics=None):
    deadline=min(time.monotonic()+.85,deadline or float('inf'))
    from native_live.probe_timer import locate_timer
    from native_live.game_font_reader import read_countdown
    try:
        located=locate_timer(image,deadline=deadline,check=check)
        font_read=read_countdown(image,located,deadline=deadline,check=check)
        if font_read.get('remaining_seconds') is not None:
            if diagnostics is not None:
                diagnostics.update(crop=located['digit_box'],reads=font_read['threshold_reads'],
                    seconds=font_read['remaining_seconds'],font_read=font_read,localization=located)
            return font_read['remaining_seconds']
    except (ValueError,TimeoutError):
        check()
    h,w=image.shape[:2];signal=timer_bar_signal(image,unit=unit)
    scale=max(.55,min(3.,min(w,h)/960))
    if signal:
        right=signal['timer_right'];left=max(0,signal['left']-max(round(unit*1.4),round(95*scale)))
        top=max(0,signal['top']-max(round(24*scale),round(unit*.25)))
        bottom=min(h,signal['bottom']+max(round(24*scale),round(unit*.25)))
    elif w<h:
        left,top,right,bottom=0,0,min(w,round(unit*2.2)),min(h,round(h*.16))
    else:left,top,right,bottom=0,0,min(w,round(150*scale)),min(h,max(round(80*scale),round(unit*.75)))
    crop=image[top:bottom,left:right]
    if not crop.size:return None
    gray=cv2.cvtColor(crop,cv2.COLOR_RGB2GRAY);gray=cv2.resize(gray,None,fx=3,fy=3)
    values=[];reads=[]
    for threshold in (None,170):
        check()
        if time.monotonic()>=deadline:break
        variant=gray if threshold is None else np.uint8(gray>=threshold)*255
        try:text=_tesseract(variant,config='--psm 7 -c tessedit_char_whitelist=0123456789',
            timeout=.4,deadline=deadline,check=check)
        except TimeoutError:break
        valid=[v for v in _timer_values(text) if 0<v<=120]
        values.extend(valid);reads.append(dict(threshold=threshold,text=text,seconds=valid))
    agreed=[v for v in values if values.count(v)>=2]
    seconds=max(agreed) if agreed else None
    if diagnostics is not None:
        diagnostics.update(crop=[left,top,right,bottom],bar=signal,reads=reads,seconds=seconds)
    return seconds

def read_visible(image,cards,deadline=None,check=lambda:None):
    out=[];diagnostics=[]
    for index,(x,y,w,h) in enumerate(cards):
        crop=image[y+round(h*.74):y+round(h*.99),x+round(w*.03):x+round(w*.99)]
        gray=cv2.cvtColor(crop,cv2.COLOR_RGB2GRAY)
        enlarged=cv2.resize(gray,None,fx=4,fy=4,interpolation=cv2.INTER_CUBIC)
        cx=x+round(w*.5);cy=y+round(h*.43);rad=max(2,round(w*.04))
        swatch=np.median(image[cy-rad:cy+rad+1,cx-rad:cx+rad+1].reshape(-1,3),axis=0)
        from native_live.game_font_reader import read_hex
        font_read=read_hex(image,(x,y,w,h),deadline=deadline,check=check)
        value=font_read.get('hex')
        if value is not None and _swatch_distance(value,swatch)<5:
            out.append(value)
            reads=[dict(row,hex=row['text'],normalized=row['text']) for row in font_read['threshold_reads']]
            diagnostics.append(dict(region=index,reads=reads,swatch_rgb=swatch.tolist(),hex=value,
                font_read=font_read,source='game font text only; swatch verifies but cannot supply digits'))
            continue
        reads=[];agreed=None
        for threshold,scale,interpolation in ((170,4,cv2.INTER_CUBIC),(195,4,cv2.INTER_CUBIC),
                (205,5,cv2.INTER_LINEAR),(145,4,cv2.INTER_CUBIC)):
            check()
            if deadline is not None and time.monotonic()>=deadline:raise TimeoutError('Research text deadline')
            source=enlarged if scale==4 else cv2.resize(gray,None,fx=scale,fy=scale,interpolation=interpolation)
            var=np.uint8(source>=threshold)*255
            count,labels,stats,_=cv2.connectedComponentsWithStats(np.uint8(var==0),8)
            for component in range(1,count):
                bx,by,bw,bh,area=stats[component]
                if bx==0 or by==0 or bx+bw==var.shape[1] or by+bh==var.shape[0]:
                    var[labels==component]=255
            var=cv2.copyMakeBorder(var,12,12,12,12,cv2.BORDER_CONSTANT,value=255)
            text=_tesseract(var,config='--psm 7 -c tessedit_char_whitelist=#0123456789ABCDEFO',
                deadline=deadline,check=check)
            # Keep the complete glyph sequence: a printed zero may be read as
            # O. Missing digits still fail the six-character agreement check.
            normalized=text.replace(' ','').replace('O','0')
            match=re.fullmatch('#?([0-9A-F]{6})',normalized)
            value='#'+match.group(1) if match else None
            reads.append(dict(threshold=threshold,scale=scale,text=text,normalized=normalized,hex=value))
            valid=[v['hex'] for v in reads if v['hex']]
            agreed=next((v for v in valid if valid.count(v)>=2 and _swatch_distance(v,swatch)<5),None)
            if agreed:break
        out.append(agreed)
        diagnostics.append(dict(region=index,reads=reads,swatch_rgb=swatch.tolist(),hex=agreed,
            source='independent text only; swatch verifies but cannot supply digits'))
    return out,diagnostics
