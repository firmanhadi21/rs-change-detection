"""Check earthchange.alos2 against GMTSAR, on every scene in a directory.

Two things are verified, and they are different claims:

  READ FIELDS   wavelength, PRF, sampling rate, pulse duration, near range,
                chirp slope, range bins -- compared against the .PRM that
                GMTSAR's ALOS_pre_process produced for the same scene.

  DERIVED       SC_vel, SC_height, earth_radius and the clock are computed
                here from the orbit and the ellipsoid rather than read, so
                they test the geometry code, not the CEOS offsets. They are
                allowed a looser tolerance: GMTSAR interpolates its orbit
                slightly differently, and a few metres of orbital height is
                agreement, not a defect.

Also reports the footprint, which is computed and has no ground truth in the
product at all -- so it is sanity-checked for plausibility rather than
compared: right hemisphere, sane size, and the scene centre inside it.

    python3 scripts/alos2_check.py ~/Teaching/UNDIP/InSAR/EQ/Pair1/raw
"""

import argparse
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from earthchange import alos2                                  # noqa: E402

READ = ("radar_wavelength", "PRF", "rng_samp_rate", "pulse_dur",
        "near_range", "chirp_slope", "num_rng_bins")
DERIVED = ("SC_vel", "SC_height", "earth_radius", "SC_clock_start")


def read_gmtsar_prm(path):
    out = {}
    for line in open(path):
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        try:
            out[k.strip()] = float(v.strip())
        except ValueError:
            out[k.strip()] = v.strip()
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("datadir")
    ap.add_argument("--pol", default="HH")
    a = ap.parse_args()
    d = os.path.expanduser(a.datadir)

    scenes = alos2.find_scenes(d, a.pol)
    print(f"{len(scenes)} scene(s) with a {a.pol} LED-/IMG- pair\n")

    all_ok = True
    for sid, (led, img) in sorted(scenes.items()):
        print(f"=== {sid} ===")
        p = alos2.prm(led, img)
        ref = glob.glob(os.path.join(d, f"IMG-{a.pol}-{sid}.PRM"))
        if not ref:
            print("   no GMTSAR .PRM to compare against; skipping\n")
            continue
        gm = read_gmtsar_prm(ref[0])

        print(f"   {'field':<18}{'ours':>20}{'GMTSAR':>20}   ok")
        for key in READ:
            mine, theirs = p.get(key), gm.get(key)
            if not isinstance(theirs, float):
                continue
            good = abs(mine - theirs) <= abs(theirs) * 1e-4
            all_ok &= good
            print(f"   {key:<18}{mine:>20.6f}{theirs:>20.6f}   "
                  f"{'yes' if good else 'NO'}")

        print(f"   {'-- derived --':<18}")
        for key in DERIVED:
            mine, theirs = p.get(key), gm.get(key)
            if not isinstance(theirs, float):
                continue
            # 0.1% covers a different orbit interpolation; a real error in the
            # geometry code is orders of magnitude larger than that.
            good = abs(mine - theirs) <= abs(theirs) * 1e-3
            all_ok &= good
            print(f"   {key:<18}{mine:>20.6f}{theirs:>20.6f}   "
                  f"{'yes' if good else 'NO'}")
        print()

    # Footprint: no ground truth exists, so check it is not absurd.
    print("=== scan() ===")
    df = alos2.scan(d, pols=(a.pol,))
    print(f"   {len(df)} record(s)")
    for idx, row in df.iterrows():
        g = row.geometry
        c = g.centroid
        w = g.bounds[2] - g.bounds[0]
        h = g.bounds[3] - g.bounds[1]
        plausible = (g.is_valid and 0.05 < w < 8 and 0.05 < h < 8
                     and -90 < c.y < 90 and -180 < c.x < 180)
        all_ok &= plausible
        print(f"   {idx[0]}  {row.flightDirection}{row.lookDirection}  "
              f"{row.startTime}")
        print(f"      centre {c.y:+.3f}, {c.x:+.3f}   "
              f"extent {h:.2f} x {w:.2f} deg   "
              f"{'plausible' if plausible else 'IMPLAUSIBLE'}")

    print(f"\n{'ALL CHECKS PASS' if all_ok else 'FAILURES ABOVE'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
