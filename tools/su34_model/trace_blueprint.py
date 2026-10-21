"""
Trace the reference drawings into machine-readable curves.

The source is `docs/refs/bp-1-three-views.png` (the user's blueprint sheet:
top view, side view and front view of the Su-34 on one page).  This script
finds the silhouette of every view, calibrates it against the known real
dimensions and writes `tools/su34_model/blueprint_data.py`, which the model
generator imports.  Nothing here is upstream geometry - it is only the
outline of a line drawing, used as a dimension table.

Calibration
-----------
* the sheet is a single-scale drawing: 1 px = 0.05 m (checked on the top view
  span 14.7 m = 294 px and on the side view length 23.3 m = 466 px),
* top view  : z grows towards the nose  (+z = nose), the centreline is the row
  where the radome tip sits,
* side view : z grows towards the nose, y = 0 is the lowest point of the
  fuselage belly (the real aircraft sits ~6.09 - 4.7 = 1.35 m above ground),
* front view: used only to check widths and the fin cant.

Run:  python3 tools/su34_model/trace_blueprint.py
Out:  tools/su34_model/blueprint_data.py
      docs/model/blueprint_trace.png   (overlay of the traced curves)
"""
from __future__ import annotations

import math
import os

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from skimage import measure

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
REF = os.path.join(ROOT, "docs", "refs", "bp-1-three-views.png")
OUT_PY = os.path.join(HERE, "blueprint_data.py")
OUT_PNG = os.path.join(ROOT, "docs", "model", "blueprint_trace.png")

# ---- view windows in pixels (x0, x1, y0, y1) ------------------------------
TOP_BOX = (0, 500, 5, 315)
SIDE_BOX = (90, 600, 250, 360)
FRONT_BOX = (270, 490, 85, 180)

LENGTH = 23.3      # m, radome tip to tail cone tip (no pitot boom)
SPAN = 14.7        # m, wingtip to wingtip


def mask(box):
    a = np.asarray(Image.open(REF).convert("L"))
    x0, x1, y0, y1 = box
    m = np.zeros_like(a, bool)
    m[y0:y1, x0:x1] = a[y0:y1, x0:x1] < 205
    return ndimage.binary_closing(m, np.ones((2, 2)))


def main_component(m):
    lab, n = ndimage.label(m, np.ones((3, 3)))
    if n == 0:
        raise SystemExit("no ink found in the view window")
    sizes = ndimage.sum(m, lab, range(1, n + 1))
    idx = int(np.argmax(sizes)) + 1
    return ndimage.binary_fill_holes(lab == idx)


def trace_top():
    sil = main_component(mask(TOP_BOX))
    ys, xs = np.where(sil)
    # the pitot boom is the 1-px trail in front of the radome: cut it off
    x_tip = xs.max()
    cols = [np.count_nonzero(sil[:, x]) for x in range(xs.min(), xs.max() + 1)]
    thin = [x for x, c in zip(range(xs.min(), xs.max() + 1), cols) if c <= 2]
    if thin:
        nose = [x for x in thin if x > xs.max() - 40]
        if nose:
            x_tip = min(nose) - 1
    x_tail = xs.min()
    scale = LENGTH / (x_tip - x_tail)          # m per px along z
    row_c = 0.5 * (ys.min() + ys.max())        # centreline between the tips
    cont = max(measure.find_contours(sil.astype(float), 0.5), key=len)
    poly = measure.approximate_polygon(cont, tolerance=1.5)
    pts = [((x - x_tail) * scale - LENGTH / 2.0, (r - row_c) * scale)
           for r, x in poly]                    # (z, span) in metres
    hit = np.zeros(sil.shape, bool)
    for x in range(x_tail, x_tip + 1):
        col = np.where(sil[:, x])[0]
        if len(col):
            hit[col.min(), x] = hit[col.max(), x] = True
    return dict(scale=scale, x_tail=x_tail, row_c=row_c, poly=pts, sil=sil,
                hit=hit, x_tip=x_tip)


