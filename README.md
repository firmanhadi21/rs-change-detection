# Investigasi PETI Capkala

**Investigasi penginderaan jauh atas tambang emas ilegal (PETI — Penambangan Emas Tanpa Izin) di Capkala, Bengkayang, Kalimantan Barat.**

Repositori ini berisi pipeline lengkap dan *reproducible* — dari pengumpulan citra satelit multi-sensor, deteksi perubahan, verifikasi legal, hingga produksi video dokumenter berdurasi 4 menit.

> **Format:** MP4 1920×1080, stereo · **Durasi:** 4 menit 6 detik · **Narator:** Bian (ElevenLabs, Bahasa Indonesia)
> **Publikasi:** Thread X — [@jalmiburung](https://x.com/jalmiburung)

---

## Temuan Utama

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
02_sirad_gee.js           ─┤       capkala_narration_v4.txt
03_planetscope_ndvi.py    ─┼──►    01_generate_tts.py  ──►  audio/*.mp3
04_legal_verification.md  ─┘       02_assemble_video.sh ──►  capkala_investigation.mp4
        (citra + bukti)                  (5 scene → video final)
```

### SIRAD — teknik inti

**SIRAD** (*Sentinel-1 RGB Anomaly Detection*) menumpuk backscatter radar VH rata-rata dari tiga periode ke dalam satu citra RGB (± 139 citra Sentinel-1 GRD):

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
├── data-collection/                 ← Pengumpulan & pemrosesan data
│   ├── 01_sentinel2_download.py     # Sentinel-2 via GEE / Copernicus
│   ├── 02_sirad_gee.js              # SIRAD — deret waktu Sentinel-1 (GEE)
│   ├── 03_planetscope_ndvi.py       # NDVI change detection PlanetScope
│   └── 04_legal_verification.md     # Verifikasi BHUMI & MODI
├── narration/
│   └── capkala_narration_v4.txt     # Naskah 5 scene (Bahasa Indonesia)
├── scripts/
│   ├── 01_generate_tts.py           # Narasi → audio (ElevenLabs)
│   └── 02_assemble_video.sh         # Gambar + audio → video (ffmpeg)
├── images/                          ← Aset visual (slide + citra mentah)
├── data/          (tidak di-git)    ← Input mentah: *.tif satelit
├── audio/         (tidak di-git)    ← Output TTS (5 mp3)
├── scenes/        (tidak di-git)    ← Output per-scene
└── capkala_investigation.mp4  (tidak di-git)  ← Video final
```

`audio/`, `scenes/`, dan `*.mp4` di-*gitignore* karena bisa dibuat ulang dari skrip.

---

## Prasyarat

| Kebutuhan | Untuk |
|-----------|-------|
| Python 3.11+ | Skrip pemrosesan |
| ffmpeg + ffprobe | Perakitan video |
| Akun Google Earth Engine | Sentinel-2 & SIRAD |
| `ELEVENLABS_API_KEY` di `~/.hermes/.env` | TTS |
| Citra PlanetScope (`data/planetscope_pre.tif`, `post.tif`) | NDVI |

```bash
pip install earthengine-api rasterio Pillow elevenlabs requests numpy
```

> **Catatan:** Direktori `data/` (input `.tif` mentah) tidak disertakan — Anda perlu mengunduh/menyediakan citranya sendiri. Skrip membuat direktori `data/` otomatis dan memberi petunjuk jika file belum ada.

---

## Cara Menjalankan

### Opsi A — Rakit video dari aset yang sudah ada

Semua slide dan citra sudah tersedia di `images/`. Cukup buat audio lalu rakit video:

```bash
python3 scripts/01_generate_tts.py     # narasi → audio/scene_00..04.mp3
bash    scripts/02_assemble_video.sh   # → capkala_investigation.mp4
```

### Opsi B — Reproduksi penuh dari data mentah

```bash
# 1. Sentinel-2 true color
python3 data-collection/01_sentinel2_download.py

# 2. SIRAD — buka di GEE Code Editor
#    Salin data-collection/02_sirad_gee.js → https://code.earthengine.google.com/
#    Run → Export ke Drive → simpan ke images/sirad_raw.png

# 3. PlanetScope NDVI (letakkan planetscope_pre.tif & post.tif di data/)
python3 data-collection/03_planetscope_ndvi.py
#    Salin hasil planetscope_ndvi_change.png → images/

# 4. Verifikasi legal (manual) — lihat data-collection/04_legal_verification.md
#    Screenshot BHUMI → images/bhumi_screenshot.jpg

# 5. Rakit video
python3 scripts/01_generate_tts.py
bash    scripts/02_assemble_video.sh
```

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
