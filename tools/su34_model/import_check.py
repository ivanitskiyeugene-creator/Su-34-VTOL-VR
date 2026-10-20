#!/usr/bin/env python3
"""
Check (and optionally normalise) an incoming Su-34 mesh before it goes into
the mod.

Why: models arrive from Blender, Sketchfab, a commissioned artist or another
game tool, and almost every one of them is wrong in the same three ways -
centimetres instead of metres, Z-up instead of Y-up, nose pointing -Z instead
of +Z. Finding that out inside Unity costs an evening; this script tells you in
a second and can rewrite the OBJ into VTOL VR's convention.

What it reports
---------------
* objects / triangles / vertices, materials, whether UVs and normals exist
* bounding box, real dimensions, and the scale it thinks the file uses
* which axis is the length axis and which end looks like the nose (the end with
  the smaller cross-section)
* degenerate triangles, faces without UVs, objects without a material
* whether the object names look like separate control surfaces (aileron, flap,
  rudder, elevator, gear_door...) which is what animation needs later

Normalisation (--out)
---------------------
    python3 tools/su34_model/import_check.py incoming.obj --out assets/model/su34_imported.obj
    python3 tools/su34_model/import_check.py incoming.obj --up z --forward -y --auto-scale --out fixed.obj

The transform is applied to vertices and normals; UVs, materials and object
names are copied untouched.

Only OBJ is understood here. FBX / glTF / .blend are fine for the Unity side of
the build, but they cannot be inspected in a plain Python environment.
"""
from __future__ import annotations

import argparse
import math
import os
import sys
from collections import Counter, OrderedDict

import numpy as np

SURFACE_WORDS = ("aileron", "flap", "rudder", "elevator", "stabilator", "canard",
                 "airbrake", "speedbrake", "gear_door", "door", "slat", "wing",
                 "fin", "stab", "gear", "landing_gear", "wheel")


class Obj:
    def __init__(self) -> None:
        self.verts: list[list[float]] = []
        self.normals: list[list[float]] = []
        self.uvs: list[list[float]] = []
        self.faces: list[tuple[int, int | None, int | None, int | None]] = []
        self.face_material: list[str] = []
        self.face_object: list[str] = []
        self.objects: list[str] = []
        self.materials: "OrderedDict[str, int]" = OrderedDict()
        self.current_object = "default"
        self.current_material = ""
        self.has_uv = False


class ObjFull(Obj):
    """Parser variant that keeps all three UV/normal indices per triangle."""

    def __init__(self) -> None:
        super().__init__()
        self.tris: list[tuple[tuple[int, int | None, int | None],
                               tuple[int, int | None, int | None],
                               tuple[int, int | None, int | None]]] = []


def parse_obj_full(path: str) -> ObjFull:
    obj = ObjFull()
    with open(path, "r", errors="replace") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line[0] == "#":
                continue
            parts = line.split()
            tag = parts[0]
            if tag == "v" and len(parts) >= 4:
                obj.verts.append([float(parts[1]), float(parts[2]), float(parts[3])])
            elif tag == "vn" and len(parts) >= 4:
                obj.normals.append([float(parts[1]), float(parts[2]), float(parts[3])])
            elif tag == "vt" and len(parts) >= 3:
                obj.uvs.append([float(parts[1]), float(parts[2])])
                obj.has_uv = True
            elif tag in ("o", "g"):
                name = " ".join(parts[1:]) or "default"
                obj.current_object = name
                if name not in obj.objects:
                    obj.objects.append(name)
            elif tag == "usemtl":
                obj.current_material = " ".join(parts[1:])
                obj.materials[obj.current_material] = obj.materials.get(obj.current_material, 0) + 1
            elif tag == "f":
                idx = []
                for token in parts[1:]:
                    chunk = token.split("/")
                    vi = int(chunk[0])
                    ti = int(chunk[1]) if len(chunk) > 1 and chunk[1] else None
                    ni = int(chunk[2]) if len(chunk) > 2 and chunk[2] else None
                    if vi < 0: vi = len(obj.verts) + vi + 1
                    if ti is not None and ti < 0: ti = len(obj.uvs) + ti + 1
                    if ni is not None and ni < 0: ni = len(obj.normals) + ni + 1
                    idx.append((vi - 1, None if ti is None else ti - 1, None if ni is None else ni - 1))
                for k in range(1, len(idx) - 1):
                    tri = (idx[0], idx[k], idx[k + 1])
                    obj.faces.append((tri[0][0], tri[1][0], tri[2][0]))
                    obj.tris.append(tri)
                    obj.face_material.append(obj.current_material)
                    obj.face_object.append(obj.current_object)
    return obj


