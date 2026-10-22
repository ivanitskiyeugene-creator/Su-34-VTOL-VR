"""Check that the two crew anchors sit inside the model's cockpit.

The builder puts the donor's seat rigs on PilotSeatAnchor / WsoSeatAnchor. If
those points are not inside the Su-34 cockpit, the pilot floats in the air or
sits inside the fuselage. This prints the distance from each anchor to the
nearest cockpit surface and renders a top/side view with the anchors marked.
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageOps

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "su34_model"))
import render_preview as R  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OBJ = os.path.join(ROOT, "assets", "model", "su34_donor.obj")
MTL = os.path.join(ROOT, "assets", "model", "su34_donor.mtl")
OUT = os.path.join(ROOT, "docs", "model")

PILOT = np.array([-0.52, 1.45, 6.30])
WSO = np.array([0.52, 1.45, 6.30])


def parse_group(path, want):
    V, F, cur = [], [], None
    for line in open(path, encoding="utf-8", errors="ignore"):
        if line.startswith("v "):
            p = line.split()
            V.append([float(p[1]), float(p[2]), float(p[3])])
        elif line.startswith("o "):
            cur = line[2:].strip()
        elif line.startswith("f ") and cur and want in cur:
            idx = [int(t.split("/")[0]) - 1 for t in line.split()[1:]]
            for i in range(1, len(idx) - 1):
                F.append((idx[0], idx[i], idx[i + 1]))
    return np.array(V), np.array(F)


def point_tri_distance(p, a, b, c):
    """Closest distance from p to triangle abc (Ericson, Real-Time Collision)."""
    ab, ac, ap = b - a, c - a, p - a
    d1, d2 = ab @ ap, ac @ ap
    if d1 <= 0 and d2 <= 0:
        return np.linalg.norm(p - a)
    bp = p - b
    d3, d4 = ab @ bp, ac @ bp
    if d3 >= 0 and d4 <= d3:
        return np.linalg.norm(p - b)
    vc = d1 * d4 - d3 * d2
    if vc <= 0 and d1 >= 0 and d3 <= 0:
        return np.linalg.norm(p - (a + (d1 / (d1 - d3)) * ab))
    cp = p - c
    d5, d6 = ab @ cp, ac @ cp
    if d6 >= 0 and d5 <= d6:
        return np.linalg.norm(p - c)
    vb = d5 * d2 - d1 * d6
    if vb <= 0 and d2 >= 0 and d6 <= 0:
        return np.linalg.norm(p - (a + (d2 / (d2 - d6)) * ac))
    va = d3 * d6 - d5 * d4
    if va <= 0 and (d4 - d3) >= 0 and (d5 - d6) >= 0:
        w = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        return np.linalg.norm(p - (b + w * (c - b)))
    denom = 1.0 / (va + vb + vc)
    v, w = vb * denom, vc * denom
    return np.linalg.norm(p - (a + ab * v + ac * w))


def main():
    V, F = parse_group(OBJ, "cockpit")
    print("cockpit triangles:", len(F))
    lo, hi = V.min(0), V.max(0)
    print("cockpit bbox", lo.round(2), hi.round(2))
    for name, p in (("pilot (left)", PILOT), ("wso (right)", WSO)):
        d = min(point_tri_distance(p, V[t[0]], V[t[1]], V[t[2]]) for t in F)
        inside = np.all(p > lo) and np.all(p < hi)
        print(f"{name:14s} at {p.round(2)}: nearest cockpit surface {d*100:5.1f} cm, "
              f"inside bbox: {inside}")

    verts, uvs, normals, tris = R.parse_obj(OBJ)
    mats = R.parse_mtl(MTL)
    views = {
        "seat_top": (R.Camera(np.array([0.0, 22.0, 6.6], float), np.array([0.0, 0.0, 6.6], float),
                              np.array([0.0, 0.0, 1.0], float), 26.0), 1100, 800),
        "seat_side": (R.Camera(np.array([16.0, 1.9, 6.6], float), np.array([0.0, 1.9, 6.6], float),
                               np.array([0.0, 1.0, 0.0], float), 26.0), 1100, 800),
    }
    for name, (cam, w, h) in views.items():
        img = ImageOps.mirror(R.render(verts, uvs, normals, tris, mats, cam, w, h))
        draw = ImageDraw.Draw(img)
        for p, col in ((PILOT, (255, 60, 60)), (WSO, (60, 200, 255))):
            sx, sy, _ = cam.project(np.array([p]), w, h)[0]
            r = 9
            draw.ellipse([sx - r, sy - r, sx + r, sy + r], outline=col, width=3)
            draw.line([sx - 18, sy, sx + 18, sy], fill=col, width=2)
            draw.line([sx, sy - 18, sx, sy + 18], fill=col, width=2)
        path = os.path.join(OUT, "donor_" + name + ".png")
        img.save(path)
        print("wrote", path)


if __name__ == "__main__":
    main()
