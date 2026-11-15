"""Perintah singkat berbahasa Indonesia untuk tugas rutin.

    earthchange banjir    "Pining, Gayo Lues"   2026-11-08
    earthchange kebakaran "Ketapang"            2026-09-15
    earthchange hutan     "Halmahera Tengah"    2019 2025
    earthchange kota      "Kota Bekasi"         2020 2025
    earthchange air       "Kabupaten Demak"     2020 2025

The user names a place and a date (or two years). Everything a remote-sensing
specialist would otherwise choose is decided here: the before/after windows,
the sensor, the thresholds (the scenario defaults), and Planetary Computer as
the backend, so no account is needed. The place name is resolved to its real
administrative boundary from OpenStreetMap, the scenario runs over the
boundary's bounding square, and the hectares are then counted INSIDE the
boundary, so "Kecamatan Pining" means Pining and not a box around it.

Errors are reported in plain Indonesian; --debug shows the traceback.
"""

import datetime as dt
import glob
import json
import math
import os
import re
import sys

NOMINATIM = "https://nominatim.openstreetmap.org/search"
USER_AGENT = ("earthchange satellite change detection "
              "(https://github.com/firmanhadi21/rs-change-detection)")
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".cache", "earthchange", "wilayah")

# Largest half-side (km) run without --paksa. A regency is ~20-45 km; a
# province is several hundred and would take hours on an office laptop.
MAX_RADIUS_KM = 50.0
# Fallback radius when the name is a point (a village centre) with no boundary.
POINT_RADIUS_KM = 5.0
# Sentinel-2 composites use only the clearest acquisition days per window, so a
# run fits an office laptop (see mpc_backend.S2_MAX_SCENES).
S2_HARI_TERJERNIH = 12
PERMUKIMAN = {"city", "town", "village", "hamlet", "suburb", "quarter",
              "neighbourhood", "isolated_dwelling", "municipality", "county", "state"}

PERINTAH = {
    "banjir": {
        "scenario": "flood", "jenis": "kejadian",
        "judul": "Banjir (genangan air)",
        "sebelum_hari": 45, "sesudah_hari": 12,
        "satelit": "Sentinel-1 (radar, menembus awan)",
        "hasil": "tergenang",
        "batasan": [
            "Radar hanya melihat air terbuka. Genangan di bawah pohon rapat atau "
            "di gang sempit permukiman bisa tidak terdeteksi.",
            "Satelit lewat beberapa hari sekali. Jika air sudah surut saat satelit "
            "lewat, genangan tercatat lebih kecil dari kenyataan.",
            "Sawah yang sengaja digenangi bisa terhitung sebagai banjir.",
            "Hasil belum dicek di lapangan.",
        ],
    },
    "kebakaran": {
        "scenario": "burn", "jenis": "kejadian",
        "judul": "Area terbakar",
        "sebelum_hari": 90, "sesudah_hari": 45,
        "satelit": "Sentinel-2 (optik)",
        "hasil": "terbakar",
        "batasan": [
            "Satelit optik tidak menembus awan dan asap tebal; jika langit tertutup "
            "terus, hasil bisa kosong atau kurang.",
            "Panen dan pembukaan lahan juga menurunkan indeks dan bisa terhitung.",
            "Cocokkan dengan titik panas (hotspot) dan cek lapangan.",
        ],
    },
    "hutan": {
        "scenario": "deforestation", "jenis": "tahun",
        "judul": "Kehilangan tutupan vegetasi (hutan)",
        "satelit": "Sentinel-2 (optik), median tahunan",
        "hasil": "kehilangan vegetasi",
        "batasan": [
            "Yang diukur adalah turunnya kehijauan vegetasi, bukan status hutan "
            "resmi. Panen kebun, peremajaan sawit, dan sawah juga bisa terhitung.",
            "Awan yang tersisa pada median tahunan bisa menimbulkan bercak palsu.",
            "Hasil belum dicek di lapangan.",
        ],
    },
    "kota": {
        "scenario": "urbanization", "jenis": "tahun",
        "judul": "Pertambahan lahan terbangun",
        "satelit": "Sentinel-2 (optik), median tahunan",
        "hasil": "lahan terbangun baru",
        "batasan": [
            "Tanah terbuka, lahan yang baru dibuka, dan tambang bisa terbaca "
            "sebagai bangunan.",
            "Hasil belum dicek di lapangan.",
        ],
    },
    "air": {
        "scenario": "water", "jenis": "tahun",
        "judul": "Pertambahan air permukaan",
        "satelit": "Sentinel-2 (optik), median tahunan",
        "hasil": "air permukaan baru",
        "batasan": [
            "Sawah tergenang dan tambak musiman bisa terhitung.",
            "Awan dan bayangan awan bisa menimbulkan bercak palsu.",
            "Hasil belum dicek di lapangan.",
        ],
    },
}

