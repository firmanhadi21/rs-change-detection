# Keberulangan karhutla nasional — `fire-national`

Metodologi, keputusan desain, hasil, dan batasnya. Ditulis 13 Oktober 2026.

Pertanyaan yang dijawab bukan "di mana terbakar tahun ini" melainkan **di mana
terbakar berulang kali, dan berapa yang di gambut**. Kebakaran sekali bisa
kecelakaan. Piksel yang terbakar pada enam dari sebelas tahun adalah rezim tata
guna lahan, bukan kecelakaan.

```
python3 -m earthchange.detect --scenario fire-national --backend gee \
    --out-dir output/fire_national
```

Tanpa argumen lain: 38 provinsi, 2015–tahun lengkap terakhir, dua definisi
gambut, dan musim berjalan dari titik panas.

---

## 1. Yang dihasilkan

| Berkas | Isi |
|---|---|
| `provinces/<Provinsi>/recurrence.tif` | uint16 tiga band atau lebih, 500 m: `inside`, satu band per definisi gambut, lalu `bits` |
| `provinces/<Provinsi>/stats.json` | seluruh angka hektar provinsi itu |
| `provinces.csv` | rekap 38 provinsi, satu blok kolom per definisi gambut |
| `stats.json` | total nasional, deret titik panas, dan daftar caveat |
| `fire_recurrence_overview.tif` | raster nasional kasar (2 km), hanya untuk peta |
| `fire_recurrence_national.png` | peta keberulangan |
| `fire_national_ranking.png` | provinsi diurutkan menurut luas terbakar berulang |
| `fire_national_season.png` | musim berjalan vs jendela tanggal yang sama tahun-tahun sebelumnya |

`recurrence.tif` adalah produknya; sisanya turunan. Raster itu yang nanti
ditumpangkan dengan batas konsesi, KHG, atau peta tutupan lahan.

---

## 2. Tiga keputusan desain, masing-masing dipaksa oleh pengukuran

### 2.1 Hanya tahun yang lengkap

MCD64A1 terbit bulanan dan **berhenti di Juli 2026** saat dokumen ini ditulis.
Artinya tahun 2026 baru dua pertiga jalan dan sama sekali **belum memuat musim
Agustus–Oktober**. Memasukkannya ke hitungan keberulangan akan diam-diam
membuat 2026 tampak ringan dibanding tiap tahun lain.

Maka: keberulangan dihitung sampai tahun lengkap terakhir (2025), dan musim
berjalan dilaporkan **terpisah** dari FIRMS, yang mutakhir sampai dua hari lalu.
Batas tahun lengkap dicari sendiri oleh `last_complete_year()`, tidak
dihardcode — supaya dokumen ini tidak perlu diperbarui tiap bulan.

### 2.2 Bitmask, bukan satu band per tahun

Sebelas tahun sebagai sebelas band byte di atas kotak pembatas Maluku ≈ 42 MB,
cukup dekat ke pagu permintaan Earth Engine (50.331.648 byte) untuk gagal di
hari yang buruk. Sebelas tahun yang sama dipadatkan ke satu uint16 — bit ke-*i*
menyala berarti "terbakar pada `years[i]`" — hanya 6 byte per piksel untuk
seluruh tumpukan.

Konsekuensinya lebih penting dari ukurannya: **setiap angka tahunan, setiap
hitungan keberulangan, dan setiap kombinasi epoch dibongkar dari raster yang
sama, secara lokal.** Tidak ada statistik yang dihitung di sisi server yang
bisa bertentangan dengan rasternya. Pelajaran ini dibayar mahal di pekerjaan
sawah: dua rumus luas yang berbeda adalah cara sebuah angka salah sampai ke
halaman publik.

Luas memakai rumus bola yang persis sama dengan `paddy_island.row_areas_ha`,
konstanta jari-jari dan semuanya, supaya dua produk dari repo yang sama tidak
pernah menyebut dua angka untuk satu hal.

### 2.3 Satu kisi global

Tiap provinsi dipaku ke kisi 0,0045° yang sama, berjangkar di (0, 0). 38 raster
itu bisa dimozaik tanpa resampling, dan satu piksel berarti hal yang sama di
Riau maupun di Papua Selatan.

---

