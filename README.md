# Investigasi PETI Capkala — End-to-End Reproducible

Investigasi tambang emas ilegal (PETI) di Capkala, Bengkayang, Kalimantan Barat. Pipeline lengkap dari pengumpulan data satelit hingga video dokumenter.

**Video final:** 4 menit 6 detik | 1920×1080 stereo | Narator Bian (ElevenLabs)

---

## Pipeline

```
                    ┌─────────────────────────┐
                    │   DATA COLLECTION        │
                    │   01_sentinel2_download  │──► Sentinel-2 true color
                    │   02_sirad_gee.js        │──► SIRAD RGB composite
                    │   03_planetscope_ndvi.py │──► NDVI change map
                    │   04_legal_verification  │──► BHUMI/MODI evidence
                    └───────────┬─────────────┘
                                │
                                ▼
                    ┌─────────────────────────┐
                    │   NARRATION              │
                    │   capkala_narration_v4   │──► Naskah 5 scene (ID)
                    └───────────┬─────────────┘
                                │
                                ▼
                    ┌─────────────────────────┐
                    │   TTS (ElevenLabs)       │
                    │   01_generate_tts.py     │──► 5 audio files
                    └───────────┬─────────────┘
                                │
                                ▼
                    ┌─────────────────────────┐
                    │   VIDEO ASSEMBLY         │
                    │   02_assemble_video.sh   │──► 5 scene videos
                    │                          │──► final combined mp4
                    └─────────────────────────┘
```

---

## Struktur Proyek

```
capkala-investigation/
├── README.md
├── data-collection/                    ← Pengumpulan & pemrosesan data
│   ├── 01_sentinel2_download.py        # Download Sentinel-2 (GEE/Copernicus)
│   ├── 02_sirad_gee.js                 # GEE SIRAD 139 citra Sentinel-1
│   ├── 03_planetscope_ndvi.py          # NDVI change detection PlanetScope
│   └── 04_legal_verification.md        # Verifikasi BHUMI, MODI
├── narration/                          ← Naskah sumber
│   └── capkala_narration_v4.txt
├── images/                             ← Aset visual (10 file)
├── audio/                              ← TTS output (5 mp3, .gitignored)
├── scripts/                            ← Build pipeline
│   ├── 01_generate_tts.py             # Narasi → audio
│   └── 02_assemble_video.sh           # Gambar + audio → video
├── scenes/                             ← Output per-scene (.gitignored)
└── capkala_investigation.mp4           ← Video final (.gitignored)
```

---

## Quick Start

### Prasyarat
- Python 3.11+, ffmpeg
- ElevenLabs API key (`ELEVENLABS_API_KEY` di `~/.hermes/.env`)
- Google Earth Engine account (untuk SIRAD)
- PlanetScope imagery (pre.tif, post.tif)

### Build Video (dari aset yang sudah ada)

```bash
# 1. Generate TTS audio
python3 scripts/01_generate_tts.py

# 2. Render video
bash scripts/02_assemble_video.sh
```

### Full Reproduction (dari data mentah)

```bash
# 1. Download Sentinel-2 imagery
python3 data-collection/01_sentinel2_download.py

# 2. Generate SIRAD (buka di GEE Code Editor)
#    Copy data-collection/02_sirad_gee.js → https://code.earthengine.google.com/
#    Export ke Drive, download ke images/sirad_raw.png

# 3. Process PlanetScope NDVI
#    Place planetscope_pre.tif and planetscope_post.tif in data/
python3 data-collection/03_planetscope_ndvi.py

# 4. Verifikasi legal (manual)
#    Lihat data-collection/04_legal_verification.md
#    Screenshot BHUMI → images/bhumi_screenshot.jpg

# 5. Build video
python3 scripts/01_generate_tts.py
bash scripts/02_assemble_video.sh
```

---

## Scene Breakdown

| Scene | Judul | Durasi | Sumber Data |
|-------|-------|--------|-------------|
| 01 | PENDAHULUAN | 31s | Slide teks |
| 02 | CITRA SENTINEL-2 | 42s | 01_sentinel2_download |
| 03 | ANALISIS SPASIAL | 37s | Slide teks |
| 04 | METODOLOGI | 94s | Semua data |
| 05 | KESIMPULAN | 40s | Slide teks |

Scene 04 — 5 langkah metodologi:
1. GEE + Sentinel-2 (gambar: sentinel2_raw.png)
2. SIRAD 139 citra Sentinel-1 (gambar: sirad_raw.png)
3. PlanetScope NDVI (gambar: planetscope_before_after.png)
4. Verifikasi legal — BHUMI, MODI (gambar: bhumi_screenshot.jpg)
5. Publikasi thread X (gambar: infographic.png)

---

## Koordinat

**Zona Tambang Utara:** 0.6784°N, 109.0836°E, radius 1.5 km

## Bukti

1. Tidak ada WPR (Wilayah Pertambangan Rakyat)
2. RDTR belum rampung
3. MODI — tidak ada IUP
4. BHUMI — TIPE HAK KOSONG, 83 ha
5. Polisi tangkap + sita ekskavator (Maret 2026)
6. Dokumen palsu (Mata Pers, Juli 2025)

## Publikasi

Thread X: [@jalmiburung](https://x.com/jalmiburung)
