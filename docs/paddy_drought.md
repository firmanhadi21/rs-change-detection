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

### Dua sumbu yang berbeda: kalender dan Kc

Mudah tertukar, jadi dipisah tegas. `--calendar` memilih **dari mana tanggalnya**,
`--kc-mode` memilih **bentuk kurva kebutuhan air**.

| `--calendar` | Tanggal tanam | Panjang musim |
|---|---|---|
| `fixed110` | optik (NDWI maksimum) | diasumsikan 110 hari |
| `full_sar` | palung radar | jendela kedua radar |
| **`hybrid`** (baku) | **optik** | **jendela kedua radar** |

Skor terhadap catatan petani (BulakBakal, 29 petak, 13 dengan jendela panen):

| Arm | Galat tanam (median) | ≤12 hari | Panen di dalam jendela |
|---|---|---|---|
| `fixed110` | 6 hari | 90% | **0 / 13** |
| `full_sar` | 12 hari | 55% | 11 / 13 |
| **`hybrid`** | **6 hari** | **90%** | **12 / 13** |

Jadi tanggal optik dua kali lebih tepat, sementara panjang musim radar yang
memenangkan jendela panen — `hybrid` mengambil keduanya.

**`--kc-mode curve110` adalah metode terkini, bukan asumsi 110 hari.** Namanya
menyesatkan: yang diambil adalah **bentuk** kurva 110 hari, lalu diregangkan ke
panjang musim yang terukur (di rujukan disebut `si_rescaled`, berbeda dari
`si_constant110` yang lama). Bedanya dengan `stage` hanya di desimal ketiga SI
(unit 4: 0,9730 constant → 0,9851 rescaled → 0,9887 stage), jadi bukan di situ
ketelitiannya berada.

### Bagaimana arm optik dijaga

Tanggal optik hanya dipakai bila dapat dipercaya — dan tanam terjadi di musim
hujan, justru saat Sentinel-2 paling sedikit melihat:

* **≥3 pengamatan cerah** (Cloud Score+), bukan satu-dua kilasan;
* **NDWI benar-benar positif** — hari terbasah yang tidak basah bukan sawah
  tergenang;
* **selisih ≤24 hari dari palung radar** (dua periode S1) — kalau berbeda jauh,
  itu kejadian lain.

Kalau gagal, tanggal radar yang dipakai dan pikselnya ditandai. Lapisan
`calendar_arm` (1 = optik, 0 = radar) dan `calendar.optical_share` di
`stats.json` melaporkan campurannya.

Diukur pada satu ubin padat Karawang: **18,5% tanam memakai tanggal optik**, 82%
tanggal identik dengan radar, median selisih 0 hari, p90 7 hari — dan hektare
kelas kemunduran bergeser di bawah 1%. Awan musim hujan adalah alasan angkanya
tidak lebih tinggi, dan itulah gunanya jalur cadangan.

**Arm berlaku untuk semua musim atau tidak sama sekali.** Kemunduran tanam adalah
selisih **antar** musim; memakai metode berbeda di satu sisinya berarti mengukur
metodenya, bukan kemundurannya — selisih ~6 hari itu sendiri akan terbaca sebagai
setengah periode keterlambatan.

### Diuji pada 2 juta hektare: kedua arm hampir sama

Skor BulakBakal diukur pada 29 petak dalam satu musim. Dijalankan penuh pada Jawa
Barat dan Jawa Tengah (442 ubin, 1,9 juta ha sawah, 2,4 juta piksel bertanggal):

| | Jawa Barat | Jawa Tengah |
|---|---|---|
| Tanggal tanam **identik** | **92,9%** | **96,8%** |
| Selisih median | 0 hari | 0 hari |
| Selisih rata-rata | 0,9 hari | 0,3 hari |
| Selisih p90 | 0 hari | 0 hari |
| **Bagian memakai tanggal optik** | **7,3%** | **3,3%** |

`not_planted_pct`, `median_delay_days`, dan `season_length_days_median` **sama
sampai desimalnya** pada kedua arm di kedua provinsi; kelas-kelas lain bergeser
≤1%.

