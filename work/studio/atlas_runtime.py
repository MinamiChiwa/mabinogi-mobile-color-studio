"""Runtime image registration and game adapter for the formal atlas flow."""
import cv2
import numpy as np
import time
from contextlib import contextmanager, nullcontext
from atlas_execution import Context, checked_translation
from atlas_stage_budget import StageBudgetExceeded
from atlas_masks import board_texture_mask, material_masks
from vision import read_codes


# OpenCV's remap implementation stores the output dimensions in a signed
# 16-bit value.  A dense material check on a high-resolution board can easily
# produce more than 32,767 point samples, even though the source frame itself
# is a normal 1280x960/2560x1440 image.  Keep each remap call below that native
# limit and concatenate the point results in their original order.
_REMAP_POINT_CHUNK = 16_384


def _remap_points(source, px, py, chunk_size=_REMAP_POINT_CHUNK):
    """Bilinearly sample arbitrary points without hitting OpenCV's size limit."""
    px = np.asarray(px, dtype=np.float32).reshape(-1)
    py = np.asarray(py, dtype=np.float32).reshape(-1)
    if px.shape != py.shape:
        raise ValueError('Point coordinate arrays must have the same length')
    if chunk_size <= 0 or chunk_size >= 32_767:
        raise ValueError('Point chunk size must stay below OpenCV remap limit')
    if not len(px):
        return np.empty((0, source.shape[2]), dtype=np.float32)
    parts = []
    for start in range(0, len(px), chunk_size):
        stop = start + chunk_size
        values = cv2.remap(source, px[start:stop, None], py[start:stop, None],
                           cv2.INTER_LINEAR)
        parts.append(values.reshape(-1, source.shape[2]))
    return np.concatenate(parts, axis=0)


def texture_mask(scene, shape):
    l, t, r, b = map(int, scene.board)
    expected = (b - t, r - l)
    full_shape = tuple(shape[:2])
    if full_shape != expected and (full_shape[0] < b or full_shape[1] < r):
        raise ValueError('Texture mask shape must match the board crop')
    return board_texture_mask(scene).astype(np.uint8) * 255


def _feature_registration(gray_a, gray_b, mask, contrast, diagnostics):
    detector = cv2.SIFT_create(nfeatures=2400, contrastThreshold=contrast)
    ka, da = detector.detectAndCompute(gray_a, mask)
    kb, db = detector.detectAndCompute(gray_b, mask)
    diagnostics.update(contrast_threshold=contrast, features_before=len(ka), features_after=len(kb))
    if da is None or db is None or len(db) < 2:
        diagnostics['reason'] = 'insufficient_features'
        return None
    pairs = cv2.BFMatcher().knnMatch(da, db, k=2)
    good = [p[0] for p in pairs if len(p) == 2 and p[0].distance < .7 * p[1].distance]
    diagnostics['matches'] = len(good)
    if len(good) < 20:
        diagnostics['reason'] = 'insufficient_matches'
        return None
    matrix, inliers = cv2.estimateAffinePartial2D(
        np.float32([ka[m.queryIdx].pt for m in good]),
        np.float32([kb[m.trainIdx].pt for m in good]), method=cv2.RANSAC,
        ransacReprojThreshold=1.5)
    if matrix is None or inliers is None or not np.isfinite(matrix).all():
        diagnostics['reason'] = 'invalid_transform'
        return None
    diagnostics.update(matrix=matrix.tolist(), inliers=int(inliers.sum()),
                       inlier_ratio=float(inliers.mean()))
    if inliers.sum() < 40 or inliers.mean() < .3:
        diagnostics['reason'] = 'insufficient_inliers'
        return None
    diagnostics['reason'] = 'ok'
    return matrix, int(inliers.sum())


