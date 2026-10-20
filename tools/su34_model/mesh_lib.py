"""
Tiny dependency-light mesh construction helpers.

Everything is built in *Unity* coordinates:
    +X = right wing
    +Y = up
    +Z = nose / forward

The output is a Wavefront OBJ with one material per logical part, which Unity
2020.3 imports natively as a hierarchy of MeshFilter/MeshRenderer objects.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Iterable, Sequence

import numpy as np

Vec3 = np.ndarray


def v(x: float, y: float, z: float) -> Vec3:
    return np.array([x, y, z], dtype=np.float64)


def normalize(a: Vec3) -> Vec3:
    n = np.linalg.norm(a)
    return a / n if n > 1e-12 else a


@dataclass
class Part:
    name: str
    material: str
    vertices: list[Vec3] = field(default_factory=list)
    faces: list[tuple[int, int, int]] = field(default_factory=list)
    smooth: bool = True
    # optional explicit per-vertex normals (used for hard-surface panels)
    normals: list[Vec3] | None = None

    def add_vertex(self, p: Sequence[float]) -> int:
        self.vertices.append(np.asarray(p, dtype=np.float64))
        return len(self.vertices) - 1

    def add_face(self, a: int, b: int, c: int) -> None:
        self.faces.append((a, b, c))

    def add_quad(self, a: int, b: int, c: int, d: int) -> None:
        self.faces.append((a, b, c))
        self.faces.append((a, c, d))

    def compute_normals(self) -> list[Vec3]:
        if self.normals is not None:
            return self.normals
        acc = [np.zeros(3) for _ in self.vertices]
        for ia, ib, ic in self.faces:
            a, b, c = self.vertices[ia], self.vertices[ib], self.vertices[ic]
            n = np.cross(b - a, c - a)  # area weighted
            acc[ia] += n
            acc[ib] += n
            acc[ic] += n
        out = []
        for n in acc:
            ln = np.linalg.norm(n)
            out.append(n / ln if ln > 1e-12 else np.array([0.0, 1.0, 0.0]))
        return out


@dataclass
class Mesh:
    parts: list[Part] = field(default_factory=list)

    @staticmethod
    def orient(part: Part, ref_fn: Callable[[Vec3], Vec3]) -> Part:
        """Flip triangles so their normals point away from a reference surface.

        ``ref_fn(face_center)`` returns a point that lies inside the volume; the
        face is flipped when its normal points towards that point. This makes
        the generators immune to winding-order mistakes.
        """
        fixed: list[tuple[int, int, int]] = []
        for ia, ib, ic in part.faces:
            a, b, c = part.vertices[ia], part.vertices[ib], part.vertices[ic]
            n = np.cross(b - a, c - a)
            center = (a + b + c) / 3.0
            if np.dot(n, center - ref_fn(center)) < 0:
                fixed.append((ia, ic, ib))
            else:
                fixed.append((ia, ib, ic))
        part.faces = fixed
        part.normals = None
        return part

    def new_part(self, name: str, material: str, smooth: bool = True) -> Part:
        p = Part(name=name, material=material, smooth=smooth)
        self.parts.append(p)
        return p

    # ------------------------------------------------------------------ lofts
    def loft(
        self,
        name: str,
        material: str,
        rings: list[list[Vec3]],
        closed_ring: bool = True,
        cap_start: bool = False,
        cap_end: bool = False,
        smooth: bool = True,
        skip: Callable[[int, int], bool] | None = None,
    ) -> Part:
        """Loft a list of equal-length rings into a tube/surface.

        ``skip(section_index, segment_index)`` can omit quads, which is how the
        cockpit opening is cut into the fuselage crown.
        """
        part = self.new_part(name, material, smooth)
        n = len(rings[0])
        idx: list[list[int]] = []
        for ring in rings:
            if len(ring) != n:
                raise ValueError("all rings must have the same vertex count")
            idx.append([part.add_vertex(p) for p in ring])

        segments = n if closed_ring else n - 1
        for r in range(len(rings) - 1):
            for i in range(segments):
                if skip is not None and skip(r, i):
                    continue
                j = (i + 1) % n
                a, b = idx[r][i], idx[r][j]
                c, d = idx[r + 1][j], idx[r + 1][i]
                part.add_quad(a, b, c, d)

        def cap(ring_index: int, flip: bool) -> None:
            ring = rings[ring_index]
            center = sum(ring) / len(ring)
            ci = part.add_vertex(center)
            ids = idx[ring_index]
            for i in range(segments):
                j = (i + 1) % n
                if flip:
                    part.add_face(ci, ids[j], ids[i])
                else:
                    part.add_face(ci, ids[i], ids[j])

        if cap_start:
            cap(0, False)
        if cap_end:
            cap(len(rings) - 1, True)
        return part

    # --------------------------------------------------------------- primitives
    def box(
        self,
        name: str,
        material: str,
        center: Sequence[float],
        size: Sequence[float],
        rotation: np.ndarray | None = None,
    ) -> Part:
        c = np.asarray(center, dtype=float)
        sx, sy, sz = (np.asarray(size, dtype=float) / 2.0)
        corners = [
            v(-sx, -sy, -sz), v(sx, -sy, -sz), v(sx, sy, -sz), v(-sx, sy, -sz),
            v(-sx, -sy, sz), v(sx, -sy, sz), v(sx, sy, sz), v(-sx, sy, sz),
        ]
        if rotation is not None:
            corners = [rotation @ p for p in corners]
        corners = [p + c for p in corners]
        part = self.new_part(name, material, smooth=False)
        ids = [part.add_vertex(p) for p in corners]
        for quad in [(0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0),
                     (4, 7, 6, 5), (0, 1, 2, 3)]:
            part.add_quad(*(ids[k] for k in quad))
        return part

    def cylinder(
        self,
        name: str,
        material: str,
        start: Sequence[float],
        end: Sequence[float],
        radius_start: float,
        radius_end: float | None = None,
        segments: int = 16,
        caps: bool = True,
        smooth: bool = True,
    ) -> Part:
        if radius_end is None:
            radius_end = radius_start
        a = np.asarray(start, dtype=float)
        b = np.asarray(end, dtype=float)
        axis = normalize(b - a)
        ref = np.array([0.0, 1.0, 0.0])
        if abs(np.dot(axis, ref)) > 0.95:
            ref = np.array([1.0, 0.0, 0.0])
        u = normalize(np.cross(ref, axis))
        w = normalize(np.cross(axis, u))
        rings: list[list[Vec3]] = []
        for p, rad in ((a, radius_start), (b, radius_end)):
            ring = []
            for k in range(segments):
                ang = 2 * math.pi * k / segments
                ring.append(p + u * (math.cos(ang) * rad) + w * (math.sin(ang) * rad))
            rings.append(ring)
        return self.loft(name, material, rings, cap_start=caps, cap_end=caps, smooth=smooth)

    def quad_strip(
        self,
        name: str,
        material: str,
        left: list[Vec3],
        right: list[Vec3],
        smooth: bool = False,
        double_sided: bool = False,
    ) -> Part:
        part = self.new_part(name, material, smooth)
        li = [part.add_vertex(p) for p in left]
        ri = [part.add_vertex(p) for p in right]
        for i in range(len(left) - 1):
            part.add_quad(li[i], li[i + 1], ri[i + 1], ri[i])
            if double_sided:
                part.add_quad(li[i], ri[i], ri[i + 1], li[i + 1])
        return part


# --------------------------------------------------------------------- profiles
def superellipse_ring(
    z: float,
    half_width: float,
    half_height: float,
    center_y: float,
    n: float = 2.2,
    count: int = 32,
    top_cut: tuple[float, float] | None = None,
) -> list[Vec3]:
    """A rounded-rectangle fuselage cross-section in the XY plane.

    ``top_cut`` removes vertices in an angular band (radians) so the loft can
    leave the canopy opening open instead of skinning over it.
    """
    pts: list[Vec3] = []
    for k in range(count):
        t = 2 * math.pi * k / count
        if top_cut is not None:
            lo, hi = top_cut
            if lo <= t <= hi:
                # collapse the skipped band to its edges (kept for indexing)
                t = lo if (t - lo) < (hi - t) else hi
        ct, st = math.cos(t), math.sin(t)
        x = half_width * math.copysign(abs(ct) ** (2.0 / n), ct)
        y = center_y + half_height * math.copysign(abs(st) ** (2.0 / n), st)
        pts.append(v(x, y, z))
    return pts


def airfoil_loop(
    le: Vec3,
    chord_dir: Vec3,
    thickness_dir: Vec3,
    chord: float,
    thickness: float,
    n: int = 10,
) -> list[Vec3]:
    """Closed symmetric NACA-style airfoil loop with split trailing edge."""
    xs = [i / (n - 1) for i in range(n)]
    upper = []
    lower = []
    for x in xs:
        yt = 5.0 * thickness * (
            0.2969 * math.sqrt(max(x, 0.0))
            - 0.126 * x
            - 0.3516 * x * x
            + 0.2843 * x ** 3
            - 0.1015 * x ** 4
        )
        upper.append(le + chord_dir * (-x * chord) + thickness_dir * (yt * chord))
        lower.append(le + chord_dir * (-x * chord) - thickness_dir * (yt * chord))
    # upper LE -> TE, then lower TE (coincident, split seam) -> LE (skip LE dup)
    loop = upper + list(reversed(lower))[1:-1]
    return loop


def lifting_surface(
    mesh: Mesh,
    name: str,
    material: str,
    sections: list[dict],
    span_dir: Vec3,
    thickness_dir: Vec3,
    chord_dir: Vec3,
    airfoil_n: int = 9,
    cap_root: bool = True,
    cap_tip: bool = True,
) -> Part:
    """Loft a wing / fin / stabiliser from spanwise sections.

    section keys: span (m), le (Vec3 = leading-edge point at this station),
                  chord (m), thickness (ratio)
    """
    rings: list[list[Vec3]] = []
    for s in sections:
        le = np.asarray(s["le"], dtype=float)
        rings.append(
            airfoil_loop(
                le,
                chord_dir=normalize(np.asarray(chord_dir, dtype=float)),
                thickness_dir=normalize(np.asarray(thickness_dir, dtype=float)),
                chord=s["chord"],
                thickness=s["thickness"],
                n=airfoil_n,
            )
        )
    return mesh.loft(
        name,
        material,
        rings,
        closed_ring=True,
        cap_start=cap_root,
        cap_end=cap_tip,
        smooth=True,
    )


# ------------------------------------------------------------------------ OBJ IO
def write_obj(path: str, mesh: Mesh, mtl_name: str = "su34.mtl") -> None:
    lines: list[str] = [
        "# Su-34 model for VTOL VR - generated by tools/su34_model/generate_su34.py",
        "# Units: metres. Axes: +X right, +Y up, +Z nose.",
        f"mtllib {mtl_name}",
    ]
    vcount = 0
    for part in mesh.parts:
        lines.append(f"o {part.name}")
        lines.append(f"usemtl {part.material}")
        normals = part.compute_normals()
        # (position, normal) dedup table keeps the file compact while preserving
        # hard edges because flat parts get per-face normals below.
        key_to_index: dict[tuple, int] = {}
        tri_entries: list[tuple[tuple, tuple, tuple]] = []
        for ia, ib, ic in part.faces:
            face_n = normalize(np.cross(part.vertices[ib] - part.vertices[ia],
                                        part.vertices[ic] - part.vertices[ia]))
            if not part.smooth:
                entry = []
                for i in (ia, ib, ic):
                    entry.append((tuple(np.round(part.vertices[i], 6)),
                                  tuple(np.round(face_n, 6))))
                tri_entries.append(tuple(entry))
            else:
                entry = []
                for i in (ia, ib, ic):
                    nn = normals[i]
                    # guard against degenerate averaged normals
                    if np.linalg.norm(nn) < 1e-9:
                        nn = face_n
                    entry.append((tuple(np.round(part.vertices[i], 6)),
                                  tuple(np.round(nn, 6))))
                tri_entries.append(tuple(entry))

        # emit vertices/normals
        entries: list[tuple] = []
        for tri in tri_entries:
            for e in tri:
                key = (e[0], e[1])
                if key not in key_to_index:
                    key_to_index[key] = vcount
                    vcount += 1
                    lines.append("v %.6f %.6f %.6f" % e[0])
                    lines.append("vn %.6f %.6f %.6f" % e[1])
                entries.append((key, e))
        # faces in the same order as generated
        face_lines = []
        for k in range(0, len(entries), 3):
            a = key_to_index[entries[k][0]] + 1
            b = key_to_index[entries[k + 1][0]] + 1
            c = key_to_index[entries[k + 2][0]] + 1
            face_lines.append(f"f {a}//{a} {b}//{b} {c}//{c}")
        lines.extend(face_lines)

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def write_mtl(path: str, materials: dict[str, dict]) -> None:
    out = ["# Su-34 material library"]
    for name, m in materials.items():
        out.append(f"newmtl {name}")
        out.append("Ka 0.0 0.0 0.0")
        out.append("Kd %.4f %.4f %.4f" % tuple(m["color"]))
        out.append("Ks %.4f %.4f %.4f" % tuple(m.get("specular", (0.15, 0.15, 0.15))))
        out.append("Ns %.1f" % m.get("shininess", 24.0))
        out.append("d %.4f" % m.get("alpha", 1.0))
        out.append("illum %d" % (2 if m.get("alpha", 1.0) < 1.0 else 2))
        out.append("")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
