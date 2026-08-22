"""Flores co-seismic interferogram via insardev_pygmtsar -- the third chain.

GMTSAR and MintPy already agreed ring by ring to within 1 cm. This is not a
third opinion on the earthquake; all three chains consume the same two
acquisitions, so the atmosphere on 18 August 2026 is common to all of them and
no amount of agreement removes it. What a third chain tests is the PROCESSING:
insardev re-implements the GMTSAR algorithms with its own burst alignment, its
own IRLS unwrapper instead of snaphu, and its own geocoding. If a 4-7 cm step
survives that, the number is not an artefact of one code path.

Two differences from the other chains are deliberate and worth naming, because
they mean an exact match is NOT the expected outcome:

  Solid Earth tides are removed here (remove_tidal_phase=True, which needs
  GMTSAR's solid_tide binary on PATH). The GMTSAR p2p chain did not remove
  them and the MintPy run stopped before its SET step. Over a 12-day pair at
  this latitude the tidal difference is sub-centimetre, so it should shift the
  answer slightly rather than change it.

  The unwrapper is IRLS, not snaphu. On a scene that is 12.5% coherent the
  unwrapper is the single largest source of disagreement between chains, which
  is precisely why running a different one is informative.

Stages are separate and each writes to disk, so a failure late in the chain
does not cost the earlier hours:

    python3 scripts/insardev_flores_run.py --stage transform
    python3 scripts/insardev_flores_run.py --stage interferogram
    python3 scripts/insardev_flores_run.py --stage unwrap
"""

import argparse
import os
import sys

REPO = os.path.expanduser("~/GitHub/rs-change-detection")
BASE = os.path.join(REPO, "data/insardev_flores")
DATADIR = os.path.join(BASE, "data")
DEM = os.path.join(BASE, "dem.nc")
LAND = os.path.join(BASE, "land.nc")
ZARR = os.path.join(BASE, "zarr")
WORK = os.path.join(BASE, "work")
GMTSAR_BIN = os.path.expanduser("~/GMTSAR/bin")

REF, REP = "2026-08-06", "2026-08-18"
# EPSG and spacing are matched to the MintPy grid so the radial profiles can be
# compared without a resampling step in between.
EPSG = 32751
SPACING = 80


def check_disk(min_gb=4.0):
    """Abort while there is still room to abort in.

    The volume is at 99%. A transform that fills the disk does not just fail
    itself -- it corrupts whatever else is mid-write and leaves the machine
    unusable. Refusing to start is cheap; running out at hour two is not.
    """
    st = os.statvfs(BASE)
    free = st.f_bavail * st.f_frsize / 1e9
    print(f"free disk: {free:.1f} GB")
    if free < min_gb:
        sys.exit(f"under {min_gb} GB free -- refusing to start. Free space "
                 f"or move data/insardev_flores to another volume.")
    return free


def dask_client(n_workers=4):
    """Stack.load() calls dask.distributed.get_client() and raises without a
    global client. The transform stage does not need one -- it parallelises
    with joblib -- so the client is created only where it is actually
    required, keeping the transform stage free of a scheduler."""
    import logging

    from dask.distributed import Client

    logging.getLogger("distributed").setLevel(logging.CRITICAL)
    c = Client(silence_logs="CRITICAL", n_workers=n_workers,
               threads_per_worker=1, processes=False)
    print(f"dask: {c.dashboard_link if c.dashboard_link else 'in-process'}, "
          f"{n_workers} workers")
    return c


def ensure_gmtsar_path():
    """remove_tidal_phase shells out to solid_tide, which is not on PATH in a
    plain conda shell. Failing here with a clear message beats failing two
    hours in with a FileNotFoundError from a worker process."""
    if not os.path.exists(os.path.join(GMTSAR_BIN, "solid_tide")):
        sys.exit(f"no solid_tide in {GMTSAR_BIN}")
    os.environ["PATH"] = GMTSAR_BIN + os.pathsep + os.environ.get("PATH", "")


