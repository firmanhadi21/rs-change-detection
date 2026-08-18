"""Zoom on the clearest parts of the interferogram, filtered so fringes show.

A null argued from a whole-island map invites the obvious objection: the scene
is mostly marginal coherence, so of course nothing is visible. This answers it
by going to the BEST ground available and looking there properly.

Two things happen here that the wide maps do not do.

FILTERING. Raw 40 m phase at coherence ~0.3 is dominated by speckle, and
speckle hides fringes. Averaging the COMPLEX interferogram over a small window
-- weighted by coherence, so good pixels lead -- suppresses that. Averaging the
phase ANGLE instead would be wrong: the mean of +3.0 and -3.0 rad is 0 when the
two are 0.28 rad apart, so wrapping must be handled by summing unit vectors.

LOCAL PHASE CONSISTENCY. |sum(coh * exp(i*phi))| / sum(coh) over the window is
near 1 where neighbouring pixels agree -- a smooth fringe -- and near 0 where
they do not. This separates "a fringe is present but faint" from "there is
nothing here", which the phase image alone cannot do, because a colourful
speckle field and a real fringe can look similar at a glance.

BOX SELECTION is measured, not eyeballed. Two boxes are reported:
  BEST         highest mean coherence anywhere in the scene
  NEAR-FIELD   highest mean coherence within --near km of the epicentre
They differ, and the difference matters: the clearest ground is not necessarily
the ground where a signal would be largest, and showing only the former would
be picking the sample that best supports the conclusion.

    python3 scripts/plot_focus_area.py
    python3 scripts/plot_focus_area.py --box-km 20 --filter 15
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
    """Sliding-window sum via an integral image; O(n) regardless of w."""
    p = np.zeros((a.shape[0] + 1, a.shape[1] + 1), dtype=np.float64)
    p[1:, 1:] = np.cumsum(np.cumsum(a, axis=0), axis=1)
    r = np.full(a.shape, np.nan)
    h = w // 2
    v = (p[w:, w:] - p[:-w, w:] - p[w:, :-w] + p[:-w, :-w])
    r[h:h + v.shape[0], h:h + v.shape[1]] = v
    return r


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--suffix", default="full")
    ap.add_argument("--pair", default="prepost", choices=("prepost", "prepre"),
                    help="prepre is the CONTROL: same track, same 12-day "
                         "baseline, no earthquake in it")
    ap.add_argument("--box-km", type=float, default=28.0)
    ap.add_argument("--filter", type=int, default=11,
                    help="complex averaging window in pixels (odd)")
    ap.add_argument("--near", type=float, default=60.0,
                    help="near-field box must lie within this many km")
    ap.add_argument("--min-valid", type=float, default=0.55,
                    help="reject boxes that are mostly sea")
    a = ap.parse_args()

    d = f"{SNAP}/{a.pair}_{a.suffix}.data"
    i, meta = read_img(d, "i_ifg")
    q, _ = read_img(d, "q_ifg")
    coh, _ = read_img(d, "coh_")

    # Box selection ALWAYS uses the co-event coherence, whichever pair is being
    # displayed. Letting the control pick its own boxes would compare different
    # ground and prove nothing; the control has to be shown the same place.
    sel_coh, sel_meta = coh, meta
    if a.pair != "prepost":
        sel_coh, sel_meta = read_img(f"{SNAP}/prepost_{a.suffix}.data", "coh_")
        h = min(sel_coh.shape[0], coh.shape[0])
        w = min(sel_coh.shape[1], coh.shape[1])
        i, q, coh = i[:h, :w], q[:h, :w], coh[:h, :w]
        sel_coh = sel_coh[:h, :w]
        meta = sel_meta

    m = meta["map info"].strip("{}").split(",")
    xr, yr = float(m[5]), float(m[6])
    west = float(m[3]) - (float(m[1]) - 1) * xr
    north = float(m[4]) + (float(m[2]) - 1) * yr
    kx = 111.32 * np.cos(np.deg2rad(EPI_LAT))

    valid = (coh > 0) & np.isfinite(coh) & ((i != 0) | (q != 0))
    cohv = np.where(valid, coh, 0.0)
    selv = np.where((sel_coh > 0) & np.isfinite(sel_coh), sel_coh, 0.0)

    bw = int(round(a.box_km / (xr * kx)))
    bw += 1 - bw % 2
    print(f"scene {i.shape}, box {a.box_km:.0f} km = {bw} px, "
          f"filter {a.filter} px = {a.filter*xr*kx*1000:.0f} m")

    # Mean coherence per candidate box, over VALID pixels only -- otherwise a
    # box half in the sea scores well simply by holding fewer bad pixels.
    s_coh = boxsum(selv, bw)
    s_val = boxsum((selv > 0).astype(np.float64), bw)
    frac = s_val / (bw * bw)
    mean_coh = np.where(s_val > 0, s_coh / np.maximum(s_val, 1), np.nan)
    mean_coh = np.where(frac >= a.min_valid, mean_coh, np.nan)

    rows = np.arange(i.shape[0])[:, None]
    cols = np.arange(i.shape[1])[None, :]
    lon_c = west + (cols + .5) * xr
    lat_c = north - (rows + .5) * yr
    dist_c = np.hypot((lon_c - EPI_LON) * kx,
                      (lat_c - EPI_LAT) * KM_PER_DEG_LAT)

    picks = []
    flat = np.where(np.isfinite(mean_coh), mean_coh, -1)
    r0, c0 = np.unravel_index(np.argmax(flat), flat.shape)
    picks.append(("BEST coherence in scene", r0, c0))

    # The second box must be COMPLEMENTARY, or the figure shows the same
    # ground twice. "Best coherence within N km" collapses onto the first pick
    # whenever the clearest ground is already near the rupture -- which it is
    # here. Take instead the CLOSEST box to the epicentre that still has
    # workable coherence, so the pair spans "clearest" and "nearest".
    good = np.isfinite(mean_coh)
    if good.any():
        thr = np.percentile(mean_coh[good], 70)
        cand = np.where(good & (mean_coh >= thr), dist_c, np.inf)
        if np.isfinite(cand).any():
            r1, c1 = np.unravel_index(np.argmin(cand), cand.shape)
            if abs(r1 - r0) > bw // 2 or abs(c1 - c0) > bw // 2:
                picks.append((f"NEAREST rupture at coherence >= {thr:.2f}",
                              r1, c1))
            else:
                print("  (nearest workable box overlaps the best box; "
                      "showing one)")

    # ---- coherence-weighted complex filter, computed once for the scene ----
    zi = boxsum(np.where(valid, cohv * i, 0.0), a.filter)
    zq = boxsum(np.where(valid, cohv * q, 0.0), a.filter)
    # i and q carry the interferogram amplitude; normalise so the phasor sum
    # is not dominated by a few bright scatterers.
    amp = np.hypot(i, q)
    ui = np.where(valid & (amp > 0), cohv * i / np.maximum(amp, 1e-12), 0.0)
    uq = np.where(valid & (amp > 0), cohv * q / np.maximum(amp, 1e-12), 0.0)
    zi = boxsum(ui, a.filter)
    zq = boxsum(uq, a.filter)
    zw = boxsum(cohv, a.filter)
    filt_phase = np.arctan2(zq, zi)
    consist = np.where(zw > 0, np.hypot(zi, zq) / np.maximum(zw, 1e-12),
                       np.nan)

    print("\n=== focus areas ===")
    boxes = []
    for name, r, c in picks:
        r_lo, r_hi = max(0, r - bw // 2), min(i.shape[0], r + bw // 2)
        c_lo, c_hi = max(0, c - bw // 2), min(i.shape[1], c + bw // 2)
        sub = (slice(r_lo, r_hi), slice(c_lo, c_hi))
        v = valid[sub]
        cc = consist[sub][v & np.isfinite(consist[sub])]
        lo_lon = west + c_lo * xr
        hi_lon = west + c_hi * xr
        hi_lat = north - r_lo * yr
        lo_lat = north - r_hi * yr
        dd = dist_c[r, c]
        print(f"\n  {name}")
        print(f"    lon {lo_lon:.3f}..{hi_lon:.3f}  "
              f"lat {lo_lat:.3f}..{hi_lat:.3f}")
        print(f"    {dd:.0f} km from epicentre, "
              f"{100*v.mean():.0f}% valid, mean coherence "
              f"{np.nanmean(np.where(v, coh[sub], np.nan)):.3f}")
        if cc.size:
            print(f"    local phase consistency after filtering: "
                  f"median {np.median(cc):.3f}, p90 {np.percentile(cc,90):.3f}")
        boxes.append((name, sub, (lo_lon, hi_lon, lo_lat, hi_lat), dd, cc))

    # ------------------------------------------------------------------ plot
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    ext = [west, west + i.shape[1] * xr, north - i.shape[0] * yr, north]
    rr = np.flatnonzero(valid.any(axis=1)); cx = np.flatnonzero(valid.any(axis=0))
    view = [west + (cx[0] - 1) * xr - .05, west + (cx[-1] + 1) * xr + .05,
            north - (rr[-1] + 1) * yr - .05, min(north - (rr[0] - 1) * yr,
                                                 EPI_LAT) + .08]

    n = len(boxes)
    fig = plt.figure(figsize=(15.5, 4.6 + 4.4 * n))
    gs = fig.add_gridspec(1 + n, 3, height_ratios=[1.0] + [1.35] * n,
                          hspace=.30, wspace=.20)

    ax = fig.add_subplot(gs[0, :])
    im = ax.imshow(np.where(valid, coh, np.nan), cmap="magma", extent=ext,
                   vmin=0, vmax=.8, origin="upper", interpolation="nearest")
    ax.plot(EPI_LON, EPI_LAT, "*", color="#00ff88", ms=17, mec="k", mew=.8)
    for k, (name, sub, bb, dd, cc) in enumerate(boxes):
        ax.add_patch(Rectangle((bb[0], bb[2]), bb[1] - bb[0], bb[3] - bb[2],
                               fill=False, ec="#00e5ff", lw=2.0))
        ax.annotate(f"{k+1}", (bb[0], bb[3]), color="#00e5ff", fontsize=13,
                    fontweight="bold", va="bottom", ha="left")
    ax.set_xlim(view[0], view[1]); ax.set_ylim(view[2], view[3])
    ax.set_title("Coherence, whole scene — focus boxes chosen by measured "
                 "coherence, not by eye\n(1 = clearest ground anywhere, "
                 "2 = clearest ground near the rupture)",
                 fontsize=10.5, loc="left")
    ax.set_xlabel("lon"); ax.set_ylabel("lat")
    fig.colorbar(im, ax=ax, shrink=.85, pad=.01)

    for k, (name, sub, bb, dd, cc) in enumerate(boxes):
        e = [bb[0], bb[1], bb[2], bb[3]]
        v = valid[sub]

        ax = fig.add_subplot(gs[k + 1, 0])
        ax.imshow(np.where(v, np.arctan2(q[sub], i[sub]), np.nan),
                  cmap="twilight_shifted", extent=e, vmin=-np.pi, vmax=np.pi,
                  origin="upper", interpolation="nearest")
        ax.set_title(f"{k+1}a  Raw wrapped phase — {name}\n"
                     f"{dd:.0f} km from epicentre · 40 m pixels, unfiltered",
                     fontsize=9.5, loc="left")
        ax.set_ylabel("lat")

        ax = fig.add_subplot(gs[k + 1, 1])
        ax.imshow(np.where(v, filt_phase[sub], np.nan),
                  cmap="twilight_shifted", extent=e, vmin=-np.pi, vmax=np.pi,
                  origin="upper", interpolation="nearest")
        ax.set_title(f"{k+1}b  Same, coherence-weighted complex filter\n"
                     f"{a.filter}x{a.filter} px · a fringe would appear here "
                     "if present", fontsize=9.5, loc="left")

        ax = fig.add_subplot(gs[k + 1, 2])
        im2 = ax.imshow(np.where(v, consist[sub], np.nan), cmap="viridis",
                        extent=e, vmin=0, vmax=.6, origin="upper",
                        interpolation="nearest")
        med = np.median(cc) if cc.size else float("nan")
        ax.set_title(f"{k+1}c  Local phase consistency (median {med:.2f})\n"
                     "1 = neighbours agree, a smooth fringe · 0 = noise",
                     fontsize=9.5, loc="left")
        fig.colorbar(im2, ax=ax, shrink=.85, pad=.02)

    label = ("CO-EVENT 6→18 Aug 2026 (spans the M7.7)" if a.pair == "prepost"
             else "CONTROL 25 Jul→6 Aug 2026 (no earthquake)")
    fig.suptitle(f"Flores M7.7 — clearest ground, filtered · {label}\n"
                 "Run both: structure appearing in the control cannot be "
                 "the earthquake.", fontsize=12.5, y=.999)
    out = f"{SNAP}/focus_areas_{a.pair}_{a.suffix}.png"
    fig.savefig(out, dpi=130, bbox_inches="tight")
    print(f"\nwrote {out}")

    print("\n=== reading the middle column ===")
    print("  continuous colour bands marching across   -> a fringe: real motion")
    print("  smooth patches with no repeating order    -> atmosphere")
    print("  residual mottling that survives filtering -> still noise")
    print("The right column decides between the last two without judgement by")
    print("eye: consistency stays low where the phase never organises.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
