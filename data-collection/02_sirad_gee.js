// SIRAD (Sentinel-1 RGB Anomaly Detection) for Capkala Mining Zone
// Google Earth Engine JavaScript
//
// Processes 139 Sentinel-1 GRD images into an RGB composite:
//   Red   = 2024 (55 images)
//   Green = 2025 (53 images)
//   Blue  = Mar-Jun 2026 (20 images, post-police raid)
//
// Each channel = mean VH backscatter for that period.
// Bright blue = new activity in 2026 (mining continued after arrest).
//
// To run:
//   1. Go to https://code.earthengine.google.com/
//   2. Paste this script
//   3. Click "Run"
//   4. Export to Drive or download via Tasks panel

// === Configuration ===
var CENTER = ee.Geometry.Point([109.0836, 0.6784]);  // [lon, lat]
var RADIUS_METERS = 1500;  // 1.5 km
var AOI = CENTER.buffer(RADIUS_METERS);

// Period definitions
var PERIOD_2024 = ['2024-01-01', '2024-12-31'];
var PERIOD_2025 = ['2025-01-01', '2025-12-31'];
var PERIOD_2026 = ['2026-03-01', '2026-06-30'];  // Post-arrest

// === Helper: Get mean VH for a period ===
function getMeanVH(startDate, endDate, geometry) {
  var s1 = ee.ImageCollection('COPERNICUS/S1_GRD')
    .filterBounds(geometry)
    .filterDate(startDate, endDate)
    .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VH'))
    .filter(ee.Filter.eq('instrumentMode', 'IW'))
    .filter(ee.Filter.eq('orbitProperties_pass', 'ASCENDING'))
    .select('VH')
    .map(function(img) {
      return img.clip(geometry);
    });
  
  var count = s1.size();
  print('Period ' + startDate + ' to ' + endDate + ': ' + count.getInfo() + ' images');
  
  return s1.mean().rename('VH_mean');
}

// === Compute RGB composite ===
var red   = getMeanVH(PERIOD_2024[0], PERIOD_2024[1], AOI);   // 2024 → R
var green = getMeanVH(PERIOD_2025[0], PERIOD_2025[1], AOI);   // 2025 → G
var blue  = getMeanVH(PERIOD_2026[0], PERIOD_2026[1], AOI);   // 2026 → B

// Stack into RGB
var sirad = ee.Image.cat([red, green, blue])
  .rename(['R_2024', 'G_2025', 'B_2026']);

// === Visualization ===
// Stretch each band to [-25, -5] dB (typical VH range over forest)
var visParams = {
  bands: ['R_2024', 'G_2025', 'B_2026'],
  min: -25,
  max: -5,
  gamma: 1.0
};

Map.centerObject(AOI, 14);
Map.addLayer(sirad, visParams, 'SIRAD RGB (R=2024, G=2025, B=2026)');
Map.addLayer(AOI, {color: 'white'}, 'AOI (1.5km)');

// === Export ===
Export.image.toDrive({
  image: sirad.visualize(visParams),
  description: 'SIRAD_Capkala_2024_2026',
  folder: 'GEE_Exports',
  fileNamePrefix: 'sirad_capkala',
  region: AOI,
  scale: 10,
  crs: 'EPSG:4326',
  maxPixels: 1e9
});

// === Interpretation Guide ===
print('');
print('=== SIRAD Interpretation ===');
print('White/Gray   = Activity in all periods (ongoing)');
print('Red          = Activity only in 2024 (old/stopped)');
print('Yellow       = Activity in 2024 + 2025 (no 2026)');
print('Cyan         = Activity in 2025 + 2026 (newer)');
print('Blue         = Activity ONLY in 2026 (post-arrest — KEY EVIDENCE)');
print('');
print('If blue visible → mining continued after March 2026 police raid.');
