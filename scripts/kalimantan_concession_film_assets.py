#!/usr/bin/env python3
"""Maps and figures for the Remotion film on Kalimantan burns vs concessions.

Reads what scripts/kalimantan_burn_concessions.py wrote -- its cached tiles,
CSVs and summary.json -- and writes, into video/narasi-karhutla:

  public/konsesi/peta.png         Kalimantan, 2026 burn inside/outside concessions
  public/konsesi/peta_titik.png   the same ground, Sep-Oct FIRMS hotspots
  public/konsesi/ketapang.png     the Ketapang cluster, concessions labelled
  src/konsesiData.json            every figure the film shows or speaks

Concessions are named by ACRONYM only (initials of the company name, "PT"
and "Tbk" dropped), on the map and in the data. The rule is mechanical so
the same company always gets the same letters.

All images are 1920x1080 on the film's soot ground with the map placed on
the right, leaving the left column for type.

    conda run -n base python scripts/kalimantan_concession_film_assets.py
"""

import glob
import json
import os
import re
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SSD_ROOT = "/Volumes/ExtremeSSD/Dropbox/GitHub/rs-change-detection"
_DATA_ROOT = (os.environ.get("RSCD_DATA_ROOT")
              or (_SSD_ROOT if os.path.isdir(_SSD_ROOT) else _REPO_ROOT))
RUN = os.path.join(_DATA_ROOT, "output", "fire", "kalimantan_concessions")
FILM = os.path.join(_REPO_ROOT, "video", "narasi-karhutla")
YEAR = 2026
TOP = 4                                     # concessions named in the film

os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)

# teema.ts
JELAGA, ARANG, GARIS, ABU = "#0A0C0F", "#161A20", "#262C35", "#7E8792"
KAPUR, BARA, NYALA = "#E8EBEE", "#FF5A1F", "#FFB020"
KONSESI = "#34493C"                        # muted green, sits under ember


def akronim(name):
    s = re.sub(r"\b(PT|Tbk)\b\.?", " ", name or "", flags=re.I)
    words = [w for w in re.split(r"[\s.,]+", s) if w]
    return "PT " + "".join(w[0].upper() for w in words)


def ucap(acr):
    """How Bian should say it: Indonesian letter names, one hyphenated run.

    Every e-letter carries é so the voice does not reduce it to a schwa:
    PT AM -> 'pé-té-a-ém'.
    """
    nama = {"A": "a", "B": "bé", "C": "cé", "D": "dé", "E": "é", "F": "éf",
            "G": "gé", "H": "ha", "I": "i", "J": "jé", "K": "ka", "L": "él",
            "M": "ém", "N": "én", "O": "o", "P": "pé", "Q": "ki", "R": "ér",
            "S": "és", "T": "té", "U": "u", "V": "vé", "W": "wé", "X": "éks",
            "Y": "yé", "Z": "zét"}
    return "-".join(nama[c] for c in acr.replace(" ", ""))


def stack():
    import rasterio
    from rasterio.merge import merge
    paths = sorted(glob.glob(os.path.join(RUN, f"tiles_{YEAR}_*", "tile_*.tif")))
    if not paths:
        raise SystemExit("no tiles — run kalimantan_burn_concessions.py first")
    srcs = [rasterio.open(p) for p in paths]
    arr, tr = merge(srcs, method="max")
    for s in srcs:
        s.close()
    return arr, tr


