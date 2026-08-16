"""Generate an Excalidraw diagram of the Flores InSAR methodology.

Writes a native .excalidraw file (open at excalidraw.com, or with the VS Code
extension) rather than an image, so the diagram stays editable.

The shape of the flow is the argument: everything from acquisition down to the
velocity fields is ordinary processing, and then a single decision -- do the two
tracks agree? -- decides whether the decomposition below it means anything. The
co-seismic branch runs beside it precisely because it skips almost all of the
correction machinery.
"""

import json
import os

# Excalidraw's palette, so the file looks native rather than imported.
BLUE = "#a5d8ff"      # data
GREEN = "#b2f2bb"     # processing
YELLOW = "#ffec99"    # guards and checks
ORANGE = "#ffd8a8"    # decision
RED = "#ffc9c9"       # negative outcome
PURPLE = "#d0bfff"    # co-seismic branch
GREY = "#e9ecef"      # notes

INK = "#1e1e1e"
DIM = "#868e96"

elements = []
_seed = [1000]


def _next():
    _seed[0] += 1
    return _seed[0]


def box(eid, x, y, w, h, text, fill=GREEN, font=16, dashed=False, rounded=True):
    """A labelled rectangle. Text is bound to the container so it moves with it."""
    tid = eid + "_t"
    elements.append({
        "id": eid, "type": "rectangle", "x": x, "y": y, "width": w, "height": h,
        "angle": 0, "strokeColor": INK, "backgroundColor": fill,
        "fillStyle": "solid", "strokeWidth": 2,
        "strokeStyle": "dashed" if dashed else "solid",
        "roughness": 1, "opacity": 100, "groupIds": [], "frameId": None,
        "roundness": {"type": 3} if rounded else None,
        "seed": _next(), "version": 1, "versionNonce": _next(),
        "isDeleted": False, "boundElements": [{"id": tid, "type": "text"}],
        "updated": 1, "link": None, "locked": False,
    })
    elements.append({
        "id": tid, "type": "text", "x": x + 8, "y": y + h / 2 - font,
        "width": w - 16, "height": font * 1.25, "angle": 0,
        "strokeColor": INK, "backgroundColor": "transparent",
        "fillStyle": "solid", "strokeWidth": 2, "strokeStyle": "solid",
        "roughness": 1, "opacity": 100, "groupIds": [], "frameId": None,
        "roundness": None, "seed": _next(), "version": 1,
        "versionNonce": _next(), "isDeleted": False, "boundElements": [],
        "updated": 1, "link": None, "locked": False,
        "text": text, "fontSize": font, "fontFamily": 2,
        "textAlign": "center", "verticalAlign": "middle",
        "baseline": font, "containerId": eid,
        "originalText": text, "lineHeight": 1.25,
    })
    return eid


def diamond(eid, x, y, w, h, text, fill=ORANGE, font=15):
    tid = eid + "_t"
    elements.append({
        "id": eid, "type": "diamond", "x": x, "y": y, "width": w, "height": h,
        "angle": 0, "strokeColor": INK, "backgroundColor": fill,
        "fillStyle": "solid", "strokeWidth": 2, "strokeStyle": "solid",
        "roughness": 1, "opacity": 100, "groupIds": [], "frameId": None,
        "roundness": None, "seed": _next(), "version": 1,
        "versionNonce": _next(), "isDeleted": False,
        "boundElements": [{"id": tid, "type": "text"}],
        "updated": 1, "link": None, "locked": False,
    })
    elements.append({
        "id": tid, "type": "text", "x": x + w * 0.18, "y": y + h / 2 - font,
        "width": w * 0.64, "height": font * 1.25, "angle": 0,
        "strokeColor": INK, "backgroundColor": "transparent",
        "fillStyle": "solid", "strokeWidth": 2, "strokeStyle": "solid",
        "roughness": 1, "opacity": 100, "groupIds": [], "frameId": None,
        "roundness": None, "seed": _next(), "version": 1,
        "versionNonce": _next(), "isDeleted": False, "boundElements": [],
        "updated": 1, "link": None, "locked": False,
        "text": text, "fontSize": font, "fontFamily": 2,
        "textAlign": "center", "verticalAlign": "middle",
        "baseline": font, "containerId": eid,
        "originalText": text, "lineHeight": 1.25,
    })
    return eid