Sebabnya ketersediaan, bukan metode: NDWI maksimum hanya bisa menanggali tanam
bila langit cerah dekat waktu tanam, dan tanam terjadi di musim hujan. Keunggulan
6-lawan-12-hari itu nyata di tingkat petak, tetapi hanya berlaku pada 3–7% luas
sawah Jawa, sehingga tidak dapat menggerakkan angka provinsi.

**Kesimpulan yang jujur:** jalur optik layak dipertahankan — biayanya hampir nol
(laju tetap 9–10 detik per ubin) dan ia memperbaiki tanggal yang dijangkaunya —
tetapi ia **bukan** alasan memilih satu konfigurasi atas yang lain pada skala
provinsi, dan tidak boleh dijual sebagai alasan itu. `full_sar` adalah pilihan
produksi yang sah di sini.

Satu catatan pembacaan: sisa perbedaan luas (~1%) **bukan** dari arm-nya. Arah
orbit terpilih identik pada seluruh 442 ubin bersama, dan hanya 2 ubin berbeda
luas sawahnya (321 ha). Sisanya karena cache `full_sar` memuat ubin yang diambil
berjam-jam berselang: `covered` bergantung pada citra Sentinel-1 yang **ada saat
pengambilan**, sehingga masker yang diturunkan ulang kemudian berbeda ~1%. Itu
batas reproduktibilitas produk ini, bukan cacat kode — dan berarti dua paket
hanya dapat dibandingkan angka-per-angka bila radar dasarnya sama.

---

## 3. Data

| Peran | Produk | Resolusi | Jeda |
|---|---|---|---|
| Siklus tanam | Sentinel-1 GRD VH, IW, satu arah orbit | 10 m → filter bintik 90 m | ~1 hari |
| ETa | `FAO/WAPOR/3/L1_AETI_D` | 300 m / dekade | ~2 pekan |
| ET acuan | `FAO/WAPOR/3/L1_RET_E` | ~9 km / harian | ~3 hari |
| Hujan | CHIRPS harian | 5,5 km | ~3 pekan |
| Prakiraan | GFS 0.25° (16 hari) | 27 km | jam |
| Lengas tanah | ERA5-Land | 11 km | ~7 hari |
| Sebaran sawah | Lahan Baku Sawah 2023 | 0,0005° = 55,66 m | tahunan |

### Jaringan analisis: 0,0005°, mengikuti LBS

Semua lapisan diunduh pada **satu** jaringan, dan jaringan itu bukan angka
bulat. Raster LBS nasional berada pada langkah 0,0005° (55,66 m) dengan titik
asal **(94,9995; 6,0007)** — dan 6,0007 **bukan** kelipatan 0,0005. Jaringan
yang berjangkar di nol karena itu melewatkan lapisan resmi sebesar 0,4 piksel,
sekitar 22 m di setiap tepi petak: sawah yang tidak ada di satu sisi, sawah yang
hilang di sisi lain.

Dua hal yang sudah diuji langsung ke Earth Engine (`crs_transform`, bukan
`scale`):

* Meminta `scale=55,66` m menghasilkan 0,00050000228° — dekat, tapi tidak pernah
  jatuh pada tepi piksel LBS, sehingga **setiap** ubin ikut diresample.
* Dengan `crs_transform` berjangkar pada asal LBS, hasil unduhan jatuh tepat
  pada jaringan LBS (selisih bilangan bulat piksel), dan membaca LBS menjadi
  sekadar potong-jendela: diuji di Klambu, **882 piksel sawah** lewat kedua
  jalur, isi array identik.

Karena itu jaringan diambil dari `--paddy-file` bila ada; kalau tidak, dari
jaringan LBS (`--paddy-grid lbs`, baku). Angka dalam meter tetap bisa diberikan
(`--paddy-grid 20`) dan dijangkarkan di nol, sehingga antar-ubin tetap sebidang
— syarat mutlak agar mosaik nasional tidak perlu diresample.

### Jaringan bukan resolusi

Grid 55,66 m tidak membuat semua lapisan 55,66 m. Yang jujur, per lapisan
(`native_m` di `stats.json`, `legend.json`, dan `summary.json`):

