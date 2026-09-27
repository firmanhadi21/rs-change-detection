"""Web-ready products for a paddy-drought run, for a site like drought.ownmap.id.

A run leaves GeoTIFFs on a local grid and a stats.json. A web map needs
something it can fetch by tile and by feature, with the legend and the caveats
travelling WITH the data rather than living in someone's head:

  cog/*.tif       Cloud-Optimised GeoTIFFs, one per layer, EPSG:3857 so a
                  tile server (titiler, rio-tiler) can serve them directly
  zones.geojson   per-zone adequacy, equity and reliability, in WGS84
  alerts.geojson  the fields worth visiting: severe deficit, not planted,
                  or puso candidates, as polygons rather than pixels
  legend.json     class values, labels in both languages, and colours, so
                  the map and the raster cannot disagree
  summary.json    headline hectares, the dates behind them, and the limits

Every file carries its own provenance: run id, as-of date, sources, and the
sentence that matters most -- that a puso flag is a candidate for a field
check, not a verdict.
"""
import json
import os

import numpy as np

from . import paddy_water as pw

WEB_CRS = "EPSG:3857"
WAPOR_PIXEL_M = 300         # what the water layers actually resolve

# What a viewer can switch between, and how each is coloured.
LAYERS = {
    # The headline drought layer. It leads because it is the one that means
    # the same thing everywhere: this season against these fields' own
    # normal. The absolute adequacy below is kept for audit, but satellite
    # ETa reads ~35% under Kc x ET0 over flooded rice, so its FAO-33 classes
    # describe the product as much as the crop until they are calibrated.
    "anomaly_class": {
        "title": {"id": "Kekeringan dibanding musim biasanya",
                  "en": "Drought against this field's normal"},
        "classes": pw.ANOMALY_CLASSES, "nodata": pw.ADEQUACY_NODATA,
    },
    "adequacy_class": {
        "title": {"id": "Kecukupan air musim ini (skala mutlak, belum "
                        "dikalibrasi)",
                  "en": "Water adequacy this season (absolute scale, "
                        "uncalibrated)"},
        "classes": pw.ADEQUACY_CLASSES, "nodata": pw.ADEQUACY_NODATA,
    },
    "outlook_class": {
        "title": {"id": "Risiko 7 hari (hujan saja)",
                  "en": "7-day risk (rainfall only)"},
        "classes": pw.ADEQUACY_CLASSES, "nodata": pw.ADEQUACY_NODATA,
    },
    "delay_class": {
        "title": {"id": "Kemunduran tanam", "en": "Planting delay"},
        "classes": pw.DELAY_CLASSES, "nodata": 255,
    },
    "paddy": {
        "title": {"id": "Sebaran sawah", "en": "Paddy extent"},
        "classes": [(0, None, None, {"id": "Bukan sawah", "en": "Not paddy"},
                     "#00000000"),
                    (1, None, None, {"id": "Sawah", "en": "Paddy"}, "#2c7bb6")],
        "nodata": None,
    },
    "puso": {
        "title": {"id": "Kandidat puso", "en": "Puso candidates"},
        "classes": [(0, None, None, {"id": "Tidak", "en": "No"}, "#00000000"),
                    (1, None, None, {"id": "Kandidat — perlu cek lapangan",
                                     "en": "Candidate — needs a field check"},
                     "#b2182b")],
        "nodata": None,
    },
}

CAVEATS = {
    "id": [
        "Kandidat puso adalah daftar untuk dicek di lapangan, bukan vonis.",
        "Prakiraan 7 hari hanya memperhitungkan hujan; pasokan irigasi tidak "
        "dapat diprakirakan. Peta ini menunjukkan di mana hujan saja tidak "
        "cukup, bukan apa yang akan dilakukan saluran.",
        "Prakiraan hujan tropis andal sampai sekitar 5-7 hari; 14 hari bersifat "
        "indikatif.",
        "Neraca air memakai WaPOR 300 m: satu piksel menutupi sekitar {cells} "
        "sel {grid:.0f} m pada jaringan analisis, sehingga hanya sel yang "
        "didominasi sawah tertanam yang dinilai.",
        "Ambang kelas mengikuti FAO-33 dan belum dikalibrasi dengan data hasil "
        "panen setempat.",
        "ETa satelit di atas sawah tergenang terbaca sekitar 35% di bawah "
        "Kc x ET0 bahkan saat air melimpah (diuji: WaPOR, MOD16, ERA5-Land "
        "sepakat). Karena itu lapisan utama adalah perbandingan dengan musim "
        "biasanya pada petak yang sama, bukan skala mutlak.",
    ],
    "en": [
        "Puso flags are candidates for a field check, not a verdict.",
        "The 7-day outlook counts rainfall only; irrigation deliveries cannot "
        "be forecast. It shows where rain alone will not cover the crop, not "
        "what the canals will do.",
        "Tropical rainfall forecasts are useful to about 5-7 days; 14 days is "
        "indicative.",
        "The water balance uses WaPOR at 300 m: one pixel covers about {cells} "
        "cells of the {grid:.0f} m analysis grid, so only cells dominated by "
        "planted paddy are scored.",
        "Class thresholds follow FAO-33 and are not calibrated against local "
        "yield data.",
        "Satellite ETa over flooded rice reads about 35% below Kc x ET0 even "
        "when water is abundant (checked: WaPOR, MOD16 and ERA5-Land agree). "
        "The headline layer is therefore this season against the same "
        "fields' own normal, not the absolute scale.",
    ],
}


