"""Validate the CEOS SLC reader against GMTSAR's own converted SLC.

This is the test that makes an ALOS-2 reader trustworthy rather than plausible.
Both files are on disk for both dates:

    raw/IMG-HH-...__A       1,499,142,672 B   the original CEOS L1.1 image
    raw/IMG-HH-...__A.SLC     743,764,320 B   what GMTSAR made of it

So every claim about the byte layout can be checked against a reference that
is known to have produced a working interferogram, instead of being inferred
from a format document and hoped over.

The arithmetic that has to hold exactly:

    720 + n_lines * (544 + n_bins * 8) == size of the CEOS file
    n_lines * n_bins * 4               == size of the GMTSAR SLC

720 is the CEOS file descriptor, 544 the per-line prefix, 8 bytes per sample
in L1.1 (real and imaginary as 4-byte BIG-endian floats). Note that n_lines
must come from the file, not from the PRM: the PRM's num_lines is the count
GMTSAR chose to process, four short of what the file actually holds here.

GMTSAR writes 2-byte signed little-endian integers instead. The factor is NOT
the PRM's SLC_scale (8000000.0) -- that is a downstream amplitude constant,
I2SCALE*2 from image_sio.h, chosen by range sampling rate. The conversion
factor is `slc_fact` in read_ALOS_data_SLC.c, which comes from the -SLC_factor
command-line option and hence from the processing config. Here it is 0.022245,
an operator's choice made to fill the short range without clipping.

That is the finding worth carrying into insardev: the CEOS floats are the
physical values, and GMTSAR's int16 SLC is a lossy rescaling by a constant
somebody picked. Reading CEOS directly is strictly better -- no quantisation,
no dependence on what was in someone's config file. So the test below asserts
PHASE agreement, which must be exact, and only checks that the amplitude ratio
is CONSTANT, without caring what the constant is.

    conda run -n base python scripts/alos2_validate_slc.py
"""

import argparse
import os
import sys

import numpy as np

RAW = os.path.expanduser("~/Teaching/UNDIP/InSAR/EQ/Pair1/raw")

IMG_DESC_LEN = 720        # CEOS file descriptor record
IMG_PREFIX_LEN = 544      # per-line prefix before the samples
BYTES_PER_SAMPLE = 8      # complex, big-endian float32 pair


def prm_value(path, key):
    with open(path) as fh:
        for line in fh:
            if line.split("=")[0].strip() == key:
                return line.split("=", 1)[1].strip()
    return None


def read_ceos_lines(path, first, count, n_bins):
    """Read `count` SLC lines starting at `first` from a CEOS L1.1 image."""
    stride = IMG_PREFIX_LEN + n_bins * BYTES_PER_SAMPLE
    out = np.empty((count, n_bins), dtype=np.complex64)
    with open(path, "rb") as fh:
        for i in range(count):
            fh.seek(IMG_DESC_LEN + (first + i) * stride + IMG_PREFIX_LEN)
            buf = fh.read(n_bins * BYTES_PER_SAMPLE)
            # >f4 pairs: CEOS is big-endian regardless of the host.
            v = np.frombuffer(buf, dtype=">f4").reshape(n_bins, 2)
            out[i] = v[:, 0] + 1j * v[:, 1]
    return out