| Lapisan | Digambar pada | Informasinya |
|---|---|---|
| `paddy` | 55,66 m | 55,66 m (LBS) atau 90 m (deteksi radar) |
| `planting_doy`, `plant_period`, `delay_days`, `delay_class` | 55,66 m | **90 m** (radius filter bintik) |
| `adequacy*`, `anomaly*`, `supply_mm`, `demand_mm`, `puso` | 55,66 m | **300 m** (WaPOR AETI) |
| `outlook_class` | 55,66 m | **27,75 km** (GFS 0,25°) |

Lapisan tanam mendekati 55 m dan itulah yang bergerak lebih dulu saat kekeringan.
Lapisan air adalah 300 m yang digambar pada jaringan 55 m: satu sel WaPOR
menutupi sekitar 29 sel analisis, dan karena itu hanya sel yang didominasi sawah
tertanam yang dinilai (`PURE_ENOUGH = 0,6`).

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

Kedua angka di atas dihitung pada grid 50 m yang lama. Kasus kemarau dijalankan
ulang pada jaringan LBS (55,66 m): sawah 3.226 ha, tertanam 1.384 ha (42,9%),
panjang musim 99 hari, anomali 565 normal · 76 agak kering · 2 lebih kering ·
31 jauh lebih kering. Pergantian jaringan **tidak menggeser kesimpulan apa pun**
— dan itu memang yang diharapkan; yang berubah adalah lapisan sawah resmi tidak
lagi diresample.

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

  Besarnya jalur itu sekarang ikut dilaporkan (`planted_provisional_ha`,
  `planted_provisional_pct`), karena tanpa angkanya peringatan di atas tidak bisa
  ditimbang. Di Klambu: **18,7% dari tanam terdeteksi bersifat provisional pada
  musim kemarau** (849 dari 4.533 piksel) lawan **2,3% pada musim hujan** (237
  dari 10.092). Artinya angka "belum tanam" musim kemarau justru paling
  bergantung pada jalur yang paling lemah, dan **harus diperiksa dengan angka
  tanam Dinas Pertanian sebelum diterbitkan** — lihat §11.
* **Prakiraan hanya hujan.** Pasokan irigasi tidak bisa diprakirakan. Peta
  menunjukkan di mana hujan saja tidak akan menutup kebutuhan — yaitu di mana
  saluran harus bekerja — bukan apa yang akan dilakukan saluran.
* **Prakiraan hujan tropis** andal ~5–7 hari; 14 hari indikatif.
* **WaPOR 300 m di atas grid 55,66 m**: satu piksel menutupi sekitar 29 sel.
  Sel yang kurang dari 60% sawah tertanam tidak dinilai (di Klambu: 2.446 dari
  4.533 piksel tertanam lolos uji ini).