BANTUAN = """\
earthchange — perintah singkat (tanpa akun, data Planetary Computer)

  earthchange banjir    WILAYAH TANGGAL       genangan setelah kejadian
  earthchange kebakaran WILAYAH TANGGAL       area terbakar setelah kejadian
  earthchange hutan     WILAYAH TAHUN1 TAHUN2 kehilangan vegetasi
  earthchange kota      WILAYAH TAHUN1 TAHUN2 lahan terbangun baru
  earthchange air       WILAYAH TAHUN1 TAHUN2 air permukaan baru

WILAYAH  nama provinsi/kabupaten/kecamatan/desa, sebaiknya dengan nama
         kabupatennya, mis. "Pining, Gayo Lues"; atau file batas wilayah
         (.geojson / .gpkg / .shp)
TANGGAL  hari kejadian, mis. 2026-11-08
TAHUN    2017 sampai tahun ini

Pilihan:
  --keluar FOLDER   simpan hasil di folder ini (bawaan: output/...)
  --paksa           jalankan juga untuk wilayah sangat luas (lambat)
  --debug           tampilkan detail teknis bila terjadi kesalahan

Contoh:
  earthchange banjir "Pining, Gayo Lues" 2026-11-08
  earthchange hutan "Halmahera Tengah" 2019 2025

Perintah lengkap untuk pengguna mahir: earthchange --list
"""


class Gagal(Exception):
    """An error to show the user as-is, in Indonesian."""


# ------------------------------------------------------------------ dates
def _tanggal(teks):
    try:
        return dt.date.fromisoformat(teks)
    except ValueError:
        raise Gagal(f"Tanggal '{teks}' tidak dikenali. Tulis seperti 2026-11-08 "
                    "(tahun-bulan-tanggal).")


def jendela_kejadian(tanggal, sebelum_hari, sesudah_hari, hari_ini=None):
    """Before/after windows around an event day.

    Before: the `sebelum_hari` days up to the day before the event.
    After: the event day up to `sesudah_hari` later, but never past today.
    Returns ((start, end), (start, end)) as ISO strings.
    """
    hari_ini = hari_ini or dt.date.today()
    if tanggal > hari_ini:
        raise Gagal(f"Tanggal {tanggal} belum terjadi. Pakai tanggal kejadian yang "
                    "sudah lewat.")
    sebelum = (tanggal - dt.timedelta(days=sebelum_hari),
               tanggal - dt.timedelta(days=1))
    akhir = min(tanggal + dt.timedelta(days=sesudah_hari), hari_ini)
    sesudah = (tanggal, akhir)
    return tuple(d.isoformat() for d in sebelum), tuple(d.isoformat() for d in sesudah)