def analyse(obj: ObjFull) -> dict:
    verts = np.array(obj.verts, dtype=np.float64) if obj.verts else np.zeros((0, 3))
    tris = np.array(obj.faces, dtype=np.int64) if obj.faces else np.zeros((0, 3), dtype=np.int64)
    result: dict = {
        "vertices": len(verts),
        "triangles": len(tris),
        "objects": len(obj.objects),
        "materials": len(obj.materials),
        "has_uv": obj.has_uv,
        "has_normals": len(obj.normals) > 0,
        "materials_bad": [m for m in obj.materials if not m or m.lower() in ("", "default", "none")],
        "faces_without_uv": 0,
        "faces_without_material": 0,
        "degenerate": 0,
        "micro": 0,
    }

    if len(tris) and len(verts):
        a = verts[tris[:, 0]]
        b = verts[tris[:, 1]]
        c = verts[tris[:, 2]]
        area = np.linalg.norm(np.cross(b - a, c - a), axis=1) * 0.5
        edge = np.max(np.stack([
            np.linalg.norm(b - a, axis=1),
            np.linalg.norm(c - b, axis=1),
            np.linalg.norm(a - c, axis=1),
        ], axis=1), axis=1)
        e2 = np.maximum(edge, 1e-9) ** 2
        result["degenerate"] = int(np.sum(area < 1e-9))
        result["micro"] = int(np.sum(area / e2 < 0.01))

    for tri, mat in zip(obj.tris, obj.face_material):
        if any(corner[1] is None for corner in tri):
            result["faces_without_uv"] += 1
        if not mat:
            result["faces_without_material"] += 1

    if len(verts):
        lo = verts.min(axis=0)
        hi = verts.max(axis=0)
        dims = hi - lo
        result["bbox_min"] = lo
        result["bbox_max"] = hi
        result["size"] = dims
        result["length_axis"] = int(np.argmax(dims))
        result["centroid"] = verts.mean(axis=0)
        result["nose_sign"] = nose_sign(verts, int(np.argmax(dims)))
    return result


def nose_sign(verts: np.ndarray, axis: int) -> int:
    """+1 if the model looks like it points along +axis, -1 otherwise.

    The nose is the end with the smaller cross-section: compare the 90th
    percentile extent of the other two axes in the outermost 12 % of the model.
    """
    lo = verts.min(axis=0)
    hi = verts.max(axis=0)
    span = max(hi[axis] - lo[axis], 1e-9)
    others = [i for i in range(3) if i != axis]
    scores = {}
    for sign in (+1, -1):
        if sign > 0:
            mask = verts[:, axis] >= hi[axis] - 0.12 * span
        else:
            mask = verts[:, axis] <= lo[axis] + 0.12 * span
        band = verts[mask]
        if len(band) < 3:
            scores[sign] = math.inf
            continue
        extent = 0.0
        for i in others:
            extent = max(extent, float(np.percentile(band[:, i], 98) - np.percentile(band[:, i], 2)))
        scores[sign] = extent
    return +1 if scores[+1] <= scores[-1] else -1


