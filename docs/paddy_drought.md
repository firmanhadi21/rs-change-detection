# Kekeringan sawah — `drought-paddy`

Metodologi, asal-usul, hasil uji, dan batasnya. Ditulis 27 September 2026.

Skenario ini menjawab tiga hal untuk **tiap petak**, bukan rata-rata kabupaten:

1. **Sudah ditanam belum, dan mundur berapa hari?** — Sentinel-1 VH
2. **Cukup airkah tanamannya?** — WaPOR ETa dibanding Kc × ET0
3. **Bagaimana dua pekan ke depan?** — prakiraan hujan GFS atas kebutuhan yang
   sudah tertentu dari kalender petak

---

## 1. Asal metode

Tidak ada yang ditemukan sendiri di sini. Semuanya diangkat dari pekerjaan yang
sudah ada di workspace ini, dengan sumber tercantum di tiap modul:

| Bagian | Berasal dari |
|---|---|
| Aturan deteksi tanam (filter median + Heikin-Ashi, ekstrem berjendela, validasi) | `rice-growth-stage-mapping` — algoritma SC (*Standing Crops*), `SC_ALGORITHM_DOCUMENTATION.md` |
| Tanda tangan fenologi sawah (banjir −20 dB → tumbuh → panen) | `s1-land-cover-classification` — `PADDY_DETECTION_README.md` |
| Susunan tumpukan S1 (IW, VH, satu arah orbit, periode 12 hari, filter speckle) | `s1-land-cover-classification/gee_stack_generator.py` |
| Jendela ganda: panjang musim dari banjir berikutnya | `paper3/reference/` — `prototype_double_anchor.py`, `s1_hybrid_calendar.py` |
| SI, Kc (kurva 110 hari yang diregangkan & langkah per fase), CU Christiansen, RI ≥ 0,80 | `paper3/reference/irrigation_performance_dynamic.py` (Sept 2026) |
| WAI = ETa/ETc, sumber WaPOR, ambang FAO-33, persentil ekuitas | `2026/laporan/WATER_ADEQUACY_INDEX_METHODOLOGY.md` |

**Yang sengaja tidak diangkat:** penetapan 6/11 kelas fase pertumbuhan. Repo itu
mengukurnya 47–78% terhadap data latihnya sendiri (lawan 92% untuk ansambel
CNN-nya), sedangkan yang dibutuhkan di sini hanya cekungan tanam dan puncak
sesudahnya. Untuk peta fase, pakai model di repo tersebut.

---

## 2. Jendela ganda — panjang musim diukur, bukan diasumsikan

Umur padi berbeda menurut varietas dan air. Karena itu dua jendela dicari, bukan
satu:

```
jendela 1   cekungan banjir musim ini            -> tanggal tanam
jendela 2   cekungan banjir BERIKUTNYA, 85-200 hari kemudian
            -> panen = awal penurunannya, dikurangi 21 hari olah tanah
```

Bukti bahwa ini penting, dari `hybrid_calendar_evaluation.csv` (BulakBakal,
29 petak, 13 dengan jendela panen dari petani):

| Kalender | Galat tanam (median) | ≤12 hari | Panen di dalam jendela |
|---|---|---|---|
| `fixed110` (optik + 110 hari) | 6 hari | 90% | **0 / 13** |
| `full_sar` (SAR + SAR) | 12 hari | 55% | 11 / 13 |
| `hybrid` (optik + panjang SAR) | 6 hari | 90% | **12 / 13** |

Panjang musim terukur di sana bermedian **75 hari**, bukan 110. Asumsi 110 hari
tidak pernah benar sekali pun.

**Musim berjalan tidak bisa mengukur panjangnya sendiri** — banjir berikutnya
belum terjadi. Maka panjang musim diambil dari median musim-musim sebelumnya
pada petak yang sama (varietas dan kebiasaan air petak itu), dan hanya jika
tidak ada riwayat sama sekali dipakai nilai cadangan 86 hari.

---

## 3. Data

