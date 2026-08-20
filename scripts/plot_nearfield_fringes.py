"""Are the predicted 3.2 km fringes present over the north coast, or not?

The observability test settled that the USGS finite-fault deformation would
produce fringes about 3.2 km apart at 40 m pixels -- 80 pixels per fringe,
trivially resolvable. So unwrapping cannot have aliased them away, and the
disagreement between model and interferogram comes down to a question that can
be answered by looking:

  FRINGES PRESENT at that spacing   the signal is in the data and unwrapping
                                    lost it. Recoverable: re-unwrap with a
                                    better reference and a coherence mask.

  FRINGES ABSENT                    the model overpredicts onshore. Teleseismic
                                    inversions constrain shallow offshore slip
                                    poorly, and this one places peak slip 4.4 km
                                    deep just offshore -- precisely where that
                                    weakness bites.

Three panels, all over the same near-field ground:

  observed wrapped phase, filtered only enough to suppress speckle
  the model's LOS field WRAPPED to the same 2.77 cm cycle, so the two are
      directly comparable as images rather than through statistics
  coherence, because a fringe cannot be believed where the phase is noise

The model panel is the control: it shows exactly what the earthquake should
have drawn on this map.

    conda run -n base python scripts/plot_nearfield_fringes.py
"""

import argparse
import glob
import os
import sys

import numpy as np

try:
    import rasterio
    from rasterio.warp import transform as warp_transform
except ImportError:                                   # pragma: no cover
    sys.exit("needs rasterio + okada-wrapper under `conda run -n base`")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from usgs_finite_fault_los import (displacement, patches,      # noqa: E402
                                   los_away, EPI_LON, EPI_LAT, KM_LAT)

FRINGE_CM = 5.5465 / 2
ROOT = os.path.expanduser("~/GitHub/rs-change-detection/output/coseismic")
FFM = ("/private/tmp/claude-501/-Users-firmanhadi-GitHub-rs-change-detection/"
       "002f025e-d8ee-4126-aa65-97d981ababcf/scratchpad/FFM.geojson")

# North-coast box: the ground nearest the rupture that this frame images.
BOX = dict(lon0=120.75, lon1=121.55, lat0=-8.70, lat1=-8.36)