def jendela_tahun(t1, t2, hari_ini=None):
    """Whole-year windows for two years (the later one cut at today)."""
    hari_ini = hari_ini or dt.date.today()
    try:
        t1, t2 = int(t1), int(t2)
    except ValueError:
        raise Gagal(f"Tahun '{t1}' atau '{t2}' tidak dikenali. Tulis seperti 2019 2025.")
    if t1 >= t2:
        raise Gagal(f"Tahun pertama ({t1}) harus lebih awal dari tahun kedua ({t2}).")
    if t1 < 2017:
        raise Gagal("Perintah singkat memakai Sentinel-2, yang tersedia sejak 2017. "
                    "Untuk tahun lebih awal, pakai perintah lengkap dengan "
                    "--sensor landsat (lihat: earthchange -s deforestation --help).")
    if t2 > hari_ini.year:
        raise Gagal(f"Tahun {t2} belum terjadi.")
    sebelum = (f"{t1}-01-01", f"{t1}-12-31")
    akhir = f"{t2}-12-31" if t2 < hari_ini.year else hari_ini.isoformat()
    if t2 == hari_ini.year and hari_ini.month < 4:
        print(f"Catatan: tahun {t2} baru berjalan {hari_ini.month} bulan; median "
              "tahunannya lebih berawan dan kurang mewakili.")
    return sebelum, (f"{t2}-01-01", akhir)


# ------------------------------------------------------------------ area
def _nama_aman(teks):
    s = re.sub(r"[^A-Za-z0-9]+", "_", teks).strip("_")
    return s[:60] or "wilayah"


def _bentuk(geom):
    return geom and geom.get("type") in ("Polygon", "MultiPolygon")


def _baca_file(path):
    """A user's own boundary file -> one GeoJSON geometry (all features merged)."""
    if path.lower().endswith((".geojson", ".json")):
        with open(path) as f:
            gj = json.load(f)
        feats = gj["features"] if gj.get("type") == "FeatureCollection" else [gj]
        geoms = [ft.get("geometry", ft) for ft in feats]
    else:
        try:
            import geopandas as gpd
        except ImportError:
            raise Gagal("Untuk membaca .gpkg/.shp perlu geopandas "
                        "(pip install 'earthchange[zones]'), atau simpan "
                        "batasnya sebagai .geojson.")
        gdf = gpd.read_file(path).to_crs(4326)
        geoms = [json.loads(gpd.GeoSeries([g]).to_json())["features"][0]["geometry"]
                 for g in gdf.geometry]
    polys = []
    for g in geoms:
        if g and g["type"] == "Polygon":
            polys.append(g["coordinates"])
        elif g and g["type"] == "MultiPolygon":
            polys.extend(g["coordinates"])
    if not polys:
        raise Gagal(f"File {path} tidak berisi poligon.")
    return {"type": "MultiPolygon", "coordinates": polys}


def pilih_hasil(hits):
    """From Nominatim hits, keep administrative boundaries with a polygon,
    ordered as returned. Returns (polygons, points)."""
    polys = [h for h in hits if h.get("category") == "boundary" and _bentuk(h.get("geojson"))]
    if not polys:
        polys = [h for h in hits if h.get("category") in ("boundary", "place")
                 and _bentuk(h.get("geojson"))]
    # Only settlements may stand in for an area. "Weda Tengah, Halmahera
    # Tengah" once matched a school, and the run was labelled with its name.
    points = [h for h in hits if not _bentuk(h.get("geojson"))
              and h.get("category") == "place" and h.get("type") in PERMUKIMAN]
    return polys, points


def _cari_nominatim(nama):
    import requests
    try:
        r = requests.get(NOMINATIM, timeout=30, headers={"User-Agent": USER_AGENT},
                         params={"q": nama, "format": "jsonv2", "countrycodes": "id",
                                 "limit": 8, "polygon_geojson": 1,
                                 "polygon_threshold": 0.0005})
        r.raise_for_status()
        return r.json()
    except requests.RequestException:
        raise Gagal("Tidak bisa mencari nama wilayah: periksa koneksi internet, "
                    "atau pakai file batas wilayah (.geojson).")


def _tanya_pilihan(kandidat):
    print("Nama ini cocok dengan beberapa wilayah:")
    for i, h in enumerate(kandidat, 1):
        print(f"  {i}. {h['display_name']}")
    while True:
        jawab = input(f"Pilih nomor 1-{len(kandidat)}: ").strip()
        if jawab.isdigit() and 1 <= int(jawab) <= len(kandidat):
            return kandidat[int(jawab) - 1]


