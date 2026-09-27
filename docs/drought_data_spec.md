# Spesifikasi data — kekeringan sawah (drought.ownmap.id)

Kontrak data untuk paket yang diunggah ke situs peta. Dihasilkan oleh
`earthchange -s drought-paddy` (satu lokasi) dan `-s drought-paddy-island`
(satu pulau). Versi dokumen: 27 September 2026, `earthchange` 0.1.91+.

Metodologi, asal tiap rumus, dan hasil ujinya:
[`paddy_drought.md`](paddy_drought.md). Dokumen ini hanya membahas **bentuk
datanya**.

---

## 1. Apa yang dijawab data ini

Tiga pertanyaan, per petak, bukan rata-rata kabupaten:

| Pertanyaan | Lapisan | Sumber fisik |
|---|---|---|
| Sudah ditanam belum, mundur berapa hari? | `delay_class`, `planting_doy` | Sentinel-1 VH |
| Airnya cukup dibanding musim biasanya? | **`anomaly_class`** (utama) | WaPOR ETa ÷ Kc × ET0 |
| Airnya cukup pada skala mutlak? | `adequacy_class` (audit) | idem, ambang FAO-33 |
| Sepekan ke depan bagaimana? | `outlook_class` | prakiraan hujan GFS |
| Mana yang perlu dicek lapangan? | `puso`, `alerts.geojson` | gabungan |

**Lapisan utama adalah `anomaly_class`**, bukan `adequacy_class`. Alasannya di
§9 dan wajib ikut ditampilkan.

---

## 2. Struktur berkas

Satu pulau = satu folder mandiri. Situs memuat pulau yang sedang dilihat.

```
drought.ownmap.id/data/
  national_summary.json          rekap lintas pulau + indeks pulau
  Jawa/
    web/
      cog/anomaly_class.tif      COG, EPSG:3857
      cog/adequacy_class.tif
      cog/outlook_class.tif
      cog/delay_class.tif
      cog/paddy.tif
      cog/puso.tif
      alerts.geojson             poligon yang layak dikunjungi
      legend.json                nilai → label dwibahasa → warna
      summary.json               angka utama, sumber, resolusi, batas
    Jawa_anomaly.tif             raster kontinu (audit, opsional diunggah)
    Jawa_anomaly_class.tif       mosaik EPSG:4326 (sumber COG)
    Jawa_adequacy.tif  Jawa_adequacy_class.tif
    Jawa_delay_days.tif  Jawa_delay_class.tif
    Jawa_planting_doy.tif  Jawa_outlook_class.tif
    Jawa_paddy.tif  Jawa_puso.tif
    stats.json                   rekap pulau + tabel per ubin
    tile_index.csv / .geojson    ubin yang dikerjakan
  Sumatera/  Sulawesi/  Kalimantan/  Bali-NusaTenggara/  Maluku/  Papua/
```

Nama pulau yang sah, persis seperti ini: `Jawa`, `Sumatera`, `Sulawesi`,
`Kalimantan`, `Bali-NusaTenggara`, `Maluku`, `Papua`, `lain`.

**Yang cukup untuk situs:** `web/` tiap pulau + `national_summary.json`.
Berkas `*.tif` di luar `web/` adalah produk audit dalam EPSG:4326 (termasuk
lapisan kontinu `anomaly`, `adequacy`, `delay_days`, `planting_doy` yang tidak
dipublikasikan sebagai COG); unggah bila ingin diunduh pengguna.

---

## 3. Sistem koordinat dan jaringan

| | Nilai |
|---|---|
| Jaringan analisis | EPSG:4326, langkah **0,0005° (55,66 m)** |
| Jangkar jaringan | titik asal raster Lahan Baku Sawah, `anchor` di `summary.json` |
| COG untuk web | **EPSG:3857**, `tiled=true`, blok 256×256, `compress=deflate` |
| Overview COG | faktor 2/4/8/16, hanya yang menyisakan ≥64 piksel |
| Mosaik pulau | EPSG:4326, ditempel per jendela **tanpa resampling** |

Semua ubin satu pulau berbagi satu jaringan yang sama, sehingga mosaik adalah
penyalinan jendela — bukan interpolasi. Jangan me-resample ulang mosaiknya bila
menggabungkan antar pulau; pakai `anchor` yang sama.

