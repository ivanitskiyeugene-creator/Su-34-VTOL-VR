"""
Tiny dependency-light mesh construction helpers (numpy only).

Everything is built in *Unity* coordinates:
    +X = right wing
    +Y = up
    +Z = nose / forward

The output is a Wavefront OBJ + MTL with per-material textures, which Unity
2020.3 imports natively as a hierarchy of MeshFilter/MeshRenderer objects.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Iterable, Sequence

import numpy as np

Vec3 = np.ndarray
UV = tuple[float, float]


def v(x: float, y: float, z: float) -> Vec3:
    return np.array([x, y, z], dtype=np.float64)


def normalize(a: Vec3) -> Vec3:
    n = np.linalg.norm(a)
    return a / n if n > 1e-12 else a


# --------------------------------------------------------------------- curves
def catmull_rom(points: np.ndarray, samples: int) -> np.ndarray:
    """Uniform Catmull-Rom through ``points`` (keeps the end points)."""
    pts = np.asarray(points, dtype=np.float64)
    if len(pts) < 3:
        return pts
    padded = np.vstack([pts[0], pts, pts[-1]])
    out = []
    spans = len(pts) - 1
    per_span = max(1, samples // spans)
    for i in range(spans):
        p0, p1, p2, p3 = padded[i], padded[i + 1], padded[i + 2], padded[i + 3]
        for k in range(per_span):
            t = k / per_span
            t2, t3 = t * t, t * t * t
            out.append(
                0.5 * ((2 * p1)
                       + (-p0 + p2) * t
                       + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                       + (-p0 + 3 * p1 - 3 * p2 + p3) * t3)
            )
    out.append(pts[-1])
    return np.array(out)


@dataclass
class Part:
    name: str
    material: str
    vertices: list[Vec3] = field(default_factory=list)
    faces: list[tuple[int, int, int]] = field(default_factory=list)
    smooth: bool = True
    normals: list[Vec3] | None = None
    #: one (uv_a, uv_b, uv_c) per face; filled by box_uv() or by hand (decals)
    face_uvs: list[tuple[UV, UV, UV]] = field(default_factory=list)

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
        face is flipped when its normal points towards that point.
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
        part.face_uvs = []
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
        """Loft a list of equal-length rings into a tube/surface."""
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

    def quad(
        self,
        name: str,
        material: str,
        corners: list[Vec3],
        uvs: list[UV] | None = None,
    ) -> Part:
        """Explicit quad (used for decals where UVs must be authored)."""
        part = self.new_part(name, material, smooth=False)
        ids = [part.add_vertex(p) for p in corners]
        part.add_quad(ids[0], ids[1], ids[2], ids[3])
        if uvs is not None:
            a, b, c, d = uvs
            part.face_uvs = [(a, b, c), (a, c, d)]
        return part


# --------------------------------------------------------------------- profiles
def superellipse_ring(
    z: float,
    half_width: float,
    half_height: float,
    center_y: float,
    n: float = 2.2,
    count: int = 32,
) -> list[Vec3]:
    """A rounded-rectangle fuselage cross-section in the XY plane."""
    pts: list[Vec3] = []
    for k in range(count):
        t = 2 * math.pi * k / count
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
    """Closed symmetric NACA-style airfoil loop with a blunt trailing edge."""
    xs = [i / (n - 1) for i in range(n)]
    upper, lower = [], []
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
    # Walk the profile as a closed loop: upper surface LE->TE, then the lower
    # surface TE->LE.  The final lower LE point is the same location as the
    # first upper point, so it is dropped to avoid a duplicated vertex (which
    # used to fold the loft into degenerate slivers).  Keeping both TE points
    # gives the blunt trailing edge the real aircraft has.
    return upper + list(reversed(lower))[:-1]


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

    section keys: le (Vec3 = leading-edge point at this station),
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
    return mesh.loft(name, material, rings, closed_ring=True,
                     cap_start=cap_root, cap_end=cap_tip, smooth=True)


# ------------------------------------------------------------------------ UVs
def box_uv(part: Part, tile_size: float = 5.0, offset: tuple[float, float] = (0.0, 0.0)) -> None:
    """World-space box projection: 1 UV unit = ``tile_size`` metres.

    Camouflage and panel lines then keep a constant physical size across the
    whole aircraft, which is what makes a tiling texture read as "skin" rather
    than as a repeating pattern.
    """
    uvs: list[tuple[UV, UV, UV]] = []
    for ia, ib, ic in part.faces:
        a, b, c = part.vertices[ia], part.vertices[ib], part.vertices[ic]
        n = np.cross(b - a, c - a)
        if np.linalg.norm(n) < 1e-12:
            uvs.append(((0.0, 0.0), (0.0, 0.0), (0.0, 0.0)))
            continue
        n = abs(n / np.linalg.norm(n))
        axis = int(np.argmax(n))  # 0 -> YZ plane, 1 -> XZ, 2 -> XY
        if axis == 0:
            pick = lambda p: (p[2], p[1])
        elif axis == 1:
            pick = lambda p: (p[0], p[2])
        else:
            pick = lambda p: (p[0], p[1])
        uvs.append(tuple(
            ((pick(p)[0] / tile_size) + offset[0], (pick(p)[1] / tile_size) + offset[1])
            for p in (a, b, c)
        ))
    part.face_uvs = uvs  # type: ignore[assignment]


def apply_box_uv(mesh: Mesh, tile_size: float = 5.0) -> None:
    for part in mesh.parts:
        if not part.face_uvs:
            box_uv(part, tile_size)


# ------------------------------------------------------------------------ OBJ IO
def write_obj(path: str, mesh: Mesh, mtl_name: str = "su34.mtl") -> None:
    v_lines: list[str] = []
    vt_lines: list[str] = []
    vn_lines: list[str] = []
    body: list[str] = []
    v_index: dict[tuple, int] = {}
    vt_index: dict[tuple, int] = {}
    vn_index: dict[tuple, int] = {}

    def idx_v(p) -> int:
        key = tuple(np.round(p, 5))
        if key not in v_index:
            v_index[key] = len(v_lines) + 1
            v_lines.append("v %.5f %.5f %.5f" % key)
        return v_index[key]

    def idx_vt(uv) -> int:
        key = (round(uv[0], 5), round(uv[1], 5))
        if key not in vt_index:
            vt_index[key] = len(vt_lines) + 1
            vt_lines.append("vt %.5f %.5f" % key)
        return vt_index[key]

    def idx_vn(n) -> int:
        key = tuple(np.round(n, 5))
        if key not in vn_index:
            vn_index[key] = len(vn_lines) + 1
            vn_lines.append("vn %.5f %.5f %.5f" % key)
        return vn_index[key]

    for part in mesh.parts:
        normals = part.compute_normals()
        uvs = part.face_uvs
        use_uv = len(uvs) == len(part.faces)
        body.append(f"o {part.name}")
        body.append(f"usemtl {part.material}")
        for fi, (ia, ib, ic) in enumerate(part.faces):
            a, b, c = part.vertices[ia], part.vertices[ib], part.vertices[ic]
            face_n = normalize(np.cross(b - a, c - a))
            corners = []
            for k, vi in enumerate((ia, ib, ic)):
                if part.smooth:
                    n = normals[vi]
                    if np.linalg.norm(n) < 1e-9:
                        n = face_n
                else:
                    n = face_n
                uv = uvs[fi][k] if use_uv else (0.0, 0.0)
                corners.append((idx_v(part.vertices[vi]), idx_vt(uv), idx_vn(n)))
            body.append("f %d/%d/%d %d/%d/%d %d/%d/%d" % (
                corners[0][0], corners[0][1], corners[0][2],
                corners[1][0], corners[1][1], corners[1][2],
                corners[2][0], corners[2][1], corners[2][2],
            ))

    lines = [
        "# Su-34 model for VTOL VR - generated by tools/su34_model/generate_su34.py",
        "# Units: metres. Axes: +X right, +Y up, +Z nose.",
        f"mtllib {mtl_name}",
    ]
    lines += v_lines + vt_lines + vn_lines + body
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
        if m.get("map"):
            out.append("map_Kd %s" % m["map"])
        if m.get("map_alpha"):
            out.append("map_d %s" % m["map_alpha"])
        out.append("")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