def guess_scale_units(size: np.ndarray) -> tuple[float, str]:
    """Return (multiplier to metres, human name)."""
    biggest = float(np.max(size)) if len(size) else 0.0
    if biggest <= 0:
        return 1.0, "unknown"
    if 8.0 <= biggest <= 40.0:
        return 1.0, "metres"
    if 0.8 <= biggest < 8.0:
        return 100.0, "decimetres?"  # rare, but 10x is the usual suspect
    if 800.0 <= biggest <= 4000.0:
        return 0.01, "centimetres"
    if 8000.0 <= biggest <= 40000.0:
        return 0.001, "millimetres"
    if 0.008 <= biggest < 0.8:
        return 1000.0, "kilometres?? (very likely wrong)"
    return 1.0, "unknown"


AXIS_FORWARD = {
    "+x": (0, 1.0), "-x": (0, -1.0),
    "+y": (1, 1.0), "-y": (1, -1.0),
    "+z": (2, 1.0), "-z": (2, -1.0),
}


def build_transform(up: str, forward: str, scale: float, flip_x: bool) -> np.ndarray:
    """Rotation (3x3) that maps the file's up/forward onto Unity's +Y/+Z."""
    fwd_axis, fwd_sign = AXIS_FORWARD[forward]
    up_axis = {"x": 0, "y": 1, "z": 2}[up.lower()]
    if up_axis == fwd_axis:
        raise SystemExit("--up and --forward must name different axes")

    rot = np.zeros((3, 3))
    rot[2, fwd_axis] = fwd_sign            # unity +Z <- file forward
    rot[1, up_axis] = 1.0                  # unity +Y <- file up
    # third axis is forced to keep the basis right-handed
    used = {fwd_axis, up_axis}
    rest = ({0, 1, 2} - used).pop()
    rot[0, rest] = 1.0
    if np.linalg.det(rot) < 0:
        rot[:, rest] *= -1.0
    if flip_x:
        rot[0, :] *= -1.0
    return rot * scale


def write_obj(src: str, out_path: str, rot: np.ndarray, translate: np.ndarray) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    with open(src, "r", errors="replace") as fh, open(out_path, "w") as out:
        out.write("# normalised by tools/su34_model/import_check.py\n")
        out.write("# transform: %s  translate: %s\n" % (np.array2string(rot, precision=6), np.array2string(translate, precision=4)))
        for raw in fh:
            line = raw.rstrip("\n")
            stripped = line.strip()
            if stripped.startswith("v "):
                parts = stripped.split()
                p = rot @ np.array([float(parts[1]), float(parts[2]), float(parts[3])]) + translate
                out.write("v %.6f %.6f %.6f\n" % (p[0], p[1], p[2]))
            elif stripped.startswith("vn "):
                parts = stripped.split()
                n = rot @ np.array([float(parts[1]), float(parts[2]), float(parts[3])])
                ln = np.linalg.norm(n)
                if ln > 1e-12:
                    n = n / ln
                out.write("vn %.6f %.6f %.6f\n" % (n[0], n[1], n[2]))
            else:
                out.write(line + "\n")


def print_report(path: str, info: dict) -> None:
    size = info.get("size", np.zeros(3))
    print("file            : %s" % path)
    print("objects         : %d" % info["objects"])
    print("vertices        : %d" % info["vertices"])
    print("triangles       : %d" % info["triangles"])
    print("materials       : %d" % info["materials"])
    print("uvs / normals   : %s / %s" % ("yes" if info["has_uv"] else "NO",
                                         "yes" if info["has_normals"] else "NO"))
    if len(size):
        print("size (x,y,z)    : %.2f x %.2f x %.2f" % (size[0], size[1], size[2]))
        axis = info["length_axis"]
        sign = info["nose_sign"]
        names = "XYZ"
        print("length axis     : %s, nose points %s%s" % (names[axis], "+" if sign > 0 else "-", names[axis]))
        mult, units = guess_scale_units(size)
        print("units look like : %s (multiplier to metres: %g)" % (units, mult))
    print("degenerate      : %d" % info["degenerate"])
    print("slivers (<1%% of the longest edge): %d" % info["micro"])
    print("faces w/o uv    : %d" % info["faces_without_uv"])
    print("faces w/o mtl   : %d" % info["faces_without_material"])
    if info["materials_bad"]:
        print("bad material    : %s" % ", ".join(info["materials_bad"]))


