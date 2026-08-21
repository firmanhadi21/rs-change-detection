"""Is the decorrelation introduced by the transform, or already in the SLCs?

The geocoded stack is noise everywhere, including over water, and its
"coherence" sits at a uniform 0.2 -- which is what an 18-look estimator
returns for ZERO true coherence, since E[|gamma_hat|] ~ sqrt(pi/4N). So the
20.6%-above-0.3 that looked like agreement with GMTSAR was the estimator's
bias, not signal.

That leaves two possibilities and this script separates them. Take the two
CEOS SLCs directly, apply the alignment we already validated against GMTSAR to
0.005 px, form the interferogram in RADAR coordinates, and measure coherence
over a small window:

  * good coherence here  -> the reader and the alignment are fine, and the
    transform is destroying the phase;
  * noise here           -> something more fundamental, and the alignment
    agreeing with GMTSAR is not enough, because xcorr matches AMPLITUDE and
    would be unmoved by a phase that is being mangled.

The window is small (8x8) on purpose: coherence must be estimated over an area
where the true phase is roughly constant. Estimating it over a window that
spans several topographic fringes measures the fringes, not the correlation,
and reports decorrelation that is not there.

    conda run -n insardev-test python scripts/alos2_radar_coherence.py
"""

import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RAW = os.path.expanduser("~/Teaching/UNDIP/InSAR/EQ/Pair1/raw")

# From GMTSAR's aligned PRM, independently reproduced by our align_rep.
RSHIFT, ASHIFT = -31.3246, 7.7519
STRETCH_R, STRETCH_A = -1.95194e-04, -5.30903e-05


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--size", type=int, default=1024)
    ap.add_argument("--window", type=int, default=8)
    ap.add_argument("--centre", type=int, nargs=2, default=None,
                    help="line, bin. Default: middle of the swath")
    a = ap.parse_args()

    import cv2
    from earthchange import alos2

    scenes = sorted(alos2.find_scenes(RAW, pol="HH").items())
    (_, (_, img_ref)), (_, (_, img_rep)) = scenes[0], scenes[1]
    ds_ref = alos2.CeosSLC(img_ref)
    ds_rep = alos2.CeosSLC(img_rep)
    print(f"ref {os.path.basename(img_ref)}  {ds_ref.shape}")
    print(f"rep {os.path.basename(img_rep)}  {ds_rep.shape}")

    if a.centre:
        cy, cx = a.centre
    else:
        cy = min(ds_ref.shape[0], ds_rep.shape[0]) // 2
        cx = min(ds_ref.shape[1], ds_rep.shape[1]) // 2
    h = a.size // 2
    print(f"patch {a.size}x{a.size} at line {cy}, bin {cx}\n")

    ref = ds_ref[cy - h:cy + h, cx - h:cx + h]

    # Where each reference pixel lands in the secondary, from the bilinear
    # model. Read a margin around it so the interpolator has support.
    yy, xx = np.mgrid[cy - h:cy + h, cx - h:cx + h].astype(np.float64)
    ry = yy + ASHIFT + STRETCH_A * xx
    rx = xx + RSHIFT + STRETCH_R * xx
    y0, y1 = int(np.floor(ry.min())) - 4, int(np.ceil(ry.max())) + 4
    x0, x1 = int(np.floor(rx.min())) - 4, int(np.ceil(rx.max())) + 4
    rep_block = ds_rep[y0:y1, x0:x1]

    # Interpolate the COMPLEX secondary. Real and imaginary parts are
    # interpolated separately, which is correct only because both are smooth
    # at the sampling rate -- interpolating amplitude and angle instead would
    # wrap and is always wrong.
    mr = (rx - x0).astype(np.float32)
    ma = (ry - y0).astype(np.float32)
    rep = (cv2.remap(rep_block.real.astype(np.float32), mr, ma,
                     cv2.INTER_LANCZOS4, borderValue=np.nan)
           + 1j * cv2.remap(rep_block.imag.astype(np.float32), mr, ma,
                            cv2.INTER_LANCZOS4, borderValue=np.nan))

    for label, sec in (("aligned", rep),
                       ("deliberately misaligned by 20 px", np.roll(rep, 20,
                                                                    axis=1))):
        ifg = ref * np.conj(sec)
        w = a.window
        ny, nx = (ifg.shape[0] // w) * w, (ifg.shape[1] // w) * w

        def blk(arr):
            return arr[:ny, :nx].reshape(ny // w, w, nx // w, w)

        with np.errstate(invalid="ignore"):
            num = np.nanmean(blk(ifg), axis=(1, 3))
            d0 = np.nanmean(blk(np.abs(ref) ** 2), axis=(1, 3))
            d1 = np.nanmean(blk(np.abs(sec) ** 2), axis=(1, 3))
            coh = np.abs(num) / np.sqrt(d0 * d1)
        c = coh[np.isfinite(coh)]
        # An N-look estimator returns about sqrt(pi/(4N)) on pure noise, so
        # quote it alongside -- a median at the floor means no signal.
        floor = np.sqrt(np.pi / (4 * w * w))
        print(f"  {label:<34} median {np.median(c):.3f}   "
              f"{100*np.mean(c > 0.4):.1f}% above 0.4   "
              f"(noise floor for {w*w} looks ~{floor:.3f})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
