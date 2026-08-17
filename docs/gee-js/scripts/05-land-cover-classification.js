// =====================================================================
// 05 · LAND COVER CLASSIFICATION with Sentinel-2
// Google Earth Engine — JavaScript Code Editor
// =====================================================================
//
// Membuat peta tutupan lahan dari citra Sentinel-2, lengkap dengan angka
// akurasi. Ini bagian yang paling sering diminta peserta, dan juga yang
// paling mudah salah dipakai: sebuah peta klasifikasi SELALU jadi, bahkan
// ketika contoh latihnya buruk. Karena itu bagian akurasi di bawah bukan
// pelengkap — itu satu-satunya cara tahu peta Anda layak dipakai atau tidak.
//
// Cara pakai:
//   1. Ubah AOI di bagian 1 ke wilayah Anda
//   2. Jalankan sampai bagian 3, lihat komposit
//   3. Gambar titik latih Anda sendiri (bagian 4)
//   4. Jalankan sisanya
// =====================================================================


// ---------------------------------------------------------------------
// 1 · AREA OF INTEREST
// ---------------------------------------------------------------------
// Ganti dengan wilayah Anda. Tiga cara, pilih salah satu:
//
//   a. Gambar poligon dengan tool di peta (jadi variabel `geometry`)
//   b. Titik + buffer, seperti di bawah
//   c. Ambil dari batas administrasi (lihat komentar paling bawah)

var aoi = ee.Geometry.Point([121.35, -8.65]).buffer(15000);  // Flores, 15 km
Map.centerObject(aoi, 11);


// ---------------------------------------------------------------------
// 2 · TIME WINDOW
// ---------------------------------------------------------------------
// Di Indonesia, musim kemarau memberi citra paling bersih. Untuk sebagian
// besar wilayah: Juni–September. Kalau hasilnya masih banyak awan, lebarkan
// rentangnya — median composite akan tetap membuang awan.

var tahun  = 2024;
var mulai  = ee.Date.fromYMD(tahun, 6, 1);
var akhir  = ee.Date.fromYMD(tahun, 9, 30);


// ---------------------------------------------------------------------
// 3 · CLOUD-FREE COMPOSITE
// ---------------------------------------------------------------------
// Scene Classification Layer (SCL) menandai tiap piksel: awan, bayangan,
// air, vegetasi, dan seterusnya. Kita buang kelas yang tidak berguna.

function maskS2 (image) {
  var scl = image.select('SCL');
  // 3 = cloud shadow, 8 = cloud medium, 9 = cloud high, 10 = cirrus
  var buruk = scl.eq(3).or(scl.eq(8)).or(scl.eq(9)).or(scl.eq(10));
  return image.updateMask(buruk.not())
              .divide(10000)            // reflectance 0–1
              .copyProperties(image, ['system:time_start']);
}

var s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
           .filterBounds(aoi)
           .filterDate(mulai, akhir)
           .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 60))
           .map(maskS2);

print('Jumlah citra yang dipakai:', s2.size());

var komposit = s2.median().clip(aoi);

// Band yang dipakai untuk klasifikasi. Menambah indeks hampir selalu
// menaikkan akurasi, karena vegetasi dan air jadi lebih mudah dibedakan.
var ndvi = komposit.normalizedDifference(['B8', 'B4']).rename('NDVI');
var ndwi = komposit.normalizedDifference(['B3', 'B8']).rename('NDWI');
var ndbi = komposit.normalizedDifference(['B11', 'B8']).rename('NDBI');

var citra = komposit.select(['B2', 'B3', 'B4', 'B8', 'B11', 'B12'])
                    .addBands([ndvi, ndwi, ndbi]);

Map.addLayer(komposit, {bands: ['B4', 'B3', 'B2'], min: 0, max: 0.3},
             'True colour');
Map.addLayer(komposit, {bands: ['B8', 'B4', 'B3'], min: 0, max: 0.4},
             'False colour (vegetasi merah)', false);


// ---------------------------------------------------------------------
// 4 · TRAINING POINTS  ← BAGIAN YANG ANDA KERJAKAN SENDIRI
// ---------------------------------------------------------------------
// Ini satu-satunya bagian yang tidak bisa disalin: komputer tidak tahu
// seperti apa "sawah" di wilayah Anda. Anda yang memberi tahu.
//
// Di panel Geometry Imports (kiri atas peta):
//   1. klik "+ new layer"
//   2. ganti namanya jadi salah satu nama kelas di bawah
//   3. klik ikon gear → Import as: FeatureCollection
//      → tambahkan property bernama "kelas" dengan nilai angka
//   4. gambar 20–40 titik di area yang JELAS kelas itu
//   5. ulangi untuk tiap kelas
//
// Angka kelas harus mulai dari 0 dan berurutan.

