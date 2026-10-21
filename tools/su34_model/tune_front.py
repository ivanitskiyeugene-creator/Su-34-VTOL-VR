"""Coordinate fit of the head-on silhouette to the drawing.

The colour three-view sheet is not perfectly isotropic between views (its
span scale and its height scale differ by ~4 %), so the front view is fitted
on its own and the other two views are re-checked afterwards.

Knobs are absolute values, searched one at a time and re-searched once:

    wing_y_root, wing_y_tip, canard_y, stab_y, canopy_hw,
    hull_scale, shoulder_gain, fin_x

Run:  python3 tools/su34_model/tune_front.py
"""
from __future__ import annotations

import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import generate_su34 as G          # noqa: E402
import overlay as O                # noqa: E402

REF, CX, ROW, SPAN = O.ref_front()
HW0 = [(z, hw) for z, hw in G.HALF_WIDTH]


def set_params(p: dict) -> None:
    G.WING["y_root"] = p["wing_y_root"]
    G.WING["y_tip"] = p["wing_y_tip"]
    G.CANARD["y"] = p["canard_y"]
    G.STAB["y"] = p["stab_y"]
    G.CANOPY_HALF_WIDTH = p["canopy_hw"]
    G.FIN["root_x"] = p["fin_x"]
    G.FIN["tip_x"] = p["fin_x"] + 0.14
    G.HALF_WIDTH = [(z, hw * p["hull_scale"]) for z, hw in HW0]
    G.SHOULDER_GAIN = p["shoulder_gain"]
    stations = []
    for zi in np.linspace(G.TAIL_Z, G.NOSE_Z, 150):
        zi = float(zi)
        stations.append((zi, G.interp(G.HALF_WIDTH, zi), G.interp(G.TOP_LINE, zi),
                         max(0.02, G.interp(G.KEEL, zi)), G.hull_exponent(zi)))
    stations.sort(key=lambda s: -s[0])
    G.STATIONS[:] = stations


def flatten(mesh):
    verts, faces, base = [], [], 0
    for part in mesh.parts:
        if any(k in part.name for k in O.NO_GEAR) or any(k in part.material for k in O.NO_GEAR):
            continue
        verts.extend(part.vertices)
        faces.extend((a + base, b + base, c + base) for a, b, c in part.faces)
        base += len(part.vertices)
    return np.asarray(verts, float), np.asarray(faces, int)


REF_TOP, REF_SIDE = O.ref_top(), O.ref_side()


def _iou(a, b) -> float:
    return (a & b).sum() / max((a | b).sum(), 1)


def score(verbose: bool = False) -> float:
    G.apply_box_uv = lambda *a, **kw: None
    v, f = flatten(G.build())
    used = np.unique(f)
    x0, x1 = v[used, 0].min(), v[used, 0].max()
    y0 = v[used, 1].min()
    k = SPAN / (x1 - x0)
    front = O.project(v, f, (0, 1),
                      lambda q: np.stack([CX + (q[:, 0] - 0.5 * (x0 + x1)) * k,
                                          ROW - (q[:, 1] - y0) * k], axis=1),
                      size=(736, 980))
    win = np.zeros_like(REF)
    win[815:965, 60:510] = True
    top = O.top_mask(v, f)
    side = O.side_mask(v, f)
    sf = _iou(REF & win, front & win)
    st = _iou(REF_TOP, top)
    ss = _iou(REF_SIDE, side)
    if verbose:
        print(f"    front {sf * 100:5.2f}  top {st * 100:5.2f}  side {ss * 100:5.2f}")
    return 0.50 * sf + 0.25 * st + 0.25 * ss


def main() -> None:
    p = dict(wing_y_root=G.WING["y_root"], wing_y_tip=G.WING["y_tip"],
             canard_y=G.CANARD["y"], stab_y=G.STAB["y"],
             canopy_hw=G.CANOPY_HALF_WIDTH, hull_scale=1.0,
             shoulder_gain=getattr(G, "SHOULDER_GAIN", 0.22), fin_x=G.FIN["root_x"])
    set_params(p)
    best = score(verbose=True)
    print(f"start  {best * 100:5.2f}%")

    grid = {
        "wing_y_root": (+0.00, +0.06, -0.06, +0.12),
        "wing_y_tip": (+0.00, +0.06, -0.06, +0.12),
        "canard_y": (+0.00, +0.06, -0.06, +0.10),
        "stab_y": (+0.00, +0.06, -0.06, +0.10),
        "canopy_hw": (+0.00, -0.04, +0.04, -0.08),
        "hull_scale": (1.00, 0.97, 1.03, 0.94),
        "shoulder_gain": (0.22, 0.16, 0.28, 0.12),
        "fin_x": (+0.00, -0.04, +0.04, -0.08),
    }
    for sweep in range(3):
        for key, deltas in grid.items():
            if sweep == 1 and key == "hull_scale":
                continue
            base = p[key]
            for d in deltas[1:]:
                trial = dict(p)
                trial[key] = base + d if key != "hull_scale" else d
                set_params(trial)
                s = score()
                if s > best + 2e-4:
                    best, p = s, trial
                    print(f"  sweep{sweep} {key:12s} {trial[key]:+.3f} -> {s * 100:5.2f}%")
                    break

    print(f"done   {best * 100:5.2f}%")
    for k, v in sorted(p.items()):
        print(f"  {k:14s} {v}")


if __name__ == "__main__":
    main()
