"""Render the donated model from a few angles, to check materials and glazing.

Uses the same software renderer as the procedural preview, so the output is
comparable: quarter view, side view and a cockpit close-up (canopy glass,
HUD combiner, instrument covers).
"""
import os
import sys

import numpy as np
from PIL import Image, ImageOps

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "su34_model"))
import render_preview as R  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OBJ = os.path.join(ROOT, "assets", "model", "su34_donor.obj")
MTL = os.path.join(ROOT, "assets", "model", "su34_donor.mtl")
OUT = os.path.join(ROOT, "docs", "model")

VIEWS = {
    "quarter": (R.Camera(np.array([15.0, 7.5, 19.0], float), np.array([0.0, 0.6, -0.5], float),
                         np.array([0.0, 1.0, 0.0], float), 30.0), 1400, 900),
    "side": (R.Camera(np.array([260.0, 1.2, 0.5], float), np.array([0.0, 1.2, 0.5], float),
                      np.array([0.0, 1.0, 0.0], float), 3.6), 1700, 760),
    # canopy sits over z = 5.8 .. 8.4, y = 1.7 .. 2.8
    "cockpit": (R.Camera(np.array([3.6, 3.9, 12.4], float), np.array([0.0, 2.0, 6.9], float),
                         np.array([0.0, 1.0, 0.0], float), 34.0), 1200, 900),
}


def main():
    verts, uvs, normals, tris = R.parse_obj(OBJ)
    mats = R.parse_mtl(MTL)
    print("materials:", ", ".join(mats))
    os.makedirs(OUT, exist_ok=True)
    for name, (cam, w, h) in VIEWS.items():
        img = R.render(verts, uvs, normals, tris, mats, cam, w, h)
        # render_preview builds its screen basis as cross(forward, up), which is
        # the mirror image of Unity's (right = +x looking down +z). Flipping the
        # result back means these previews show what the game will show.
        img = ImageOps.mirror(img)
        path = os.path.join(OUT, "donor_" + name + ".png")
        img.save(path)
        print("wrote", path)


if __name__ == "__main__":
    main()
