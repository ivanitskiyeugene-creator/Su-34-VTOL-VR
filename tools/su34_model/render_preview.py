"""
Small headless software renderer used to preview the generated Su-34 OBJ.
No OpenGL, no display required - just numpy + Pillow.

Usage:
    python3 tools/su34_model/render_preview.py
"""
from __future__ import annotations

import math
import os
import sys
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OBJ = os.path.join(ROOT, "assets", "model", "su34.obj")
MTL = os.path.join(ROOT, "assets", "model", "su34.mtl")
OUT = os.path.join(ROOT, "docs", "model")


def parse_mtl(path: str) -> dict[str, dict]:
    mats: dict[str, dict] = {}
    cur = None
    for line in open(path, encoding="utf-8"):
        p = line.split()
        if not p:
            continue
        if p[0] == "newmtl":
            cur = p[1]
            mats[cur] = {"color": (0.7, 0.7, 0.7), "alpha": 1.0, "spec": 0.1}
        elif p[0] == "Kd" and cur:
            mats[cur]["color"] = tuple(float(x) for x in p[1:4])
        elif p[0] == "Ks" and cur:
            mats[cur]["spec"] = sum(float(x) for x in p[1:4]) / 3
        elif p[0] == "d" and cur:
            mats[cur]["alpha"] = float(p[1])
    return mats


def parse_obj(path: str):
    verts: list[tuple[float, float, float]] = []
    normals: list[tuple[float, float, float]] = []
    tris: list[tuple[int, int, int, str]] = []
    cur = "default"
    for line in open(path, encoding="utf-8"):
        p = line.split()
        if not p:
            continue
        if p[0] == "v":
            verts.append(tuple(float(x) for x in p[1:4]))
        elif p[0] == "vn":
            normals.append(tuple(float(x) for x in p[1:4]))
        elif p[0] == "usemtl":
            cur = p[1]
        elif p[0] == "f":
            idx = []
            for tok in p[1:]:
                a = tok.split("/")[0]
                idx.append(int(a) - 1)
            for k in range(1, len(idx) - 1):
                tris.append((idx[0], idx[k], idx[k + 1], cur))
    return np.array(verts, dtype=np.float64), np.array(normals, dtype=np.float64), tris


@dataclass
class Camera:
    eye: np.ndarray
    target: np.ndarray
    up: np.ndarray
    fov_deg: float
    width: int
    height: int

    def view(self):
        f = self.target - self.eye
        f = f / np.linalg.norm(f)
        r = np.cross(f, self.up)
        r = r / np.linalg.norm(r)
        u = np.cross(r, f)
        return f, r, u

    def project(self, pts: np.ndarray):
        f, r, u = self.view()
        rel = pts - self.eye
        z = rel @ f
        x = rel @ r
        y = rel @ u
        fov = math.radians(self.fov_deg)
        fl = 0.5 * self.height / math.tan(fov / 2)
        sx = self.width / 2 + (x / np.maximum(z, 1e-5)) * fl
        sy = self.height / 2 - (y / np.maximum(z, 1e-5)) * fl
        return np.stack([sx, sy, z], axis=1)


