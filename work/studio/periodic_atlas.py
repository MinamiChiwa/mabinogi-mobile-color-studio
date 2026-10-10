"""Offline, phase-aligned periodic RGB maps. No game input or assumed period.

Coordinates: screen = origin + basis @ phase + measured_translation.
Columns of basis are the two measured period vectors. Each material has its
own map in the same phase coordinates; uncovered pixels are never invented.
"""
import numpy as np
import cv2
from vision import lab, rgb


class PeriodicAtlas:
    def __init__(self, basis, origin=(0, 0), resolution=256, regions=3):
        self.basis = np.asarray(basis, dtype=float)
        self.origin = np.asarray(origin, dtype=float)
        if (self.basis.shape != (2, 2) or not np.isfinite(self.basis).all()
                or abs(np.linalg.det(self.basis)) < 1e-6
                or self.origin.shape != (2,) or not np.isfinite(self.origin).all()):
            raise ValueError('A finite, non-degenerate measured period basis is required')
        if not 4 <= resolution <= 1024 or type(regions) is not int or regions not in (2,3):
            raise ValueError('Use 4..1024 samples per period and two or three material regions')
        self.resolution = int(resolution)
        self.regions=regions
        shape = (regions, self.resolution, self.resolution)
        self.count = np.zeros(shape, np.uint32)
        # RGB values are bounded to 0..255 and the atlas only accumulates the
        # current session's frames.  float32 has ample precision here while
        # halving memory traffic in the 768x768 reconstruction.
        self.total = np.zeros((*shape, 3), np.float32)
        # Keep second moments in float64 so diagnostics remain bit-for-bit
        # stable across the native and resampled accumulation paths.
        self.squared = np.zeros((*shape, 3), np.float64)

    def add(self, image, masks, translation=(0, 0)):
        """Accumulate a fixed-scale/angle frame using image-measured translation.

        masks has one boolean mask per material in full image coordinates. The caller must
        exclude UI, circles, lines, cursor, seams and low-confidence alignment.
        Translation is absolute relative to this atlas's reference frame.
        """
        image = np.asarray(image)
        masks = np.asarray(masks, dtype=bool)
        translation = np.asarray(translation, float)
        if image.ndim != 3 or image.shape[2] != 3 or image.dtype != np.uint8:
            raise ValueError('Expected native uint8 RGB image')
        if masks.shape != (self.regions, *image.shape[:2]):
            raise ValueError('Expected one full-image mask per region')
        if translation.shape != (2,) or not np.isfinite(translation).all():
            raise ValueError('Expected finite measured translation')
        inverse = np.linalg.inv(self.basis)
        for region, mask in enumerate(masks):
            y, x = np.where(mask)
            phase = (np.column_stack((x, y)) - self.origin - translation) @ inverse.T
            cells = np.floor(np.mod(phase, 1) * self.resolution).astype(int)
            ix, iy = cells.T
            values = image[y, x].astype(float)
            np.add.at(self.count[region], (iy, ix), 1)
            np.add.at(self.total[region], (iy, ix), values)
            np.add.at(self.squared[region], (iy, ix), values * values)

    def maps(self, max_rmse=8, region=None):
        selection=slice(None) if region is None else region
        count=self.count[selection]
        divisor = np.maximum(count, 1)[..., None]
        mean = self.total[selection] / divisor
        variance = np.maximum(0, self.squared[selection] / divisor - mean * mean)
        rmse = np.sqrt(variance.mean(axis=-1))
        valid = (count > 0) & (rmse <= max_rmse)
        return np.rint(mean).clip(0, 255).astype(np.uint8), valid, rmse

    def add_resampled(self, image, masks, translation=(0, 0)):
        """Inverse-project bin centers, avoiding averaging different subpixels.

        Bilinear sampling requires four valid source pixels in the same material.
        Source resolution remains the upper bound on recovered color detail.
        """
        image=np.asarray(image);masks=np.asarray(masks,bool);translation=np.asarray(translation,float)
        if image.ndim!=3 or image.shape[2]!=3 or image.dtype!=np.uint8:
            raise ValueError('Expected native uint8 RGB image')
        if masks.shape!=(self.regions,*image.shape[:2]) or translation.shape!=(2,) or not np.isfinite(translation).all():
            raise ValueError('Invalid masks or measured translation')
        h,w=image.shape[:2];n=self.resolution
        corners=(np.array([[0,0],[w-1,0],[0,h-1],[w-1,h-1]])-self.origin-translation)@np.linalg.inv(self.basis).T
        low=np.floor(corners.min(axis=0)).astype(int);high=np.floor(corners.max(axis=0)).astype(int)
        if np.prod(high-low+1)>1024:raise ValueError('Period too small for bounded resampling')
        source=image.astype(np.float32)
        for ty in range(low[1],high[1]+1):
            for tx in range(low[0],high[0]+1):
                # Only project cells whose phase rectangle intersects this
                # frame. Padding is conservative for rotated/skewed bases;
                # the original source-pixel mask remains authoritative.
                start=np.clip(np.floor((corners.min(axis=0)-[tx,ty])*n-.5).astype(int)-1,0,n)
                end=np.clip(np.ceil((corners.max(axis=0)-[tx,ty])*n-.5).astype(int)+2,0,n)
                x0,y0=start;x1,y1=end
                if x1<=x0 or y1<=y0:continue
                if self.basis[0,1]==0 and self.basis[1,0]==0:
                    # Live scans use axis-aligned periods. Keep the same
                    # arithmetic but avoid materializing a million 2D phase
                    # vectors for every frame and periodic tile.
                    xpoints=(((np.arange(x0,x1)+.5)/n+tx)*self.basis[0,0]+self.origin[0]+translation[0]).astype(np.float32)
                    ypoints=(((np.arange(y0,y1)+.5)/n+ty)*self.basis[1,1]+self.origin[1]+translation[1]).astype(np.float32)
                    px=np.broadcast_to(xpoints,(y1-y0,x1-x0))
                    py=np.broadcast_to(ypoints[:,None],(y1-y0,x1-x0))
                    ix=np.floor(xpoints).astype(int)[None,:]
                    iy=np.floor(ypoints).astype(int)[:,None]
                else:
                    yy,xx=np.mgrid[y0:y1,x0:x1]
                    phase=np.stack(((xx+.5)/n,(yy+.5)/n),axis=-1)
                    points=(phase+[tx,ty])@self.basis.T+self.origin+translation
                    px,py=points[...,0].astype(np.float32),points[...,1].astype(np.float32)
                    ix=np.floor(px).astype(int);iy=np.floor(py).astype(int)
                inside=(ix>=0)&(iy>=0)&(ix<w-1)&(iy<h-1)
                ix=np.clip(ix,0,w-2);iy=np.clip(iy,0,h-2)
                values=cv2.remap(source,px,py,cv2.INTER_LINEAR)
                for i,mask in enumerate(masks):
                    good=inside&mask[iy,ix]&mask[iy+1,ix]&mask[iy,ix+1]&mask[iy+1,ix+1]
                    if not good.any():
                        continue
                    # Material stripes occupy only part of a projected tile.
                    # Avoid reading/writing the other stripes' moment arrays;
                    # keep exactly the same samples and accumulation order.
                    rows=np.flatnonzero(good.any(axis=1));cols=np.flatnonzero(good.any(axis=0))
                    ya,yb=int(rows[0]),int(rows[-1])+1
                    xa,xb=int(cols[0]),int(cols[-1])+1
                    good=good[ya:yb,xa:xb]
                    # Each tile contributes at most once per atlas cell.
                    # Dense slice arithmetic avoids expensive indexed writes.
                    self.count[i,y0+ya:y0+yb,x0+xa:x0+xb] += good
                    weighted = values[ya:yb,xa:xb] * good[..., None]
                    self.total[i,y0+ya:y0+yb,x0+xa:x0+xb] += weighted
                    self.squared[i,y0+ya:y0+yb,x0+xa:x0+xb] += weighted.astype(np.float64) * weighted

    def sample(self, region, points, translation=(0,0)):
        """Predict RGB at screen points, with a conservative periodic validity mask."""
        colors,valid,_=self.maps(region=region);n=self.resolution
        points=np.asarray(points,float)
        phase=(points-self.origin-np.asarray(translation))@np.linalg.inv(self.basis).T
        coords=np.mod(phase,1)*n-.5
        ix=np.floor(coords[:,0]).astype(int);iy=np.floor(coords[:,1]).astype(int)
        good=(valid[iy%n,ix%n]&valid[(iy+1)%n,ix%n]
              &valid[iy%n,(ix+1)%n]&valid[(iy+1)%n,(ix+1)%n])
        # OpenCV remap limits each output dimension to SHRT_MAX. A native-frame
        # sample list or an exhaustive phase search can contain millions of points.
        source=colors.astype(np.float32)
        values=np.empty((len(coords),3),np.float32)
        for start in range(0,len(coords),16384):
            part=coords[start:start+16384]
            values[start:start+len(part)]=cv2.remap(source,part[:,0,None].astype(np.float32),
                         part[:,1,None].astype(np.float32),cv2.INTER_LINEAR,borderMode=cv2.BORDER_WRAP).reshape(-1,3)
        return values,good

    def report(self):
        _, valid, rmse = self.maps()
        return [dict(region=i + 1, coverage=float(valid[i].mean()),
                     observed=float((self.count[i] > 0).mean()),
                     overlap_rmse=float(rmse[i][self.count[i] > 1].mean())
                     if (self.count[i] > 1).any() else None) for i in range(self.regions)]

    def snapshot(self):
        """Prepare immutable maps once after accumulation for this session.

        A snapshot owns its arrays. Further mutable atlas additions cannot
        silently change it, and it is never an implicit cross-session cache.
        """
        return AtlasSnapshot(self)