def check_names(obj: ObjFull) -> None:
    names = obj.objects
    if not names:
        return
    surfaces = [n for n in names if any(w in n.lower() for w in SURFACE_WORDS)]
    print("object names    : %d total, %d look like surfaces" % (len(names), len(surfaces)))
    if surfaces:
        print("   surfaces     : %s" % ", ".join(surfaces[:12]))
    else:
        print("   note: no aileron / rudder / elevator / gear_door objects found -")
        print("         control surfaces will not be animatable until they are split out")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Inspect and normalise an incoming Su-34 mesh (OBJ).")
    ap.add_argument("model", help="OBJ file to inspect")
    ap.add_argument("--out", help="write a normalised OBJ here")
    ap.add_argument("--up", default="y", choices=["x", "y", "z"],
                    help="which axis is UP in the source file (default: y)")
    ap.add_argument("--forward", default="+z", choices=sorted(AXIS_FORWARD),
                    help="where the nose points in the source file (default: +z)")
    ap.add_argument("--scale", type=float, default=None,
                    help="explicit scale factor to metres (overrides --auto-scale)")
    ap.add_argument("--auto-scale", action="store_true",
                    help="pick the scale from the bounding box")
    ap.add_argument("--flip-x", action="store_true",
                    help="mirror left/right (use when the model comes out mirrored)")
    ap.add_argument("--center-x", action="store_true",
                    help="move the model so x is symmetric around zero")
    ap.add_argument("--expect-length", type=float, default=24.0,
                    help="warn if the length differs from this by more than 30%% (default 24 m)")
    # argparse treats "-y" as an option, so "--forward -y" would fail.
    # Fold it into "--forward=-y" before parsing.
    if argv is None:
        argv = sys.argv[1:]
    fixed = []
    for i, token in enumerate(argv):
        if fixed and fixed[-1] == "--forward" and token in AXIS_FORWARD:
            fixed[-1] = "--forward=" + token
            continue
        fixed.append(token)
    args = ap.parse_args(fixed)

    if not os.path.isfile(args.model):
        print("no such file: %s" % args.model, file=sys.stderr)
        return 2

    obj = parse_obj_full(args.model)
    info = analyse(obj)
    print_report(args.model, info)
    check_names(obj)

    if len(info.get("size", [])) and args.expect_length > 0:
        length = float(info["size"][info["length_axis"]])
        units_mult, _ = guess_scale_units(info["size"])
        if units_mult != 1.0:
            length *= units_mult
        if abs(length - args.expect_length) > 0.3 * args.expect_length:
            print("WARNING         : length %.1f m, expected around %.1f m" % (length, args.expect_length))

    if not args.out:
        print("\n(no --out: nothing written. Add --out fixed.obj to normalise.)")
        return 0

    scale = args.scale
    if scale is None:
        if args.auto_scale:
            scale = guess_scale_units(info["size"])[0]
        else:
            scale = 1.0

    rot = build_transform(args.up, args.forward, scale, args.flip_x)

    translate = np.zeros(3)
    if args.center_x and len(obj.verts):
        verts = np.array(obj.verts)
        translate[0] = -0.5 * (verts[:, 0].min() + verts[:, 0].max()) * scale
        if args.flip_x:
            translate[0] *= -1.0

    write_obj(args.model, args.out, rot, translate)
    print("\nwrote           : %s   (scale %.4g, up %s, forward %s%s)" % (
        args.out, scale, args.up, args.forward, ", flipped X" if args.flip_x else ""))

    written = parse_obj_full(args.out)
    again = analyse(written)
    print("after transform : size %.2f x %.2f x %.2f, nose %s%s, %d tris" % (
        again["size"][0], again["size"][1], again["size"][2],
        "+" if again["nose_sign"] > 0 else "-", "XYZ"[again["length_axis"]],
        again["triangles"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
