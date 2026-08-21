"""Geocoding ALOS-2 through insardev's transform, without copying it.

THE PROBLEM. transform() ends in a ProcessPoolExecutor over
_process_chunk_nisar, and that chunk worker reads its SLC window with

    nisar_slc(h5_path, pol=pol, frequency=frequency, row_slice=, col_slice=)

which is HDF5-only. Three things make this harder to redirect than the xcorr
case was:

  * the executor is created with mp_context='spawn', so nothing monkeypatched
    in the parent survives into the workers -- each is a fresh interpreter;
  * _process_chunk_nisar is a module-level function called by name from
    _transform_slc_int16_nisar_chunked, which is itself called by name from
    transform(), so a subclass cannot redirect any of them;
  * copying that chain to change one line means reproducing roughly 730 lines
    that would then drift from upstream.

THE LEVER. _process_chunk_nisar does its import INSIDE the function body:

    def _process_chunk_nisar(...):
        ...
        from .utils_nisar import nisar_slc

`from X import Y` reads the attribute off the module object at call time. So a
patch applied in the WORKER process, before delegating to the untouched
upstream function, is picked up -- and the worker is where we can reach,
because a spawned worker unpickles the callable by its own module path. Swap
the one module global the parent passes to executor.map and the workers import
this module instead, patch themselves, and call upstream's chunk code
verbatim.

That reduces the reproduced code to the six-line worker below. Everything that
does real work -- the remap, the topographic and tidal phase, the int16
quantisation, the zarr writes -- stays upstream's.

The parent-side swap is global to the process, so it is scoped to a context
manager and restored afterwards; NISAR processing in the same session is
unaffected outside the with-block.

STATUS: RUNS, BUT THE OUTPUT IS NOT YET INTERFEROMETRICALLY USABLE. Read this
before building on it.

The redirect works -- both dates geocode, 69% coverage, and the two land on
the map grid registered to 0.02 px. What does not work is the phase: against
GMTSAR's interferogram for the same pair, agreement is 0.001 where chance is
0.001.

What that is NOT, established rather than assumed:

  * not the reader or the alignment. alos2_radar_coherence.py forms the
    interferogram in RADAR coordinates with the alignment we validated against
    GMTSAR to 0.005 px and gets median coherence 0.296 with 28% above 0.4,
    while the same test with a deliberate 20 px shift collapses to 0.148 --
    the noise floor for 64 looks. The SLCs are good and the offsets are right.
  * not the registration. alos2_check_geocoded_shift.py cross-correlates the
    two GEOCODED amplitude images: peak at dx +0.023, dy -0.002 px.
  * not output resolution, though that was one real error along the way.
    resolution=(30, 30) aliases 4 m speckle and decorrelates the pair; (8, 16)
    fixes that and lifts coherence to 20.7% above 0.3, close to GMTSAR's
    22.5%. But be careful with that number -- see below.

Three defects in this build's NISAR topographic-phase path, each of which hid
the next, all fixed or worked around above:

  1. _process_chunk_nisar reads topo from outdir/topo while
     compute_conversion_chunked writes it to outdir/conversion/topo, and the
     read is guarded by os.path.exists, so the correction was silently skipped
     -- with and without remove_topo_phase the output was byte-identical.
  2. flat_earth_topo_phase gained a fourth positional argument for S1; all
     three Nisar_transform call sites still use the old signature and raise
     TypeError once (1) is fixed.
  3. tidal_phase_radar needs prm_ref.orbit_df, but the chunk worker rebuilds
     its PRMs from dicts and never restores the orbit, so it is None. Worked
     around by passing remove_tidal_phase=False, which is also the more
     like-for-like setting against GMTSAR, since GMTSAR does not remove tides
     either.

With all three handled the topo correction runs, and the phase is still noise.
So there is a fourth problem, and it is most likely in how the topographic and
flat-earth phase is being computed or applied rather than in whether it runs.

A caution about the coherence number, because it misled me: at 6x3 = 18 looks
the estimator returns E|gamma| ~ sqrt(pi/4N) ~ 0.21 for ZERO true coherence.
Our "20.7% above 0.3" was the estimator's bias, not signal -- visible because
the same 0.2 appears over open water, where coherence must be zero. Judge this
against a picture and a noise floor, never against a bare median.
"""

import contextlib
import os

from .alos2_mission import ALOS2_align

try:
    from insardev_pygmtsar import Nisar_transform as _nt_module
    from insardev_pygmtsar.Nisar_transform import Nisar_transform
except ImportError as exc:                                # pragma: no cover
    raise ImportError(
        "needs insardev_pygmtsar; run under the insardev-test env"
    ) from exc

for _needed in ("_process_chunk_nisar", "_process_chunk_nisar_worker"):
    if not hasattr(_nt_module, _needed):
        raise ImportError(
            f"insardev_pygmtsar.Nisar_transform has no {_needed}; the chunk "
            f"worker this module redirects has been renamed or removed")


