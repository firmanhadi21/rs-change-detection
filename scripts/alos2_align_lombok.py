"""Align the Lombok pair in insardev and check it against GMTSAR's answer.

This is the first test that exercises the whole alignment path at once --
SAT_llt2rat projecting a coarse DEM into both scenes, fitoffset fitting a
bilinear model, then the xcorr grid refining it -- rather than testing the
pieces. And it is checkable, because GMTSAR aligned the same pair and left its
answer on disk:

    SLC/IMG-HH-...-180804-...PRM     rshift -32, sub_int_r 0.675400
                                     ashift   7, sub_int_a 0.751880
                                     stretch_r -1.95194e-04
                                     stretch_a -5.30903e-05
    SLC/freq_xcorr.dat               the 1000 patch offsets behind them

WHAT AGREEMENT WOULD AND WOULD NOT MEAN. The two codes measure the same
physical misregistration, so the totals should match closely. They do not have
to match exactly: GMTSAR correlates over its own patch grid with its own
window and its own SNR cut, and insardev uses a different grid, a Hann window
and phaseCorrelate. A sub-pixel difference is expected. A difference of whole
pixels is not, and a difference in SIGN would mean one of us has the reference
and secondary the other way round -- which is the failure this is really
looking for, because it produces a perfectly clean-looking interferogram of
the wrong thing.

    conda run -n insardev-test python scripts/alos2_align_lombok.py
"""

import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE = os.path.expanduser("~/Teaching/UNDIP/InSAR/EQ/Pair1")
RAW = os.path.join(BASE, "raw")
DEM = os.path.join(BASE, "topo", "dem.grd")
GMTSAR_PRM = os.path.join(
    BASE, "SLC", "IMG-HH-ALOS2226747020-180804-FBDR1.1__A.PRM")
XCORR = os.path.join(BASE, "SLC", "freq_xcorr.dat")


def read_prm(path):
    out = {}
    with open(path) as fh:
        for line in fh:
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            try:
                out[k.strip()] = float(v.strip())
            except ValueError:
                out[k.strip()] = v.strip()
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--patch", type=int, default=512)
    ap.add_argument("--n-jobs", type=int, default=8)
    ap.add_argument("--min-response", type=float, default=0.2)
    ap.add_argument("--degrees", type=float, default=12.0 / 3600)
    a = ap.parse_args()

    from earthchange.alos2_mission import ALOS2

    if not os.path.exists(DEM):
        sys.exit(f"missing DEM {DEM}")

    stack = ALOS2(RAW, DEM=DEM)
    scenes = sorted(stack.df.index.get_level_values(2))
    ref, rep = scenes[0], scenes[1]
    print(f"\nreference {ref}\nsecondary {rep}\n")

    print("align_ref ...")
    prm_ref, _, _ = stack.align_ref(ref, return_slc=False)
    print(f"  clock_start {prm_ref.get('clock_start'):.7f}, "
          f"SC_vel {prm_ref.get('SC_vel'):.2f}, "
          f"earth_radius {prm_ref.get('earth_radius'):.1f}")

    print("\nalign_rep ...")
    prm_rep, _, _ = stack.align_rep(
        rep, ref, prm_ref, degrees=a.degrees, return_slc=False,
        xcorr=(a.patch, a.patch), xcorr_n_jobs=a.n_jobs,
        xcorr_min_response=a.min_response, debug=True)

    ours = {k: float(prm_rep.get(k)) for k in
            ("rshift", "sub_int_r", "ashift", "sub_int_a",
             "stretch_r", "stretch_a", "a_stretch_r", "a_stretch_a")}
    g = read_prm(GMTSAR_PRM)

    print("\n  alignment, ours vs GMTSAR")
    print(f"  {'':<14}{'ours':>16}{'GMTSAR':>16}{'diff':>14}")
    r_ours = ours["rshift"] + ours["sub_int_r"]
    r_g = g["rshift"] + g["sub_int_r"]
    a_ours = ours["ashift"] + ours["sub_int_a"]
    a_g = g["ashift"] + g["sub_int_a"]
    print(f"  {'rshift total':<14}{r_ours:>16.4f}{r_g:>16.4f}"
          f"{r_ours - r_g:>+14.4f} px")
    print(f"  {'ashift total':<14}{a_ours:>16.4f}{a_g:>16.4f}"
          f"{a_ours - a_g:>+14.4f} px")
    for k in ("stretch_r", "stretch_a", "a_stretch_r", "a_stretch_a"):
        gv = g.get(k, float("nan"))
        print(f"  {k:<14}{ours[k]:>16.3e}{gv:>16.3e}{ours[k] - gv:>+14.3e}")

    # The stretch terms are only meaningful multiplied by a coordinate, so
    # compare what they actually do: the total offset each model predicts at
    # the far edge of the swath, where the difference is largest.
    nx = float(prm_rep.get("num_rng_bins"))
    ny = float(prm_rep.get("num_lines"))
    print(f"\n  predicted offset at the far-range, far-azimuth corner "
          f"({int(nx)}, {int(ny)})")
    for label, rs, as_, sr, sa, asr, asa in (
        ("ours", r_ours, a_ours, ours["stretch_r"], ours["stretch_a"],
         ours["a_stretch_r"], ours["a_stretch_a"]),
        ("GMTSAR", r_g, a_g, g["stretch_r"], g["stretch_a"],
         g.get("a_stretch_r", 0.0), g.get("a_stretch_a", 0.0)),
    ):
        dr = rs + sr * nx + asr * ny
        da = as_ + sa * nx + asa * ny
        print(f"    {label:<8} dr {dr:+9.4f}   da {da:+9.4f}")

    # And against the raw measurements GMTSAR made, which are independent of
    # how either code fitted them.
    if os.path.exists(XCORR):
        d = np.loadtxt(XCORR)
        print(f"\n  GMTSAR's {len(d)} raw patch offsets: "
              f"dr median {np.median(d[:, 1]):+.3f} "
              f"(p16..p84 {np.percentile(d[:, 1], 16):+.3f} .. "
              f"{np.percentile(d[:, 1], 84):+.3f})")
        print(f"  {'':<26} da median {np.median(d[:, 3]):+.3f} "
              f"(p16..p84 {np.percentile(d[:, 3], 16):+.3f} .. "
              f"{np.percentile(d[:, 3], 84):+.3f})")

    ok = abs(r_ours - r_g) < 1.0 and abs(a_ours - a_g) < 1.0
    print(f"\n  {'AGREES' if ok else 'DISAGREES'} with GMTSAR to within "
          f"1 pixel in both directions")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
