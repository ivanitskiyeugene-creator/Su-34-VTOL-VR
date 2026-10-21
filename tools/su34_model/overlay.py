"""
Overlay the generated model on the reference drawing.

The model is projected orthographically (top and side) at the exact scale of
`docs/refs/bp-1-three-views.png` and compared pixel by pixel with the traced
silhouette, so every deviation is visible and measurable:

    orange = drawing only (the model is missing volume there)
    blue   = model only  (the model has volume the drawing does not)
    grey   = both agree

Also prints the silhouette IoU and the largest deviation in metres.

Run:  python3 tools/su34_model/overlay.py [assets/model/su34.obj]
Out:  docs/model/su34_overlay.png
"""
from __future__ import annotations

import os
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from skimage import measure

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
from blueprint_data import SIDE_BOT, SIDE_TOP  # noqa: E402

REF = os.path.join(ROOT, "docs", "refs", "bp-1-three-views.png")
OUT = os.path.join(ROOT, "docs", "model", "su34_overlay.png")
OBJ = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "assets", "model", "su34.obj")

FRONT_REF = os.path.join(ROOT, "docs", "refs", "bp-3-livery.png")
FRONT_OUT = os.path.join(ROOT, "docs", "model", "su34_overlay_front.png")

TOP_BOX = (0, 500, 5, 315)
SIDE_BOX = (90, 600, 250, 360)
SCALE = 0.050652
ROW_C = 157.5
X_TAIL = 4
SIDE_X0, SIDE_Y0 = 125, 354
LENGTH = 23.3
STEP = 0.5          # m, chord sampling for the projections


NO_GEAR = ("Gear", "Wheel", "Tire", "Hub", "Axle", "Strut", "Brace")


def load_obj(path, skip_gear=False):
    """Vertices / triangles; with ``skip_gear`` the landing gear and wheels are
    dropped, because the drawing's side view shows the aircraft clean."""
    verts, faces = [], []
    keep = keep_obj = True
    for line in open(path):
        if line.startswith("g ") or line.startswith("o "):
            name = line.split(None, 1)[1].strip()
            keep_obj = not (skip_gear and any(k in name for k in NO_GEAR))
            keep = keep_obj
        elif line.startswith("v "):
            verts.append([float(t) for t in line.split()[1:4]])
        elif line.startswith("usemtl "):
            mat = line.split(None, 1)[1].strip()
            keep = keep_obj and not (skip_gear and any(k in mat for k in NO_GEAR))
        elif line.startswith("f ") and keep:
            idx = [int(t.split("/")[0]) - 1 for t in line.split()[1:]]
            for k in range(1, len(idx) - 1):
                faces.append((idx[0], idx[k], idx[k + 1]))
    return np.array(verts), np.array(faces, dtype=np.int64)


def project(verts, faces, axes, to_px, size=(600, 385)):
    """Rasterise the projected triangles into a bool mask of the ref sheet."""
    pts = np.zeros((verts.shape[0], 2))
    pts[:, 0] = verts[:, axes[0]]
    pts[:, 1] = verts[:, axes[1]]
    px = to_px(pts)
    img = Image.new("1", size, 0)
    d = ImageDraw.Draw(img)
    for a, b, c in faces:
        d.polygon([tuple(px[a]), tuple(px[b]), tuple(px[c])], fill=1)
    return np.array(img, dtype=bool)


def top_mask(verts, faces):
    return project(verts, faces, (2, 0),
                   lambda p: np.stack([X_TAIL + (p[:, 0] + LENGTH / 2) / SCALE,
                                       ROW_C - p[:, 1] / SCALE], axis=1))


def side_mask(verts, faces):
    return project(verts, faces, (2, 1),
                   lambda p: np.stack([SIDE_X0 + (LENGTH / 2 - p[:, 0]) / SCALE,
                                       SIDE_Y0 - p[:, 1] / SCALE], axis=1))


def ref_top():
    a = np.asarray(Image.open(REF).convert("L"))
    m = np.zeros_like(a, bool)
    x0, x1, y0, y1 = TOP_BOX
    m[y0:y1, x0:x1] = a[y0:y1, x0:x1] < 205
    m = ndimage.binary_closing(m, np.ones((2, 2)))
    lab, n = ndimage.label(m, np.ones((3, 3)))
    sizes = ndimage.sum(m, lab, range(1, n + 1))
    sil = ndimage.binary_fill_holes(lab == int(np.argmax(sizes)) + 1)
    # drop the pitot boom
    for x in range(int(X_TAIL + LENGTH / SCALE), sil.shape[1]):
        sil[:, x] = False
    return sil


def ref_side():
    m = np.zeros((385, 600), bool)
    top = dict(SIDE_TOP)
    bot = dict(SIDE_BOT)
    zs = sorted(top)
    img = Image.new("1", (600, 385), 0)
    d = ImageDraw.Draw(img)
    pts = []
    for z in zs:
        pts.append((SIDE_X0 + (LENGTH / 2 - z) / SCALE, SIDE_Y0 - top[z] / SCALE))
    for z in reversed(zs):
        pts.append((SIDE_X0 + (LENGTH / 2 - z) / SCALE, SIDE_Y0 - bot[z] / SCALE))
    d.polygon(pts, fill=1)
    return np.array(img, dtype=bool)