* **Prakiraan dihitung hanya untuk hari yang sudah terbit.** Satu run GFS
  diterbitkan jam-demi-jam, sehingga permintaan 14 hari tak lama setelah 00Z
  meninggalkan hari-hari terakhir kosong. Hari yang belum ada dilewati di
  **kedua** sisi — membandingkan kebutuhan 7 hari dengan hujan 3 hari akan
  mencetak defisit dari data yang belum lengkap — dan jumlah hari yang benar-benar
  terpakai dilaporkan (`outlook.lead_days`).
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
web/legend.json    nilai, label dwibahasa, warna, plus grid_m dan native_m
web/summary.json   angka utama, sumber, resolusi per lapisan, dan batas di §6
```

Legenda dan caveat ikut dalam paket, supaya peta dan raster tidak bisa
berselisih dan batasnya tidak tertinggal di kepala seseorang. Termasuk
resolusinya: tiap lapisan di `legend.json` membawa `grid_m` (jaringan yang
digambar) dan `native_m` (resolusi informasinya), sehingga penampil peta bisa
menyatakan sendiri bahwa lapisan air adalah 300 m, bukan ukuran per petak.

---

## 8. Skala nasional: satu pulau sebagai satu pekerjaan

Pulau adalah satuan **pelaporan dan penerbitan**, bukan satuan hitung. Kotak
pembatas Sumatera sekitar 1,85 juta km² sementara sawahnya 1,77 juta ha — permintaan
seluas pulau berarti meminta ratusan ribu kali lebih banyak piksel daripada
tanamannya. Earth Engine pun menolaknya: batas satu permintaan adalah
**50.331.648 byte**.

Karena itu pulau dipotong menjadi ubin. Ukurannya diukur, bukan dipilih — dengan
tumpukan 85 periode yang sebenarnya:

| Ubin | Hasil |
|---|---|
| 0,25° (27,8 km) | **ditolak** — 106.462.500 byte, dua kali lipat batas |
| **0,125° (13,9 km)** | **15,5 MB dalam 11 detik** ✓ |

`drought-paddy-island` mengerjakan satu pulau: menyusun indeks ubin dari lapisan
sawah, mengerjakan ubin **yang paling padat sawah lebih dulu**, lalu memosaik,
merekap, dan menerbitkan. Ubin yang sudah selesai tidak diunduh ulang, jadi
pekerjaan yang terhenti bisa dilanjutkan.

| Pulau | Ubin | Juta ha | % | Ubin untuk 90% | Jam (4 pekerja) |
|---|---|---|---|---|---|
| Jawa | 783 | 3,423 | 45,8 | 493 | 4,9 |
| Sumatera | 1.703 | 1,768 | 23,7 | 674 | 10,6 |
| Sulawesi | 730 | 0,970 | 13,0 | 276 | 4,6 |
| Kalimantan | 1.050 | 0,739 | 9,9 | 319 | 6,6 |
| Bali–Nusa Tenggara | 464 | 0,482 | 6,4 | 196 | 2,9 |
| Papua | 75 | 0,049 | 0,7 | 21 | 0,5 |
| Maluku | 78 | 0,028 | 0,4 | 28 | 0,5 |
| **Nasional** | **4.932** | **7,47** | 100 | 2.022 | ~31 |

Sebarannya sangat miring: **Jawa memuat 46% sawah nasional dalam 16% ubin**, jadi
Jawa sekaligus yang terpenting dan yang termurah. `--coverage 0.9` memangkas
sekitar dua pertiga ubin.

### Arah orbit tidak bisa dipatok

Temuan yang mengubah hasil, dan berlaku di luar skenario ini. Diukur pada sembilan
ubin melintang Jawa, jumlah periode kosong dari 85:

| Ubin | Bujur | Descending | Ascending | Dipilih |
|---|---|---|---|---|
| t0100_0086 | 105,8 | 54 kosong, rentetan 13 | **1, rentetan 1** | ASC |
| t0103_0098 | 107,3 | 13, rentetan 4 | **1, rentetan 1** | ASC |
| t0107_0113 | 109,2 | **9, rentetan 3** | 13, rentetan 4 | **DESC** |
| t0102_0135 | 111,9 | 42, rentetan 23 | **1, rentetan 1** | ASC |

**Descending adalah pilihan yang salah untuk sebagian besar Jawa** — dan untuk
sebagian kecil justru benar. Satu ubin di Jawa Timur kehilangan 42 dari 85 periode
dengan rentetan kosong 23 periode (276 hari): seluruh ubin terbuang, dan dalam uji
pertama memang terbuang. Dengan orbit dipilih per ubin, lubang menyusut menjadi
rentetan ≤3 periode — yaitu tepat yang sudah bisa ditambal `fill_time_gaps`.

Karena itu `--orbit-pass auto` kini benar-benar otomatis: jumlah akuisisi tiap
arah dihitung dalam **satu** permintaan (`paddy_data.s1_acquisitions`), arah dengan
lubang terpendek dipakai, dan pilihan itu **dicatat bersama ubinnya**. Mencampur
arah di dalam satu tumpukan tetap tidak boleh — geometri menggeser hamburan balik
lebih besar daripada tanamannya.

Ubin yang bahkan dengan orbit terbaiknya masih berlubang panjang dilaporkan
sebagai **tidak dapat dinilai siklus ini** beserta alasannya, dan hektare sawahnya
dijumlahkan sebagai `tiles.unscored_paddy_ha` — penyebut yang jujur untuk total
satu pulau.

### Provinsi: satuan yang sebenarnya dipakai instansi

Pulau memotong dengan rapi; **provinsi** yang dilaporkan Dinas Pertanian dan BPS.
Keduanya hanya pengelompokan ubin yang sama, jadi `--province` memilih ubin dari
indeks yang sudah ditandai (FAO GAUL 2025, 38 provinsi) dan dua provinsi
**berbagi satu cache ubin per arm** — 68 ubin yang dibagi Jawa Barat dan Jawa
Tengah dihitung sekali, bukan dua kali.

Angka provinsi **bukan jumlah ubinnya**. Ubin di perbatasan milik dua provinsi,
dan menjumlahkannya menggelembungkan keduanya. Karena itu batas GAUL dibakar ke
jaringan mosaiknya sendiri dan kelas dijumlahkan hanya di dalamnya
(`admin_totals`). Kedua angka tetap ditulis: yang di dalam batas sebagai angka
utama, jumlah per-ubin di `per_tile_totals`, dan selisihnya **adalah** perhitungan
ganda perbatasan itu.

Indeks provinsinya sejalan dengan Lahan Baku Sawah resmi:

| Provinsi | Indeks ini | LBS resmi |
|---|---|---|
| Jawa Barat | 0,932 juta ha | ~0,929 |
| Jawa Tengah | 0,992 juta ha | ~1,043 |
| Jawa Timur | 1,225 juta ha | ~1,214 |

### Menjalankan

```bash
# satu provinsi, kalender hybrid (baku)
earthchange -s drought-paddy-island --province "Jawa Barat" \
    --paddy-file data/LBS_Ind_2023_0005.tif \
    --tiles-dir output/tiles_hybrid

