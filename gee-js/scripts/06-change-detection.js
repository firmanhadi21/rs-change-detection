// =====================================================================
// 06 · CHANGE DETECTION  —  membandingkan dua tahun
// Day 2 · 25 menit
// =====================================================================
//
// Cara paling sederhana, dan paling mudah dipertanggungjawabkan dalam
// laporan: hitung NDVI untuk dua tahun, lalu lihat selisihnya.
//
// Satu aturan yang menentukan hasilnya benar atau menyesatkan:
// GUNAKAN JENDELA MUSIM YANG SAMA untuk kedua tahun. Membandingkan
// Juni 2019 dengan Januari 2024 akan memperlihatkan pergantian musim,
// bukan perubahan tutupan lahan.
// =====================================================================


// ---------------------------------------------------------------------
// 1 · SETUP
// ---------------------------------------------------------------------
var aoi = ee.Geometry.Point([122.21, -8.62]).buffer(15000);
Map.centerObject(aoi, 11);

var tahunAwal  = '2019';
var tahunAkhir = '2024';

// Jendela musim yang sama untuk keduanya
var bulanMulai = '-06-01';
var bulanAkhir = '-09-30';

function maskS2 (image) {
  var scl = image.select('SCL');
  var buruk = scl.eq(3).or(scl.eq(8)).or(scl.eq(9)).or(scl.eq(10));
  return image.updateMask(buruk.not()).divide(10000);
}


// ---------------------------------------------------------------------
// 2 · NDVI FOR ONE YEAR  —  ditulis sekali, dipakai dua kali
// ---------------------------------------------------------------------
function ndviTahun (tahun) {
  return ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
    .filterBounds(aoi)
    .filterDate(tahun + bulanMulai, tahun + bulanAkhir)
    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 60))
    .map(maskS2)
    .median()
    .normalizedDifference(['B8', 'B4'])
    .rename('NDVI')
    .clip(aoi);
}

var ndviAwal  = ndviTahun(tahunAwal);
var ndviAkhir = ndviTahun(tahunAkhir);

var vis = {min: -0.2, max: 0.8,
           palette: ['#c8553d', '#f0e6c8', '#2d6a4f']};

Map.addLayer(ndviAwal,  vis, 'NDVI ' + tahunAwal,  false);
Map.addLayer(ndviAkhir, vis, 'NDVI ' + tahunAkhir, false);


// ---------------------------------------------------------------------
// 3 · THE DIFFERENCE
// ---------------------------------------------------------------------
var selisih = ndviAkhir.subtract(ndviAwal).rename('perubahan');

Map.addLayer(selisih,
             {min: -0.3, max: 0.3,
              palette: ['#b2182b', '#f7f7f7', '#1a9850']},
             'Perubahan NDVI');

// Merah = NDVI turun (vegetasi berkurang)
// Putih = tidak berubah
// Hijau = NDVI naik (vegetasi bertambah)


// ---------------------------------------------------------------------
// 4 · THRESHOLD  —  mana yang dianggap "berubah"
// ---------------------------------------------------------------------
// Ambang batas ini adalah keputusan Anda, dan harus disebutkan dalam
// laporan. Tidak ada angka yang benar secara universal; -0.2 adalah
// titik awal yang wajar untuk kehilangan vegetasi yang nyata.

var AMBANG = -0.2;

var berkurang = selisih.lt(AMBANG);
var bertambah = selisih.gt(-AMBANG);

Map.addLayer(berkurang.selfMask(), {palette: ['#d73027']}, 'Vegetasi berkurang');
Map.addLayer(bertambah.selfMask(), {palette: ['#1a9850']}, 'Vegetasi bertambah', false);

// selfMask() menyembunyikan piksel bernilai 0, sehingga hanya area yang
// memenuhi syarat yang tergambar.


// ---------------------------------------------------------------------
// 5 · REMOVE SPECKLE
// ---------------------------------------------------------------------
// Piksel tunggal yang berubah biasanya bukan perubahan nyata, melainkan
// sisa awan atau perbedaan sudut perekaman. Buang kelompok yang terlalu
// kecil — di sini, kurang dari 5 piksel (500 m² pada Sentinel-2).

var kelompok = berkurang.connectedPixelCount(25, false);
var bersih   = berkurang.updateMask(kelompok.gte(5));

Map.addLayer(bersih.selfMask(), {palette: ['#7b0000']},
             'Vegetasi berkurang (dibersihkan)');


// ---------------------------------------------------------------------
// 6 · AREA  —  angka untuk tabel laporan
// ---------------------------------------------------------------------
function luasHektar (mask, nama) {
  var luas = ee.Image.pixelArea().divide(1e4)
    .updateMask(mask)
    .reduceRegion({
      reducer: ee.Reducer.sum(),
      geometry: aoi,
      scale: 10,
      maxPixels: 1e10,
      tileScale: 4
    });
  print(nama, luas);
}

luasHektar(berkurang, 'Luas vegetasi berkurang, mentah (ha):');
luasHektar(bersih,    'Luas vegetasi berkurang, dibersihkan (ha):');
luasHektar(bertambah, 'Luas vegetasi bertambah (ha):');

// Bandingkan angka mentah dengan yang dibersihkan. Selisihnya
// memperlihatkan berapa banyak "perubahan" tadi sebenarnya derau.


// ---------------------------------------------------------------------
// 7 · EXPORT
// ---------------------------------------------------------------------
Export.image.toDrive({
  image: bersih.byte(),
  description: 'perubahan_' + tahunAwal + '_' + tahunAkhir,
  folder: 'GEE_webinar',
  region: aoi,
  scale: 10,
  maxPixels: 1e10,
  fileFormat: 'GeoTIFF'
});


// =====================================================================
// PERINGATAN PENTING UNTUK LAPORAN
// =====================================================================
//
// Turunnya NDVI BUKAN otomatis berarti deforestasi. Bisa juga:
//
//   - panen, kalau areanya sawah atau tebu
//   - kekeringan musiman
//   - perbedaan tanggal perekaman dalam jendela yang sama
//   - sisa awan tipis yang lolos dari mask
//
// Sebelum menyebutnya "perubahan tutupan lahan" dalam laporan:
//
//   1. periksa beberapa titik dengan citra resolusi tinggi
//      (Google Earth, atau layer Satellite di peta ini)
//   2. lihat grafik deret waktunya (skrip 04) — kehilangan permanen
//      terlihat berbeda dari pola musiman yang berulang
//   3. sebutkan ambang batas yang Anda pakai, dan alasannya
//
// Analisis yang jujur tentang ketidakpastiannya jauh lebih berguna —
// dan lebih sulit dibantah — daripada angka tunggal tanpa penjelasan.