def render(verts, normals, tris, mats, cam: Camera, background=(28, 34, 42)) -> Image.Image:
    W, H = cam.width, cam.height
    img = np.zeros((H, W, 3), dtype=np.float64)
    # vertical gradient
    top = np.array([78, 98, 118], dtype=np.float64)
    bot = np.array([26, 32, 40], dtype=np.float64)
    for y in range(H):
        t = y / max(H - 1, 1)
        img[y, :, :] = top * (1 - t) + bot * t
    zbuf = np.full((H, W), np.inf)

    proj = cam.project(verts)
    face_n = np.cross(verts[:, None, :] - verts, verts - verts)  # placeholder
    del face_n

    # camera-space depth for sorting
    opaque = []
    transparent = []
    for (a, b, c, mat) in tris:
        pa, pb, pc = proj[a], proj[b], proj[c]
        if pa[2] <= 0.1 or pb[2] <= 0.1 or pc[2] <= 0.1:
            continue
        if max(pa[0], pb[0], pc[0]) < 0 or min(pa[0], pb[0], pc[0]) >= W:
            continue
        if max(pa[1], pb[1], pc[1]) < 0 or min(pa[1], pb[1], pc[1]) >= H:
            continue
        m = mats.get(mat, {"color": (0.7, 0.7, 0.7), "alpha": 1.0, "spec": 0.1})
        depth = (pa[2] + pb[2] + pc[2]) / 3
        item = (a, b, c, m, depth)
        if m.get("alpha", 1.0) < 0.99:
            transparent.append(item)
        else:
            opaque.append(item)

    light = np.array([-0.45, 0.75, 0.55])
    light = light / np.linalg.norm(light)
    fill = np.array([0.5, -0.2, -0.7])
    fill = fill / np.linalg.norm(fill)

    def shade(n, m):
        ndl = max(0.0, float(np.dot(n, light)))
        ndf = max(0.0, float(np.dot(n, fill)))
        amb = 0.42
        diff = 0.95 * ndl
        base = np.array(m["color"], dtype=np.float64)
        # simple sky/ground ambient tint
        tint = np.array([0.94, 0.99, 1.08])
        col = base * (amb * tint + diff) + base * 0.18 * ndf
        # specular
        view_dir = np.array([0.0, 0.0, 1.0])
        h = light + view_dir
        h = h / np.linalg.norm(h)
        sp = m.get("spec", 0.1) * max(0.0, float(np.dot(n, h))) ** 24
        col = col + sp * np.array([1.0, 1.0, 1.0])
        return np.clip(col, 0.0, 1.6)

    for (a, b, c, m, depth) in opaque:
        pa, pb, pc = proj[a], proj[b], proj[c]
        n = np.cross(verts[b] - verts[a], verts[c] - verts[a])
        ln = np.linalg.norm(n)
        if ln < 1e-12:
            continue
        n = n / ln
        # backface cull
        centroid = (verts[a] + verts[b] + verts[c]) / 3
        to_cam = cam.eye - centroid
        if np.dot(n, to_cam) < 0:
            continue
        minx = max(int(math.floor(min(pa[0], pb[0], pc[0]))), 0)
        maxx = min(int(math.ceil(max(pa[0], pb[0], pc[0]))), W - 1)
        miny = max(int(math.floor(min(pa[1], pb[1], pc[1]))), 0)
        maxy = min(int(math.ceil(max(pa[1], pb[1], pc[1]))), H - 1)
        if maxx < minx or maxy < miny:
            continue
        x = np.arange(minx, maxx + 1)
        y = np.arange(miny, maxy + 1)
        xx, yy = np.meshgrid(x, y)
        x0, y0 = pa[0], pa[1]
        x1, y1 = pb[0], pb[1]
        x2, y2 = pc[0], pc[1]
        den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(den) < 1e-9:
            continue
        w0 = ((y1 - y2) * (xx - x2) + (x2 - x1) * (yy - y2)) / den
        w1 = ((y2 - y0) * (xx - x2) + (x0 - x2) * (yy - y2)) / den
        w2 = 1.0 - w0 - w1
        inside = (w0 >= -1e-4) & (w1 >= -1e-4) & (w2 >= -1e-4)
        if not inside.any():
            continue
        z = w0 * pa[2] + w1 * pb[2] + w2 * pc[2]
        mask = inside & (z < zbuf[miny:maxy + 1, minx:maxx + 1])
        if not mask.any():
            continue
        col = shade(n, m)
        region = img[miny:maxy + 1, minx:maxx + 1]
        zb = zbuf[miny:maxy + 1, minx:maxx + 1]
        region[mask] = col * 255.0
        zb[mask] = z[mask]

    # transparent pass, back to front
    transparent.sort(key=lambda it: it[4], reverse=True)
    for (a, b, c, m, depth) in transparent:
        pa, pb, pc = proj[a], proj[b], proj[c]
        n = np.cross(verts[b] - verts[a], verts[c] - verts[a])
        ln = np.linalg.norm(n)
        if ln < 1e-12:
            continue
        n = n / ln
        centroid = (verts[a] + verts[b] + verts[c]) / 3
        if np.dot(n, cam.eye - centroid) < 0:
            n = -n
        minx = max(int(math.floor(min(pa[0], pb[0], pc[0]))), 0)
        maxx = min(int(math.ceil(max(pa[0], pb[0], pc[0]))), W - 1)
        miny = max(int(math.floor(min(pa[1], pb[1], pc[1]))), 0)
        maxy = min(int(math.ceil(max(pa[1], pb[1], pc[1]))), H - 1)
        if maxx < minx or maxy < miny:
            continue
        x = np.arange(minx, maxx + 1)
        y = np.arange(miny, maxy + 1)
        xx, yy = np.meshgrid(x, y)
        x0, y0 = pa[0], pa[1]
        x1, y1 = pb[0], pb[1]
        x2, y2 = pc[0], pc[1]
        den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(den) < 1e-9:
            continue
        w0 = ((y1 - y2) * (xx - x2) + (x2 - x1) * (yy - y2)) / den
        w1 = ((y2 - y0) * (xx - x2) + (x0 - x2) * (yy - y2)) / den
        w2 = 1.0 - w0 - w1
        inside = (w0 >= -1e-4) & (w1 >= -1e-4) & (w2 >= -1e-4)
        z = w0 * pa[2] + w1 * pb[2] + w2 * pc[2]
        mask = inside & (z < zbuf[miny:maxy + 1, minx:maxx + 1])
        if not mask.any():
            continue
        col = shade(n, m) * 255.0
        alpha = float(m.get("alpha", 1.0))
        region = img[miny:maxy + 1, minx:maxx + 1]
        region[mask] = region[mask] * (1 - alpha) + col * alpha

    out = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB")
    return out


