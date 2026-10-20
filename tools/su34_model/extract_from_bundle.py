"""
Pull a Su-34 mesh out of a VTOL VR custom-asset (CSA / NPC pack) bundle.

Why this exists
---------------
The mod ships with a fully procedural, original Su-34 (generate_su34.py), so
nothing here is required to fly. But if you already own an add-on that contains
a Su-34 (for example an NPC / custom-aircraft pack you subscribed to in the
Steam Workshop), this script can read that asset bundle directly and export the
mesh as OBJ + textures, so the mod can use it instead.

It works on the files in your Steam library, which are downloaded by Steam:

    <Steam>/steamapps/workshop/content/3018410/<item id>/

Point the script at that folder (or at one specific .bundle / .unity3d file).

Licensing
---------
A mesh that comes from somebody else's mod is still their work. Ask the author
before you publish anything that contains it, and credit them in the mod
description. The procedural model in this repository has no such restriction.

Usage
-----
    # what is inside a bundle?
    python3 tools/su34_model/extract_from_bundle.py --list "<folder or .bundle>"

    # export the mesh whose name matches a substring
    python3 tools/su34_model/extract_from_bundle.py \
        --bundle "<folder or .bundle>" --mesh su-34 \
        --out assets/model/su34_imported.obj

Options
-------
    --list              only print the meshes/textures found, do not export
    --mesh SUBSTR       case-insensitive substring of the mesh name
    --out PATH          output OBJ (textures are written next to it)
    --flip-x            negate X (Unity is left-handed; default: on)
    --scale N           multiply all coordinates (default 1.0)
    --upside            rotate 180 degrees around Z before exporting
"""
from __future__ import annotations

import argparse
import os
import re
from typing import Iterable

try:
    import UnityPy
except ImportError:  # pragma: no cover - only the environment matters
    raise SystemExit(
        "UnityPy is not installed.\n"
        "Install it with:  pip install --break-system-packages UnityPy"
    )


# --------------------------------------------------------------------- helpers
def iter_files(path: str) -> Iterable[str]:
    """Yield every file under ``path`` (or the single file itself)."""
    if os.path.isfile(path):
        yield path
        return
    for root, _dirs, files in os.walk(path):
        for name in files:
            # Skip the obvious junk that Steam leaves in workshop folders.
            if name.endswith((".png", ".jpg", ".txt", ".json", ".dll", ".cs")):
                continue
            yield os.path.join(root, name)


def load_environment(path: str):
    """UnityPy.load() never throws for unknown data, it just yields nothing."""
    try:
        return UnityPy.load(path)
    except Exception:
        return None


def mesh_vertices(mesh):
    """Return (vertices, uvs, triangles) from a UnityPy Mesh object."""
    verts = list(getattr(mesh, "m_Vertices", []) or [])
    uvs = list(getattr(mesh, "m_UV", []) or [])
    indices = list(getattr(mesh, "m_IndexBuffer", []) or [])

    if not verts:
        # Compressed / streamed meshes: ask UnityPy to decompress them.
        try:
            mesh.decompress()  # type: ignore[attr-defined]
            verts = list(getattr(mesh, "m_Vertices", []) or [])
            uvs = list(getattr(mesh, "m_UV", []) or [])
            indices = list(getattr(mesh, "m_IndexBuffer", []) or [])
        except Exception:
            pass
    if not verts:
        return [], [], []

    tris = []
    submeshes = list(getattr(mesh, "m_SubMeshes", []) or [])
    if submeshes and indices:
        for sub in submeshes:
            first = int(getattr(sub, "firstByte", 0)) // 2
            count = int(getattr(sub, "indexCount", 0))
            base = int(getattr(sub, "baseVertex", 0))
            chunk = indices[first:first + count]
            for i in range(0, len(chunk) - 2, 3):
                tris.append((chunk[i] + base, chunk[i + 1] + base, chunk[i + 2] + base))
    else:
        for i in range(0, len(indices) - 2, 3):
            tris.append((indices[i], indices[i + 1], indices[i + 2]))
    return verts, uvs, tris


