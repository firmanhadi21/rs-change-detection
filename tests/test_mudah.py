"""Short Indonesian commands (earthchange banjir/hutan/...).

What can go wrong for a non-specialist user is a wrong window, the wrong
place, or hectares counted over a box instead of the named area — so that is
what these cover. All offline.
"""

import datetime as dt
import json

import numpy as np
import pytest

from earthchange import mudah

HARI_INI = dt.date(2026, 11, 16)


# ------------------------------------------------------------------ dates
def test_event_windows_before_and_after():
    pre, post = mudah.jendela_kejadian(dt.date(2026, 11, 8), 45, 12, hari_ini=HARI_INI)
    assert pre == ("2026-09-24", "2026-11-07")
    # after-window is cut at today, never in the future
    assert post == ("2026-11-08", "2026-11-16")


def test_event_in_future_is_refused():
    with pytest.raises(mudah.Gagal, match="belum terjadi"):
        mudah.jendela_kejadian(dt.date(2026, 12, 1), 45, 12, hari_ini=HARI_INI)


def test_year_windows():
    pre, post = mudah.jendela_tahun("2019", "2025", hari_ini=HARI_INI)
    assert pre == ("2019-01-01", "2019-12-31")
    assert post == ("2025-01-01", "2025-12-31")


def test_current_year_ends_today():
    _pre, post = mudah.jendela_tahun(2020, 2026, hari_ini=HARI_INI)
    assert post == ("2026-01-01", "2026-11-16")


@pytest.mark.parametrize("t1,t2,pesan", [
    (2025, 2019, "lebih awal"),
    (2015, 2020, "sejak 2017"),
    (2020, 2030, "belum terjadi"),
    ("dua ribu", 2020, "tidak dikenali"),
])
def test_bad_years(t1, t2, pesan):
    with pytest.raises(mudah.Gagal, match=pesan):
        mudah.jendela_tahun(t1, t2, hari_ini=HARI_INI)


def test_bad_date_text():
    with pytest.raises(mudah.Gagal, match="tahun-bulan-tanggal"):
        mudah._tanggal("8 November")


# ------------------------------------------------------------------ area
SQUARE = {"type": "Polygon",
          "coordinates": [[[97.0, 4.0], [97.2, 4.0], [97.2, 4.2], [97.0, 4.2], [97.0, 4.0]]]}


def test_boundary_preferred_over_point():
    hits = [{"category": "place", "type": "village", "display_name": "Pining village",
             "geojson": {"type": "Point", "coordinates": [97.1, 4.1]}},
            {"category": "boundary", "display_name": "Pining, Gayo Lues",
             "geojson": SQUARE}]
    polys, points = mudah.pilih_hasil(hits)
    assert [h["display_name"] for h in polys] == ["Pining, Gayo Lues"]
    assert len(points) == 1


def test_a_school_is_not_an_area():
    # "Weda Tengah, Halmahera Tengah" once resolved to a school
    hits = [{"category": "amenity", "type": "school",
             "display_name": "SMA Negeri 1 Halmahera Tengah",
             "geojson": {"type": "Point", "coordinates": [127.9, 0.4]}}]
    assert mudah.pilih_hasil(hits) == ([], [])


def test_square_covers_area():
    lat, lon, r = mudah.kotak_aoi(SQUARE)
    assert (lat, lon) == pytest.approx((4.1, 97.1))
    # 0.2 deg is ~22 km wide, so the half-side is ~11 km plus a margin
    assert 11.0 < r < 12.0


def test_circle_for_point_only():
    g = mudah.lingkaran(4.0, 97.0, 5.0)
    _lat, _lon, r = mudah.kotak_aoi(g)
    assert r == pytest.approx(5.0 * 1.02, rel=0.02)


def test_boundary_file_is_read(tmp_path):
    p = tmp_path / "desa.geojson"
    p.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {}, "geometry": SQUARE}]}))
    nama, geom, catatan = mudah.cari_wilayah(str(p))
    assert nama == "desa"
    assert geom["type"] == "MultiPolygon"
    assert "file" in catatan


