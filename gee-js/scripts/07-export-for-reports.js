// =====================================================================
// 07 · EXPORT FOR REPORTS AND PRESENTATIONS
// Day 2 · 25 menit
// =====================================================================
//
// Analisis yang tidak bisa dimasukkan ke laporan tidak berguna bagi
// sebagian besar peserta webinar ini. Skrip ini tentang mengeluarkan
// hasil dalam bentuk yang benar-benar bisa dipakai.
//
// SATU HAL YANG PALING SERING TERLEWAT:
//   Export TIDAK langsung mengekspor. Ia hanya MENGANTRE tugas.
//   Anda masih harus membuka tab "Tasks" di panel kanan dan klik RUN
//   pada setiap tugas. Ini keluhan nomor satu di semua webinar GEE.
// =====================================================================


// ---------------------------------------------------------------------
// 1 · SETUP
// ---------------------------------------------------------------------
var aoi = ee.Geometry.Point([122.21, -8.62]).buffer(15000);
Map.centerObject(aoi, 11);

function maskS2 (image) {
  var scl = image.select('SCL');
  var buruk = scl.eq(3).or(scl.eq(8)).or(scl.eq(9)).or(scl.eq(10));
  return image.updateMask(buruk.not()).divide(10000);
}

var komposit = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
  .filterBounds(aoi)
  .filterDate('2024-06-01', '2024-09-30')
  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 60))
  .map(maskS2).median().clip(aoi);

var ndvi = komposit.normalizedDifference(['B8', 'B4']).rename('NDVI');

// Tampilkan dulu apa yang akan diekspor. Mengekspor sesuatu yang belum
// pernah Anda lihat adalah cara tercepat menghabiskan kuota Drive untuk
// berkas yang ternyata kosong atau salah wilayah.
Map.addLayer(komposit, {bands: ['B4', 'B3', 'B2'], min: 0, max: 0.3},
             'True colour');
Map.addLayer(ndvi, {min: -0.2, max: 0.8,
                    palette: ['#c8553d', '#f0e6c8', '#2d6a4f']}, 'NDVI');

print('Wilayah ekspor (ha):',
      aoi.area().divide(1e4));


// ---------------------------------------------------------------------
// 2 · GeoTIFF  —  untuk dibuka lagi di QGIS atau ArcGIS
// ---------------------------------------------------------------------
// Punya koordinat, bisa dianalisis lebih lanjut, bisa ditumpuk dengan
// data lain. Ini yang Anda pilih kalau pekerjaannya belum selesai.

Export.image.toDrive({
  image: ndvi.multiply(10000).int16(),
  description: 'ndvi_geotiff',
  folder: 'GEE_webinar',
  region: aoi,
  scale: 10,
  crs: 'EPSG:4326',
  maxPixels: 1e10,
  fileFormat: 'GeoTIFF'
});

// int16 dan dikali 10000: berkas jadi jauh lebih kecil daripada float.
// Setelah dibuka di QGIS, bagi lagi dengan 10000.
//
// crs: 'EPSG:4326' adalah lintang-bujur. Untuk perhitungan luas yang
// teliti, pakai UTM — Indonesia terbentang dari zona 46N sampai 54S,
// misalnya 'EPSG:32751' untuk UTM 51S (Flores, Bali, NTB, NTT).


// ---------------------------------------------------------------------
// 3 · PICTURE  —  untuk ditempel ke Word atau PowerPoint
// ---------------------------------------------------------------------
// visualize() membakar palet warna ke dalam citra, jadi hasilnya sudah
// berwarna seperti yang tampak di layar.

Export.image.toDrive({
  image: ndvi.visualize({
    min: -0.2, max: 0.8,
    palette: ['#c8553d', '#f0e6c8', '#2d6a4f']
  }),
  description: 'ndvi_gambar',
  folder: 'GEE_webinar',
  region: aoi,
  scale: 20,           // 20 m sudah cukup untuk gambar di laporan
  maxPixels: 1e10,
  fileFormat: 'GeoTIFF'
});


// ---------------------------------------------------------------------
// 4 · NUMBERS  —  untuk tabel
// ---------------------------------------------------------------------
// Statistik per wilayah, diekspor sebagai CSV yang bisa dibuka di Excel.

