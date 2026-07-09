# Satellite Change Detection (multiguna)

[![PyPI](https://img.shields.io/pypi/v/satchange.svg)](https://pypi.org/project/satchange/)
[![Python](https://img.shields.io/pypi/pyversions/satchange.svg)](https://pypi.org/project/satchange/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-tutorial-blue.svg)](https://firmanhadi21.github.io/rs-change-detection/)

Instalasi: `pip install 'satchange[all]'` — perintah `satchange` & `satmap`.

**Alat deteksi perubahan berbasis penginderaan jauh untuk berbagai skenario** —
deforestasi, tambang, urbanisasi, banjir, kebakaran, dan perubahan air — berjalan
di Google Earth Engine (Python). Pilih skenario + koordinat, hasil ter-unduh
sebagai PNG, GeoTIFF tergeoreferensi, dan statistik.

Studi kasus unggulan repо ini: **investigasi tambang emas ilegal (PETI) di Capkala**,
Kalimantan Barat — lengkap sampai video dokumenter (lihat bagian bawah).

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

Alat inti dikemas sebagai paket Python **`satchange`** dengan perintah `satchange`
(dan `satmap`). Dependensi berat bersifat opsional (*extras*):

```bash
pip install 'satchange[gee]'       # backend Earth Engine (butuh akun GEE)
pip install 'satchange[mpc,maps]'  # Planetary Computer + peta (tanpa akun)
pip install 'satchange[all]'       # semuanya

satchange -s deforestation --lat -3.333 --lon 122.25 --map
satmap output/<run-id>             # render ulang peta
```

Dari checkout sumber (repo ini) tanpa instalasi, `python3 detect.py …` tetap
berfungsi (shim ke paket). Untuk kembangkan: `pip install -e '.[all]'`.
Panduan rilis PyPI ada di [`PUBLISHING.md`](PUBLISHING.md).

> Contoh perintah di bawah memakai `python3 detect.py …`; setelah instal paket,
> ganti dengan `satchange …` (argumen identik).

---

## Deteksi Perubahan Multiguna — `detect.py`

Satu perintah: `-s <skenario>` memilih **metode** yang tepat, lokasi lewat
`--lat/--lon`, `-l 'lat,lon'`, atau `--site NAMA`.

| Skenario | Metode | Sensor |
|----------|--------|--------|
| `deforestation` | Kehilangan NDVI (ΔNDVI < ambang) | Sentinel-2 |
| `mining` | SIRAD radar temporal **+** kehilangan NDVI | Sentinel-1 + S2 |
| `urbanization` | Kenaikan NDBI (indeks terbangun) | Sentinel-2 |
| `flood` | Luas genangan SAR (event vs baseline) | Sentinel-1 VV |
| `burn` | dNBR (severity kebakaran) | Sentinel-2 |
| `water` | Perubahan NDWI (air permukaan) | Sentinel-2 |

```bash
# Sintaks umum
python3 detect.py -s <skenario> --lat <LAT> --lon <LON> [--radius KM] \
    [--pre START:END] [--post START:END] [-n NAMA]

# Contoh
python3 detect.py -s mining --site konawe               # pakai preset sites.py
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
├── pyproject.toml                   ← Paket PyPI `satchange` (build + extras)
├── PUBLISHING.md                    ← Panduan rilis ke PyPI
├── satchange/                       ← Paket inti (yang di-`pip install`)
│   ├── detect.py                    #   CLI utama → perintah `satchange`
│   ├── make_map.py                  #   Render peta → perintah `satmap`
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
pakai `--epochs` (sama seperti `satchange -s mining`):

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

## Disclaimer

Repositori ini dibuat untuk tujuan jurnalisme investigatif dan verifikasi berbasis bukti terbuka (*open-source intelligence*). Interpretasi citra satelit bersifat indikatif; status hukum final merupakan kewenangan otoritas berwenang. Semua sumber data yang digunakan bersifat publik atau berlisensi sah.