def label(x, y, text, size=14, colour=DIM, align="left", width=280):
    elements.append({
        "id": f"lbl{_next()}", "type": "text", "x": x, "y": y,
        "width": width, "height": size * 1.25 * (text.count("\n") + 1),
        "angle": 0, "strokeColor": colour, "backgroundColor": "transparent",
        "fillStyle": "solid", "strokeWidth": 1, "strokeStyle": "solid",
        "roughness": 1, "opacity": 100, "groupIds": [], "frameId": None,
        "roundness": None, "seed": _next(), "version": 1,
        "versionNonce": _next(), "isDeleted": False, "boundElements": [],
        "updated": 1, "link": None, "locked": False,
        "text": text, "fontSize": size, "fontFamily": 2,
        "textAlign": align, "verticalAlign": "top", "baseline": size,
        "containerId": None, "originalText": text, "lineHeight": 1.25,
    })


def arrow(a, b, text=None, dashed=False, colour=INK):
    """Bind an arrow between two elements; Excalidraw routes it."""
    ea = next(e for e in elements if e["id"] == a)
    eb = next(e for e in elements if e["id"] == b)
    x1 = ea["x"] + ea["width"] / 2
    y1 = ea["y"] + ea["height"]
    x2 = eb["x"] + eb["width"] / 2
    y2 = eb["y"]
    aid = f"ar{_next()}"
    elements.append({
        "id": aid, "type": "arrow", "x": x1, "y": y1,
        "width": abs(x2 - x1), "height": abs(y2 - y1), "angle": 0,
        "strokeColor": colour, "backgroundColor": "transparent",
        "fillStyle": "solid", "strokeWidth": 2,
        "strokeStyle": "dashed" if dashed else "solid",
        "roughness": 1, "opacity": 100, "groupIds": [], "frameId": None,
        "roundness": {"type": 2}, "seed": _next(), "version": 1,
        "versionNonce": _next(), "isDeleted": False, "boundElements": [],
        "updated": 1, "link": None, "locked": False,
        "points": [[0, 0], [x2 - x1, y2 - y1]],
        "lastCommittedPoint": None,
        "startBinding": {"elementId": a, "focus": 0, "gap": 4},
        "endBinding": {"elementId": b, "focus": 0, "gap": 4},
        "startArrowhead": None, "endArrowhead": "arrow",
    })
    for e in (ea, eb):
        e["boundElements"].append({"id": aid, "type": "arrow"})
    if text:
        label(min(x1, x2) + 10, (y1 + y2) / 2 - 10, text, size=13, colour=DIM,
              width=120)
    return aid


# ─────────────────────────── layout ───────────────────────────
X, W, H = 360, 340, 66      # main column
GAP = 108

label(300, -80, "Interseismic InSAR over Flores — methodology",
      size=28, colour=INK, width=760)
label(300, -40,
      "705 Sentinel-1 pairs · 2022-08 → 2026-08 · ASF HyP3 + MintPy",
      size=15, width=760)

y = 20
box("acq", X, y, W, H,
    "Sentinel-1A/D SLC   IW\n351 asc (path 112) · 354 desc (path 163)", BLUE, 14)
y += GAP
box("hyp3", X, y, W, H,
    "ASF HyP3  INSAR_GAMMA  20×4 looks\nSBAS: 3 connections, ≤ 60 d baseline", GREEN, 14)
label(X + W + 24, y + 6,
      "+ DEM, incidence, look vectors\n(lv_theta / lv_phi — azimuth angle)", 13)
y += GAP

box("norm", X, y, W, H,
    "normalize_grid\nwarp all bands to the modal grid", YELLOW, 14)
label(X + W + 24, y + 6,
      "HyP3 sizes each product to its own\nfootprint; load_data silently DROPS\n"
      "any that differ — 387 pairs lost", 13)
y += GAP

box("prep", X, y, W, H, "prep_hyp3\nwrite .rsc metadata per product", GREEN, 14)
y += GAP

box("load", X, y, W, H,
    "MintPy load_data\nifgramStack.h5 + geometryGeo.h5", GREEN, 14)
y += GAP

box("guard", X, y, W, H,
    "check_stack   ← GUARD\nloaded pairs == pairs on disk?", YELLOW, 14)
label(X + W + 24, y + 12,
      "the only defence against a run that\n'succeeds' on less data than you think", 13)
y += GAP

box("inv", X, y, W, H,
    "invert_network → timeseries.h5\nminTempCoh 0.1 · unwrapError OFF", GREEN, 14)