## 3. Gambut: dua definisi, sengaja tidak dipilih salah satu

Ini mata rantai terlemah dan dokumen ini menyatakannya keras-keras.

Tidak ada proxy gambut **tanpa unduhan** yang memadai. Diukur ulang di sini
terhadap provinsi yang angka resminya ada, keduanya gagal ke **arah yang
berlawanan**:

| Provinsi | OpenLandMap SOC ≥ 30 | PEATGRIDS > 0 | lazim dikutip |
|---|---|---|---|
| Riau | 3,91 juta ha | 5,83 juta ha | ± 4,0 juta ha |
| Kalimantan Tengah | 6,62 juta ha | 5,27 juta ha | ± 3,0 juta ha |

(Angka ini mereproduksi tabel perbandingan di README — 3,88 dan 5,74 untuk
Riau, 6,55 dan 5,20 untuk Kalteng — selisih tipisnya dari batas GAUL 2025.
Reproduksi mandiri yang cocok, bukan angka baru.)

SOC nyaris tepat di Riau dan 2× berlebih di Kalteng; PEATGRIDS kebalikannya di
Riau dan tetap berlebih di Kalteng. Selisih keduanya di Riau saja 1,9 juta ha.
Memilih satu diam-diam berarti mengubur ketidakpastian ±50% di dalam angka
utama. Maka keduanya dibawa: angka gambut terbakar **diterbitkan sebagai
rentang**, kolom CSV-nya bernama `*_soc` dan `*_peatgrids` sehingga tidak ada
kolom `peat_ha` polos yang bisa salah dikutip, dan grafik menggambar selisihnya
sebagai arsir, bukan garis.

### Yang seharusnya dipakai untuk publikasi

**Gumbricht et al. 2017 (CIFOR), 231 m, terbit peer-review dan bisa disitasi.**
README repo ini sudah membandingkannya per provinsi: paling tepat di Kalteng
(2,63 vs ±3,0) dan Sumsel (1,70 vs ±1,4), dan paling konservatif secara umum.
Perlu unduh sekali (332 MB):

```bash
curl -L -o peat.7z "https://data.cifor.org/api/access/datafile/1727"
7z x peat.7z
python3 -m earthchange.detect --scenario fire-national --backend gee \
    --peat-file TROP-SUBTROP_PeatV21_2016_CIFOR.tif \
    --out-dir output/fire_national_gumbricht
```

Dengan `--peat-source both` (default), peta yang diberikan **memimpin** dan
kedua proxy ikut di belakangnya — sehingga satu angka yang bisa disitir dan
rentang tempat ia duduk terbit bersamaan. Rentang dua-proxy itu pengakuan bahwa
peta yang bisa disitasi belum dipasang, bukan penggantinya.

---

## 4. Musim berjalan: titik panas, bukan luas terbakar

Luas terbakar terlambat berbulan-bulan, jadi tidak bisa menggambarkan musim
yang masih berlangsung. Titik panas bisa. Jendelanya **persis sama tiap tahun**
(1 Agustus – hari ini), satu-satunya cara membandingkan musim yang belum selesai
dengan rekor secara jujur.

Sebelum dipakai, kehomogenan rekam FIRMS di GEE diperiksa: 73 citra harian per
tahun, skala nominal 927 m, band yang sama, 2015 sampai 2026. Tidak ada
pergantian sensor yang bisa disalahartikan sebagai lonjakan musim.

---

## 5. Hasil — 38 provinsi, 2015–2025

Dijalankan 13 Oktober 2026. 38 dari 38 provinsi berhasil.

**Nasional:** **5.472.230 ha** terbakar sekurangnya sekali — 2,8% daratan.
Dari jumlah itu **1.318.664 ha (24%) terbakar ≥2 tahun** dan 380.951 ha ≥3
tahun. Gambut: **2,74–3,60 juta ha**, yaitu **50–66%** dari seluruh yang
terbakar, tergantung definisi gambut.

Sebaran keberulangan runtuh cepat, dan itu pokok persoalannya: 224 ha di
Indonesia terbakar pada **delapan** dari sebelas tahun.

| terbakar | luas |
|---|---|
| 1× | 4.153.566 ha |
| 2× | 937.714 ha |
| 3× | 267.824 ha |
| 4× | 75.842 ha |
| 5–8× | 37.284 ha |