class AtlasSnapshot:
    """Read-only sampling view; numerically identical to the source maps."""
    def __init__(self, atlas):
        self.basis=atlas.basis.copy();self.origin=atlas.origin.copy()
        self.resolution=atlas.resolution;self.count=atlas.count.copy();self.regions=atlas.regions
        self.colors,self.valid,self.rmse=atlas.maps()
        for value in (self.basis,self.origin,self.count,self.colors,self.valid,self.rmse):
            value.flags.writeable=False

    def maps(self,max_rmse=8,region=None):
        selection=slice(None) if region is None else region
        valid=self.valid if max_rmse==8 else (self.count>0)&(self.rmse<=max_rmse)
        return self.colors[selection],valid[selection],self.rmse[selection]

    sample=PeriodicAtlas.sample
    report=PeriodicAtlas.report


def _equivalent_moves(relative, basis, current_translation, radius=1,
                      max_distance=None):
    """Return an unfolded representative for every periodic phase.

    ``relative`` is the phase displacement in the fundamental cell.  A phase
    has infinitely many equivalent screen displacements; keeping those
    representatives explicit lets the caller choose a farther cycle when its
    execution constraints or scoring policy require it.
    """
    current = np.asarray(current_translation, float)
    choices = []
    for ox in range(-int(radius), int(radius) + 1):
        for oy in range(-int(radius), int(radius) + 1):
            choices.append((relative + [ox, oy]) @ basis.T)
    moves = np.stack(choices, axis=0)  # cycles, candidates, xy
    distance = np.linalg.norm(moves, axis=2)
    if max_distance is not None:
        distance = np.where(distance <= float(max_distance), distance, np.inf)
    # Select the shortest admissible representative.  Ties are deterministic.
    index = np.argmin(distance, axis=0)
    return moves[index, np.arange(len(relative))], distance[index, np.arange(len(relative))]


