# Satellite Environmental Monitoring & Change Detection

[![PyPI](https://img.shields.io/pypi/v/earthchange.svg)](https://pypi.org/project/earthchange/)
[![Python](https://img.shields.io/pypi/pyversions/earthchange.svg)](https://pypi.org/project/earthchange/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-tutorial-blue.svg)](https://firmanhadi21.github.io/rs-change-detection/)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21370696.svg)](https://doi.org/10.5281/zenodo.21370696)

Instalasi: `pip install 'earthchange[all]'` — perintah `earthchange` & `earthmap`.

**Pemantauan lingkungan dan deteksi perubahan berbasis penginderaan jauh** —
24 skenario: bahaya kebakaran (FDRS), paparan asap, lintasan asap, kekeringan,
suhu permukaan, banjir, deforestasi, tambang, urbanisasi, dan perubahan air.
Berjalan di Google Earth Engine atau Microsoft Planetary Computer (Python).
Pilih skenario + lokasi; hasilnya PNG, GeoTIFF tergeoreferensi, statistik JSON,
dan — untuk rantai kebakaran-asap — catatan Markdown yang dapat disitasi serta
ringkasan siap kirim. Setiap keluaran membawa batasannya sendiri.

Studi kasus unggulan repо ini: **investigasi tambang emas ilegal (PETI) di Capkala**,
Kalimantan Barat — lengkap sampai video dokumenter (lihat bagian bawah).

## Mengapa perangkat lunak ini ada

Data satelit sudah gratis bertahun-tahun. Kemampuan memakainya belum.

Citranya ada — Sentinel, Landsat, MODIS, berpuluh tahun, bisa diunduh siapa saja.
Yang berdiri di antara citra itu dan sebuah jawaban adalah tumpukan hal yang perlu
berbulan-bulan untuk dikuasai: penapisan awan, sistem proyeksi, indeks mana untuk
pertanyaan mana, ambang berapa yang pantas disebut "berubah", dan bagaimana
mengubah raster menjadi angka yang bisa ditindaklanjuti orang. Sementara mereka
yang paling membutuhkan jawabannya — penyuluh kehutanan di kabupaten, peneliti
lembaga swadaya, wartawan yang dikejar tenggat, dosen yang menyiapkan kuliah,
mahasiswa yang tinggal punya tiga bulan — justru sering kali adalah orang-orang
yang tidak punya bulan-bulan itu.

Maka pertanyaan yang diajukan paket ini sempit saja: **bisakah satu baris perintah
mengerjakan seluruhnya?**

### Tujuan

- **Satu perintah untuk satu pertanyaan.** `earthchange -s deforestation --city
  "Ketapang" --map` seharusnya cukup. Tidak perlu menulis skrip Earth Engine, tidak
  perlu memilih ambang, tidak perlu mengurus proyeksi.
- **Dikalibrasi di tempat ia dipakai.** Ambang kelas bahaya kebakaran mengikuti
  BMKG, bukan Kanada. Faktor panjang hari memakai konvensi ekuatorial, karena tabel
  bakunya disusun untuk 46°LU. Drought Code dipimpinkan di atas FWI, karena
  kebakaran gambut didorong pengeringan lapisan dalam. Kualitas udara memakai ISPU.
  Perkakas global dikalibrasi untuk seluruh dunia — yang berarti tidak untuk tempat
  mana pun secara khusus.
- **Keluaran yang benar-benar bisa dipakai.** Lembar peta A4 siap cetak, GeoTIFF
  yang langsung terbuka di QGIS, statistik dalam JSON, teks dwibahasa.
- **Data Anda sendiri, bukan hanya data global.** Lahan baku sawah, batas fungsi
  kawasan, peta gambut resmi — silangkan dengan data satelit publik. Platform
  global tidak bisa membaca berkas lokal Anda; inilah yang membedakan "Kalimantan
  Barat kering" dari "87% cagar alam ini kering".
- **Jujur tentang batasnya.** Tiap keluaran menyebutkan apa yang tidak bisa ia
  katakan: MODIS meremehkan kebakaran gambut, ERA5-Land meratakan cuaca pada 11 km,
  jumlah titik panas bukan luas terbakar. Perangkat yang menyembunyikan batasnya
  akan menyesatkan tepat pada saat ia paling dipercaya.
- **Gratis, terbuka, dapat disitasi.** Lisensi MIT, DOI Zenodo.

### Harapan

Ukuran keberhasilan paket ini bukan jumlah unduhan.

Ukurannya adalah apakah ada analisis yang tadinya tidak akan pernah terjadi,
akhirnya terjadi — karena orang yang perlu menjawab pertanyaannya tidak lagi harus
lebih dulu menjadi ahli penginderaan jauh. Seorang dosen memakainya untuk mengajar.
Seorang mahasiswa menyelesaikan skripsinya dengannya. Sebuah lembaga menerbitkan
angka yang bisa diperiksa orang lain. Seorang pejabat kabupaten melihat kawasan
mana yang sedang mengering, sebelum ia terbakar.

Dan harapan yang lebih jauh: bahwa orang mengambil pendekatan ini untuk tempat
mereka sendiri. Ambang BMKG hanya cocok untuk Indonesia, tetapi gagasan bahwa
sebuah perkakas harus dikalibrasi untuk tempat ia dipakai — dan harus mengatakan
apa yang tidak diketahuinya — berlaku di mana saja.

> 📚 **Tutorial hands-on (GitHub Pages):** https://firmanhadi21.github.io/rs-change-detection/
> — panduan langkah demi langkah (dwibahasa 🇮🇩/🇬🇧, ada tombol EN/ID) agar siapa pun bisa memakai & menyesuaikan alat ini.

```bash
python3 detect.py --list                                        # daftar skenario
python3 detect.py -s deforestation --lat -3.333 --lon 122.25    # deteksi deforestasi
python3 detect.py -s flood --lat 27.2 --lon 68.3 \
    --pre 2022-07-01:2022-07-25 --post 2022-08-20:2022-09-10     # pemetaan banjir
```

---

## Instalasi

Alat inti dikemas sebagai paket Python **`earthchange`** dengan perintah `earthchange`
(dan `earthmap`). Dependensi berat bersifat opsional (*extras*):

```bash
pip install 'earthchange[gee]'       # backend Earth Engine (butuh akun GEE)
pip install 'earthchange[mpc,maps]'  # Planetary Computer + peta (tanpa akun)
pip install 'earthchange[all]'       # semuanya

earthchange -s deforestation --lat -3.333 --lon 122.25 --map
earthmap output/<run-id>             # render ulang peta
```

Dari checkout sumber (repo ini) tanpa instalasi, `python3 detect.py …` tetap
berfungsi (shim ke paket). Untuk kembangkan: `pip install -e '.[all]'`.
Panduan rilis PyPI ada di [`PUBLISHING.md`](PUBLISHING.md).

> Contoh perintah di bawah memakai `python3 detect.py …`; setelah instal paket,
> ganti dengan `earthchange …` (argumen identik).

---

## Deteksi Perubahan Multiguna — `detect.py`

Uji: `pip install 'earthchange[dev]'` lalu `pytest -m "not network"` — berjalan
luring dalam ±1 detik. `pytest` tanpa penanda juga menguji bahwa berkas
meteorologi GDAS1 yang dirujuk benar-benar ada di S3 publik ARL. Uji yang
memerlukan HYSPLIT akan dilewati bila `hyts_std` tidak terpasang.

Bantuan per skenario: `earthchange -s <skenario> --help` hanya menampilkan opsi
yang berlaku untuk skenario itu (dari 106 opsi, biasanya 20–30), lengkap dengan
satu baris tentang apa yang dilaporkannya. `--help` tanpa `-s` tetap menampilkan
semuanya.

Satu perintah: `-s <skenario>` memilih **metode** yang tepat, lokasi lewat
`--lat/--lon`, `-l 'lat,lon'`, **`--city 'Nama, Negara'`** (geocoding OpenStreetMap
gratis), atau `--site NAMA`.

| Skenario | Metode | Sensor |
|----------|--------|--------|
| `smoke-track` | Lintasan asap → kipas lintasan + daftar kabupaten terlintasi. Dua mesin: **kinematik** (bawaan, angin ERA5 100 m, tanpa binary — **ILUSTRASI, bukan atribusi**) dan **`--engine hysplit`** (NOAA ARL HYSPLIT + GDAS1, gerak vertikal nyata, mendukung `--direction backward` dari kabupaten ber-PM2.5 tertinggi atau dari `--receptors "Nama,lon,lat; …"`). Perlu `pip install 'earthchange[track]'`; mesin HYSPLIT perlu `hyts_std` (gratis) | ERA5 / GDAS1 + FIRMS + CAMS |
| `smoke-exposure` | Paparan asap: person-day per kelas ISPU per kabupaten/kota, dipilah balita & lansia (WorldPop) → laporan + peta panas kabupaten×hari | CAMS + WorldPop + GAUL |
| `smoke-video` | Animasi peta asap kebakaran 1080×1080 (MP4+GIF): relief 3-D forge3d, asap CAMS asli, titik api VIIRS 7 hari, penghitung langsung. **Tanpa akun GEE** — semua sumber HTTP publik. Perlu `pip install 'earthchange[video]'` + ffmpeg | CAMS + FIRMS VIIRS + AWS Terrain |
| `fire-record` | Catatan musim kebakaran per kawasan yang dapat dihitung ulang: lintasan DC, tanggal ambang BMKG terlampaui, titik panas, luas terbakar → catatan Markdown yang dapat disitasi **+ peta dua panel** (DC puncak musim; titik panas & bekas terbakar, keduanya di bawah batas kawasan) | ERA5-Land + FIRMS + MCD64A1 |
| `fire-danger` | Peringkat bahaya kebakaran (Sistem FWI Kanada): FFMC/DMC/DC/ISI/BUI/FWI dari cuaca ERA5-Land. DC & BUI memimpin — gambut didorong pengeringan lapisan dalam | ERA5-Land |
| `imagery` | Citra saja: GeoTIFF reflektansi 6 band + pratinjau warna alami & SWIR. `--date` satu tanggal atau `START:END` untuk komposit | Sentinel-2 / Landsat |
| `deforestation` | Kehilangan NDVI (ΔNDVI < ambang) | Sentinel-2 |
| `mining` | SIRAD radar temporal **+** kehilangan NDVI | Sentinel-1 + S2 |
| `urbanization` | Kenaikan NDBI (indeks terbangun) | Sentinel-2 |
| `urban-trend` | Timing built-up 3 epoch → komposit RGB | Landsat 5, 8/9 |
| `urban-history` | Built-up per **dekade sejak 1980** (GHSL + Landsat) + infografik | GHSL + Landsat |
| `flood` | Luas genangan SAR — **satu** scene pra/pasca, orbit sama | Sentinel-1 VV |
| `disturbance` | Dampak banjir/longsor via **perubahan VH** (untuk medan) | Sentinel-1 |
| `burn` | dNBR (severity kebakaran) | Sentinel-2 |
| `water` | Perubahan NDWI (air permukaan) | Sentinel-2 |
| `coastline` | Garis pantai + perubahan garis pantai (abrasi/akresi) + laju surut m/thn | S1 SAR / S2 / Landsat |
| `transit-access` | % populasi yang menjangkau transportasi publik (SDG 11.2.1) | WorldPop + OSM |
| `island-heat` | Tren SST + LST + wet-bulb (panas lembab) pulau kecil | OISST / Landsat / ERA5 |
| `urban-heat` | Pulau panas perkotaan (SUHII) + peta titik panas + tren dekadal | GHSL + Landsat + MODIS |
| `forest-history` | Deforestasi multi-periode: peta tahun-kehilangan + tren luas hutan | S2 / Landsat NDVI |
| `population-change` | Perubahan populasi 2 epoch: infografik siluet-pulau gaya Miloš + peta + ekspor forge3d | GHSL GHS_POP |
| `haze` | Asap & kualitas udara karhutla: PM2.5 (ISPU), indeks aerosol, titik panas | CAMS + Sentinel-5P + FIRMS |
| `fire-history` | Riwayat karhutla: luas terbakar/tahun (gambut vs mineral), peta frekuensi, musim | MODIS MCD64A1 + FIRMS |
| `drought` | Kekeringan: anomali hujan (z-score), VCI/TCI/VHI, ENSO + IOD; `--cdi` menggabungkan meteorologis/pertanian/vegetasi jadi satu peta kelas, `--cdi-mask` membacanya hanya di atas sawah | CHIRPS/ERA5-Land/IMERG + MODIS + OISST |

```bash
# Sintaks umum
python3 detect.py -s <skenario> --lat <LAT> --lon <LON> [--radius KM] \
    [--pre START:END] [--post START:END] [-n NAMA]

# Contoh
python3 detect.py -s mining --site konawe               # pakai preset sites.py
python3 detect.py -s urbanization --city "Surabaya, Indonesia" -r 20   # geocoding nama tempat
python3 detect.py -s urbanization --lat -6.2 --lon 106.8 --radius 12
python3 detect.py -s burn --lat -7.5 --lon 110.4 \
    --pre 2025-08-01:2025-08-20 --post 2025-09-10:2025-09-30

# Mining/SIRAD: atur sendiri 3 periode (R/G/B) dengan --epochs
python3 detect.py -s mining --site konawe \
    --epochs 2024-01-01:2024-12-31,2025-01-01:2025-12-31,2026-01-01:2026-06-30
```

> `--epochs W1,W2,W3` menetapkan tiga periode untuk **mining/SIRAD** (kanal R/G/B)
> maupun **urban-trend** (epoch). Tanpa itu, dipakai periode default dari skenario.

**Output per run** (klip **persegi**, bukan lingkaran). Setiap run menulis ke
folder ber-ID unik **`output/<timestamp>_<skenario>_<nama>_<token>/`** berisi:

| Berkas | Isi |
|--------|-----|
| `<skenario>_<produk>_<nama>.png` | Quick-look berwarna |
| `<skenario>_<produk>_<nama>.tif` | GeoTIFF resolusi penuh (buka di QGIS) |
| `<skenario>_<produk>_<nama>.meta.json` | Metadata (untuk render peta ulang) |
| `<skenario>_<produk>_<nama>_map.{pdf,png}` | Peta (bila `--map`) |
| `stats.json` | Statistik (mean Δ, % area terdampak, dll.) |

Contoh: `output/20260708-222632_deforestation_m3p333_122p25_fac24e/`.
Folder `output/` di-*gitignore*.

Setiap skenario optik memakai **median composite banyak scene** dengan masking
awan per-piksel (SCL), jadi hasil bebas awan. Skenario radar (SIRAD/banjir)
memilih arah orbit Sentinel-1 yang punya cakupan otomatis.

**Menambah skenario:** tambahkan entri di [`scenarios.py`](scenarios.py)
(indeks/metode + ambang + palet). Indeks spektral ada di [`indices.py`](indices.py).

### Metode alternatif per skenario (`--method`)

Skenario optik tidak terikat pada satu indeks. Ganti metode dengan `--method`
(berlaku di kedua backend):

```bash
python3 detect.py -s urbanization --lat -6.23 --lon 106.85 --method IBI
python3 detect.py -s urbanization --lat -6.23 --lon 106.85 --method UI --backend mpc
python3 detect.py -s urbanization --lat -6.23 --lon 106.85 --method NDBI --thr 0.12
```

Metode built-up untuk **urbanisasi**:

| Metode | Sensor | Catatan |
|--------|--------|---------|
| `NDBI` (default), `UI`, `BU` (=NDBI−NDVI), `IBI` | Sentinel-2 | IBI di-*clamp* ke [−1,1] |
| `NDISI`, `EBBI` | **Landsat 8/9** (pakai band termal) | otomatis beralih ke Landsat |

Tiap metode punya ambang default sendiri (`METHOD_DEFAULTS` di `indices.py`);
sesuaikan lewat `--thr`/`--severe`.

```bash
# Indeks termal — otomatis memakai Landsat 8/9 (juga jalan di --backend mpc)
python3 detect.py -s urbanization --lat -6.23 --lon 106.85 --method NDISI
python3 detect.py -s urbanization --lat -6.23 --lon 106.85 --method EBBI --backend mpc
```

**NDISI/EBBI** butuh band termal (TIR), jadi memuat **Landsat C2‑L2**
(`LANDSAT/LC08|LC09/C02/T1_L2` di GEE; `landsat-c2-l2` di MPC) — resolusi 30 m.
Indeks termal peka pada kondisi akuisisi (suhu permukaan berbeda antar-tanggal),
jadi kalibrasi ambang untuk area Anda.

### Landsat untuk baseline pra-2015 (`--sensor landsat`) & masking air

Sentinel-2 baru ada sejak ~2015. Untuk **baseline lama** — mis. deforestasi sejak
**1980-an** — pakai `--sensor landsat`: komposit reflektansi Landsat (arsip **sejak
1984** via Landsat 5 TM; L7 dilewati karena SLC-off), 30 m. Berlaku untuk skenario
optik (NDVI/NBR/NDBI, dst.) di kedua backend (di GEE paling andal untuk arsip lama).

```bash
# Deforestasi 1990 -> 2022 dari Landsat, air di-mask otomatis
earthchange -s deforestation --lat 1.0 --lon 102.5 --radius 8 --sensor landsat \
    --pre 1990-01-01:1992-12-31 --post 2021-01-01:2023-12-31
```

**Masking air (default).** Untuk analisis berbasis NDVI (deforestasi/burn/urban),
laut, sungai, dan danau (MNDWI>0 pada kedua tanggal) **otomatis di-mask** agar tidak
salah terhitung sebagai perubahan vegetasi — penting di **pulau & pesisir**. Matikan
dengan `--no-water-mask`. Skenario `water` (NDWI) tidak di-mask (justru soal air).

> **Catatan:** di backend MPC, komposit Sentinel-2 kini **diselaraskan** untuk
> pergeseran *processing baseline 04.00* (offset −1000 DN sejak 2022‑01‑25) — tanpa
> ini, NDVI yang melintasi batas 2022 (mis. 2019 vs 2023) bias dan memalsukan
> "kehilangan vegetasi". GEE sudah memakai koleksi harmonized.

### Perubahan multi-tahun (mis. 2010 · 2015 · 2020)

**Penting:** Sentinel-2 baru tersedia sejak ~2015/2016 — **tidak bisa** melihat
2010. Untuk analisis historis pakai skenario **`urban-trend`** yang berbasis
**Landsat** (arsip sejak 1984, memakai Landsat 5/8/9 — L7 dilewati karena SLC-off) dan memetakan
**timing** pertumbuhan built-up pada 3 epoch sekaligus sebagai citra RGB
(epoch-1 = Merah, epoch-2 = Hijau, epoch-3 = Biru):

```bash
python3 detect.py -s urban-trend --lat -6.30 --lon 107.15 --radius 10 --map
# epoch kustom (default 2010/2015/2020):
python3 detect.py -s urban-trend --lat -6.30 --lon 107.15 \
    --epochs 2010-01-01:2010-12-31,2015-01-01:2015-12-31,2020-01-01:2020-12-31
```

Interpretasi: **putih** = terbangun di semua epoch (kota lama), **biru** =
tumbuh hanya di epoch terakhir (paling baru), **cyan** = sejak epoch ke-2.
Statistik: % built-up tiap epoch + % built-up baru. Jalan juga di `--backend mpc`.
Contoh (Cikarang/Bekasi): built-up 10% (2010) → 23% (2020), 15% baru.

> Untuk perbandingan **dua** tanggal saja, jalankan skenario optik/termal biasa
> dengan `--pre`/`--post` (mis. `--method NDISI` untuk memakai band termal Landsat).

### Sejarah urban per dekade — `urban-history` (+ close-up PlanetScope opsional)

Memetakan **ekspansi built-up & kehilangan vegetasi per dekade sejak 1980**,
menggabungkan **GHSL GHS-BUILT-S** (built-up otoritatif 1980–2025, hanya GEE)
dengan NDBI/NDVI Landsat. Menghasilkan: peta **"dekade pertama terbangun"** (kota
meluas cincin demi cincin), panel per dekade, grafik tren built-up & vegetasi,
peta konversi vegetasi→urban, overlay jalan OSM, dan **infografik satu halaman**
(PNG + PDF). TM & OLI tidak digabung lintas patahan sensor 2011–2013: epoch TM
(1990/2000/2010, sebanding) dipakai untuk peta vegetation-loss, epoch OLI
(2015/2020/2025, sebanding satu sama lain) dilaporkan terpisah.

```bash
earthchange -s urban-history --city "Jakarta, Indonesia" --radius 45
# Contoh Jabodetabek: built-up 507 → 872 km² (1980→2025), +72%.
```

**Hybrid PlanetScope (opsional, `--planet`).** GHSL menemukan sel **paling banyak
berubah**, lalu PlanetScope harian (Data API, 4-band → **NDVI**) meng-close-up area
kecil itu pada **~3 m**. Hemat kuota: pencarian **gratis** (tak memakai kuota),
unduhan (order ter-*clip*) hanya terjadi dengan `--planet-confirm`.

```bash
# dry-run (gratis): urban-history + hotspot otomatis + pencarian Planet + estimasi kuota
earthchange -s urban-history --lat -6.2 --lon 106.85 --radius 45 --planet
# lalu benar-benar ambil scene ter-clip & buat close-up (memakai kuota):
earthchange -s urban-history --lat -6.2 --lon 106.85 --radius 45 \
    --planet --planet-confirm --hotspot-from 2015 --hotspot-to 2025
```

Kunci Planet dibaca dari `--planet-key`, `$PLANET_API_KEY`, atau
`~/.planet.json` / `~/planet.conf` / `~/.config/planet.*`. Tanpa `--planet`,
aplikasi **tidak menyentuh** PlanetScope sama sekali (tanpa kunci, tanpa kuota).
`--hotspot-from/--hotspot-to` memilih periode perubahan GHSL; `--planet-pre/--planet-post`
tanggal citra Planet.

### Garis pantai & perubahan garis pantai — `coastline`

Mengekstrak **batas laut–darat** dan memetakan **perubahan garis pantai**
(abrasi/akresi) serta **laju surut (m/tahun)**. Keluaran raster **dan** vektor
GeoJSON (`coastline.geojson`, `sea.geojson`) untuk QGIS.

Tiga sensor lewat `--coast-method`:

| Metode | Sumber | Catatan |
|--------|--------|---------|
| `sar` (default) | Sentinel-1 VV | Tembus awan, ~10 m — cepat & andal |
| `optical` | Sentinel-2 MNDWI + Otsu + marching-squares | **Sub-piksel**, 10 m, sejak 2015 |
| `landsat` | MNDWI (L5/8-9), 30 m | **Arsip sejak 1984** — perubahan multi-dekade |

```bash
# Garis pantai satu tanggal (SAR)
earthchange -s coastline --lat -6.95 --lon 110.45 --radius 8

# Perubahan: abrasi (darat→laut) & akresi (laut→darat) antar dua tanggal
earthchange -s coastline --lat -6.95 --lon 110.45 --radius 8 \
    --pre 2016-01-01:2016-12-31 --post 2025-01-01:2025-12-31

# Deret waktu periodik + transek laju surut (m/thn), Landsat sejak 1990-an
earthchange -s coastline --coast-method landsat --lat -6.95 --lon 110.45 --radius 10 \
    --epochs 1994-01-01:1996-12-31,2014-01-01:2016-12-31,2023-01-01:2025-12-31
```

Mode deret waktu (`--epochs`) menulis garis pantai per epoch, peta
`shorelines_map.png` (berwarna per tahun), grafik tren, dan analisis **transek**
(`transects.geojson` + `transects_map.png`, `--transect-spacing` default 500 m)
dengan laju perubahan **m/tahun** (merah = surut). Statistik: laju rata-rata/median,
% pantai yang surut. Contoh Pekalongan 1994→2023: median **−2,3 m/thn**, 84% pantai
surut. Metode `optical`/`landsat` butuh `earthchange[maps]` (scikit-image, shapely).

**Transek kustom (`--transects-file`).** Di teluk kompleks, transek otomatis bisa
salah arah. Anda dapat menggambar sendiri transek melintang-pantai di QGIS,
menyimpannya sebagai GeoJSON `LineString` (titik pertama = sisi darat), lalu:

```bash
earthchange -s coastline --coast-method landsat --city "Pekalongan" --radius 12 \
    --epochs 1994-01-01:1996-12-31,2014-01-01:2016-12-31,2023-01-01:2025-12-31 \
    --transects-file transek_saya.geojson
```

Setiap transek dipotong dengan garis pantai tiap epoch, lalu jarak-vs-tahun
diregresi menjadi laju **m/tahun** (mengikuti pendekatan CoastSat, MIT-native).

> **Catatan:** di pantai tambak (mis. Demak/Pekalongan), tambak yang
> tersambung ke laut ikut terhitung sebagai "laut", sehingga angka abrasi
> mencampur surut nyata dengan genangan akibat penurunan tanah (rob). Transek
> otomatis bisa salah arah di teluk kompleks — median dipakai sebagai angka utama.
>
> **Soal koreksi pasang-surut:** garis pantai di sini diambil dari **komposit median**
> per epoch, sehingga sudah **ter-rata-rata terhadap pasang** (waterline ≈ muka air
> rata-rata, bukan satu ketinggian pasang sesaat). Koreksi pasang per-scene ala
> CoastSat hanya berlaku untuk citra per-tanggal, bukan komposit — jadi tidak
> ditambahkan agar tidak memberi kesan presisi yang keliru.

### Akses transportasi publik (SDG 11.2.1) — `transit-access`

Menghitung **berapa persen populasi yang dapat menjangkau halte/stasiun dengan
berjalan kaki** — indikator resmi **SDG 11.2.1** (angka di balik pernyataan seperti
"transportasi publik kini menjangkau 60% populasi perkotaan dunia"). Aksesibilitas
diukur **menyusuri jaringan jalan** (bukan sekadar lingkaran buffer), sehingga
sungai atau jalan bebas-hambatan tanpa penyeberangan tetap memutus akses meski
halte dekat secara garis lurus.

Cara kerja: (1) jaringan pejalan kaki dari OpenStreetMap, (2) halte dari
`--transit-file` Anda **atau** otomatis dari OSM, (3) *multi-source Dijkstra* →
jarak jalan kaki tiap simpul ke halte terdekat, (4) grid populasi **WorldPop 100 m**
(GEE) → tiap sel dinilai punya-akses bila simpul jalan terdekatnya ≤ ambang
(default **500 m**; SDG 11.2.1 memakai 500 m untuk bus, ~1 km untuk kereta).

```bash
# Halte otomatis dari OSM (default), Semarang
earthchange -s transit-access --city "Semarang" --radius 8 --backend gee

# Ambang ganda (bus 500 m + kereta 1 km); yang pertama dipakai untuk peta
earthchange -s transit-access --lat -6.9667 --lon 110.4167 --radius 8 \
    --walk-dist 500,1000 --pop-year 2020

# Halte/rute Anda sendiri (mis. koridor TransSemarang dari QGIS)
earthchange -s transit-access --city "Semarang" --radius 10 \
    --transit-file transjateng_stops.geojson

# Hitung populasi di dalam batas administrasi (diambil dari OSM), AOI otomatis
earthchange -s transit-access --lat -7.02 --lon 110.39 --backend gee \
    --boundary "Kota Semarang" --walk-dist 500,1000 \
    --transit-file transsemarang_halte.geojson
```

Dengan `--boundary "<nama wilayah>"`, batas administrasi diambil dari OpenStreetMap,
**AOI di-ukur otomatis** ke wilayah itu, dan **% dihitung hanya untuk populasi di dalam
batas** (peta tetap menampilkan seluruh raster + garis batas). Pakai `--aoi-file
batas.geojson` untuk batas resmi (BPS/BIG) Anda sendiri. `--snap-dist` (default 400 m)
mengatur jarak maksimum sebuah sel populasi/halte "menempel" ke jalan terdekat
(lebih kecil = lebih ketat).

Keluaran: `transit_access_map.png` (kepadatan WorldPop + **jaringan jalan OSM** +
jalan dalam jangkauan + halte + garis batas), `service_area.geojson`,
`boundary.geojson`, `stops.geojson`, dan `stats.json` dengan **% populasi terlayani**,
jumlah orang terlayani/total, per ambang. Butuh `earthchange[transit]` (networkx, scipy,
shapely, rasterio, matplotlib, contextily). Untuk kota besar, jaringan jalan diambil
dengan **tiling + retry** Overpass agar tahan terhadap server yang sibuk.

> **Catatan:** `--transit-file` menerima titik (halte) atau garis (rute — otomatis
> dicuplik tiap ~250 m). Kelengkapan hasil bergantung pada kelengkapan pemetaan
> jalan/halte di OSM; untuk angkot yang belum terpetakan, berikan halte Anda
> sendiri. Peta contoh koridor BRT Semarang tersedia sebagai layer ArcGIS yang
> dapat diekspor ke GeoJSON.

### Panas pulau kecil: SST + LST + wet-bulb — `island-heat`

Membangun **deret waktu suhu** untuk pulau kecil: **SST** (suhu laut sekitar, NOAA
OISST 1981+), **LST** (suhu darat pulau, Landsat termal, di-mask ke lahan bervegetasi
NDVI agar pulau sub-km bersih), dan **wet-bulb** (panas *lembab* dari suhu udara +
titik embun ERA5-Land, rumus Stull) — beserta **tren °C/dekade** dan **puncak
wet-bulb harian per tahun** relatif ambang bahaya (28 °C) dan ekstrem (31 °C).
Latar: ancaman pulau kecil bukan hanya kenaikan muka laut, tetapi panas-lembab yang
membuat keringat tak lagi mendinginkan tubuh.

```bash
# Satu klaster pulau (mode agregat, default): satu deret SST/LST/wet-bulb
earthchange -s island-heat --backend gee --lat -5.7 --lon 106.55 --radius 35 \
    --start-year 2000 -n "Kepulauan Seribu"

# Pulau lebih besar (mis. Karimunjawa): LST MODIS 1 km lebih bersih
earthchange -s island-heat --backend gee --lat -5.85 --lon 110.42 --radius 25 \
    --lst-source modis -n "Karimunjawa"

# Per-pulau: deret LST terpisah tiap pulau (SST & wet-bulb tetap regional)
earthchange -s island-heat --backend gee --lat -5.7 --lon 106.55 --radius 35 \
    --island-mode per-island --islands-file pulau.geojson

# Poster cerita satu halaman (dwibahasa)
earthchange -s island-heat --lat -0.66 --lon 130.23 --radius 40 \
    -n "Raja Ampat" --infographic --lang both
```

**Poster cerita (`--infographic`).** Menghasilkan `island_heat_story_<id|en>.png`:
blok judul, tiga angka utama (tren SST / LST / wet-bulb dalam °C per dekade),
grafik tren gabungan, dan panel puncak wet-bulb tahunan terhadap ambang **28 °C
bahaya** / **31 °C ekstrem**, plus catatan sumber & keterbatasan. Pilih bahasa
dengan `--lang id` (default), `en`, atau `both`. Perlu `--island-mode aggregate`
(mode per-pulau tidak punya satu deret gabungan untuk diceritakan).

Pilih sensor LST dengan `--lst-source`: **`landsat`** (default; 100 m, di-mask ke
lahan bervegetasi NDVI — memisahkan pulau kecil/tersebar dari air & daratan utama)
atau **`modis`** (1 km, lebih rapat/bersih — terbaik untuk satu pulau besar yang jauh
dari daratan utama).

Keluaran: `island_heat.png` (tren SST/LST/wet-bulb + panel puncak wet-bulb),
**tiga peta perubahan dekadal** `sst_change_map.png` (SST laut, MODIS 4 km),
`lst_change_map.png` (LST lahan pulau, Landsat — laut transparan), dan
`combined_change_map.png` (gabungan: LST di darat + SST di laut dalam satu raster)
beserta GeoTIFF-nya, dan `stats.json` (tren per variabel, deret tahunan). Butuh
`earthchange[maps]`.

> **Catatan:** data ini **observasi** (satelit + reanalisis), yakni tren
> terukur — **bukan** proyeksi model iklim (CMIP6) hingga 2100. **SST & wet-bulb
> adalah sinyal yang paling andal.** Tren **LST untuk pulau sangat kecil (<1 km, mis.
> Kepulauan Seribu) tidak stabil** apa pun sensornya (piksel lahan sedikit/tercampur
> air) — bersifat indikatif; pulau lebih besar (mis. Karimunjawa dengan `--lst-source
> modis`) memberi LST bersih. Wet-bulb memakai ERA5 global (mencakup laut) sehingga
> deretnya berakhir ~2020 (cakupan dataset).

### Pulau panas perkotaan (SUHII) — `urban-heat`

Mengukur **pulau panas permukaan perkotaan**: kota lebih panas dari sekitarnya
karena permukaan gelap kedap air menyimpan panas dan vegetasi pendingin hilang.
Metrik utamanya **SUHII** (*Surface Urban Heat Island Intensity*) = rata-rata LST
kota − rata-rata LST pedesaan. Urban vs rural ditentukan dari **GHSL** (fraksi
permukaan terbangun), dan referensi pedesaan dibatasi ke ketinggian serupa (SRTM)
agar topografi tidak membiaskan.

```bash
# Snapshot + tren dekadal (default epoch 2000/2013/2022)
earthchange -s urban-heat --backend gee --lat -6.20 --lon 106.83 --radius 18 -n "Jakarta"

# Epoch & musim kemarau sendiri (UHI paling jelas saat kering)
earthchange -s urban-heat --city "Surabaya" --radius 15 \
    --epochs 2001-01-01:2003-12-31,2012-01-01:2014-12-31,2022-01-01:2024-12-31 \
    --months 6-9
```

Keluaran: `uhi_hotspot_map.png` (**suhu permukaan absolut** Landsat 100 m — kuning =
titik panas), `uhi_lst.tif`, `uhi_trend.png` (tren SUHII), dan `stats.json`. Butuh
`earthchange[maps]`.

> **Catatan:** dua angka SUHII berbeda karena resolusi. **Snapshot** memakai
> **Landsat 100 m** — memisahkan atap/aspal panas (>45 °C) dari sawah sejuk (~29 °C),
> jadi SUHII besar (Jakarta ~14 °C). **Tren** memakai **MODIS 1 km sensor konsisten**
> (Landsat mencampur TM/OLI yang tak sebanding) — piksel kasar mencampur kota+desa,
> jadi SUHII absolutnya lebih kecil (~2 °C); yang penting adalah *arah* perubahannya.
> Ini suhu *permukaan* siang hari (bukan suhu udara, yang jauh lebih kecil).

### Deforestasi multi-periode — `forest-history`

Bukan sekadar sebelum/sesudah — beri **4–5 periode** dan dapatkan **kapan** tiap
piksel hutan hilang. "Hilang" ditakar relatif terhadap baseline tiap piksel (tahan
terhadap jenis hutan/musim/beda sensor TM vs OLI): piksel yang awalnya hutan (NDVI
baseline > ambang) dinyatakan hilang pada epoch pertama NDVI-nya turun lebih dari
`--drop-thr` di bawah baseline. Air di-mask (MNDWI). Pakai `--sensor landsat` untuk
menjangkau **sejak 1980-an**.

```bash
# 5 periode dari Landsat, 1990 -> 2024 (frontier deforestasi Kalteng)
earthchange -s forest-history --backend gee --sensor landsat --lat -2.2 --lon 113.0 --radius 12 \
    --epochs 1990-01-01:1992-12-31,2000-01-01:2002-12-31,2010-01-01:2012-12-31,2017-01-01:2019-12-31,2023-01-01:2025-12-31
```

Keluaran: `forest_loss_map.png` (**peta tahun-kehilangan** — hijau = masih hutan,
kuning→merah tua = hilang lebih awal→lebih baru), `forest_trajectory.png` (luas hutan
asli tersisa per periode), `forest_loss.tif`, dan `stats.json` (luas hutan & kehilangan
per periode, total). Butuh `earthchange[maps]`. Atur ambang dengan
`--forest-thr` (default 0.6) & `--drop-thr` (default 0.2).

> **Catatan:** ΔNDVI antar-dekade menangkap perubahan *neto* — lahan yang
> ditebang lalu ditanami sawit dapat pulih NDVI-nya dan tak terhitung "hilang".
> Beberapa periode (bukan satu pra/pasca) memberi kisah yang lebih benar. Untuk arsip
> lama pakai GEE (paling andal). Contoh Kalteng: 56.316 → 49.802 ha (−12%, terbesar
> pada 2000–2010).

### Asap & kualitas udara saat karhutla — `haze`

Kebakaran baru separuh cerita; yang dirasakan orang adalah **asapnya**. Skenario ini
menggabungkan api dengan udara yang dihirup, hari demi hari:

- **PM2.5 permukaan** dari **CAMS (ECMWF)**, diberi kategori **ISPU** Indonesia dan
  garis **pedoman WHO 24 jam (15 µg/m³)**;
- **indeks aerosol** Sentinel-5P TROPOMI (pelacak plume asap);
- **titik panas FIRMS** pada jendela yang sama, jadi terlihat api penyebabnya;
- **peta sebaran asap** untuk episode yang sedang berlangsung.

```bash
# Episode terkini di sebuah kota (45 hari terakhir)
earthchange -s haze --lat -2.21 --lon 113.92 --radius 30 -n "Palangka Raya"

# Se-provinsi, jendela tanggal sendiri
earthchange -s haze --admin "Kalimantan Tengah" --haze-start 2026-07-01 --haze-end 2026-07-29
```

Keluaran: `haze_timeline.png` (tiga panel: PM2.5 berpita ISPU, indeks aerosol, titik
panas), `haze_smoke_map.png`, dan `stats.json` (PM2.5 harian, jumlah hari per kategori
ISPU, hari di atas pedoman WHO, PM2.5 terakhir & puncaknya). Butuh `earthchange[maps]`.
Backend: **GEE**.

> **Catatan penting:**
> - **PM2.5 CAMS adalah model** (reanalisis/prakiraan), **bukan** alat ukur darat.
>   Bagus untuk *kapan* episode mulai, seberapa parah relatifnya, dan arah trennya —
>   bandingkan dengan data stasiun BMKG/KLHK bila perlu angka resmi.
> - **Indeks aerosol Sentinel-5P sering gagal menangkap asap dekat permukaan.** AAI
>   peka pada aerosol di ketinggian; asap yang terperangkap inversi di bawah sering
>   terbaca lemah/negatif. Pada uji Palangka Raya (Juli 2026) PM2.5 melonjak ke
>   kategori *Tidak Sehat* sementara AAI tetap negatif. Jadikan PM2.5 + titik panas
>   sebagai sinyal utama; AAI sebagai konteks.
> - Sumber punya **latensi berbeda** (CAMS memimpin FIRMS beberapa hari), jadi hari
>   terakhir bisa punya PM2.5 tanpa titik panas.

### Riwayat kebakaran hutan & lahan — `fire-history`

Berbeda dari `burn` (severity **satu** kejadian via dNBR), skenario ini membangun
**rekaman panjang**: di mana area terbakar, **kapan** dalam setahun, dan **seberapa
sering**. Sumber: **MODIS MCD64A1** (luas terbakar bulanan, 500 m, sejak 2000-11)
dan **FIRMS** (titik panas aktif).

```bash
# Per provinsi (poligon asli FAO GAUL — angka jadi bermakna per wilayah)
earthchange -s fire-history --admin Riau
earthchange -s fire-history --admin "Kalimantan Tengah" --start-year 2001

# Riwayat karhutla Riau 2001–2024 (jantung lahan gambut)
earthchange -s fire-history --lat 0.5 --lon 101.9 --radius 60 -n Riau

# Rentang tahun & kotak batas sendiri
earthchange -s fire-history --bbox 113.5,-3.0,114.5,-2.0 --start-year 2015 -n Sebangau

# Angka yang bisa disitasi: pakai peta gambut resmi (KLHK/BBSDLP)
earthchange -s fire-history --lat 0.5 --lon 101.9 --radius 60 --peat-file gambut_klhk.geojson

# Bandingkan beberapa wilayah sekaligus -> fire_areas_comparison.png
earthchange -s fire-history --areas "Riau,Jambi,Sumatera Selatan,Kalimantan Tengah,Kalimantan Barat"

# Musim berjalan vs seluruh rekaman -> fire_vs_baseline.png
earthchange -s fire-history --admin "Kalimantan Barat" --vs-baseline
```

**Banding antar-wilayah (`--areas`).** Daftar nama admin dipisah koma; tiap wilayah
dijalankan ke subfoldernya sendiri, lalu dirakit satu panel: deret tahunan per
wilayah (gambut vs mineral, skala-y masing-masing), total, porsi gambut, dan
kurva musim yang ditumpuk. `stats.json` memuat semuanya plus peringkat luas terbakar.

**Musim berjalan vs baseline (`--vs-baseline`).** Menghitung titik panas FIRMS
untuk **jendela tanggal yang sama** (1 Jan → hari ini) di **setiap tahun**, jadi musim
yang belum selesai dibandingkan secara adil — bukan melawan tahun penuh. Memakai
FIRMS, bukan MCD64A1, karena luas terbakar tertinggal beberapa bulan sehingga tak
bisa menggambarkan musim yang sedang berjalan. Grafiknya menampilkan **dua** garis
acuan: rata-rata seluruh rekaman **dan** rata-rata dekade terakhir — penting, karena
rezim kebakaran bergeser (pasca krisis 2015 provinsi-provinsi turun tajam, sehingga
rata-rata panjang meremehkan seberapa anomali musim berjalan).

Keluaran: **`fire_frequency_map.png`** (+ `.tif`) — peta **berapa kali tiap piksel
terbakar** sepanjang periode, sehingga titik **berulang** (biasanya gambut terdrainase)
menonjol dari kebakaran sekali-jalan; **`fire_by_year.png`** — batang luas terbakar per
tahun **dipisah gambut vs tanah mineral**, ditumpuk dengan garis titik panas FIRMS;
**`fire_season.png`** — luas terbakar per bulan sepanjang semua tahun (musim kebakaran);
dan `stats.json` (per tahun, per bulan, total, %-gambut, tahun terparah, bulan puncak).
Butuh `earthchange[maps]`. Backend: **GEE**.

**Lapisan gambut — tiga pilihan.** Tidak ada satu pun yang unggul di semua wilayah,
jadi ketiganya bisa dipilih:

| Sumber | Cara pakai | Sifat |
|--------|-----------|-------|
| **SOC proxy** (default) | `--peat-source soc` | Karbon organik tanah OpenLandMap (10 cm) ≥ `--peat-thr` (30). Tanpa unduhan. |
| **PEATGRIDS** | `--peat-source peatgrids` | Ketebalan gambut global 1 km (GPM 2.0 + digital soil mapping). Tanpa unduhan. |
| **Gumbricht 2017 (CIFOR)** | `--peat-file <file>.tif` | Peta gambut tropis 231 m, **terbit peer-review & bisa disitasi**. Perlu unduh sekali. |

Mengunduh **Gumbricht et al. 2017** (Tropical and Subtropical Wetlands Distribution,
[DOI 10.17528/CIFOR/DATA.00058](https://doi.org/10.17528/CIFOR/DATA.00058)):

```bash
curl -L -o peat.7z "https://data.cifor.org/api/access/datafile/1727"   # 40 MB
7z x peat.7z          # -> TROP-SUBTROP_PeatV21_2016_CIFOR.tif (332 MB, 231 m)
earthchange -s fire-history --lat 0.5 --lon 101.9 --radius 60 \
    --peat-file TROP-SUBTROP_PeatV21_2016_CIFOR.tif
```

Definisi Gumbricht: tanah dengan **≥30 cm** bahan organik terdekomposisi dan **≥50%**
bahan organik; disusun dari kelas lahan basah pembentuk gambut (mangrove, rawa, fen,
riverine, floodswamp); kesesuaian 65% terhadap 275 profil tanah.

**Perbandingan jujur** terhadap angka provinsi yang lazim dikutip (BBSDLP/Wetlands
International — perkiraan, bukan kebenaran mutlak):

| Provinsi | Lazim dikutip | Gumbricht | SOC≥30 | PEATGRIDS |
|----------|--------------|-----------|--------|-----------|
| Riau | ±4,0 Mha | 2,14 (kurang) | **3,88** ✓ | 5,74 (lebih) |
| Kalimantan Tengah | ±3,0 | **2,63** ✓ | 6,55 (2× lebih) | 5,20 (lebih) |
| Jawa Barat | ±0 | 0,16 (positif palsu) | **0,01** ✓ | **0,00** ✓ |
| Papua | ±3,7 | 6,06 (lebih) | **3,61** ✓ | 11,92 (3× lebih) |
| Sumatera Selatan | ±1,4 | **1,70** ✓ | 4,37 (3× lebih) | 3,41 (lebih) |

Ringkasnya: **Gumbricht** lebih konservatif dan paling tepat di Kalteng & Sumsel
(dan bisa disitasi), **SOC proxy** paling tepat di Riau, Papua & Jawa, **PEATGRIDS**
konsisten melebih-lebihkan. Pilih sesuai wilayah, dan sebutkan sumbernya — nama
lapisan selalu dicetak di grafik dan tersimpan di `stats.json`.

Untuk peta gambut resmi Indonesia (KLHK/BBSDLP) berbentuk poligon, `--peat-file`
juga menerima **GeoJSON**.

> **Catatan:** MCD64A1 beresolusi 500 m dan **cenderung meremehkan** kebakaran gambut
> Indonesia — banyak api gambut membara di bawah permukaan dan tertutup asap/awan.
> Angka ini bagus untuk **pola** (di mana berulang, kapan puncaknya, tren antar-tahun),
> bukan untuk audit luas yang presisi. Luas per tahun dijumlahkan, jadi piksel yang
> terbakar di beberapa tahun terhitung sekali per tahun — total > luas area unik.

### Perubahan populasi sebagai hutan paku 3D — `population-change`

Membandingkan populasi ber-grid (**GHSL GHS_POP**) antara **dua epoch** (default
1990 & 2020) dan mengklasifikasikan tiap sel: **abu** = ada di kedua tahun (dalam
pita netral ±1%), **hijau** = bertambah, **magenta** = berkurang. Tinggi paku =
populasi *terbesar* dari dua epoch (skala log) — permukiman besar menjulang tinggi.
Terinspirasi peta paku populasi GHSL milik Miloš Popović.

```bash
# Skala nasional (AOI = seluruh negara via LSIB; ukuran sel otomatis)
earthchange -s population-change --country Indonesia

# Per pulau utama → panel gabungan (Sumatera, Jawa, Bali, Nusa Tenggara,
# Kalimantan, Sulawesi, Maluku, Papua) — tiap pulau di-clip ke batas negara
earthchange -s population-change --country Indonesia --regions indonesia --cell-km 5

# Detail kota (sel 1 km) via kotak batas w,s,e,n
earthchange -s population-change --bbox 106.3,-6.5,107.2,-5.9 --cell-km 1 -n Jakarta

# Reproduksi contoh Miloš
earthchange -s population-change --country Poland --pop-years 1990,2020
```

Mode **`--regions indonesia`** menjalankan skenario per **pulau utama** dan merakit
satu **panel `pop_islands_panel.png`** (satu hutan paku per pulau, tiap subplot diberi
%-perubahan neto) plus subfolder per pulau berisi peta, paku, dan `stats.json`-nya.
Cocok untuk kepulauan yang tersebar — jauh lebih terbaca daripada satu bingkai
nasional selebar 46°. Tiap kotak pulau di-clip ke garis negara (LSIB) sehingga
Malaysia (di Borneo) dan PNG (di Papua) tidak ikut terhitung.

Keluaran: **`pop_poster.png` + `pop_poster_dark.png`** — **infografik gaya Miloš per
kota**: tiap **kota** (puncak populasi lokal) jadi satu paku; **tinggi paku ∝
populasi kota** (log — kota terbesar tertinggi), badan **abu = level 1990**, dan
**ujung** menandai perubahan — **hijau kalau tumbuh, merah kalau menyusut**.
Perubahan dihitung atas **catchment kota** (semua sel berpenduduk dalam 25 km dari
puncaknya, ditetapkan ke kota terdekat) — bukan sel puncak saja, sehingga metro yang
intinya jenuh (Jakarta, Bandung) tetap terbaca tumbuh. Pulau digambar sebagai
**basemap terrain ber-hillshade** (SRTM, diunduh otomatis sebagai `terrain.tif`)
dengan relief halus. Plus
blok judul, legenda, label kota, dan catatan sumber (terang & gelap). Juga
`pop_change_map.png` (peta 2D tambah/kurang/tetap), `pop_change_class.tif`
(raster kelas), `pop_<y1>.tif`/`pop_<y2>.tif` (grid populasi), **`pop_cells.csv`**
(satu baris per sel: lon, lat, pop tiap epoch, delta, %, kelas, tinggi — **siap
dirender 3D di [forge3d](https://github.com/milos-agathon/forge3d)**), dan `stats.json`. Butuh
`earthchange[maps]`. Atur dengan `--pop-years`, `--cell-km`, `--neutral-pct`
(default 1), `--min-pop` (default 150). Backend: **GEE** (GHS_POP; unduhan nasional
otomatis di-tile agar tidak melampaui batas komputasi Earth Engine).

Poster paling terbaca untuk **satu pulau ringkas** (mis. `-n Jawa` dengan kotak Jawa)
— siluetnya jelas, tiap kota jadi paku, seperti contoh *POLAND* Miloš. Kota dideteksi
sebagai puncak populasi lokal (ambang diskala ke ukuran sel); label kota otomatis
muncul untuk Jawa, Sumatera, Kalimantan, Sulawesi, Papua, Bali, Nusa Tenggara,
Maluku, dan Indonesia.

```bash
# Poster per-kota Jawa (paling mirip contoh Miloš)
earthchange -s population-change --bbox 105,-8.9,114.6,-5.8 --cell-km 5 -n Jawa
```

**3D GPU asli via forge3d (`--forge3d`).** Poster di atas adalah proyeksi 2.5D
matplotlib. Untuk render **3D GPU sungguhan** — persis pipeline
[forge3d](https://github.com/milos-agathon/forge3d) (Rust/WebGPU) milik Miloš —
tambahkan `--forge3d`: raster populasi (yang lebih besar dari dua epoch) jadi
**height-field terrain**, di-warnai overlay kelas (abu tetap / hijau tambah / merah
kurang), lalu di-snapshot lewat viewer forge3d menjadi `pop_spikes_3d.png`.

```bash
pip install 'earthchange[forge3d]'   # butuh GPU WebGPU (Metal di macOS)
earthchange -s population-change --bbox 105,-8.9,114.6,-5.8 --cell-km 5 -n Jawa --forge3d
# atau tulis input saja (height TIFF + overlay), render nanti di mesin ber-GPU:
earthchange -s population-change ... --forge3d-prep-only
```

Persiapan data (height TIFF EPSG:3857 + overlay RGBA) jalan di mana saja; langkah
snapshot butuh `forge3d` + GPU. Bila tak tersedia, run mencetak pesan jelas dan
tetap menghasilkan poster 2.5D — tidak gagal.

> **Catatan:** GHS_POP adalah **model** (sensus di-disagregasi ke grid terbangun),
> bukan cacah langsung; nilai antar-epoch adalah estimasi model. Baik untuk pola
> redistribusi (kota tumbuh vs desa menyusut), bukan angka sel yang presisi. Metro
> yang seragam padat (mis. Jabodetabek) tampak seluruhnya hijau; pola "hutan paku"
> paling terbaca pada skala nasional saat sel laut/hutan rontok.

### Backend data: GEE atau Planetary Computer (tanpa akun)

Sumber data dipilih lewat `--backend`:

| Backend | Sumber | Perlu akun? |
|---------|--------|-------------|
| `gee` (default) | Google Earth Engine | Ya — akun gratis + `earthengine authenticate` |
| `mpc` | **Microsoft Planetary Computer** (STAC) | **Tidak** — aset ditandatangani anonim |

Backend `mpc` mengunduh COG Sentinel-1/2 dan memproses **lokal** dengan
`rasterio`/`odc-stac`/`numpy` — tanpa Earth Engine. Keluaran (PNG, GeoTIFF,
statistik) dan peta identik.

```bash
# Tanpa akun GEE — pakai Planetary Computer
python3 detect.py -s deforestation --lat -3.333 --lon 122.25 --backend mpc --map
python3 detect.py -s flood --lat 27.2 --lon 68.3 \
    --pre 2022-07-01:2022-07-25 --post 2022-08-20:2022-09-10 --backend mpc
```

Dependensi backend `mpc` (sudah di `requirements.txt`):
`pystac-client planetary-computer odc-stac rioxarray`.

---

## Produk Peta (Value-Added)

Tambahkan `--map` untuk menghasilkan **peta jadi berukuran A4 landscape** (PDF +
PNG) per produk: basemap OpenStreetMap + layer perubahan, judul, legenda,
panel statistik, inset lokasi, grid koordinat, skala, panah utara, dan footer sumber.

```bash
python3 detect.py -s deforestation --lat -3.333 --lon 122.25 --map
python3 detect.py -s mining --site konawe --map --basemap gray
```

Render ulang **tanpa GEE** dari hasil yang sudah ada (memakai sidecar `.meta.json`):

```bash
python3 make_map.py output/20260708-222632_deforestation_x_fac24e   # 1 folder run
python3 make_map.py output/<run>/mining_sirad_x.tif --basemap gray  # atau 1 .tif
```

Peta tersimpan di dalam folder run yang sama. Tata letak & elemen kartografi
ada di [`mapmaker.py`](mapmaker.py)
(butuh `matplotlib`, `rasterio`, `contextily`).

---

## Studi Kasus: Investigasi PETI Capkala

> **Video:** MP4 1920×1080, 4 menit 6 detik · Narator Bian (ElevenLabs) ·
> Thread X — [@jalmiburung](https://x.com/jalmiburung)

### Temuan Utama

Empat sumber data independen menunjuk pada kesimpulan yang sama: tambang beroperasi **tanpa izin, di atas tanah tanpa hak.**

| Metode | Sumber Data | Temuan |
|--------|-------------|--------|
| Citra optik | Sentinel-2 (true color) | Bukaan lahan tambang tampak jelas, tutupan awan <1% |
| Radar deret waktu | Sentinel-1 → **SIRAD** | Aktivitas **berlanjut setelah penggerebekan polisi Maret 2026** |
| Optik resolusi tinggi | PlanetScope (3 m) | NDVI 0.862 → 0.793 (**ΔNDVI −0.068**); 24.7% area terdampak, 9.2% kerusakan berat |
| Catatan legal | BHUMI, MODI | **Tidak ada hak tanah, tidak ada IUP** di lokasi tambang |

**Zona Tambang Utara:** `0.6784°N, 109.0836°E`, radius 1.5 km.

### Rantai bukti legal

1. Tidak ada WPR (Wilayah Pertambangan Rakyat)
2. RDTR (Rencana Detail Tata Ruang) belum rampung
3. MODI ESDM — tidak ada IUP tercatat
4. BHUMI ATR/BPN — **TIPE HAK KOSONG**, 83 ha
5. Polres Bengkayang — penangkapan + sita ekskavator (Maret 2026)
6. Dokumen palsu beredar (Mata Pers, Juli 2025)

Detail langkah verifikasi: [`data-collection/04_legal_verification.md`](data-collection/04_legal_verification.md).

---

## Pipeline

```
DATA COLLECTION                    NARRATION → TTS → VIDEO
─────────────────                  ───────────────────────
01_sentinel2_download.py  ─┐
02_sirad_gee.py (radar)   ─┤       capkala_narration_v4.txt
03_ndvi_change_gee.py     ─┼──►    01_generate_tts.py  ──►  audio/*.mp3
03_planetscope_ndvi.py    ─┤       02_assemble_video.py ──►  capkala_investigation.mp4
04_legal_verification.md  ─┘             (5 scene → video final)
   (citra + deteksi perubahan)
```

### SIRAD — teknik inti

**SIRAD** (*Sentinel-1 RGB Anomaly Detection*) menumpuk backscatter radar VH rata-rata dari tiga periode ke dalam satu citra RGB (± 139 citra Sentinel-1 GRD). **Seluruh pemrosesan berjalan di Google Earth Engine melalui Python** (`earthengine-api`) — tanpa Code Editor — dan hasilnya diunduh otomatis ke `images/sirad_raw.png`:

- **Merah** = 2024
- **Hijau** = 2025
- **Biru** = Mar–Jun 2026 (pasca-penggerebekan)

Karena radar menembus awan, deret waktu tidak terputus oleh tutupan awan. Interpretasi warna:

| Warna | Arti |
|-------|------|
| Putih/abu | Aktivitas di semua periode (berlangsung terus) |
| Merah | Hanya 2024 (berhenti) |
| Kuning | 2024 + 2025 |
| Cyan | 2025 + 2026 (lebih baru) |
| **Biru** | **Hanya 2026 — bukti kunci: tambang berlanjut setelah penggerebekan** |

---

## Struktur Proyek

```
rs-change-detection/
├── README.md
├── pyproject.toml                   ← Paket PyPI `earthchange` (build + extras)
├── PUBLISHING.md                    ← Panduan rilis ke PyPI
├── earthchange/                       ← Paket inti (yang di-`pip install`)
│   ├── detect.py                    #   CLI utama → perintah `earthchange`
│   ├── make_map.py                  #   Render peta → perintah `earthmap`
│   ├── mapmaker.py                  #   Tata letak kartografi (matplotlib)
│   ├── scenarios.py                 #   Registry skenario → metode
│   ├── indices.py                   #   Indeks spektral + komposit + Landsat
│   ├── mpc_backend.py               #   Backend Planetary Computer (tanpa akun)
│   ├── gee_utils.py                 #   Helper GEE: unduh, init, klip, mask
│   └── sites.py                     #   Preset lokasi (Capkala, Konawe, …)
├── detect.py  ·  make_map.py        ← Shim agar `python3 detect.py …` tetap jalan
├── requirements.txt                 ← Dependensi (untuk pakai dari sumber)
├── run_all.py                       ← Pipeline Capkala end-to-end 1 perintah
├── .env.example                     ← Template kunci API (salin ke .env)
├── data-collection/                 ← Pengumpulan, pemrosesan & deteksi perubahan
│   ├── 01_sentinel2_download.py     # Sentinel-2 true color via GEE (Python)
│   ├── 02_sirad_gee.py              # SIRAD — deteksi perubahan radar Sentinel-1
│   ├── 03_ndvi_change_gee.py        # Deteksi perubahan NDVI Sentinel-2 (gratis)
│   ├── 03_planetscope_ndvi.py       # Deteksi perubahan NDVI PlanetScope (3 m, komersial)
│   └── 04_legal_verification.md     # Verifikasi BHUMI & MODI
├── narration/
│   └── capkala_narration_v4.txt     # Naskah 5 scene (Bahasa Indonesia)
├── scripts/
│   ├── 01_generate_tts.py           # Narasi → audio (ElevenLabs)
│   ├── 02_assemble_video.py         # Gambar + audio → video (Python + ffmpeg)
│   └── config/  (tidak di-git)      # Kredensial: ee-geodetic.json, elevenlabs.txt
├── output/        (tidak di-git)    ← Hasil detect.py per-run: output/<run-id>/
├── images/                          ← Aset visual (slide + citra mentah)
├── data/                            ← Input mentah *.tif (README saja di-git)
├── audio/         (tidak di-git)    ← Output TTS (5 mp3)
├── scenes/        (tidak di-git)    ← Output per-scene
└── capkala_investigation.mp4  (tidak di-git)  ← Video final
```

Seluruh pipeline **murni Python** (pemrosesan citra berjalan di Google Earth Engine via `earthengine-api`; perakitan video memakai `ffmpeg` sebagai mesin render). `audio/`, `scenes/`, `*.mp4`, dan input `.tif` di-*gitignore* karena bisa dibuat ulang / berlisensi.

---

## Prasyarat

| Kebutuhan | Untuk |
|-----------|-------|
| Python 3.11+ | Semua skrip |
| `ffmpeg` + `ffprobe` di PATH | Perakitan video (mesin render) |
| Akun Google Earth Engine (`earthengine authenticate`) | Sentinel-2 & SIRAD |
| `ELEVENLABS_API_KEY` (env var atau `.env`) | TTS |
| Citra PlanetScope (`data/planetscope_pre.tif`, `post.tif`) | NDVI |

```bash
# 1. Dependensi Python
pip install -r requirements.txt

# 2. ffmpeg (mesin render video)
brew install ffmpeg            # macOS  ·  Debian/Ubuntu: sudo apt install ffmpeg

# 3. Autentikasi Google Earth Engine (sekali saja)
earthengine authenticate

# 4. Kunci API — salin template lalu isi
cp .env.example .env           # isi ELEVENLABS_API_KEY di dalamnya
```

**Kredensial** dibaca dari beberapa lokasi (berurutan):
- **ElevenLabs**: env `ELEVENLABS_API_KEY` → `.env` root → `scripts/config/elevenlabs.txt` → `~/.hermes/.env`
- **Earth Engine**: `scripts/config/ee-geodetic.json` (service account) → `~/.config/earthengine/ee-geodetic.json` → `earthengine authenticate`

Letakkan kunci di folder `scripts/config/` agar tidak perlu variabel lingkungan (folder ini di-*gitignore*).

> **Catatan:** Direktori `data/` (input `.tif` mentah) tidak di-git — lihat [`data/README.md`](data/README.md) untuk file yang diperlukan. Citra PlanetScope bersifat komersial; data lain gratis/terbuka.

---

## Jalankan End-to-End (satu perintah)

`run_all.py` menjalankan seluruh pipeline analisis + **deteksi perubahan** untuk
satu lokasi, berurutan: Sentinel-2 → SIRAD (radar) → NDVI change (Sentinel-2) →
NDVI PlanetScope (opsional, dilewati bila tak ada data komersial).

```bash
python3 run_all.py --site konawe          # semua langkah untuk Konawe
python3 run_all.py --site capkala         # untuk Capkala (default)
python3 run_all.py --site konawe --drive  # + ekspor resolusi penuh ke Drive
```

Hasil (per-situs) langsung ter-unduh ke disk:

| Berkas | Isi |
|--------|-----|
| `images/sentinel2_<situs>.png` · `data/sentinel2_<situs>.tif` | True color |
| `images/sirad_<situs>.png` · `data/sirad_<situs>.tif` | Perubahan radar (SIRAD) |
| `images/ndvi_change_<situs>.png` · `data/ndvi_change_<situs>.tif` | **Peta perubahan NDVI** (merah = kehilangan vegetasi) |
| `data/ndvi_<situs>_stats.json` | Statistik: mean ΔNDVI, % area terdampak/berat |

**Deteksi perubahan** tersedia dua cara: **SIRAD** (radar temporal, menembus awan)
dan **NDVI change Sentinel-2** (`03_ndvi_change_gee.py`, gratis, membandingkan
median NDVI periode dasar vs terkini). Versi 3 m PlanetScope (`03_planetscope_ndvi.py`)
opsional dan butuh citra komersial.

> **Awan Sentinel-2:** skrip mengambil satu scene dengan tutupan awan **≤ 10%**;
> bila tidak ada, ia otomatis menyusun *median composite* dari banyak scene yang
> sudah di-mask awan (SCL) untuk menekan awan. Deteksi perubahan NDVI selalu
> memakai median banyak scene.

Untuk menjalankan per-langkah (bukan sekaligus), lihat di bawah.

---

## Cara Menjalankan

### Opsi A — Rakit video dari aset yang sudah ada

Semua slide dan citra sudah tersedia di `images/`. Cukup buat audio lalu rakit video:

```bash
python3 scripts/01_generate_tts.py     # narasi → audio/scene_00..04.mp3
python3 scripts/02_assemble_video.py   # → capkala_investigation.mp4
```

### Opsi B — Reproduksi penuh dari data mentah

```bash
# 1. Sentinel-2 true color (GEE via Python)
python3 data-collection/01_sentinel2_download.py

# 2. SIRAD — berjalan di GEE via Python; hasil → images/sirad_raw.png otomatis
python3 data-collection/02_sirad_gee.py

# 3. PlanetScope NDVI (letakkan planetscope_pre.tif & post.tif di data/)
python3 data-collection/03_planetscope_ndvi.py
#    Salin hasil planetscope_ndvi_change.png → images/

# 4. Verifikasi legal (manual) — lihat data-collection/04_legal_verification.md
#    Screenshot BHUMI → images/bhumi_screenshot.jpg

# 5. Rakit video
python3 scripts/01_generate_tts.py
python3 scripts/02_assemble_video.py
```

---

## Lokasi Lain (Multi-Situs)

Pipeline pengumpulan data **tidak terikat ke Capkala**. Pilih lokasi dengan
`--site <nama>` atau variabel lingkungan `SITE`. Lokasi didefinisikan di
[`sites.py`](sites.py) (AOI + periode). Sudah tersedia: `capkala`, `konawe`.

```bash
# Contoh: jalankan untuk Konawe (tambang nikel, Sulawesi Tenggara)
python3 data-collection/02_sirad_gee.py         --site konawe
python3 data-collection/01_sentinel2_download.py --site konawe
python3 data-collection/03_planetscope_ndvi.py  --site konawe   # butuh data/planetscope_konawe_*.tif
```

### Mengunduh hasil

Setiap skrip GEE mengunduh **dua** berkas langsung ke disk (per-situs, tanpa
lewat Google Drive):

| Berkas | Isi | Untuk |
|--------|-----|-------|
| `images/sirad_<situs>.png`, `images/sentinel2_<situs>.png` | Quick-look RGB (1920 px) | Pratinjau cepat |
| `data/sirad_<situs>.tif`, `data/sentinel2_<situs>.tif` | **GeoTIFF resolusi penuh, tergeoreferensi** | Buka di QGIS / rasterio |

Nama per-situs mencegah hasil antar-lokasi saling menimpa. Untuk ekspor
resolusi penuh ke Google Drive (opsional), tambahkan flag `--drive`:

```bash
python3 data-collection/02_sirad_gee.py --site konawe --drive
```

Untuk mengganti tiga periode SIRAD (kanal R/G/B) tanpa mengubah `sites.py`,
pakai `--epochs` (sama seperti `earthchange -s mining`):

```bash
python3 data-collection/02_sirad_gee.py --site konawe \
    --epochs 2024-01-01:2024-12-31,2025-01-01:2025-12-31,2026-01-01:2026-06-30
```

**Menambah lokasi baru:** salin satu entri di `sites.py`, ubah `lat`/`lon`/
`radius_km` dan tanggal periode. SIRAD otomatis memilih arah orbit Sentinel-1
(ASCENDING/DESCENDING) yang punya cakupan di setiap periode, dan Sentinel-2
mencari citra paling minim awan dalam jendela ±30 hari — jadi lokasi baru
langsung menghasilkan citra tanpa penyetelan manual.

---

## Rincian Scene

| # | Judul | Durasi | Sumber |
|---|-------|--------|--------|
| 01 | PENDAHULUAN | 31s | Slide teks |
| 02 | CITRA SENTINEL-2 | 42s | `01_sentinel2_download` |
| 03 | ANALISIS SPASIAL | 37s | Slide teks |
| 04 | METODOLOGI | 94s | Semua data (5 langkah) |
| 05 | KESIMPULAN | 40s | Slide teks |

**Scene 04** membagi narasi metodologi ke 5 langkah citra:
Sentinel-2 → SIRAD → PlanetScope NDVI → verifikasi legal (BHUMI/MODI) → publikasi.

---

## Atribusi Data

- **Sentinel-1 / Sentinel-2** — Copernicus / ESA (data terbuka).
- **PlanetScope** — Planet Labs PBC (tunduk pada lisensi masing-masing).
- **Google Earth Engine** — pemrosesan citra.
- **BHUMI** ATR/BPN & **MODI** ESDM — catatan publik Pemerintah Indonesia.

## Sitasi

Jika Anda menggunakan perangkat lunak ini dalam penelitian atau publikasi, mohon sitasi.
Di GitHub, gunakan tombol **"Cite this repository"** (didukung oleh berkas
[`CITATION.cff`](CITATION.cff)) untuk mendapatkan format APA/BibTeX terkini.

DOI (semua versi): [10.5281/zenodo.21370696](https://doi.org/10.5281/zenodo.21370696)

**APA**

> Hadi, F., Wahyuddin, Y., & Sabri, L. M. (2026). *earthchange: Multipurpose satellite change detection* (Versi 0.1.56) [Perangkat lunak]. Universitas Diponegoro. https://doi.org/10.5281/zenodo.21370696

**BibTeX**

```bibtex
@software{hadi_earthchange_2026,
  author    = {Hadi, Firman and Wahyuddin, Yasser and Sabri, L. M.},
  title     = {earthchange: Multipurpose satellite change detection},
  version   = {0.1.56},
  year      = {2026},
  publisher = {Zenodo},
  doi       = {10.5281/zenodo.21370696},
  url        = {https://doi.org/10.5281/zenodo.21370696},
  note      = {Universitas Diponegoro}
}
```

> DOI di atas adalah *concept DOI* (selalu menuju versi terbaru). Untuk mengutip
> rilis tertentu, gunakan **DOI versi** yang tertera pada halaman rilis di Zenodo.

## Disclaimer

Repositori ini dibuat untuk tujuan jurnalisme investigatif dan verifikasi berbasis bukti terbuka (*open-source intelligence*). Interpretasi citra satelit bersifat indikatif; status hukum final merupakan kewenangan otoritas berwenang. Semua sumber data yang digunakan bersifat publik atau berlisensi sah.