var statistik = ee.FeatureCollection([
  ee.Feature(null, ndvi.reduceRegion({
    reducer: ee.Reducer.mean()
      .combine({reducer2: ee.Reducer.stdDev(), sharedInputs: true})
      .combine({reducer2: ee.Reducer.minMax(), sharedInputs: true}),
    geometry: aoi,
    scale: 20,
    maxPixels: 1e9
  }))
]);

Export.table.toDrive({
  collection: statistik,
  description: 'statistik_ndvi',
  folder: 'GEE_webinar',
  fileFormat: 'CSV'
});


// ---------------------------------------------------------------------
// 5 · LEGEND  —  supaya peta bisa langsung dipresentasikan
// ---------------------------------------------------------------------
// Legenda ini tampil di peta Code Editor, bukan di berkas ekspor. Berguna
// saat Anda membagikan layar atau mengambil tangkapan layar.

var legenda = ui.Panel({
  style: {position: 'bottom-left', padding: '10px 14px',
          backgroundColor: 'rgba(255,255,255,0.9)'}
});

legenda.add(ui.Label('NDVI 2024', {
  fontWeight: 'bold', fontSize: '16px', margin: '0 0 8px 0'
}));

var kelasNDVI = [
  {warna: 'c8553d', label: '< 0.2 · terbuka / terbangun'},
  {warna: 'f0e6c8', label: '0.2 – 0.4 · vegetasi jarang'},
  {warna: '96b96a', label: '0.4 – 0.7 · pertanian, kebun'},
  {warna: '2d6a4f', label: '> 0.7 · hutan rapat'}
];

kelasNDVI.forEach(function (k) {
  legenda.add(ui.Panel({
    widgets: [
      ui.Label('', {backgroundColor: '#' + k.warna, padding: '9px',
                    margin: '0 6px 4px 0', border: '1px solid #999'}),
      ui.Label(k.label, {margin: '0 0 4px 0', fontSize: '13px'})
    ],
    layout: ui.Panel.Layout.Flow('horizontal')
  }));
});

Map.add(legenda);


// ---------------------------------------------------------------------
// 6 · SPLIT-SCREEN COMPARISON  —  sangat efektif untuk presentasi
// ---------------------------------------------------------------------
// Dua peta bersebelahan, gerakannya tersinkron. Cara paling meyakinkan
// untuk memperlihatkan perubahan kepada orang yang bukan ahli.
//
// Hapus tanda // di bawah untuk mencobanya. Perhatikan bahwa ini
// mengganti seluruh tampilan Code Editor.
//
// var kiri  = ui.Map();
// var kanan = ui.Map();
// var tautan = ui.Map.Linker([kiri, kanan]);
//
// kiri.addLayer(komposit, {bands:['B4','B3','B2'], min:0, max:0.3}, '2024');
// kanan.addLayer(ndvi, {min:-0.2, max:0.8,
//                       palette:['#c8553d','#f0e6c8','#2d6a4f']}, 'NDVI');
//
// var panel = ui.SplitPanel({firstPanel: kiri, secondPanel: kanan,
//                            orientation: 'horizontal', wipe: true});
// ui.root.clear();
// ui.root.add(panel);
// kiri.centerObject(aoi, 11);


// =====================================================================
// MEMILIH FORMAT
// =====================================================================
//
//   Keperluan                    Format
//   ---------------------------  -------------------------------------
//   dibuka lagi di QGIS/ArcGIS   GeoTIFF biasa
//   gambar untuk laporan Word    GeoTIFF hasil .visualize()
//   angka untuk tabel            CSV lewat Export.table
//   grafik                       PNG dari Console (klik ikon panah)
//   berbagi dengan rekan         Earth Engine asset atau tautan skrip
//
// Untuk peta yang benar-benar siap cetak — dengan skala, arah utara,
// grid koordinat dan kotak judul — ekspor GeoTIFF-nya, lalu susun tata
// letaknya di QGIS. Earth Engine unggul untuk analisis; QGIS lebih baik
// untuk kartografi. Memakai keduanya sesuai kekuatannya masing-masing
// jauh lebih cepat daripada memaksa salah satunya melakukan semuanya.
