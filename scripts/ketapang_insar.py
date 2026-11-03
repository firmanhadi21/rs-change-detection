#!/usr/bin/env python3
"""Peat subsidence on the Ketapang coast before the 2026 fire: Sentinel-1 SBAS
with InSAR.dev (insardev_pygmtsar + insardev), following the working Semarang
notebook in ../pygmtsar (PyGMTSAR_Land_subsidence_Semarang_2024_2026_insardev-rev)
and its snippets (SSD dask client, sign check).

WHY. Drained peat sinks: canals lower the water table, the exposed peat
oxidises and compacts, typically 2-5 cm a year. Subsidence is therefore the
physical trace of drainage, which the excess-burn analysis
(ketapang_excess_burn.py) points to as the reason the four concessions burned
more than comparable land outside. This measures it, inside and outside.

WHAT.  Track 149 descending (frame 598) covers all four concessions with
       ~12-day repeats. Bursts only over the AOI, VV.
       Period 2024-01-01 .. 2026-06-30: pre-fire, so the 2026 burn (sudden
       peat loss + decorrelation) does not mix with the drainage rate. The
       2023 fire season (Aug-Oct 2023) is before it.
       SBAS pairs <= BASEDAYS days: C-band over vegetated peat decorrelates
       within weeks, so long pairs only add noise (Semarang used 100 days on
       a city).
       400 m Gaussian + Goldstein, 60 m output, IRLS unwrapping on the merged
       bursts, coherence-weighted plane per pair for ramps, fit1d for the
       linear rate. Vertical = LOS / cos(incidence): one geometry only, so
       horizontal motion is assumed zero, which holds for peat subsidence.
       Reference: the median of high-coherence MINERAL-soil pixels (neither
       peat map calls them peat), since InSAR rates are relative.

STAGES (each writes to disk; run in order):
    search     free: bursts and dates over the AOI, volume estimate
    fetch      bursts + orbits + DEM (Earthdata login from ~/.netrc,
               straight to ASF, not the insar.dev cache proxy)
    transform  align and geocode bursts into a Zarr stack
    sbas       interferograms, unwrapping, velocity -> GeoTIFFs
    analyze    rates by zone / peat / canal density, SKM boundary transect

    conda run -n insardev python scripts/ketapang_insar.py --stage search

LICENCE. insardev is under InSARdev-SAL-1.0: funded academic, institutional
or professional use needs a subscription (see the InSARdev repository).
"""

import argparse
import json
import netrc
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SSD_ROOT = "/Volumes/ExtremeSSD/Dropbox/GitHub/rs-change-detection"
_DATA_ROOT = (os.environ.get("RSCD_DATA_ROOT")
              or (_SSD_ROOT if os.path.isdir(_SSD_ROOT) else _REPO_ROOT))
BASE = os.path.join(_DATA_ROOT, "data", "insar_ketapang")
DATADIR = os.path.join(BASE, "data")
DEM = os.path.join(DATADIR, "dem.nc")          # the downloader writes dem.vrt
LAND = os.path.join(DATADIR, "land.vrt")
ZARRDIR = os.path.join(BASE, "zarr")
WORK = os.path.join(BASE, "work")
OUT = os.path.join(_DATA_ROOT, "output", "fire", "ketapang_origin", "insar")
SCRATCH = "/Volumes/ExtremeSSD/insar/dask-scratch"

# the four concessions plus the undrained dome NW of SKM/SPAS and mineral land
AOI_BOX = (110.00, -2.10, 110.58, -1.45)
ORBIT, PATH, POL = "D", 149, "VV"
START, END = "2024-01-01", "2026-06-30"
BASEDAYS, BASEMETERS = 48, 150
FILTER_M, GOLDSTEIN_M, SPACING = 400, 200, 60
EARTHDATA = "urs.earthdata.nasa.gov"
BURST_MB = 140                                 # VV burst SLC, typical


def aoi():
    import geopandas as gpd
    import shapely
    return gpd.GeoDataFrame(geometry=[shapely.geometry.box(*AOI_BOX)], crs=4326)


def search_bursts():
    import pandas as pd
    from insardev_toolkit import ASF
    b = ASF.search(aoi(), startTime=START, stopTime=END, flightDirection=ORBIT,
                   polarization=POL)
    b = b[b["pathNumber"].astype(int) == PATH]
    b = b[b["sceneName"].str.contains(f"_{POL}_")].reset_index(drop=True)
    return b


def creds():
    auth = netrc.netrc().authenticators(EARTHDATA)
    if not auth:
        sys.exit(f"no {EARTHDATA} entry in ~/.netrc")
    return auth[0], auth[2]


def check_disk(need_gb):
    os.makedirs(BASE, exist_ok=True)
    st = os.statvfs(BASE)
    free = st.f_bavail * st.f_frsize / 1e9
    print(f"free disk: {free:.0f} GB (need ~{need_gb:.0f} GB)")
    if free < need_gb * 1.3:
        sys.exit("not enough free disk -- refusing to start")