**Per tahun** — deret ini mengikuti ENSO nyaris sempurna:

| tahun | ha | | tahun | ha |
|---|---|---|---|---|
| 2015 | 2.528.286 | | 2021 | 71.452 |
| 2016 | 240.972 | | 2022 | **52.456** |
| 2017 | 161.155 | | 2023 | 1.099.440 |
| 2018 | 715.960 | | 2024 | 136.413 |
| 2019 | 2.056.142 | | 2025 | 100.790 |
| 2020 | 171.562 | | | |

2020–2022 adalah La Niña tiga tahun beruntun: 2022 **48× lebih sepi** dari
2015, dan 18 dari 38 provinsi mencatat nol. Nol itu nyata, bukan lubang data —
DKI Jakarta nol pada sebelas tahun (memang kota), sementara Riau tetap mencatat
17.098 ha pada 2021. Lalu El Niño 2023 mengembalikannya 21× lipat.

**Sepuluh provinsi dengan luas terbakar berulang terbesar:**

| Provinsi | terbakar (ha) | berulang ≥2× (ha) | % berulang | gambut | maks |
|---|---|---|---|---|---|
| Kalimantan Tengah | 989.047 | 277.662 | 28% | 94–95% | 5× |
| Papua Selatan | 925.561 | 273.687 | 30% | 14–84% | 8× |
| Sumatera Selatan | 808.902 | 220.896 | 27% | 78–83% | 5× |
| Kalimantan Selatan | 403.549 | 123.053 | 30% | 70–72% | 7× |
| Kalimantan Barat | 360.566 | 71.095 | 20% | 76–77% | 8× |
| Nusa Tenggara Timur | 198.017 | 62.391 | 32% | 0–2% | 8× |
| Lampung | 185.862 | 57.128 | 31% | 24–43% | 7× |
| Nusa Tenggara Barat | 94.130 | 40.828 | **43%** | 0–2% | 7× |
| Kalimantan Timur | 380.937 | 40.576 | 11% | 24–43% | 4× |
| Maluku | 212.649 | 36.711 | 17% | 1–7% | 8× |

Dua hal menonjol. **Papua Selatan** sudah setara Kalteng dalam luas terbakar
berulang — dan rentang gambutnya 14–84% menunjukkan betapa tidak siapnya
lapisan gambut terbuka untuk Papua (PEATGRIDS memberi Papua 11,92 juta ha
melawan ±3,7 resmi; 14% jauh lebih masuk akal dari 84%). **NTB dan NTT** punya
porsi berulang tertinggi di Indonesia pada tanah yang sama sekali bukan gambut —
rezim kebakaran savana, persoalan yang berbeda dari karhutla gambut dan sering
hilang dari pemberitaan yang berpusat pada gambut.

### 5.1 Musim 2026 — terbesar dalam rekaman

Luas terbakar belum bisa bicara (MCD64A1 baru sampai Juli). Titik panas bisa,
dan hasilnya tegas. Jendela **1 Agustus – 13 Oktober**, sama persis tiap tahun:

| tahun | titik panas | | tahun | titik panas |
|---|---|---|---|---|
| **2026** | **483.991** | | 2019 | 280.503 |
| 2015 | 320.973 | | 2023 | 175.488 |
| 2018 | 141.455 | | 2024 | 70.269 |

**2026 adalah ×1,51 krisis 2015 dan ×4,3 rata-rata 2015–2025** pada jendela
tanggal yang sama. Sebelum angka ini dipercaya, kehomogenan rekaman FIRMS
diperiksa (§4): tidak ada pergantian sensor.

Kenaikannya hampir merata — 37 dari 38 provinsi di atas rata-ratanya sendiri,
satu-satunya pengecualian Nusa Tenggara Timur (×0,9):

| Provinsi | 2026 | rata-rata sebelumnya | rasio |
|---|---|---|---|
| Kalimantan Tengah | 117.010 | 18.304 | ×6,4 |
| Kalimantan Barat | 81.163 | 19.521 | ×4,2 |
| Papua Selatan | 56.793 | 8.362 | ×6,8 |
| Sumatera Selatan | 46.330 | 10.815 | ×4,3 |
| Kalimantan Timur | 35.787 | 7.003 | ×5,1 |
| Papua Barat | 11.639 | 178 | ×65 |

