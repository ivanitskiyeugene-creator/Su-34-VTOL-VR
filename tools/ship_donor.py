"""Copy the reframed donor OBJ + MTL into assets/model, so Unity picks it up.

The intermediate files under assets/import keep the names they got from the GLB
converter (Su-34.obj / Su-34.mtl); the shipped pair is renamed to
su34_donor.obj / su34_donor.mtl and its material library line is fixed up.
"""
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT, "assets", "import", "su34_donor")
OBJ_SRC = os.path.join(SRC_DIR, "obj", "Su-34_frame.obj")
MTL_SRC = os.path.join(SRC_DIR, "obj", "Su-34.mtl")
OUT_DIR = os.path.join(ROOT, "assets", "model")
OBJ_DST = os.path.join(OUT_DIR, "su34_donor.obj")
MTL_DST = os.path.join(OUT_DIR, "su34_donor.mtl")


def main():
    with open(OBJ_SRC, encoding="utf-8") as f:
        lines = f.readlines()
    with open(OBJ_DST, "w", encoding="utf-8") as f:
        for line in lines:
            if line.startswith("mtllib "):
                f.write("mtllib su34_donor.mtl\n")
            else:
                f.write(line)
    shutil.copyfile(MTL_SRC, MTL_DST)
    print("wrote", OBJ_DST)
    print("wrote", MTL_DST)


if __name__ == "__main__":
    main()
