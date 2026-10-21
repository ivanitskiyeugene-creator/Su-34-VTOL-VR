"""Close-up sheet for the areas that are hard to judge in the four flat views.

Run after ``generate_su34.py``; writes ``docs/model/su34_details.png``.
"""
from __future__ import annotations

import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from render_preview import Camera, parse_mtl, parse_obj, render  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OBJ = os.path.join(ROOT, "assets", "model", "su34.obj")
MTL = os.path.join(ROOT, "assets", "model", "su34.mtl")
OUT = os.path.join(ROOT, "docs", "model")

SHOTS = [
    ("main gear", (14.0, -0.2, -8.6), (2.2, -0.7, -3.0), 22.0),
    ("nose gear", (10.5, 0.2, 7.4), (0.0, -0.4, 3.4), 20.0),
    ("canopy", (13.0, 3.0, 8.6), (0.0, 2.5, 5.2), 21.0),
    ("intake", (9.0, 1.2, 5.6), (1.35, 1.0, 2.4), 22.0),
    ("nozzles", (11.0, 1.4, -13.2), (1.3, 1.2, -8.4), 22.0),
    ("tail", (13.0, 3.6, -14.5), (0.0, 2.6, -9.0), 24.0),
]


def main() -> None:
    verts, uvs, normals, tris = parse_obj(OBJ)
    mats = parse_mtl(MTL)
    w, h = 640, 420
    sheet = Image.new("RGB", (w * 3, h * 2), (12, 15, 20))
    for i, (label, eye, target, fov) in enumerate(SHOTS):
        cam = Camera(np.array(eye), np.array(target), np.array([0.0, 1.0, 0.0]), fov)
        img = render(verts, uvs, normals, tris, mats, cam, w, h)
        sheet.paste(img, ((i % 3) * w, (i // 3) * h))
        ImageDraw.Draw(sheet).text(((i % 3) * w + 14, (i // 3) * h + 10),
                                   f"Su-34 / {label}", fill=(238, 240, 244))
        print("  rendered", label)
    path = os.path.join(OUT, "su34_details.png")
    sheet.save(path)
    print("wrote", path)


if __name__ == "__main__":
    main()
