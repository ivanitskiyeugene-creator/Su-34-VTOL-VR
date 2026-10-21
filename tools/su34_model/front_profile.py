"""Print the head-on silhouette of the model in metres, band by band.

The colour sheet's front view is squashed vertically, so its raw IoU is not a
fair score.  This tool projects the model onto the X-Y plane at a known scale
and prints the solid runs at a set of heights, which is directly comparable
with the hand-measured bands taken off the drawing.
"""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from overlay import load_obj, project  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OBJ = os.path.join(ROOT, "assets", "model", "su34.obj")
RES = 0.02        # metres per pixel
W, H = 800, 300   # x -8..8 m, y 0..6 m


def mask() -> np.ndarray:
    verts, faces = load_obj(OBJ, skip_gear=True)
    return project(verts, faces, (0, 1),
                   lambda p: np.stack([W / 2.0 + p[:, 0] / RES,
                                       (H - 1) - p[:, 1] / RES], axis=1),
                   size=(W, H))


def runs(row: np.ndarray):
    xs = np.where(row)[0]
    if not len(xs):
        return []
    out, s, p = [], xs[0], xs[0]
    for x in xs[1:]:
        if x - p > 1:
            out.append((s, p))
            s = x
        p = x
    out.append((s, p))
    return [((a - W / 2.0) * RES, (b - W / 2.0) * RES) for a, b in out]


def main() -> None:
    m = mask()
    heights = [0.05, 0.25, 0.45, 0.65, 1.05, 1.25, 1.45, 1.65, 1.85, 2.05,
               2.25, 2.45, 2.65, 2.85, 3.05, 3.45, 3.85, 4.25, 4.55]
    for h in heights:
        r = int((H - 1) - h / RES)
        segs = runs(m[r])
        print(f"h={h:4.2f}  " + "  ".join(f"[{a:+.2f},{b:+.2f}]" for a, b in segs))


if __name__ == "__main__":
    main()