def cari_wilayah(teks):
    """Area text -> (name, GeoJSON geometry, note).

    A path to a boundary file is read directly. Otherwise the name is looked up
    on OpenStreetMap (Indonesia only) and cached, so repeat runs are offline
    for the area step.
    """
    if os.path.exists(teks):
        return _nama_aman(os.path.splitext(os.path.basename(teks))[0]), _baca_file(teks), \
            f"batas dari file {teks}"

    os.makedirs(CACHE_DIR, exist_ok=True)
    cache = os.path.join(CACHE_DIR, _nama_aman(teks.lower()) + ".json")
    if os.path.exists(cache):
        with open(cache) as f:
            c = json.load(f)
        return c["nama"], c["geom"], c["catatan"]

    polys, points = pilih_hasil(_cari_nominatim(teks))
    if polys:
        labels = list(dict.fromkeys(h["display_name"] for h in polys))
        hit = polys[0]
        if len(labels) > 1 and sys.stdin.isatty():
            hit = _tanya_pilihan([next(h for h in polys if h["display_name"] == l)
                                  for l in labels])
        elif len(labels) > 1:
            print(f"Catatan: '{teks}' juga cocok dengan: " + "; ".join(labels[1:4]))
        geom, catatan = hit["geojson"], f"batas wilayah OpenStreetMap: {hit['display_name']}"
        nama = hit["display_name"].split(",")[0].strip()
    elif points:
        hit = points[0]
        print(f"PERHATIAN: batas wilayah '{teks}' tidak ada di OpenStreetMap. Yang ditemukan "
              f"hanya titik pusat '{hit['display_name']}'; dipakai lingkaran "
              f"{POINT_RADIUS_KM:g} km di sekitarnya. Untuk batas yang tepat, pakai file "
              "batas wilayah (.geojson/.gpkg/.shp).")
        if sys.stdin.isatty() and input("Lanjutkan? [y/N] ").strip().lower() not in ("y", "ya"):
            raise Gagal("Dibatalkan. Coba nama kabupaten, atau pakai file batas wilayah.")
        lat, lon = float(hit["lat"]), float(hit["lon"])
        geom = lingkaran(lat, lon, POINT_RADIUS_KM)
        catatan = (f"batas resmi '{hit['display_name']}' tidak tersedia; dipakai "
                   f"lingkaran {POINT_RADIUS_KM:g} km di sekitar titik pusatnya")
        nama = hit["display_name"].split(",")[0].strip()
    else:
        raise Gagal(f"Wilayah '{teks}' tidak ditemukan sebagai batas wilayah atau permukiman. "
                    "Periksa ejaan, tambahkan nama kabupatennya (mis. \"Pining, Gayo Lues\"), "
                    "atau pakai file batas wilayah (.geojson/.gpkg/.shp).")

    if not polys:
        return nama, geom, catatan          # a circle guess is not cached
    with open(cache, "w") as f:
        json.dump({"nama": nama, "geom": geom, "catatan": catatan}, f)
    return nama, geom, catatan


def lingkaran(lat, lon, km, n=64):
    dlat = km / 110.574
    dlon = km / (111.320 * math.cos(math.radians(lat)))
    ring = [[lon + dlon * math.cos(2 * math.pi * i / n),
             lat + dlat * math.sin(2 * math.pi * i / n)] for i in range(n)]
    ring.append(ring[0])
    return {"type": "Polygon", "coordinates": [ring]}


def _semua_titik(geom):
    if geom["type"] == "Polygon":
        rings = geom["coordinates"]
    else:
        rings = [r for poly in geom["coordinates"] for r in poly]
    for ring in rings:
        for x, y in ring:
            yield x, y


def kotak_aoi(geom):
    """Centre (lat, lon) and half-side km of the square that covers the area."""
    xs, ys = zip(*_semua_titik(geom))
    w, e, s, n = min(xs), max(xs), min(ys), max(ys)
    lat, lon = (s + n) / 2, (w + e) / 2
    half_ns = (n - s) / 2 * 110.574
    half_ew = (e - w) / 2 * 111.320 * math.cos(math.radians(lat))
    return lat, lon, round(max(half_ns, half_ew, 1.0) * 1.02, 2)


