"""Render the perspective the crew will actually have, from the two seats.

Only the interior is drawn (cockpit shell, canopy glass, HUD, instrument
covers) - the airframe skin would otherwise surround the camera and hide
everything. Views are rendered with a wide lens, close to what a VR headset
shows, and a raised ambient term because a cockpit interior is lit by its own
bounce light, not by the sky.

Usage:
    python tools/render_cockpit.py
Out:
    docs/model/cockpit_*.png  and  docs/model/cockpit_sheet.png
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "su34_model"))
import render_preview as R  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OBJ = os.path.join(ROOT, "assets", "model", "su34_donor.obj")
MTL = os.path.join(ROOT, "assets", "model", "su34_donor.mtl")
OUT = os.path.join(ROOT, "docs", "model")

INTERIOR = ("Su-34-cockpit", "Su-34-canopy", "Su-34-hud", "Su-34-instrGlass")

# Seat cushion centres measured from the mesh (tools/seat_check.py). The eye is
# not 30 cm above the cushion - a seated pilot's eye sits ~0.75 m above the seat
# pan, and the model itself confirms it: the HUD combiner spans y 2.11..2.35 at
# z 6.52..6.77, so the eye has to be at that height to look through it.
PILOT_EYE = np.array([-0.52, 2.22, 6.22])
WSO_EYE = np.array([0.52, 2.22, 6.22])

UP = np.array([0.0, 1.0, 0.0])


def views():
    out = {}
    # straight ahead
    out["pilot_forward"] = (PILOT_EYE, PILOT_EYE + np.array([0.0, -0.17, 1.0]), 88.0, 1280, 900)
    # down onto the instrument panel / consoles
    out["pilot_panel"] = (PILOT_EYE, PILOT_EYE + np.array([0.0, -0.85, 1.0]), 88.0, 1280, 900)
    # to the right, at the other crew member
    out["pilot_look_right"] = (PILOT_EYE, PILOT_EYE + np.array([1.0, -0.12, 0.35]), 90.0, 1100, 900)
    # the WSO's own view
    out["wso_forward"] = (WSO_EYE, WSO_EYE + np.array([0.0, -0.17, 1.0]), 88.0, 1280, 900)
    # from behind and above, both seats in frame. The camera has to sit inside
    # the canopy (which ends at z = 5.82): anything further back ends up outside
    # the shell and the render shows the inner surface of the fuselage.
    out["pair"] = (np.array([0.0, 2.44, 5.72]), np.array([0.0, 1.60, 6.90]), 82.0, 1280, 900)
    return out


def parse_objects(path):
    """OBJ -> (verts, uvs, normals, tris with the owning object name).

    render_preview.parse_obj drops the `o` lines, and which node a triangle
    belongs to is exactly what decides whether it is part of the interior.
    """
    verts, uvs, normals, tris = [], [], [], []
    obj = "default"
    for line in open(path, encoding="utf-8"):
        p = line.split()
        if not p:
            continue
        if p[0] == "v":
            verts.append(tuple(float(x) for x in p[1:4]))
        elif p[0] == "vt":
            uvs.append((float(p[1]), float(p[2])))
        elif p[0] == "vn":
            normals.append(tuple(float(x) for x in p[1:4]))
        elif p[0] == "o":
            obj = p[1]
        elif p[0] == "f":
            idx = []
            for tok in p[1:]:
                parts = tok.split("/")
                a = int(parts[0]) - 1
                t = int(parts[1]) - 1 if len(parts) > 1 and parts[1] else -1
                n = int(parts[2]) - 1 if len(parts) > 2 and parts[2] else -1
                idx.append((a, t, n))
            for k in range(1, len(idx) - 1):
                tris.append((*idx[0], *idx[k], *idx[k + 1], obj))
    return (np.array(verts, dtype=np.float64),
            np.array(uvs, dtype=np.float64),
            np.array(normals, dtype=np.float64),
            tris)


def main():
    verts, uvs, normals, tris = parse_objects(OBJ)
    mats = R.parse_mtl(MTL)

    subset = [t for t in tris if t[9] in INTERIOR]
    print("interior triangles:", len(subset), "of", len(tris),
          "->", ", ".join(sorted({t[9] for t in subset})))

    os.makedirs(OUT, exist_ok=True)
    images = {}
    for name, (eye, target, fov, w, h) in views().items():
        cam = R.Camera(np.array(eye, float), np.array(target, float), UP, fov)
        img = R.render(verts, uvs, normals, subset, mats, cam, w, h, ambient=0.34)
        img.save(os.path.join(OUT, "cockpit_" + name + ".png"))
        images[name] = img
        print("wrote", os.path.join(OUT, "cockpit_" + name + ".png"))

    # contact sheet
    cw, ch = 640, 450
    sheet = Image.new("RGB", (cw * 2, ch * 3), (12, 15, 20))
    order = ["pilot_forward", "pilot_panel", "pilot_look_right", "wso_forward", "pair"]
    for i, name in enumerate(order):
        thumb = images[name].resize((cw, ch), Image.LANCZOS)
        x, y = (i % 2) * cw, (i // 2) * ch
        sheet.paste(thumb, (x, y))
        ImageDraw.Draw(sheet).text((x + 14, y + 12), name, fill=(235, 238, 242))
    path = os.path.join(OUT, "cockpit_sheet.png")
    sheet.save(path)
    print("wrote", path)


if __name__ == "__main__":
    main()
