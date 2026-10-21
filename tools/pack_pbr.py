"""Pack the donated metallic/roughness maps into one Unity-style map.

The glTF material carries a single metallic-roughness texture where:
    G = roughness, B = metallic.
Unity's Standard shader wants the opposite packing:
    R = metallic, A = smoothness (1 - roughness), G and B unused.

Doing the pack here (Python, once) instead of in Unity keeps the editor script
simple and means the shipped texture is already correct for the bundle.

Output: assets/model/textures/donor_metalsmooth.png
    2048x2048 RGBA. Metallic and roughness are smooth, low-frequency maps, so
    half the base colour resolution is plenty (8.6 mm per texel) and it keeps
    about 16 MB of VRAM free compared with a 4K copy.
"""
import os

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "assets", "import", "su34_donor", "textures")
OUT = os.path.join(ROOT, "assets", "model", "textures", "donor_metalsmooth.png")
SIZE = 2048


def main():
    metallic = Image.open(os.path.join(SRC, "Metallic-Roughness_2@channels=B.png")).convert("L")
    roughness = Image.open(os.path.join(SRC, "Metallic-Roughness_2@channels=G.png")).convert("L")

    metallic = metallic.resize((SIZE, SIZE), Image.LANCZOS)
    roughness = roughness.resize((SIZE, SIZE), Image.LANCZOS)

    m = np.asarray(metallic).astype(np.float32) / 255.0
    r = np.asarray(roughness).astype(np.float32) / 255.0

    rgba = np.zeros((SIZE, SIZE, 4), dtype=np.uint8)
    rgba[..., 0] = np.clip(m * 255.0, 0, 255).astype(np.uint8)          # metallic
    rgba[..., 1] = 0
    rgba[..., 2] = 0
    rgba[..., 3] = np.clip((1.0 - r) * 255.0, 0, 255).astype(np.uint8)  # smoothness

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    Image.fromarray(rgba, "RGBA").save(OUT, optimize=True)
    print("metallic mean %.3f, roughness mean %.3f" % (m.mean(), r.mean()))
    print("wrote", OUT, "%.1f MB" % (os.path.getsize(OUT) / 1e6))


if __name__ == "__main__":
    main()
