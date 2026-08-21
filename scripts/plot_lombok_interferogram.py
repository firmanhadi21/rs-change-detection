"""Map the GMTSAR Lombok interferogram, 12 May -> 4 August 2018.

WHICH EARTHQUAKE THIS PAIR ACTUALLY SPANS, because it is easy to get wrong.
The 2018 Lombok sequence ran

    29 Jul 2018   M6.4   foreshock
     5 Aug 2018   M6.9   mainshock
    19 Aug 2018   M6.9

and the second acquisition here is 4 August -- the day BEFORE the mainshock.
So this interferogram contains the M6.4 of 29 July and nothing later. Labelling
it "the Lombok earthquake" would attribute the wrong event.

ONE FRINGE IS 12.12 cm, not 2.77. ALOS-2 is L-band at 0.242452 m. Carrying the
Sentinel-1 figure over would understate every displacement by 4.4x.

Three panels: filtered wrapped phase (masked), the same unmasked so the mask's
effect is visible rather than assumed, and coherence underneath -- because a
fringe pattern means nothing where the phase is noise.

    conda run -n base python scripts/plot_lombok_interferogram.py
"""

import argparse
import os
import sys

import numpy as np

try:
    import xarray as xr
except ImportError:                                   # pragma: no cover
    sys.exit("needs xarray + matplotlib: run under `conda run -n base`")

D = os.path.expanduser(
    "~/Teaching/UNDIP/InSAR/EQ/Pair1/intf/2018132_2018216")
OUT = os.path.expanduser(
    "~/GitHub/rs-change-detection/output/lombok_interferogram.png")
WAVELENGTH_M = 0.242452
FRINGE_CM = WAVELENGTH_M / 2 * 100

# USGS locations for the sequence.
EVENTS = [
    ("M6.4  29 Jul", 116.426, -8.239, "#ffdd00"),
    ("M6.9   5 Aug", 116.439, -8.287, "#ff5500"),
]


def load(name):
    p = os.path.join(D, name)
    return xr.open_dataarray(p) if os.path.exists(p) else None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()

    ph_m = load("phasefilt_mask_ll.grd")
    ph = load("phasefilt_ll.grd")
    corr = load("corr_ll.grd")
    if ph_m is None or corr is None:
        sys.exit("missing geocoded grids")

    ydim, xdim = ph_m.dims
    lat, lon = ph_m[ydim].values, ph_m[xdim].values
    ext = [lon.min(), lon.max(), lat.min(), lat.max()]
    # GMTSAR grids run south-to-north; imshow with origin='lower' then puts
    # north at the top without flipping the data.
    print(f"grid {ph_m.shape}, extent {ext}")

    c = corr.values
    good = np.isfinite(c)
    print(f"coherence over finite pixels: median {np.nanmedian(c):.3f}, "
          f"{100*np.nanmean(c[good] >= 0.3):.1f}% above 0.3")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(1, 3, figsize=(16.5, 6.4))

    for axi, arr, ttl, cmap, kw in (
        (ax[0], ph_m.values,
         "Filtered wrapped phase, masked\none colour cycle = "
         f"{FRINGE_CM:.1f} cm line-of-sight",
         "twilight_shifted", dict(vmin=-np.pi, vmax=np.pi)),
        (ax[1], ph.values if ph is not None else ph_m.values,
         "Same, unmasked\n(so the mask's effect is visible)",
         "twilight_shifted", dict(vmin=-np.pi, vmax=np.pi)),
        (ax[2], c, "Coherence\na fringe means nothing where this is low",
         "magma", dict(vmin=0, vmax=0.8)),
    ):
        im = axi.imshow(arr, extent=ext, origin="lower",
                        cmap=cmap, interpolation="nearest", **kw)
        axi.set_title(ttl, fontsize=10.5, loc="left")
        axi.set_xlabel("lon")
        for label, elon, elat, col in EVENTS:
            axi.plot(elon, elat, "*", ms=16, mfc=col, mec="black", mew=.9,
                     zorder=5)
        fig.colorbar(im, ax=axi, shrink=.82, pad=.02)
    ax[0].set_ylabel("lat")

    ax[0].annotate("M6.4 29 Jul\n(in this pair)", xy=(116.426, -8.239),
                   xytext=(116.15, -8.05), fontsize=9, color="#8a6d00",
                   fontweight="bold",
                   arrowprops=dict(arrowstyle="->", color="#8a6d00"))
    ax[0].annotate("M6.9 5 Aug\n(NOT in this pair)", xy=(116.439, -8.287),
                   xytext=(116.15, -8.62), fontsize=9, color="#a03000",
                   fontweight="bold",
                   arrowprops=dict(arrowstyle="->", color="#a03000"))

    fig.suptitle("Lombok, ALOS-2 12 May → 4 Aug 2018 — spans the M6.4 "
                 "foreshock only, not the 5 Aug mainshock",
                 fontsize=13, y=.99)
    fig.tight_layout(rect=[0, 0, 1, .95])
    fig.savefig(a.out, dpi=130)
    print(f"\nwrote {a.out}")
    print(f"\nReading it: the rings are centred on Rinjani's summit, roughly")
    print(f"116.45, -8.42 -- NOT on either epicentre star 15-20 km north.")
    print(f"That is the tell. Concentric rings around a 3726 m volcano in a")
    print(f"12-week pair are stratified tropospheric delay: 81% of the phase")
    print(f"variance here is a function of elevation. Each cycle is still")
    print(f"{FRINGE_CM:.1f} cm of line-of-sight path change, but the path")
    print(f"changed because the atmosphere did, not because the ground did.")
    print(f"See scripts/lombok_topo_vs_deformation.py for the test.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