def test_cached_name_needs_no_network(tmp_path, monkeypatch):
    monkeypatch.setattr(mudah, "CACHE_DIR", str(tmp_path))

    def no_network(_nama):
        raise AssertionError("network used")

    (tmp_path / "pining_gayo_lues.json").write_text(json.dumps(
        {"nama": "Pining", "geom": SQUARE, "catatan": "cache"}))
    monkeypatch.setattr(mudah, "_cari_nominatim", no_network)
    assert mudah.cari_wilayah("Pining, Gayo Lues")[0] == "Pining"


def test_unknown_name(tmp_path, monkeypatch):
    monkeypatch.setattr(mudah, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(mudah, "_cari_nominatim", lambda _n: [])
    with pytest.raises(mudah.Gagal, match="tidak ditemukan"):
        mudah.cari_wilayah("Tempat Yang Tidak Ada")


# ------------------------------------------------------------------ hectares
def _tif(path, data):
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin
    # 0.001 deg pixels over the square's west half and beyond
    with rasterio.open(path, "w", driver="GTiff", height=data.shape[0], width=data.shape[1],
                       count=1, dtype="float32", crs="EPSG:4326",
                       transform=from_origin(97.0, 4.2, 0.001, 0.001), nodata=np.nan) as dst:
        dst.write(data.astype("float32"), 1)


def test_flood_hectares_counted_inside_boundary_only(tmp_path):
    # 400 x 400 px = 0.4 deg box; the boundary is its NW 0.2 x 0.2 deg quarter
    data = np.full((400, 400), np.nan)
    data[:200, :200] = 1.0      # flood inside the boundary
    data[200:, 200:] = 1.0      # flood outside it: must not count
    tif = tmp_path / "flood.tif"
    _tif(tif, data)
    out = mudah.hitung_luas(str(tif), SQUARE, "flood", {})
    # 0.2 deg x 0.2 deg at 4.1 N ~ 22.2 km x 22.1 km ~ 49,000 ha
    assert out["terdampak_ha"] == pytest.approx(out["luas_wilayah_ha"], rel=0.01)
    assert 48000 < out["luas_wilayah_ha"] < 50000
    assert out["luas_terpantau_ha"] == out["luas_wilayah_ha"]


def test_optical_thresholds(tmp_path):
    data = np.full((400, 400), 0.0)
    data[:100, :200] = -0.2     # loss past thr (-0.15), not severe
    data[100:150, :200] = -0.4  # severe
    data[150:200, :200] = np.nan  # cloud: not observed
    tif = tmp_path / "dndvi.tif"
    _tif(tif, data)
    cfg = {"thr": -0.15, "severe": -0.30, "direction": "loss"}
    out = mudah.hitung_luas(str(tif), SQUARE, "deforestation", cfg)
    w = out["luas_wilayah_ha"]
    assert out["terdampak_ha"] == pytest.approx(0.75 * w, rel=0.02)
    assert out["kuat_ha"] == pytest.approx(0.25 * w, rel=0.02)
    assert out["luas_terpantau_ha"] == pytest.approx(0.75 * w, rel=0.02)


# ------------------------------------------------------------------ messages
def test_mountain_warning():
    notes = mudah.catatan_tambahan("flood", {"pct_steep_masked": 96.0,
                                             "date_pre": "2026-11-06",
                                             "date_post": "2026-11-12"})
    assert any("PERHATIAN" in n for n in notes)
    assert any("2026-11-12" in n for n in notes)


def test_known_error_translated():
    assert "radar" in mudah._terjemahkan("No Sentinel-1 orbit covers both windows (MPC): [3, 0]")


def test_help_without_area(capsys):
    assert mudah.main(["banjir"]) == 0
    assert "earthchange banjir" in capsys.readouterr().out


def test_missing_date_is_plain_indonesian(capsys):
    assert mudah.main(["banjir", "Pining"]) == 1
    assert "tanggal kejadian" in capsys.readouterr().err
