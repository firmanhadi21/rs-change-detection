"""Are those bands fringes, or undulation? Measure it along transects.

Filtered wrapped phase over western Flores looks banded, and banded looks like
fringes. But two very different things produce bands in a cyclic colourmap:

  FRINGES       phase ADVANCES through the colour wheel in one rotational
                direction, accumulating 2*pi per fringe. Crossing five fringes
                accumulates 10*pi and never comes back.
  UNDULATION    phase rises and returns -- atmosphere thickening then thinning.
                The colours run forward through the wheel and then BACKWARD
                through the same sequence, netting to roughly zero.

A static image cannot separate them, because the eye sees "bands" either way
and the wrap makes both look periodic. Unwrapping along a line does separate
them, with one number:

    fringe fraction = |net phase change| / total variation along the transect

Near 1: every step went the same way -- fringes, real motion.
Near 0: the phase went out and came back -- undulation, atmosphere.

The control pair is processed identically and shown beside it. Whatever the
co-event number turns out to be, it only means something relative to twelve
days that contained no earthquake.

    python3 scripts/fringe_test.py
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
FRINGE_CM = 5.5465 / 2
# Box 1 from plot_focus_area.py: the clearest ground in the scene, and the
# panel the bands are most visible in.
BOX = dict(lon0=121.118, lon1=121.371, lat0=-8.806, lat1=-8.552)


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


def boxsum(a, w):
    p = np.zeros((a.shape[0] + 1, a.shape[1] + 1), dtype=np.float64)
    p[1:, 1:] = np.cumsum(np.cumsum(a, axis=0), axis=1)
    r = np.full(a.shape, np.nan)
    h = w // 2
    v = p[w:, w:] - p[:-w, w:] - p[w:, :-w] + p[:-w, :-w]
    r[h:h + v.shape[0], h:h + v.shape[1]] = v
    return r


def smooth1d(z, k):
    """Boxcar-average a complex line; keeps wrapping correct."""
    ker = np.ones(k) / k
    return (np.convolve(z.real, ker, mode="same")
            + 1j * np.convolve(z.imag, ker, mode="same"))


def load(pair, win):
    d = f"{SNAP}/{pair}_full.data"
    i, meta = read_img(d, "i_ifg")
    q, _ = read_img(d, "q_ifg")
    coh, _ = read_img(d, "coh_")
    m = meta["map info"].strip("{}").split(",")
    xr, yr = float(m[5]), float(m[6])
    west = float(m[3]) - (float(m[1]) - 1) * xr
    north = float(m[4]) + (float(m[2]) - 1) * yr

    valid = (coh > 0) & np.isfinite(coh) & ((i != 0) | (q != 0))
    cohv = np.where(valid, coh, 0.0)
    amp = np.hypot(i, q)
    ui = np.where(valid & (amp > 0), cohv * i / np.maximum(amp, 1e-12), 0.0)
    uq = np.where(valid & (amp > 0), cohv * q / np.maximum(amp, 1e-12), 0.0)
    z = boxsum(ui, win) + 1j * boxsum(uq, win)

    c0 = int((BOX["lon0"] - west) / xr); c1 = int((BOX["lon1"] - west) / xr)
    r0 = int((north - BOX["lat1"]) / yr); r1 = int((north - BOX["lat0"]) / yr)
    sub = (slice(r0, r1), slice(c0, c1))
    return z[sub], valid[sub], (BOX["lon0"], BOX["lon1"],
                                BOX["lat0"], BOX["lat1"]), xr


def transects(z, valid, n, smooth_px):
    """Unwrap along evenly spaced rows; return per-row statistics."""
    out = []
    rows = np.linspace(0, z.shape[0] - 1, n + 2).astype(int)[1:-1]
    for r in rows:
        line = z[r]
        good = valid[r] & np.isfinite(line.real) & (np.abs(line) > 0)
        if good.sum() < 200:
            continue
        # Longest run of valid samples: a transect broken by sea would create
        # a false jump at the gap, which unwrapping would happily absorb.
        idx = np.flatnonzero(good)
        splits = np.split(idx, np.flatnonzero(np.diff(idx) > 1) + 1)
        seg = max(splits, key=len)
        if len(seg) < 200:
            continue
        zz = smooth1d(line[seg] / np.abs(line[seg]), smooth_px)
        phi = np.unwrap(np.angle(zz))
        # Trim the smoothing edges, where the boxcar runs off the segment.
        h = smooth_px
        phi = phi[h:-h] if len(phi) > 3 * h else phi
        if len(phi) < 100:
            continue
        net = phi[-1] - phi[0]
        tv = float(np.abs(np.diff(phi)).sum())
        out.append(dict(row=r, phi=phi, seg=seg, net=net, tv=tv,
                        frac=abs(net) / tv if tv > 0 else np.nan))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--filter", type=int, default=11)
    ap.add_argument("--smooth-px", type=int, default=25,
                    help="along-transect boxcar; 25 px = 1 km, suppresses "
                         "noise that would inflate total variation")
    ap.add_argument("--n", type=int, default=7)
    a = ap.parse_args()

    res = {}
    for pair in ("prepost", "prepre"):
        z, valid, ext, xr = load(pair, a.filter)
        t = transects(z, valid, a.n, a.smooth_px)
        res[pair] = (z, valid, ext, t)
        label = "CO-EVENT" if pair == "prepost" else "CONTROL "
        print(f"\n=== {label} ({pair}) — box 1, {len(t)} transects ===")
        print("   row   net phase   cycles   total var   fringe fraction")
        for d in t:
            print(f"  {d['row']:5d}  {d['net']:+8.2f}    "
                  f"{d['net']/(2*np.pi):+5.2f}    {d['tv']:8.2f}     "
                  f"{d['frac']:.3f}")
        fr = np.array([d["frac"] for d in t])
        cy = np.array([abs(d["net"]) / (2 * np.pi) for d in t])
        print(f"  median fringe fraction {np.median(fr):.3f}   "
              f"median |cycles| {np.median(cy):.2f}")
        res[pair] += (fr, cy)

    fp = np.median(res["prepost"][4]); fc = np.median(res["prepre"][4])
    print("\n=== verdict ===")
    print(f"  co-event fringe fraction {fp:.3f}   "
          f"control {fc:.3f}")
    print("  A fringe pattern gives a fraction near 1: phase advances and")
    print("  never returns. Undulation gives near 0: it goes out and comes")
    print("  back. Values here are what matters, and so is the gap between")
    print("  them -- if the control matches, the bands are not the event.")
    if fp > 0.6 and fp > fc + 0.2:
        print("  -> co-event bands ADVANCE and the control does not: fringes.")
    elif abs(fp - fc) < 0.15:
        print("  -> co-event and control behave the SAME. The bands are")
        print("     undulation present with or without an earthquake.")
    else:
        print("  -> intermediate; report the numbers, do not round them into")
        print("     a verdict.")

    # ------------------------------------------------------------------ plot
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(14, 10.5),
                             gridspec_kw=dict(width_ratios=[1, 1.25]))
    for k, pair in enumerate(("prepost", "prepre")):
        z, valid, ext, t, fr, cy = res[pair]
        ph = np.where(valid & (np.abs(z) > 0), np.angle(z), np.nan)
        ax = axes[k][0]
        ax.imshow(ph, cmap="twilight_shifted", extent=ext, vmin=-np.pi,
                  vmax=np.pi, origin="upper", interpolation="nearest")
        for d in t:
            y = ext[3] - (d["row"] / z.shape[0]) * (ext[3] - ext[2])
            x0 = ext[0] + (d["seg"][0] / z.shape[1]) * (ext[1] - ext[0])
            x1 = ext[0] + (d["seg"][-1] / z.shape[1]) * (ext[1] - ext[0])
            ax.plot([x0, x1], [y, y], color="#00e5ff", lw=1.1)
        lab = ("CO-EVENT 6→18 Aug (spans the M7.7)" if pair == "prepost"
               else "CONTROL 25 Jul→6 Aug (no earthquake)")
        ax.set_title(f"{lab}\nfiltered phase · cyan = transects",
                     fontsize=10, loc="left")
        ax.set_ylabel("lat")
        if k:
            ax.set_xlabel("lon")

        ax = axes[k][1]
        for d in t:
            x = np.linspace(0, len(d["phi"]) * 0.04, len(d["phi"]))
            ax.plot(x, (d["phi"] - d["phi"][0]) / (2 * np.pi), lw=1.1)
        ax.axhline(0, color="0.4", lw=.8)
        ax.set_ylabel("cumulative phase (cycles)")
        ax.set_ylim(-2.2, 2.2)
        ax.set_title(f"Unwrapped along each transect — median fringe "
                     f"fraction {np.median(fr):.2f}\n"
                     "fringes would climb steadily; these wander and return",
                     fontsize=10, loc="left")
        if k:
            ax.set_xlabel("distance along transect (km)")

    fig.suptitle("Are the bands fringes? Phase must ADVANCE, not oscillate — "
                 "co-event against an earthquake-free control",
                 fontsize=13, y=.98)
    fig.tight_layout(rect=[0, 0, 1, .96])
    out = f"{SNAP}/fringe_test.png"
    fig.savefig(out, dpi=135)
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
