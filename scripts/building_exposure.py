"""Pre-event building exposure over Flores, from Google Open Buildings v3.

This is the EXPOSURE half of the damage assessment, and it is independent of
the co-seismic interferogram -- it says what was standing before the event, so
it can be built and checked now.

The resolution constraint decides the whole design and is worth stating
plainly: coherence is 40 m, buildings on Flores are 8-15 m. A 40 m cell holds
several buildings in a village and a fraction of one in open country. So this
CANNOT say which building was damaged. What it can do is aggregate to cells or
settlements, count the built area inside each, and let the coherence change
rank them for field survey. That is a triage product, not a damage census, and
the difference matters when someone acts on it.

Writes a grid of building counts and built area, on a grid chosen to match the
coherence raster so the two can be combined without resampling either.

    python3 scripts/building_exposure.py                 # summary only
    python3 scripts/building_exposure.py --export        # to Drive as GeoTIFF
"""

import argparse
import sys

# Flores, matching the co-seismic frames on ascending path 112.
AOI = {"west": 120.4, "east": 123.0, "south": -8.95, "north": -8.15}
CELL_M = 400          # aggregation cell; 10 coherence pixels at 40 m
MIN_CONFIDENCE = 0.70  # v3 confidence runs 0.65-1.0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--export", action="store_true",
                    help="queue a GeoTIFF export to Google Drive")
    ap.add_argument("--project", default=None, help="Earth Engine cloud project id")
    ap.add_argument("--cell", type=int, default=CELL_M)
    ap.add_argument("--confidence", type=float, default=MIN_CONFIDENCE)
    a = ap.parse_args()

    import os
    import ee

    # Reuse the package's own initialiser rather than reinventing it. It knows
    # that ~/.config/earthengine/ee-geodetic.json is a SERVICE ACCOUNT KEY, not
    # a project name -- which is what my first attempt got wrong, passing the
    # filename to ee.Initialize(project=...) and getting "project not found".
    # It also handles $EARTHCHANGE_EE_KEY and falls back to user credentials.
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        from earthchange.gee_utils import initialize_ee
    except ImportError:
        initialize_ee = None

    if initialize_ee is not None and not a.project:
        # prefer_user for --export: a service account writes to its OWN Drive,
        # which nobody can browse.
        initialize_ee(prefer_user=a.export)
    else:
        ee.Initialize(project=a.project) if a.project else ee.Initialize()
        print(f"Earth Engine project: {a.project or '(default)'}")

    aoi = ee.Geometry.Rectangle(
        [AOI["west"], AOI["south"], AOI["east"], AOI["north"]])

    buildings = (ee.FeatureCollection(
                     "GOOGLE/Research/open-buildings/v3/polygons")
                 .filterBounds(aoi)
                 .filter(ee.Filter.gte("confidence", a.confidence)))

    n = buildings.size()
    area = buildings.aggregate_sum("area_in_meters")
    print(f"AOI {AOI['west']}..{AOI['east']} E, "
          f"{AOI['south']}..{AOI['north']} N")
    print(f"confidence >= {a.confidence}")
    print(f"\nbuildings: {n.getInfo():,}")
    print(f"built area: {area.getInfo()/1e6:.1f} km2")

    # Size distribution, because it says whether 40 m cells are hopeless or
    # merely coarse: if the median building is 60 m2, roughly 8 m across, then
    # a 40 m cell spans several and per-building attribution is out.
    sizes = buildings.aggregate_array("area_in_meters")
    pct = ee.List([10, 25, 50, 75, 90]).map(
        lambda p: sizes.reduce(ee.Reducer.percentile([p])))
    print("\nbuilding footprint area (m2):")
    for p, v in zip([10, 25, 50, 75, 90], pct.getInfo()):
        val = list(v.values())[0] if isinstance(v, dict) else v
        print(f"  p{p:<3} {val:8.1f}")

    # Rasterise onto the aggregation grid. Count and area are both kept: count
    # ranks dense settlements, area ranks where the built fabric is largest,
    # and they disagree where a few big structures sit among small houses.
    count = (buildings.map(lambda f: f.set("one", 1))
             .reduceToImage(properties=["one"], reducer=ee.Reducer.count())
             .unmask(0).rename("building_count"))
    built = (buildings.reduceToImage(properties=["area_in_meters"],
                                     reducer=ee.Reducer.sum())
             .unmask(0).rename("built_area_m2"))

    grid = count.addBands(built).reproject(
        crs="EPSG:32751", scale=a.cell).clip(aoi)   # UTM 51S, as the frames

    stats = grid.reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=aoi, scale=a.cell, maxPixels=1e10, bestEffort=True)
    print(f"\nafter aggregation to {a.cell} m cells:")
    print(f"  {stats.getInfo()}")

    print("\n--- what this can and cannot support ---")
    print("  CAN: rank villages or cells for field survey by built area")
    print("       inside anomalously decorrelated cells")
    print("  CANNOT: say which building was damaged — a 40 m coherence pixel")
    print("       holds several buildings, and Open Buildings is a PRE-event")
    print("       layer derived from optical imagery, so it describes what was")
    print("       standing, not what remains")

    if not a.export:
        print("\nsummary only — rerun with --export to queue a GeoTIFF")
        return 0

    task = ee.batch.Export.image.toDrive(
        image=grid.toFloat(),
        description=f"flores_building_exposure_{a.cell}m",
        folder="GEE_coseismic",
        region=aoi,
        scale=a.cell,
        crs="EPSG:32751",
        maxPixels=int(1e10),
        fileFormat="GeoTIFF",
    )
    task.start()
    print(f"\nexport queued: {task.id}")
    print("  check status at https://code.earthengine.google.com/tasks")
    print("  lands in Google Drive under GEE_coseismic/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
