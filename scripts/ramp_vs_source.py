"""The co-event pair has a phase gradient. Is it the earthquake, or an orbit?

Transects in the near-field box climb ~+0.8 cycles where the earthquake-free
control stays flat. That is a real difference between the two pairs and it
needs an explanation. There are two candidates and they are cleanly separable:

  DEFORMATION   the gradient is largest near the rupture and DECAYS away from
                it. That is what a source does.
  ORBITAL RAMP  the gradient is roughly UNIFORM across the whole scene, because
                a baseline error tilts the phase linearly over 250 km. These
                products use RESTITUTED orbits -- precise orbits (POEORB) are
                published ~20 days after acquisition and did not exist for the
                18 Aug scene when this was processed -- so a residual ramp is
                expected, not surprising.

Ionospheric gradients and long-wavelength stratified atmosphere also produce
near-uniform tilts and are not separable from an orbital ramp here; "ramp"
below means all of them together.

GRADIENT WITHOUT UNWRAPPING. Unwrapping to measure a gradient risks the
unwrapper inventing the very thing being measured. Instead take the complex
product z[x+1] * conj(z[x]): its angle is the phase STEP between neighbours,
correct through wraps, and averaging those products over a tile gives the mean
step directly. No unwrapping anywhere in this file.

    python3 scripts/ramp_vs_source.py
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
KM_LAT = 110.57
FRINGE_CM = 5.5465 / 2


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


def tile_gradients(pair, tile_km=12.0):
    d = f"{SNAP}/{pair}_full.data"
    i, meta = read_img(d, "i_ifg")
    q, _ = read_img(d, "q_ifg")
    coh, _ = read_img(d, "coh_")
    m = meta["map info"].strip("{}").split(",")
    xr, yr = float(m[5]), float(m[6])
    west = float(m[3]) - (float(m[1]) - 1) * xr
    north = float(m[4]) + (float(m[2]) - 1) * yr
    kx = 111.32 * np.cos(np.deg2rad(EPI_LAT))

    valid = (coh > 0) & np.isfinite(coh) & ((i != 0) | (q != 0)) & (coh >= .2)
    amp = np.hypot(i, q)
    z = np.where(valid & (amp > 0), (i + 1j * q) / np.maximum(amp, 1e-12), 0)

    # Filter FIRST, with the same 11x11 coherence-weighted complex average the
    # transect test uses. Measuring the gradient on raw 40 m phase instead gave
    # a scene-median of ~0.9 rad/km, which implies ~2.9 cycles across a 20 km
    # transect -- four times what unwrapping the same ground actually shows.
    # Adjacent geocoded pixels are correlated (4x1 multilook then resampled to
    # 40 m), so per-pixel differences are not independent samples of a smooth
    # gradient and their circular mean does not recover it. Both tests now run
    # on the same field, so their numbers are comparable.
    def bs(x, wn):
        p = np.zeros((x.shape[0] + 1, x.shape[1] + 1), dtype=np.float64)
        p[1:, 1:] = np.cumsum(np.cumsum(x, axis=0), axis=1)
        r = np.zeros(x.shape)
        hh = wn // 2
        v = p[wn:, wn:] - p[:-wn, wn:] - p[wn:, :-wn] + p[:-wn, :-wn]
        r[hh:hh + v.shape[0], hh:hh + v.shape[1]] = v
        return r

    W = 11
    cohw = np.where(valid, coh, 0.0)
    z = bs(cohw * z.real, W) + 1j * bs(cohw * z.imag, W)
    valid = valid & (np.abs(z) > 0)
    az = np.abs(z)
    z = np.where(valid, z / np.maximum(az, 1e-12), 0)

    # Phase step between horizontally and vertically adjacent pixels, wrap-safe.
    gx = z[:, 1:] * np.conj(z[:, :-1])
    gy = z[1:, :] * np.conj(z[:-1, :])
    mx = valid[:, 1:] & valid[:, :-1]
    my = valid[1:, :] & valid[:-1, :]

    ty = max(1, int(round(tile_km / (yr * KM_LAT))))
    tx = max(1, int(round(tile_km / (xr * kx))))
    nh, nw = (z.shape[0] - 1) // ty, (z.shape[1] - 1) // tx

    def agg(g, mask, n_h, n_w):
        g = np.where(mask, g, 0)[:n_h * ty, :n_w * tx]
        c = mask.astype(np.float64)[:n_h * ty, :n_w * tx]
        gs = g.reshape(n_h, ty, n_w, tx).sum(axis=(1, 3))
        cs = c.reshape(n_h, ty, n_w, tx).sum(axis=(1, 3))
        return gs, cs

    gxs, cxs = agg(gx, mx, nh, nw)
    gys, cys = agg(gy, my, nh, nw)
    enough = (cxs > 0.25 * ty * tx) & (cys > 0.25 * ty * tx)

    # rad/pixel -> rad/km, and the resultant length as a quality gate.
    px_km_x = xr * kx
    px_km_y = yr * KM_LAT
    dphidx = np.where(enough, np.angle(gxs) / px_km_x, np.nan)
    dphidy = np.where(enough, np.angle(gys) / px_km_y, np.nan)
    Rx = np.where(enough, np.abs(gxs) / np.maximum(cxs, 1), np.nan)

    lon = west + (np.arange(nw) + .5) * tx * xr
    lat = north - (np.arange(nh) + .5) * ty * yr
    LO, LA = np.meshgrid(lon, lat)
    dist = np.hypot((LO - EPI_LON) * kx, (LA - EPI_LAT) * KM_LAT)
    return dict(dx=dphidx, dy=dphidy, R=Rx, dist=dist, lon=LO, lat=LA,
                ext=[west, west + z.shape[1] * xr,
                     north - z.shape[0] * yr, north])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tile-km", type=float, default=12.0)
    ap.add_argument("--min-R", type=float, default=0.10)
    a = ap.parse_args()

    out = {}
    for pair in ("prepost", "prepre"):
        g = tile_gradients(pair, a.tile_km)
        ok = np.isfinite(g["dx"]) & (g["R"] >= a.min_R)
        g["ok"] = ok
        out[pair] = g
        lab = "CO-EVENT" if pair == "prepost" else "CONTROL "
        cm_km = np.nanmedian(g["dx"][ok]) / (2 * np.pi) * FRINGE_CM
        print(f"\n=== {lab} ({pair}) — {ok.sum()} tiles of "
              f"{a.tile_km:.0f} km ===")
        print(f"  median east-west gradient  {np.nanmedian(g['dx'][ok]):+.4f} "
              f"rad/km  ({cm_km:+.3f} cm/km)")
        print(f"  median north-south gradient {np.nanmedian(g['dy'][ok]):+.4f} "
              f"rad/km")
        print("\n   distance     tiles    median dphi/dx (rad/km)")
        prof = []
        for lo in range(20, 180, 20):
            s = ok & (g["dist"] >= lo) & (g["dist"] < lo + 20)
            if s.sum() < 4:
                continue
            v = float(np.nanmedian(g["dx"][s]))
            print(f"    {lo:3d}-{lo+20:<3d} km   {s.sum():5d}     {v:+.4f}")
            prof.append((lo, v, int(s.sum())))
        g["prof"] = prof

    pp = out["prepost"]["prof"]
    print("\n=== ramp or source? ===")
    if len(pp) >= 4:
        near = np.mean([p[1] for p in pp[:2]])
        far = np.mean([p[1] for p in pp[-2:]])
        allv = np.array([p[1] for p in pp])
        scatter = float(np.std(allv))
        print(f"  co-event gradient: near {near:+.4f}, far {far:+.4f} rad/km")
        print(f"  spread across all distance bins: sd {scatter:.4f}")
        if abs(near) > 2 * abs(far) and abs(near - far) > 2 * scatter:
            print("  -> gradient DECAYS with distance: consistent with a")
            print("     source. Worth modelling.")
        elif abs(near - far) < scatter:
            print("  -> gradient is essentially UNIFORM across the scene.")
            print("     That is a ramp -- residual orbit, ionosphere or")
            print("     long-wavelength atmosphere -- not a source. A source")
            print("     at 20 km cannot produce the same tilt at 170 km.")
        else:
            print("  -> intermediate. Report the numbers; do not round them.")

    # ------------------------------------------------------------------ plot
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(15, 9.5))
    for k, pair in enumerate(("prepost", "prepre")):
        g = out[pair]
        lab = ("CO-EVENT 6→18 Aug (spans the M7.7)" if pair == "prepost"
               else "CONTROL 25 Jul→6 Aug (no earthquake)")
        ax = axes[k][0]
        im = ax.imshow(np.where(g["ok"], g["dx"], np.nan), cmap="RdBu_r",
                       extent=g["ext"], vmin=-.6, vmax=.6, origin="upper",
                       interpolation="nearest", aspect="auto")
        ax.plot(EPI_LON, EPI_LAT, "*", color="#00ff88", ms=16, mec="k", mew=.8)
        ax.set_title(f"{lab}\neast-west phase gradient (rad/km), "
                     f"{a.tile_km:.0f} km tiles", fontsize=10, loc="left")
        ax.set_ylabel("lat")
        fig.colorbar(im, ax=ax, shrink=.85, pad=.02)
        if k:
            ax.set_xlabel("lon")

        ax = axes[k][1]
        if g["prof"]:
            ax.plot([p[0] + 10 for p in g["prof"]],
                    [p[1] for p in g["prof"]], "o-", lw=1.4,
                    color="#1f3b73" if not k else "#8c2d04")
        ax.axhline(0, color="0.4", lw=.8)
        ax.set_ylim(-.5, .5)
        ax.set_ylabel("median dφ/dx (rad/km)")
        ax.set_title("Gradient against distance from the rupture\n"
                     "a source decays; a ramp is flat", fontsize=10,
                     loc="left")
        if k:
            ax.set_xlabel("distance from epicentre (km)")

    fig.suptitle("Is the co-event phase gradient a source or a ramp?",
                 fontsize=13, y=.99)
    fig.tight_layout(rect=[0, 0, 1, .96])
    o = f"{SNAP}/ramp_vs_source.png"
    fig.savefig(o, dpi=130)
    print(f"\nwrote {o}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
