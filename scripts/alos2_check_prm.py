"""Compare our PRM against GMTSAR's for the same scene, field by field.

GMTSAR wrote a PRM for both Lombok scenes and then made a working
interferogram from it, so it is the closest thing to ground truth available.
Every field we produce that GMTSAR also produces can be checked; the ones only
we produce are reported so they are at least visible.

Also checks that calc_dop_orb actually COMPUTES rather than passing through.
Our PRM seeds fd1 = 0, and a zero-Doppler L1.1 product legitimately ends with
fd1 = 0, so "it ran and fd1 is 0" is not evidence it did anything. The test is
whether the fields calc_dop_orb is supposed to write changed at all.

    conda run -n insardev-test python scripts/alos2_check_prm.py
"""

import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RAW = os.path.expanduser("~/Teaching/UNDIP/InSAR/EQ/Pair1/raw")

# Fields GMTSAR records that mean the same thing in both, with the tolerance
# each one actually deserves. Setting these too tight is not conservatism --
# it flags correct values as broken and buries the one field that is really
# wrong. GMTSAR's PRM is a text file with fixed print precision, so for
# several fields it is the LESS precise of the two and the tolerance has to be
# set by its printing, not by our reading.
COMPARE = {
    "radar_wavelength": 1e-5,   # PRM prints 0.242452; leader has 0.2424525
    "rng_samp_rate": 1e-9,      # printed in full
    "PRF": 1e-7,                # PRM prints 2134.770000, leader 2134.7701213
    "near_range": 1e-9,         # integer metres in both
    "chirp_slope": 1e-6,
    "num_rng_bins": 0,          # exact or the layout is wrong
    "clock_start": 2e-9,        # 2e-9 days = 0.17 ms, well under one line
    "SC_clock_start": 1e-11,    # same quantity, larger magnitude
    # Geometry we derive rather than read. These are computed at a slightly
    # different point along the orbit than GMTSAR uses, so they are expected
    # to agree in the fifth digit and not beyond; insardev's own calc_dop_orb
    # disagrees with GMTSAR by more than we do (see below).
    "SC_height": 2e-3,
    "earth_radius": 1e-5,
    "SC_vel": 2e-3,
}


def read_prm(path):
    out = {}
    with open(path) as fh:
        for line in fh:
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip()
            try:
                out[k] = float(v)
            except ValueError:
                out[k] = v
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    a = ap.parse_args()

    from earthchange import alos2
    from insardev_pygmtsar.PRM import PRM

    n_ok = n_tot = 0
    for scene, (leader, image) in sorted(
            alos2.find_scenes(RAW, pol="HH").items()):
        ref = image + ".PRM"
        if not os.path.exists(ref):
            continue
        print(f"\n{os.path.basename(image)}")
        g = read_prm(ref)
        ours = alos2.prm(leader, image)

        print(f"  {'field':<18} {'ours':>22} {'GMTSAR':>22}   rel")
        for k, tol in COMPARE.items():
            if k not in g or k not in ours:
                print(f"  {k:<18} {'-- absent --':>22}")
                continue
            o, r = float(ours[k]), float(g[k])
            rel = abs(o - r) / max(abs(r), 1e-30)
            ok = rel <= tol
            n_ok += ok
            n_tot += 1
            print(f"  {k:<18} {o:>22.10g} {r:>22.10g}   "
                  f"{rel:.2e} {'ok' if ok else 'MISMATCH'}")

        # Fields GMTSAR has that we do not emit at all.
        missing = [k for k in ("num_lines", "num_valid_az", "nrows",
                               "num_patches", "fd1", "SC_identity")
                   if k in g and k not in ours]
        if missing:
            print(f"  not emitted by us: {missing}")

        # --- does calc_dop_orb do anything? ---------------------------------
        prm = PRM()
        prm.set(**ours)
        prm.orbit_df = alos2.orbit(leader)
        before = {k: prm.get(k) for k in ("SC_vel", "SC_height",
                                          "earth_radius", "fd1")}
        prm.calc_dop_orb(inplace=True)
        after = {k: prm.get(k) for k in before}
        changed = [k for k in before
                   if not np.isclose(float(before[k]), float(after[k]),
                                     rtol=1e-12, atol=0)]
        print(f"\n  calc_dop_orb changed: {changed or 'NOTHING'}")
        for k in before:
            print(f"    {k:<14} {float(before[k]):>18.6f} -> "
                  f"{float(after[k]):>18.6f}")
        if not changed:
            print("    -- it ran but wrote nothing; the orbit frame is "
                  "probably not being read")
        else:
            # SC_vel is the one to sanity-check: calc_dop_orb recomputes it
            # from the orbit, so agreement with GMTSAR here is independent
            # evidence that the state vectors were parsed correctly.
            if "SC_vel" in g:
                rel = abs(float(after["SC_vel"]) - float(g["SC_vel"])) \
                    / abs(float(g["SC_vel"]))
                n_ok += rel < 5e-3
                n_tot += 1
                print(f"    recomputed SC_vel vs GMTSAR: {rel:.2e} "
                      f"{'ok' if rel < 5e-3 else 'MISMATCH'}")

    print(f"\n{n_ok}/{n_tot} field comparisons within tolerance")
    return 0 if n_ok == n_tot else 1


if __name__ == "__main__":
    sys.exit(main())