def main() -> None:
    verts, normals, tris = parse_obj(OBJ)
    mats = parse_mtl(MTL)
    os.makedirs(OUT, exist_ok=True)
    W, H = 1100, 700
    views = {
        "quarter": Camera(np.array([24.0, 11.0, 26.0]), np.array([0.0, 0.0, -1.0]),
                          np.array([0.0, 1.0, 0.0]), 30, W, H),
        "side": Camera(np.array([40.0, 2.0, 0.0]), np.array([0.0, 0.2, 0.0]),
                       np.array([0.0, 1.0, 0.0]), 28, W, H),
        "top": Camera(np.array([0.0, 44.0, -1.0]), np.array([0.0, 0.0, -0.5]),
                      np.array([0.0, 0.0, 1.0]), 28, W, H),
        "front": Camera(np.array([0.0, 2.5, 40.0]), np.array([0.0, 0.3, 0.0]),
                        np.array([0.0, 1.0, 0.0]), 24, W, H),
    }
    images = {}
    for name, cam in views.items():
        img = render(verts, normals, tris, mats, cam)
        path = os.path.join(OUT, f"su34_{name}.png")
        img.save(path)
        images[name] = img
        print("wrote", path)

    # contact sheet
    sheet = Image.new("RGB", (W * 2, H * 2), (12, 15, 20))
    order = ["quarter", "side", "top", "front"]
    for i, name in enumerate(order):
        sheet.paste(images[name], ((i % 2) * W, (i // 2) * H))
    draw = ImageDraw.Draw(sheet)
    for i, name in enumerate(order):
        draw.text(((i % 2) * W + 18, (i // 2) * H + 16), f"Su-34  /  {name}", fill=(230, 235, 240))
    sheet_path = os.path.join(OUT, "su34_preview.png")
    sheet.save(sheet_path)
    print("wrote", sheet_path)


if __name__ == "__main__":
    main()