# provinsi tetangga, cache yang sama: ubin perbatasan tidak dihitung ulang
earthchange -s drought-paddy-island --province "Jawa Tengah" \
    --paddy-file data/LBS_Ind_2023_0005.tif \
    --tiles-dir output/tiles_hybrid

# arm pembanding — cache TERPISAH, karena produknya berbeda
earthchange -s drought-paddy-island --province "Jawa Barat" \
    --paddy-file data/LBS_Ind_2023_0005.tif \
    --calendar full_sar --tiles-dir output/tiles_full_sar

# satu pulau, atau seluruh negeri pulau demi pulau
earthchange -s drought-paddy-island --island Jawa \
    --paddy-file data/LBS_Ind_2023_0005.tif
earthchange -s drought-paddy-island --island all \
    --paddy-file data/LBS_Ind_2023_0005.tif --coverage 0.9
```

Cache ubin **tidak boleh dibagi antar arm** — produknya berbeda, dan ubin yang
sudah selesai tidak dihitung ulang, sehingga arm yang tercampur tidak akan
terlihat.

### Hasil pertama: Jawa Barat dan Jawa Tengah, 27 September 2026

442 ubin, dua arm, 162 menit pada 8 pekerja. Nol ubin gagal, nol ubin kosong.

| | Jawa Barat | Jawa Tengah |
|---|---|---|
| Sawah di dalam batas | 902.214 – 912.727 ha | 980.820 – 983.427 ha |
| LBS resmi (pembanding) | ~929.000 ha | ~1.043.000 ha |
| Tertanam | 213.000 – 216.000 ha | 318.000 – 319.000 ha |
| **Belum tanam** | **66,5%** | **60,6%** |
| Panjang musim (median) | 92,5 hari | 86,5 hari |
| Kandidat puso | ~145.000 ha | ~153.000 ha |
| Arah orbit terpilih | ASCENDING 230/230 | ASCENDING 162, **DESCENDING 63** |
| Hitung ganda perbatasan | **66.370 ha** | **120.431 ha** |

Rentang pada dua baris pertama adalah selisih antar arm (~1%), yang sebabnya
dijelaskan di §2 — bukan kalendernya.

Dua hal yang perlu dibaca dari tabel ini:

* **Hitung ganda perbatasan besar.** Menjumlahkan ubin akan menambahkan 66.370 ha
  pada Jawa Barat dan 120.431 ha pada Jawa Tengah — sebesar satu kabupaten.
  Karena itu angka provinsi selalu dari masker batas.
* **Jawa Tengah memilih DESCENDING pada 63 ubin.** Arah orbit yang dipatok akan
  salah menangani 63 ubin di satu provinsi saja.

Keluaran per pulau: `<Pulau>_<lapisan>.tif` (mosaik, tanpa resample — ubin memang
satu jaringan), `stats.json` (rekap pulau + tabel per ubin + arah orbit tiap
ubin), `tile_index.csv`/`.geojson`, dan `web/` dengan kontrak yang sama seperti
satu lokasi.

### Yang perlu dibangun: riwayat yang disimpan

Tumpukan membentang ~1.012 hari, dan hampir seluruhnya adalah masa lalu yang tidak
berubah. Dihitung langsung dari jendela musimnya:

| Siklus berikutnya | Periode baru | Bisa dipakai ulang |
|---|---|---|
| +12 hari | **2 dari 85 (2,4%)** | 83 (97,6%) |
| +24 hari | 3 | 82 |
| +120 hari | 11 | 74 |

Dan penting: **ember 12-hari antar siklus persis berhimpit** — awal rentang
bergeser tepat 12 hari ketika `as_of` bergeser 12 hari, jadi setiap ember lama
tetap ember yang sama. Syaratnya `as_of` maju dalam kelipatan 12 hari; maju 7
hari akan menggeser semua ember dan tidak ada yang bisa dipakai ulang.

Karena itu cache sebaiknya diberi kunci **tanggal awal periode**, bukan indeks,
supaya pemakaian ulang terjadi sendiri. Dengan itu satu siklus nasional turun dari
~31 jam menjadi sekitar 45 menit — dari pekerjaan sekali-jalan menjadi denyut rutin
tiap 12 hari. Belum dibangun.

---

## 9. Menjalankan

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
`--kc-mode curve110|stage`, `--orbit-pass`, dan `--paddy-grid` (baku `lbs`:
ikut jaringan `--paddy-file`, atau jaringan LBS nasional; angka = ukuran piksel
dalam meter, mis. `--paddy-grid 20` untuk satu daerah irigasi).

Modul: `paddy_phenology.py` (aturan SC, jendela ganda), `paddy_water.py`
(Kc, SI, CU, RI, anomali, Hargreaves), `paddy_data.py` (pengambilan GEE),
`paddy_tiles.py` (indeks ubin, provinsi), `paddy_island.py` (satu wilayah, dari
ubin sampai paket web, plus `finalise` untuk menurunkan ulang tanpa GEE),
`paddy_drought.py` (orkestrasi), `paddy_publish.py` (paket web). Uji:
`tests/test_paddy_*.py`.

---

## 11. Yang belum divalidasi — jangan diterbitkan tanpa ini

Satu angka menonjol dan belum layak diedarkan sebagai fakta:

> **Belum tanam 66,5% (Jawa Barat) dan 60,6% (Jawa Tengah) per 27 September 2026.**

Masuk akal untuk puncak musim kemarau, dan kontras musim hujan di Klambu (96%
tertanam) menunjukkan detektornya bekerja. Tetapi angka ini adalah angka paling
berkonsekuensi dalam produk, dan bergantung pada bagian yang paling lemah:
aturan SC tidak dapat mengonfirmasi tanam ~60 hari terakhir, dan di musim kemarau
**18,7%** tanam terdeteksi hanya provisional (Klambu). Bila detektor banjir
provisional terlalu berhati-hati, sebagian "belum tanam" sesungguhnya adalah tanam
gadu yang baru berjalan.

Yang diperlukan, dan tidak dapat dipenuhi dari satelit sendiri:

1. **Angka tanam Dinas Pertanian per kabupaten** untuk musim gadu 2026, dibandingkan
   dengan `planted_ha` per kabupaten.
2. **Beberapa petak cek lapangan** pada piksel `delay_class == 4` (belum tanam) dan
   pada piksel provisional — dua kesalahan yang berbeda arah.
3. Bila keduanya sejalan, angka ini bisa diterbitkan; bila tidak, yang perlu
   disetel adalah `flood_signature` (`drop_db`, `floor_db`), bukan pelaporannya.

Sampai itu dilakukan, sajikan angka ini dengan `planted_provisional_pct` di
sebelahnya, dan sebut musim yang dimaksud (gadu/MT2), bukan "sawah tidak
digarap".
