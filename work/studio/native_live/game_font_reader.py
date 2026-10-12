"""Small, pixel-only reader for the game's fixed Latin HEX and timer font.

The asset combines decoded source glyph rendering variations with archived
text calibration. No native color, swatch, target, or expected timer is input.
Ambiguous, incomplete, and conflicting threshold reads stay unknown.
"""
import functools,hashlib,json,math,time
from pathlib import Path
import cv2,numpy as np
from scipy.spatial.distance import cdist

ASSET=Path(__file__).parent/'assets/game_font_glyphs.npz'
CHARACTERS='#0123456789ABCDEF'

@functools.lru_cache(maxsize=1)
def _load():
    meta=json.loads(ASSET.with_suffix('.json').read_text(encoding='utf-8'))
    if meta.get('schema')!=1 or hashlib.sha256(ASSET.read_bytes()).hexdigest()!=meta.get('asset_sha256'):
        raise ValueError('Game font asset checksum or schema mismatch')
    with np.load(ASSET,allow_pickle=False) as source:
        labels=source['labels'].copy();patterns=source['patterns'].astype(np.float64);ratios=source['ratios'].copy()
    if (patterns.shape!=(len(labels),24,16) or ratios.shape!=(len(labels),)
            or set(labels.tolist())!=set(CHARACTERS) or not np.isfinite(patterns).all()
            or not np.isfinite(ratios).all() or np.any(ratios<=0)
            or np.any(patterns<0) or np.any(patterns>1)):
        raise ValueError('Invalid game font asset shapes or values')
    for value in (labels,patterns,ratios):value.setflags(write=False)
    return labels,patterns,ratios

def prepare_game_font_assets():
    _load()
    return dict(path=str(ASSET),asset_sha256=hashlib.sha256(ASSET.read_bytes()).hexdigest(),preloaded=True)

def _guard(deadline,clock,check):
    check()
    if deadline is not None and (not math.isfinite(deadline) or clock()>=deadline):
        raise TimeoutError('Game font text deadline')

def _classify(mask,alphabet):
    labels,patterns,ratios=_load()
    normalized=cv2.resize(mask.astype(np.float32),(16,24),interpolation=cv2.INTER_AREA)
    # City-block distance is exactly the mean absolute template error, evaluated
    # in compiled code without allocating one full tensor for every character.
    distances=cdist(normalized.reshape(1,-1),patterns.reshape(len(patterns),-1),metric='cityblock')[0]/384
    distances+=.06*np.abs(np.log(ratios/(mask.shape[1]/mask.shape[0])))
    ordered=sorted((float(np.min(distances[labels==char])),char) for char in alphabet)
    distance,char=ordered[0];margin=ordered[1][0]-distance if len(ordered)>1 else 1.
    accepted=distance<=.18 and margin>=.025
    return dict(character=char if accepted else None,best_character=char,distance=distance,margin=margin)

def _read_line(gray,*,bright,thresholds,counts,alphabet,deadline,clock,check):
    # Enlarge before binarizing: a small antialiased stroke can otherwise
    # disappear or join its neighbour before segmentation sees its shape.
    enlarged=cv2.resize(gray,None,fx=4,fy=4,interpolation=cv2.INTER_CUBIC)
    reads=[]
    for threshold in thresholds:
        _guard(deadline,clock,check)
        mask=np.uint8(enlarged>=threshold if bright else enlarged<threshold)
        _,component_map,stats,_=cv2.connectedComponentsWithStats(mask,8)
        boxes=[]
        for index,(x,y,w,h,area) in enumerate(stats[1:],1):
            x,y,w,h,area=map(int,(x,y,w,h,area))
            if (h>=max(8,enlarged.shape[0]*.35) and w>=2 and area>=8
                    and x>0 and y>0 and x+w<mask.shape[1] and y+h<mask.shape[0]):
                boxes.append((x,y,w,h,index))
        boxes.sort()
        read=dict(threshold=threshold,text=None,component_count=len(boxes))
        if len(boxes) in counts:
            chars=[];decisions=[]
            for position,(x,y,w,h,index) in enumerate(boxes):
                _guard(deadline,clock,check)
                chunk=np.uint8(component_map[y:y+h,x:x+w]==index)
                decision=_classify(chunk,alphabet)
                if not bright and ((position==0 and decision['character']!='#')
                        or (position>0 and decision['character']=='#')):
                    decision['character']=None
                chars.append(decision['character']);decisions.append(decision)
            read.update(decisions=decisions,text=''.join(chars) if all(chars) else None)
        reads.append(read)
    _guard(deadline,clock,check)
    valid=[r['text'] for r in reads if r['text'] is not None]
    text=valid[0] if len(valid)>=2 and len(set(valid))==1 else None
    return dict(text=text,threshold_reads=reads,method='game_font_multithreshold')

def read_hex(image,card,*,deadline,clock=time.monotonic,check=lambda:None):
    _guard(deadline,clock,check)
    if len(card)!=4 or any(type(v) is not int for v in card):raise ValueError('Integer screenshot card required')
    x,y,w,h=card
    if x<0 or y<0 or w<=0 or h<=0 or x+w>image.shape[1] or y+h>image.shape[0]:
        raise ValueError('Card outside screenshot')
    crop=image[y+round(h*.74):y+round(h*.99),x+round(w*.03):x+round(w*.99)]
    if not crop.size:return dict(hex=None,glyphs_unambiguous=False,threshold_reads=[])
    result=_read_line(cv2.cvtColor(crop,cv2.COLOR_RGB2GRAY),bright=False,thresholds=(160,175,190),
        counts=(7,),alphabet=CHARACTERS,deadline=deadline,clock=clock,check=check)
    return dict(result,hex=result['text'],glyphs_unambiguous=result['text'] is not None,ready_for_input=False)

def read_countdown(image,located,*,deadline,clock=time.monotonic,check=lambda:None):
    _guard(deadline,clock,check)
    l,t,r,b=located['digit_box'];crop=image[t:b,l:r]
    if not crop.size:return dict(text=None,threshold_reads=[],method='game_font_multithreshold')
    result=_read_line(cv2.cvtColor(crop,cv2.COLOR_RGB2GRAY),bright=True,thresholds=(170,195,215),
        counts=(len(located['digit_components']),),alphabet='0123456789',deadline=deadline,clock=clock,check=check)
    text=result['text']
    value=int(text) if text is not None and not text.startswith('0') else None
    return dict(result,remaining_seconds=value if value is not None and 1<=value<=120 else None)