def motion(a, b, scene, diagnostics=None):
    """Measure existing frames; a denser feature retry never sends game input.

    Retry only a failed geometric estimate. Both attempts use the same match,
    RANSAC and inlier gates, followed by the same per-material RGB checks.
    """
    diagnostics = {} if diagnostics is None else diagnostics
    diagnostics.clear()
    diagnostics.update(passed=False, attempts=[])
    l, t, r, bottom = scene.board
    mask = texture_mask(scene, a.shape)
    gray_a = cv2.cvtColor(a[t:bottom, l:r], cv2.COLOR_RGB2GRAY)
    gray_b = cv2.cvtColor(b[t:bottom, l:r], cv2.COLOR_RGB2GRAY)
    registration = None
    for contrast in (.04, .01):
        attempt = {}
        diagnostics['attempts'].append(attempt)
        registration = _feature_registration(gray_a, gray_b, mask, contrast, attempt)
        if registration is not None:
            break
    if registration is None:
        diagnostics['reason'] = attempt['reason']
        return None
    matrix, inliers = registration
    # Material boundaries stay fixed on screen while texture moves. Crossing
    # into a different material changes RGB even for a correct registration.
    # Check all four bilinear source pixels against the SAME material label.
    materials = material_masks(scene)
    labels = np.zeros(mask.shape, np.uint8)
    for region, region_mask in enumerate(materials, 1):
        labels[region_mask] = region
    yy, xx = np.where(labels[::4, ::4] > 0)
    xx, yy = xx * 4, yy * 4
    points = np.column_stack((xx, yy)) @ matrix[:, :2].T + matrix[:, 2]
    px, py = points.T
    w, h = r - l, bottom - t
    good_points = (px > 0) & (px < w - 1) & (py > 0) & (py < h - 1)
    ix = np.clip(np.floor(px).astype(int), 0, w-2)
    iy = np.clip(np.floor(py).astype(int), 0, h-2)
    source_labels = labels[yy, xx]
    for ox, oy in ((0,0),(1,0),(0,1),(1,1)):
        good_points &= labels[iy+oy, ix+ox] == source_labels
    diagnostics['same_material_samples'] = int(good_points.sum())
    if good_points.sum() < 200:
        diagnostics['reason'] = 'insufficient_material_overlap'
        return None
    actual = _remap_points(b[t:bottom, l:r].astype(np.float32),
                           px[good_points], py[good_points])
    squared = (actual - a[t + yy[good_points], l + xx[good_points]]) ** 2
    rgb_rmse = float(np.sqrt(np.mean(squared)))
    region_rmse = []
    region_samples = []
    for region in range(1, 4):
        samples = source_labels[good_points] == region
        region_samples.append(int(samples.sum()))
        region_rmse.append(float(np.sqrt(np.mean(squared[samples]))) if samples.any() else None)
    diagnostics.update(rgb_rmse=rgb_rmse, region_rgb_rmse=region_rmse,
                       region_samples=region_samples)
    if min(region_samples) < 32:
        diagnostics['reason'] = 'insufficient_region_overlap'
        return None
    if not np.isfinite([rgb_rmse, *region_rmse]).all() or max(region_rmse) > 10:
        diagnostics['reason'] = 'material_rgb_mismatch'
        return None
    diagnostics.update(passed=True, reason='ok')
    return dict(matrix=matrix.tolist(),
                angle=float(np.degrees(np.arctan2(matrix[1, 0], matrix[0, 0]))),
                scale=float(np.hypot(matrix[0, 0], matrix[1, 0])),
                inliers=inliers, rgb_rmse=rgb_rmse, contrast_threshold=contrast,
                region_rgb_rmse=region_rmse, same_material_samples=int(good_points.sum()))


