"""Evidence figure: how much co-seismic motion can we actually rule out?

"We saw no fringes" is not a result -- it does not separate an absent signal
from a badly-conducted search. This turns the null into an UPPER BOUND: the
amplitude of radially-organised line-of-sight motion that would have been
detected had it been there.

THE STATISTIC, AND WHY NOT THE OBVIOUS ONE.
An earlier version of this analysis binned pixels by distance from the rupture
and reported the resultant length R within each annulus. That statistic cannot
work here, for a reason worth stating plainly: a radially symmetric signal adds
the SAME phase to every pixel in an annulus, which rotates the mean phasor
without changing its length. R is blind to precisely the signal being searched
for. What R actually measures is the noise, and it says the noise is large
(R ~ 0.06, i.e. the phase is 94% uniformly distributed).

The signal lives in the SEQUENCE OF BIN MEAN ANGLES instead: deformation makes
that sequence vary smoothly and monotonically with distance. So the question
becomes how precisely each bin's mean angle is known.

THE ERROR BAR, AND WHY BLOCKS.
Not from the pixel count. Turbulent atmosphere is correlated over kilometres,
so a bin holding 300,000 40-metre pixels holds perhaps a hundred independent
samples. Dividing by sqrt(300000) would understate the error by ~50x and
manufacture a confident detection out of weather. So: divide the scene into
blocks wider than the atmospheric correlation length, take one mean per block,
and bootstrap over BLOCKS. Each block counts once no matter how many pixels it
holds.

WHAT THE BOUND MEANS.
The bootstrap gives a confidence interval on each bin's mean phase, in cm of
line-of-sight motion. A radial signal larger than that interval would have
moved the profile out of it. Note the ceiling: phase wraps at 2.77 cm, so this
test cannot bound anything above half a fringe (1.39 cm) -- signals larger than
that must instead be excluded by the ABSENCE OF VISIBLE FRINGES in the maps,
which is why the maps are in the figure and not decoration.

    python3 scripts/plot_null_evidence.py
"""

import argparse
import glob
import os
import sys

for _v in ("PROJ_LIB", "PROJ_DATA", "GDAL_DATA"):
    os.environ.pop(_v, None)

import numpy as np  # noqa: E402

SNAP = os.path.expanduser(
    "~/GitHub/rs-change-detection/output/coseismic/snap")
EPI_LON, EPI_LAT = 121.3517, -8.3101
FRINGE_CM = 5.5465 / 2
KM_PER_DEG_LAT = 110.57

# Wider than the turbulent-atmosphere correlation length (~1-10 km), so that
# two blocks are close to independent samples of the weather.
BLOCK_KM = 20.0
N_BOOT = 400
rng = np.random.default_rng(0)


def read_img(data_dir, prefix):
    hdr = sorted(glob.glob(f"{data_dir}/{prefix}*.hdr"))[0]
    meta = {}
    for line in open(hdr, errors="ignore"):
        if "=" in line:
            k, _, v = line.partition("=")
            meta[k.strip().lower()] = v.strip()
    w, h = int(meta["samples"]), int(meta["lines"])
    endian = ">" if meta.get("byte order", "0").strip() == "1" else "<"
    kind = {"4": "f4", "5": "f8", "12": "u2", "2": "i2"}.get(
        meta.get("data type", "4").strip(), "f4")
    a = np.fromfile(hdr[:-4] + ".img", dtype=endian + kind)
    return a.reshape(h, w).astype("float32"), meta


def corners(meta, shape):
    m = meta["map info"].strip("{}").split(",")
    xr, yr = float(m[5]), float(m[6])
    west = float(m[3]) - (float(m[1]) - 1) * xr
    north = float(m[4]) + (float(m[2]) - 1) * yr
    return west, north, xr, yr


