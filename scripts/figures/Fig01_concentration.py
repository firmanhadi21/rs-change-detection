"""Fig01 (hero): concessions as a whole did not burn more than comparable land, but a few did.

(a) map of the 1,095 analysed concessions by per-unit matched class (BH q <= 0.05) over 2026 S2 burned
    cells (1 km aggregation); WGS 84 (EPSG:4326), Ketapang four ringed;
(b) matching ladder: burned-share ratio as covariates are added cumulatively (matched.json);
(c) concentration curve: cumulative share of concession burned area vs cumulative share of units ranked
    by matched ratio (per_concession_matched.csv).

    python scripts/figures/Fig01_concentration.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from _style import (BURN, CTL, DATA, DEFICIT, EXCESS, INK, KIND_COL, NODIFF, RUN, W_DOUBLE, panel, run,  # noqa: E402
                    save, setup)


def units_gdf():
    import geopandas as gpd
    from kalimantan_excess_burn import CONC, HTI, KAL
    op = gpd.read_file(CONC).to_crs(4326).cx[KAL[0]:KAL[2], KAL[1]:KAL[3]].reset_index(drop=True)
    hti = gpd.read_file(HTI).to_crs(4326).reset_index(drop=True)
    P = pd.read_csv(os.path.join(RUN, "per_concession_matched.csv"))
    P["geometry"] = [(op if k == "oil palm" else hti).geometry.iloc[i - 1] for k, i in zip(P.kind, P.id)]
    g = gpd.GeoDataFrame(P, crs=4326)
    g["geometry"] = g.geometry.make_valid()
    return g


def burned_raster():
    import json
    df = pd.read_parquet(os.path.join(DATA, "sample_200m.parquet"), columns=["r", "c", "burned"])
    grid = json.load(open(os.path.join(DATA, "sample_grid.json")))
    tr, (ny, nx) = grid["transform"], grid["shape"]
    f = 5                                                     # 5 x 200 m = 1 km
    b = df[df.burned]
    img = np.zeros((ny // f + 1, nx // f + 1))
    np.add.at(img, (b.r.to_numpy() // f, b.c.to_numpy() // f), 1)
    ext = (tr[2], tr[2] + nx * tr[0], tr[5] - ny * abs(tr[4]), tr[5])
    return np.ma.masked_equal(img, 0), ext


def main():
    setup()
    import geopandas as gpd
    from shapely.geometry import box
    from ketapang_fire_origin import FOUR
    g = units_gdf()
    ne = gpd.read_file(os.path.join(DATA, "ne_countries", "ne_10m_admin_0_countries.zip"))
    bb = box(108.3, -4.6, 119.3, 7.5)
    fig = plt.figure(figsize=(W_DOUBLE, 4.6))
    ax = fig.add_axes([0.0, 0.0, 0.55, 1.0])
    ne[ne.ADM0_A3.isin(["MYS", "BRN"])].clip(bb).plot(ax=ax, color="#EFEFEF", edgecolor="#BDBDBD", lw=0.4)
    idn = ne[ne.ADM0_A3 == "IDN"].clip(bb).explode(index_parts=False)
    b_ = idn.geometry.bounds
    idn[~((b_.minx > 118.6) & (b_.maxy < 0.5))].plot(ax=ax, color="#F7F7F7", edgecolor="#9A9A9A", lw=0.4)  # drop W Sulawesi
    img, ext = burned_raster()
    from matplotlib.colors import ListedColormap
    ax.imshow(np.ma.masked_equal((img > 0).astype(int), 0), extent=ext, cmap=ListedColormap([BURN]),
              interpolation="nearest", zorder=2)
    for cls, col in (("deficit", DEFICIT), ("no difference", NODIFF), ("excess", EXCESS)):
        g[g.class_fdr == cls].plot(ax=ax, color=col, edgecolor="none", zorder=3)
    four = g[g.label.fillna("").str.contains("|".join(FOUR.values()), case=False)]
    c = four.union_all().centroid
    ax.add_patch(plt.Circle((c.x, c.y), 0.42, fill=False, ec=INK, lw=1.0, zorder=4))
    ax.annotate("Ketapang four", (c.x - 0.42, c.y), xytext=(108.4, c.y - 0.9), fontsize=7,
                arrowprops=dict(arrowstyle="-", lw=0.6, color=INK))
    ax.set_xlim(108.3, 119.3), ax.set_ylim(-4.6, 7.5), ax.set_aspect("equal"), ax.axis("off")
    # scale bar (100 km at the equator) and north arrow
    x0, y0, dx = 116.6, -4.1, 100 / 111.32
    ax.plot([x0, x0 + dx], [y0, y0], color=INK, lw=2)
    ax.text(x0 + dx / 2, y0 + 0.2, "100 km", ha="center", fontsize=7)
    ax.annotate("N", (118.6, 6.8), xytext=(118.6, 5.9), ha="center", fontsize=8, fontweight="bold",
                arrowprops=dict(arrowstyle="-|>", lw=0.8, color=INK))
    n = g.class_fdr.value_counts()
    handles = [plt.Rectangle((0, 0), 1, 1, color=c_) for c_ in (EXCESS, NODIFF, DEFICIT)] + \
              [plt.Rectangle((0, 0), 1, 1, color=BURN)]
    ax.legend(handles, [f"excess (n={n.get('excess', 0)})", f"no difference ({n.get('no difference', 0)})",
                        f"deficit ({n.get('deficit', 0)})", "burned 2026 (1 km)"],
              loc="upper left", bbox_to_anchor=(0.0, 0.98), frameon=False, title="Concession vs matched land\n(Benjamini–Hochberg q ≤ 0.05)",
              title_fontsize=7)
    panel(ax, "a")

    # (b) ladder
    axb = fig.add_axes([0.63, 0.58, 0.36, 0.38])
    m = [r for r in run("matched.json") if r["test"] == "burn" and r["treated"] in KIND_COL]
    steps = ["raw", "+ peat", "+ peat depth", "+ land cover", "+ burn history", "+ distance to water",
             "+ distance to settlement"]
    for kind, col in KIND_COL.items():
        rr = [next(r for r in m if r["treated"] == kind and r["matched_on"] == s) for s in steps]
        x = np.arange(len(rr))
        axb.fill_between(x, [r["ratio_ci95"][0] for r in rr], [r["ratio_ci95"][1] for r in rr], color=col, alpha=0.18, lw=0)
        axb.plot(x, [r["ratio"] for r in rr], "o-", color=col, ms=3, label=kind)
    axb.axhline(1, color=CTL, ls="--", lw=0.8)
    axb.set_yscale("log"), axb.set_yticks([0.8, 0.9, 1.0, 1.2, 1.4]), axb.set_yticklabels(["0.8", "0.9", "1.0", "1.2", "1.4"])
    axb.minorticks_off()
    axb.set_xticks(range(len(steps)), ["raw", "peat", "depth", "land\ncover", "burn\nhistory", "water", "settle-\nment"])
    axb.set_ylabel("Burned-share ratio,\nconcession / matched")
    axb.set_xlabel("Covariate added (cumulative)")
    axb.legend(frameon=False, loc="upper right")
    panel(axb, "b")

    # (c) concentration
    axc = fig.add_axes([0.63, 0.08, 0.36, 0.36])
    for kind, col in KIND_COL.items():
        u = g[g.kind == kind].assign(ex=lambda d: d.class_fdr.eq("excess")).sort_values(["ex", "ratio"], ascending=False)
        xs = np.arange(1, len(u) + 1) / len(u)
        ys = u.burned_km2.cumsum().to_numpy() / u.burned_km2.sum()
        axc.plot(np.r_[0, xs], np.r_[0, ys], color=col, label=kind)
        k = int((u.class_fdr == "excess").sum())
        share = u[u.class_fdr == "excess"].burned_km2.sum() / u.burned_km2.sum()
        axc.plot([k / len(u)], [share], "o", color=col, ms=4, zorder=5)
        axc.annotate(f"{kind}: {100 * k / len(u):.1f}% of units (excess)\nhold {100 * share:.0f}% of burned area",
                     (k / len(u), share), xytext=(0.56, 0.12 if kind == "oil palm" else 0.30), fontsize=6.5, color=col,
                     arrowprops=dict(arrowstyle="-", lw=0.5, color=col))
    axc.plot([0, 1], [0, 1], color=CTL, ls=":", lw=0.8)
    axc.set_xlim(0, 1), axc.set_ylim(0, 1.02)
    axc.set_xlabel("Cumulative share of concessions\n(excess units first, then by matched ratio)")
    axc.set_ylabel("Cumulative share of\nconcession burned area")
    panel(axc, "c")
    save(fig, "Fig01_concentration")


if __name__ == "__main__":
    main()
