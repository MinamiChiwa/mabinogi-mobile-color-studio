"""Research-only screenshot text templates, never a color-to-HEX decoder.

Templates are prior successful screenshot OCR glyphs, excluding current failed
session. Two threshold reads must agree and every character must be confident.
Missing/ambiguous components remain unknown. Limited font/size/theme evidence.
"""
import functools,hashlib,json,math,time
from pathlib import Path
import cv2,numpy as np

ASSET=Path(__file__).parent/'assets/dye_hex_glyphs.npz'
METADATA=ASSET.with_suffix('.json')
THRESHOLDS=(160,180)


def extract_glyphs(image,card,threshold):
    if len(card)!=4 or any(type(v) is not int for v in card):raise ValueError('Integer screenshot card required')
    x,y,w,h=card
    if w<=0 or h<=0 or x<0 or y<0 or x+w>image.shape[1] or y+h>image.shape[0]:raise ValueError('Card outside screenshot')
    region=image[y+round(h*.76):y+round(h*.96),x+round(w*.10):x+round(w*.94)]
    mask=np.uint8(cv2.cvtColor(region,cv2.COLOR_RGB2GRAY)<threshold)
    stats=cv2.connectedComponentsWithStats(mask)[2]
    boxes=sorted([tuple(map(int,s[:4])) for s in stats[1:] if s[3]>=region.shape[0]*.45 and s[2]>=3 and s[4]>=6])
    # Require a distinct prefix plus six complete components. The reference
    # prefix is classified independently too; no guessing a dropped glyph.
    if len(boxes)!=7:return None
    return [cv2.resize(mask[by:by+bh,bx:bx+bw].astype(np.float32),(16,24),interpolation=cv2.INTER_AREA)
            for bx,by,bw,bh in boxes]


@functools.lru_cache(maxsize=1)
def _load():
    prepare_hex_assets(validate_only=True)
    with np.load(ASSET,allow_pickle=False) as asset:
        data={key:asset[key].copy() for key in asset.files}
    for threshold in THRESHOLDS:
        labels=data[f'labels_{threshold}'];patterns=data[f'patterns_{threshold}']
        if patterns.shape!=(len(labels),24,16) or not np.isfinite(patterns).all():raise ValueError('Invalid template shapes')
        if set(labels.tolist())!=set('#0123456789ABCDEF'):raise ValueError('Incomplete screenshot glyph coverage')
        patterns.setflags(write=False)
    return data


def prepare_hex_assets(path=None,metadata_path=None,*,validate_only=False):
    path=Path(path) if path is not None else ASSET
    metadata=json.loads((Path(metadata_path) if metadata_path is not None else METADATA).read_text(encoding='utf-8'))
    actual=hashlib.sha256(path.read_bytes()).hexdigest()
    if actual!=metadata.get('asset_sha256'):raise ValueError('HEX template checksum mismatch')
    if metadata.get('schema')!=1 or metadata.get('thresholds')!=list(THRESHOLDS):raise ValueError('Unsupported template metadata')
    if path==ASSET and not validate_only:_load()
    return dict(path=str(path.resolve()),asset_sha256=actual,preloaded=path==ASSET and not validate_only,
        scope='Prior screenshot text glyphs, fixed theme and measured 80/81px cards; not arbitrary DPI guarantee')


def read_card_glyphs(image,card,*,deadline,check=lambda:None,clock=time.monotonic):
    def guard():
        check()
        if not math.isfinite(deadline) or clock()>=deadline:raise TimeoutError('HEX glyph deadline')
    guard();data=_load();reads=[]
    for threshold in THRESHOLDS:
        guard();chunks=extract_glyphs(image,card,threshold)
        if chunks is None:reads.append(dict(threshold=threshold,text=None,reason='incomplete_components'));continue
        labels=data[f'labels_{threshold}'];patterns=data[f'patterns_{threshold}'];decisions=[];characters=[]
        for index,chunk in enumerate(chunks):
            guard();distances=np.mean(np.abs(patterns-chunk),axis=(1,2))
            classes='#' if index==0 else '0123456789ABCDEF'
            ordered=sorted((float(np.min(distances[labels==c])),c) for c in classes)
            distance,c=ordered[0]
            margin=ordered[1][0]-distance if len(ordered)>1 else 1.
            # Fixed engineering reject thresholds, not a probabilistic score.
            unambiguous=distance<=.18 and margin>=.04
            decisions.append(dict(character=c if unambiguous else None,distance=distance,margin=margin))
            characters.append(c if unambiguous else None)
        text=''.join(characters) if all(characters) else None
        reads.append(dict(threshold=threshold,text=text,decisions=decisions))
    guard();texts=[r['text'] for r in reads]
    code=texts[0] if len(texts)==2 and texts[0] is not None and texts[0]==texts[1] else None
    return dict(hex=code,method='two_threshold_reference_glyphs',threshold_reads=reads,
        glyphs_unambiguous=code is not None,ready_for_input=False)