# ------------------------------------------------------------------ area count
def hitung_luas(tif, geom, scenario, cfg):
    """Hectares of the result inside the boundary.

    flood: pixels marked 1. Optical scenarios: the index change past the
    scenario's threshold (and its severe threshold). Pixel area follows the
    latitude, since the GeoTIFFs are in EPSG:4326.
    """
    import numpy as np
    import rasterio
    from rasterio.features import geometry_mask

    with rasterio.open(tif) as src:
        data = src.read(1).astype("float64")
        if src.nodata is not None:
            data[data == src.nodata] = np.nan
        inside = geometry_mask([geom], out_shape=data.shape, transform=src.transform,
                               invert=True, all_touched=False)
        t = src.transform
        rows = np.arange(data.shape[0])
        lat = t.f + (rows + 0.5) * t.e
        px_ha = (abs(t.a) * 111320.0 * np.cos(np.radians(lat))) * (abs(t.e) * 110574.0) / 1e4
        px_ha = np.broadcast_to(px_ha[:, None], data.shape)

    valid = inside & np.isfinite(data)
    out = {"luas_wilayah_ha": float(px_ha[inside].sum()),
           "luas_terpantau_ha": float(px_ha[valid].sum())}
    if scenario == "flood":
        # The flood GeoTIFF holds 1 for flood and no-data for everything else,
        # so "observed" cannot be read from it: the whole boundary is the base.
        out["luas_terpantau_ha"] = out["luas_wilayah_ha"]
        out["terdampak_ha"] = float(px_ha[valid & (data >= 0.5)].sum())
    else:
        thr, severe = cfg["thr"], cfg["severe"]
        if cfg["direction"] == "loss":
            aff, sev = data < thr, data < severe
        else:
            aff, sev = data > thr, data > severe
        out["terdampak_ha"] = float(px_ha[valid & aff].sum())
        out["kuat_ha"] = float(px_ha[valid & sev].sum())
    return out


# ------------------------------------------------------------------ messages
TERJEMAHAN = [
    ("No Sentinel-1 orbit covers both windows",
     "Tidak ada citra radar Sentinel-1 untuk sebelum dan sesudah tanggal itu. "
     "Jika kejadiannya baru, citra sesudah kejadian mungkin belum tersedia; "
     "coba lagi 2-3 hari lagi."),
    ("No Sentinel-2 scenes in the post",
     "Tidak ada citra Sentinel-2 yang bisa dipakai sesudah tanggal itu "
     "(belum tersedia atau tertutup awan). Coba lagi nanti."),
    ("No Sentinel-2 scenes in the pre",
     "Tidak ada citra Sentinel-2 yang bisa dipakai sebelum tanggal itu."),
    ("not supported by the MPC backend",
     "Analisis ini belum tersedia tanpa akun Earth Engine."),
]


def _terjemahkan(pesan):
    for kunci, teks in TERJEMAHAN:
        if kunci in pesan:
            return teks
    return pesan


def _ha(x):
    return f"{x:,.0f}".replace(",", ".") if x >= 10 else f"{x:.1f}".replace(".", ",")


def catatan_tambahan(scenario, hasil):
    """Run-specific caveats from the scenario's stats (Indonesian)."""
    out = []
    if hasil.get("date_pre") and hasil.get("date_post"):
        out.append(f"Citra yang dipakai: sebelum {hasil['date_pre']}, sesudah "
                   f"{hasil['date_post']}. Yang terlihat adalah keadaan pada tanggal itu.")
    if scenario == "flood":
        if (hasil.get("pct_steep_masked") or 0) > 50:
            out.append("PERHATIAN: wilayah ini sebagian besar berlereng curam. Banjir bandang "
                       "di lembah sempit hampir tidak terlihat oleh radar satelit; angka di "
                       "atas jangan dipakai sebagai luas banjir. Andalkan laporan lapangan.")
        if hasil.get("pct_steep_masked"):
            out.append(f"Lereng curam (> 5°) tidak dihitung, sekitar "
                       f"{hasil['pct_steep_masked']:.0f}% dari kotak analisis: di sana radar "
                       "tidak bisa membedakan air dari bayangan lereng.")
        if hasil.get("pct_observed") is not None and hasil["pct_observed"] < 95:
            out.append(f"Hanya {hasil['pct_observed']:.0f}% kotak analisis terekam radar; "
                       "sebagian wilayah tidak terpantau.")
    else:
        out.append(f"Komposit tiap periode memakai paling banyak {S2_HARI_TERJERNIH} hari "
                   "citra yang paling sedikit awannya (menurut catatan awan per citra).")
    for k in ("scenes_pre", "scenes_post"):
        if hasil.get(k) == 0:
            out.append("Tidak ada citra pada salah satu periode; hasil tidak bisa dipakai.")
    return out