var KELAS = [
  {nama: 'air',        nilai: 0, warna: '1f4e79'},
  {nama: 'hutan',      nilai: 1, warna: '1a7d3a'},
  {nama: 'pertanian',  nilai: 2, warna: '9acd32'},
  {nama: 'terbangun',  nilai: 3, warna: 'c0392b'},
  {nama: 'lahanTerbuka', nilai: 4, warna: 'd9b38c'}
];

// Setelah menggambar, gabungkan di sini. Hapus tanda // dan sesuaikan nama
// variabelnya dengan nama layer yang Anda buat.
//
// var titikLatih = air.merge(hutan).merge(pertanian)
//                     .merge(terbangun).merge(lahanTerbuka);

// --- Untuk latihan saat webinar: titik contoh otomatis ----------------
// Ini HANYA supaya skrip bisa jalan sebelum Anda menggambar sendiri.
// Hasilnya tidak bisa dipakai untuk laporan. Ganti dengan titik Anda.
var titikLatih = ee.FeatureCollection([
  ee.Feature(ee.Geometry.Point([121.28, -8.72]), {kelas: 1}),
  ee.Feature(ee.Geometry.Point([121.31, -8.70]), {kelas: 1}),
  ee.Feature(ee.Geometry.Point([121.40, -8.68]), {kelas: 2}),
  ee.Feature(ee.Geometry.Point([121.42, -8.66]), {kelas: 2}),
  ee.Feature(ee.Geometry.Point([121.36, -8.60]), {kelas: 0}),
  ee.Feature(ee.Geometry.Point([121.33, -8.62]), {kelas: 3}),
  ee.Feature(ee.Geometry.Point([121.45, -8.74]), {kelas: 4})
]);
print('PERINGATAN: memakai titik contoh. Ganti dengan titik Anda sendiri.');


// ---------------------------------------------------------------------
// 5 · SAMPLE THE IMAGE AT THE TRAINING POINTS
// ---------------------------------------------------------------------
// Mengambil nilai tiap band di lokasi tiap titik. Inilah "contoh" yang
// dipelajari model: kombinasi nilai band → nama kelas.

var contoh = citra.sampleRegions({
  collection: titikLatih,
  properties: ['kelas'],
  scale: 10,              // Sentinel-2: 10 m
  tileScale: 2,           // naikkan ke 4 atau 8 kalau muncul error memori
  geometries: false
});

print('Jumlah contoh terkumpul:', contoh.size());


// ---------------------------------------------------------------------
// 6 · SPLIT: TRAIN vs TEST
// ---------------------------------------------------------------------
// Bagian yang paling sering dilewati, dan paling penting.
//
// Kalau model diuji dengan data yang sama seperti data latihnya, akurasinya
// hampir selalu terlihat bagus — persis seperti murid yang sudah diberi
// bocoran soal. Angka itu tidak berarti apa-apa. Karena itu 30% titik
// disisihkan dan tidak pernah dilihat model sampai saat pengujian.

var berlabelAcak = contoh.randomColumn('acak', 42);   // 42 = seed, agar hasil sama tiap run
var dataLatih = berlabelAcak.filter(ee.Filter.lt('acak', 0.7));
var dataUji   = berlabelAcak.filter(ee.Filter.gte('acak', 0.7));

print('Titik untuk melatih:', dataLatih.size());
print('Titik untuk menguji:', dataUji.size());


// ---------------------------------------------------------------------
// 7 · TRAIN THE CLASSIFIER
// ---------------------------------------------------------------------
// Random Forest: banyak pohon keputusan, hasilnya divoting. Pilihan yang
// baik untuk pemula karena jarang perlu disetel dan tahan terhadap band
// yang saling berkorelasi.

var classifier = ee.Classifier.smileRandomForest({numberOfTrees: 100})
  .train({
    features: dataLatih,
    classProperty: 'kelas',
    inputProperties: citra.bandNames()
  });

var hasil = citra.classify(classifier);


// ---------------------------------------------------------------------
// 8 · ACCURACY — JANGAN LEWATI BAGIAN INI
// ---------------------------------------------------------------------
// Peta di bawah akan tampil bagus apa pun yang terjadi. Angka-angka inilah
// yang menentukan boleh atau tidaknya peta itu masuk laporan.

