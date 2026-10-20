"""
Procedural, original Su-34 exterior for the VTOL VR Su-34 mod.

Everything is built from scratch (no ripped game assets) using real-world
dimensions in metres, Unity axes (+X right, +Y up, +Z nose):

    length 23.3 m, wingspan 14.7 m, height 6.1 m (gear down)

The fuselage is lofted through Catmull-Rom-smoothed stations with asymmetric
cross sections (flat belly, rounded spine), the canopy opening is cut out of
the crown, and wings / canards / fins / stabilators are lofted from NACA
profiles. Skin textures come from generate_textures.py and are mapped with
world-space box projection (5 m per tile).

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
    Mesh, Part, apply_box_uv, catmull_rom, lifting_surface, normalize,
    write_mtl, write_obj, v,
)

OUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "assets", "model"))
TEX = "textures/"

# --------------------------------------------------------------------- palette
# Kd is only a fallback; in Unity the map_Kd texture drives the colour.
MATERIALS = {
    "Su34_Camo":      {"color": (0.573, 0.639, 0.678), "specular": (0.12, 0.13, 0.14),
                       "shininess": 22, "map": TEX + "su34_camo.png"},
    "Su34_CamoDark":  {"color": (0.506, 0.576, 0.620), "specular": (0.12, 0.13, 0.14),
                       "shininess": 22, "map": TEX + "su34_camo_dark.png"},
    "Su34_Underside": {"color": (0.620, 0.675, 0.710), "specular": (0.10, 0.11, 0.11),
                       "shininess": 16, "map": TEX + "su34_underside.png"},
    "Su34_Radome":    {"color": (0.804, 0.816, 0.824), "specular": (0.06, 0.06, 0.06),
                       "shininess": 10, "map": TEX + "su34_radome.png"},
    "Su34_Glass":     {"color": (0.56, 0.70, 0.78), "specular": (0.95, 1.00, 1.00),
                       "shininess": 180, "alpha": 0.42},
    "Su34_Frame":     {"color": (0.188, 0.204, 0.220), "specular": (0.30, 0.30, 0.32),
                       "shininess": 60, "map": TEX + "su34_frame.png"},
    "Su34_Metal":     {"color": (0.502, 0.518, 0.533), "specular": (0.78, 0.78, 0.80),
                       "shininess": 120, "map": TEX + "su34_metal.png"},
    "Su34_Nozzle":    {"color": (0.34, 0.34, 0.35), "specular": (0.85, 0.82, 0.78),
                       "shininess": 150, "map": TEX + "su34_nozzle.png"},
    "Su34_Intake":    {"color": (0.10, 0.11, 0.12), "specular": (0.02, 0.02, 0.02),
                       "shininess": 6, "map": TEX + "su34_intake.png"},
    "Su34_Gear":      {"color": (0.408, 0.431, 0.416), "specular": (0.22, 0.22, 0.22),
                       "shininess": 34, "map": TEX + "su34_gear.png"},
    "Su34_Tire":      {"color": (0.086, 0.090, 0.094), "specular": (0.03, 0.03, 0.03),
                       "shininess": 8},
    "Su34_Cockpit":   {"color": (0.235, 0.259, 0.278), "specular": (0.04, 0.04, 0.04),
                       "shininess": 8, "map": TEX + "su34_cockpit.png"},
    "Su34_Star":      {"color": (0.70, 0.14, 0.12), "specular": (0.15, 0.08, 0.08),
                       "shininess": 20, "map": TEX + "su34_star.png",
                       "map_alpha": TEX + "su34_star.png"},
    "Su34_Number":    {"color": (0.70, 0.13, 0.12), "specular": (0.15, 0.15, 0.15),
                       "shininess": 20, "map": TEX + "su34_number.png",
                       "map_alpha": TEX + "su34_number.png"},
    "Su34_FinTip":    {"color": (0.870, 0.885, 0.890), "specular": (0.10, 0.10, 0.10),
                       "shininess": 16, "map": TEX + "su34_fintip.png"},
    "Su34_MFD":       {"color": (0.035, 0.070, 0.085), "specular": (0.55, 0.70, 0.75),
                       "shininess": 90},
    "Su34_HUD":       {"color": (0.30, 0.85, 0.50), "specular": (0.90, 0.95, 0.90),
                       "shininess": 160, "alpha": 0.22},
    "Su34_Cushion":   {"color": (0.180, 0.190, 0.175), "specular": (0.05, 0.05, 0.05),
                       "shininess": 6},
}

# ------------------------------------------------------------------ fuselage
# Control stations: (z, half width, top y, bottom y, superellipse exponent)
# Values are real Su-34 proportions: blunt wide nose (radar + side-by-side
# cockpit), flat belly, slight taper towards the tail, boom between the
# engine nacelles.
FUSELAGE_CONTROL = [
    # The forward fuselage is the Su-34 "platypus": wider than it is deep and
    # quite flat on top, so the radians are not an egg.
    (11.42, 0.30, 0.17, -0.13, 2.30),
    (11.16, 0.56, 0.30, -0.24, 2.40),
    (10.82, 0.82, 0.43, -0.36, 2.50),
    (10.42, 1.02, 0.54, -0.46, 2.58),
    (10.00, 1.15, 0.62, -0.53, 2.64),
    (9.62, 1.23, 0.68, -0.57, 2.70),
    (9.30, 1.27, 0.72, -0.60, 2.72),
    (8.60, 1.28, 0.81, -0.72, 2.75),
    (7.90, 1.29, 0.90, -0.84, 2.80),
    (7.10, 1.29, 0.96, -0.90, 2.80),
    (6.20, 1.31, 0.99, -0.93, 2.85),
    (5.10, 1.34, 1.01, -0.95, 2.85),
    (4.00, 1.38, 1.02, -0.97, 2.85),
    (2.80, 1.43, 1.02, -0.98, 2.85),
    (1.50, 1.48, 1.02, -1.00, 2.85),
    (0.00, 1.52, 1.02, -1.02, 2.85),
    (-1.50, 1.52, 1.02, -1.02, 2.85),
    (-3.00, 1.50, 1.01, -1.01, 2.80),
    (-4.50, 1.47, 0.99, -0.99, 2.75),
    (-6.00, 1.42, 0.96, -0.96, 2.65),
    (-7.50, 1.36, 0.92, -0.92, 2.55),
    (-9.00, 1.29, 0.87, -0.87, 2.45),
    (-10.20, 1.21, 0.81, -0.81, 2.35),
    (-11.10, 1.10, 0.74, -0.74, 2.25),
    (-11.75, 0.94, 0.64, -0.64, 2.15),
]

# The control stations above carry the *full* widths that a flat top view
# suggests; real Flanker hulls are only ~1.6 m wide, so the loft is squashed in
# X.  Without this the aircraft reads as a wide-body airliner.
BODY_X = 0.52
FUSELAGE_CONTROL = [(z, hw * BODY_X, top, bot, n)
                    for (z, hw, top, bot, n) in FUSELAGE_CONTROL]

COCKPIT_Z0, COCKPIT_Z1 = 5.05, 7.85   # canopy opening (rear .. front)
CANOPY_HALF_WIDTH = 0.62              # opening half width at the sill
# (z, crown height) of the canopy: one-piece windscreen in front, bubble
# over the two side-by-side seats, arch at the rear.
CANOPY_SECTIONS = [
    (7.85, 1.22), (7.50, 1.40), (7.05, 1.52), (6.40, 1.60),
    (5.75, 1.62), (5.20, 1.58), (5.05, 1.38),
]


def smooth_fuselage(samples: int = 120) -> np.ndarray:
    """Catmull-Rom through the control stations, z descending as given."""
    return catmull_rom(np.array(FUSELAGE_CONTROL, dtype=np.float64), samples)


def fuselage_ring(z, hw, top, bot, n, count=56) -> list:
    cy = (top + bot) / 2.0
    hh = (top - bot) / 2.0
    pts = []
    for k in range(count):
        t = 2 * math.pi * k / count
        ct, st = math.cos(t), math.sin(t)
        x = hw * math.copysign(abs(ct) ** (2.0 / n), ct)
        y = cy + hh * math.copysign(abs(st) ** (2.0 / n), st)
        pts.append(v(x, y, z))
    return pts


def station_at(z: float) -> tuple[float, float, float, float]:
    """Interpolate (half width, top, bottom, exponent) at an arbitrary z."""
    ctrl = np.array(FUSELAGE_CONTROL)
    zs = ctrl[:, 0][::-1]
    for i in range(len(zs) - 1):
        if zs[i] <= z <= zs[i + 1]:
            t = (z - zs[i]) / max(1e-9, zs[i + 1] - zs[i])
            row = ctrl[::-1][i] * (1 - t) + ctrl[::-1][i + 1] * t
            return row[1], row[2], row[3], row[4]
    row = ctrl[0] if z > zs[-1] else ctrl[-1]
    return row[1], row[2], row[3], row[4]


def build_fuselage(mesh: Mesh) -> None:
    stations = smooth_fuselage()
    count = 56
    rings = []
    for z, hw, top, bot, n in stations:
        rings.append(fuselage_ring(z, hw, top, bot, n, count))

    def in_cockpit(z: float) -> bool:
        return COCKPIT_Z0 <= z <= COCKPIT_Z1

    # Skip the crown quads of the canopy opening. The test is done on the
    # vertex coordinates (not on angles) so the cut edge lands exactly where
    # the canopy sill is, with no gap around the glass.
    def skip(section: int, segment: int) -> bool:
        z = stations[section][0]
        if not in_cockpit(z):
            return False
        ring = rings[section]
        n_ring = len(ring)
        a = ring[segment]
        b = ring[(segment + 1) % n_ring]
        cut = skin_top_y(z, CANOPY_HALF_WIDTH) - 0.02
        for p in (a, b):
            if abs(p[0]) > CANOPY_HALF_WIDTH + 0.075:
                return False
            if p[1] < cut:
                return False
        return True

    radome = [r for r, s in zip(rings, stations) if s[0] >= 9.30]
    body = [r for r, s in zip(rings, stations) if s[0] <= 9.30]

    p_radome = mesh.loft("Su34_Radome", "Su34_Radome", radome, cap_start=True, cap_end=False)
    mesh.orient(p_radome, lambda c: v(0, 0.0, c[2]))

    body_start = [i for i, s in enumerate(stations) if s[0] <= 9.30][0]
    p_body = mesh.loft(
        "Su34_Fuselage", "Su34_Camo", body, cap_start=False, cap_end=True,
        skip=lambda s, i: skip(body_start + s, i))
    mesh.orient(p_body, lambda c: v(0, 0.0, c[2]))

    # Belly in the underside colour: an open arc lofted just outside the
    # lower fuselage, which gives the two-tone split without extra UV work.
    belly_rings = []
    arc_count = 22
    for z, hw, top, bot, n in stations:
        if z > 9.4 or z < -11.5:
            continue
        cy = (top + bot) / 2.0
        hh = (top - bot) / 2.0
        ring = []
        for k in range(arc_count):
            t = math.radians(198.0) + math.radians(144.0) * k / (arc_count - 1)
            ct, st = math.cos(t), math.sin(t)
            x = hw * 1.012 * math.copysign(abs(ct) ** (2.0 / n), ct)
            y = cy + hh * 1.012 * math.copysign(abs(st) ** (2.0 / n), st)
            ring.append(v(x, y, z))
        belly_rings.append(ring)
    if len(belly_rings) > 2:
        p_belly = mesh.loft("Su34_Belly", "Su34_Underside", belly_rings,
                            closed_ring=False, cap_start=False, cap_end=False)
        mesh.orient(p_belly, lambda c: v(0.0, 0.4, c[2]))

    build_cockpit(mesh)
    build_canopy(mesh)



def skin_top_y(z: float, x: float) -> float:
    """Top surface height of the fuselage at station ``z`` and offset ``x``."""
    hw, top, bot, n = station_at(z)
    cy = (top + bot) / 2.0
    hh = (top - bot) / 2.0
    t = min(abs(x) / max(hw, 1e-6), 1.0)
    cos_t = t ** (n / 2.0)
    sin_t = math.sqrt(max(1.0 - cos_t * cos_t, 0.0))
    return cy + hh * (sin_t ** (2.0 / n))


def sill_y(z: float) -> float:
    """Height of the canopy sill (where the fuselage shoulder meets the glass)."""
    return skin_top_y(z, CANOPY_HALF_WIDTH) - 0.015


def canopy_crown(z: float) -> float:
    """Canopy crown height at station ``z`` (linear between the control sections)."""
    for (za, ca), (zb, cb) in zip(CANOPY_SECTIONS, CANOPY_SECTIONS[1:]):
        if zb <= z <= za:
            t = (za - z) / (za - zb)
            return ca + (cb - ca) * t
    return CANOPY_SECTIONS[0][1]


def canopy_ring(z: float, crown: float, n: int = 24, scale: float = 1.0):
    base = sill_y(z)
    hw = CANOPY_HALF_WIDTH * scale
    ring = []
    for k in range(n + 1):
        t = math.pi * k / n
        y = base + (crown - base) * math.sin(t) ** 0.72
        ring.append(v(hw * math.cos(t), y, z))
    return ring


def build_cockpit(mesh: Mesh) -> None:
    """Side-by-side Su-34 cockpit: two seats, one wide panel, two MFD sets.

    The real aircraft puts the pilot on the left and the weapons systems
    officer on the right, shoulder to shoulder (not in tandem), with a single
    wide instrument panel and one HUD in front of the pilot.
    """
    z0, z1 = COCKPIT_Z0, COCKPIT_Z1
    x = CANOPY_HALF_WIDTH
    ref = sill_y(6.40)               # sill height at the crew stations
    yfloor = ref - 0.52
    seat_z = 6.40

    # ---------------------------------------------------------------- tub
    # Open-topped channel whose rim follows the real skin shoulder, so the
    # glass sits exactly on the tub edge and no daylight leaks between them.
    tub_rings = []
    steps = 9
    for k in range(steps + 1):
        z = z0 + (z1 - z0) * k / steps
        rim = sill_y(z)
        tub_rings.append([
            v(x, rim, z), v(x, yfloor, z), v(-x, yfloor, z), v(-x, rim, z),
        ])
    tub = mesh.loft("Su34_CockpitTub", "Su34_Cockpit", tub_rings,
                    closed_ring=False, cap_start=False, cap_end=False,
                    smooth=False)
    mesh.orient(tub, lambda c: v(0, yfloor + 0.05, c[2]))

    # floor plate
    floor = mesh.box("Su34_CockpitFloor", "Su34_Cockpit",
                     v(0.0, yfloor - 0.02, (z0 + z1) / 2), (2 * x, 0.06, z1 - z0))
    mesh.orient(floor, lambda c: v(0, yfloor + 0.30, c[2]))

    # -------------------------------------------------------------- seats
    # z = seat pan centre, the crew faces +Z (the nose).
    for sx in (-0.30, 0.30):
        mesh.box("Su34_SeatFrame", "Su34_Frame",
                 v(sx, yfloor + 0.22, seat_z), (0.38, 0.12, 0.44))
        mesh.box("Su34_SeatCushion", "Su34_Cushion",
                 v(sx, yfloor + 0.31, seat_z), (0.34, 0.10, 0.42))
        mesh.box("Su34_SeatBack", "Su34_Cushion",
                 v(sx, yfloor + 0.64, seat_z - 0.25), (0.34, 0.72, 0.11))
        mesh.box("Su34_SeatHeadrest", "Su34_Cushion",
                 v(sx, yfloor + 1.00, seat_z - 0.27), (0.22, 0.18, 0.10))
        # side rails of the ejection seat
        for rx in (-0.19, 0.19):
            mesh.box("Su34_SeatRail", "Su34_Frame",
                     v(sx + rx, yfloor + 0.60, seat_z - 0.25), (0.04, 0.68, 0.16))

    # ----------------------------------------------------- instrument panel
    # The panel stands just behind the dash; its top edge and the dash form a
    # flat shelf under the windscreen (a smooth ramp read as a grey hill).
    panel_z = z1 - 0.42
    panel_y = ref - 0.075
    mesh.box("Su34_InstrumentPanel", "Su34_Frame",
             v(0.0, panel_y, panel_z), (2 * x - 0.04, 0.40, 0.20))
    # knee panel down to the floor, so the cockpit front looks finished
    mesh.box("Su34_KneePanel", "Su34_Cockpit",
             v(0.0, (yfloor + panel_y - 0.15) / 2, panel_z - 0.02),
             (2 * x - 0.10, panel_y - 0.15 - yfloor, 0.24))

    # two MFDs per crew station, recessed into the panel
    for sx in (-0.30, 0.30):
        for dx in (-0.14, 0.14):
            mesh.box("Su34_MFDBezel", "Su34_Frame",
                     v(sx + dx, panel_y - 0.05, panel_z + 0.105),
                     (0.26, 0.24, 0.03))
            mesh.box("Su34_MFDScreen", "Su34_MFD",
                     v(sx + dx, panel_y - 0.05, panel_z + 0.125),
                     (0.21, 0.19, 0.01))

    # dash: flat shelf from the panel top to the windscreen base
    dash_y = panel_y + 0.225
    mesh.box("Su34_Dash", "Su34_Cockpit",
             v(0.0, dash_y, (panel_z + 0.10 + z1) / 2), (2 * x - 0.02, 0.05, z1 - panel_z - 0.10))

    # HUD in front of the pilot (left seat) only
    mesh.box("Su34_HUDFrame", "Su34_Frame",
             v(-0.30, dash_y + 0.05, panel_z + 0.22), (0.32, 0.04, 0.12))
    mesh.box("Su34_HUDCombiner", "Su34_HUD",
             v(-0.30, dash_y + 0.17, panel_z + 0.18), (0.28, 0.22, 0.02))
    for px in (-0.43, -0.17):
        mesh.box("Su34_HUDFrame", "Su34_Frame",
                 v(px, dash_y + 0.17, panel_z + 0.18), (0.02, 0.24, 0.03))

    # ---------------------------------------------------------- consoles
    for sx in (-1, 1):
        mesh.box("Su34_SideConsole", "Su34_Frame",
                 v(sx * (x - 0.10), yfloor + 0.34, seat_z + 0.10),
                 (0.16, 0.26, 1.30))
        # throttle quadrant on the left of each station
        mesh.box("Su34_Throttle", "Su34_Frame",
                 v(sx * (x - 0.10), yfloor + 0.54, seat_z + 0.32),
                 (0.09, 0.10, 0.26))
    for sx in (-0.30, 0.30):
        mesh.cylinder("Su34_Stick", "Su34_Frame",
                      v(sx, yfloor + 0.34, seat_z + 0.48),
                      v(sx, yfloor + 0.56, seat_z + 0.46), 0.022, 0.018, segments=8)
        mesh.box("Su34_StickGrip", "Su34_Frame",
                 v(sx, yfloor + 0.60, seat_z + 0.45), (0.06, 0.10, 0.07))
        mesh.box("Su34_RudderPedal", "Su34_Frame",
                 v(sx, yfloor + 0.10, seat_z + 0.94), (0.16, 0.04, 0.14))

    # central pedestal between the two seats
    mesh.box("Su34_CentreConsole", "Su34_Frame",
             v(0.0, yfloor + 0.30, seat_z + 0.02), (0.18, 0.22, 1.05))

    # sill coaming: a thin lip that covers the seam between the tub rim and
    # the fuselage cut, following the same shoulder curve
    lip = mesh.new_part("Su34_CanopySill", "Su34_Frame", smooth=False)
    for side in (-1, 1):
        inner = [v(side * x, sill_y(z), z) for z in np.linspace(z0, z1, 9)]
        outer = [v(side * (x + 0.075), sill_y(z) - 0.02, z) for z in np.linspace(z0, z1, 9)]
        mesh.quad_strip("Su34_CanopySill", "Su34_Frame", inner, outer,
                        smooth=False, double_sided=True)

    # rear bulkhead, closing the tub behind the crew
    rear = mesh.new_part("Su34_CockpitBulkhead", "Su34_Cockpit", smooth=False)
    top = canopy_crown(z0)
    pts = [v(-x, yfloor, z0), v(x, yfloor, z0)]
    for k in range(9):
        t = math.pi - math.pi * k / 8
        pts.append(v(x * math.cos(t), sill_y(z0) + (top - sill_y(z0)) * math.sin(t) ** 0.72, z0))
    ids = [rear.add_vertex(q) for q in pts]
    # fan from the floor centre
    cid = rear.add_vertex(v(0.0, yfloor, z0))
    for k in range(len(ids) - 1):
        rear.add_face(cid, ids[k], ids[k + 1])
    mesh.orient(rear, lambda c: v(0, c[1] - 0.3 if c[2] > z0 else c[1], c[2]))

    # front bulkhead: closes the nose end of the tub under the windscreen
    front = mesh.box("Su34_CockpitBulkhead", "Su34_Cockpit",
                     v(0.0, yfloor + 0.44, z1 - 0.01), (2 * x, 0.88, 0.04))


def build_canopy(mesh: Mesh) -> None:
    """Side-by-side canopy bubble: one-piece windscreen, two bow frames."""
    n = 24
    rings = [canopy_ring(z, crown, n) for z, crown in CANOPY_SECTIONS]
    p = mesh.loft("Su34_Canopy", "Su34_Glass", rings, closed_ring=False)
    mesh.orient(p, lambda c: v(0, sill_y(c[2]) - 0.15, c[2]))

    # bow frames: windscreen arch, canopy hinge, rear arch
    for z, crown in (CANOPY_SECTIONS[0], CANOPY_SECTIONS[3], CANOPY_SECTIONS[-1]):
        pts = canopy_ring(z, crown, n, scale=1.012)
        pts = [v(q[0], q[1] + 0.002, q[2]) for q in pts]
        pts2 = [v(q[0], q[1], q[2] - 0.055) for q in pts]
        mesh.quad_strip("Su34_CanopyFrame", "Su34_Frame", pts, pts2,
                        smooth=False, double_sided=True)

    # centre rail running from the windscreen to the rear arch
    rail_l, rail_r = [], []
    for z, crown in CANOPY_SECTIONS[:-1]:
        y = crown + 0.008
        rail_l.append(v(-0.028, y, z))
        rail_r.append(v(0.028, y, z))
    mesh.quad_strip("Su34_CanopyRail", "Su34_Frame", rail_l, rail_r,
                    smooth=False, double_sided=True)

    # rear fairing: canopy blends into the spine behind the opening
    fairing = []
    for z, crown in ((COCKPIT_Z0, canopy_crown(COCKPIT_Z0)),
                     (COCKPIT_Z0 - 0.45, canopy_crown(COCKPIT_Z0) - 0.18),
                     (COCKPIT_Z0 - 0.90, (station_at(COCKPIT_Z0 - 0.90)[1] + 0.05))):
        fairing.append(canopy_ring(z, crown, n, scale=0.99))
    pf = mesh.loft("Su34_CanopyFairing", "Su34_Camo", fairing, closed_ring=False)
    mesh.orient(pf, lambda c: v(0, sill_y(c[2]) - 0.15, c[2]))


# ---------------------------------------------------------------------- wings
WING_ROOT_X = 0.72
WING_TIP_X = 7.22


def wing_le(x: float) -> float:
    return 5.45 - (x - WING_ROOT_X) * (8.75 / (WING_TIP_X - WING_ROOT_X))


def wing_chord(x: float) -> float:
    return 7.30 - (x - WING_ROOT_X) * (5.30 / (WING_TIP_X - WING_ROOT_X))


def build_wings(mesh: Mesh) -> None:
    for side in (-1, 1):
        sections = []
        for f, y, th in ((0.00, -0.10, 0.055), (0.16, -0.12, 0.052),
                         (0.38, -0.16, 0.048), (0.60, -0.20, 0.045),
                         (0.82, -0.24, 0.042), (1.00, -0.27, 0.040)):
            x = WING_ROOT_X + (WING_TIP_X - WING_ROOT_X) * f
            sections.append({"le": v(side * x, y, wing_le(x)),
                             "chord": wing_chord(x), "thickness": th})
        name = "Su34_Wing_L" if side < 0 else "Su34_Wing_R"
        p = lifting_surface(mesh, name, "Su34_Camo", sections,
                            span_dir=v(side, 0, 0), thickness_dir=v(0, 1, 0),
                            chord_dir=v(0, 0, 1), airfoil_n=11, cap_root=False)
        mesh.orient(p, lambda c: v(c[0], -0.2, c[2]))

        # wing-root glove: a shallow wedge that fairings the wing into the hull
        glove = []
        for f, x, dy in ((0.0, 0.42, 0.16), (0.5, 0.78, 0.06), (1.0, 1.14, -0.02)):
            le = wing_le(max(x, WING_ROOT_X)) + 0.30
            glove.append({"le": v(side * x, dy, le),
                          "chord": wing_chord(max(x, WING_ROOT_X)) * 1.12,
                          "thickness": 0.075})
        p = lifting_surface(mesh, "Su34_WingGlove_L" if side < 0 else "Su34_WingGlove_R",
                            "Su34_Camo", glove, span_dir=v(side, 0, 0),
                            thickness_dir=v(0, 1, 0), chord_dir=v(0, 0, 1),
                            airfoil_n=9, cap_root=False)
        mesh.orient(p, lambda c: v(c[0], 0.0, c[2]))

        # aileron (outer) and flap (inner) along the trailing edge
        for label, x0, x1, mat in (("Flap", 1.75, 3.95, "Su34_CamoDark"),
                                   ("Aileron", 4.05, 7.20, "Su34_CamoDark")):
            surf = []
            for x, chord_frac in ((x0, 0.11), (x1, 0.10)):
                chord = wing_chord(abs(x)) * chord_frac
                hinge = wing_le(abs(x)) - wing_chord(abs(x)) + 0.02
                surf.append({"le": v(side * x, -0.235, hinge),
                             "chord": chord, "thickness": 0.115})
            p = lifting_surface(mesh, f"Su34_{label}_" + ("L" if side < 0 else "R"),
                                mat, surf, span_dir=v(side, 0, 0),
                                thickness_dir=v(0, 1, 0), chord_dir=v(0, 0, 1),
                                airfoil_n=7)
            mesh.orient(p, lambda c: v(c[0], -0.235, c[2]))

        # wingtip pod + rail
        tip_x = side * (WING_TIP_X + 0.02)
        mesh.cylinder("Su34_WingtipPod", "Su34_Metal",
                      v(tip_x, -0.27, -3.25), v(tip_x, -0.27, -5.05), 0.115, 0.075, segments=14)

    build_canards(mesh)


def build_canards(mesh: Mesh) -> None:
    """Close-coupled canard surfaces ahead of the wing root."""
    for side in (-1, 1):
        sections = []
        for f, x, y, th in ((0.0, 0.86, 0.60, 0.050), (0.5, 1.72, 0.575, 0.046),
                            (1.0, 2.55, 0.55, 0.042)):
            le = 5.32 - (x - 0.86) * 0.95
            sections.append({"le": v(side * x, y, le),
                             "chord": 1.65 - (x - 0.90) * 0.42, "thickness": th})
        p = lifting_surface(mesh, "Su34_Canard_L" if side < 0 else "Su34_Canard_R",
                            "Su34_Camo", sections, span_dir=v(side, 0, 0),
                            thickness_dir=v(0, 1, 0), chord_dir=v(0, 0, 1),
                            airfoil_n=9, cap_root=False)
        mesh.orient(p, lambda c: v(c[0], 0.60, c[2]))


# ----------------------------------------------------------------------- tail
def build_tail(mesh: Mesh) -> None:
    for side in (-1, 1):
        # All-moving stabilators
        sections = []
        for f, x, y, th in ((0.0, 1.05, 0.02, 0.050), (0.45, 2.50, -0.05, 0.046),
                            (0.75, 3.55, -0.10, 0.043), (1.0, 4.55, -0.16, 0.040)):
            le = -6.85 - (x - 1.05) * 0.72
            sections.append({"le": v(side * x, y, le),
                             "chord": 3.85 - (x - 1.05) * 0.62, "thickness": th})
        p = lifting_surface(mesh, "Su34_Stab_L" if side < 0 else "Su34_Stab_R",
                            "Su34_Camo", sections, span_dir=v(side, 0, 0),
                            thickness_dir=v(0, 1, 0), chord_dir=v(0, 0, 1),
                            airfoil_n=11, cap_root=False)
        mesh.orient(p, lambda c: v(c[0], -0.05, c[2]))

        # elevators on the stabilator trailing edge
        el = []
        for x, cf in ((2.40, 0.16), (4.40, 0.15)):
            chord = (3.85 - (abs(x) - 1.05) * 0.62) * cf
            hinge = -6.85 - (abs(x) - 1.05) * 0.72 - (3.85 - (abs(x) - 1.05) * 0.62)
            el.append({"le": v(side * x, -0.08, hinge),
                       "chord": chord, "thickness": 0.115})
        p = lifting_surface(mesh, "Su34_Elevator_L" if side < 0 else "Su34_Elevator_R",
                            "Su34_CamoDark", el, span_dir=v(side, 0, 0),
                            thickness_dir=v(0, 1, 0), chord_dir=v(0, 0, 1),
                            airfoil_n=7)
        mesh.orient(p, lambda c: v(c[0], -0.08, c[2]))

        # Canted twin fins. They stand on the outer shoulder of the nacelles,
        # so the root chord must end before the nacelles do (-10 m): otherwise
        # the fin hangs in the air behind the aircraft.
        # The root sits just above the nacelle crown (y ~= 0) so the fin is a
        # closed surface standing on the cowling rather than a shell buried in
        # it: buried shells poke through wherever the two surfaces cross.
        FIN_ROOT_Y = 0.06

        def fin_le(y: float) -> float:
            return -7.55 - (y - FIN_ROOT_Y) * 0.42

        def fin_chord(y: float) -> float:
            return 2.65 - (y - FIN_ROOT_Y) * 0.30

        def fin_x(y: float) -> float:
            return 1.06 + (y - FIN_ROOT_Y) * (1.63 - 1.06) / (3.55 - FIN_ROOT_Y)

        sections = []
        for y, th in ((FIN_ROOT_Y, 0.052), (1.20, 0.049), (2.40, 0.046), (3.22, 0.044)):
            sections.append({"le": v(side * fin_x(y), y, fin_le(y)),
                             "chord": fin_chord(y), "thickness": th})
        p = lifting_surface(mesh, "Su34_Fin_L" if side < 0 else "Su34_Fin_R",
                            "Su34_Camo", sections, span_dir=v(0, 1, 0),
                            thickness_dir=v(side, 0, 0), chord_dir=v(0, 0, 1),
                            airfoil_n=11, cap_root=False)
        mesh.orient(p, lambda c: v(side * 1.2, c[1], c[2]))

        # fin base fairing hides the joint with the cowling
        mesh.box("Su34_FinBase", "Su34_Camo",
                 v(side * 1.07, 0.10, fin_le(FIN_ROOT_Y) - fin_chord(FIN_ROOT_Y) * 0.55),
                 (0.20, 0.16, fin_chord(FIN_ROOT_Y) * 1.05))

        # white fin tip cap: the real aircraft carries one on both fins
        tip = []
        for y, th in ((3.20, 0.044), (3.38, 0.043), (3.55, 0.042)):
            tip.append({"le": v(side * fin_x(y), y, fin_le(y)),
                        "chord": fin_chord(y), "thickness": th})
        p = lifting_surface(mesh, "Su34_FinTip_L" if side < 0 else "Su34_FinTip_R",
                            "Su34_FinTip", tip, span_dir=v(0, 1, 0),
                            thickness_dir=v(side, 0, 0), chord_dir=v(0, 0, 1),
                            airfoil_n=11, cap_root=False)
        mesh.orient(p, lambda c: v(side * 1.2, c[1], c[2]))

        # rudder: a true flap on the fin trailing edge, not a floating panel
        rud = []
        for y in (0.85, 3.25):
            te = fin_le(y) - fin_chord(y)
            rud.append({"le": v(side * fin_x(y), y, te + 0.03),
                        "chord": 0.52 - (y - 0.85) * 0.02, "thickness": 0.11})
        p = lifting_surface(mesh, "Su34_Rudder_L" if side < 0 else "Su34_Rudder_R",
                            "Su34_CamoDark", rud, span_dir=v(0, 1, 0),
                            thickness_dir=v(side, 0, 0), chord_dir=v(0, 0, 1),
                            airfoil_n=7)
        mesh.orient(p, lambda c: v(side * 1.35, c[1], c[2]))

    # Tail boom with the brake-parachute container between the engines
    mesh.cylinder("Su34_TailBoom", "Su34_Camo",
                  v(0, 0.10, -10.60), v(0, 0.16, -12.15), 0.42, 0.19, segments=20)
    mesh.cylinder("Su34_BrakeChute", "Su34_Frame",
                  v(0, 0.16, -12.12), v(0, 0.17, -12.30), 0.19, 0.17, segments=16)
    # dorsal spine fairing between the fins
    mesh.box("Su34_SpineFairing", "Su34_Camo", v(0, 0.90, -8.4), (0.46, 0.22, 3.0))
    # antennas
    mesh.box("Su34_AntennaDorsal", "Su34_Frame", v(0, 1.10, -4.2), (0.05, 0.26, 0.55))
    mesh.box("Su34_AntennaVentral", "Su34_Frame", v(0, -1.04, -3.6), (0.04, 0.16, 0.40))
    mesh.box("Su34_AntennaTail", "Su34_Frame", v(0, 0.42, -11.9), (0.04, 0.30, 0.30))


# -------------------------------------------------------------------- engines
NACELLE_X = 0.95
NACELLE_Y = -0.55


def build_nacelles(mesh: Mesh) -> None:
    stations = [
        (2.55, 0.35, 0.35), (2.20, 0.44, 0.44), (1.60, 0.50, 0.51),
        (0.60, 0.53, 0.55), (-1.00, 0.53, 0.56), (-3.00, 0.52, 0.56),
        (-5.00, 0.51, 0.55), (-7.00, 0.49, 0.52), (-8.80, 0.46, 0.49),
        (-10.00, 0.42, 0.44),
    ]
    for side in (-1, 1):
        rings = []
        for z, hw, hh in stations:
            rings.append(fuselage_ring(z, hw, hh, -hh, 2.3, 28))
        rings = [[p + v(side * NACELLE_X, NACELLE_Y, 0) for p in r] for r in rings]
        p = mesh.loft("Su34_Nacelle_L" if side < 0 else "Su34_Nacelle_R",
                      "Su34_Camo", rings, cap_start=False, cap_end=True)
        mesh.orient(p, lambda c, s=side: v(s * NACELLE_X, NACELLE_Y, c[2]))

        # intake lip, dark throat and the splitter plate in front of it
        lip_ring = fuselage_ring(2.55, 0.35, 0.35, -0.35, 2.3, 28)
        lip_ring = [p + v(side * NACELLE_X, NACELLE_Y, 0) for p in lip_ring]
        lip2 = [p + v(0, 0, -0.12) for p in lip_ring]
        p = mesh.loft("Su34_IntakeLip_L" if side < 0 else "Su34_IntakeLip_R",
                      "Su34_Metal", [lip_ring, lip2])
        mesh.orient(p, lambda c, s=side: v(s * NACELLE_X, NACELLE_Y, c[2]))
        mesh.cylinder("Su34_Intake_L" if side < 0 else "Su34_Intake_R", "Su34_Intake",
                      v(side * NACELLE_X, NACELLE_Y, 2.45),
                      v(side * NACELLE_X, NACELLE_Y, 1.10),
                      0.32, 0.32, segments=22, caps=True, smooth=False)
        mesh.box("Su34_IntakeSplitter", "Su34_Metal",
                 v(side * (NACELLE_X - 0.10), NACELLE_Y, 2.62), (0.08, 0.70, 0.30))

        # nozzle: converging petals plus a dark interior
        mesh.cylinder("Su34_Nozzle_L" if side < 0 else "Su34_Nozzle_R", "Su34_Nozzle",
                      v(side * NACELLE_X, NACELLE_Y, -9.95),
                      v(side * NACELLE_X, NACELLE_Y, -11.45), 0.41, 0.32,
                      segments=22, caps=False)
        mesh.cylinder("Su34_NozzleInner", "Su34_Intake",
                      v(side * NACELLE_X, NACELLE_Y, -10.9),
                      v(side * NACELLE_X, NACELLE_Y, -11.55), 0.26, 0.26,
                      segments=18, caps=True, smooth=False)
        # two raised rings read as the petal seams without sticking out
        for zr, rad in ((-10.35, 0.395), (-10.95, 0.365)):
            mesh.cylinder("Su34_NozzleRing", "Su34_Nozzle",
                          v(side * NACELLE_X, NACELLE_Y, zr + 0.02),
                          v(side * NACELLE_X, NACELLE_Y, zr - 0.02),
                          rad, rad, segments=22, caps=False, smooth=False)

    # tail cone fairing between the nacelles
    mesh.box("Su34_NacelleFairing", "Su34_Camo", v(0, NACELLE_Y, -9.6), (0.86, 0.42, 1.8))


# ---------------------------------------------------------------------- gear
def build_gear(mesh: Mesh) -> None:
    # nose gear: twin wheels, drag brace, doors
    mesh.cylinder("Su34_NoseGearStrut", "Su34_Gear",
                  v(0, -0.86, 6.30), v(0, -2.15, 6.30), 0.075, 0.065, segments=12)
    mesh.cylinder("Su34_NoseGearBrace", "Su34_Gear",
                  v(0, -0.95, 6.95), v(0, -1.85, 6.35), 0.045, 0.040, segments=8)
    mesh.cylinder("Su34_NoseGearAxle", "Su34_Gear",
                  v(-0.28, -2.40, 6.30), v(0.28, -2.40, 6.30), 0.05, 0.05, segments=8)
    for sx in (-1, 1):
        mesh.cylinder("Su34_NoseWheel", "Su34_Tire",
                      v(sx * 0.11, -2.40, 6.30), v(sx * 0.29, -2.40, 6.30),
                      0.32, 0.32, segments=20, caps=True)
        mesh.cylinder("Su34_NoseHub", "Su34_Metal",
                      v(sx * 0.28, -2.40, 6.30), v(sx * 0.31, -2.40, 6.30),
                      0.12, 0.12, segments=12, caps=True)
    mesh.box("Su34_NoseGearDoorL", "Su34_Underside", v(-0.26, -0.98, 6.05), (0.34, 0.04, 1.05))
    mesh.box("Su34_NoseGearDoorR", "Su34_Underside", v(0.26, -0.98, 6.05), (0.34, 0.04, 1.05))

    # main gear: tandem bogies under the engine nacelles
    for side in (-1, 1):
        x = side * 2.10
        mesh.cylinder("Su34_MainGearStrut", "Su34_Gear",
                      v(x, -1.05, -1.20), v(x, -2.20, -1.20), 0.085, 0.070, segments=12)
        mesh.cylinder("Su34_MainGearBrace", "Su34_Gear",
                      v(x, -1.15, -1.90), v(x, -2.00, -1.30), 0.050, 0.045, segments=8)
        mesh.cylinder("Su34_MainGearBogie", "Su34_Gear",
                      v(x, -2.20, -2.20), v(x, -2.20, -0.20), 0.06, 0.06, segments=10)
        for z in (-1.70, -0.70):
            for sx in (-1, 1):
                mesh.cylinder("Su34_MainWheel", "Su34_Tire",
                              v(x + sx * 0.12, -2.42, z), v(x + sx * 0.31, -2.42, z),
                              0.40, 0.40, segments=20, caps=True)
                mesh.cylinder("Su34_MainHub", "Su34_Metal",
                              v(x + sx * 0.30, -2.42, z), v(x + sx * 0.33, -2.42, z),
                              0.15, 0.15, segments=12, caps=True)
        mesh.box("Su34_MainGearDoor", "Su34_Underside",
                 v(side * 1.02, -1.06, -1.20), (0.46, 0.04, 2.30))


# -------------------------------------------------------------------- pylons
def build_pylons(mesh: Mesh) -> None:
    for side in (-1, 1):
        for x_frac, z, length in ((0.24, -0.40, 1.30), (0.44, -0.75, 1.25),
                                  (0.64, -1.20, 1.15), (0.84, -1.75, 1.05)):
            x = WING_ROOT_X + (WING_TIP_X - WING_ROOT_X) * x_frac
            y = -0.30 - 0.02 * x_frac
            mesh.box("Su34_PylonWing", "Su34_CamoDark",
                     v(side * x, y - 0.16, z), (0.16, 0.28, length))
            mesh.box("Su34_PylonShoe", "Su34_Metal",
                     v(side * x, y - 0.30, z), (0.11, 0.09, length * 0.86))
        # fuselage / intake pylons
        mesh.box("Su34_PylonBody", "Su34_CamoDark",
                 v(side * 1.06, -1.10, 0.55), (0.14, 0.26, 1.25))


# ------------------------------------------------------------------- details
def build_details(mesh: Mesh) -> None:
    # nose: pitot booms and the IRST ball offset to port
    # dark tip on the radome, then the single centre pitot boom
    mesh.cylinder("Su34_RadomeTip", "Su34_Frame",
                  v(0.0, 0.0, 11.05), v(0.0, 0.0, 11.60), 0.17, 0.075, segments=16)
    mesh.cylinder("Su34_Pitot", "Su34_Metal",
                  v(0.0, 0.0, 11.55), v(0.0, 0.0, 12.62), 0.030, 0.010, segments=8)
    mesh.box("Su34_PitotVane", "Su34_Metal", v(0.0, 0.0, 12.28), (0.02, 0.02, 0.16))

    # IRST sphere in front of the windscreen (right of centreline on the Su-34)
    mesh.cylinder("Su34_IRST", "Su34_Frame",
                  v(0.26, 0.82, 7.95), v(0.26, 0.98, 8.10), 0.11, 0.10, segments=14)
    mesh.cylinder("Su34_IRSTLens", "Su34_Intake",
                  v(0.26, 0.96, 8.06), v(0.26, 0.99, 8.12), 0.085, 0.085,
                  segments=14, caps=True, smooth=False)

    # refuelling probe on the port side of the nose
    mesh.cylinder("Su34_RefuelProbe", "Su34_Metal",
                  v(-0.56, 0.55, 7.55), v(-0.68, 0.62, 8.55), 0.045, 0.030, segments=10)
    mesh.box("Su34_RefuelFairing", "Su34_Camo", v(-0.58, 0.52, 7.60), (0.14, 0.14, 0.65))

    # gun mount fairing on the starboard lower nose
    mesh.box("Su34_GunFairing", "Su34_Camo", v(0.42, -0.72, 6.55), (0.30, 0.30, 0.90))
    mesh.cylinder("Su34_GunBarrel", "Su34_Metal",
                  v(0.42, -0.82, 7.00), v(0.42, -0.84, 7.42), 0.035, 0.030, segments=10)

    # airbrake panels on the upper rear fuselage
    for side in (-1, 1):
        mesh.box("Su34_Airbrake", "Su34_CamoDark",
                 v(side * 0.50, 0.79, -5.6), (0.36, 0.035, 1.05))

    # formation light strips and a couple of small vents
    for side in (-1, 1):
        mesh.box("Su34_Vent", "Su34_Intake", v(side * 0.60, 0.24, 2.2), (0.12, 0.06, 0.30))
        mesh.box("Su34_Vent", "Su34_Intake", v(side * 0.74, -0.18, -3.4), (0.09, 0.08, 0.26))

    build_decals(mesh)



def _outward(corners, side: int):
    """Order a decal quad so its normal points away from the aircraft."""
    a, b, c = corners[0], corners[1], corners[2]
    n = np.cross(b - a, c - a)
    if np.dot(n, np.array([side, 0.0, 0.0])) < 0:
        return corners[::-1]
    return corners



def _decal_uvs(corners, side: int):
    """World-space UVs for a side decal so the artwork reads correctly."""
    zs = [c[2] for c in corners]
    ys = [c[1] for c in corners]
    z0, z1 = min(zs), max(zs)
    y0, y1 = min(ys), max(ys)
    dz = max(z1 - z0, 1e-6)
    dy = max(y1 - y0, 1e-6)
    uvs = []
    for c in corners:
        u = (c[2] - z0) / dz
        if side > 0:
            u = 1.0 - u
        uvs.append((u, (c[1] - y0) / dy))
    return uvs


def build_decals(mesh: Mesh) -> None:
    """Red stars on the fins and the bort number on the nose.

    These are flat quads with authored UVs (the whole decal texture) placed on
    the skin: the star follows the fin cant, the number follows the local
    fuselage half width, so neither floats off the surface.
    """
    def fin_x(y: float) -> float:
        return 1.06 + (y - 0.06) * (1.63 - 1.06) / (3.55 - 0.06)

    star_y0, star_y1 = 1.35, 2.75
    star_z0, star_z1 = -9.55, -8.35
    num_y0, num_y1 = 0.12, 0.92
    num_z0, num_z1 = 7.55, 8.50

    for side in (-1, 1):
        corners = [
            v(side * (fin_x(star_y0) + 0.075), star_y0, star_z0),
            v(side * (fin_x(star_y0) + 0.062), star_y0, star_z1),
            v(side * (fin_x(star_y1) + 0.050), star_y1, star_z1),
            v(side * (fin_x(star_y1) + 0.050), star_y1, star_z0),
        ]
        quad = _outward(corners, side)
        mesh.quad("Su34_Star", "Su34_Star", quad, uvs=_decal_uvs(quad, side))

        def nose_x(z: float) -> float:
            hw, _, _, _ = station_at(z)
            return hw + 0.014

        corners = [
            v(side * nose_x(num_z0), num_y0, num_z0),
            v(side * nose_x(num_z1), num_y0, num_z1),
            v(side * nose_x(num_z1), num_y1, num_z1),
            v(side * nose_x(num_z0), num_y1, num_z0),
        ]
        quad = _outward(corners, side)
        mesh.quad("Su34_BortNumber", "Su34_Number", quad, uvs=_decal_uvs(quad, side))


# ------------------------------------------------------------------------ main
def build() -> Mesh:
    mesh = Mesh()
    build_fuselage(mesh)
    build_wings(mesh)
    build_tail(mesh)
    build_nacelles(mesh)
    build_gear(mesh)
    build_pylons(mesh)
    build_details(mesh)
    apply_box_uv(mesh, tile_size=5.0)
    return mesh


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    mesh = build()
    obj_path = os.path.join(OUT_DIR, "su34.obj")
    write_obj(obj_path, mesh, mtl_name="su34.mtl")
    write_mtl(os.path.join(OUT_DIR, "su34.mtl"), MATERIALS)

    tris = sum(len(p.faces) for p in mesh.parts)
    verts = sum(len(p.vertices) for p in mesh.parts)
    used = sorted({p.material for p in mesh.parts})
    print(f"wrote {obj_path}")
    print(f"  parts: {len(mesh.parts)}  raw verts: {verts}  tris: {tris}")
    print(f"  materials used: {len(used)} -> {', '.join(used)}")


if __name__ == "__main__":
    main()
