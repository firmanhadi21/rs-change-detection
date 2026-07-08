# Satellite Change Detection (multiguna)

**Alat deteksi perubahan berbasis penginderaan jauh untuk berbagai skenario** —
deforestasi, tambang, urbanisasi, banjir, kebakaran, dan perubahan air — berjalan
di Google Earth Engine (Python). Pilih skenario + koordinat, hasil ter-unduh
sebagai PNG, GeoTIFF tergeoreferensi, dan statistik.

Studi kasus unggulan repо ini: **investigasi tambang emas ilegal (PETI) di Capkala**,
Kalimantan Barat — lengkap sampai video dokumenter (lihat bagian bawah).

> 📚 **Tutorial hands-on (GitHub Pages):** https://firmanhadi21.github.io/rs-change-detection/
> — panduan langkah demi langkah agar siapa pun bisa memakai & menyesuaikan alat ini.

```bash
python3 detect.py --list                                        # daftar skenario
python3 detect.py -s deforestation --lat -3.333 --lon 122.25    # deteksi deforestasi
python3 detect.py -s flood --lat 27.2 --lon 68.3 \
    --pre 2022-07-01:2022-07-25 --post 2022-08-20:2022-09-10     # pemetaan banjir
```

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
```

**Output per run** (klip berbentuk **persegi**, bukan lingkaran):

| Berkas | Isi |
|--------|-----|
| `images/<skenario>_<produk>_<nama>.png` | Quick-look berwarna |
| `data/<skenario>_<produk>_<nama>.tif` | GeoTIFF resolusi penuh (buka di QGIS) |
| `data/<skenario>_<nama>_stats.json` | Statistik (mean Δ, % area terdampak, dll.) |

Setiap skenario optik memakai **median composite banyak scene** dengan masking
awan per-piksel (SCL), jadi hasil bebas awan. Skenario radar (SIRAD/banjir)
memilih arah orbit Sentinel-1 yang punya cakupan otomatis.

**Menambah skenario:** tambahkan entri di [`scenarios.py`](scenarios.py)
(indeks/metode + ambang + palet). Indeks spektral ada di [`indices.py`](indices.py).

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
python3 make_map.py deforestation_dndvi_m3p333_122p25          # basename
python3 make_map.py data/mining_sirad_konawe.tif --basemap osm # atau path .tif
```

Peta tersimpan di `maps/<skenario>_<produk>_<nama>_map.{pdf,png}`.
Tata letak & elemen kartografi ada di [`mapmaker.py`](mapmaker.py)
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
├── requirements.txt                 ← Dependensi Python
├── detect.py                        ← CLI deteksi perubahan multiguna (utama)
├── make_map.py                      ← Render peta A4 dari hasil (offline)
├── mapmaker.py                      ← Tata letak kartografi (matplotlib)
├── scenarios.py                     ← Registry skenario → metode
├── indices.py                       ← Indeks spektral + komposit (NDVI/NDBI/…)
├── sites.py                         ← Preset lokasi (Capkala, Konawe, …)
├── run_all.py                       ← Pipeline Capkala end-to-end 1 perintah
├── gee_utils.py                     ← Helper GEE: unduh, init, klip persegi, mask
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