def tulis_ringkasan(run_dir, p, nama, catatan, sebelum, sesudah, luas, tambahan=()):
    persen = (100.0 * luas["terdampak_ha"] / luas["luas_terpantau_ha"]
              if luas["luas_terpantau_ha"] else 0.0)
    baris = [
        f"# {p['judul']} — {nama}",
        "",
        f"- Wilayah: {catatan}",
        f"- Sebelum: {sebelum[0]} s.d. {sebelum[1]}",
        f"- Sesudah: {sesudah[0]} s.d. {sesudah[1]}",
        f"- Satelit: {p['satelit']}",
        "",
        "## Hasil",
        "",
        f"- Luas {p['hasil']}: **{_ha(luas['terdampak_ha'])} ha** "
        f"({f'{persen:.1f}'.replace('.', ',')}% dari wilayah yang terpantau)",
    ]
    if "kuat_ha" in luas:
        baris.append(f"- Di antaranya perubahan kuat: {_ha(luas['kuat_ha'])} ha")
    baris += [
        f"- Luas wilayah: {_ha(luas['luas_wilayah_ha'])} ha; terpantau satelit: "
        f"{_ha(luas['luas_terpantau_ha'])} ha",
        "",
        "## Batasan",
        "",
    ] + [f"- {b}" for b in list(tambahan) + p["batasan"]] + [
        "",
        "## File",
        "",
        "- `*_map.png` / `*_map.pdf`: peta siap cetak",
        "- `*.tif`: GeoTIFF untuk QGIS",
        "- `wilayah.geojson`: batas wilayah yang dipakai",
        "- `stats.json`, `ringkasan.json`: angka lengkap",
        "",
        "Dibuat dengan earthchange. Data: Copernicus Sentinel (ESA) via Microsoft "
        "Planetary Computer; batas wilayah © kontributor OpenStreetMap (ODbL).",
    ]
    teks = "\n".join(baris) + "\n"
    with open(os.path.join(run_dir, "RINGKASAN.md"), "w") as f:
        f.write(teks)
    with open(os.path.join(run_dir, "ringkasan.json"), "w") as f:
        json.dump({"perintah": p["scenario"], "wilayah": nama, "sumber_batas": catatan,
                   "sebelum": sebelum, "sesudah": sesudah, "persen_terpantau": persen,
                   **luas}, f, indent=2)
    return teks


# ------------------------------------------------------------------ main
def _argumen(argv):
    import argparse
    ap = argparse.ArgumentParser(prog="earthchange", add_help=False)
    ap.add_argument("perintah")
    ap.add_argument("wilayah", nargs="?")
    ap.add_argument("waktu", nargs="*")
    ap.add_argument("--keluar")
    ap.add_argument("--paksa", action="store_true")
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("-h", "--help", "--bantuan", action="store_true")
    return ap.parse_args(argv)