---

## 4. Lapisan raster

Semua COG bertipe **uint8**. Nilai di luar tabel harus diabaikan.

### 4.1 `anchor` nilai kelas

#### `anomaly_class` — lapisan utama
SI musim ini ÷ median SI musim-musim sebelumnya **pada piksel yang sama**.

| Nilai | Rasio | Label (id) | Label (en) | Warna |
|---|---|---|---|---|
| 0 | ≥ 0,95 | Normal | Normal | `#2c7bb6` |
| 1 | 0,85–0,95 | Agak kering | Slightly drier | `#abd9e9` |
| 2 | 0,70–0,85 | Lebih kering | Drier than normal | `#fdae61` |
| 3 | < 0,70 | Jauh lebih kering | Much drier than normal | `#d7191c` |
| 255 | — | tidak dinilai | no data | transparan |

#### `adequacy_class` — skala mutlak, **belum dikalibrasi**
SI = min(1,2 × ETa / (Kc × ET0), 1), ambang FAO-33.

| Nilai | SI | Label (id) | Label (en) | Warna |
|---|---|---|---|---|
| 0 | ≥ 1,00 | Cukup | Adequate | `#2c7bb6` |
| 1 | 0,85–1,00 | Defisit ringan | Mild deficit | `#abd9e9` |
| 2 | 0,65–0,85 | Defisit sedang | Moderate deficit | `#fdae61` |
| 3 | < 0,65 | Defisit berat | Severe deficit | `#d7191c` |
| 255 | — | tidak dinilai | no data | transparan |

> Kelas **0 (Cukup) praktis tidak pernah muncul**. ETa satelit di atas sawah
> tergenang terbaca ~35% di bawah Kc × ET0 bahkan saat air melimpah. Jangan
> jadikan lapisan ini headline.

#### `outlook_class` — risiko 7 hari, **hujan saja**
Ambang dan warna sama dengan `adequacy_class`. Nilai 255 = tidak dinilai.

#### `delay_class` — kemunduran tanam
| Nilai | Arti | Label (id) | Label (en) | Warna |
|---|---|---|---|---|
| 0 | < 12 hari | Tepat waktu | On time | `#1a9850` |
| 1 | 12–24 hari | Mundur 12-24 hari | 12-24 days late | `#fee08b` |
| 2 | 24–36 hari | Mundur 24-36 hari | 24-36 days late | `#fc8d59` |
| 3 | > 36 hari | Mundur >36 hari | More than 36 days late | `#b2182b` |
| **4** | tidak tanam | Belum tanam | Not planted | `#6a3d9a` |
| 255 | bukan sawah / tak dinilai | — | — | transparan |

#### `paddy` — sebaran sawah
| Nilai | Arti | Warna |
|---|---|---|
| 0 | bukan sawah | transparan (`#00000000`) |
| 1 | sawah | `#2c7bb6` |

Tanpa nodata: **0 berarti bukan sawah**, bukan "tidak diketahui".

#### `puso` — kandidat puso
| Nilai | Arti | Warna |
|---|---|---|
| 0 | tidak | transparan |
| 1 | Kandidat — perlu cek lapangan | `#b2182b` |

Tanpa nodata. **Kandidat, bukan vonis** — wajib disebut di antarmuka.

### 4.2 Jaringan bukan resolusi

Semua lapisan digambar pada 55,66 m; informasinya tidak. Nilai `native_m` ada
di `legend.json` per lapisan dan di `summary.json`:

| Lapisan | Digambar | Informasi asli |
|---|---|---|
| `paddy` | 55,66 m | 55,66 m (LBS) atau 90 m (deteksi radar) |
| `delay_class`, `planting_doy` | 55,66 m | **90 m** (radius filter bintik S1) |
| `anomaly_class`, `adequacy_class`, `puso` | 55,66 m | **300 m** (WaPOR AETI) |
| `outlook_class` | 55,66 m | **27.750 m** (GFS 0,25°) |

Zoom maksimum yang jujur untuk lapisan air kira-kira setara 300 m; di atas itu
tampilkan peringatan atau hentikan penajaman.

---

## 5. `alerts.geojson`

`FeatureCollection`, geometri `Polygon`, EPSG:4326. Tempat yang layak
dikunjungi — bukan seluruh piksel bermasalah.