def _ranking_subset(predictions, enabled, ids, priorities, limit):
    """Discard worse priority tiers only when the best has enough colours.

    This preserves the full lexicographic top distinct-colour results. A
    bounded probe only decides whether this optimization is possible: if it
    cannot prove there are enough unique combinations, keep the wider pool.
    The colour samples, validity and landing neighbourhoods are unchanged.
    """
    for metric in priorities:
        if len(ids)<=limit:break
        values=metric[ids]
        best=ids[values==values.min()]
        def enough(pool):
            distinct=set()
            for index in pool[:1024]:
                distinct.add(b''.join(predictions[i][index].tobytes() for i in enabled))
                if len(distinct)>=limit:return True
            return False
        if len(best)>=limit and enough(best):
            ids=best
            continue
        # A continuous risk score rarely has 32 identical best values. Keep
        # a proven sufficient prefix instead of sorting the entire screen
        # lattice. Include every cutoff tie; a sample only proves that enough
        # distinct colors remain, never decides which final rows to publish.
        if len(ids)>1024:
            cutoff=np.partition(values,1023)[1023]
            prefix=ids[values<=cutoff]
            if len(prefix)<len(ids) and enough(prefix):ids=prefix
        break
    return ids


def translation_candidates(atlas, markers, rules, current_translation=(0, 0),
                           limit=8, cancelled=lambda: False, cycle_radius=1,
                           max_move=None, landing_radius=0., integer_moves=False):
    """Search fixed scale/angle, using actual integer moves when requested.

    Returns screenshot predictions (Delta E 76), never verified game HEX.
    All markers share one phase offset. Missing/conflicting pixels invalidate
    the whole combination. Precision is limited by atlas sampling resolution.
    """
    markers = np.asarray(markers, float)
    current = np.asarray(current_translation, float)
    regions=len(rules)
    if (regions not in (2,3) or markers.shape != (regions,2) or not np.isfinite(markers).all()
            or getattr(atlas,'regions',regions)!=regions):
        raise ValueError('Atlas, markers and rules must have matching two or three regions')
    if current.shape != (2,) or not np.isfinite(current).all() or not 1 <= limit <= 100:
        raise ValueError('Invalid current translation or result limit')
    if not np.isfinite(landing_radius) or landing_radius < 0:
        raise ValueError('Landing radius must be finite and nonnegative')
    enabled = [i for i, rule in enumerate(rules) if rule['enabled']]
    if not enabled:
        return []
    n = atlas.resolution
    inverse = np.linalg.inv(atlas.basis)
    if integer_moves:
        # Enumerating atlas phase bins then rounding skipped integer mouse
        # positions whenever a measured period exceeded atlas resolution.
        # Sample the screen lattice directly in a centered fundamental cell.
        # Padding is sampled too, so boundary landing checks do not assume
        # that a noninteger texture period equals an integer grid wrap.
        pad=int(np.ceil(landing_radius))
        corners=np.array([[-.5,-.5],[-.5,.5],[.5,-.5],[.5,.5]])@atlas.basis.T
        low=np.floor(corners.min(axis=0)).astype(int)-pad
        high=np.ceil(corners.max(axis=0)).astype(int)+pad
        yy,xx=np.mgrid[low[1]:high[1]+1,low[0]:high[0]+1]
        grid_shape=xx.shape
        moves=np.column_stack((xx.ravel(),yy.ravel()))
        relative=moves@inverse.T
        candidate_mask=((relative>=-.5)&(relative<.5)).all(axis=1)
        distance=np.linalg.norm(moves,axis=1)
        if max_move is not None:candidate_mask&=distance<=max_move
        sample_shifts=current+moves
        shifts=np.mod(sample_shifts@inverse.T,1.)
    else:
        yy, xx = np.mgrid[:n, :n]
        grid_shape=(n,n)
        shifts = np.column_stack((xx.ravel(), yy.ravel())) / n
        current_phase = current @ inverse.T
        relative = (shifts-current_phase+.5) % 1-.5
        moves, distance = _equivalent_moves(relative, atlas.basis, current,
                                             radius=cycle_radius,
                                             max_distance=max_move)
        sample_shifts=shifts@atlas.basis.T
        candidate_mask=np.isfinite(distance)
    count=len(moves)
    predictions = []; deltas = []; passes = []; usable = np.ones(count, bool)
    for i in range(regions):
        if cancelled():
            raise InterruptedError('Calculation cancelled')
        sampled, supported = atlas.sample(i,markers[i]-sample_shifts)
        values = np.rint(sampled).clip(0,255).astype(np.uint8)
        predictions.append(values)
        if i not in enabled:
            deltas.append(None); passes.append(None); continue
        usable &= supported
        targets = np.array([rgb(c) for c in rules[i]['colors']])
        if not len(targets):
            raise ValueError('An enabled region needs a target color')
        distances = np.full(count, np.inf)
        exact = np.zeros(count, bool)
        values_lab = lab(values)
        for target, target_lab in zip(targets, lab(targets)):
            distances = np.minimum(distances, np.linalg.norm(values_lab-target_lab, axis=1))
            exact |= (values == target).all(axis=1)
        deltas.append(distances)
        passes.append(exact if rules[i]['exact'] else distances <= rules[i]['tolerance'])
    maximum = np.maximum.reduce([deltas[i] for i in enabled])
    average = np.mean([deltas[i] for i in enabled], axis=0)
    passed = np.logical_and.reduce([passes[i] for i in enabled])
    # Prefer an island of acceptable colors over a narrow stripe with a
    # slightly lower center error. Wrap morphology at the atlas period seam.
    # This is a sampled prediction neighborhood, never game HEX verification.
    stable = np.zeros(len(passed), bool)
    neighborhood_maximum = maximum.copy()
    if landing_radius:
        if not integer_moves:
            pad=int(np.ceil(n*landing_radius*np.abs(inverse).sum(axis=1).max()))
            if pad > n:
                raise ValueError('Landing neighborhood exceeds one atlas period')
        kernel=np.ones((2*pad+1,2*pad+1),np.uint8)
        field=np.where(usable,maximum,np.inf).reshape(grid_shape).astype(np.float32)
        accepted_mask=(passed&usable).reshape(grid_shape).astype(np.uint8)
        if integer_moves:
            neighborhood_maximum=cv2.dilate(field,kernel,borderType=cv2.BORDER_CONSTANT,
                                            borderValue=float('inf')).ravel()
            stable=cv2.erode(accepted_mask,kernel,borderType=cv2.BORDER_CONSTANT,
                             borderValue=0).ravel().astype(bool)
        else:
            padded=cv2.copyMakeBorder(field,pad,pad,pad,pad,cv2.BORDER_WRAP)
            neighborhood_maximum=cv2.dilate(padded,kernel)[pad:-pad,pad:-pad].ravel()
            padded=cv2.copyMakeBorder(accepted_mask,pad,pad,pad,pad,cv2.BORDER_WRAP)
            stable=cv2.erode(padded,kernel)[pad:-pad,pad:-pad].ravel().astype(bool)
    risk=np.maximum(neighborhood_maximum,maximum)
    from candidate_ranking import candidate_order,exact_priority,exact_fields
    from color_family import family_priority,family_fields
    hits,exact_max,exact_avg,exact_total=exact_priority(predictions,deltas,rules)
    family_max,family_avg,family_losses=family_priority(predictions,rules)
    from region_priority import vector_priority_components, priority_fields
    priority=vector_priority_components(predictions,deltas,rules)
    priority_metrics=() if priority is None else tuple(priority[:,i] for i in range(priority.shape[1]))
    ids=_ranking_subset(predictions,enabled,np.flatnonzero(usable&candidate_mask),
                        (~(passed&stable) if landing_radius else ~passed,*priority_metrics,risk,maximum,average,-hits,exact_max,exact_avg,
                         family_max,family_avg),limit)
    order=ids[candidate_order(hits[ids],maximum[ids],average[ids],passed[ids],stable[ids],
                          neighborhood_maximum[ids],distance[ids],
                          exact_maximum=exact_max[ids],exact_average=exact_avg[ids],
                           family_maximum=family_max[ids],family_average=family_avg[ids],
                           neighborhood_present=bool(landing_radius),candidate_ids=ids,
                           region_priority=None if priority is None else priority[ids])]
    result = []; seen = set()
    for index in order:
        if cancelled():
            raise InterruptedError('Calculation cancelled')
        if not usable[index] or not np.isfinite(distance[index]):
            continue
        hexes = ['#%02X%02X%02X' % tuple(predictions[i][index]) if i in enabled else None for i in range(regions)]
        key = tuple(hexes)
        if key in seen:
            continue
        seen.add(key)
        result.append(dict(id=len(result), predicted=True, verified=False,
                           colors=hexes, deltas=[float(deltas[i][index]) if i in enabled else None for i in range(regions)],
                           maximum=float(maximum[index]), average=float(average[index]),
                           accepted=bool(passed[index]), phase=shifts[index].tolist(),
                           dx=float(moves[index, 0]), dy=float(moves[index, 1]), angle=0., scale=1.))
        if landing_radius:
            result[-1].update(landing_radius=float(landing_radius),
                             landing_safe=bool(stable[index]),
                             landing_maximum=(float(neighborhood_maximum[index])
                                              if np.isfinite(neighborhood_maximum[index]) else None))
        result[-1].update(exact_fields(hits,exact_max,exact_avg,exact_total,index))
        result[-1].update(family_fields(family_max,family_avg,family_losses,index))
        result[-1].update(priority_fields(hexes,result[-1]['deltas'],rules))
        if len(result) >= limit:
            break
    return result
