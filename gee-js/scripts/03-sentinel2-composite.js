// =====================================================================
// 03 · CLOUD-FREE SENTINEL-2 COMPOSITE
// Day 2 · 20 menit
// =====================================================================
//
// Satu citra Sentinel-2 di Indonesia hampir selalu berawan. Solusinya
// bukan mencari hari yang cerah — sering kali tidak ada — melainkan
// menggabungkan banyak citra dan mengambil nilai tengah tiap piksel.
// Awan berpindah-pindah, jadi ia kalah suara.
// =====================================================================


// ---------------------------------------------------------------------
// 1 · AREA OF INTEREST
// ---------------------------------------------------------------------
var aoi = ee.Geometry.Point([122.21, -8.62]).buffer(15000);   // 15 km
Map.centerObject(aoi, 11);

// Alternatif: pakai batas kabupaten, tidak perlu menggambar
// var adm = ee.FeatureCollection('FAO/GAUL/2015/level2')
//             .filter(ee.Filter.eq('ADM2_NAME', 'Sikka'));
// var aoi = adm.geometry();


// ---------------------------------------------------------------------
// 2 · TIME WINDOW
// ---------------------------------------------------------------------
// Musim kemarau memberi citra paling bersih. Untuk sebagian besar
// Indonesia: Juni–September. Kalau hasilnya masih berlubang, lebarkan.

var mulai = '2024-06-01';
var akhir = '2024-09-30';


// ---------------------------------------------------------------------
// 3 · CLOUD MASK
// ---------------------------------------------------------------------
// Sentinel-2 menyertakan band SCL (Scene Classification Layer) yang
// menandai tiap piksel: awan, bayangan awan, air, vegetasi, dan
// seterusnya. Kita buang kelas yang mengganggu.

function maskS2 (image) {
  var scl = image.select('SCL');
  var buruk = scl.eq(3)        // cloud shadow
        .or(scl.eq(8))         // cloud, medium probability
        .or(scl.eq(9))         // cloud, high probability
        .or(scl.eq(10));       // cirrus

  return image.updateMask(buruk.not())
              .divide(10000)   // reflectance jadi skala 0-1
              .copyProperties(image, ['system:time_start']);
}

// Kenapa divide(10000): Sentinel-2 menyimpan reflektansi sebagai
// bilangan bulat untuk menghemat ruang. Dibagi 10.000 supaya kembali ke
// skala 0-1 — yang membuat nilai NDVI nanti masuk akal.


// ---------------------------------------------------------------------
// 4 · BUILD THE COMPOSITE
// ---------------------------------------------------------------------
var koleksi = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
  .filterBounds(aoi)
  .filterDate(mulai, akhir)
  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 60))
  .map(maskS2);

print('Jumlah citra yang digabungkan:', koleksi.size());

var komposit = koleksi.median().clip(aoi);

// median, bukan mean: nilai tengah tahan terhadap nilai ekstrem. Satu
// piksel awan yang sangat terang tidak akan menarik hasilnya, sedangkan
// rata-rata akan terpengaruh.


// ---------------------------------------------------------------------
// 5 · DISPLAY
// ---------------------------------------------------------------------
Map.addLayer(komposit, {bands: ['B4', 'B3', 'B2'], min: 0, max: 0.3},
             'True colour');

Map.addLayer(komposit, {bands: ['B8', 'B4', 'B3'], min: 0, max: 0.4},
             'False colour (vegetasi merah)', false);

// Layer kedua dimatikan dulu (false di akhir). Nyalakan lewat panel
// Layers di kanan atas peta. Pada false colour, vegetasi tampak merah
// terang — jauh lebih mudah membedakan hutan dari lahan terbuka.


// ---------------------------------------------------------------------
// 6 · CHECK BEFORE MOVING ON
// ---------------------------------------------------------------------
// Jangan lanjut ke NDVI sebelum komposit ini terlihat wajar.
//
//   Gejala                    Perbaikan
//   ------------------------  ----------------------------------------
//   banyak lubang kosong      lebarkan rentang tanggal
//   masih berawan             naikkan CLOUDY_PIXEL_PERCENTAGE ke 80
//   terlalu gelap             turunkan max ke 0.2
//   terlalu putih             naikkan max ke 0.4
//   kosong sama sekali        cek urutan koordinat: [bujur, lintang]

print('Tanggal citra pertama:',
      ee.Date(koleksi.first().get('system:time_start')).format('YYYY-MM-dd'));


// =====================================================================
// LATIHAN
// =====================================================================
// 1. Ganti AOI ke wilayah kerja Anda
// 2. Bandingkan median() dengan mean() — mana yang lebih bersih?
// 3. Coba tahun lain, lalu perhatikan apakah jumlah citranya berbeda
//    (Sentinel-2 baru lengkap dua satelit sejak 2017)