label(X + W + 24, y + 6,
      "OFF because HyP3 GAMMA ships no\nconnected components; phase_closure\n"
      "writes zeros that 'auto' then prefers", 13)
y += GAP

box("corr", X, y, W, H,
    "Corrections\nsolid Earth tides → ERA5 → topo residual", GREEN, 14)
label(X + W + 24, y + 12, "deramp OFF: singular over a sparse mask", 13)
y += GAP

box("vel", X, y, W, H,
    "timeseries2velocity\nLOS velocity, mm/yr — each track", BLUE, 14)
y += GAP

box("ref", X, y, W, H,
    "common_reference\none reference pixel for BOTH tracks", YELLOW, 14)
label(X + W + 24, y + 12,
      "auto-chosen references landed 178 km apart", 13)
y += GAP + 6

diamond("test", X - 30, y, W + 60, 130,
        "asc vs desc\nAGREEMENT TEST\ncorrelate the two LOS fields")
label(X + W + 54, y + 40,
      "uses NO incidence, NO azimuth,\nNO decomposition — upstream of\n"
      "every geometric assumption", 13)
y += 130 + 70

box("neg", 40, y, 320, 96,
    "r ≈ 0  →  DISAGREE\nfields are not common ground motion\n"
    "REPORT THE NEGATIVE RESULT", RED, 14)
box("pos", 740, y, 320, 96,
    "r > 0.5  →  AGREE\ndecompose into vertical + east-west\n"
    "(asc_desc2horz_vert)", PURPLE, 14)

arrow("acq", "hyp3")
arrow("hyp3", "norm")
arrow("norm", "prep")
arrow("prep", "load")
arrow("load", "guard")
arrow("guard", "inv")
arrow("inv", "corr")
arrow("corr", "vel")
arrow("vel", "ref")
arrow("ref", "test")
arrow("test", "neg", "r ≈ 0.05–0.09")
arrow("test", "pos", "not observed", dashed=True)

y += 96 + 46
box("out", 40, y, 320, 92,
    "RESULT\nnoise floor 24–26 mm/yr\natmosphere-limited, not decorrelation", GREY, 14)
arrow("neg", "out")

label(40, y + 108,
      "Coherence PERSISTS (median 67/156 desc, 144/162 asc).\n"
      "Flores is savanna, not high-canopy forest — so the\n"
      "limit is turbulent troposphere below ERA5's ~30 km grid,\n"
      "not loss of scatterers.", 13, width=400)

# ── co-seismic branch, deliberately short ──
# Its own column, clear of the AGREE box at x=740..1060: this is a parallel
# route through the same data, not an outcome of the agreement test.
cx = 1160
box("cos1", cx, y - 300, 320, 84,
    "CO-SEISMIC  (single pair)\n2026-08-06 → 2026-08-18 spanning M7.7", PURPLE, 14)
box("cos2", cx, y - 300 + 108, 320, 84,
    "HyP3 10×2 looks + LOS displacement\nNO stacking · NO ERA5 · NO time series", PURPLE, 14)
box("cos3", cx, y - 300 + 216, 320, 84,
    "asc + desc → vertical & east-west\nsame decomposition, real signal", PURPLE, 14)
arrow("cos1", "cos2")
arrow("cos2", "cos3")
label(cx, y - 348,
      "Why this works where the above did not:\n"
      "displacement is 10–30 cm against a few cm of\n"
      "per-pair atmosphere — roughly 3–10× margin.", 13, width=340)

out = {
    "type": "excalidraw",
    "version": 2,
    "source": "https://excalidraw.com",
    "elements": elements,
    "appState": {"gridSize": None, "viewBackgroundColor": "#ffffff"},
    "files": {},
}

dest = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "docs", "flores_insar_methodology.excalidraw")
os.makedirs(os.path.dirname(dest), exist_ok=True)
with open(dest, "w") as f:
    json.dump(out, f, indent=1)

print(f"wrote {dest}")
print(f"  {len(elements)} elements "
      f"({sum(1 for e in elements if e['type'] == 'rectangle')} boxes, "
      f"{sum(1 for e in elements if e['type'] == 'diamond')} decisions, "
      f"{sum(1 for e in elements if e['type'] == 'arrow')} arrows, "
      f"{sum(1 for e in elements if e['type'] == 'text')} labels)")