class Adapter:
    def __init__(self, game, scene, session):
        self.g, self.scene, self.session = game, scene, session
        self.last_motion_diagnostics = None
        self.last_motion_before = self.last_motion_after = None
        self._code_cache = {}
        self._stage_budget = None
        self.code_read_stats = dict(calls=0,ocr_passes=0,ocr_cards=0,reused_cards=0,seconds=0.)

    def check(self):
        self.g.check()

    def check_positioning(self):
        self.check()
        if self._stage_budget is not None:self._stage_budget.check_input()

    def check_observation(self):
        if self._stage_budget is not None:
            self.check()
            self._stage_budget.check_observation()

    @contextmanager
    def execution_scope(self,budget):
        previous=self._stage_budget
        self._stage_budget=budget
        try:yield
        finally:self._stage_budget=previous

    def context(self):
        return Context(self.session, tuple(self.g.geometry()), tuple(self.scene.board),
                       tuple(map(tuple, self.scene.markers)))

    def capture(self):
        self.check_observation()
        self.last_frame=self.g.capture()
        return self.last_frame

    def motion(self, before, after):
        self.check_observation()
        self.last_motion_before, self.last_motion_after = before, after
        self.last_motion_diagnostics = {}
        measured=motion(before, after, self.scene, self.last_motion_diagnostics)
        try:self.check_observation()
        except StageBudgetExceeded:
            # The pair is already registered and there has been no further
            # input. Deliver it so execution can retain the measured pose;
            # its next stage check prevents additional input or OCR work.
            if measured is None:raise
            self.last_motion_diagnostics['observation_deadline_reached']=True
        return measured

    def drag(self, dx, dy):
        self.g.drag(self.scene.board, dx, dy)
        self.park()

    def perform_gesture(self, gesture):
        self.check_positioning()
        scope=(self.g.input_scope(self._stage_budget.input_deadline,self.check_positioning,
                                 expiry_factory=StageBudgetExceeded)
               if self._stage_budget is not None else nullcontext())
        with scope:
            self.g.perform_gesture(gesture)
            self.park()

    def rotate(self, angle, anchor):
        self.g.rotate(self.scene.board, angle, anchor=anchor)
        self.park()

    def wheel(self, steps, anchor):
        self.g.wheel(self.scene.board, steps, anchor=anchor)
        self.park()

    def park(self):
        self.g.move_to((int(self.g.initial[2] * .5), int(self.g.initial[3] * .15)))

    def pause(self, seconds):
        self.check_observation()
        if self._stage_budget is not None and not self._stage_budget.can_observe(seconds):
            raise StageBudgetExceeded('Observation wait would consume the return reserve')
        self.g.pause(seconds)

    def read_codes(self, image):
        # Reuse only a successfully validated HEX for an identical FULL card,
        # including both text and swatch. Capturing the second frame, waiting,
        # and registering the board remain the executor's responsibility.
        # No approximate image hash, old pose, or predicted colour is used.
        self.check_observation()
        started=time.perf_counter()
        enabled=getattr(self,'enabled',None)
        if enabled is None:enabled=[True]*len(self.scene.cards)
        needed=[False]*len(self.scene.cards);result=[None]*len(self.scene.cards)
        cards={};reused=0
        for index,(x,y,w,h) in enumerate(self.scene.cards):
            if not enabled[index]:continue
            pixels=image[y:y+h,x:x+w]
            geometry=(tuple(image.shape),str(image.dtype),(x,y,w,h),bool(self.scene.markers))
            complete=pixels.shape==(h,w,3) and w>0 and h>0
            cached=self._code_cache.get(index)
            if complete and cached is not None and cached[0]==geometry and np.array_equal(pixels,cached[1]):
                result[index]=cached[2];reused+=1
            else:
                needed[index]=True
                cards[index]=(geometry,pixels,complete)
        if any(needed):
            options=({} if self._stage_budget is None else dict(
                deadline=self._stage_budget.observation_deadline,
                clock=self._stage_budget.clock,check=self.check))
            try:fresh=read_codes(image,self.scene.cards,self.scene.markers,enabled=needed,**options)
            except TimeoutError as exc:
                if self._stage_budget is None:raise
                raise StageBudgetExceeded(str(exc)) from exc
            for index,(geometry,pixels,complete) in cards.items():
                result[index]=fresh[index]
                if fresh[index] is not None and complete:
                    self._code_cache[index]=(geometry,pixels.copy(),fresh[index])
                else:self._code_cache.pop(index,None)
            self.code_read_stats['ocr_passes']+=1
        self.code_read_stats['calls']+=1
        self.code_read_stats['ocr_cards']+=sum(needed)
        self.code_read_stats['reused_cards']+=reused
        self.code_read_stats['seconds']+=time.perf_counter()-started
        return result

    def release(self):
        try:self.g.send(4)
        finally:self.g.send(16)