```json
{
  "type": "Feature",
  "geometry": {"type": "Polygon", "coordinates": [[[110.84, -6.94], "..."]]},
  "properties": {
    "kind": "severe_deficit",
    "label": {"id": "Defisit berat", "en": "Severe deficit"},
    "area_ha": 1.53
  }
}
```

| `kind` | Asal | Label |
|---|---|---|
| `severe_deficit` | `adequacy_class == 3` | Defisit berat / Severe deficit |
| `not_planted` | `delay_class == 4` | Belum tanam / Not planted |
| `puso_candidate` | `puso == 1` | Kandidat puso / Puso candidate |

* `area_ha` dihitung pada jaringan analisis (sebelum reproyeksi), di lintang
  poligon itu sendiri.
* Poligon disederhanakan ~25 m.
* **Ambang luas minimum:** 0,5 ha untuk satu lokasi, **5 ha untuk skala pulau**
  (`summary.alerts.min_ha`). Bercak di bawah ambang tidak dimuat — pada satu
  pulau berkasnya akan puluhan MB dan isinya sebagian besar piksel campuran.
* Untuk skala nasional, sajikan sebagai vector tile (PMTiles) — GeoJSON mentah
  tidak layak di peramban.

---

## 6. `zones.geojson` (opsional)

Hanya ada bila run diberi `--zones`, yakni produk per daerah irigasi — **tidak
dihasilkan pada run pulau**. Properti tambahan per zona:

| Properti | Arti |
|---|---|
| `paddy_ha` | luas sawah dalam zona |
| `si_mean` | rata-rata kecukupan air |
| `si_p10` | persentil ke-10 (ekuitas; < 0,65 = ujung saluran tertekan) |
| `reliability` | fraksi periode dengan SI ≥ 0,80 |
| `equity_flag` | `true` bila `si_p10` di bawah 0,65 |

---

## 7. `legend.json`

Satu entri per lapisan COG. Peta **harus** mewarnai dari berkas ini, bukan dari
salinan warna di kode situs, supaya peta dan raster tidak bisa berselisih.

```json
{
  "anomaly_class": {
    "title": {"id": "Kekeringan dibanding musim biasanya",
              "en": "Drought against this field's normal"},
    "nodata": 255,
    "grid_m": 55.66,
    "native_m": 300,
    "classes": [
      {"value": 0, "colour": "#2c7bb6", "label": {"id": "Normal", "en": "Normal"}}
    ]
  }
}
```

---

## 8. `summary.json`

| Kunci | Isi |
|---|---|
| `scenario` | selalu `"drought-paddy"` |
| `island` | nama pulau (paket pulau) |
| `run_id`, `location`, `radius_km` | paket satu lokasi |
| `as_of` | **tanggal jawaban** — semua lapisan merujuk tanggal ini |
| `bbox` | `[lon_min, lat_min, lon_max, lat_max]` |
| `season` | `{start, end, baseline_seasons}` |
| `tiles` | `{in_index, run, with_products, empty, unscored_paddy_ha, orbit_pass}` |
| `tile_deg` | ukuran ubin (0,125) |
| `headline` | lihat di bawah |
| `alerts` | `{features, min_ha, note}` |
| `resolution` | `{grid, native_m, note}` |
| `sources` | id aset Earth Engine yang dipakai |
| `outlook` | `{lead_days, lead_days_wanted, gfs_run, basis}` |
| `caveats` | daftar kalimat batas — **wajib tampil** |
| `layers` | daftar lapisan COG yang tersedia |

`headline` berisi hektare:

```
paddy_ha, planted_ha, not_planted_ha, not_planted_pct,
median_delay_days, season_length_days_median,
anomaly_ha{}, planting_delay_ha{}, adequacy_ha{}, outlook_ha{},
puso_candidates_ha
```

Kunci di dalam `anomaly_ha` dan kawan-kawan adalah **label bahasa**, bukan
angka kelas (mis. `{"Normal": 12519.4, "Agak kering": 143.4}`). Jangan
mengurutkannya sendiri — urutannya mengikuti urutan kelas.

Contoh `resolution` dan `outlook` apa adanya:

```json
"resolution": {"grid": {"deg": 0.0005, "m": 55.66,
                        "anchor": [0.0, 0.0002],
                        "aligned_to": "LBS_Ind_2023_0005.tif",
                        "crs": "EPSG:4326"},
               "native_m": {"anomaly_class": 300, "delay_class": 90, "...": 0}},
"outlook": {"lead_days": 7, "lead_days_wanted": 7,
            "gfs_run": "2026-09-27T00:00:00+00:00",
            "basis": "rainfall only; irrigation deliveries not forecast"}
```

`outlook.lead_days` bisa **lebih kecil** dari `lead_days_wanted` bila run GFS
belum menerbitkan semua harinya. Tampilkan angka `lead_days`, bukan "7 hari"
yang dipatok.

---

## 9. Aturan penyajian — yang wajib ikut

Bukan hiasan. Tanpa ini angkanya akan dibaca lebih kuat daripada yang
ditanggung datanya.

1. **`anomaly_class` sebagai lapisan pertama.** `adequacy_class` boleh dipilih
   pengguna, dengan label "skala mutlak, belum dikalibrasi".
2. **Isi `summary.caveats` harus dapat dibaca** dari halaman peta (panel info,
   bukan hanya tooltip). Enam kalimat, dwibahasa, sudah disiapkan.
3. **`puso` = kandidat**, sebut "perlu cek lapangan" di legenda maupun popup.
4. **Prakiraan hanya hujan.** Sebutkan bahwa pasokan irigasi tidak diprakirakan
   — peta menunjukkan di mana hujan saja tidak menutup kebutuhan.
5. **Tanam ~60 hari terakhir bersifat provisional** (banjir terdeteksi, belum
   terkonfirmasi). Jangan sajikan sebagai "belum tanam".
6. **`native_m` per lapisan** tampil di info lapisan; lapisan air adalah 300 m.
7. **`tiles.unscored_paddy_ha`** harus muncul di ringkasan pulau: itu sawah yang
   ada di indeks tetapi tidak tertutup produk (umumnya lubang liputan radar).
   Total pulau tanpa angka ini menyesatkan.

---

## 10. Kadens dan versi

| | |
|---|---|
| Siklus | tiap **12 hari** (ulangan Sentinel-1) |
| Penentu tanggal | jeda WaPOR AETI ~2 pekan → `as_of` mengikutinya |
| Prakiraan | dapat disegarkan harian; `outlook.gfs_run` menyatakan run-nya |
| Lapisan sawah | Lahan Baku Sawah 2023, tahunan |

Setiap unggahan menimpa folder pulau yang sama. Untuk riwayat, simpan per
`as_of` (`Jawa/2026-09-27/...`) — lapisan kelas kecil (beberapa MB per pulau).

---

## 11. Yang tidak ada di data ini

Supaya tidak dicari-cari:

* **Tidak ada mosaik nasional 50 m.** Satu lapisan seluruh kepulauan adalah 3,1
  miliar piksel per band. Yang bersifat nasional adalah aritmetika
  (`national_summary.json`) dan indeks pulau.
* **Tidak ada `zones.geojson` pada run pulau** — indeks per daerah irigasi
  adalah produk per skema.
* **Tidak ada fase pertumbuhan padi** (vegetatif/generatif/dst). Untuk itu pakai
  model di `rice-growth-stage-mapping`.
* **Tidak ada prakiraan pasokan irigasi.** Tidak bisa diprakirakan.
* **Kelas "Cukup" pada `adequacy_class`** praktis kosong; lihat §4.1.
* **Papua, Maluku, dan sebagian Kalimantan** bukan irigasi teknis; `summary.caveats`
  pulau tersebut memuat catatan tambahan yang harus ikut tampil.

---

## 12. Contoh penyajian COG

Dengan `titiler` atau `rio-tiler`, warnai dari `legend.json`:

```
GET /cog/tiles/{z}/{x}/{y}.png
    ?url=.../Jawa/web/cog/anomaly_class.tif
    &colormap={"0":[44,123,182,255],"1":[171,217,233,255],
               "2":[253,174,97,255],"3":[215,25,28,255]}
    &nodata=255
```

Nilai 255 harus transparan. Untuk `paddy` dan `puso` yang tanpa nodata,
petakan 0 ke alfa 0.