| Peran | Produk | Resolusi | Jeda |
|---|---|---|---|
| Siklus tanam | Sentinel-1 GRD VH, IW, satu arah orbit | 50 m / 12 hari | ~1 hari |
| ETa | `FAO/WAPOR/3/L1_AETI_D` | 300 m / dekade | ~2 pekan |
| ET acuan | `FAO/WAPOR/3/L1_RET_E` | ~9 km / harian | ~3 hari |
| Hujan | CHIRPS harian | 5,5 km | ~3 pekan |
| Prakiraan | GFS 0.25° (16 hari) | 27 km | jam |
| Lengas tanah | ERA5-Land | 11 km | ~7 hari |

Dua catatan untuk tim irigasi:

* **ID aset WaPOR di dokumen WAI salah tulis.** Dokumen mencantumkan
  `FAO/WAPOR/3/L1/AETI_D`; yang benar memakai garis bawah:
  `FAO/WAPOR/3/L1_AETI_D` dan `FAO/WAPOR/3/L1_RET_E`. Mengikuti dokumen apa
  adanya menghasilkan *asset not found*.
* **Pembanding silang yang diresepkan tidak bisa memeriksa musim berjalan.**
  PML-V2 di GEE berhenti Desember 2023 dan WaPOR 2 Maret 2023. WaPOR 3 sendiri
  mutakhir (AETI 11 Sep, RET 24 Sep 2026).

---

## 4. Uji: musim hujan sebagai kontrol

Petak yang sama (Klambu, radius 4 km, Lahan Baku Sawah resmi), dijalankan dua
kali: seperti musim kemarau sekarang, dan seolah-olah pertengahan April.

| | Tertanam | Panjang musim | Anomali terhadap musim biasanya |
|---|---|---|---|
| Kemarau (27 Sep 2026) | 1.370 ha (**43%**) | 99 hari | 497 normal · 65 agak kering · 21 jauh lebih kering |
| Hujan (15 Apr 2026) | 3.074 ha (**96%**) | 93 hari | 1.923 normal · 392 agak kering · 524 lebih kering |

**Deteksi tanam lulus** — 96% lawan 43% adalah kontras yang memang harus muncul,
dari kode dan lapisan yang sama. Luas sawah dari LBS resmi (3.214 ha) juga
sejalan dengan deteksi radar mandiri (3.493 ha).

**Neraca air mutlak tidak lulus**, dan itu mengubah lapisan utama. Lihat §5.

---

## 5. Mengapa lapisan utama adalah anomali, bukan skala mutlak

Pada uji di atas, musim hujan justru terbaca lebih defisit daripada musim
kemarau — terbalik. Penelusurannya:

1. **Bukan salah WaPOR.** Tiga produk ET sepakat di petak yang sama —
   musim hujan: WaPOR 3,32 · MOD16 3,32 · ERA5-Land 3,98 mm/hari; kemarau:
   2,49 · 2,16 · 2,55.
2. **Semuanya mentok di ETa/ET0 ≈ 0,90** pada bulan terbasah. Dengan Kc ≈ 1,1,
   sawah yang tercukupi penuh pun hanya mencapai 0,82 — kelas "cukup" mustahil
   tercapai. Inilah gunanya faktor **1,2** pada implementasi Paper 3, sehingga
   faktor itu dipertahankan (atas dasar ukuran, bukan argumen).
3. **Bukan pula akibat fase awal tergenang.** Dipisah per fase, kekurangannya
   merata: 0,64 awal · 0,66 vegetatif · 0,77 generatif — padahal hujan pada
   jendela itu 13 mm/hari.

Kesimpulan: **ETa satelit di atas sawah tergenang terbaca ~35% di bawah
Kc × ET0 bahkan saat air melimpah.** Ambang FAO-33 karena itu menggambarkan
produk sebanyak ia menggambarkan tanaman — hal yang memang sudah ditandai
"belum dikalibrasi" di dokumen WAI.

Kekeringan adalah **penyimpangan dari biasanya**. Rasio terhadap musim-musim
sebelumnya **pada piksel yang sama** membagi habis bias itu:

```
anomali = SI musim ini / median SI musim-musim sebelumnya (petak yang sama)

≥0,95 normal | 0,85–0,95 agak kering | 0,70–0,85 lebih kering | <0,70 jauh lebih kering
```