Ini mengkonfirmasi — secara mandiri, dari data terbuka — arah yang disebut
laporan Pantau Gambut dan Greenpeace Indonesia untuk musim 2026, termasuk
Kalimantan Tengah dan Papua Selatan sebagai dua titik terburuk. **Angkanya
tidak bisa dibandingkan langsung**: "titik sumber asap" yang mereka hitung
adalah satuan lain, bukan piksel-hari FIRMS.

### 5.2 Satu uji silang yang menenangkan, satu yang tidak

Total nasional 2015 di sini, 2,53 juta ha, duduk dekat angka KLHK yang lazim
dikutip untuk 2015 (±2,6 juta ha) — selisih beberapa persen, jauh lebih baik
dari dugaan awal. *(Perlu diverifikasi terhadap SIPONGI sebelum disitir.)*

Yang tidak menenangkan: **di Riau** MCD64A1 memberi 54.018 ha untuk 2015,
sementara angka resmi provinsi itu berkisar ratusan ribu hektar. Kecocokan di
tingkat nasional karena itu melibatkan galat yang saling meniadakan, bukan
karena tiap provinsi tepat. Pakai angka nasional dengan percaya diri; pakai
angka provinsi gambut sebagai **batas bawah**.

---

## 6. Yang **tidak** boleh disimpulkan dari produk ini

**Titik panas atau bekas bakar di dalam konsesi bukan bukti bahwa pemegang
konsesi yang membakar.** Ini lapisan penyaring. Atribusi memerlukan geometri
bekas bakar, waktu dan pola penyalaan, angin, penguasaan lahan sampai tingkat
blok, dan pada akhirnya proses hukum. Peta yang menyiratkan pembakaran sengaja
bisa dipatahkan pada satu titik yang kelewat diklaim, dan seluruh sisanya ikut
jatuh.

**MCD64A1 500 m melewatkan api kecil.** Angka di sini adalah batas bawah, paling
parah untuk pembakaran lahan rakyat berskala kecil, dan untuk api gambut yang
membara di bawah permukaan tanpa bekas bakar permukaan yang jelas. Angka resmi
KLHK lebih besar; perbedaannya bukan pertentangan, melainkan dua definisi dan
dua batas deteksi yang berbeda.

**`burned_ha` adalah luas berbeda yang terbakar sekurangnya sekali**, bukan
jumlah angka tahunan. Piksel yang terbakar enam tahun bernilai satu hektar di
sini dan enam di penjumlahan itu. Keduanya benar untuk pertanyaan yang berbeda;
yang salah adalah menukar keduanya.

**Titik panas adalah hitungan deteksi, bukan luas.** Satuannya piksel-hari FIRMS
1 km. VIIRS 375 m akan merinci lebih banyak dan tidak dipakai di sini karena
tidak tersedia sebagai deret panjang yang homogen di GEE.

---

## 7. Langkah berikutnya yang didukung produk ini

Raster per provinsi dirancang agar tiga pekerjaan lanjutan hanya perlu
menumpangkan lapisan, bukan menghitung ulang kebakaran:

1. **Titik panas × konsesi.** Perlu batas PBPH/HTI dan HGU sawit serta KHG.
   Aritmetika titik-dalam-poligon, sepele begitu poligonnya ada; kendalanya
   akses data, bukan metode. Batas konsesi yang beredar tidak resmi dan tidak
   lengkap, jadi hitungannya batas bawah di atas penyebut yang tidak pasti.
2. **Tata guna lahan pasca-bakar.** Bekas bakar 2015–2019 mudah; mengklasifikasi
   yang tumbuh di atasnya sekarang adalah pekerjaannya. Sawit relatif bisa
   (peta sawit global, atau pendekatan S1+S2 di `s1-land-cover-classification`).
   Memisahkan sawit dari akasia dari belukar yang beregenerasi adalah bagian
   sulitnya — semuanya berkayu dan mirip di optik.
3. **Pengeringan gambut.** Memetakan kanal langsung butuh citra resolusi tinggi
   dan rumit. Penurunan muka tanah gambut dari InSAR adalah indikator yang lebih
   bisa dipertahankan, dan perangkatnya sudah ada di repo ini.
