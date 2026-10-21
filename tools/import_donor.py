"""Convert the donated Su-34 GLB into a plain OBJ + MTL for the mod.

The GLB carries separate nodes for the airframe, canopy, cockpit, HUD and the
two landing-gear states; each node keeps its own name so the Unity side can
pick what it needs (gear down / gear up, glass on / glass off).
"""
from __future__ import annotations

import json
import os
import struct
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "assets", "import", "su34_donor", "source", "Su-34.glb")
OUT_DIR = os.path.join(ROOT, "assets", "import", "su34_donor", "obj")

# The GLB carries four materials: the painted airframe with the PBR set, plain
# glass for the canopy and the instrument covers, the green HUD combiner and the
# landing lights. Keeping them apart is what lets Unity make the glass actually
# transparent and the lamps actually glow - merging everything into one
# material (as the first import did) gives an opaque canopy.
MATERIAL_NAMES = {
    0: "Su34_Airframe",
    1: "Su34_Glass",
    2: "Su34_HUD",
    3: "Su34_Lights",
}

MTL_BODY = """newmtl {name}
Ka 0 0 0
Kd {kd}
Ks {ks}
Ns {ns}
d {d}
illum {illum}
{extra}"""

MTL_ENTRIES = [
    ("Su34_Airframe", "1.0 1.0 1.0", "0.12 0.12 0.12", 24, 1.0, 2,
     "map_Kd textures/donor_basecolor.png\n"
     "map_Ks textures/donor_roughness.png\n"
     "norm textures/donor_normal.png\n"),
    ("Su34_Glass", "0.62 0.72 0.78", "0.90 0.90 0.90", 200, 0.32, 4, ""),
    ("Su34_HUD", "0.00 0.80 0.01", "0.20 0.20 0.20", 120, 0.55, 4,
     "Ke 0.00 0.80 0.01\n"),
    ("Su34_Lights", "1.0 1.0 1.0", "0.10 0.10 0.10", 10, 1.0, 5,
     "Ke 1.0 1.0 1.0\n"),
]

CTYPE = {5120: ("b", 1), 5121: ("B", 1), 5122: ("h", 2), 5123: ("H", 2),
         5125: ("I", 4), 5126: ("f", 4)}
NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def load(path):
    data = open(path, "rb").read()
    _, _, length = struct.unpack_from("<III", data, 0)
    off, chunks = 12, []
    while off < length:
        clen, ctype = struct.unpack_from("<II", data, off)
        chunks.append((ctype, off + 8, clen))
        off += 8 + clen
    js = json.loads(data[chunks[0][1]:chunks[0][1] + chunks[0][2]].decode("utf-8"))
    return js, data[chunks[1][1]:chunks[1][1] + chunks[1][2]]


def accessor(js, bin_, idx):
    acc = js["accessors"][idx]
    fmt, size = CTYPE[acc["componentType"]]
    n = NCOMP[acc["type"]]
    bv = js["bufferViews"][acc["bufferView"]]
    start = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
    stride = bv.get("byteStride") or size * n
    raw = bin_[start:start + stride * acc["count"]]
    arr = np.frombuffer(raw, dtype=np.dtype(fmt), count=acc["count"] * n)
    arr = arr.reshape(acc["count"], n) if n > 1 else arr
    if stride != size * n:
        out = np.zeros((acc["count"], n), dtype=arr.dtype)
        for i in range(acc["count"]):
            o = i * stride
            out[i] = np.frombuffer(raw[o:o + size * n], dtype=np.dtype(fmt))
        arr = out
    return np.array(arr, dtype=np.float64)


def main():
    js, bin_ = load(SRC)
    os.makedirs(OUT_DIR, exist_ok=True)
    obj_path = os.path.join(OUT_DIR, "Su-34.obj")
    mtl_path = os.path.join(OUT_DIR, "Su-34.mtl")

    verts, uvs, normals = [], [], []
    vbase = 0
    body, stats = [], []
    for node in js["nodes"]:
        if "mesh" not in node:
            continue
        name = node.get("name", "part")
        mesh = js["meshes"][node["mesh"]]
        t = node.get("translation")
        r = node.get("rotation")
        s = node.get("scale")
        m = np.eye(4)
        if t:
            m[:3, 3] = t
        if r:  # quaternion xyzw
            x, y, z, w = r
            m[:3, :3] = np.array([
                [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
            ])
        if s:
            m[:3, :3] = m[:3, :3] @ np.diag(s)

        body.append(f"o {name}")
        cnt = 0
        for pr in mesh["primitives"]:
            mat_name = MATERIAL_NAMES.get(pr.get("material", 0), "Su34_Airframe")
            body.append("usemtl " + mat_name)
            pos = accessor(js, bin_, pr["attributes"]["POSITION"])
            pos = pos @ m[:3, :3].T + m[:3, 3]
            nrm = None
            if "NORMAL" in pr["attributes"]:
                nrm = accessor(js, bin_, pr["attributes"]["NORMAL"])
                nrm = nrm @ np.linalg.inv(m[:3, :3]).T
                ln = np.linalg.norm(nrm, axis=1, keepdims=True)
                nrm = nrm / np.maximum(ln, 1e-9)
            uv = (accessor(js, bin_, pr["attributes"]["TEXCOORD_0"])
                  if "TEXCOORD_0" in pr["attributes"] else None)
            idx = (accessor(js, bin_, pr["indices"]) if "indices" in pr
                   else np.arange(len(pos)))
            for p in pos:
                verts.append(tuple(p))
            if nrm is not None:
                for n in nrm:
                    normals.append(tuple(n))
            if uv is not None:
                for q in uv:
                    uvs.append(tuple(q))
            vidx = idx.astype(np.int64) + vbase + 1
            # positions, uvs and normals are appended in lockstep, so the
            # same absolute index addresses all three
            for k in range(0, len(vidx), 3):
                a, b, c = vidx[k:k + 3]
                if nrm is not None and uv is not None:
                    body.append(f"f {a}/{a}/{a} {b}/{b}/{b} {c}/{c}/{c}")
                elif uv is not None:
                    body.append(f"f {a}/{a} {b}/{b} {c}/{c}")
                else:
                    body.append(f"f {a} {b} {c}")
            vbase += len(pos)
            cnt += len(idx) // 3
        stats.append((name, cnt, np.array(pos).min(0), np.array(pos).max(0)))

    with open(mtl_path, "w") as f:
        f.write("# Su-34 donor materials - see tools/import_donor.py\n")
        for name, kd, ks, ns, alpha, illum, extra in MTL_ENTRIES:
            f.write(MTL_BODY.format(name=name, kd=kd, ks=ks, ns=ns,
                                    d=alpha, illum=illum, extra=extra))
            f.write("\n")

    with open(obj_path, "w") as f:
        f.write("# Su-34 donor model, converted from GLB\n")
        f.write(f"mtllib {os.path.basename(mtl_path)}\n")
        for p in verts:
            f.write("v %.5f %.5f %.5f\n" % p)
        for q in uvs:
            f.write("vt %.5f %.5f\n" % q)
        for n in normals:
            f.write("vn %.5f %.5f %.5f\n" % n)
        f.write("\n".join(body) + "\n")

    print(f"{len(verts)} verts, {len(uvs)} uv, {len(normals)} normals")
    for name, cnt, lo, hi in stats:
        print(f"{name:26s} {cnt:6d} tris  bbox {np.round(lo,2)} .. {np.round(hi,2)}")
    print("wrote", obj_path)


if __name__ == "__main__":
    main()