Skala mutlak (SI), beserta **supply_mm** dan **demand_mm**, tetap ditulis
sebagai produk: angka yang tidak bisa dibongkar bukan angka yang bisa diaudit.

---

## 6. Batas yang dijaga

* **Tanam ~60 hari terakhir belum bisa dikonfirmasi.** Aturan SC memvalidasi
  cekungan terhadap lima periode di kedua sisi; tajuk belum tumbuh kembali.
  Dilaporkan **provisional** (banjir terdeteksi, menunggu konfirmasi), bukan
  "belum tanam" — sebab justru itulah sinyal yang dicari.
* **Prakiraan hanya hujan.** Pasokan irigasi tidak bisa diprakirakan. Peta
  menunjukkan di mana hujan saja tidak akan menutup kebutuhan — yaitu di mana
  saluran harus bekerja — bukan apa yang akan dilakukan saluran.
* **Prakiraan hujan tropis** andal ~5–7 hari; 14 hari indikatif.
* **WaPOR 300 m di atas grid 50 m**: satu piksel menutupi 36 sel. Sel yang
  kurang dari 60% sawah tertanam tidak dinilai (di Klambu: 2.993 dari 6.013
  piksel tertanam lolos uji ini).
* **Kebutuhan hanya dihitung untuk periode yang pasokannya sudah terbit** —
  WaPOR tertinggal ~2 pekan dan jika tidak, keterlambatan data akan terbaca
  sebagai defisit baru.
* **Kandidat puso adalah daftar untuk dicek lapangan, bukan vonis.**
* **Lapisan sawah resmi selalu mengalahkan deteksi radar.** Pakai
  `--paddy-file` bila ada.

---

## 7. Keluaran

Raster (GeoTIFF, grid analisis): `paddy`, `planting_doy`, `plant_period`,
`delay_days`, `delay_class`, `adequacy`, `adequacy_class`, `anomaly`,
`anomaly_class`, `supply_mm`, `demand_mm`, `outlook_class`, `puso`; ditambah
`stats.json` berisi hektare per kelas, sumber, dan catatan batas.

`--publish` menulis `web/` untuk situs peta seperti **drought.ownmap.id**:

```
web/cog/*.tif      COG EPSG:3857, bertingkat (anomaly_class memimpin)
web/alerts.geojson poligon yang layak dikunjungi + luas (ha)
web/zones.geojson  indeks per petak tersier (bila --zones diberikan)
web/legend.json    nilai, label dwibahasa, warna
web/summary.json   angka utama, sumber, dan daftar batas di §6
```

Legenda dan caveat ikut dalam paket, supaya peta dan raster tidak bisa
berselisih dan batasnya tidak tertinggal di kepala seseorang.

---

## 8. Menjalankan

```bash
# lapisan sawah resmi + paket web
earthchange -s drought-paddy --lat=-6.95 --lon=110.85 -r 8 \
    --paddy-file data/LBS_Ind_2023_0005.tif \
    --zones data/di_klambu_petak.gpkg --zone-field NO_SWAH \
    --publish -n klambu

# musim lalu, untuk pembanding
earthchange -s drought-paddy --lat=-6.95 --lon=110.85 -r 8 \
    --as-of 2026-04-15 --paddy-file data/LBS_Ind_2023_0005.tif -n klambu_lalu
```

Pilihan penting: `--as-of` (tanggal jawaban), `--season-days` (baku 210 — satu
siklus padi plus tenggang, agar tanaman yang berdiri sekarang masuk jendela),
`--baseline-seasons` (baku 2 — dasar anomali dan sumber panjang musim),
`--kc-mode curve110|stage`, `--paddy-grid`, `--orbit-pass`.

Modul: `paddy_phenology.py` (aturan SC, jendela ganda), `paddy_water.py`
(Kc, SI, CU, RI, anomali, Hargreaves), `paddy_data.py` (pengambilan GEE),
`paddy_drought.py` (orkestrasi), `paddy_publish.py` (paket web). Uji:
`tests/test_paddy_*.py`.