def jalankan(argv):
    a = _argumen(argv)
    if a.help or not a.wilayah:
        print(BANTUAN)
        return 0
    p = PERINTAH[a.perintah]

    if p["jenis"] == "kejadian":
        if len(a.waktu) != 1:
            raise Gagal(f"Tulis satu tanggal kejadian, mis.: earthchange {a.perintah} "
                        f"\"{a.wilayah}\" 2026-11-08")
        sebelum, sesudah = jendela_kejadian(_tanggal(a.waktu[0]),
                                            p["sebelum_hari"], p["sesudah_hari"])
    else:
        if len(a.waktu) != 2:
            raise Gagal(f"Tulis dua tahun, mis.: earthchange {a.perintah} "
                        f"\"{a.wilayah}\" 2019 2025")
        sebelum, sesudah = jendela_tahun(*a.waktu)

    print(f"Mencari wilayah '{a.wilayah}'...")
    nama, geom, catatan = cari_wilayah(a.wilayah)
    print(f"  → {catatan}")
    lat, lon, radius = kotak_aoi(geom)
    if radius > MAX_RADIUS_KM and not a.paksa:
        raise Gagal(f"Wilayah ini sangat luas (kotak analisis sekitar {2 * radius:.0f} km, "
                    "termasuk laut di antara pulau-pulaunya). Di laptop kantor bisa butuh "
                    "berjam-jam. Pilih wilayah yang lebih kecil (kecamatan), pakai file batas "
                    "bagian yang diperlukan, atau tambahkan --paksa untuk tetap menjalankan.")

    from .detect import main as detect_main
    from .scenarios import SCENARIOS
    from . import mpc_backend
    mpc_backend.S2_MAX_SCENES = S2_HARI_TERJERNIH
    scen = p["scenario"]
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = os.path.abspath(a.keluar or os.path.join(
        os.getcwd(), "output", f"{stamp}_{a.perintah}_{_nama_aman(nama)}"))
    os.makedirs(run_dir, exist_ok=True)
    with open(os.path.join(run_dir, "wilayah.geojson"), "w") as f:
        json.dump({"type": "Feature", "properties": {"nama": nama, "sumber": catatan},
                   "geometry": geom}, f)

    print(f"{p['judul']} · {nama} · sebelum {sebelum[0]}–{sebelum[1]} · "
          f"sesudah {sesudah[0]}–{sesudah[1]}\nHasil disimpan di: {run_dir}\n")
    args = ["-s", scen, "--lat", f"{lat:.5f}", "--lon", f"{lon:.5f}",
            "-r", f"{radius}", "--pre", ":".join(sebelum), "--post", ":".join(sesudah),
            "--backend", "mpc", "-n", _nama_aman(nama), "-o", run_dir, "--map"]
    argv_lama = sys.argv
    sys.argv = ["earthchange"] + args
    try:
        detect_main()
    finally:
        sys.argv = argv_lama

    tifs = sorted(glob.glob(os.path.join(run_dir, f"{scen}_*.tif")))
    if not tifs:
        raise Gagal("Analisis selesai tetapi tidak menghasilkan peta. Jalankan lagi "
                    "dengan --debug.")
    luas = hitung_luas(tifs[0], geom, scen, SCENARIOS[scen])
    try:
        with open(os.path.join(run_dir, "stats.json")) as f:
            hasil = json.load(f).get("results", {})
    except (OSError, ValueError):
        hasil = {}
    print("\n" + tulis_ringkasan(run_dir, p, nama, catatan, sebelum, sesudah, luas,
                                 catatan_tambahan(scen, hasil)))
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    debug = "--debug" in argv
    try:
        return jalankan(argv)
    except Gagal as e:
        print(f"\nGagal: {e}", file=sys.stderr)
        return 1
    except SystemExit as e:
        if e.code in (0, None):
            return 0
        if debug:
            raise
        print(f"\nGagal: {_terjemahkan(str(e.code))}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nDibatalkan.", file=sys.stderr)
        return 130
    except Exception as e:  # noqa: BLE001
        if debug:
            raise
        nama = type(e).__name__
        if "Connection" in nama or "Timeout" in nama or "HTTP" in nama:
            pesan = ("Koneksi ke server data satelit terputus. Periksa internet dan "
                     "coba lagi.")
        else:
            pesan = f"Terjadi kesalahan tak terduga ({nama}: {e})."
        print(f"\nGagal: {pesan}\nUntuk detail teknis, jalankan lagi dengan --debug.",
              file=sys.stderr)
        return 1