def ref_front():
    """The head-on view sits at the bottom of the colour three-view sheet.

    Returns the filled silhouette, its centre column and its bottom row, so the
    model can be dropped on it at the sheet's own span scale.
    """
    a = np.asarray(Image.open(FRONT_REF).convert("L"))
    win = np.zeros_like(a, bool)
    win[815:965, 60:510] = True
    m = ndimage.binary_closing((a < 200) & win, np.ones((2, 2)))
    lab, n = ndimage.label(m, np.ones((3, 3)))
    sizes = ndimage.sum(m, lab, range(1, n + 1))
    sil = ndimage.binary_fill_holes(lab == int(np.argmax(sizes)) + 1)
    ys, xs = np.where(sil)
    return sil, 0.5 * (xs.min() + xs.max()), ys.max(), (xs.max() - xs.min() + 1)


def front_mask(verts, faces, cx, row_bot, span_px, row_top=None):
    """Orthographic head-on silhouette, scaled and dropped onto the sheet.

    ``row_top`` switches on separate horizontal / vertical scales: the colour
    sheet's head-on view is drawn about 5 % squashed vertically, so a single
    isotropic scale would charge that drawing error to the model.  Pass it to
    measure shape rather than the sheet's aspect ratio.
    """
    used = np.unique(faces) if len(faces) else np.array([], int)
    x0, x1 = verts[used, 0].min(), verts[used, 0].max()
    y0, y1 = verts[used, 1].min(), verts[used, 1].max()
    kx = span_px / (x1 - x0)
    ky = kx
    if row_top is not None:
        ky = (row_bot - row_top) / max(y1 - y0, 1e-6)
    return project(verts, faces, (0, 1),
                   lambda p: np.stack([cx + (p[:, 0] - 0.5 * (x0 + x1)) * kx,
                                       row_bot - (p[:, 1] - y0) * ky], axis=1),
                   size=(736, 980))


def report(name, ref, got):
    inter = (ref & got).sum()
    union = (ref | got).sum()
    iou = inter / max(union, 1)
    miss = (ref & ~got).sum() * SCALE ** 2
    extra = (got & ~ref).sum() * SCALE ** 2
    print(f"{name:5s} IoU {iou * 100:5.1f}%   missing {miss:7.2f} m2   "
          f"extra {extra:7.2f} m2")
    return iou


def main():
    verts, faces = load_obj(OBJ)
    v2, f2 = load_obj(OBJ, skip_gear=True)
    rt, rs = ref_top(), ref_side()
    mt, ms = top_mask(verts, faces), side_mask(v2, f2)
    # trim to the drawing windows
    win = np.zeros_like(rt)
    win[TOP_BOX[2]:TOP_BOX[3], TOP_BOX[0]:TOP_BOX[1]] = True
    rt, mt = rt & win, mt & win
    sw = np.zeros_like(rs)
    sw[SIDE_BOX[2]:SIDE_BOX[3], SIDE_BOX[0]:SIDE_BOX[1]] = True
    rs, ms = rs & sw, ms & sw
    report("top", rt, mt)
    report("side", rs, ms)

    rf, fcx, frow, fspan = ref_front()
    v3, f3 = load_obj(OBJ, skip_gear=True)
    fwin = np.zeros_like(rf)
    fwin[815:965, 60:510] = True
    rf = rf & fwin
    rows = np.where(rf.any(1))[0]
    mf = front_mask(v3, f3, fcx, frow, fspan) & fwin
    report("front", rf, mf)
    # shape score: the sheet's head-on view is squashed vertically, so re-fit
    # the vertical scale before judging the outline itself
    mf2 = front_mask(v3, f3, fcx, frow, fspan, row_top=int(rows.min())) & fwin
    report("front*", rf, mf2)

    base = Image.open(REF).convert("RGB")
    px = np.array(base)
    def paint(mask_ref, mask_mdl, boost=0.0):
        agree = mask_ref & mask_mdl
        miss = mask_ref & ~mask_mdl
        extra = mask_mdl & ~mask_ref
        px[agree] = (px[agree] * 0.55 + np.array([90, 90, 90]) * 0.45).astype(np.uint8)
        px[miss] = (px[miss] * 0.25 + np.array([255, 140, 0]) * 0.75).astype(np.uint8)
        px[extra] = (px[extra] * 0.25 + np.array([40, 110, 255]) * 0.75).astype(np.uint8)
    paint(rt, mt)
    paint(rs, ms)
    base = Image.fromarray(px)
    d = ImageDraw.Draw(base)
    d.text((6, 322), "orange = drawing only, blue = model only, grey = match",
           fill=(0, 0, 0))
    base.save(OUT)

    fimg = Image.open(FRONT_REF).convert("RGB")
    fpx = np.array(fimg)
    for mask_ref, mask_mdl in ((rf, mf2),):
        agree = mask_ref & mask_mdl
        miss = mask_ref & ~mask_mdl
        extra = mask_mdl & ~mask_ref
        fpx[agree] = (fpx[agree] * 0.35 + np.array([40, 40, 40]) * 0.65).astype(np.uint8)
        fpx[miss] = (fpx[miss] * 0.15 + np.array([255, 140, 0]) * 0.85).astype(np.uint8)
        fpx[extra] = (fpx[extra] * 0.15 + np.array([40, 110, 255]) * 0.85).astype(np.uint8)
    fi = Image.fromarray(fpx).crop((40, 800, 530, 975))
    fi = fi.resize((fi.width * 2, fi.height * 2), Image.LANCZOS)
    ImageDraw.Draw(fi).text((8, 8), "front: orange = drawing only, blue = model only",
                            fill=(0, 0, 0))
    fi.save(FRONT_OUT)
    print("wrote", os.path.relpath(FRONT_OUT, ROOT))
    print("wrote", os.path.relpath(OUT, ROOT))


if __name__ == "__main__":
    main()
