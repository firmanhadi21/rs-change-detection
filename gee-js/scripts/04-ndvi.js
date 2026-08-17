// =====================================================================
// 04 · NDVI  —  peta kehijauan dan grafik deret waktu
// Day 2 · 20 menit
// =====================================================================
//
// NDVI membandingkan inframerah dekat (B8) dengan merah (B4). Vegetasi
// sehat memantulkan banyak inframerah dan menyerap merah, jadi nilainya
// tinggi. Air memantulkan sedikit inframerah, jadi nilainya negatif.
//
//   NDVI = (B8 - B4) / (B8 + B4)
//
// Skrip ini melanjutkan komposit dari skrip 03.
// =====================================================================


// ---------------------------------------------------------------------
// 1 · SETUP  (sama seperti skrip 03)
// ---------------------------------------------------------------------
var aoi = ee.Geometry.Point([122.21, -8.62]).buffer(15000);
Map.centerObject(aoi, 11);

function maskS2 (image) {
  var scl = image.select('SCL');
  var buruk = scl.eq(3).or(scl.eq(8)).or(scl.eq(9)).or(scl.eq(10));
  return image.updateMask(buruk.not())
              .divide(10000)
              .copyProperties(image, ['system:time_start']);
}

var komposit = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
  .filterBounds(aoi)
  .filterDate('2024-06-01', '2024-09-30')
  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 60))
  .map(maskS2)
  .median()
  .clip(aoi);


// ---------------------------------------------------------------------
// 2 · NDVI
// ---------------------------------------------------------------------
// normalizedDifference melakukan rumus (a-b)/(a+b) untuk kita.
// Urutannya penting: yang pertama dikurangi yang kedua.

var ndvi = komposit.normalizedDifference(['B8', 'B4']).rename('NDVI');

Map.addLayer(ndvi,
             {min: -0.2, max: 0.8,
              palette: ['#c8553d', '#f0e6c8', '#2d6a4f']},
             'NDVI');

// Palet: merah (rendah) → krem (sedang) → hijau tua (tinggi)


// ---------------------------------------------------------------------
// 3 · READING THE VALUES
// ---------------------------------------------------------------------
//   NDVI          biasanya
//   < 0           air
//   0   - 0.2     lahan terbuka, terbangun
//   0.2 - 0.4     vegetasi jarang, semak
//   0.4 - 0.7     pertanian, perkebunan
//   > 0.7         hutan rapat
//
// VERIFIKASI dengan Inspector sebelum lanjut:
//   klik di laut     → harus negatif
//   klik di hutan    → harus di atas 0.6
// Kalau tidak sesuai, ada yang salah pada komposit Anda. Lebih baik
// ketahuan sekarang daripada tiga langkah kemudian.


// ---------------------------------------------------------------------
// 4 · STATISTICS FOR THE REPORT
// ---------------------------------------------------------------------
var stat = ndvi.reduceRegion({
  reducer: ee.Reducer.mean().combine({
    reducer2: ee.Reducer.minMax(),
    sharedInputs: true
  }),
  geometry: aoi,
  scale: 20,
  maxPixels: 1e9
});

print('Statistik NDVI wilayah:', stat);


// ---------------------------------------------------------------------
// 5 · TIME SERIES  —  yang biasanya diminta untuk laporan
// ---------------------------------------------------------------------
// Bagaimana kehijauan berubah sepanjang tahun. Untuk pertanian, grafik
// ini memperlihatkan pola tanam; untuk kehutanan, memperlihatkan
// gangguan.

var setahun = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
  .filterBounds(aoi)
  .filterDate('2024-01-01', '2024-12-31')
  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 70))
  .map(maskS2)
  .map(function (img) {
    return img.addBands(img.normalizedDifference(['B8', 'B4']).rename('NDVI'))
              .copyProperties(img, ['system:time_start']);
  });

var grafik = ui.Chart.image.series({
  imageCollection: setahun.select('NDVI'),
  region: aoi,
  reducer: ee.Reducer.mean(),
  scale: 100          // 100 m cukup untuk grafik; 10 m akan sangat lambat
}).setOptions({
  title: 'NDVI rata-rata sepanjang 2024',
  vAxis: {title: 'NDVI'},
  hAxis: {title: 'Tanggal'},
  lineWidth: 2,
  pointSize: 4
});

print(grafik);

// Grafik muncul di Console. Klik ikon panah di pojoknya untuk membuka
// di tab baru, lalu unduh sebagai PNG (untuk laporan) atau CSV (kalau
// angkanya mau diolah di Excel).


// ---------------------------------------------------------------------
// 6 · EXPORT THE NDVI MAP
// ---------------------------------------------------------------------
Export.image.toDrive({
  image: ndvi.multiply(10000).int16(),   // int16 jauh lebih kecil dari float
  description: 'ndvi_2024',
  folder: 'GEE_webinar',
  region: aoi,
  scale: 10,
  maxPixels: 1e10,
  fileFormat: 'GeoTIFF'
});

// Ingat: ini baru MENGANTRE. Buka tab Tasks di panel kanan, klik RUN.
// Nilainya dikali 10000 supaya muat sebagai bilangan bulat; bagi lagi
// dengan 10000 setelah dibuka di QGIS.


// =====================================================================
// LATIHAN
// =====================================================================
// 1. Ganti AOI ke sawah atau kebun yang Anda kenal. Apakah grafiknya
//    memperlihatkan pola tanam yang Anda ketahui?
// 2. Coba indeks lain dengan mengganti bandnya:
//      NDWI (air)          : ['B3', 'B8']
//      NDBI (terbangun)    : ['B11', 'B8']
// 3. Bandingkan NDVI musim hujan dan musim kemarau di wilayah yang sama