def boxfilt(a, w):
    """Separable box filter via cumulative sums; keeps complex phase valid."""
    k = np.ones(w) / w
    out = np.apply_along_axis(lambda m: np.convolve(m, k, mode="same"), 1, a)
    return np.apply_along_axis(lambda m: np.convolve(m, k, mode="same"), 0, out)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--product", default="*prepost-d2*")
    ap.add_argument("--min-coh", type=float, default=0.25)
    ap.add_argument("--filter", type=int, default=9,
                    help="complex box filter, pixels (40 m each)")
    ap.add_argument("--model-stride", type=int, default=6)
    ap.add_argument("--out", default=os.path.join(
        ROOT, "nearfield_fringes.png"))
    a = ap.parse_args()

    wrp = sorted(glob.glob(f"{ROOT}/{a.product}/*_wrapped_phase.tif"))[0]
    corr_p = wrp.replace("_wrapped_phase.tif", "_corr.tif")
    with rasterio.open(wrp) as src:
        tr, crs = src.transform, src.crs
        res_m = abs(tr.a)
        H, W = src.height, src.width
        rows, cols = np.mgrid[0:H, 0:W]
        xs = tr.c + (cols + .5) * tr.a
        ys = tr.f + (rows + .5) * tr.e
        lon, lat = warp_transform(crs, "EPSG:4326", xs.ravel(), ys.ravel())
        lon = np.array(lon).reshape(H, W)
        lat = np.array(lat).reshape(H, W)
        sel = ((lon >= BOX["lon0"]) & (lon <= BOX["lon1"])
               & (lat >= BOX["lat0"]) & (lat <= BOX["lat1"]))
        r0, r1 = np.flatnonzero(sel.any(axis=1))[[0, -1]]
        c0, c1 = np.flatnonzero(sel.any(axis=0))[[0, -1]]
        win = rasterio.windows.Window(c0, r0, c1 - c0 + 1, r1 - r0 + 1)
        phase = src.read(1, window=win).astype("float64")
    with rasterio.open(corr_p) as src:
        coh = src.read(1, window=win)

    lon = lon[r0:r1 + 1, c0:c1 + 1]
    lat = lat[r0:r1 + 1, c0:c1 + 1]
    ext = [lon.min(), lon.max(), lat.min(), lat.max()]
    print(f"north-coast window {phase.shape} at {res_m:.0f} m")
    print(f"  lon {ext[0]:.3f}..{ext[1]:.3f}  lat {ext[2]:.3f}..{ext[3]:.3f}")

    valid = np.isfinite(phase) & (phase != 0) & (coh >= a.min_coh)
    print(f"  coherent pixels: {int(valid.sum()):,} "
          f"({100*valid.mean():.1f}%)")

    # Filter the COMPLEX phase, never the angle: averaging angles puts the
    # mean of +3.0 and -3.0 rad at 0 when they are 0.28 rad apart.
    z = np.where(valid, np.exp(1j * phase), 0)
    zf = boxfilt(z.real, a.filter) + 1j * boxfilt(z.imag, a.filter)
    obs = np.where(valid, np.angle(zf), np.nan)

    # Model on the same ground, wrapped to the same cycle.
    subs = patches(FFM)
    sl = (slice(None, None, a.model_stride), slice(None, None, a.model_stride))
    E, N, U = displacement(lon[sl], lat[sl], subs)
    mod_cm = los_away(E, N, U, 39.0, -13.0) * 100.0
    mod_wrapped = np.angle(np.exp(1j * (mod_cm / FRINGE_CM * 2 * np.pi)))
    span = float(np.nanmax(mod_cm) - np.nanmin(mod_cm))
    print(f"  model LOS across this window: {span:.1f} cm "
          f"= {span/FRINGE_CM:.1f} fringes")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(3, 1, figsize=(12, 13.5))
    ax[0].imshow(obs, cmap="twilight_shifted", extent=ext, origin="upper",
                 vmin=-np.pi, vmax=np.pi, interpolation="nearest")
    ax[0].set_title(f"Observed wrapped phase, {a.filter}x{a.filter} filtered "
                    f"— 40 m pixels\nif the earthquake is here, fringes should "
                    f"be ~3.2 km apart", fontsize=10.5, loc="left")

    ax[1].imshow(mod_wrapped, cmap="twilight_shifted", extent=ext,
                 origin="upper", vmin=-np.pi, vmax=np.pi,
                 interpolation="nearest")
    ax[1].set_title(f"USGS finite fault, wrapped to the same 2.77 cm cycle "
                    f"— the control\n{span:.0f} cm across this window "
                    f"= {span/FRINGE_CM:.0f} fringes", fontsize=10.5,
                    loc="left")

    im = ax[2].imshow(np.where(coh > 0, coh, np.nan), cmap="magma",
                      extent=ext, origin="upper", vmin=0, vmax=0.8,
                      interpolation="nearest")
    ax[2].set_title("Coherence — a fringe cannot be believed where the phase "
                    "is noise", fontsize=10.5, loc="left")
    fig.colorbar(im, ax=ax[2], shrink=.85, pad=.02)

    for axi in ax:
        axi.plot(EPI_LON, EPI_LAT, "*", color="#00ff88", ms=18, mec="k",
                 mew=.8)
        axi.set_ylabel("lat")
        axi.set_xlim(ext[0], ext[1])
        axi.set_ylim(ext[2], ext[3])
    ax[2].set_xlabel("lon")
    fig.suptitle("Flores M7.7 — north coast: are the predicted fringes there?",
                 fontsize=13)
    fig.tight_layout(rect=[0, 0, 1, .97])
    fig.savefig(a.out, dpi=135)
    print(f"\nwrote {a.out}")
    print("\n  Compare panels 1 and 2 directly. Matching fringe pattern means")
    print("  the signal is present and unwrapping lost it. No corresponding")
    print("  pattern means the model overpredicts this ground.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