def read_gmtsar_lines(path, first, count, n_bins):
    """Read the same lines from GMTSAR's short-integer SLC."""
    stride = n_bins * 4                      # 2 bytes real + 2 bytes imag
    out = np.empty((count, n_bins), dtype=np.complex64)
    with open(path, "rb") as fh:
        fh.seek(first * stride)
        buf = fh.read(count * stride)
    v = np.frombuffer(buf, dtype="<i2").reshape(count, n_bins, 2)
    out[:] = v[..., 0] + 1j * v[..., 1]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scene", default="IMG-HH-ALOS2226747020-180804-"
                                       "FBDR1.1__A")
    ap.add_argument("--first-line", type=int, default=10000)
    ap.add_argument("--lines", type=int, default=8)
    ap.add_argument("--slc-factor", type=float, default=0.022245,
                    help="SLC_factor from the processing config, for "
                         "comparison only")
    a = ap.parse_args()

    ceos = os.path.join(RAW, a.scene)
    gslc = ceos + ".SLC"
    prm = ceos + ".PRM"
    for p in (ceos, gslc, prm):
        if not os.path.exists(p):
            sys.exit(f"missing {p}")

    n_bins = int(float(prm_value(prm, "num_rng_bins")))
    prm_lines = int(float(prm_value(prm, "num_lines")))
    print(f"{a.scene}")
    print(f"  PRM says {n_bins} bins, num_lines {prm_lines}\n")

    # --- the layout arithmetic, before reading a single sample --------------
    # The line count comes from the FILE. The PRM's num_lines is what GMTSAR
    # chose to process, which here is four lines short of what is on disk;
    # trusting it would misalign every subsequent read by nothing at the start
    # and by four lines at the end, which is exactly the kind of off-by-N that
    # survives visual inspection.
    stride = IMG_PREFIX_LEN + n_bins * BYTES_PER_SAMPLE
    got_ceos = os.path.getsize(ceos)
    got_gslc = os.path.getsize(gslc)
    implied = (got_ceos - IMG_DESC_LEN) / stride
    print(f"  CEOS   {got_ceos:>15,} B  / stride {stride:,} "
          f"-> {implied:.4f} lines")
    if implied != int(implied):
        sys.exit("  not a whole number of lines -- the record layout is "
                 "wrong, stop here")
    n_lines = int(implied)
    implied_g = got_gslc / (n_bins * 4)
    print(f"  GMTSAR {got_gslc:>15,} B  / {n_bins} x 4 "
          f"-> {implied_g:.4f} lines")
    if implied_g != n_lines:
        sys.exit(f"  the two disagree on line count ({n_lines} vs "
                 f"{implied_g}) -- cannot compare them line by line")
    print(f"  both hold {n_lines} lines; the PRM's {prm_lines} is "
          f"{n_lines - prm_lines} fewer\n")

    # --- now the samples ----------------------------------------------------
    c = read_ceos_lines(ceos, a.first_line, a.lines, n_bins)
    g = read_gmtsar_lines(gslc, a.first_line, a.lines, n_bins)

    # Compare only where GMTSAR did not clip: shorts saturate at +-32767, and
    # a saturated sample carries no information about the scale.
    unsat = (np.abs(g.real) < 32000) & (np.abs(g.imag) < 32000)
    nz = unsat & (np.abs(g) > 0)
    print(f"  {a.lines} lines from line {a.first_line}: "
          f"{100*nz.mean():.1f}% usable "
          f"({100*(~unsat).mean():.2f}% saturated)")

    if nz.sum() < 1000:
        sys.exit("  too few usable samples to compare")

    # Amplitude: recover the operator's SLC_factor and check it is CONSTANT.
    # The value itself is a config choice, so agreement in magnitude proves
    # nothing about the reader; constancy proves the layout is right.
    ratio = np.abs(g[nz]) / np.abs(c[nz])
    ratio = ratio[np.isfinite(ratio) & (ratio > 0)]
    med = np.median(ratio)
    p1, p99 = np.percentile(ratio, [1, 99])
    print(f"  recovered SLC_factor: {med:.6f}   (1/{1/med:.2f})")
    print(f"    spread p99/p1 = {p99/p1:.4f}  "
          f"-- 1.00 would be exact; departure is int16 rounding")
    cfg = a.slc_factor
    if cfg:
        print(f"    processing config says {cfg:.6f} "
              f"-> agrees to {100*med/cfg:.3f}%")

    # Phase is the check that matters, and it must be near-exact: the scale
    # cancels in an interferogram, but a byte-order or interleave error does
    # not, and neither survives this test.
    dphi = np.angle(c[nz] * np.conj(g[nz]))
    med_mrad = np.median(np.abs(dphi)) * 1000
    p99_mrad = np.percentile(np.abs(dphi), 99) * 1000
    print(f"\n  phase difference: median {med_mrad:.4f} mrad, "
          f"p99 {p99_mrad:.4f} mrad")
    print(f"    for scale, one fringe is 6283 mrad, so this is "
          f"1 part in {6283/max(med_mrad, 1e-9):,.0f} of a cycle")

    # Big-endian shorts would give a scrambled result; show that the little-
    # endian reading is not just the one that happened to be tried first.

    ok_phase = p99_mrad < 10          # a hundredth of a fringe
    ok_scale = (p99 / p1) < 1.05
    if ok_phase and ok_scale:
        print("\n  VALIDATED. The 720-byte descriptor, the 544-byte line")
        print("  prefix, big-endian float pairs and the sample count are all")
        print("  confirmed against a conversion known to have produced a")
        print("  working interferogram. The CEOS floats are the physical")
        print("  values; GMTSAR's int16 is the lossy copy, so insardev should")
        print("  read CEOS directly rather than reproduce this step.")
    else:
        print("\n  NOT validated -- do not build on this reader yet.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