def caveats(lang="id", grid_m=None):
    """The limits, with the WaPOR footprint stated in the grid actually used."""
    from . import paddy_data as pdata
    grid = float(grid_m or pdata.grid_metres())
    cells = max(1, round((WAPOR_PIXEL_M / grid) ** 2))
    return [c.format(cells=cells, grid=grid) if "{cells}" in c else c
            for c in CAVEATS.get(lang, CAVEATS["id"])]


def legend(lang="id", grid_m=None, native_m=None):
    """Values, labels and colours, so map and raster cannot drift apart.

    Each layer also carries the grid it is drawn on and what its information
    actually resolves. They differ -- the water layers are WaPOR at 300 m on a
    ~56 m grid -- and a viewer that does not say so invites a 300 m number to
    be read as a field measurement.
    """
    native_m = native_m or {}
    out = {}
    for key, spec in LAYERS.items():
        out[key] = {
            "title": spec["title"],
            "nodata": spec["nodata"],
            "grid_m": round(grid_m, 2) if grid_m else None,
            "native_m": native_m.get(key),
            "classes": [{"value": cid, "colour": colour,
                         "label": labels if isinstance(labels, dict) else
                         {"id": labels, "en": labels}}
                        for cid, _, _, labels, colour in spec["classes"]],
        }
    return out