def trace_side(top):
    m = mask(SIDE_BOX)
    lab, n = ndimage.label(m, np.ones((3, 3)))
    sizes = ndimage.sum(m, lab, range(1, n + 1))
    sil = ndimage.binary_fill_holes(lab == int(np.argmax(sizes)) + 1)
    ys, xs = np.where(sil)
    x0, x1 = xs.min(), xs.max()
    # the sheet draws a long horizontal reference line through the profile;
    # drop 1..3 px thick runs sitting on it so they do not poison the belly
    for y in range(330, 352):
        band = sil[y]
        if band.sum() > 0.6 * band.size:
            for x in range(x0, x1 + 1):
                if sil[y, x] and (not sil[y - 1, x] and not sil[y + 1, x]):
                    sil[y, x] = False
    sil = ndimage.binary_closing(sil, np.ones((3, 3)))
    ys, xs = np.where(sil)
    # the side view is drawn nose-left.  The pitot boom sticks out ahead of
    # the radome as a 1-2 px line, so the ends are taken where the profile
    # actually gains thickness; both views share one scale (checked on the
    # top view span), and the length is pinned to 23.3 m.
    heavy = [x for x in range(xs.min(), xs.max() + 1) if np.count_nonzero(sil[:, x]) >= 4]
    x_nose, x_tail = min(heavy), max(heavy)
    scale = LENGTH / (x_tail - x_nose)
    y_floor = int(np.percentile(ys, 99.5))
    top_line, bot_line = {}, {}
    for x in range(x_nose, x_tail + 1):
        col = np.where(sil[:, x])[0]
        if not len(col):
            continue
        z = (x_tail - x) * scale - LENGTH / 2.0   # +z = nose
        top_line[z] = (y_floor - col.min()) * scale
        bot_line[z] = (y_floor - col.max()) * scale
    y_belly = min(bot_line.values())
    top_line = {z: y - y_belly for z, y in top_line.items()}
    bot_line = {z: y - y_belly for z, y in bot_line.items()}
    return dict(scale=scale, x_lo=x_nose, x_hi=x_tail, y_floor=y_floor,
                top=top_line, bot=bot_line, sil=sil), top


def sample(pairs, step=0.1):
    """(z, v) pairs -> dense table on a regular z grid (monotone z)."""
    pairs = dict(pairs)
    zs = sorted(pairs)
    z0, z1 = zs[0], zs[-1]
    out = []
    n = max(2, int(round((z1 - z0) / step)) + 1)
    for i in range(n):
        z = z0 + (z1 - z0) * i / (n - 1)
        lo = max(k for k in zs if k <= z) if z > z0 else z0
        hi = min(k for k in zs if k >= z) if z < z1 else z1
        if hi == lo:
            v = pairs[lo]
        else:
            t = (z - lo) / (hi - lo)
            v = pairs[lo] * (1 - t) + pairs[hi] * t
        out.append((z, v))
    return out


def fuselage_width(top, side):
    """Half width of the fuselage only.

    In the top view the wings and canards swallow the hull from z = +3.6 to
    -5.2; there the contour is the wing, not the body, so the hull width is
    interpolated across that window from the nose and the aft body, and the
    wing glove covers the joint anyway.
    """
    pts = top["poly"]
    right = [(z, s) for z, s in pts if s > 0.2]
    body = [(z, s) for z, s in right if z > 3.7 or z < -5.3]
    body.sort()
    probe = [(-11.4, 0.30), (-10.6, 0.42), (-9.6, 0.48), (-8.6, 0.62),
             (-7.8, 1.85), (-6.2, 2.05), (-5.3, 2.20), (-3.0, 2.15),
             (-1.0, 1.95), (0.5, 1.80), (1.6, 1.62), (2.6, 1.60),
             (3.9, 1.53), (5.2, 1.28), (6.3, 0.95), (7.5, 0.95),
             (8.6, 0.88), (9.5, 0.83), (10.4, 0.60), (11.0, 0.44),
             (11.4, 0.10)]
    return probe