def stage_transform(a):
    from insardev_pygmtsar import S1
    from insardev_toolkit import Tiles

    check_disk()
    ensure_gmtsar_path()
    s1 = S1(DATADIR)
    df = s1.to_dataframe()
    print(f"{len(df)} bursts, paths {sorted(df.pathNumber.unique())}, "
          f"{df.flightDirection.iloc[0]}")
    dates = sorted(set(df.startTime.dt.strftime("%Y-%m-%d")))
    print(f"dates: {dates}")
    if REF not in dates or REP not in dates:
        sys.exit(f"need both {REF} and {REP}; have {dates}")
    if df.orbit.isna().any():
        sys.exit(f"{int(df.orbit.isna().sum())} bursts without an orbit")

    if not os.path.exists(DEM):
        print("downloading DEM")
        Tiles().download_dem(df, provider="GLO", filename=DEM)
    if not os.path.exists(LAND):
        # The frame is mostly ocean -- that is why frame 1153 gave 1.1%
        # coherence. Masking water before unwrapping is not cosmetic here.
        print("downloading land mask")
        Tiles().download_landmask(df, filename=LAND, product="1s")

    s1 = S1(DATADIR, DEM=DEM)
    print(f"\ntransform -> {ZARR}  epsg={EPSG} resolution=({SPACING}, "
          f"{SPACING // 4})")
    s1.transform(ZARR, ref=REF, epsg=EPSG,
                 resolution=(SPACING, SPACING // 4),
                 remove_topo_phase=True, remove_tidal_phase=True,
                 overwrite=a.overwrite, n_jobs=a.n_jobs, debug=a.debug)
    print("transform done")


def unwrap_and_los(stack, intf, corr, a):
    """Unwrap with IRLS and convert to line-of-sight metres.

    The unwrapper is the deliberate difference from the GMTSAR chain, which
    used snaphu. On a scene this incoherent the unwrapper is where two
    implementations most plausibly diverge, so this is the part of the
    comparison that carries information.
    """
    import xarray as xr

    pz = os.path.join(WORK, "phase.zarr")
    phase2d = stack.unwrap2d_dataset(intf.to_dataset(), corr.to_dataset())
    phase2d.to_zarr(pz, mode="w")
    print("unwrapped")

    # Re-open from disk instead of reusing the in-memory result. Carrying the
    # whole graph -- interferogram, Goldstein, downsample, unwrap -- into the
    # LOS write made a worker drop its dependencies and the final store failed
    # with FutureCancelledError after the expensive part had already
    # succeeded. Reading back the persisted phase truncates the graph at the
    # point that is already safe on disk, and LOS itself is only a
    # multiplication by wavelength/(4*pi).
    phase2d = xr.open_zarr(pz)
    phase = intf.from_dataset(phase2d).compute()
    los = stack.displacement_los(phase)
    return los.to_dataset().compute()


def stage_interferogram(a):
    import numpy as np
    import xarray as xr
    from insardev import Stack

    os.makedirs(WORK, exist_ok=True)
    client = dask_client(a.n_jobs)
    stack = Stack().load(ZARR)
    print(stack)

    landmask = np.isfinite(xr.open_dataarray(LAND).rio.reproject(stack.crs))

    # Stack.pairs() documents date strings but feeds its argument straight to
    # isel, so it only accepts integer indices -- the notebook's literal
    # [0, 1] was positions, not dates. Resolve the positions from the date
    # coordinate rather than hardcoding them, so this stays correct if the
    # stack ever holds more than two acquisitions.
    dates = [str(d)[:10] for d in np.asarray(stack.coords["date"])]
    print(f"stack dates: {dates}")
    try:
        pairs = [(dates.index(REF), dates.index(REP))]
    except ValueError:
        sys.exit(f"need {REF} and {REP} in the stack; have {dates}")
    print(f"pair indices: {pairs}  ({REF} -> {REP})")

    # wavelength=200 m matches filter_wavelength in the GMTSAR config, so the
    # two chains smooth by the same amount and a difference between them is
    # not just a difference in filtering.
    intf, corr = (stack.pairs(pairs)
                  .interferogram(wavelength=a.wavelength)
                  .goldstein(a.goldstein)
                  .angle())
    intf = intf.mask(landmask).downsample(SPACING).compute()
    corr = corr.mask(landmask).downsample(SPACING).compute()
    intf = intf.align().dissolve().compute()
    corr = corr.dissolve().compute()

    intf.to_dataset().to_zarr(os.path.join(WORK, "intf.zarr"), mode="w")
    corr.to_dataset().to_zarr(os.path.join(WORK, "corr.zarr"), mode="w")
    print(f"wrote {WORK}/intf.zarr and corr.zarr")

    # Unwrapping needs the intf Batch itself, not just its dataset:
    # from_dataset() maps the unwrapped single raster back onto the burst
    # structure it came from. Reloading the zarr would give a bare Dataset
    # with no way back, so the two steps stay in one process. The whole chain
    # is about a minute, so there is nothing to gain by splitting them.
    ds = unwrap_and_los(stack, intf, corr, a)
    ds.to_zarr(os.path.join(WORK, "los.zarr"), mode="w")
    var = list(ds.data_vars)[0]
    da = ds[var]
    if "pair" in da.dims:
        da = da.isel(pair=0)
    tif = os.path.join(WORK, "los.tif")
    da.rio.to_raster(tif)
    print(f"wrote {tif}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stage", required=True,
                    choices=["transform", "interferogram"])
    ap.add_argument("--wavelength", type=float, default=200.0)
    ap.add_argument("--goldstein", type=int, default=16,
                    help="Goldstein window in pixels; the signature wants an "
                         "int, not the float the notebook implies")
    ap.add_argument("--n-jobs", type=int, default=4)
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--debug", action="store_true")
    a = ap.parse_args()

    {"transform": stage_transform,
     "interferogram": stage_interferogram}[a.stage](a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