def to_cog(src_path, out_path, resampling="nearest"):
    """Reproject to web mercator and write a tiled, overviewed GeoTIFF.

    Written with rasterio rather than rio-cogeo so the package keeps its
    dependencies; the result is a valid COG: tiled, compressed, with
    overviews, which is what a tile server needs to avoid reading whole files.
    """
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.warp import calculate_default_transform, reproject

    how = getattr(Resampling, resampling)
    with rasterio.open(src_path) as src:
        transform, width, height = calculate_default_transform(
            src.crs, WEB_CRS, src.width, src.height, *src.bounds)
        prof = src.profile.copy()
        prof.update(crs=WEB_CRS, transform=transform, width=width,
                    height=height, driver="GTiff", tiled=True,
                    blockxsize=256, blockysize=256, compress="deflate",
                    BIGTIFF="IF_SAFER")
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with rasterio.open(out_path, "w", **prof) as dst:
            for b in range(1, src.count + 1):
                reproject(source=rasterio.band(src, b),
                          destination=rasterio.band(dst, b),
                          src_transform=src.transform, src_crs=src.crs,
                          dst_transform=transform, dst_crs=WEB_CRS,
                          resampling=how)
            factors = [f for f in (2, 4, 8, 16) if min(width, height) // f >= 64]
            if factors:
                dst.build_overviews(factors, how)
                dst.update_tags(ns="rio_overview", resampling=resampling)
    return out_path


def polygonise(mask, profile, props=None, simplify_m=0):
    """Contiguous True areas of `mask` as WGS84 GeoJSON features.

    Pixels are not an operational unit: a field officer visits a patch. Areas
    are computed before reprojection, where the grid is regular.
    """
    import rasterio
    from rasterio.features import shapes
    from shapely.geometry import shape as to_shape
    from shapely.ops import transform as shp_transform

    m = np.asarray(mask).astype("uint8")
    feats = []
    for geom, value in shapes(m, mask=m.astype(bool),
                              transform=profile["transform"]):
        if not value:
            continue
        g = to_shape(geom)
        if simplify_m:
            g = g.simplify(simplify_m / 111320.0)
        feats.append({"type": "Feature", "geometry": g.__geo_interface__,
                      "properties": dict(props or {})})
    src_crs = str(profile.get("crs", "EPSG:4326"))
    if src_crs.upper() not in ("EPSG:4326", "WGS84"):
        import pyproj
        project = pyproj.Transformer.from_crs(src_crs, "EPSG:4326",
                                              always_xy=True).transform
        for f in feats:
            f["geometry"] = shp_transform(
                project, to_shape(f["geometry"])).__geo_interface__
    return feats


def alerts_geojson(rasters, profile, area_ha, lang="id", min_ha=0.5):
    """The three things worth a visit, as polygons with their area.

    Small specks are dropped: a quarter-hectare of "severe" inside a healthy
    block is more likely a mixed pixel than a field in trouble.
    """
    import rasterio

    def read(path):
        with rasterio.open(path) as src:
            return src.read(1)

    kinds = [
        ("severe_deficit", {"id": "Defisit berat", "en": "Severe deficit"},
         read(rasters["adequacy_class"]) == 3),
        ("not_planted", {"id": "Belum tanam", "en": "Not planted"},
         read(rasters["delay_class"]) == pw.NOT_PLANTED),
        ("puso_candidate", {"id": "Kandidat puso", "en": "Puso candidate"},
         read(rasters["puso"]) == 1),
    ]
    from shapely.geometry import shape as to_shape

    out = []
    for key, label, mask in kinds:
        for f in polygonise(mask, profile, {"kind": key, "label": label},
                            simplify_m=25):
            g = to_shape(f["geometry"])
            # Degrees squared mean nothing to a field officer: convert at the
            # patch's own latitude, where a degree of longitude is shorter.
            lat = g.centroid.y
            deg_ha = (111320.0 * float(np.cos(np.radians(lat))) * 110540.0) / 1e4
            ha = float(g.area * deg_ha)
            if ha < min_ha:
                continue
            f["properties"]["area_ha"] = round(ha, 2)
            out.append(f)
    return {"type": "FeatureCollection", "features": out}


def zones_geojson(zones_file, rows, zone_field=None):
    """The zone layer with the run's numbers joined on."""
    import geopandas as gpd
    gdf = gpd.read_file(zones_file).to_crs("EPSG:4326")
    by_id = {r["zone"]: r for r in rows}
    if zone_field and zone_field in gdf.columns:
        keys = [int(v) for v in gdf[zone_field]]
    else:
        keys = list(range(1, len(gdf) + 1))
    for col in ("paddy_ha", "si_mean", "si_p10", "reliability", "equity_flag"):
        gdf[col] = [by_id.get(k, {}).get(col) for k in keys]
    return json.loads(gdf.to_json())


def publish(run_dir, rasters, stats, profile, area_ha, out_dir=None,
            zones_file=None, zone_field=None, lang="id"):
    """Write the web bundle next to the run, and return what was written."""
    out_dir = out_dir or os.path.join(run_dir, "web")
    os.makedirs(os.path.join(out_dir, "cog"), exist_ok=True)
    written = {"cog": {}}

    for key in LAYERS:
        src = rasters.get(key)
        if src and os.path.exists(src):
            dst = os.path.join(out_dir, "cog", f"{key}.tif")
            to_cog(src, dst)
            written["cog"][key] = dst

    alerts = alerts_geojson(rasters, profile, area_ha, lang)
    with open(os.path.join(out_dir, "alerts.geojson"), "w") as f:
        json.dump(alerts, f)
    written["alerts"] = os.path.join(out_dir, "alerts.geojson")

    if zones_file and stats.get("zones", {}).get("rows"):
        gj = zones_geojson(zones_file, stats["zones"]["rows"], zone_field)
        with open(os.path.join(out_dir, "zones.geojson"), "w") as f:
            json.dump(gj, f)
        written["zones"] = os.path.join(out_dir, "zones.geojson")

    grid = stats.get("grid") or {"m": stats.get("grid_m")}
    native_m = stats.get("native_m") or {}
    with open(os.path.join(out_dir, "legend.json"), "w") as f:
        json.dump(legend(lang, grid.get("m"), native_m), f, indent=2)
    written["legend"] = os.path.join(out_dir, "legend.json")

    summary = {
        "run_id": stats.get("run_id"),
        "as_of": stats.get("as_of"),
        "scenario": stats.get("scenario"),
        "location": stats.get("location"),
        "radius_km": stats.get("radius_km"),
        "season": stats.get("season"),
        "headline": {
            "paddy_ha": stats.get("paddy_ha"),
            "planted_ha": stats.get("planted_ha"),
            "not_planted_ha": stats.get("not_planted_ha"),
            "not_planted_pct": stats.get("not_planted_pct"),
            "median_delay_days": stats.get("median_delay_days"),
            "season_length_days_median": stats.get("season_length_days_median"),
            "adequacy_ha": stats.get("adequacy_ha"),
            "outlook_ha": stats.get("outlook_ha"),
            "puso_candidates_ha": stats.get("puso_candidates_ha"),
        },
        "alerts": {"features": len(alerts["features"])},
        "sources": stats.get("sources"),
        "outlook": stats.get("outlook"),
        # The grid every layer is drawn on, and what each layer's information
        # actually resolves. A map that shows only the first invites the water
        # layers to be read as field measurements.
        "resolution": {
            "grid": grid,
            "native_m": native_m,
            "note": {
                "id": "Semua lapisan digambar pada jaringan yang sama; "
                      "native_m adalah resolusi asli informasinya. Lapisan air "
                      "berasal dari WaPOR 300 m, bukan ukuran per petak.",
                "en": "Every layer is drawn on the same grid; native_m is what "
                      "its information actually resolves. The water layers come "
                      "from WaPOR at 300 m, not from field-level measurement.",
            },
        },
        "caveats": caveats(lang, grid.get("m")),
        "layers": list(written["cog"]),
    }
    with open(os.path.join(out_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    written["summary"] = os.path.join(out_dir, "summary.json")
    return written