def dask_client():
    """The SSD snippet: 2 x 9 GB workers on a 24-26 GB Apple Silicon Mac;
    4 x 5 GB workers were killed in align/dissolve."""
    import logging
    import dask
    from dask.distributed import Client
    os.makedirs(SCRATCH, exist_ok=True)
    dask.config.set({"temporary-directory": SCRATCH})
    logging.getLogger("distributed").setLevel(logging.CRITICAL)
    c = Client(silence_logs="CRITICAL", n_workers=2, threads_per_worker=1,
               memory_limit="9GB", resources={"gpu": 1}, local_directory=SCRATCH)
    print(f"dask: {c}")
    return c


# ------------------------------------------------------------------ stages
def stage_search(a):
    import pandas as pd
    b = search_bursts()
    dates = pd.to_datetime(b.startTime).dt.date
    ids = sorted(b.fullBurstID.unique())
    per = b.groupby("fullBurstID").size()
    print(f"{len(b)} bursts, {dates.nunique()} dates, {len(ids)} burst IDs "
          f"({sorted(b.fullBurstID.str[-3:].unique())})")
    print(per.to_string())
    gb = len(b) * BURST_MB / 1000
    print(f"download ~{gb:.0f} GB; Zarr stack adds roughly the same again")
    os.makedirs(BASE, exist_ok=True)
    b.drop(columns=[c for c in b.columns if c == "geometry"]).to_csv(
        os.path.join(BASE, "bursts.csv"), index=False)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from insardev_toolkit import ASF
        ASF.plot(b)
        aoi().boundary.plot(ax=plt.gca(), color="red")
        os.makedirs(OUT, exist_ok=True)
        plt.savefig(os.path.join(OUT, "bursts.png"), dpi=120)
        print(f"Saved: {os.path.join(OUT, 'bursts.png')}")
    except Exception as e:                           # noqa: BLE001
        print(f"(burst plot skipped: {e})")


def stage_fetch(a):
    from insardev_toolkit import ASF, EOF, Tiles
    from insardev_pygmtsar import S1
    b = search_bursts()
    check_disk(2 * len(b) * BURST_MB / 1000)
    user, pwd = creds()
    print(f"authenticating to ASF as {user}")
    os.makedirs(DATADIR, exist_ok=True)
    # S1 scanning raises on XML from a parallel-download race: keep n_jobs modest
    print(ASF(user, pwd).download(DATADIR, b, n_jobs=a.n_jobs))
    s1 = S1(DATADIR)
    EOF().download(DATADIR, s1.to_dataframe())
    if not (os.path.exists(DEM) or os.path.exists(DEM.replace(".nc", ".vrt"))):
        Tiles().download_dem(s1.to_dataframe(), provider="GLO", filename=DEM)
    if not os.path.exists(LAND):
        Tiles().download_landmask(s1.to_dataframe(), filename=LAND, product="1s")
    s1 = S1(DATADIR)
    miss = int(s1.to_dataframe().orbit.isna().sum())
    print("every burst has an orbit" if not miss else f"WARNING: {miss} bursts without orbit")


def stage_transform(a):
    import pandas as pd
    from insardev_pygmtsar import S1
    s1 = S1(DATADIR, DEM=DEM)
    df = s1.to_dataframe()
    dates = sorted(pd.to_datetime(df.startTime).dt.strftime("%Y-%m-%d").unique())
    ref = a.reference or dates[0]
    print(f"{len(df)} bursts, {len(dates)} dates, reference {ref}")
    s1.transform(ZARRDIR, ref=ref, n_jobs=a.n_jobs, overwrite=a.overwrite)
    print("transform done")


GEOMETRY = ["radar_wavelength", "near_range", "rng_samp_rate", "earth_radius",
            "num_lines", "num_rng_bins", "SC_height_start", "SC_height_end",
            "ref_height", "geometry"]


def burst_meta(ds):
    """fit1d() needs radar metadata that unwrap2d()/trend2d() drop (Semarang)."""
    import numpy as np
    meta = {}
    for name in GEOMETRY:
        if name in ds.variables and not {"y", "x"} & set(ds[name].dims):
            v = ds[name]
            meta[name] = v.mean() if np.issubdtype(v.dtype, np.number) \
                else v.isel({d: 0 for d in v.dims})
    return meta