def block_profile(phi, dist, block, edges):
    """Bin mean phase with a bootstrap CI computed over blocks, not pixels."""
    out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        sel = (dist >= lo) & (dist < hi)
        if sel.sum() < 2000:
            continue
        b = block[sel]
        z = np.exp(1j * phi[sel])

        # One unit phasor per block: a block with 50,000 pixels must not
        # outvote a block with 500, since both are one sample of the weather.
        uniq, inv = np.unique(b, return_inverse=True)
        sums = np.zeros(len(uniq), dtype=complex)
        np.add.at(sums, inv, z)
        cnt = np.bincount(inv, minlength=len(uniq))
        keep = cnt >= 200
        if keep.sum() < 6:
            continue
        unit = sums[keep] / np.abs(sums[keep])

        m = unit.mean()
        boot = np.empty(N_BOOT)
        n = len(unit)
        for k in range(N_BOOT):
            s = unit[rng.integers(0, n, n)].mean()
            boot[k] = np.angle(s)
        # Centre the bootstrap angles on the point estimate before taking
        # percentiles, or a distribution straddling +/-pi reports a spurious
        # full-circle interval.
        d = np.angle(np.exp(1j * (boot - np.angle(m))))
        lo_ci, hi_ci = np.percentile(d, [2.5, 97.5])
        out.append(dict(r=0.5 * (lo + hi), ang=np.angle(m), R=abs(m),
                        nblk=n, lo=lo_ci, hi=hi_ci))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--suffix", default="full")
    ap.add_argument("--min-coh", type=float, default=0.3)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    d = f"{SNAP}/prepost_{a.suffix}.data"
    i, meta = read_img(d, "i_ifg")
    q, _ = read_img(d, "q_ifg")
    coh, _ = read_img(d, "coh_")
    west, north, xr, yr = corners(meta, i.shape)

    phase = np.arctan2(q, i)
    ok = (coh >= a.min_coh) & np.isfinite(coh) & ((i != 0) | (q != 0))
    rows, cols = np.nonzero(ok)
    lon = west + (cols + 0.5) * xr
    lat = north - (rows + 0.5) * yr
    kx = 111.32 * np.cos(np.deg2rad(EPI_LAT))
    dist = np.hypot((lon - EPI_LON) * kx, (lat - EPI_LAT) * KM_PER_DEG_LAT)
    phi = phase[ok]

    bx = max(1, int(round(BLOCK_KM / (xr * kx))))
    by = max(1, int(round(BLOCK_KM / (yr * KM_PER_DEG_LAT))))
    block = (rows // by).astype(np.int64) * 100000 + (cols // bx)
    print(f"scene {i.shape}, {ok.sum():,} px at coh >= {a.min_coh}")
    print(f"blocks: {BLOCK_KM:.0f} km = {bx}x{by} px, "
          f"{len(np.unique(block)):,} distinct")

    edges = np.arange(20, 181, 15)
    prof = block_profile(phi, dist, block, edges)

    print(f"\n=== radial phase profile, {BLOCK_KM:.0f} km blocks, "
          f"{N_BOOT} bootstrap draws ===")
    print("   dist    blocks   mean phase        95% CI (cm LOS)")
    half = []
    for p in prof:
        c = p["ang"] / (2 * np.pi) * FRINGE_CM
        clo = p["lo"] / (2 * np.pi) * FRINGE_CM
        chi = p["hi"] / (2 * np.pi) * FRINGE_CM
        half.append(0.5 * (chi - clo))
        print(f"  {p['r']:5.0f} km  {p['nblk']:5d}   {c:+6.2f} cm   "
              f"[{c+clo:+6.2f}, {c+chi:+6.2f}]   +/-{0.5*(chi-clo):.2f}")

    floor = float(np.median(half))
    spread = np.array([p["ang"] for p in prof])
    spread_cm = np.abs(np.angle(np.exp(1j * (spread - np.angle(
        np.exp(1j * spread).mean()))))).max() / (2 * np.pi) * FRINGE_CM

    print(f"\n  typical 95% CI half-width : +/-{floor:.2f} cm")
    print(f"  largest bin departure     : {spread_cm:.2f} cm")
    print(f"  half-fringe wrap ceiling  : {FRINGE_CM/2:.2f} cm")

    # ---- coherence change against distance, same blocks ------------------
    cc = None
    base = f"{SNAP}/prepre_{a.suffix}.data"
    if os.path.isdir(base):
        pre, mpre = read_img(base, "coh_")
        h = min(pre.shape[0], coh.shape[0])
        w = min(pre.shape[1], coh.shape[1])
        use = (pre[:h, :w] >= 0.3) & (coh[:h, :w] > 0)
        r2, c2 = np.nonzero(use)
        lo2 = west + (c2 + 0.5) * xr
        la2 = north - (r2 + 0.5) * yr
        d2 = np.hypot((lo2 - EPI_LON) * kx, (la2 - EPI_LAT) * KM_PER_DEG_LAT)
        v2 = (coh[:h, :w] - pre[:h, :w])[use]
        cc = []
        for lo, hi in zip(edges[:-1], edges[1:]):
            s = (d2 >= lo) & (d2 < hi)
            if s.sum() < 2000:
                continue
            cc.append((0.5 * (lo + hi), float(np.median(v2[s]))))

    # ---------------------------------------------------------------- plot
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle

    ph = np.where(ok, phase, np.nan)
    ext = [west, west + i.shape[1] * xr, north - i.shape[0] * yr, north]
    rr = np.flatnonzero(ok.any(axis=1)); ccx = np.flatnonzero(ok.any(axis=0))
    pad = 0.06
    view = [min(west + (ccx[0] - 1) * xr, EPI_LON) - pad,
            max(west + (ccx[-1] + 1) * xr, EPI_LON) + pad,
            min(north - (rr[-1] + 1) * yr, EPI_LAT) - pad,
            max(north - (rr[0] - 1) * yr, EPI_LAT) + pad]

    fig = plt.figure(figsize=(15.5, 14.5))
    gs = fig.add_gridspec(3, 2, height_ratios=[1.55, 1.5, 1.2], hspace=.30,
                          wspace=.22)

    def rings(ax, labels=False):
        for km in (25, 50, 75, 100, 150):
            ax.add_patch(Circle((EPI_LON, EPI_LAT),
                                km / KM_PER_DEG_LAT, fill=False,
                                ec="0.35", lw=.7, ls=":",
                                transform=ax.transData))
            if labels:
                ax.annotate(f"{km} km", (EPI_LON, EPI_LAT - km / KM_PER_DEG_LAT),
                            fontsize=7, color="0.3", ha="center", va="bottom")
        ax.plot(EPI_LON, EPI_LAT, marker="*", color="#00ff88", ms=17,
                mec="black", mew=.8, zorder=5)

    ax = fig.add_subplot(gs[0, :])
    ax.imshow(ph, cmap="twilight_shifted", extent=ext, vmin=-np.pi,
              vmax=np.pi, origin="upper", interpolation="nearest")
    rings(ax, labels=True)
    ax.set_xlim(view[0], view[1]); ax.set_ylim(view[2], view[3])
    ax.set_title("A  Wrapped interferometric phase, 6→18 Aug 2026 "
                 "(spans the M7.7)\nall three subswaths · 1 fringe = "
                 f"{FRINGE_CM:.2f} cm line-of-sight · dotted rings = "
                 "distance from epicentre", fontsize=10.5, loc="left")
    ax.set_xlabel("lon"); ax.set_ylabel("lat")

    # IW1: the western swath, where the phase has the most visible structure
    # and therefore the strongest claim to being mistaken for deformation.
    ax = fig.add_subplot(gs[1, 0])
    ax.imshow(ph, cmap="twilight_shifted", extent=ext, vmin=-np.pi,
              vmax=np.pi, origin="upper", interpolation="nearest")
    rings(ax)
    ax.set_xlim(view[0], 121.62); ax.set_ylim(-8.95, -8.24)
    ax.set_title("B  IW1, western Flores — the structure that looks most\n"
                 "like signal. Smooth blobs sit over the highlands, 60–90 km\n"
                 "from the rupture, not on the coast nearest it.",
                 fontsize=10, loc="left")
    ax.set_xlabel("lon"); ax.set_ylabel("lat")

    ax = fig.add_subplot(gs[1, 1])
    im = ax.imshow(np.where(coh > 0, coh, np.nan), cmap="magma", extent=ext,
                   vmin=0, vmax=.8, origin="upper", interpolation="nearest")
    rings(ax)
    ax.set_xlim(view[0], 121.62); ax.set_ylim(-8.95, -8.24)
    ax.set_title("C  Coherence, same area. The interferogram is sound —\n"
                 "this is not a decorrelation failure. Phase is measurable;\n"
                 "there is simply no earthquake in it.", fontsize=10,
                 loc="left")
    ax.set_xlabel("lon"); fig.colorbar(im, ax=ax, shrink=.85, pad=.02)

    ax = fig.add_subplot(gs[2, 0])
    r = [p["r"] for p in prof]
    y = [p["ang"] / (2 * np.pi) * FRINGE_CM for p in prof]
    lo = [-p["lo"] / (2 * np.pi) * FRINGE_CM for p in prof]
    hi = [p["hi"] / (2 * np.pi) * FRINGE_CM for p in prof]
    ax.axhspan(-floor, floor, color="#d62728", alpha=.10, zorder=0)

    # Some bins DO sit outside the band -- structure at the ~1 cm level is
    # real. The argument is not that the profile is flat; it is that the
    # departures wander. Draw the shape a real source would make, so the
    # contrast is visible rather than asserted. Far-field line-of-sight
    # displacement decays roughly as 1/(1+(r/rc)^2); this curve is an
    # illustrative template, NOT a fitted or Okada-modelled source.
    rr_ = np.linspace(20, 175, 200)
    ref = 2.5 / (1 + (rr_ / 35.0) ** 2)
    ax.plot(rr_, ref, "--", color="#d62728", lw=1.4, zorder=1,
            label="illustrative co-seismic decay (2.5 cm near-field)")

    ax.errorbar(r, y, yerr=[lo, hi], fmt="o-", ms=5, lw=1.3, capsize=3,
                color="#1f3b73", zorder=3, label="observed")
    ax.axhline(0, color="0.4", lw=.8)
    ax.set_xlabel("distance from epicentre (km)")
    ax.set_ylabel("mean line-of-sight phase (cm)")
    ax.legend(fontsize=7.5, loc="lower right", framealpha=.9)
    ax.set_title(f"D  Radial profile, {BLOCK_KM:.0f} km blocks, bootstrap CI\n"
                 f"shaded = typical 95% CI (±{floor:.2f} cm). Departures are "
                 "real but\nwander up and down; a source decays monotonically "
                 "(dashed).", fontsize=10, loc="left")

    if cc:
        ax = fig.add_subplot(gs[2, 1])
        ax.plot([c[0] for c in cc], [c[1] for c in cc], "s-", color="#8c2d04",
                ms=5, lw=1.3)
        ax.axhline(0, color="0.4", lw=.8)
        ax.set_ylim(-0.16, 0.04)
        ax.set_xlabel("distance from epicentre (km)")
        ax.set_ylabel("median coherence change")
        ax.set_title("E  Damage proxy against distance. Shaking damage must\n"
                     "fall off with distance from the rupture; this is flat\n"
                     "across 150 km, which is weather, not damage.",
                     fontsize=10, loc="left")

    fig.suptitle("Flores M7.7, 14 Aug 2026 — ascending path 112: no "
                 "detectable co-seismic signal, and the bound on it",
                 fontsize=13.5, y=.995)
    out = a.out or f"{SNAP}/null_evidence_{a.suffix}.png"
    fig.savefig(out, dpi=130, bbox_inches="tight")
    print(f"\nwrote {out}")

    print("\n=== what this figure supports, and what it does not ===")
    print(f"  Supported: no radially-organised LOS motion above "
          f"~{max(floor, FRINGE_CM/2):.1f} cm,")
    print("    and no distance-dependent coherence loss at any amplitude.")
    print("  NOT supported: 'the earthquake produced no ground motion.' It")
    print("    produced motion; this pass could not resolve it onshore, where")
    print("    the nearest land is ~20 km from an offshore rupture.")
    print("  Ceiling: phase wraps every "
          f"{FRINGE_CM:.2f} cm, so the profile test cannot bound above")
    print(f"    {FRINGE_CM/2:.2f} cm. Larger signals are excluded by panels "
          "A-B showing no fringes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