def frame(path, cls, tr, colors, extent=None, overlay=None, labels=(),
          right=True):
    """One 1920x1080 still: class raster on soot, map in the right column."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.colors import ListedColormap
    import matplotlib.patheffects as pe

    h, w = cls.shape
    full = (tr.c, tr.c + w * tr.a, tr.f + h * tr.e, tr.f)
    x0, x1, y0, y1 = extent or full
    fig = plt.figure(figsize=(19.2, 10.8), dpi=100, facecolor=JELAGA)
    # The map's box: right-hand 62% of the frame, aspect kept, and clear of
    # the film's header rule (y < 130 px) and source line (y > 960 px).
    bw, bh = (0.62, 0.72) if right else (0.9, 0.72)
    aspect = (x1 - x0) / (y1 - y0) * (10.8 / 19.2)
    if aspect > bw / bh:
        ww, hh = bw, bw / aspect
    else:
        ww, hh = bh * aspect, bh
    left = (0.97 - ww) if right else (0.5 - ww / 2)
    ax = fig.add_axes([left, 0.5 - hh / 2, ww, hh])
    ax.set_facecolor(JELAGA)
    ax.imshow(cls, cmap=ListedColormap(colors), vmin=0, vmax=len(colors) - 1,
              extent=full, interpolation="nearest")
    if overlay is not None:
        overlay(ax)
    for x, y, t in labels:
        ax.annotate(t, (x, y), xytext=(14, 10), textcoords="offset points",
                    fontsize=22, fontweight="bold", color=KAPUR,
                    fontfamily="DejaVu Sans",
                    path_effects=[pe.withStroke(linewidth=6, foreground=JELAGA)])
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.axis("off")
    fig.savefig(path, facecolor=JELAGA)
    plt.close(fig)
    print(f"Saved: {path}")


def main():
    import geopandas as gpd
    import numpy as np
    import pandas as pd
    from rasterio import features

    S = json.load(open(os.path.join(RUN, "summary.json")))
    per = pd.read_csv(os.path.join(RUN, "concessions_burned.csv"))
    pat = pd.read_csv(os.path.join(RUN, f"patches_{YEAR}.csv"))
    conc = gpd.read_file(os.path.join(RUN, "concessions_kalimantan.gpkg"))
    hs = pd.read_csv(glob.glob(os.path.join(RUN, "firms_*.csv"))[0])

    arr, tr = stack()
    kab, burn = arr[0], arr[1] > 0
    land = kab > 0
    shape = kab.shape
    inside = features.rasterize([(g, 1) for g in conc.geometry], out_shape=shape,
                                transform=tr, dtype="uint8").astype(bool) & land
    burn &= land

    # Kabupaten edges, faint, drawn as their own class.
    edge = np.zeros_like(land)
    k32 = kab.astype(np.int32)
    edge[:, 1:] |= k32[:, 1:] != k32[:, :-1]
    edge[1:, :] |= k32[1:, :] != k32[:-1, :]
    edge &= land

    os.makedirs(os.path.join(FILM, "public", "konsesi"), exist_ok=True)
    out = lambda n: os.path.join(FILM, "public", "konsesi", n)  # noqa: E731

    # 0 sea, 1 land, 2 kab edge, 3 concession, 4 burn outside, 5 burn inside
    from scipy import ndimage

    def classes(b_out, b_in):
        c = np.zeros(shape, np.uint8)
        c[land] = 1
        c[edge] = 2
        c[inside] = 3
        c[b_out] = 4
        c[b_in] = 5
        return c

    pal = [JELAGA, "#1B2029", "#232933", KONSESI, NYALA, BARA]
    # At national scale a 500 m pixel is half a screen pixel and the burn
    # vanishes. For that frame only, each burned pixel is grown by three
    # pixels (about 1.5 km) and the film says so on screen; the zoomed
    # Ketapang frame uses the true pixels. A grown pixel keeps the class of
    # the burn it grew from, not of the ground it spilled onto.
    g_in = ndimage.binary_dilation(burn & inside, iterations=3) & land
    g_out = ndimage.binary_dilation(burn & ~inside, iterations=3) & land & ~g_in
    frame(out("peta.png"), classes(g_out, g_in), tr, pal)
    cls = classes(burn & ~inside, burn & inside)

    # Hotspots over concessions only, burn hidden: a different sensor and a
    # different period, so it must not share a frame with the MCD64A1 burn.
    cls2 = cls.copy()
    cls2[burn] = np.where(inside[burn], 3, 1)

    def dots(ax):
        ax.scatter(hs.lon, hs.lat, s=1.1, c=NYALA, alpha=0.18, lw=0)
    frame(out("peta_titik.png"), cls2, tr, pal, overlay=dots)

    # Ketapang: the TOP concessions by 2026 burn, which all sit there.
    top = per.head(TOP).copy()
    top["akronim"] = top.company.map(akronim)
    sel = conc[conc.gfwid.isin(top.gfwid)]
    x0, y0, x1, y1 = sel.total_bounds
    pad = 0.12
    ext = (x0 - pad, x1 + pad, y0 - pad, y1 + pad)

    def outlines(ax):
        sel.boundary.plot(ax=ax, color=KAPUR, lw=1.6)
    lab = []
    for _, r in top.iterrows():
        g = sel[sel.gfwid == r.gfwid].geometry.iloc[0]
        p = g.representative_point()
        lab.append((p.x, p.y, r.akronim))
    frame(out("ketapang.png"), cls, tr, pal, extent=ext, overlay=outlines,
          labels=lab)

    y = S["years"]
    biggest = pat.iloc[0]
    D = {
        "_comment": ["Ditulis oleh scripts/kalimantan_concession_film_assets.py",
                     "dari keluaran kalimantan_burn_concessions.py. Jangan ketik",
                     "angka di sini dengan tangan; jalankan ulang skripnya."],
        "mcd64a1_bulan_akhir": S["mcd64a1_last_month"],
        "titik_jendela": S["hotspot_window"],
        "daratan_ha": S["land_ha"],
        "konsesi_ha": S["concession_ha"],
        "konsesi_pct": 100 * S["concession_ha"] / S["land_ha"],
        "poligon_konsesi": S["concession_polygons_in_kalimantan"],
        "tahun": [{"tahun": int(k), "terbakar_ha": v["burned_ha"],
                   "dalam_ha": v["burned_in_concession_ha"],
                   "dalam_pct": 100 * v["share_in_concession"],
                   "periode": v["period"]}
                  for k, v in sorted(y.items())],
        "titik": {"total": S["hotspots"]["total"],
                  "dalam": S["hotspots"]["in_concession"],
                  "dalam_pct": 100 * S["hotspots"]["in_concession"]
                  / S["hotspots"]["total"]},
        "konsesi_teratas": [
            {"akronim": r.akronim, "ucap": ucap(r.akronim),
             "kabupaten": r.kabupaten, "provinsi": r.province,
             "luas_ha": r.area_ha, "terbakar_ha": r[f"burned_{YEAR}_ha"],
             "terbakar_pct": r[f"burned_{YEAR}_pct"]}
            for _, r in top.iterrows()],
        "patch_terbesar": {"luas_ha": biggest.area_ha,
                           "dalam_ha": biggest.in_concession_ha,
                           "kabupaten": biggest.kabupaten,
                           "provinsi": biggest.province},
    }
    D["konsesi_teratas_total_ha"] = sum(c["terbakar_ha"] for c in D["konsesi_teratas"])
    cur = next(t for t in D["tahun"] if t["tahun"] == YEAR)
    D["luar_pct"] = 100 - cur["dalam_pct"]
    with open(os.path.join(FILM, "src", "konsesiData.json"), "w") as f:
        json.dump(D, f, indent=1, ensure_ascii=False)
    print(json.dumps({k: D[k] for k in ("tahun", "titik", "konsesi_teratas",
                                        "patch_terbesar", "luar_pct",
                                        "konsesi_teratas_total_ha")},
                     indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
