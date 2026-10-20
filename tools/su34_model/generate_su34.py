"""
Procedural, original Su-34 exterior for the VTOL VR Su-34 mod.

The model is intentionally built from scratch (no ripped game assets). It is a
mid-detail, game-ready approximation of the Su-34's silhouette: side-by-side
cockpit fairing, canards, LERX, twin engine nacelles, twin canted fins, stinger,
landing gear and pylons. Dimensions are real-world metres so the aircraft drops
into Unity at 1:1 scale.

Run:  python3 tools/su34_model/generate_su34.py
Out:  assets/model/su34.obj, su34.mtl
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mesh_lib import (  # noqa: E402
    Mesh, airfoil_loop, lifting_surface, normalize, superellipse_ring, v,
    write_mtl, write_obj,
)

OUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "assets", "model"))

MATERIALS = {
    "Su34_Camo":      {"color": (0.335, 0.400, 0.435), "specular": (0.10, 0.11, 0.12), "shininess": 18},
    "Su34_CamoDark":  {"color": (0.215, 0.275, 0.310), "specular": (0.08, 0.09, 0.10), "shininess": 14},
    "Su34_Underside": {"color": (0.520, 0.565, 0.590), "specular": (0.08, 0.08, 0.08), "shininess": 12},
    "Su34_Radome":    {"color": (0.155, 0.175, 0.185), "specular": (0.05, 0.05, 0.05), "shininess": 8},
    "Su34_Glass":     {"color": (0.330, 0.470, 0.540), "specular": (0.70, 0.80, 0.85), "shininess": 120, "alpha": 0.30},
    "Su34_Frame":     {"color": (0.130, 0.155, 0.165), "specular": (0.20, 0.20, 0.20), "shininess": 40},
    "Su34_Metal":     {"color": (0.390, 0.405, 0.420), "specular": (0.75, 0.75, 0.78), "shininess": 110},
    "Su34_Intake":    {"color": (0.040, 0.045, 0.050), "specular": (0.02, 0.02, 0.02), "shininess": 4},
    "Su34_Gear":      {"color": (0.230, 0.245, 0.230), "specular": (0.18, 0.18, 0.18), "shininess": 30},
    "Su34_Tire":      {"color": (0.035, 0.035, 0.038), "specular": (0.02, 0.02, 0.02), "shininess": 6},
    "Su34_Cockpit":   {"color": (0.080, 0.090, 0.095), "specular": (0.03, 0.03, 0.03), "shininess": 6},
    "Su34_Red":       {"color": (0.480, 0.070, 0.060), "specular": (0.10, 0.05, 0.05), "shininess": 20},
}


def fuselage_stations() -> list[tuple[float, float, float, float, float]]:
    """(z, half_width, half_height, centre_y, superellipse exponent)"""
    return [
        (11.55, 0.12, 0.12, 0.00, 2.0),
        (11.20, 0.30, 0.28, 0.00, 2.0),
        (10.65, 0.52, 0.44, 0.01, 2.1),
        (9.95, 0.72, 0.60, 0.02, 2.2),
        (9.20, 0.90, 0.73, 0.04, 2.3),
        (8.40, 1.02, 0.84, 0.06, 2.4),
        (7.70, 1.12, 0.92, 0.08, 2.5),
        (7.00, 1.20, 0.98, 0.09, 2.6),
        (6.20, 1.26, 1.02, 0.09, 2.7),
        (5.30, 1.32, 1.06, 0.08, 2.8),
        (4.40, 1.38, 1.10, 0.06, 2.8),
        (3.50, 1.44, 1.14, 0.04, 2.8),
        (2.40, 1.50, 1.17, 0.02, 2.8),
        (1.20, 1.55, 1.20, 0.00, 2.8),
        (0.00, 1.58, 1.22, 0.00, 2.8),
        (-1.20, 1.58, 1.22, 0.00, 2.8),
        (-2.40, 1.56, 1.20, 0.01, 2.8),
        (-3.60, 1.54, 1.18, 0.02, 2.7),
        (-4.80, 1.50, 1.14, 0.04, 2.6),
        (-6.00, 1.44, 1.09, 0.06, 2.5),
        (-7.20, 1.37, 1.03, 0.08, 2.4),
        (-8.40, 1.30, 0.96, 0.10, 2.3),
        (-9.60, 1.22, 0.88, 0.12, 2.2),
        (-10.60, 1.14, 0.80, 0.12, 2.1),
        (-11.30, 1.05, 0.72, 0.12, 2.0),
        (-11.75, 0.92, 0.62, 0.12, 2.0),
    ]


def build_fuselage(mesh: Mesh) -> None:
    stations = fuselage_stations()
    rings = []
    for z, hw, hh, cy, n in stations:
        rings.append(superellipse_ring(z, hw, hh, cy, n=n, count=40))

    # Index range of the canopy cut (between z ~= 7.6 and z ~= 3.4)
    def in_cockpit(z: float) -> bool:
        return 3.30 <= z <= 7.75

    def skip(section: int, segment: int) -> bool:
        z = stations[section][0]
        if not in_cockpit(z):
            return False
        # top sector: 60 deg .. 120 deg, with a little margin
        a0 = 2 * math.pi * segment / 40
        a1 = 2 * math.pi * (segment + 1) / 40
        top = (math.pi / 3.0, 2.0 * math.pi / 3.0)
        return (top[0] <= a0 <= top[1]) and (top[0] <= a1 <= top[1])

    # Separately skin the nose/radome so it gets its own material and a clean
    # panel seam at z ~= 9.2.
    nose = [r for r, s in zip(rings, stations) if s[0] >= 9.20]
    body = [r for r, s in zip(rings, stations) if s[0] <= 9.20]
    p_nose = mesh.loft("Su34_Radome", "Su34_Radome", nose, cap_start=True, cap_end=False)
    p_body = mesh.loft("Su34_Fuselage", "Su34_Camo", body, cap_start=False, cap_end=True,
                       skip=lambda s, i: skip(
                           [k for k, st in enumerate(stations) if st[0] <= 9.20][s], i))
    mesh.orient(p_nose, lambda c: v(0, c[1] * 0.0 + 0.0, c[2]))
    mesh.orient(p_body, lambda c: v(0, 0.0, c[2]))

    # Cockpit tub: a dark open box under the canopy opening so the fuselage
    # does not look hollow from outside. The donor cockpit sits inside it.
    tub = mesh.new_part("Su34_CockpitTub", "Su34_Cockpit", smooth=False)
    z0, z1 = 3.35, 7.70
    x = 0.86
    ytop, yfloor = 0.94, 0.18
    verts = [
        v(-x, ytop, z0), v(x, ytop, z0), v(x, ytop, z1), v(-x, ytop, z1),
        v(-x, yfloor, z0), v(x, yfloor, z0), v(x, yfloor, z1), v(-x, yfloor, z1),
    ]
    ids = [tub.add_vertex(p) for p in verts]
    # floor, walls (normals point inward, into the tub)
    for quad in [(4, 5, 6, 7), (0, 4, 7, 3), (1, 2, 6, 5), (3, 7, 6, 2), (0, 1, 5, 4)]:
        a, b, c, d = (ids[k] for k in quad)
        tub.add_quad(a, b, c, d)
    mesh.orient(tub, lambda c: v(0, (ytop + yfloor) * 0.5, (z0 + z1) * 0.5))

    # Canopy sill / coaming
    rim = mesh.new_part("Su34_CanopySill", "Su34_Frame", smooth=False)
    for side in (-1, 1):
        left = [v(side * x, ytop, 3.35), v(side * x, ytop, 7.70)]
        right = [v(side * (x + 0.09), ytop - 0.015, 3.35), v(side * (x + 0.09), ytop - 0.015, 7.70)]
        if side > 0:
            mesh.quad_strip("Su34_CanopySill", "Su34_Frame", left, right)
    # front and rear sills
    mesh.quad_strip("Su34_CanopySillFront", "Su34_Frame",
                    [v(-x - 0.09, ytop - 0.015, 7.70), v(-x, ytop, 7.70)],
                    [v(x + 0.09, ytop - 0.015, 7.70), v(x, ytop, 7.70)])
    mesh.quad_strip("Su34_CanopySillRear", "Su34_Frame",
                    [v(-x - 0.09, ytop - 0.015, 3.35), v(-x, ytop, 3.35)],
                    [v(x + 0.09, ytop - 0.015, 3.35), v(x, ytop, 3.35)])


def build_canopy(mesh: Mesh) -> None:
    """Semi-transparent side-by-side canopy bubble with frame arches."""
    # (z, half_width at sill, top height, centre y at sill)
    sections = [
        (7.65, 0.52, 1.05, 0.94),
        (7.20, 0.72, 1.34, 0.94),
        (6.60, 0.82, 1.52, 0.94),
        (5.90, 0.86, 1.62, 0.94),
        (5.10, 0.86, 1.65, 0.94),
        (4.40, 0.82, 1.60, 0.94),
        (3.80, 0.74, 1.44, 0.94),
        (3.40, 0.64, 1.20, 0.94),
    ]
    rings = []
    n = 20
    for z, hw, top, sill in sections:
        ring = []
        for k in range(n + 1):
            t = math.pi * k / n  # 0..pi across the top
            ring.append(v(hw * math.cos(t), sill + (top - sill) * math.sin(t) ** 0.85, z))
        rings.append(ring)
    p = mesh.loft("Su34_Canopy", "Su34_Glass", rings, closed_ring=False)
    mesh.orient(p, lambda c: v(0, 0.80, c[2]))

    # canopy frames: arches + windshield centre post
    for z, hw, top, sill in [sections[0], sections[1], sections[3], sections[5], sections[-1]]:
        pts = []
        for k in range(n + 1):
            t = math.pi * k / n
            pts.append(v(hw * math.cos(t) * 1.01, sill + (top - sill) * math.sin(t) ** 0.85 * 1.01, z))
        # thin arch: a second ring slightly behind
        pts2 = [v(p[0] * 1.01, p[1], p[2] - 0.055) for p in pts]
        mesh.quad_strip("Su34_CanopyFrame", "Su34_Frame", pts, pts2, smooth=False)
    # centre rail along the windshield
    # follow the canopy top curve
    rail_l = [v(-0.035, 0.94 + (1.65 - 0.94) * (0.35 if z > 7.0 else 0.85), z) for z in (7.65, 7.2, 6.6, 5.9)]
    rail_r = [v(0.035, p[1], p[2]) for p in rail_l]
    mesh.quad_strip("Su34_CanopyRail", "Su34_Frame", rail_l, rail_r, smooth=False)


def build_wings(mesh: Mesh) -> None:
    # Main wings. Root LE +2.6, tip LE -3.55 -> ~42 deg leading edge sweep.
    for side in (-1, 1):
        x0, x1 = 2.15, 7.35
        sections = []
        for f, le_z, chord, y, th in [
            (0.00, 2.60, 6.60, -0.24, 0.055),
            (0.18, 1.55, 5.60, -0.26, 0.052),
            (0.40, 0.10, 4.35, -0.30, 0.048),
            (0.62, -1.30, 3.20, -0.34, 0.045),
            (0.82, -2.55, 2.35, -0.37, 0.042),
            (1.00, -3.55, 1.85, -0.40, 0.040),
        ]:
            x = x0 + (x1 - x0) * f
            sections.append({"le": v(side * x, y, le_z), "chord": chord, "thickness": th})
        name = "Su34_Wing_L" if side < 0 else "Su34_Wing_R"
        p = lifting_surface(mesh, name, "Su34_Camo", sections, span_dir=v(side, 0, 0),
                            thickness_dir=v(0, 1, 0), chord_dir=v(0, 0, 1))
        mesh.orient(p, lambda c: v(c[0], -0.24 - 0.03 * max(0.0, abs(c[0]) - 2.15), c[2]))

        # LERX: a thin, blended strake from the wing root to the forward fuselage
        lerx_sections = []
        for f, x, le_z, chord, y in [
            (0.0, 1.30, 4.90, 2.0, 0.62),
            (0.35, 1.70, 4.30, 2.6, 0.45),
            (0.70, 2.15, 3.60, 3.2, 0.20),
            (1.0, 2.55, 2.90, 3.9, -0.05),
        ]:
            lerx_sections.append({"le": v(side * x, y, le_z), "chord": chord, "thickness": 0.030})
        p = lifting_surface(mesh, "Su34_LERX_L" if side < 0 else "Su34_LERX_R",
                            "Su34_Camo", lerx_sections, span_dir=v(side, 0, 0),
                            thickness_dir=v(0, 1, 0), chord_dir=v(0, 0, 1), airfoil_n=7)
        mesh.orient(p, lambda c: v(c[0], 0.1, c[2]))

        # Ailerons (outer trailing edge). The wing's LE and chord taper
        # linearly, so the hinge line must follow that taper.
        def wing_le(x: float) -> float:
            return 2.60 - (x - 2.15) * (6.15 / 5.20)

        def wing_chord(x: float) -> float:
            return 6.60 - (x - 2.15) * (4.75 / 5.20)

        ail = []
        for x, chord in [(4.30, 0.62), (7.15, 0.50)]:
            le_z = wing_le(x) - wing_chord(x) - 0.03
            ail.append({"le": v(side * x, -0.33, le_z), "chord": chord, "thickness": 0.05})
        p = lifting_surface(mesh, "Su34_Aileron_L" if side < 0 else "Su34_Aileron_R",
                            "Su34_CamoDark", ail, span_dir=v(side, 0, 0),
                            thickness_dir=v(0, 1, 0), chord_dir=v(0, 0, 1), airfoil_n=7)
        mesh.orient(p, lambda c: v(c[0], -0.34, c[2]))

        # Flaps (inner trailing edge)
        flap = []
        for x, chord in [(2.35, 0.70), (4.15, 0.62)]:
            le_z = wing_le(x) - wing_chord(x) - 0.03
            flap.append({"le": v(side * x, -0.27, le_z), "chord": chord, "thickness": 0.05})
        p = lifting_surface(mesh, "Su34_Flap_L" if side < 0 else "Su34_Flap_R",
                            "Su34_CamoDark", flap, span_dir=v(side, 0, 0),
                            thickness_dir=v(0, 1, 0), chord_dir=v(0, 0, 1), airfoil_n=7)
        mesh.orient(p, lambda c: v(c[0], -0.28, c[2]))

        # Wingtip ECM pod / missile rail
        mesh.cylinder("Su34_WingtipPod_L" if side < 0 else "Su34_WingtipPod_R",
                      "Su34_Metal",
                      v(side * 7.42, -0.42, -3.20), v(side * 7.42, -0.42, -5.55),
                      0.13, 0.10, segments=12)
        mesh.cylinder("Su34_WingtipRail_L" if side < 0 else "Su34_WingtipRail_R",
                      "Su34_Metal",
                      v(side * 7.50, -0.42, -3.30), v(side * 7.50, -0.42, -5.40),
                      0.035, 0.035, segments=8)


def build_tail(mesh: Mesh) -> None:
    for side in (-1, 1):
        # Horizontal stabilators
        st = []
        for f, x, le_z, chord, y, th in [
            (0.0, 1.10, -7.55, 3.55, 0.12, 0.050),
            (0.45, 2.55, -8.55, 2.65, 0.04, 0.046),
            (0.75, 3.55, -9.20, 2.00, -0.02, 0.043),
            (1.0, 4.45, -9.85, 1.45, -0.08, 0.040),
        ]:
            st.append({"le": v(side * x, y, le_z), "chord": chord, "thickness": th})
        p = lifting_surface(mesh, "Su34_Stab_L" if side < 0 else "Su34_Stab_R",
                            "Su34_Camo", st, span_dir=v(side, 0, 0),
                            thickness_dir=v(0, 1, 0), chord_dir=v(0, 0, 1))
        mesh.orient(p, lambda c: v(c[0], 0.02, c[2]))

        # Elevators on the stabilator trailing edge
        def stab_le(x: float) -> float:
            return -7.55 - (x - 1.10) * (2.30 / 3.35)

        def stab_chord(x: float) -> float:
            return 3.55 - (x - 1.10) * (2.10 / 3.35)

        el = []
        for x, chord in [(2.55, 0.62), (4.25, 0.50)]:
            le_z = stab_le(x) - stab_chord(x) - 0.03
            el.append({"le": v(side * x, 0.00, le_z), "chord": chord, "thickness": 0.05})
        p = lifting_surface(mesh, "Su34_Elevator_L" if side < 0 else "Su34_Elevator_R",
                            "Su34_CamoDark", el, span_dir=v(side, 0, 0),
                            thickness_dir=v(0, 1, 0), chord_dir=v(0, 0, 1), airfoil_n=7)
        mesh.orient(p, lambda c: v(c[0], 0.0, c[2]))

        # Canted twin fins
        fin = []
        for f, y, x, le_z, chord, th in [
            (0.0, 0.35, 1.55, -6.75, 3.70, 0.050),
            (0.45, 1.75, 1.95, -7.80, 2.95, 0.046),
            (0.75, 2.65, 2.22, -8.50, 2.35, 0.043),
            (1.0, 3.35, 2.42, -9.05, 1.85, 0.040),
        ]:
            fin.append({"le": v(side * x, y, le_z), "chord": chord, "thickness": th})
        p = lifting_surface(mesh, "Su34_Fin_L" if side < 0 else "Su34_Fin_R",
                            "Su34_Camo", fin, span_dir=v(0, 1, 0),
                            thickness_dir=v(side, 0, 0), chord_dir=v(0, 0, 1),
                            airfoil_n=9)
        mesh.orient(p, lambda c: v(side * (1.5 + 0.35 * c[1]), c[1], c[2]))

        # Rudders
        rud = []
        for y, x, le_z, chord in [(0.9, 1.77, -9.35, 0.62), (3.0, 2.34, -10.55, 0.50)]:
            rud.append({"le": v(side * x, y, le_z), "chord": chord, "thickness": 0.05})
        p = lifting_surface(mesh, "Su34_Rudder_L" if side < 0 else "Su34_Rudder_R",
                            "Su34_CamoDark", rud, span_dir=v(0, 1, 0),
                            thickness_dir=v(side, 0, 0), chord_dir=v(0, 0, 1),
                            airfoil_n=7)
        mesh.orient(p, lambda c: v(side * (1.7 + 0.25 * c[1]), c[1], c[2]))

    # Tail stinger / brake parachute container
    mesh.cylinder("Su34_TailStinger", "Su34_Camo",
                  v(0, 0.12, -10.30), v(0, 0.18, -12.75), 0.38, 0.10, segments=16)
    # Small antenna blades
    mesh.box("Su34_AntennaDorsal", "Su34_Frame", v(0, 1.30, -2.4), (0.05, 0.22, 0.38))
    mesh.box("Su34_AntennaVentral", "Su34_Frame", v(0, -1.22, -3.2), (0.04, 0.18, 0.32))


def build_nacelles(mesh: Mesh) -> None:
    stations = [
        (2.15, 0.46, 0.46, -1.12),
        (1.90, 0.55, 0.55, -1.12),
        (1.20, 0.62, 0.64, -1.12),
        (0.20, 0.64, 0.67, -1.12),
        (-1.50, 0.64, 0.69, -1.12),
        (-3.50, 0.63, 0.69, -1.12),
        (-5.50, 0.61, 0.67, -1.12),
        (-7.50, 0.58, 0.63, -1.12),
        (-9.20, 0.54, 0.58, -1.12),
        (-10.40, 0.50, 0.53, -1.12),
    ]
    for side in (-1, 1):
        rings = [superellipse_ring(z, hw, hh, cy, n=2.4, count=24) for z, hw, hh, cy in stations]
        rings = [[p + v(side * 1.58, 0, 0) for p in r] for r in rings]
        p = mesh.loft("Su34_Nacelle_L" if side < 0 else "Su34_Nacelle_R",
                      "Su34_Camo", rings, cap_start=False, cap_end=True)
        mesh.orient(p, lambda c, s=side: v(s * 1.58, -1.12, c[2]))

        # Intake lip and dark intake duct
        lip = superellipse_ring(2.15, 0.46, 0.46, -1.12, n=2.4, count=24)
        lip = [p + v(side * 1.58, 0, 0) for p in lip]
        mesh.loft("Su34_IntakeLip_L" if side < 0 else "Su34_IntakeLip_R",
                  "Su34_Metal",
                  [lip, [p + v(0, 0, -0.10) * 1.0 for p in lip]],
                  closed_ring=True)
        # black throat, recessed
        mesh.cylinder("Su34_Intake_L" if side < 0 else "Su34_Intake_R", "Su34_Intake",
                      v(side * 1.58, -1.12, 2.05), v(side * 1.58, -1.12, 1.1),
                      0.42, 0.42, segments=20, caps=True, smooth=False)

        # Nozzles
        mesh.cylinder("Su34_Nozzle_L" if side < 0 else "Su34_Nozzle_R", "Su34_Metal",
                      v(side * 1.58, -1.12, -10.35), v(side * 1.58, -1.12, -11.95),
                      0.50, 0.40, segments=20, caps=False)
        mesh.cylinder("Su34_NozzleInner_L" if side < 0 else "Su34_NozzleInner_R", "Su34_Intake",
                      v(side * 1.58, -1.12, -11.2), v(side * 1.58, -1.12, -12.02),
                      0.34, 0.34, segments=18, caps=True, smooth=False)
        # Afterburner petals (simple raised strips)
        for k in range(8):
            a = 2 * math.pi * k / 8
            x = side * 1.58 + math.cos(a) * 0.44
            y = -1.12 + math.sin(a) * 0.44
            mesh.box("Su34_NozzlePetal", "Su34_Metal", v(x, y, -11.65),
                     (0.10, 0.10, 0.55))



def build_canards(mesh: Mesh) -> None:
    """Su-34 canards: small, close-coupled delta surfaces ahead of the wing."""
    for side in (-1, 1):
        sections = []
        for f, x, le_z, chord, y, th in [
            (0.0, 1.02, 4.15, 1.35, 0.34, 0.050),
            (0.55, 1.95, 3.55, 0.95, 0.30, 0.046),
            (1.0, 2.72, 3.05, 0.68, 0.26, 0.042),
        ]:
            sections.append({"le": v(side * x, y, le_z), "chord": chord, "thickness": th})
        p = lifting_surface(mesh, "Su34_Canard_L" if side < 0 else "Su34_Canard_R",
                            "Su34_Camo", sections, span_dir=v(side, 0, 0),
                            thickness_dir=v(0, 1, 0), chord_dir=v(0, 0, 1), airfoil_n=7)
        mesh.orient(p, lambda c: v(c[0], 0.30, c[2]))


def build_gear(mesh: Mesh) -> None:
    # Nose gear
    mesh.cylinder("Su34_NoseGearStrut", "Su34_Gear",
                  v(0, -0.55, 6.95), v(0, -2.05, 6.95), 0.075, 0.065, segments=10)
    mesh.cylinder("Su34_NoseGearAxle", "Su34_Gear",
                  v(-0.30, -2.30, 6.95), v(0.30, -2.30, 6.95), 0.05, 0.05, segments=8)
    for sx in (-1, 1):
        mesh.cylinder("Su34_NoseWheel", "Su34_Tire",
                      v(sx * 0.12, -2.30, 6.95), v(sx * 0.30, -2.30, 6.95),
                      0.31, 0.31, segments=18, caps=True)
    # Nose gear doors
    mesh.box("Su34_NoseGearDoorL", "Su34_Underside", v(-0.22, -0.72, 6.55), (0.40, 0.05, 1.25))
    mesh.box("Su34_NoseGearDoorR", "Su34_Underside", v(0.22, -0.72, 6.55), (0.40, 0.05, 1.25))

    # Main gear (tandem bogies under the engine nacelles)
    for side in (-1, 1):
        x = side * 2.05
        mesh.cylinder("Su34_MainGearStrut", "Su34_Gear",
                      v(x, -0.75, -1.05), v(x, -2.05, -1.05), 0.085, 0.07, segments=10)
        mesh.cylinder("Su34_MainGearBogie", "Su34_Gear",
                      v(x, -2.05, -2.05), v(x, -2.05, -0.05), 0.06, 0.06, segments=8)
        for z in (-1.55, -0.45):
            for sx in (-1, 1):
                mesh.cylinder("Su34_MainWheel", "Su34_Tire",
                              v(x + sx * 0.13, -2.25, z), v(x + sx * 0.32, -2.25, z),
                              0.39, 0.39, segments=18, caps=True)
        mesh.box("Su34_MainGearDoor", "Su34_Underside",
                 v(side * 1.65, -0.72, -1.0), (0.55, 0.05, 2.4))


def build_pylons(mesh: Mesh) -> None:
    for side in (-1, 1):
        for x, z, length in [(2.95, -1.30, 1.55), (4.65, -1.55, 1.45), (6.25, -2.10, 1.30)]:
            mesh.box("Su34_PylonWing", "Su34_CamoDark",
                     v(side * x, -0.55, z), (0.18, 0.30, length))
            mesh.box("Su34_PylonWingTip", "Su34_Metal",
                     v(side * x, -0.72, z), (0.12, 0.10, length * 0.85))
        # intake / fuselage pylons
        mesh.box("Su34_PylonBody", "Su34_CamoDark",
                 v(side * 1.85, -1.72, 0.10), (0.16, 0.28, 1.35))


def build_pitot(mesh: Mesh) -> None:
    mesh.cylinder("Su34_Pitot", "Su34_Metal",
                  v(0, 0.0, 11.55), v(0, 0.0, 12.75), 0.035, 0.012, segments=8)
    mesh.box("Su34_PitotVane", "Su34_Metal", v(0, 0.0, 12.20), (0.28, 0.03, 0.20))


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    mesh = Mesh()
    build_fuselage(mesh)
    build_canopy(mesh)
    build_wings(mesh)
    build_tail(mesh)
    build_canards(mesh)
    build_nacelles(mesh)
    build_gear(mesh)
    build_pylons(mesh)
    build_pitot(mesh)

    obj_path = os.path.join(OUT_DIR, "su34.obj")
    mtl_path = os.path.join(OUT_DIR, "su34.mtl")
    write_obj(obj_path, mesh, mtl_name="su34.mtl")
    write_mtl(mtl_path, MATERIALS)

    tris = sum(len(p.faces) for p in mesh.parts)
    verts = sum(len(p.vertices) for p in mesh.parts)
    print(f"wrote {obj_path}")
    print(f"  parts: {len(mesh.parts)}  raw verts: {verts}  tris: {tris}")
    print(f"  materials: {len(MATERIALS)}")


if __name__ == "__main__":
    main()