def convert_vertex(p, flip_x: bool, scale: float):
    x, y, z = float(p[0]), float(p[1]), float(p[2])
    if flip_x:
        x = -x
    return x * scale, y * scale, z * scale


def export_obj(path: str, verts, uvs, tris, flip_x: bool, scale: float) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    out = ["# exported by tools/su34_model/extract_from_bundle.py"]
    for p in verts:
        out.append("v %.5f %.5f %.5f" % convert_vertex(p, flip_x, scale))
    if uvs:
        for uv in uvs:
            out.append("vt %.5f %.5f" % (float(uv[0]), float(uv[1])))
    for (a, b, c) in tris:
        if uvs:
            out.append("f %d/%d %d/%d %d/%d" % (a + 1, a + 1, b + 1, b + 1, c + 1, c + 1))
        else:
            out.append("f %d %d %d" % (a + 1, b + 1, c + 1))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
    print("wrote", path, "->", len(verts), "vertices,", len(tris), "triangles")


# ------------------------------------------------------------------------ main
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bundle", dest="bundle", default=None,
                    help="folder or bundle file to inspect")
    ap.add_argument("--list", action="store_true", help="only list the contents")
    ap.add_argument("--mesh", default="su-34", help="substring of the mesh name")
    ap.add_argument("--out", default="assets/model/su34_imported.obj")
    ap.add_argument("--no-flip-x", action="store_false", dest="flip_x",
                    help="keep Unity's handedness")
    ap.add_argument("--scale", type=float, default=1.0)
    args = ap.parse_args()

    target = args.bundle or os.environ.get("VTOL_WORKSHOP_DIR")
    if not target:
        raise SystemExit(
            "--bundle is required (a workshop folder or one .bundle file).\n"
            "Typical path: <Steam>/steamapps/workshop/content/3018410/<item id>/"
        )

    found_meshes = []
    found_textures = []
    wanted = args.mesh.lower()
    stem = re.sub(r"[^a-z0-9]", "", wanted)

    for path in iter_files(target):
        env = load_environment(path)
        if env is None:
            continue
        for obj in env.objects:
            try:
                type_name = obj.type.name
            except Exception:
                continue
            if type_name == "Mesh":
                try:
                    mesh = obj.read()
                except Exception:
                    continue
                name = str(getattr(mesh, "m_Name", "") or "")
                verts, uvs, tris = mesh_vertices(mesh)
                found_meshes.append((name, len(verts), len(tris), mesh))
                if not args.list and wanted in name.lower() and len(verts):
                    export_obj(args.out, verts, uvs, tris,
                               args.flip_x, args.scale)
                    print("source bundle:", path)
            elif type_name == "Texture2D" and not args.list:
                try:
                    tex = obj.read()
                    name = str(getattr(tex, "m_Name", "") or "")
                except Exception:
                    continue
                norm = re.sub(r"[^a-z0-9]", "", name.lower())
                if stem and stem not in norm:
                    continue
                try:
                    image = tex.image
                except Exception:
                    continue
                out_dir = os.path.join(os.path.dirname(os.path.abspath(args.out)), "textures")
                os.makedirs(out_dir, exist_ok=True)
                safe = "".join(ch if ch.isalnum() or ch in "-_ " else "_" for ch in name) or "texture"
                png = os.path.join(out_dir, safe + ".png")
                image.save(png)
                found_textures.append((name, png))

    if args.list or not found_meshes:
        print("\nmeshes:")
        for name, nv, nt, _mesh in sorted(found_meshes, key=lambda m: -m[1]):
            print("  %-52s %6d verts %6d tris" % (name[:52], nv, nt))
        if found_textures:
            print("\ntextures:")
            for name, png in found_textures:
                print("  %-52s %s" % (name[:52], png))
        if not found_meshes:
            print("  (none) - is this really a Unity bundle / CSA pack folder?")
    else:
        print("\n%d mesh(es) exported candidates; textures: %d"
              % (len(found_meshes), len(found_textures)))


if __name__ == "__main__":
    main()