def main():
    top = trace_top()
    side, _ = trace_side(top)
    print(f"top   scale {top['scale']:.5f} m/px  tail x={top['x_tail']} "
          f"tip x={top['x_tip']}  centre row={top['row_c']:.1f}")
    print(f"side  scale {side['scale']:.5f} m/px  x {side['x_lo']}..{side['x_hi']} "
          f"floor y={side['y_floor']}")
    span_px = max(r for _, r in [(0, abs(r - top['row_c'])) for r in range(0, 1)])
    ys, xs = np.where(top["sil"])
    span_px = max(abs(ys.min() - top["row_c"]), abs(ys.max() - top["row_c"]))
    print(f"top   traced span {2 * span_px * top['scale']:.2f} m "
          f"(real {SPAN})")

    poly_right = sorted([(round(z, 3), round(s, 3)) for z, s in top["poly"] if s >= 0])
    top_tab = sample(side["top"], 0.1)
    bot_tab = sample(side["bot"], 0.1)
    hw = fuselage_width(top, side)

    with open(OUT_PY, "w") as f:
        f.write('"""Blueprint tables - GENERATED by trace_blueprint.py, do not edit.\n\n')
        f.write("Source drawing: docs/refs/bp-1-three-views.png (Su-34 three-view).\n")
        f.write(f"Calibration: {top['scale']:.5f} m/px, +Z = nose, y = 0 at the belly.\n")
        f.write(f"Overall: length {LENGTH} m, span {SPAN} m.\n")
        f.write('"""\n\n')
        f.write("SCALE_M_PER_PX = %.6f\n" % top["scale"])
        f.write("LENGTH = %.3f\nSPAN = %.3f\n\n" % (LENGTH, SPAN))
        f.write("# top view outline, starboard half, (z, half-span) in metres\n")
        f.write("TOP_OUTLINE = [\n")
        for z, s in poly_right:
            f.write(f"    ({z:7.3f}, {s:6.3f}),\n")
        f.write("]\n\n")
        f.write("# side view profile, (z, y) in metres, y = 0 at the belly\n")
        f.write("SIDE_TOP = [\n")
        for z, y in top_tab:
            f.write(f"    ({z:7.3f}, {y:6.3f}),\n")
        f.write("]\nSIDE_BOT = [\n")
        for z, y in bot_tab:
            f.write(f"    ({z:7.3f}, {y:6.3f}),\n")
        f.write("]\n\n")
        f.write("# fuselage half width per station, (z, half-width)\n")
        f.write("FUSE_HALF_WIDTH = [\n")
        for z, w in hw:
            f.write(f"    ({z:7.3f}, {w:6.3f}),\n")
        f.write("]\n")
    print("wrote", os.path.relpath(OUT_PY, ROOT))

    # ---- debug overlay -----------------------------------------------------
    im = Image.open(REF).convert("RGB")
    d = ImageDraw.Draw(im)
    s = top["scale"]
    for z, w in poly_right:
        x = top["x_tail"] + (z + LENGTH / 2.0) / s
        for r in (top["row_c"] - w / s, top["row_c"] + w / s):
            d.point((x, r), fill=(255, 0, 0))
    for z, y in top_tab:
        x = side["x_lo"] + (z + LENGTH / 2.0) / side["scale"]
        d.point((x, side["y_floor"] - y / side["scale"]), fill=(0, 160, 0))
    for z, y in bot_tab:
        x = side["x_lo"] + (z + LENGTH / 2.0) / side["scale"]
        d.point((x, side["y_floor"] - y / side["scale"]), fill=(0, 0, 255))
    for z, w in hw:
        x = top["x_tail"] + (z + LENGTH / 2.0) / s
        if 0 <= x < im.width:
            for r in (top["row_c"] - w / s, top["row_c"] + w / s):
                d.ellipse([x - 1, r - 1, x + 1, r + 1], outline=(0, 180, 255))
    os.makedirs(os.path.dirname(OUT_PNG), exist_ok=True)
    im.save(OUT_PNG)
    print("wrote", os.path.relpath(OUT_PNG, ROOT))


if __name__ == "__main__":
    main()
