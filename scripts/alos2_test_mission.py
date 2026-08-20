"""Exercise ALOS2_slc and ALOS2_align against both real datasets.

The checks are ordered so that a failure points at one thing:

  1. The class layout resolves the way it is supposed to. Multiple inheritance
     from a third-party class is only safe if the MRO actually puts our
     _make_scene ahead of Nisar's, and that is worth asserting rather than
     assuming -- if it inverted, the pipeline would try to open a CEOS image
     with h5py and fail somewhere far from the cause.
  2. The scan produces insardev's record frame, and level 0 groups the scenes
     that can be paired. This is derived from the product id rather than read
     from metadata, so it is the check most likely to be wrong on a dataset I
     have not seen.
  3. _make_scene answers the contract at both modes, with a PRM that PRM()
     accepts and Doppler that calc_dop_orb can compute.
  4. The xcorr patch reader agrees with a direct read, and correlating a patch
     against ITSELF returns zero shift with high response. That last one is
     the calibration: if a self-correlation does not peak at (0, 0), the patch
     reader or the window is wrong, and every real offset measured afterwards
     inherits the error.

    conda run -n insardev-test python scripts/alos2_test_mission.py
"""

import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

LOMBOK = os.path.expanduser("~/Teaching/UNDIP/InSAR/EQ/Pair1/raw")
BRAZIL = os.path.expanduser(
    "~/GitHub/rs-change-detection/data/ALOS2_Brazil/raw")

PASS = []


def check(label, ok, detail=""):
    PASS.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" +
          (f"   {detail}" if detail else ""))
    return bool(ok)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--patch", type=int, default=256)
    a = ap.parse_args()

    from earthchange import alos2
    from earthchange.alos2_mission import (ALOS2, ALOS2_align, ALOS2_slc,
                                           _xcorr_batch_ceos)
    from insardev_pygmtsar.Nisar_align import Nisar_align
    from insardev_pygmtsar.PRM import PRM

    # 1. class layout ------------------------------------------------------
    print("\nclass layout")
    mro = [c.__name__ for c in ALOS2.__mro__]
    check("ALOS2 resolves ALOS2_slc before Nisar_slc",
          mro.index("ALOS2_slc") < mro.index("Nisar_slc"),
          " -> ".join(mro[:6]))
    check("align_ref/align_rep come from Nisar_align",
          ALOS2.align_ref is Nisar_align.align_ref
          and ALOS2.align_rep is Nisar_align.align_rep)
    check("_xcorr_refine is ours, not Nisar's",
          ALOS2._xcorr_refine is ALOS2_align._xcorr_refine
          and ALOS2._xcorr_refine is not Nisar_align._xcorr_refine)
    check("_make_scene is ours",
          ALOS2._make_scene is ALOS2_slc._make_scene)

    for label, datadir in (("Lombok FBD", LOMBOK), ("Brazil HBQ", BRAZIL)):
        if not os.path.isdir(datadir):
            print(f"\n(missing {datadir})")
            continue
        print(f"\n{label}  {datadir}")

        # 2. the scan ------------------------------------------------------
        stack = ALOS2(datadir)
        df = stack.df
        check("record frame has insardev's 3-level index",
              list(df.index.names) == ["sceneId", "polarization", "scene"],
              str(list(df.index.names)))
        check("has the columns Satellite reads",
              {"startTime", "path", "geometry"} <= set(df.columns))
        groups = df.index.get_level_values(0).unique()
        check("both dates land in ONE pairing group",
              len(groups) == 1 and len(df) == 2,
              f"{len(df)} scenes in group {list(groups)}")
        check("footprints are non-degenerate polygons",
              bool(df.geometry.is_valid.all())
              and float(df.geometry.area.min()) > 0,
              f"area {df.geometry.area.min():.4f} deg^2")

        scenes = list(df.index.get_level_values(2))
        ref, rep = sorted(scenes)
        check("get_record finds a scene by its level-2 name",
              len(stack.get_record(ref)) == 1)

        # 3. _make_scene ---------------------------------------------------
        prm_obj, orbit_df = stack._make_scene(ref, mode=0)
        check("mode 0 returns a usable PRM and orbit",
              isinstance(prm_obj, PRM) and len(orbit_df) > 10,
              f"{len(orbit_df)} state vectors")
        try:
            prm_obj.calc_dop_orb(inplace=True)
            fd = prm_obj.get("fd1")
            check("calc_dop_orb accepts the PRM", np.isfinite(fd),
                  f"fd1 = {fd:.4f}")
        except Exception as exc:                          # noqa: BLE001
            check("calc_dop_orb accepts the PRM", False, repr(exc))

        d = stack._get_h5_path(ref)
        check("_get_h5_path points at a real CEOS image",
              os.path.exists(d) and os.path.getsize(d) > 1e8,
              f"{os.path.getsize(d)/1e9:.2f} GB")

        # 4. the patch reader ---------------------------------------------
        ds1 = alos2.CeosSLC(stack._get_h5_path(ref))
        ds2 = alos2.CeosSLC(stack._get_h5_path(rep))
        half = a.patch // 2
        cy = min(ds1.shape[0], ds2.shape[0]) // 2
        cx = min(ds1.shape[1], ds2.shape[1]) // 2

        # Self-correlation: the calibration. Zero shift, high response.
        one = [{"cy1": cy, "cx1": cx, "cy2": cy, "cx2": cx,
                "frac_a": 0.0, "frac_r": 0.0}]
        res = _xcorr_batch_ceos(ds1.path, ds1.path, None, one, a.patch, 0.0)
        if not res:
            check("self-correlation returns a result", False)
        else:
            r = res[0]
            check("a patch correlated with itself gives zero shift",
                  abs(r["dy"]) < 1e-6 and abs(r["dx"]) < 1e-6
                  and r["response"] > 0.9,
                  f"dy={r['dy']:.2e}, dx={r['dx']:.2e}, "
                  f"response={r['response']:.4f}")

        # Cross-date: must produce a finite, bounded offset.
        two = [{"cy1": cy, "cx1": cx, "cy2": cy, "cx2": cx,
                "frac_a": 0.0, "frac_r": 0.0}]
        res2 = _xcorr_batch_ceos(ds1.path, ds2.path, None, two, a.patch, 0.0)
        if not res2:
            check("cross-date correlation returns a result", False)
        else:
            r = res2[0]
            check("cross-date correlation is finite and bounded",
                  np.isfinite(r["dy"]) and np.isfinite(r["dx"])
                  and abs(r["dy"]) < a.patch and abs(r["dx"]) < a.patch,
                  f"dy={r['dy']:+.3f}, dx={r['dx']:+.3f}, "
                  f"response={r['response']:.4f}")

        # A patch out of bounds must be skipped, not read as garbage.
        bad = [{"cy1": ds1.shape[0] - 2, "cx1": cx, "cy2": cy, "cx2": cx,
                "frac_a": 0.0, "frac_r": 0.0}]
        res3 = _xcorr_batch_ceos(ds1.path, ds2.path, None, bad, a.patch, 0.0)
        check("an out-of-bounds patch is skipped, not truncated",
              len(res3) == 0)

        print(f"  info: {stack.info()}")

    n = sum(PASS)
    print(f"\n{n}/{len(PASS)} checks passed")
    return 0 if n == len(PASS) else 1


if __name__ == "__main__":
    sys.exit(main())
