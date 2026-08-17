// =====================================================================
// 01 · HELLO, CODE EDITOR
// Day 1 · 15 menit · skrip pertama Anda
// =====================================================================
//
// Tujuan skrip ini hanya satu: memastikan Earth Engine berjalan di akun
// Anda, dan mengenalkan tiga hal yang akan dipakai terus-menerus —
// print, Map.addLayer, dan Inspector.
//
// Jalankan baris demi baris. Setelah tiap bagian, klik Run dan lihat
// apa yang berubah.
// =====================================================================


// ---------------------------------------------------------------------
// 1 · PRINT — cara melihat sesuatu
// ---------------------------------------------------------------------
// Hasilnya muncul di panel Console, kanan atas.

print('Halo Earth Engine');
print('Tahun ini:', 2026);


// ---------------------------------------------------------------------
// 2 · VARIABLES — menyimpan sesuatu dengan nama
// ---------------------------------------------------------------------
var kota  = 'Maumere';
var tahun = 2024;

print(kota, tahun);

// Ganti isi variabel di atas dengan kota Anda, lalu Run lagi.


// ---------------------------------------------------------------------
// 3 · A POINT ON THE MAP
// ---------------------------------------------------------------------
// Perhatikan urutannya: [bujur, lintang] — longitude DULU, baru latitude.
// Ini kebalikan dari cara kita biasa menyebut koordinat, dan merupakan
// salah satu kesalahan paling sering. Kalau peta Anda mendarat di Somalia,
// hampir pasti keduanya tertukar.

var titik = ee.Geometry.Point([122.21, -8.62]);   // Maumere, Flores

Map.centerObject(titik, 11);                       // 11 = tingkat zoom
Map.addLayer(titik, {color: 'red'}, 'Lokasi saya');


// ---------------------------------------------------------------------
// 4 · YOUR FIRST SATELLITE IMAGE
// ---------------------------------------------------------------------
// Ambil satu citra Sentinel-2 mana saja di lokasi itu.

var citra = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
              .filterBounds(titik)
              .filterDate('2024-06-01', '2024-09-30')
              .first();                            // ambil yang pertama

Map.addLayer(citra,
             {bands: ['B4', 'B3', 'B2'], min: 0, max: 3000},
             'Sentinel-2');

// bands: ['B4','B3','B2'] artinya merah-hijau-biru, warna seperti mata
// melihat. min dan max mengatur kecerahan — kalau gambarnya terlalu gelap,
// turunkan max ke 2000; kalau terlalu putih, naikkan ke 4000.


// ---------------------------------------------------------------------
// 5 · WHAT IS ACTUALLY IN THAT IMAGE
// ---------------------------------------------------------------------
print('Isi citra:', citra);

// Buka segitiga kecil di Console. Anda akan melihat daftar band, ukuran
// piksel, dan properti seperti tanggal perekaman.
//
// Perhatikan: yang tercetak BUKAN gambar, melainkan DESKRIPSI tentang
// gambar. Ini inti hari pertama — objek ee. berisi resep, bukan data.


// ---------------------------------------------------------------------
// 6 · INSPECTOR
// ---------------------------------------------------------------------
// Klik tab "Inspector" di panel kanan, lalu klik satu titik di peta.
// Anda akan melihat nilai tiap band di titik itu.
//
// Coba klik di laut, lalu di daratan bervegetasi. Perhatikan bahwa B8
// (inframerah dekat) jauh lebih tinggi di vegetasi. Itulah dasar NDVI,
// yang akan kita pakai besok.


// =====================================================================
// LATIHAN
// =====================================================================
// 1. Ganti titik ke wilayah kerja Anda
// 2. Ganti rentang tanggal ke musim kemarau tahun lalu
// 3. Tampilkan juga versi false colour, dengan menambahkan baris:
//
//    Map.addLayer(citra, {bands: ['B8','B4','B3'], min: 0, max: 4000},
//                 'False colour');
//
//    Pada tampilan ini vegetasi berwarna merah terang. Bandingkan dengan
//    true colour — mana yang lebih mudah untuk membedakan hutan dari
//    lahan terbuka?
