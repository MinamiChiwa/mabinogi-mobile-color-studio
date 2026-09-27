"""Runtime image registration and game adapter for the formal atlas flow."""
import cv2
import numpy as np
from atlas_execution import Context, checked_translation
from atlas_masks import board_texture_mask, material_masks
from vision import read_codes


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
    actual = cv2.remap(b[t:bottom, l:r].astype(np.float32),
                       px[good_points, None].astype(np.float32),
                       py[good_points, None].astype(np.float32), cv2.INTER_LINEAR).reshape(-1, 3)
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

    def check(self):
        self.g.check()

    def context(self):
        return Context(self.session, tuple(self.g.geometry()), tuple(self.scene.board),
                       tuple(map(tuple, self.scene.markers)))

    def capture(self):
        self.last_frame=self.g.capture()
        return self.last_frame

    def motion(self, before, after):
        self.last_motion_before, self.last_motion_after = before, after
        self.last_motion_diagnostics = {}
        return motion(before, after, self.scene, self.last_motion_diagnostics)

    def drag(self, dx, dy):
        self.g.drag(self.scene.board, dx, dy)
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
        self.g.pause(seconds)

    def read_codes(self, image):
        return read_codes(image, self.scene.cards, self.scene.markers)

    def release(self):
        try:self.g.send(4)
        finally:self.g.send(16)
