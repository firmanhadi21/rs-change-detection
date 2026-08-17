// =====================================================================
// 02 · JUST ENOUGH JAVASCRIPT  +  CLIENT vs SERVER
// Day 1 · 60 menit · bagian terpenting seluruh webinar
// =====================================================================
//
// Anda tidak perlu belajar JavaScript. Anda perlu enam hal, dan satu
// konsep yang menjelaskan hampir semua error membingungkan di Earth
// Engine. Bagian 7 adalah konsep itu.
// =====================================================================


// ---------------------------------------------------------------------
// 1 · VARIABLES
// ---------------------------------------------------------------------
var teks   = 'Sikka';        // teks pakai tanda kutip
var angka  = 2024;           // angka tanpa kutip
var benar  = true;           // true / false

print(teks, angka, benar);


// ---------------------------------------------------------------------
// 2 · LISTS — hitungan mulai dari NOL
// ---------------------------------------------------------------------
var bands = ['B4', 'B3', 'B2'];

print('Seluruh daftar:', bands);
print('Anggota pertama:', bands[0]);    // 'B4', bukan bands[1]
print('Jumlah anggota:', bands.length);

// Mulai dari nol adalah sumber kesalahan nomor satu bagi orang yang
// terbiasa dengan spreadsheet. bands[3] tidak ada — daftarnya hanya
// punya indeks 0, 1, 2.


// ---------------------------------------------------------------------
// 3 · DICTIONARIES — pasangan nama: nilai
// ---------------------------------------------------------------------
var visual = {
  bands: ['B4', 'B3', 'B2'],
  min: 0,
  max: 3000
};

print('Pengaturan tampilan:', visual);
print('Nilai max:', visual.max);

// Hampir semua fungsi Earth Engine menerima dictionary seperti ini
// sebagai parameter. Urutan penulisannya tidak penting; namanya penting.


// ---------------------------------------------------------------------
// 4 · FUNCTIONS — instruksi yang diberi nama
// ---------------------------------------------------------------------
function luasPersegi (sisi) {
  return sisi * sisi;
}

print('Luas 5x5:', luasPersegi(5));

// Fungsi berguna karena bisa dipakai berulang pada banyak hal sekaligus.
// Di bagian 6 kita memakainya untuk memproses ratusan citra.


// ---------------------------------------------------------------------
// 5 · CHAINING — merangkai perintah
// ---------------------------------------------------------------------
var aoi = ee.Geometry.Point([122.21, -8.62]).buffer(10000);

var koleksi = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                .filterBounds(aoi)                          // saring wilayah
                .filterDate('2024-06-01', '2024-09-30');    // saring tanggal

print('Jumlah citra ditemukan:', koleksi.size());

// Titik di awal baris berarti "lalu lakukan ini pada hasil sebelumnya".
// Dibaca seperti kalimat, dari atas ke bawah.


// ---------------------------------------------------------------------
// 6 · MAP — menerapkan fungsi ke SEMUA citra
// ---------------------------------------------------------------------
// Ini yang membuat Earth Engine kuat: satu instruksi, ratusan citra.

function tambahNDVI (image) {
  var ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI');
  return image.addBands(ndvi);
}

var denganNDVI = koleksi.map(tambahNDVI);
print('Sekarang tiap citra punya band NDVI:', denganNDVI.first());

// Perhatikan: .map() untuk objek ee., bukan perulangan for. Alasannya
// ada di bagian berikutnya.


// =====================================================================
// 7 · CLIENT vs SERVER  ← INTI SELURUH HARI PERTAMA
// =====================================================================
//
// Ada DUA DUNIA di dalam satu skrip.
//
//   CLIENT — browser Anda. Semua di bagian 1-4 tadi.
//   SERVER — komputer Google. Semua yang diawali "ee."
//
// Objek ee. TIDAK BERISI NILAI di komputer Anda. Ia berisi RESEP:
// catatan tentang perhitungan yang akan dijalankan nanti, di sana.

var a = 5;                  // client: benar-benar berisi angka 5
var b = ee.Number(5);       // server: resep yang nanti menghasilkan 5

print('client:', a + 1);          // 6
print('server:', b.add(1));       // 6 — hasilnya sama, jalannya berbeda

// Perhatikan: b.add(1), bukan b + 1.
// Objek server punya metodenya sendiri: .add() .subtract()
// .multiply() .divide() .gt() .lt() .eq()


// --- Yang TIDAK BISA dilakukan --------------------------------------
//
// Hapus tanda // di bawah kalau ingin melihat sendiri apa yang terjadi.
// Skrip akan tetap "berjalan", tapi hasilnya salah — dan justru itu yang
// berbahaya: tidak ada pesan error yang jelas.
//
// if (koleksi.size() > 100) {
//   print('banyak citra');
// }
//
// Kenapa salah: koleksi.size() bukan angka. Ia janji untuk menghitung,
// nanti, di server. Sedangkan "if" berjalan SEKARANG, di browser — jadi
// ia menilai sesuatu yang nilainya belum ada.


// --- Cara yang benar, kalau memang perlu angkanya sekarang -----------
// getInfo() memaksa server menghitung dan menunggu hasilnya. Berguna,
// tapi lambat, dan jangan pernah dipakai di dalam .map().

var jumlah = koleksi.size().getInfo();     // sekarang benar-benar angka
if (jumlah > 100) {
  print('Banyak citra tersedia:', jumlah);
} else {
  print('Citra terbatas:', jumlah);
}


// =====================================================================
// ATURAN PRAKTIS
// =====================================================================
//
// Cukup ingat satu kalimat ini untuk seluruh webinar:
//
//   Kalau namanya diawali "ee.", jangan pakai if, for, atau operator
//   + - * / biasa padanya. Pakai metodenya sendiri: .add() .gt() .map()
//
// Dari sinilah hampir semua kalimat "kok hasilnya kosong" berasal.
// Dan begitu Anda memahaminya, dokumentasi Earth Engine yang tadinya
// membingungkan langsung masuk akal — seluruh API-nya disusun mengikuti
// pembagian client/server ini.
