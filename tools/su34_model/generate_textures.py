"""
Procedural skin textures for the Su-34 model.

Everything is generated from scratch with Pillow/numpy: no photos, no game
assets. The textures tile in world space (the OBJ uses box-projected UVs at
5 metres per tile), so camouflage and panel lines keep a constant physical
size across the whole airframe.

Run:  python3 tools/su34_model/generate_textures.py
Out:  assets/model/textures/*.png
"""
from __future__ import annotations

import math
import os
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

OUT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..",
                                   "assets", "model", "textures"))
SIZE = 1024


# --------------------------------------------------------------------- helpers
def _wrap(offset_rng=((-1, 0, 1), (-1, 0, 1))):
    for dx in offset_rng[0]:
        for dy in offset_rng[1]:
            yield dx, dy


def poly(draw, pts, fill):
    for dx, dy in _wrap():
        draw.polygon([(x + dx * SIZE, y + dy * SIZE) for x, y in pts], fill=fill)


def line(draw, p0, p1, fill, width=2):
    for dx, dy in _wrap():
        draw.line([(p0[0] + dx * SIZE, p0[1] + dy * SIZE),
                   (p1[0] + dx * SIZE, p1[1] + dy * SIZE)], fill=fill, width=width)


def ellipse(draw, box, fill):
    for dx, dy in _wrap():
        draw.ellipse([box[0] + dx * SIZE, box[1] + dy * SIZE,
                      box[2] + dx * SIZE, box[3] + dy * SIZE], fill=fill)


def rect(draw, box, fill):
    for dx, dy in _wrap():
        draw.rectangle([box[0] + dx * SIZE, box[1] + dy * SIZE,
                        box[2] + dx * SIZE, box[3] + dy * SIZE], fill=fill)


def blob(rng: random.Random, cx: float, cy: float, r: float, n: int = 7):
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        rr = r * rng.uniform(0.62, 1.25)
        pts.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr * rng.uniform(0.55, 1.0)))
    return pts