def stage_sbas(a):
    import numpy as np
    import pandas as pd
    import xarray as xr
    from insardev import Stack
    from insardev_toolkit import Tiles
    os.makedirs(WORK, exist_ok=True)
    os.makedirs(OUT, exist_ok=True)
    client = dask_client()                           # noqa: F841
    stack = Stack().load(ZARRDIR)

    # bursts may differ in date count: keep the common dates (Semarang fix)
    def days(ds):
        return pd.DatetimeIndex(ds.coords["date"].values).normalize()
    common = sorted(set.intersection(*[set(days(ds)) for ds in stack.values()]))
    stack = stack.map(lambda ds: ds.isel(date=np.flatnonzero(days(ds).isin(common))))
    print(f"{len(stack)} bursts, {len(common)} common dates")
    baseline = stack.baseline(days=BASEDAYS, meters=BASEMETERS)
    baseline.to_csv(os.path.join(OUT, "baseline_pairs.csv"))
    print(f"{len(baseline)} pairs (<= {BASEDAYS} d, <= {BASEMETERS} m)")

    intf, corr = (stack.pairs(baseline.tolist()).interferogram(FILTER_M)
                  .goldstein(GOLDSTEIN_M).downsample(SPACING).compute())
    intf = intf.align().dissolve().compute()
    corr = corr.dissolve().compute()
    corr.snapshot(store=os.path.join(WORK, "corr"))
    phase = intf.unwrap2d(weight=corr, union=True).compute()
    phase_dt = phase.trend2d(weight=corr, degree=1, detrend=True)
    displacement = stack.displacement_los(phase_dt)

    phase_fit = type(phase_dt)({k: ds.assign(burst_meta(stack[k]))
                                for k, ds in phase_dt.items()})
    model = phase_fit.fit1d(weight=corr).compute()
    velocity = model[["velocity"]].displacement_los(stack)

    land = np.isfinite(Tiles().open(LAND).rio.reproject(stack.crs))
    velocity = velocity.mask(land).compute()

    # sign check (snippets/periods_1_velocity.py): the fitted velocity must
    # correlate positively with the coherence-free per-pair rate
    d = displacement.mask(land).to_dataset()[POL]
    yrs = (pd.to_datetime(baseline["rep"]) - pd.to_datetime(baseline["ref"])).dt.days.values / 365.25
    dt = xr.DataArray(yrs, dims="pair")
    rate = ((d * dt).sum("pair") / (d.notnull() * dt ** 2).sum("pair")).compute()
    v = velocity.to_dataset()["velocity"].reindex_like(rate, method="nearest").compute()
    ok = (np.isfinite(rate) & np.isfinite(v)).values
    r = float(np.corrcoef(rate.values[ok], v.values[ok])[0, 1])
    print(f"sign check: corr(per-pair rate, fit1d velocity) = {r:+.2f}")
    if r < 0:
        velocity = (-1) * velocity
        print("  velocity sign flipped")

    vlos = (1000 * velocity).to_dataset()["velocity"]
    vlos.rio.to_raster(os.path.join(OUT, "velocity_los_mm_yr.tif"))
    inc = stack.incidence().to_dataset()
    inc = inc[list(inc.data_vars)[0]].reindex_like(vlos, method="nearest")
    vvert = (vlos / np.cos(np.radians(inc))).rename("vertical")
    vvert.rio.write_crs(vlos.rio.crs).rio.to_raster(
        os.path.join(OUT, "velocity_vertical_mm_yr.tif"))
    cm = corr.to_dataset()
    cm = cm[list(cm.data_vars)[0]].mean("pair").reindex_like(vlos, method="nearest")
    cm.rio.write_crs(vlos.rio.crs).rio.to_raster(os.path.join(OUT, "coherence_mean.tif"))
    print(f"wrote velocity (LOS, vertical) and mean coherence to {OUT}")


def stage_analyze(a):
    """Rates on the 25 m analysis grid: by zone x peat, by canal density, and
    the SKM boundary transect. Referenced to coherent mineral soil."""
    import glob
    import numpy as np
    import pandas as pd
    import rasterio
    from rasterio.merge import merge
    from rasterio.warp import reproject, Resampling
    sys.path.insert(0, os.path.join(_REPO_ROOT, "scripts"))
    from ketapang_fire_origin import OUT as ORIGIN
    vt = os.path.join(OUT, "velocity_vertical_mm_yr.tif")
    if not os.path.exists(vt):
        sys.exit("run --stage sbas first")
    srcs = [rasterio.open(p) for p in sorted(glob.glob(os.path.join(ORIGIN, "stack", "stack_*.tif")))]
    stack, tr = merge(srcs, method="first")
    for s in srcs:
        s.close()
    shape = stack.shape[1:]

    def on25(path, resampling=Resampling.average):
        dst = np.full(shape, np.nan, np.float32)
        with rasterio.open(path) as src:
            reproject(rasterio.band(src, 1), dst, src_transform=src.transform,
                      src_crs=src.crs, dst_transform=tr, dst_crs="EPSG:4326",
                      resampling=resampling, dst_nodata=np.nan)
        return dst
    vel = on25(vt)
    coh = on25(os.path.join(OUT, "coherence_mean.tif"))
    np.save(os.path.join(WORK, "vel25.npy"), vel)
    np.save(os.path.join(WORK, "coh25.npy"), coh)
    print("velocity on the 25 m grid; zone / peat / canal analysis to follow "
          "in ketapang_excess_burn.py once the stack exists")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", required=True,
                    choices=["search", "fetch", "transform", "sbas", "analyze"])
    ap.add_argument("--n-jobs", type=int, default=4)
    ap.add_argument("--reference", default=None, help="reference date (default: first)")
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args()
    {"search": stage_search, "fetch": stage_fetch, "transform": stage_transform,
     "sbas": stage_sbas, "analyze": stage_analyze}[a.stage](a)


if __name__ == "__main__":
    main()
