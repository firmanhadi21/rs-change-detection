"""Map the co-seismic interferogram: wrapped phase, coherence, and change.

Wrapped phase is what exists before unwrapping, and it is the right thing to
look at first. Each full colour cycle is one fringe, and one fringe is half a
wavelength of line-of-sight motion -- 2.77 cm for Sentinel-1 C-band. So the
number of fringes IS the displacement, countable by eye, without unwrapping
anything.

What to look for. Real ground motion makes fringes that are CONTINUOUS,
CONCENTRIC and centred somewhere physical. Atmosphere makes smooth blobs that
follow terrain or wander. Noise makes salt-and-pepper with no structure at all.
Distinguishing those three by eye is the whole reason to plot this before
computing anything.

    python3 scripts/plot_interferogram.py
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
WAVELENGTH_CM = 5.5465          # Sentinel-1 C-band
FRINGE_CM = WAVELENGTH_CM / 2   # one 2-pi cycle in line of sight


def read_img(data_dir, prefix):
    hdr = sorted(glob.glob(f"{data_dir}/{prefix}*.hdr"))[0]
    meta = {}
    for line in open(hdr, errors="ignore"):
        if "=" in line:
            k, _, v = line.partition("=")
            meta[k.strip().lower()] = v.strip()
    w, h = int(meta["samples"]), int(meta["lines"])
    # SNAP writes big-endian; reading it little-endian gives 1e38 nonsense.
    endian = ">" if meta.get("byte order", "0").strip() == "1" else "<"
    kind = {"4": "f4", "5": "f8", "12": "u2", "2": "i2"}.get(
        meta.get("data type", "4").strip(), "f4")
    a = np.fromfile(hdr[:-4] + ".img", dtype=endian + kind)
    return a.reshape(h, w).astype("float32"), meta


def extent(meta, shape):
    m = meta["map info"].strip("{}").split(",")
    rx, ry = float(m[1]), float(m[2])
    ulx, uly = float(m[3]), float(m[4])
    xr, yr = float(m[5]), float(m[6])
    west = ulx - (rx - 1) * xr
    north = uly + (ry - 1) * yr
    return [west, west + shape[1] * xr, north - shape[0] * yr, north]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pair", default="prepost", choices=("prepost", "prepre"))
    ap.add_argument("--suffix", default="coh",
                    help="'coh' for the IW2-only run, 'full' for all three "
                         "subswaths merged")
    ap.add_argument("--min-coh", type=float, default=0.25,
                    help="hide phase below this; below it the phase is noise")
    a = ap.parse_args()

    d = f"{SNAP}/{a.pair}_{a.suffix}.data"
    i, meta = read_img(d, "i_ifg")
    q, _ = read_img(d, "q_ifg")
    coh, _ = read_img(d, "coh_")

    phase = np.arctan2(q, i)
    valid = (coh > 0) & np.isfinite(coh) & ((i != 0) | (q != 0))
    print(f"{a.pair}: {i.shape}, {valid.sum():,} valid px "
          f"({100*valid.mean():.1f}%)")
    print(f"coherence over valid: median {np.median(coh[valid]):.3f}")

    # Phase is meaningless where coherence is low; showing it invites reading
    # noise as fringes.
    shown = valid & (coh >= a.min_coh)
    print(f"phase shown where coh >= {a.min_coh}: {shown.sum():,} px "
          f"({100*shown.sum()/max(valid.sum(),1):.1f}% of valid)")

    ph = np.where(shown, phase, np.nan)
    ext = extent(meta, i.shape)
    epi = (121.3517, -8.3101)

    # The geocoded bounding box includes a lot of empty sea. Crop the axes to
    # rows/columns that actually hold data, so the island fills the figure --
    # with a margin wide enough to keep the epicentre visible.
    rows = np.flatnonzero(valid.any(axis=1))
    cols = np.flatnonzero(valid.any(axis=0))
    yr = (ext[3] - ext[2]) / i.shape[0]
    xr = (ext[1] - ext[0]) / i.shape[1]
    pad = 0.06
    view = [min(ext[0] + (cols[0] - 1) * xr, epi[0]) - pad,
            max(ext[0] + (cols[-1] + 1) * xr, epi[0]) + pad,
            min(ext[3] - (rows[-1] + 1) * yr, epi[1]) - pad,
            max(ext[3] - (rows[0] - 1) * yr, epi[1]) + pad]

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # Three panels side by side shrink each to a third of the width. For a
    # scene four times wider than tall that leaves the phase too small to tell
    # fringes from noise -- which is the one question the figure exists to
    # answer. Stack instead whenever the scene is wide.
    # Key this on the CROPPED VIEW, not the array shape. The full array is only
    # 1.6x wider than tall because the bounding box carries empty sea; the land
    # actually on show is nearly 3x wider than tall.
    span = (view[3] - view[2]) / (view[1] - view[0])
    if span < 0.5:
        fig, axes = plt.subplots(3, 1, figsize=(15, 3 * (2.2 + 13 * span)),
                                 constrained_layout=True)
    else:
        fig, axes = plt.subplots(1, 3, figsize=(17, 6.4),
                                 constrained_layout=True)

    # Cyclic colormap: phase wraps, so the colours must wrap too. A linear ramp
    # would draw a false discontinuity at every -pi/+pi crossing.
    im0 = axes[0].imshow(ph, cmap="twilight_shifted", extent=ext,
                         vmin=-np.pi, vmax=np.pi, origin="upper")
    axes[0].set_title(f"Wrapped phase — {a.pair}\n"
                      f"1 fringe = {FRINGE_CM:.2f} cm line-of-sight",
                      fontsize=11)
    cb = fig.colorbar(im0, ax=axes[0], shrink=.8)
    cb.set_ticks([-np.pi, 0, np.pi])
    cb.set_ticklabels(["−π", "0", "+π"])

    im1 = axes[1].imshow(np.where(valid, coh, np.nan), cmap="magma",
                         extent=ext, vmin=0, vmax=0.8, origin="upper")
    axes[1].set_title(f"Coherence — {a.pair}", fontsize=11)
    fig.colorbar(im1, ax=axes[1], shrink=.8)

    base = f"{SNAP}/prepre_{a.suffix}.data"
    if a.pair == "prepost" and os.path.isdir(base):
        pre, m_pre = read_img(base, "coh_")
        h = min(pre.shape[0], coh.shape[0])
        w = min(pre.shape[1], coh.shape[1])
        delta = np.where((pre[:h, :w] >= 0.3) & (coh[:h, :w] > 0),
                         coh[:h, :w] - pre[:h, :w], np.nan)
        im2 = axes[2].imshow(delta, cmap="RdBu_r", extent=ext,
                             vmin=-0.4, vmax=0.4, origin="upper")
        axes[2].set_title("Coherence change\n(co-event − baseline)", fontsize=11)
        fig.colorbar(im2, ax=axes[2], shrink=.8)
    else:
        axes[2].axis("off")

    for ax in axes:
        if ax.has_data():
            ax.plot(*epi, marker="*", color="#00ff88", markersize=18,
                    markeredgecolor="black", markeredgewidth=.8)
            ax.set_xlim(view[0], view[1]); ax.set_ylim(view[2], view[3])
            ax.set_xlabel("lon"); ax.set_ylabel("lat")

    scope = "IW1+IW2+IW3" if a.suffix == "full" else "IW2"
    fig.suptitle(f"Flores M7.7, 14 Aug 2026 — ascending path 112, {scope} "
                 "(star = epicentre)", fontsize=13)
    out = f"{SNAP}/interferogram_{a.pair}_{a.suffix}.png"
    fig.savefig(out, dpi=135)
    print(f"\nwrote {out}")

    print("\n=== how to read the left panel ===")
    print("  concentric, continuous fringes  -> ground motion; count them,")
    print(f"     each is {FRINGE_CM:.2f} cm along the line of sight")
    print("  smooth blobs following terrain  -> atmosphere, not the earthquake")
    print("  salt-and-pepper, no structure   -> no resolvable signal")
    print("\nLOS displacement in metres needs UNWRAPPING (SNAPHU); this is the")
    print("wrapped phase, which is what exists before that step.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