def noise_layer(seed: int, scale: int = 3, blur: float = 2.0) -> Image.Image:
    rng = np.random.default_rng(seed)
    small = rng.normal(0.5, 0.16, (SIZE // scale, SIZE // scale))
    small = np.clip(small, 0, 1)
    img = Image.fromarray((small * 255).astype(np.uint8), "L").resize((SIZE, SIZE), Image.BICUBIC)
    return img.filter(ImageFilter.GaussianBlur(blur))


def streaks(img: Image.Image, seed: int, strength: int, direction: int = 1) -> Image.Image:
    """Subtle soot / oil streaks, as a darkening layer."""
    rng = random.Random(seed)
    layer = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for _ in range(90):
        x = rng.uniform(0, SIZE)
        y = rng.uniform(0, SIZE)
        length = rng.uniform(60, 320)
        w = rng.uniform(1.5, 6)
        alpha = rng.randint(6, strength)
        col = (0, 0, 0, alpha)
        line(d, (x, y), (x, y + length * direction), col, width=max(1, int(w)))
    layer = layer.filter(ImageFilter.GaussianBlur(1.2))
    out = Image.alpha_composite(img.convert("RGBA"), layer)
    return out


def panel_lines(img: Image.Image, seed: int, strength: int = 46,
                spacing=(70, 120), rivets: bool = True,
                line_color=(28, 32, 36)) -> Image.Image:
    """Irregular panel seams. A perfect grid reads as graph paper, so every
    seam is broken into a few slightly offset segments."""
    rng = random.Random(seed)
    layer = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    col = (*line_color, max(10, int(strength * 0.62)))

    def seam(p0, p1, width=2, alpha=None):
        c = (*line_color, alpha if alpha is not None else col[3])
        segments = rng.randint(2, 5)
        for i in range(segments):
            t0 = i / segments
            t1 = (i + 1) / segments
            jitter = rng.uniform(-2.5, 2.5)
            a = (p0[0] + (p1[0] - p0[0]) * t0, p0[1] + (p1[1] - p0[1]) * t0 + jitter)
            b = (p0[0] + (p1[0] - p0[0]) * t1, p0[1] + (p1[1] - p0[1]) * t1 + jitter)
            line(d, a, b, c, width=width)

    # a handful of long fuselage seams, mostly horizontal
    n_h = rng.randint(3, 5)
    for i in range(n_h):
        y = SIZE * (i + rng.uniform(0.15, 0.85)) / n_h
        seam((0, y), (SIZE, y + rng.uniform(-18, 18)), width=2)
    # fewer vertical seams
    n_v = rng.randint(2, 4)
    for i in range(n_v):
        x = SIZE * (i + rng.uniform(0.2, 0.8)) / n_v
        seam((x, 0), (x + rng.uniform(-22, 22), SIZE), width=2)

    # access panels / hatches with slightly rounded corners
    for _ in range(16):
        w = rng.uniform(70, 210)
        h = rng.uniform(50, 150)
        px = rng.uniform(0, SIZE)
        py = rng.uniform(0, SIZE)
        alpha = rng.randint(18, max(20, int(strength * 0.55)))
        for (a, b) in (((px, py), (px + w, py)),
                       ((px, py + h), (px + w, py + h)),
                       ((px, py), (px, py + h)),
                       ((px + w, py), (px + w, py + h))):
            line(d, a, b, (*line_color, alpha), width=1)

    if rivets:
        for _ in range(1500):
            px = rng.uniform(0, SIZE)
            py = rng.uniform(0, SIZE)
            ellipse(d, (px, py, px + 1.9, py + 1.9),
                    (20, 24, 28, rng.randint(18, min(70, strength))))

    layer = layer.filter(ImageFilter.GaussianBlur(0.55))
    return Image.alpha_composite(img.convert("RGBA"), layer)


def finish(img: Image.Image, name: str) -> str:
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name)
    img.convert("RGB").save(path, optimize=True)
    return path


# ------------------------------------------------------------------- materials
def make_camo(name: str, base, blotches, seed: int, streaks_strength: int = 26,
              panel_strength: int = 44, soft: float = 0.9) -> str:
    rng = random.Random(seed)
    img = Image.new("RGB", (SIZE, SIZE), base)
    d = ImageDraw.Draw(img)
    # Large soft patches (2-4 m across on a 5 m tile) are what the Su-34
    # scheme actually looks like; a field of small blobs reads as digital camo.
    for i in range(46):
        cx, cy = rng.uniform(0, SIZE), rng.uniform(0, SIZE)
        r = rng.uniform(160, 330)
        col = blotches[i % len(blotches)]
        poly(d, blob(rng, cx, cy, r, n=rng.randint(9, 14)), col)
    # a second, smaller generation breaks up the borders of the big patches
    for i in range(80):
        cx, cy = rng.uniform(0, SIZE), rng.uniform(0, SIZE)
        r = rng.uniform(45, 130)
        col = blotches[(i * 2 + 1) % len(blotches)]
        poly(d, blob(rng, cx, cy, r, n=rng.randint(7, 11)), col)
    img = img.filter(ImageFilter.GaussianBlur(soft))
    # grain
    n = noise_layer(seed + 1, scale=2, blur=1.0)
    arr = np.asarray(img).astype(np.float32)
    grain = (np.asarray(n).astype(np.float32) - 128.0) * 0.07
    arr = np.clip(arr + grain[..., None], 0, 255)
    img = Image.fromarray(arr.astype(np.uint8), "RGB")
    img = streaks(img, seed + 2, streaks_strength)
    img = panel_lines(img, seed + 3, strength=panel_strength)
    return finish(img, name)


def make_plain(name: str, base, seed: int, panel_strength: int = 30,
               grain: float = 0.10, streaks_strength: int = 12) -> str:
    img = Image.new("RGB", (SIZE, SIZE), base)
    n = noise_layer(seed, scale=2, blur=1.2)
    arr = np.asarray(img).astype(np.float32) + ((np.asarray(n).astype(np.float32) - 128.0) * grain)[..., None]
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
    if panel_strength:
        img = panel_lines(img, seed + 1, strength=panel_strength, spacing=(120, 220), rivets=False)
    if streaks_strength:
        img = streaks(img, seed + 2, streaks_strength)
    return finish(img, name)


def make_nozzle(name: str, seed: int) -> str:
    """Heat-tinted titanium with vertical scorching."""
    h, w = SIZE, SIZE
    arr = np.zeros((h, w, 3), dtype=np.float32)
    for y in range(h):
        t = y / h
        # dark titanium: a faint straw/blue heat tint, no brown racing stripes
        arr[y, :, 0] = 72 + 16 * math.sin(t * math.pi * 2.1) ** 2
        arr[y, :, 1] = 72 + 12 * math.sin(t * math.pi * 1.7) ** 2
        arr[y, :, 2] = 76 + 14 * math.cos(t * math.pi * 1.9) ** 2
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
    rng = random.Random(seed)
    d = ImageDraw.Draw(img)
    for _ in range(14):
        x = rng.uniform(0, SIZE)
        col = (rng.randint(40, 70), rng.randint(40, 70), rng.randint(46, 78))
        line(d, (x, 0), (x + rng.uniform(-20, 20), SIZE), (*col, 26), width=rng.randint(1, 3))
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    n = noise_layer(seed + 1, scale=2, blur=1.0)
    arr = np.asarray(img).astype(np.float32) + ((np.asarray(n).astype(np.float32) - 128.0) * 0.14)[..., None]
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
    return finish(img, name)


def make_decal_star(name: str, size: int = 512) -> str:
    """Red star with a white outline on a transparent background."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    def star(cx, cy, r_out, r_in, fill, outline=None, width=0):
        pts = []
        for i in range(10):
            a = -math.pi / 2 + i * math.pi / 5
            r = r_out if i % 2 == 0 else r_in
            pts.append((cx + math.cos(a) * r, cy + math.sin(a) * r))
        d.polygon(pts, fill=fill, outline=outline, width=width)

    star(size / 2, size / 2, size * 0.44, size * 0.175, (232, 236, 238, 255))
    star(size / 2, size / 2, size * 0.40, size * 0.155, (176, 32, 30, 255))
    img.save(os.path.join(OUT, name), optimize=True)
    return os.path.join(OUT, name)


def make_decal_number(name: str, text: str = "24", size: int = 512,
                      color=(226, 231, 234, 235)) -> str:
    """Bort number, drawn as thick segments so no font file is needed."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # seven-segment style digits
    segs = {
        "0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc",
        "5": "afgcd", "6": "afgecd", "7": "abc", "8": "abcdefg", "9": "abcdfg",
    }
    w, h = size * 0.30, size * 0.52
    x0 = size * 0.5 - (w * len(text) + size * 0.08 * (len(text) - 1)) / 2
    y0 = size * 0.24
    t = size * 0.03
    for ch in text:
        for s in segs.get(ch, ""):
            if s == "a":
                box = (x0, y0, x0 + w, y0 + t)
            elif s == "b":
                box = (x0 + w - t, y0, x0 + w, y0 + h / 2)
            elif s == "c":
                box = (x0 + w - t, y0 + h / 2, x0 + w, y0 + h)
            elif s == "d":
                box = (x0, y0 + h - t, x0 + w, y0 + h)
            elif s == "e":
                box = (x0, y0 + h / 2, x0 + t, y0 + h)
            elif s == "f":
                box = (x0, y0, x0 + t, y0 + h / 2)
            else:  # g
                box = (x0, y0 + h / 2 - t / 2, x0 + w, y0 + h / 2 + t / 2)
            d.rectangle(box, fill=color)
        x0 += w + size * 0.08
    img.save(os.path.join(OUT, name), optimize=True)
    return os.path.join(OUT, name)


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    made = []

    # Russian AF blue-grey camouflage: two tones on top, light blue-grey below.
    made.append(make_camo("su34_camo.png",
                          base=(113, 128, 141),
                          blotches=[(104, 119, 133), (123, 137, 149), (95, 111, 126)],
                          seed=11, streaks_strength=8, panel_strength=26, soft=3.2))
    made.append(make_camo("su34_camo_dark.png",
                          base=(103, 118, 132),
                          blotches=[(95, 110, 124), (114, 128, 141), (86, 102, 117)],
                          seed=23, streaks_strength=10, panel_strength=30, soft=3.2))
    made.append(make_camo("su34_underside.png",
                          base=(138, 152, 164),
                          blotches=[(128, 143, 156), (150, 163, 173), (120, 136, 149)],
                          seed=31, streaks_strength=8, panel_strength=26, soft=2.4))
    # The Su-34 radome is light grey with a dark tip.
    made.append(make_plain("su34_radome.png", (188, 192, 196), 41, panel_strength=14, grain=0.04))
    made.append(make_plain("su34_fintip.png", (222, 226, 228), 43, panel_strength=8, grain=0.03))
    made.append(make_plain("su34_metal.png", (128, 132, 136), 51, panel_strength=26, grain=0.12))
    made.append(make_plain("su34_intake.png", (26, 28, 30), 61, panel_strength=0, grain=0.05,
                           streaks_strength=0))
    made.append(make_plain("su34_frame.png", (48, 52, 56), 71, panel_strength=12, grain=0.06))
    made.append(make_plain("su34_gear.png", (104, 110, 106), 81, panel_strength=20, grain=0.10))
    made.append(make_plain("su34_cockpit.png", (58, 63, 68), 91, panel_strength=16, grain=0.05))
    made.append(make_nozzle("su34_nozzle.png", 101))
    made.append(make_decal_star("su34_star.png"))
    made.append(make_decal_number("su34_number.png", "24", color=(178, 32, 30, 235)))

    for path in made:
        size = os.path.getsize(path)
        print(f"wrote {path}  ({size // 1024} KiB)")


if __name__ == "__main__":
    main()
