"""Sanity check for the generated OBJ: bounding box, triangle count, materials."""
import os
import sys
from collections import Counter

import numpy as np

OBJ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "assets", "model", "su34.obj"))


def main(path=OBJ):
    verts, materials, tris = [], Counter(), 0
    cur = "default"
    degenerate = 0
    for line in open(path, encoding="utf-8"):
        p = line.split()
        if not p:
            continue
        if p[0] == "v":
            verts.append([float(x) for x in p[1:4]])
        elif p[0] == "usemtl":
            cur = p[1]
        elif p[0] == "f":
            materials[cur] += 1
            idx = [int(t.split("/")[0]) - 1 for t in p[1:]]
            tris += len(idx) - 2
            a, b, c = (np.array(verts[i]) for i in idx[:3])
            if np.linalg.norm(np.cross(b - a, c - a)) < 1e-12:
                degenerate += 1
    v = np.array(verts)
    lo, hi = v.min(axis=0), v.max(axis=0)
    size = hi - lo
    print("file        :", path)
    print("vertices    :", len(verts))
    print("triangles   :", tris)
    print("degenerate  :", degenerate)
    print("materials   :", len(materials))
    for name, count in materials.most_common():
        print(f"   {name:<18} {count}")
    print("bbox min    : %.2f %.2f %.2f" % tuple(lo))
    print("bbox max    : %.2f %.2f %.2f" % tuple(hi))
    print("length  (Z) : %.2f m" % size[2])
    print("wingspan(X) : %.2f m" % size[0])
    print("height  (Y) : %.2f m" % size[1])


if __name__ == "__main__":
    main(*sys.argv[1:])