def _link_topo(outdir):
    """Put the topo group where the chunk worker expects to find it.

    _process_chunk_nisar reads two zarr groups out of `outdir`:

        os.path.join(outdir, 'transform')     exists
        os.path.join(outdir, 'topo')          does NOT

    because compute_conversion_chunked writes the second one to
    outdir/conversion/topo. The worker guards that read with
    `if os.path.exists(topo_path)`, so the mismatch does not raise -- it
    silently skips the flat-earth and topographic phase correction, which is
    precisely what makes a resampled pair interferometrically coherent.

    The symptom is diagnostic and worth recording: the geocoded dates register
    to 0.02 px on the map grid, so the geometry is right, while the phase is
    noise at every scale. Amplitude survives, phase does not. Left uncorrected,
    the differential range term alone runs to a fringe every few hundred
    metres, which decorrelates the pair at any sensible look size and reads as
    "the data is bad".

    Linking rather than copying, and only when the expected path is absent and
    the alternative is present, so this becomes a no-op the moment upstream
    agrees with itself.
    """
    want = os.path.join(outdir, "topo")
    have = os.path.join(outdir, "conversion", "topo")
    if os.path.exists(want) or not os.path.exists(have):
        return
    try:
        os.symlink(have, want)
    except FileExistsError:            # another worker won the race
        pass


def _ceos_chunk_worker(args):
    """Runs in a spawned worker: fix up what it needs, then hand off untouched.

    Patching utils_nisar in here is process-local -- this interpreter exists
    to do one chunk and exit (max_tasks_per_child=1) -- so it cannot leak into
    anything else. The signature of read_slc is deliberately identical to
    nisar_slc's, including the pol and frequency arguments it does not need,
    so the call inside _process_chunk_nisar needs no adaptation.
    """
    import numpy as np
    import insardev_pygmtsar.utils_nisar as utils_nisar
    import insardev_pygmtsar.utils_satellite as utils_satellite
    from insardev_pygmtsar.Nisar_transform import _process_chunk_nisar

    from earthchange import alos2

    utils_nisar.nisar_slc = alos2.read_slc

    # flat_earth_topo_phase takes earth_radius_azi as its fourth POSITIONAL
    # argument -- a per-azimuth-line geocentric radius, added so Sentinel-1
    # bursts with different scalar earth_radius values do not leave phase ramps
    # at their seams. S1_transform passes it; all three call sites in
    # Nisar_transform still use the old signature and raise TypeError. That is
    # an upstream regression, and it is invisible in this build because the
    # outdir/topo path mismatch above means the call is never reached.
    #
    # A stripmap scene has ONE earth_radius, so the correct value is a constant
    # array rather than a stand-in: there are no bursts for it to vary across.
    original = utils_satellite.flat_earth_topo_phase

    def _with_earth_radius(topo, prm_rep, prm_ref, *args, **kwargs):
        if args:                       # caller already supplied it
            return original(topo, prm_rep, prm_ref, *args, **kwargs)
        n = topo.shape[0] if topo is not None else 1
        er = np.full(n, float(prm_ref.get("earth_radius")), dtype=np.float64)
        return original(topo, prm_rep, prm_ref, er, **kwargs)

    utils_satellite.flat_earth_topo_phase = _with_earth_radius

    # args[6] is outdir; see the chunk_args tuple in
    # _transform_slc_int16_nisar_chunked.
    _link_topo(args[6])
    return _process_chunk_nisar(*args)


@contextlib.contextmanager
def ceos_chunk_workers():
    """Point insardev's chunk executor at the CEOS worker for this block."""
    original = _nt_module._process_chunk_nisar_worker
    _nt_module._process_chunk_nisar_worker = _ceos_chunk_worker
    try:
        yield
    finally:
        _nt_module._process_chunk_nisar_worker = original


class ALOS2_transform(ALOS2_align, Nisar_transform):
    """transform() with the chunk reader redirected to CEOS."""

    def transform(self, *args, **kwargs):
        with ceos_chunk_workers():
            return super().transform(*args, **kwargs)


class ALOS2(ALOS2_transform):
    """ALOS-2 PALSAR-2 L1.1: scan, align and geocode.

        from earthchange.alos2_transform import ALOS2
        a = ALOS2('.../raw', DEM='.../dem.grd')
        a.transform('stack.zarr', ref='2018-05-12')
    """

    def info(self):
        if self.df is None or len(self.df) == 0:
            return {"error": "No data loaded"}
        dates = self.df.startTime.dt.date.unique()
        return {
            "n_scenes": len(self.df),
            "n_dates": len(dates),
            "date_range": (str(min(dates)), str(max(dates))),
            "groups": sorted(self.df.index.get_level_values(0).unique()),
            "polarizations":
                sorted(self.df.index.get_level_values(1).unique()),
        }
