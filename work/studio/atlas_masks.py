"""Shared board-material masks for atlas reconstruction and registration.

    The game draws a white colour-pick card, a connector stem and a translucent
halo above each pick point.  The halo is not reliably separable by RGB, so the
formal atlas path uses geometry-based exclusion with the same conservative
width for accumulation, validation and registration.
"""
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


def _field(scene, name):
    return scene[name] if isinstance(scene, dict) else getattr(scene, name)


def board_markers(scene):
    """Return marker coordinates in the local board-crop coordinate system."""
    left, top, right, bottom = map(int, _field(scene, 'board'))
    markers = np.asarray(_field(scene, 'markers'), dtype=float) - (left, top)
    if markers.shape != (3, 2) or not np.isfinite(markers).all():
        raise ValueError("Expected three finite colour-pick markers")
    spacing = float(markers[1, 0] - markers[0, 0])
    if spacing <= 0:
        raise ValueError("Colour-pick markers must be ordered left to right")
    return markers, spacing, (right - left, bottom - top)


def board_texture_mask(scene, *, stem_half_width=None, ring_radius=None,
                       edge_margin=None, seam_half_width=None):
    """Return valid texture pixels in board-local coordinates.

    The default corridor spans the full board height and the full 18-pixel
    marker radius at spacing 166. Thus a change in marker height cannot expose
    the ring flanks or change coverage. Explicit narrower corridors remain
    available for replaying historical masks; ring exclusion still applies.
    All dimensions are geometry-only, independent of sampled colours.
    """
    markers, spacing, (w, h) = board_markers(scene)
    y, x = np.mgrid[:h, :w]
    unit = spacing / 166.
    radius = max(1, round(18 * unit)) if ring_radius is None else int(ring_radius)
    half = max(max(1, round(18 * unit)), radius) if stem_half_width is None else int(stem_half_width)
    edge_margin = max(1, round(8 * unit)) if edge_margin is None else int(edge_margin)
    seam_half_width = max(1, round(8 * unit)) if seam_half_width is None else int(seam_half_width)
    if half < 1 or radius < 1 or edge_margin < 0 or seam_half_width < 0:
        raise ValueError("Mask dimensions must be positive")
    mask = (x >= edge_margin) & (x < w - edge_margin)
    mask &= (y >= edge_margin) & (y < h - edge_margin)
    for mx, my in markers:
        # The connector can appear at any vertical position in a later frame.
        # Keep the whole conservative vertical corridor, including its halo.
        mask &= ~(np.abs(x - mx) <= half)
        mask &= ((x - mx) ** 2 + (y - my) ** 2 > radius ** 2)
    cards = scene.get('cards', []) if isinstance(scene, dict) else getattr(scene, 'cards', [])
    left, top, _, _ = _field(scene, 'board')
    for cx, cy, cw, ch in cards:
        # Include the card body and its soft outer extension, even if future
        # layouts place part of a card inside the recognized board crop.
        pad = max(1, round(cw * .3))
        mask &= ~((x >= cx-left-pad) & (x <= cx-left+cw+pad)
                  & (y >= cy-top-pad) & (y <= cy-top+ch+pad))
    # The two internal material seams are also UI/edge pixels and can create
    # false matches when a frame is shifted across a period boundary.
    for border in (markers[:-1, 0] + markers[1:, 0]) / 2:
        mask &= np.abs(x - border) > seam_half_width
    return mask


def material_masks(scene, *, stem_half_width=None, ring_radius=None,
                   edge_margin=None, seam_half_width=None, side_margin=None):
    """Return three same-material masks using the shared texture exclusion."""
    markers, spacing, _ = board_markers(scene)
    side_margin = max(1, round(8 * spacing / 166)) if side_margin is None else int(side_margin)
    clean = board_texture_mask(scene, stem_half_width=stem_half_width,
                               ring_radius=ring_radius, edge_margin=edge_margin,
                               seam_half_width=seam_half_width)
    _, _, (w, h) = board_markers(scene)
    y, x = np.mgrid[:h, :w]
    masks=[]
    for mx, my in markers:
        masks.append(clean & (x > mx - spacing / 2 + side_margin)
                     & (x < mx + spacing / 2 - side_margin))
    return np.asarray(masks, dtype=bool)


def save_mask_overlay(image, masks, path):
    """Save a review image with excluded pixels tinted red and region edges."""
    base = np.asarray(image).copy()
    masks = np.asarray(masks, dtype=bool)
    if base.ndim != 3 or base.shape[2] != 3 or masks.shape[1:] != base.shape[:2]:
        raise ValueError("Image and board-local masks must have matching shapes")
    # A neutral red tint makes the excluded connectors visible over any dye.
    valid = masks.any(axis=0)
    overlay = base.astype(np.float32)
    excluded = ~valid
    overlay[excluded] = overlay[excluded] * .35 + np.array([210, 35, 35]) * .65
    output = Image.fromarray(np.rint(overlay).clip(0, 255).astype(np.uint8))
    draw = ImageDraw.Draw(output)
    colors=((60,220,90),(60,160,255),(220,180,40))
    for mask, color in zip(masks, colors):
        # Draw a one-pixel boundary around each material mask for visual QA.
        boundary = mask ^ np.pad(mask[1:, :], ((0, 1), (0, 0)))
        yy, xx = np.where(boundary)
        if len(xx):
            draw.point(list(zip(xx.tolist(), yy.tolist())), fill=color)
    output.save(Path(path))


def mask_summary(masks):
    masks = np.asarray(masks, dtype=bool)
    if masks.ndim != 3:
        raise ValueError("Expected three material masks")
    return [dict(region=i + 1, valid_pixels=int(row.sum()),
                 coverage=float(row.mean())) for i, row in enumerate(masks)]


def mask_parameters():
    """Return the geometry parameters in a JSON-friendly diagnostic record."""
    return dict(version=3, reference_marker_spacing=166, stem_half_width=18,
                ring_radius=18, edge_margin=8, seam_half_width=8, side_margin=8,
                full_height_connector_columns=True, scaled_with_marker_spacing=True,
                card_padding_fraction=.3)