var ujian = dataUji.classify(classifier);
var matriks = ujian.errorMatrix('kelas', 'classification');

print('--- AKURASI ---');
print('Confusion matrix:', matriks);
print('Overall accuracy:', matriks.accuracy());
print('Kappa:', matriks.kappa());
print("Producer's accuracy (per kelas):", matriks.producersAccuracy());
print("Consumer's accuracy (per kelas):", matriks.consumersAccuracy());

// Pegangan kasar untuk membaca overall accuracy:
//   > 0.85  bagus, layak dipakai untuk laporan
//   0.70–0.85  cukup; sebutkan angkanya, dan hati-hati pada kelas yang lemah
//   < 0.70  jangan dipakai; tambah titik latih pada kelas yang tertukar
//
// Kalau angkanya rendah, lihat confusion matrix: baris yang nilainya
// tersebar menunjukkan kelas mana yang tertukar dengan apa. Biasanya
// "pertanian" tertukar dengan "lahan terbuka" saat lahan sedang bera.


// ---------------------------------------------------------------------
// 9 · DISPLAY
// ---------------------------------------------------------------------
var palet = KELAS.map(function (k) { return k.warna; });

Map.addLayer(hasil, {min: 0, max: KELAS.length - 1, palette: palet},
             'Land cover');

// Legenda sederhana, supaya peta bisa langsung dipakai untuk presentasi.
var legenda = ui.Panel({style: {position: 'bottom-left', padding: '8px 12px'}});
legenda.add(ui.Label('Tutupan Lahan ' + tahun,
                     {fontWeight: 'bold', fontSize: '15px', margin: '0 0 6px 0'}));

KELAS.forEach(function (k) {
  legenda.add(ui.Panel({
    widgets: [
      ui.Label('', {backgroundColor: '#' + k.warna, padding: '9px',
                    margin: '0 6px 4px 0', border: '1px solid #999'}),
      ui.Label(k.nama, {margin: '0 0 4px 0', fontSize: '13px'})
    ],
    layout: ui.Panel.Layout.Flow('horizontal')
  }));
});
Map.add(legenda);


// ---------------------------------------------------------------------
// 10 · AREA PER CLASS — angka untuk tabel laporan
// ---------------------------------------------------------------------
var luas = ee.Image.pixelArea().divide(1e4)      // m² → hektar
  .addBands(hasil)
  .reduceRegion({
    reducer: ee.Reducer.sum().group({groupField: 1, groupName: 'kelas'}),
    geometry: aoi,
    scale: 10,
    maxPixels: 1e10,
    tileScale: 4
  });

print('Luas per kelas (hektar):', luas);


// ---------------------------------------------------------------------
// 11 · EXPORT
// ---------------------------------------------------------------------
// Jalankan, lalu buka tab "Tasks" di panel kanan dan klik RUN.
// Hasilnya masuk ke Google Drive Anda, bukan ke komputer langsung.

Export.image.toDrive({
  image: hasil.byte(),                 // byte: ukuran berkas jauh lebih kecil
  description: 'tutupan_lahan_' + tahun,
  folder: 'GEE_webinar',
  region: aoi,
  scale: 10,
  maxPixels: 1e10,
  fileFormat: 'GeoTIFF'
});

// Untuk dimasukkan ke laporan sebagai gambar, PNG lebih praktis:
// Export.image.toDrive({
//   image: hasil.visualize({min: 0, max: KELAS.length - 1, palette: palet}),
//   description: 'tutupan_lahan_png_' + tahun,
//   folder: 'GEE_webinar', region: aoi, scale: 20, fileFormat: 'GeoTIFF'
// });


// =====================================================================
// CATATAN
// =====================================================================
//
// Batas administrasi, kalau Anda tidak ingin menggambar AOI sendiri:
//
//   var adm = ee.FeatureCollection('FAO/GAUL/2015/level2')
//               .filter(ee.Filter.eq('ADM1_NAME', 'Nusa Tenggara Timur'))
//               .filter(ee.Filter.eq('ADM2_NAME', 'Sikka'));
//   var aoi = adm.geometry();
//
// Kalau muncul "User memory limit exceeded":
//   - naikkan tileScale (2 → 4 → 8)
//   - perkecil AOI
//   - naikkan scale dari 10 ke 20 saat masih bereksperimen
//
// Kalau akurasi rendah:
//   - tambah titik latih, terutama pada kelas yang saling tertukar
//   - pastikan titik berada di tengah tutupan, bukan di batas antar kelas
//   - pertimbangkan menggabungkan dua kelas yang memang mirip secara spektral
