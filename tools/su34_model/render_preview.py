"""
Headless software renderer used to preview the generated Su-34 OBJ.

Textured (samples the MTL map_Kd images), no OpenGL and no display required:
just numpy + Pillow. Used to check the model without opening Unity.

Usage:
    python3 tools/su34_model/render_preview.py
Out:
    docs/model/su34_{quarter,side,top,front}.png and su34_preview.png
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OBJ = os.path.join(ROOT, "assets", "model", "su34.obj")
MTL = os.path.join(ROOT, "assets", "model", "su34.mtl")
OUT = os.path.join(ROOT, "docs", "model")

W, H = 1280, 760
SS = 2  # supersampling factor


# ------------------------------------------------------------------- materials
def parse_mtl(path: str) -> dict[str, dict]:
    mats: dict[str, dict] = {}
    cur = None
    base = os.path.dirname(path)
    for line in open(path, encoding="utf-8"):
        p = line.split()
        if not p:
            continue
        if p[0] == "newmtl":
            cur = p[1]
            mats[cur] = {"color": (0.7, 0.7, 0.7), "alpha": 1.0, "spec": 0.1,
                         "tex": None, "tile": 1.0}
        elif p[0] == "Kd" and cur:
            mats[cur]["color"] = tuple(float(x) for x in p[1:4])
        elif p[0] == "Ks" and cur:
            mats[cur]["spec"] = sum(float(x) for x in p[1:4]) / 3
        elif p[0] == "d" and cur:
            mats[cur]["alpha"] = float(p[1])
        elif p[0] == "map_Kd" and cur:
            tex_path = os.path.join(base, " ".join(p[1:]))
            if os.path.exists(tex_path):
                rgba = Image.open(tex_path).convert("RGBA")
                arr = np.asarray(rgba).astype(np.float32) / 255.0
                mats[cur]["tex"] = arr[..., :3]
                mats[cur]["tex_alpha"] = arr[..., 3]
                if arr[..., 3].min() < 0.99:
                    mats[cur]["alpha"] = 1.0  # handled per texel
    return mats


def parse_obj(path: str):
    verts: list[tuple[float, float, float]] = []
    uvs: list[tuple[float, float]] = []
    normals: list[tuple[float, float, float]] = []
    tris: list[tuple] = []
    cur = "default"
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
        elif p[0] == "usemtl":
            cur = p[1]
        elif p[0] == "f":
            idx = []
            for tok in p[1:]:
                parts = tok.split("/")
                a = int(parts[0]) - 1
                t = int(parts[1]) - 1 if len(parts) > 1 and parts[1] else -1
                n = int(parts[2]) - 1 if len(parts) > 2 and parts[2] else -1
                idx.append((a, t, n))
            for k in range(1, len(idx) - 1):
                tri = idx[0] + idx[k] + idx[k + 1]
                tris.append((*tri, cur))
    return (np.array(verts, dtype=np.float64),
            np.array(uvs, dtype=np.float64) if uvs else np.zeros((0, 2)),
            np.array(normals, dtype=np.float64) if normals else np.zeros((0, 3)),
            tris)


# ---------------------------------------------------------------------- camera
@dataclass
class Camera:
    eye: np.ndarray
    target: np.ndarray
    up: np.ndarray
    fov_deg: float

    def basis(self):
        f = self.target - self.eye
        f = f / np.linalg.norm(f)
        r = np.cross(f, self.up)
        r = r / np.linalg.norm(r)
        u = np.cross(r, f)
        return f, r, u

    def project(self, pts: np.ndarray, width: int, height: int):
        f, r, u = self.basis()
        rel = pts - self.eye
        z = rel @ f
        x = rel @ r
        y = rel @ u
        fl = 0.5 * height / math.tan(math.radians(self.fov_deg) / 2)
        sx = width / 2 + (x / np.maximum(z, 1e-4)) * fl
        sy = height / 2 - (y / np.maximum(z, 1e-4)) * fl
        return np.stack([sx, sy, z], axis=1)


# --------------------------------------------------------------------- renderer
def render(verts, uvs, normals, tris, mats, cam: Camera, width: int, height: int,
           shadow: bool = True, ambient: float = 0.40) -> Image.Image:
    img = np.zeros((height, width, 3), dtype=np.float64)
    top = np.array([92, 112, 132], dtype=np.float64)
    bot = np.array([22, 27, 34], dtype=np.float64)
    for y in range(height):
        t = y / max(height - 1, 1)
        img[y, :, :] = top * (1 - t) + bot * t

    zbuf = np.full((height, width), np.inf)
    proj = cam.project(verts, width, height)

    light = np.array([-0.42, 0.78, 0.46])
    light = light / np.linalg.norm(light)
    fill = np.array([0.55, -0.15, -0.60])
    fill = fill / np.linalg.norm(fill)

    opaque, transparent = [], []
    for tri in tris:
        a, ta, na, b, tb, nb, c, tc, nc, mat = tri
        pa, pb, pc = proj[a], proj[b], proj[c]
        if min(pa[2], pb[2], pc[2]) <= 0.15:
            continue
        if max(pa[0], pb[0], pc[0]) < 0 or min(pa[0], pb[0], pc[0]) >= width:
            continue
        if max(pa[1], pb[1], pc[1]) < 0 or min(pa[1], pb[1], pc[1]) >= height:
            continue
        m = mats.get(mat) or {"color": (0.7, 0.7, 0.7), "alpha": 1.0, "spec": 0.1,
                              "tex": None}
        item = (a, b, c, ta, tb, tc, na, nb, nc, m, (pa[2] + pb[2] + pc[2]) / 3)
        if m.get("alpha", 1.0) < 0.99:
            transparent.append(item)
        else:
            opaque.append(item)

    def shade(n, m, texel=None):
        base = texel if texel is not None else np.array(m["color"], dtype=np.float64)
        ndl = max(0.0, float(np.dot(n, light)))
        ndf = max(0.0, float(np.dot(n, fill)))
        amb = ambient
        col = base * (amb + 0.95 * ndl) + base * 0.16 * ndf
        h = light + np.array([0.0, 0.0, 1.0])
        h /= np.linalg.norm(h)
        col = col + m.get("spec", 0.1) * max(0.0, float(np.dot(n, h))) ** 28
        return col

    def rasterize(items, transparent_pass: bool):
        for (a, b, c, ta, tb, tc, na, nb, nc, m, _depth) in items:
            pa, pb, pc = proj[a], proj[b], proj[c]
            n = np.cross(verts[b] - verts[a], verts[c] - verts[a])
            ln = np.linalg.norm(n)
            if ln < 1e-12:
                continue
            n = n / ln
            centroid = (verts[a] + verts[b] + verts[c]) / 3
            facing = np.dot(n, cam.eye - centroid)
            # Two-sided shading. Closed shells keep their near surface in front
            # of the z-buffer anyway, and grazing plates (fins and wings seen
            # almost edge-on) no longer dissolve into a comb of gaps.
            if facing < 0:
                n = -n

            x0, y0, z0 = pa[0], pa[1], pa[2]
            x1, y1, z1 = pb[0], pb[1], pb[2]
            x2, y2, z2 = pc[0], pc[1], pc[2]
            den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
            if abs(den) < 1e-12:
                continue

            # Only truly degenerate triangles are dropped. Thin-but-valid ones
            # must stay: they are what makes grazing surfaces (fin roots, wing
            # skins seen edge-on) render as a solid silhouette instead of a
            # comb of stripes.
            if abs(den) < 1e-6:
                continue

            minx = max(int(math.floor(min(x0, x1, x2))), 0)
            maxx = min(int(math.ceil(max(x0, x1, x2))), width - 1)
            miny = max(int(math.floor(min(y0, y1, y2))), 0)
            maxy = min(int(math.ceil(max(y0, y1, y2))), height - 1)
            if maxx < minx or maxy < miny:
                continue
            ys, xs = np.mgrid[miny:maxy + 1, minx:maxx + 1]
            w0 = ((y1 - y2) * (xs - x2) + (x2 - x1) * (ys - y2)) / den
            w1 = ((y2 - y0) * (xs - x2) + (x0 - x2) * (ys - y2)) / den
            w2 = 1.0 - w0 - w1
            inside = (w0 >= -1e-4) & (w1 >= -1e-4) & (w2 >= -1e-4)
            if not inside.any():
                continue
            z = w0 * z0 + w1 * z1 + w2 * z2
            zb = zbuf[miny:maxy + 1, minx:maxx + 1]
            mask = inside & (z < zb)
            if not mask.any():
                continue
            cut = None

            tex = m.get("tex")
            tex_alpha = m.get("tex_alpha")
            texels = None
            if tex is not None and ta >= 0 and tb >= 0 and tc >= 0:
                ua, va = uvs[ta]
                ub, vb = uvs[tb]
                uc, vc = uvs[tc]
                iz = 1.0 / np.maximum(z, 1e-6)
                uu = (w0 * ua * iz + w1 * ub * iz + w2 * uc * iz) * z
                vv = (w0 * va * iz + w1 * vb * iz + w2 * vc * iz) * z
                th, tw = tex.shape[:2]
                px = np.clip((uu % 1.0) * (tw - 1), 0, tw - 1).astype(np.int32)
                py = np.clip((1.0 - (vv % 1.0)) * (th - 1), 0, th - 1).astype(np.int32)
                texels = tex[py, px]
                if tex_alpha is not None:
                    cut = tex_alpha[py, px] > 0.5

            if normals.shape[0]:
                npx = (w0[..., None] * normals[na] + w1[..., None] * normals[nb]
                       + w2[..., None] * normals[nc])
            else:
                npx = np.broadcast_to(n, (mask.shape[0], mask.shape[1], 3))
            ln = np.linalg.norm(npx, axis=2, keepdims=True)
            npx = npx / np.maximum(ln, 1e-9)

            ndl = np.clip(npx @ light, 0.0, None)
            ndf = np.clip(npx @ fill, 0.0, None)
            half = light + np.array([0.0, 0.0, 1.0])
            half /= np.linalg.norm(half)
            spec = m.get("spec", 0.1) * np.clip(npx @ half, 0.0, None) ** 28
            tint = (ambient + 0.95 * ndl + 0.16 * ndf)[..., None]

            if texels is not None:
                lit = texels * tint + spec[..., None]
            else:
                colour = np.array(m["color"], dtype=np.float64)
                lit = colour[None, None, :] * tint + spec[..., None]

            if cut is not None:
                mask &= cut
                if not mask.any():
                    continue

            region = img[miny:maxy + 1, minx:maxx + 1]
            if transparent_pass:
                alpha = float(m.get("alpha", 1.0))
                region[mask] = region[mask] * (1 - alpha) + np.clip(lit, 0, 1.4)[mask] * alpha
            else:
                region[mask] = np.clip(lit, 0, 1.4)[mask] * 1.15 * 255.0
            zb[mask] = z[mask]

    rasterize(opaque, False)
    transparent.sort(key=lambda it: it[7], reverse=True)
    rasterize(transparent, True)

    out = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB")

    return out


def add_ground_shadow(img: Image.Image, proj, verts, tris) -> Image.Image:
    """Cheap fake: project every vertex onto y = -3.0 and darken the floor."""
    mask = Image.new("L", img.size, 0)
    d = ImageDraw.Draw(mask)
    ground = -2.95
    height, width = img.size[1], img.size[0]
    for tri in tris:
        a, b, c = tri[0], tri[2], tri[4]
        pts = []
        ok = True
        for i in (a, b, c):
            p = verts[i].copy()
            if p[1] < ground:
                ok = False
                break
            p[1] = ground
            q = proj[i][:2] + np.array([0.0, 1.0]) * (p[1] - verts[i][1]) * 0.0  # placeholder
            pts.append((q[0], q[1]))
        if ok and len(pts) == 3:
            d.polygon(pts, fill=90)
    mask = mask.filter(ImageFilter.GaussianBlur(9))
    shadow = Image.composite(Image.new("RGB", img.size, (0, 0, 0)), img, mask.point(lambda v: int(v * 0.55)))
    return shadow


def main() -> None:
    verts, uvs, normals, tris = parse_obj(OBJ)
    mats = parse_mtl(MTL)
    os.makedirs(OUT, exist_ok=True)

    w, h = W * SS, H * SS
    views = {
        "quarter": Camera(np.array([21.0, 8.5, 24.0]), np.array([0.0, -0.2, -1.0]),
                          np.array([0.0, 1.0, 0.0]), 30),
        "side": Camera(np.array([38.0, 1.2, 0.6]), np.array([0.0, -0.1, 0.6]),
                       np.array([0.0, 1.0, 0.0]), 28),
        "top": Camera(np.array([0.0, 52.0, -0.5]), np.array([0.0, 0.0, -0.5]),
                      np.array([0.0, 0.0, 1.0]), 28),
        "front": Camera(np.array([0.0, 1.4, 40.0]), np.array([0.0, -0.1, 0.0]),
                        np.array([0.0, 1.0, 0.0]), 22),
    }
    images = {}
    for name, cam in views.items():
        print("rendering", name, "...")
        img = render(verts, uvs, normals, tris, mats, cam, w, h)
        img = img.resize((W, H), Image.LANCZOS)
        path = os.path.join(OUT, f"su34_{name}.png")
        img.save(path)
        images[name] = img
        print("  wrote", path)

    sheet = Image.new("RGB", (W * 2, H * 2), (12, 15, 20))
    order = ["quarter", "side", "top", "front"]
    for i, name in enumerate(order):
        sheet.paste(images[name], ((i % 2) * W, (i // 2) * H))
    draw = ImageDraw.Draw(sheet)
    for i, name in enumerate(order):
        draw.text(((i % 2) * W + 18, (i // 2) * H + 16), f"Su-34  /  {name}", fill=(235, 238, 242))
    sheet_path = os.path.join(OUT, "su34_preview.png")
    sheet.save(sheet_path)
    print("wrote", sheet_path)

    clay_sheet(verts, uvs, normals, tris, mats)
    cockpit_sheet(verts, uvs, normals, tris, mats)


def clay_sheet(verts, uvs, normals, tris, mats) -> None:
    """Same four views, one neutral material: judges shape, not camouflage.

    Textures are dropped and every material is replaced by a light grey clay,
    except the glass, which stays transparent so the canopy silhouette reads.
    """
    clay = {}
    for name in mats:
        if "Glass" in name:
            clay[name] = {"color": (0.55, 0.62, 0.68), "spec": 0.2, "alpha": 0.35,
                          "tex": None, "tex_alpha": None}
        elif "HUD" in name or "MFD" in name:
            clay[name] = {"color": (0.18, 0.20, 0.22), "spec": 0.3, "alpha": 1.0,
                          "tex": None, "tex_alpha": None}
        else:
            clay[name] = {"color": (0.72, 0.73, 0.75), "spec": 0.18, "alpha": 1.0,
                          "tex": None, "tex_alpha": None}

    views = {
        "quarter": Camera(np.array([21.0, 8.5, 24.0]), np.array([0.0, -0.2, -1.0]),
                          np.array([0.0, 1.0, 0.0]), 30),
        "side": Camera(np.array([38.0, 1.2, 0.6]), np.array([0.0, -0.1, 0.6]),
                       np.array([0.0, 1.0, 0.0]), 28),
        "top": Camera(np.array([0.0, 52.0, -0.5]), np.array([0.0, 0.0, -0.5]),
                      np.array([0.0, 0.0, 1.0]), 28),
        "front": Camera(np.array([0.0, 1.4, 40.0]), np.array([0.0, -0.1, 0.0]),
                        np.array([0.0, 1.0, 0.0]), 22),
    }
    w, h = W * SS, H * SS
    panels = []
    for name, cam in views.items():
        img = render(verts, uvs, normals, tris, clay, cam, w, h, ambient=0.55)
        panels.append((name, img.resize((W, H), Image.LANCZOS)))

    sheet = Image.new("RGB", (W * 2, H * 2), (12, 15, 20))
    order = ["quarter", "side", "top", "front"]
    by_name = dict(panels)
    for i, name in enumerate(order):
        sheet.paste(by_name[name], ((i % 2) * W, (i // 2) * H))
    draw = ImageDraw.Draw(sheet)
    for i, name in enumerate(order):
        draw.text(((i % 2) * W + 18, (i // 2) * H + 16), f"Su-34  /  {name}  (clay)",
                  fill=(235, 238, 242))
    path = os.path.join(OUT, "su34_clay.png")
    sheet.save(path)
    print("wrote", path)


def cockpit_sheet(verts, uvs, normals, tris, mats) -> None:
    """Two-crew cockpit sheet: bubble, interior, pilot and WSO eye views."""
    glass = ("Su34_Glass",)
    cw, ch = 1000, 700
    shots = [
        ("canopy - two crew side by side", False,
         Camera(np.array([3.2, 3.6, 3.4]), np.array([0.0, 0.7, 6.4]),
                np.array([0.0, 1.0, 0.0]), 44), 0.55),
        ("interior - glass hidden", True,
         Camera(np.array([1.9, 1.75, 4.9]), np.array([-0.05, 0.55, 6.9]),
                np.array([0.0, 1.0, 0.0]), 58), 0.90),
        ("two seats from above, glass hidden", True,
         Camera(np.array([0.0, 3.30, 4.95]), np.array([0.0, 0.60, 6.75]),
                np.array([0.0, 0.0, 1.0]), 52), 0.85),
        ("crew stations from the windscreen, glass hidden", True,
         Camera(np.array([0.0, 1.55, 7.95]), np.array([0.0, 0.90, 5.40]),
                np.array([0.0, 1.0, 0.0]), 66), 0.85),
    ]
    panels = []
    for label, drop_glass, cam, amb in shots:
        subset = tris
        if drop_glass:
            subset = [t for t in tris if t[9] not in glass]
        img = render(verts, uvs, normals, subset, mats, cam, cw, ch, ambient=amb)
        panels.append((label, img))

    pad = 14
    sheet = Image.new("RGB", (cw * 2 + pad, ch * 2 + pad), (12, 15, 20))
    draw_pos = []
    for i, (label, img) in enumerate(panels):
        x = (i % 2) * (cw + pad)
        y = (i // 2) * (ch + pad)
        sheet.paste(img, (x, y))
        draw_pos.append((x, y, label))
    draw = ImageDraw.Draw(sheet)
    for x, y, label in draw_pos:
        draw.text((x + 18, y + 16), "Su-34  /  " + label, fill=(235, 238, 242))
    path = os.path.join(OUT, "su34_cockpit.png")
    sheet.save(path)
    print("wrote", path)


if __name__ == "__main__":
    main()
