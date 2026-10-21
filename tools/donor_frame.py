"""Rewrite the donor OBJ into the frame the rest of the pipeline uses.

Donor: +x = nose, +y = up, +z = starboard.  Ours: +z = nose, +x = starboard,
+y = up.  The airframe is shifted so the radome tip lands on z = +11.62 like
the traced model; the span is left as delivered (14.74 m).
"""
import os

SRC = os.path.join(os.path.dirname(__file__), "..", "assets", "import",
                   "su34_donor", "obj", "Su-34.obj")
DST = os.path.join(os.path.dirname(__file__), "..", "assets", "import",
                   "su34_donor", "obj", "Su-34_frame.obj")
OFFSET = 2.50
YOFF = 0.99
SCALE = 1.015


def main():
    out = []
    with open(SRC) as f:
        for line in f:
            p = line.split()
            if not p:
                continue
            if p[0] == "v":
                x, y, z = (float(q) for q in p[1:4])
                out.append("v %.5f %.5f %.5f" % (z * SCALE, (y + YOFF) * SCALE,
                                                 x * SCALE - OFFSET))
            elif p[0] == "o":
                name = p[1]
                if name.startswith("Su-34-landing"):
                    name = "Su34_Gear" + name.split("-")[-1]
                out.append("o " + name)
            else:
                out.append(line.rstrip("\n"))
    with open(DST, "w") as f:
        f.write("\n".join(out) + "\n")
    print("wrote", DST)


if __name__ == "__main__":
    main()
