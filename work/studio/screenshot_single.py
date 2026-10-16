"""Single-region screenshot search: inspect each view before exploring another."""
import cv2,numpy as np
from atlas_masks import material_masks
from screenshot_samples import distances
from color_matching import matching_distances


def candidates(c,*,matched_only=True):
    """Use original visible RGB from the enabled material, without a tile model."""
    active=[i for i,r in enumerate(c.rules) if r['enabled']]
    if len(active)!=1:return []
    i=active[0];rule=c.rules[i];l,t,r,b=c.scene.board
    image=c.frame[t:b,l:r];mask=material_masks(c.scene)[i]
    y,x=np.where(mask)
    if not len(x):return []
    colors=image[y,x];delta=distances(colors,rule)
    quality=matching_distances(colors,rule)
    matched=delta<=(0 if rule['exact'] else rule['tolerance'])
    ids=np.flatnonzero(matched) if matched_only else np.arange(len(x))
    if not len(ids):return []
    interior=np.zeros(mask.shape,np.uint8);interior[y[matched],x[matched]]=1
    margin=cv2.distanceTransform(interior,cv2.DIST_L2,5)[y[ids],x[ids]]
    marker=np.asarray(c.scene.markers[i])-c.scene.board[:2]
    points=np.column_stack((x[ids],y[ids]));travel=np.linalg.norm(points-marker,axis=1)
    # Interior exact-color pixels tolerate positioning better; tied points use
    # the shortest translation. Similar colors respect the original tolerance.
    order=np.lexsort((travel,delta[ids],-margin)) if matched_only else np.lexsort((travel,quality[ids]))
    inverse=np.linalg.inv(c.pose);seen=getattr(c,'single_seen',set())
    for n in order:
        point=points[n];source=point@inverse[:2,:2].T+inverse[:2,2]
        signature=(*np.rint(source*4).astype(int),round(float(np.hypot(c.pose[0,0],c.pose[1,0])),4),
            round(float(np.arctan2(c.pose[1,0],c.pose[0,0])),4))
        if signature in seen:continue
        matrix=c.pose.copy();matrix[:2,2]+=marker-point
        return [dict(matrix=matrix,point=point,source=source,signature=signature,
            region=i,observed_rgb=colors[ids[n]].tolist(),delta=float(delta[ids[n]]),
            match_score=float(quality[ids[n]]),
            margin=float(margin[n]),proposal_only=True)]
    return []


def collect(c):
    c.single_seen=set();c.single_reads=[]
    skip=getattr(c,'single_retry',False);c.single_retry=False
    c.single_force_zoom=skip
    c.single_candidates=[] if skip else candidates(c)
    c.progress('search','单区域寻色：先检查当前画面，找到目标后立即定位。')


def search(c):
    # Import inside the runner to keep the screenshot session's existing
    # deadline/retry exceptions and independent game-HEX verification.
    from screenshot_live import _sampling_check
    from screenshot_search import actual_result
    if not hasattr(c,'single_seen'):collect(c)
    _sampling_check(c)
    nearest=None
    def inspect():
        nonlocal nearest
        _sampling_check(c)
        if not c.relocalize():return False,False
        # Exploration may already put a target beneath the excluded marker.
        # The swatch can request a text read, but can never certify a match.
        if len(c.scene.cards)==len(c.rules) and actual_result(c.preview()['colors'],c.rules)['accepted']:
            if read_match('single-visible-actual',True):return True,True
        rows=candidates(c);c.single_candidates=[]
        close=candidates(c,matched_only=False)
        if close and (nearest is None or close[0]['match_score']<nearest['match_score']):nearest=close[0]
        if not rows:return False,True
        matched=attempt(rows[0])
        return matched,c.relocalize()

    def read_match(label,reuse=False):
        result=c.observe(label,reuse_frame=reuse)
        c.single_reads.append(dict(label=label,colors=result['actual_colors'],deltas=result['actual_deltas']))
        c.write('single-region.json',dict(region=[i for i,r in enumerate(c.rules) if r['enabled']][0],
            observations=c.single_reads,full_palette_collected=False))
        if result['accepted']:
            confirm=c.observe('single-match-confirmation')
            if confirm['accepted']:return True
        return False

    def attempt(row):
        _sampling_check(c)
        cost=c.return_cost(dict(matrix=row['matrix']))
        recovery=c.return_cost(from_matrix=row['matrix'])
        if not c.budget.can_input(cost+recovery+1.5):return False
        c.single_seen.add(row['signature'])
        c.progress('position','单区域寻色：正在定位并核对游戏色码。')
        if not c.move_to(row['matrix'],'single-position',local=True):return False
        if read_match('single-actual',True):return True
        # One-pixel raw targets need subpixel placement. Check a small area
        # around the measured landing, retaining the best actual HEX throughout.
        center=c.pose.copy()
        for shift in ((.25,0),(-.25,0),(0,.25),(0,-.25)):
            _sampling_check(c);desired=center.copy();desired[:2,2]+=shift
            if not c.budget.can_input(c.return_cost(dict(matrix=desired))+
                c.return_cost(from_matrix=desired)+1.5):break
            if not c.move_to(desired,'single-fine',local=True):break
            if read_match('single-fine-actual',True):return True
        # Keep the measured exploration pose. Returning to an early best here
        # resets the scale and repeats the shrink chain after every failed HEX.
        # Each next gesture reserves recovery time; restore once on completion.
        return False

    matched,known=(False,True) if c.single_force_zoom else inspect()
    c.single_force_zoom=False
    if matched or not known:return None
    # Explore progressively at the current scale, then toward the minimum.
    # Every gesture is followed by an immediate target check, never a full scan.
    minimum=False
    while not minimum:
        _sampling_check(c)
        l,t,r,b=c.scene.board;center=np.array([(r-l)/2,(b-t)/2])
        zoom=np.diag([.99**25,.99**25,1.]);zoom[:2,2]=center*(1-.99**25)
        if not c.budget.can_input(1.8+c.return_cost(from_matrix=zoom@c.pose)+1.5):break
        before=c.pose.copy();c.wheel(-25,'single-explore-minimum')
        if not c.relocalize():break
        response=c.pose@np.linalg.inv(before)
        minimum=np.hypot(response[0,0],response[1,0])>.998
        matched,known=inspect()
        if matched or not known:return None
    spacing=float(np.asarray(c.scene.markers)[1,0]-np.asarray(c.scene.markers)[0,0])
    gestures=[('drag',[spacing*.38,0]) for _ in range(4)]
    gestures += [('wheel',20) for _ in range(5)]
    gestures += [('drag',[(r-l)*.2,0]) for _ in range(7)]
    gestures += [('drag',[0,(b-t)*.5])]
    gestures += [('drag',[-(r-l)*.2,0]) for _ in range(7)]
    for kind,value in gestures:
        _sampling_check(c)
        predicted=c.pose.copy()
        if kind=='wheel':
            zoom=np.diag([1.01**value,1.01**value,1.]);zoom[:2,2]=center*(1-1.01**value)
            predicted=zoom@predicted
        else:predicted[:2,2]+=value
        if not c.budget.can_input(1.8+c.return_cost(from_matrix=predicted)+1.5):break
        c.progress('capture','单区域寻色：正在探索新位置，每次移动后立即检查目标。')
        if kind=='wheel':c.wheel(value,'single-explore-zoom')
        else:c.drag(value,'single-explore-view')
        matched,known=inspect()
        if matched or not known:return None
    if nearest is not None:attempt(nearest)
    c.restore()
    return None
