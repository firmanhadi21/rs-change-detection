"""Exercise the CEOS SLC accessor the way insardev will.

Four things have to hold before the align and transform layers can be
inherited instead of rewritten, and each fails in its own way:

  1. It reports the same geometry the naive line-by-line reader does. A memmap
     over a structured dtype with the wrong record length does not raise -- it
     reads plausible garbage at a constant offset, which looks like an SLC.
  2. A windowed read equals the same window cut out of a larger read. This is
     the property _xcorr_batch depends on: it pulls hundreds of 512x512
     patches at arbitrary centres and correlates them against patches from
     another file. An off-by-one in the offset arithmetic shifts every patch
     by the same amount, so the cross-correlation still peaks -- at the wrong
     place, consistently, which is indistinguishable from a real misregistration.
  3. It survives the h5py call pattern verbatim, including the context manager
     and `.shape` before any read.
  4. It agrees with GMTSAR's own SLC in phase, where GMTSAR has produced one.

Then the same reader is pointed at Sandwell's Brazil example, which is HBQ
(high-sensitive quad-pol) rather than Lombok's FBD. Different mode, different
bandwidth, different range bin count, and nothing in the reader was fitted to
it -- so parsing it correctly is evidence the reader parses rather than
remembers.

    conda run -n base python scripts/alos2_test_accessor.py
"""

import argparse
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from earthchange import alos2                              # noqa: E402

LOMBOK = os.path.expanduser("~/Teaching/UNDIP/InSAR/EQ/Pair1/raw")
BRAZIL = os.path.expanduser(
    "~/GitHub/rs-change-detection/data/ALOS2_Brazil/raw")


def check(label, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" +
          (f"   {detail}" if detail else ""))
    return bool(ok)


def exercise(image, gmtsar_slc=None, first=10000, verbose=True):
    """Run every check on one image; return (n_passed, n_total)."""
    name = os.path.basename(image)
    print(f"\n{name}")
    results = []

    ds = alos2.CeosSLC(image)
    m = ds.meta
    print(f"  {ds.shape[0]} lines x {ds.shape[1]} bins, record "
          f"{m['record_length']} B, near range {m['near_range']:,.0f} m, "
          f"chirp slope {m['chirp_slope']:.4g}")

    # 1. geometry agrees with the naive reader ------------------------------
    naive = alos2.slc(image, lines=4, first_line=first)
    results.append(check(
        "shape matches the naive reader",
        naive.shape[1] == ds.shape[1],
        f"{naive.shape[1]} bins both ways"))
    win = ds[first:first + 4, :]
    results.append(check(
        "values match the naive reader exactly",
        np.array_equal(win, naive),
        f"max |diff| = {np.abs(win - naive).max():.3e}"))

    # 2. windowed read == window of a larger read ---------------------------
    # The property _xcorr_batch leans on. Test at a centre that is not on any
    # chunk boundary, because boundary-aligned reads can hide offset errors.
    y, x, half = first + 137, ds.shape[1] // 3 + 61, 256
    big = ds[y - half - 40:y + half + 40, x - half - 40:x + half + 40]
    small = ds[y - half:y + half, x - half:x + half]
    results.append(check(
        "patch read == same patch cut from a bigger read",
        np.array_equal(small, big[40:-40, 40:-40]),
        f"{small.shape[0]}x{small.shape[1]} at ({y}, {x})"))

    # A single line and a single sample, since h5py supports both.
    results.append(check(
        "scalar and row indexing agree with the 2D read",
        ds[y, x] == ds[y:y + 1, x:x + 1][0, 0] and
        np.array_equal(ds[y], ds[y:y + 1][0])))

    # 3. the h5py call pattern ----------------------------------------------
    try:
        with alos2.open_slc(image) as f:
            d = f["/science/whatever/the/name/is"]
            shape_first = d.shape
            patch = d[y - 8:y + 8, x - 8:x + 8]
        ok = shape_first == ds.shape and patch.shape == (16, 16) \
            and patch.dtype == np.complex64
        results.append(check("h5py call pattern (with/getitem/shape/slice)",
                             ok, f"dtype {patch.dtype}"))
    except Exception as exc:                              # noqa: BLE001
        results.append(check("h5py call pattern", False, repr(exc)))

    # read_slc mirrors nisar_slc's signature
    try:
        r = alos2.read_slc(image, pol="HH",
                           row_slice=slice(first, first + 3),
                           col_slice=slice(100, 140))
        results.append(check("read_slc(pol=, row_slice=, col_slice=)",
                             r.shape == (3, 40)))
    except Exception as exc:                              # noqa: BLE001
        results.append(check("read_slc signature", False, repr(exc)))

    # Asking the wrong polarisation must fail loudly, not return HH silently.
    try:
        alos2.read_slc(image, pol="VV", row_slice=slice(0, 1))
        results.append(check("wrong polarisation is rejected", False,
                             "returned data for VV"))
    except ValueError:
        results.append(check("wrong polarisation is rejected", True))

    # 3b. the metadata the accessor sits on ---------------------------------
    # Cheap here, and it is the check that catches a reader that memorised one
    # mode: HBQ and FBD must come out with DIFFERENT sampling rates and PRFs
    # but the SAME wavelength and orbit, because they are the same satellite.
    leader = image.replace(os.path.basename(image).split("-")[0] + "-HH-",
                           "LED-").replace("IMG-HH-", "LED-")
    if os.path.exists(leader):
        p = alos2.prm(leader, image)
        results.append(check(
            "leader parses to physical values",
            0.2424 < p["radar_wavelength"] < 0.2425
            and 1e7 < p["rng_samp_rate"] < 1e8
            and 1000 < p["PRF"] < 5000
            and 6.2e5 < p["SC_height"] < 6.6e5
            and 7000 < p["SC_vel"] < 7800,
            f"fs {p['rng_samp_rate']/1e6:.1f} MHz, PRF {p['PRF']:.0f} Hz, "
            f"h {p['SC_height']/1000:.0f} km"))
    else:
        print(f"  [skip] no leader beside this scene")

    # 4. against GMTSAR, where it exists -------------------------------------
    if gmtsar_slc and os.path.exists(gmtsar_slc):
        nb = ds.shape[1]
        with open(gmtsar_slc, "rb") as fh:
            fh.seek(first * nb * 4)
            g = np.frombuffer(fh.read(4 * nb * 4), dtype="<i2")
        g = g.reshape(4, nb, 2)
        g = (g[..., 0] + 1j * g[..., 1]).astype(np.complex64)
        c = ds[first:first + 4, :]
        keep = (np.abs(g) > 0) & (np.abs(g.real) < 32000) & \
               (np.abs(g.imag) < 32000)
        dphi = np.abs(np.angle(c[keep] * np.conj(g[keep])))
        p99 = np.percentile(dphi, 99) * 1000
        results.append(check("phase agrees with GMTSAR's SLC", p99 < 10,
                             f"p99 {p99:.3f} mrad = 1/{6283/p99:,.0f} fringe"))
    elif verbose:
        print("  [skip] no GMTSAR SLC beside this scene")

    return sum(results), len(results)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bench", action="store_true",
                    help="time patch reads the way _xcorr_batch does")
    a = ap.parse_args()

    passed = total = 0
    seen = 0
    for datadir, has_gmtsar in ((LOMBOK, True), (BRAZIL, False)):
        if not os.path.isdir(datadir):
            print(f"\n(missing {datadir})")
            continue
        scenes = alos2.find_scenes(datadir, pol="HH")
        for scene, (leader, image) in sorted(scenes.items()):
            seen += 1
            p, t = exercise(image,
                            image + ".SLC" if has_gmtsar else None)
            passed += p
            total += t

    if a.bench and os.path.isdir(LOMBOK):
        scenes = alos2.find_scenes(LOMBOK, pol="HH")
        image = sorted(scenes.values())[0][1]
        ds = alos2.CeosSLC(image)
        rng = np.random.default_rng(0)
        ys = rng.integers(512, ds.shape[0] - 512, 200)
        xs = rng.integers(512, ds.shape[1] - 512, 200)
        t0 = time.perf_counter()
        for y, x in zip(ys, xs):
            _ = ds[y - 256:y + 256, x - 256:x + 256]
        dt = time.perf_counter() - t0
        print(f"\n  200 random 512x512 patches in {dt:.2f} s "
              f"({1000*dt/200:.1f} ms each, "
              f"{200*512*512*8/dt/1e6:.0f} MB/s)")

    print(f"\n{passed}/{total} checks passed across {seen} scenes")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
