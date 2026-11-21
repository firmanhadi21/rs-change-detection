/**
 * "Api, Gambut, dan Sawit: Apa yang Membuat Kalimantan Terbakar?" / "Fire, Peat and Palm: What Makes
 * Kalimantan Burn?" A standalone film, plus two infographic pages, from the 500 m MODIS-grid panel.
 *
 *   carbon     fire emissions 2001-2025, central 2.63 Gt CO2e (1.53-3.74); peat 9% of land, 86% of emissions
 *   drivers    factor-group ranking, 50 km spatial-block CV: drought > forest condition > access > palm > peat
 *   palm       fire peaks 1-2 yr before planting, almost gone 3 yr after (stacked event study)
 *   swidden    VIIRS 2012-2025: swidden-like mosaic fires stay small; peat fires escape
 *   test       2026 (Jun-Sep rain ~half normal): dry-scenario map vs MCD64A1 Jan-Sep 2026
 *   2027       normal vs El Nino scenario: burned area, CO2e, priced at 5 / 51 / 185 USD per t
 *
 * Same palette, type and audio pipeline as Hutan.tsx. Every figure is from apiData.json
 * (scripts/api_film_assets.py). No company is named.
 */

import React, { createContext, useContext } from "react";
import { AbsoluteFill, Audio, Img, interpolate, Sequence, staticFile, useCurrentFrame } from "remotion";
import { JADWAL_API } from "./jadwalApi";
import type { Bahasa } from "./jadwalKonsesi";
import { Bingkai, Judul, Keterangan, Kolom, LatarDiam, Lembut, masuk } from "./komponen";
import { angkaGaya, judulFont, koma as komaL, ribuan as ribuanL, tubuhFont, warna } from "./teema";
import D from "./apiData.json";

const ABU_GELAP = "#3A424D";
const PETA_WARNA = ["#1B2029", "#3A424D", "#9A6530", warna.bara, warna.nyala];

const TEKS_ID = {
  lokal: "id-ID",
  audio: "audio/api",
  musik: "musik-api.mp3",
  labelSumber: "Sumber",
  kiri: "Karhutla Kalimantan",
  waktu: "November 2026",
  alisJudul: "Analisis citra satelit 2001–2026",
  judul: ["APA YANG", "MEMBUAT KALIMANTAN", "TERBAKAR?"],
  judulPendek: "Api, Gambut, dan Sawit",
  subJudul: "Dua puluh lima tahun kebakaran di grid 500 meter: berapa karbonnya, apa pemicunya, dan di mana risikonya pada 2027.",
  satuanGt: "miliar ton CO₂e",
  satuanMt: "juta ton CO₂e",
  alisBuka: "Emisi kebakaran, 2001–2025",
  rentang: (a: string, b: string) => `rentang ${a}–${b} miliar ton, karena kedalaman gambut terbakar tidak pasti`,
  terburuk: "terburuk",
  sumberBuka: "Area terbakar MODIS MCD64A1 (500 m) · emisi gambut IPCC 2013 Wetlands Supplement Tabel 2.6–2.7 · biomassa ESA CCI v6 × IPCC 2006 Tabel 2.5–2.6",
  judulGambut: "Gambut: sedikit lahan, sebagian besar emisi",
  luasDarat: "Luas daratan",
  emisi: "Emisi kebakaran 2001–2025",
  gambut: "gambut",
  mineral: "tanah mineral",
  kali: (n: string, a: string, b: string) => `Per km², gambut terbakar melepas ± ${n}× lebih banyak: ${a} vs ${b} t CO₂e per tahun`,
  sumberGambut: "Sebaran gambut BBSDLP (via GFW) · emisi seperti di atas, nilai tengah",
  judulFaktor: "Apa yang paling menentukan di mana api muncul?",
  faktor: {
    "drought (Jun-Oct rain)": "Kekeringan (hujan Jun–Okt)",
    "forest condition": "Kondisi hutan (utuh / rusak / terbuka)",
    "access & terrain": "Akses dan medan (jalan, sungai, ketinggian)",
    "oil palm & concessions": "Sawit dan konsesi",
    peat: "Gambut",
    "fire history": "Riwayat kebakaran",
    "forest-area status (APL etc.)": "Status kawasan (APL, HP, HL …)",
    "recent clearing": "Pembukaan baru",
    settlement: "Permukiman",
  } as Record<string, string>,
  ukuranFaktor: "Seberapa turun ketepatan model jika faktor itu diacak",
  catatanFaktor: (auc: string, km: number) => `Model gradient boosting, dilatih 2002–2025, diuji di petak ${km} km yang tidak dilihatnya (ROC-AUC ${auc}).`,
  sumberFaktor: "MCD64A1 · CHIRPS · JRC TMF · peta sawit Descals dkk. · KLHK kawasan hutan (via GFW) · GRIP4 · SRTM",
  judulSawit: "Api di lahan yang ditanami sawit, sebelum dan sesudah tanam",
  sumbuSawit: "tahun terhadap tahun tanam",
  rasio: "kebakaran dibanding lahan pembanding (1 = sama)",
  sebelum: "dibuka",
  sesudah: "sudah ditanam",
  catatanSawit: (km: string, y: number) => `Kebun sawit industri sendiri jarang terbakar: paling banyak ${km} km² dalam setahun (${y}).`,
  sumberSawit: "Studi peristiwa bertumpuk, tahun kering; tahun tanam: peta sawit Descals dkk. (2000–2021); area terbakar MCD64A1",
  judulLadang: "Ladang vs gambut: seberapa sering api menjadi besar?",
  kolomLadang: "Bentang ladang dan kebun campuran (tanah mineral)",
  kolomGambut: "Gambut di luar izin",
  barisLadang: ["Kejadian api yang menjadi besar", "Titik api pada tahun kering vs tahun basah", "Bagian titik api di kejadian besar"],
  sumberLadang: "VIIRS 375 m (FIRMS) 2012–2025, kejadian = titik dalam 0,75 km dan 2 hari; besar = menyentuh ≥ 10 sel MODIS",
  judulUji: "Ujian 2026: hujan Juni–September hanya ± separuh normal",
  tertangkap: "bagian area terbakar 2026 yang ada di …",
  atas5: "5% wilayah paling berisiko",
  atas10: "10% wilayah paling berisiko",
  model: "Model (skenario kering)",
  gambutSaja: "Gambut saja",
  gambutRiwayat: "Gambut + kebakaran 3 tahun terakhir",
  catatanUji: "Model hanya belajar sampai 2025. Area terbakar 2026: MCD64A1 Januari–September.",
  sumberUji: "Hujan CHIRPS Jun–Sep 2026 dibanding 2001–2025 · area terbakar MCD64A1",
  alisRamal: "Ramalan 2027",
  normal: "Tahun normal",
  elNino: "Tahun El Niño",
  terbakar: "km² terbakar",
  harga: "Kerugian karbon, US$5 / 51 / 185 per ton",
  miliar: "miliar US$",
  dimana: "5% wilayah paling berisiko (skenario El Niño):",
  dimanaBaris: (apl: string, hp: string, g: string, o: string, n: string) => [
    `${apl}% di APL, ${hp}% di hutan produksi`,
    `${g}% di gambut · ${o}% lahan terbuka atau terdegradasi`,
    `${n}% tidak terbakar pada 2024–2026`,
  ],
  legendaRendah: "rendah",
  legendaTinggi: "tinggi",
  legendaJudul: "Peluang terbakar 2027, skenario El Niño",
  sumberRamal: "Model sebagai di atas, dilatih 2002–2026 · harga karbon: Strand dkk. 2018 (US$5), pemerintah AS 2021 (US$51), Rennert dkk. 2022 (US$185)",
  tutup1: "Apa yang membuat Kalimantan terbakar?",
  tutup2: "Kemarau menyalakan api. Lahan yang rusak dan terbuka, terutama gambut, yang membuatnya menyebar.",
  tutup3: "Peta risiko bisa disiapkan jauh sebelum musim kering.",
  tutupCatat:
    "Angka satelit, kemungkinan di bawah kenyataan: MODIS melewatkan api kecil dan api gambut yang membara. Kedalaman gambut terbakar adalah ketidakpastian terbesar. Wilayah adat belum masuk analisis. Belum ditelaah sejawat.",
  sumberData: "Sumber data",
  barisSumber: [
    ["Area terbakar", "MODIS MCD64A1 v6.1 (NASA), 500 m, 2001–2026"],
    ["Titik api", "VIIRS 375 m, NASA FIRMS, 2012–2026"],
    ["Hutan", "JRC Tropical Moist Forest 1990–2024; biomassa ESA CCI Biomass v6"],
    ["Sawit", "Descals dkk., peta sawit global 2000–2021"],
    ["Hujan", "CHIRPS (UCSB-CHG), Juni–Oktober"],
    ["Kawasan", "KLHK kawasan hutan (via Global Forest Watch); gambut BBSDLP; konsesi GFW"],
    ["Emisi", "IPCC 2006 Vol. 4 Bab 2; IPCC 2013 Wetlands Supplement Bab 2"],
    ["Harga karbon", "Strand dkk. 2018 (Nature Sustainability); Rennert dkk. 2022 (Nature)"],
  ],
  peringatan: "Pemicu adalah hasil model statistik, bukan bukti pelaku. Angka satelit dapat berbeda dari data resmi. Tidak ada perusahaan yang disebut.",
  judulHal2: "Di mana Kalimantan paling mungkin terbakar pada 2027?",
  artinya: "Apa artinya",
  artinyaBaris: [
    "Kekeringan tidak bisa dicegah; kondisi lahan bisa. Pulihkan dan basahi gambut yang rusak.",
    "Awasi pembukaan lahan: api memuncak 1–2 tahun sebelum sawit ditanam.",
    "Ladang berpindah bukan sumber utama api besar; api gambutlah yang lepas kendali.",
  ],
  catatan: "Catatan",
};

type Teks = typeof TEKS_ID;

const TEKS_EN: Teks = {
  ...TEKS_ID,
  lokal: "en-GB",
  audio: "audio/api-en",
  musik: "musik-api-en.mp3",
  labelSumber: "Source",
  kiri: "Kalimantan fires",
  alisJudul: "A satellite analysis, 2001–2026",
  judul: ["WHAT MAKES", "KALIMANTAN", "BURN?"],
  judulPendek: "Fire, Peat and Palm",
  subJudul: "Twenty-five years of fire on a 500 m grid: how much carbon, what drives it, and where the risk lies in 2027.",
  satuanGt: "billion tonnes CO₂e",
  satuanMt: "million tonnes CO₂e",
  alisBuka: "Fire emissions, 2001–2025",
  rentang: (a: string, b: string) => `range ${a}–${b} billion tonnes, because the depth of burned peat is uncertain`,
  terburuk: "worst",
  sumberBuka: "Burned area MODIS MCD64A1 (500 m) · peat emissions IPCC 2013 Wetlands Supplement Tables 2.6–2.7 · biomass ESA CCI v6 × IPCC 2006 Tables 2.5–2.6",
  judulGambut: "Peat: little land, most of the emissions",
  luasDarat: "Land area",
  emisi: "Fire emissions 2001–2025",
  gambut: "peat",
  mineral: "mineral soil",
  kali: (n: string, a: string, b: string) => `Per km², burning peat releases about ${n}× more: ${a} vs ${b} t CO₂e a year`,
  sumberGambut: "Peat extent BBSDLP (via GFW) · emissions as above, central value",
  judulFaktor: "What decides where fire breaks out?",
  faktor: {
    "drought (Jun-Oct rain)": "Drought (Jun–Oct rain)",
    "forest condition": "Forest condition (intact / damaged / open)",
    "access & terrain": "Access and terrain (roads, rivers, elevation)",
    "oil palm & concessions": "Oil palm and concessions",
    peat: "Peat",
    "fire history": "Fire history",
    "forest-area status (APL etc.)": "Forest-area status (APL, HP, HL …)",
    "recent clearing": "Recent clearing",
    settlement: "Settlement",
  },
  ukuranFaktor: "How much the model's accuracy drops when the factor is shuffled",
  catatanFaktor: (auc: string, km: number) => `Gradient-boosting model, trained on 2002–2025, tested on ${km} km blocks it never saw (ROC-AUC ${auc}).`,
  sumberFaktor: "MCD64A1 · CHIRPS · JRC TMF · oil palm map, Descals et al. · KLHK forest areas (via GFW) · GRIP4 · SRTM",
  judulSawit: "Fire on land planted with oil palm, before and after planting",
  sumbuSawit: "years relative to planting",
  rasio: "fire compared with similar land (1 = the same)",
  sebelum: "cleared",
  sesudah: "planted",
  catatanSawit: (km: string, y: number) => `Industrial plantations themselves rarely burn: at most ${km} km² in a year (${y}).`,
  sumberSawit: "Stacked event study, dry years; planting year: oil palm map, Descals et al. (2000–2021); burned area MCD64A1",
  judulLadang: "Swidden vs peat: how often does fire grow large?",
  kolomLadang: "Mosaic of fields and mixed gardens (mineral soil)",
  kolomGambut: "Peat outside permits",
  barisLadang: ["Fire events that become large", "Detections in dry vs wet years", "Share of detections in large events"],
  sumberLadang: "VIIRS 375 m (FIRMS) 2012–2025, event = detections within 0.75 km and 2 days; large = touches ≥ 10 MODIS cells",
  judulUji: "The 2026 test: June–September rain about half of normal",
  tertangkap: "share of 2026 burned area that fell in …",
  atas5: "the 5% of land ranked most at risk",
  atas10: "the 10% of land ranked most at risk",
  model: "Model (dry scenario)",
  gambutSaja: "Peat alone",
  gambutRiwayat: "Peat + fire in the last 3 years",
  catatanUji: "The model learned only up to 2025. 2026 burned area: MCD64A1, January–September.",
  sumberUji: "CHIRPS rain Jun–Sep 2026 against 2001–2025 · burned area MCD64A1",
  alisRamal: "The 2027 forecast",
  normal: "Normal year",
  elNino: "El Niño year",
  terbakar: "km² burned",
  harga: "Carbon loss at US$5 / 51 / 185 per tonne",
  miliar: "US$ billion",
  dimana: "The 5% of land most at risk (El Niño scenario):",
  dimanaBaris: (apl: string, hp: string, g: string, o: string, n: string) => [
    `${apl}% in APL, ${hp}% in production forest`,
    `${g}% on peat · ${o}% open or degraded land`,
    `${n}% did not burn in 2024–2026`,
  ],
  legendaRendah: "low",
  legendaTinggi: "high",
  legendaJudul: "Chance of burning in 2027, El Niño scenario",
  sumberRamal: "Model as above, trained on 2002–2026 · carbon prices: Strand et al. 2018 (US$5), US government 2021 (US$51), Rennert et al. 2022 (US$185)",
  tutup1: "What makes Kalimantan burn?",
  tutup2: "Drought lights the fire. Damaged and open land, above all peat, lets it spread.",
  tutup3: "Risk maps can be ready long before the dry season.",
  tutupCatat:
    "Satellite figures, probably below the real toll: MODIS misses small fires and smouldering peat. The depth of burned peat is the largest uncertainty. Customary (adat) territories are not yet included. Not yet peer reviewed.",
  sumberData: "Data sources",
  barisSumber: [
    ["Burned area", "MODIS MCD64A1 v6.1 (NASA), 500 m, 2001–2026"],
    ["Fire detections", "VIIRS 375 m, NASA FIRMS, 2012–2026"],
    ["Forest", "JRC Tropical Moist Forest 1990–2024; biomass ESA CCI Biomass v6"],
    ["Oil palm", "Descals et al., global oil palm map 2000–2021"],
    ["Rain", "CHIRPS (UCSB-CHG), June–October"],
    ["Land status", "KLHK forest areas (via Global Forest Watch); peat BBSDLP; concessions GFW"],
    ["Emissions", "IPCC 2006 Vol. 4 Ch. 2; IPCC 2013 Wetlands Supplement Ch. 2"],
    ["Carbon price", "Strand et al. 2018 (Nature Sustainability); Rennert et al. 2022 (Nature)"],
  ],
  peringatan: "Drivers are statistical model results, not proof of who lit a fire. Satellite figures may differ from official statistics. No company is named.",
  judulHal2: "Where is Kalimantan most likely to burn in 2027?",
  artinya: "What it means",
  artinyaBaris: [
    "Drought cannot be prevented; land condition can. Restore and rewet damaged peat.",
    "Watch land clearing: fire peaks 1–2 years before oil palm is planted.",
    "Shifting cultivation is not the main source of large fires; peat fires are what escape.",
  ],
  catatan: "Notes",
};

const Ctx = createContext<Bahasa>("id");
const useT = () => {
  const T = useContext(Ctx) === "en" ? TEKS_EN : TEKS_ID;
  return { T, koma: (n: number, d = 1) => komaL(n, d, T.lokal), ribuan: (n: number) => ribuanL(n, T.lokal) };
};

/* ------------------------------ furniture ----------------------------- */

const Bkg: React.FC<{ sumber?: string; tampil?: number }> = ({ sumber, tampil }) => {
  const { T } = useT();
  return <Bingkai kiri={T.kiri} waktu={T.waktu} labelSumber={T.labelSumber} sumber={sumber} tampil={tampil} />;
};

const Alis: React.FC<{ anak: string }> = ({ anak }) => (
  <div style={{ fontFamily: tubuhFont, fontSize: 21, fontWeight: 600, letterSpacing: "0.22em", textTransform: "uppercase", color: warna.bara }}>{anak}</div>
);

const Angka: React.FC<{ anak: string; ukuran?: number; warnaA?: string }> = ({ anak, ukuran = 150, warnaA = warna.nyala }) => (
  <div style={{ ...angkaGaya, fontSize: ukuran, fontWeight: 600, color: warnaA, lineHeight: 1 }}>{anak}</div>
);

const Garis: React.FC<{ anak: string; tampil: number; lebar?: number; ukuran?: number }> = ({ anak, tampil, lebar = 620, ukuran = 26 }) => (
  <div style={{ borderLeft: `3px solid ${warna.bara}`, paddingLeft: 18, fontFamily: tubuhFont, fontSize: ukuran, color: warna.kapur, lineHeight: 1.35, maxWidth: lebar, opacity: tampil }}>
    {anak}
  </div>
);

const Peta: React.FC<{ panjang: number; zoom?: number; redup?: number }> = ({ panjang, zoom = 1.04, redup = 0 }) => {
  const f = useCurrentFrame();
  const s = interpolate(f, [0, panjang], [1, zoom], { extrapolateRight: "clamp" });
  return (
    <AbsoluteFill style={{ backgroundColor: warna.jelaga, overflow: "hidden" }}>
      <Img src={staticFile("api/peta_risiko.jpg")} style={{ width: "100%", height: "100%", transform: `scale(${s})`, transformOrigin: "70% 70%", opacity: 1 - redup }} />
    </AbsoluteFill>
  );
};

const Legenda: React.FC<{ lebar?: number; ukuran?: number }> = ({ lebar = 360, ukuran = 19 }) => {
  const { T } = useT();
  return (
    <div>
      <div style={{ fontFamily: tubuhFont, fontSize: ukuran, color: warna.abu, marginBottom: 8 }}>{T.legendaJudul}</div>
      <div style={{ width: lebar, height: 14, background: `linear-gradient(90deg, ${PETA_WARNA.join(", ")})` }} />
      <div style={{ width: lebar, display: "flex", justifyContent: "space-between", fontFamily: tubuhFont, fontSize: ukuran - 2, color: warna.samar, marginTop: 4 }}>
        <span>{T.legendaRendah}</span>
        <span>{T.legendaTinggi}</span>
      </div>
    </div>
  );
};

/** Vertical bar chart: years along the bottom, labels on chosen bars. */
const BatangTahun: React.FC<{ tahun: (number | string)[]; nilai: number[]; tampil: (i: number) => number; sorot?: (i: number) => boolean; W?: number; H?: number; label?: (i: number) => string | null; ukuranLabel?: number }> = ({
  tahun,
  nilai,
  tampil,
  sorot = () => false,
  W = 1100,
  H = 420,
  label = () => null,
  ukuranLabel = 22,
}) => {
  const maks = Math.max(...nilai);
  const n = nilai.length;
  const bw = W / n;
  return (
    <svg width={W} height={H + 70}>
      {nilai.map((v, i) => {
        const o = tampil(i);
        const h = (H * v * o) / maks;
        const s = sorot(i);
        const lab = label(i);
        return (
          <g key={i}>
            <rect x={i * bw + bw * 0.14} y={H - h + 30} width={bw * 0.72} height={h} fill={s ? warna.bara : ABU_GELAP} />
            {lab && o > 0.5 ? (
              <text x={i * bw + bw / 2} y={H - h + 18} fill={s ? warna.bara : warna.abu} fontSize={ukuranLabel} textAnchor="middle" fontFamily={angkaGaya.fontFamily as string} fontWeight={600}>
                {lab}
              </text>
            ) : null}
            {(i % 5 === 0 || i === n - 1) && (
              <text x={i === 0 ? 0 : i === n - 1 ? W : i * bw + bw / 2} y={H + 62} fill={warna.samar} fontSize={20} textAnchor={i === 0 ? "start" : i === n - 1 ? "end" : "middle"} fontFamily={tubuhFont}>
                {tahun[i]}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
};

/** Horizontal bar, 0-100%. */
const Persen: React.FC<{ label: string; pct: number; tampil: number; lebar?: number; tinggi?: number; ukuran?: number; warnaB?: string; lokal: string }> = ({
  label,
  pct,
  tampil,
  lebar = 900,
  tinggi = 54,
  ukuran = 28,
  warnaB = warna.bara,
  lokal,
}) => (
  <div>
    <div style={{ fontFamily: tubuhFont, fontSize: ukuran, color: warna.kapur, marginBottom: 8 }}>{label}</div>
    <div style={{ display: "flex", alignItems: "center", gap: 22 }}>
      <div style={{ width: lebar, height: tinggi, background: warna.arang, position: "relative" }}>
        <div style={{ width: (lebar * pct * tampil) / 100, height: tinggi, background: warnaB }} />
      </div>
      <div style={{ ...angkaGaya, fontSize: tinggi * 0.9, fontWeight: 600, color: warnaB, opacity: tampil }}>{komaL(pct, pct < 10 ? 1 : 0, lokal)}%</div>
    </div>
  </div>
);

const urutPeringkat = D.factors;
const MAKS_FAKTOR = urutPeringkat[0].v;
const STATUS_KEY = "forest-area status (APL etc.)";

const Faktor: React.FC<{ tampil: (i: number) => number; lebarNama?: number; lebarBatang?: number; ukuran?: number; tinggi?: number; gap?: number }> = ({
  tampil,
  lebarNama = 640,
  lebarBatang = 760,
  ukuran = 28,
  tinggi = 34,
  gap = 14,
}) => {
  const { T, koma } = useT();
  return (
    <div style={{ display: "flex", flexDirection: "column", gap }}>
      {urutPeringkat.map((d, i) => {
        const o = tampil(i);
        const st = d.k === STATUS_KEY;
        const w = st ? warna.nyala : i < 5 ? warna.bara : ABU_GELAP;
        return (
          <div key={d.k} style={{ display: "flex", alignItems: "center", gap: 20 }}>
            <div style={{ width: lebarNama, flexShrink: 0, fontFamily: tubuhFont, fontSize: ukuran, color: st ? warna.nyala : i < 5 ? warna.kapur : warna.abu, fontWeight: st || i < 5 ? 600 : 400 }}>
              {i + 1}. {T.faktor[d.k]}
            </div>
            <div style={{ width: lebarBatang, height: tinggi, background: warna.arang, flexShrink: 0 }}>
              <div style={{ width: (lebarBatang * d.v * o) / MAKS_FAKTOR, height: tinggi, background: w }} />
            </div>
            <div style={{ ...angkaGaya, fontSize: ukuran * 0.85, color: w, opacity: o, width: 110 }}>{koma(d.v, 3)}</div>
          </div>
        );
      })}
    </div>
  );
};

/** Event-study ratios around the planting year, peat and mineral soil, on a log axis. */
const GrafikSawit: React.FC<{ W: number; H: number; tampil: (i: number) => number; ukuran?: number }> = ({ W, H, tampil, ukuran = 20 }) => {
  const { T, koma } = useT();
  const bins = D.sawit.peat.map((b) => b.bin);
  const n = bins.length;
  const lo = Math.log(0.01), hi = Math.log(3.2);
  const y = (r: number) => H - ((Math.log(Math.max(r, 0.01)) - lo) / (hi - lo)) * H;
  const x = (i: number) => 70 + (i + 0.5) * ((W - 90) / n);
  const seri = [
    { k: "peat", w: warna.bara, data: D.sawit.peat, nama: T.gambut },
    { k: "mineral", w: warna.abu, data: D.sawit.mineral, nama: T.mineral },
  ];
  const lab = (b: string) => b.replace("..", " – ").replace("-9 – -6", "−9 – −6").replace("-5 – -3", "−5 – −3").replace("-2 – -1", "−2 – −1");
  return (
    <svg width={W} height={H + 80}>
      {[0.01, 0.1, 1, 2].map((t) => (
        <g key={t}>
          <line x1={60} x2={W} y1={y(t) + 10} y2={y(t) + 10} stroke={t === 1 ? warna.kapur : warna.garis} strokeWidth={t === 1 ? 2 : 1} strokeDasharray={t === 1 ? "8 6" : undefined} />
          <text x={52} y={y(t) + 16} fill={warna.samar} fontSize={ukuran - 2} textAnchor="end" fontFamily={tubuhFont}>
            {koma(t, t < 1 ? (t < 0.1 ? 2 : 1) : 0)}
          </text>
        </g>
      ))}
      <rect x={x(3) - (W - 90) / n / 2} y={0} width={(W - 90) / n * 4} height={H + 20} fill="rgba(255,255,255,0.03)" />
      {seri.map((s) => (
        <g key={s.k}>
          <polyline
            points={s.data.map((b, i) => `${x(i)},${y(b.ratio) + 10}`).filter((_, i) => tampil(i) > 0.5).join(" ")}
            fill="none"
            stroke={s.w}
            strokeWidth={4}
          />
          {s.data.map((b, i) => (
            <circle key={i} cx={x(i)} cy={y(b.ratio) + 10} r={8} fill={s.w} opacity={tampil(i)} />
          ))}
        </g>
      ))}
      {bins.map((b, i) => (
        <text key={b} x={x(i)} y={H + 48} fill={warna.abu} fontSize={ukuran} textAnchor="middle" fontFamily={tubuhFont}>
          {lab(b)}
        </text>
      ))}
      <text x={x(1)} y={H + 76} fill={warna.samar} fontSize={ukuran - 2} textAnchor="middle" fontFamily={tubuhFont}>
        ← {T.sebelum}
      </text>
      <text x={x(4.5)} y={H + 76} fill={warna.samar} fontSize={ukuran - 2} textAnchor="middle" fontFamily={tubuhFont}>
        {T.sesudah} →
      </text>
      {seri.map((s, k) => (
        <g key={`leg${s.k}`}>
          <rect x={W - 260} y={14 + k * 34} width={22} height={6} fill={s.w} />
          <text x={W - 228} y={22 + k * 34} fill={s.w} fontSize={ukuran} fontFamily={tubuhFont} fontWeight={600}>
            {s.nama}
          </text>
        </g>
      ))}
    </svg>
  );
};

/* ---------------------------------- scenes --------------------------- */

const KartuJudul: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { T } = useT();
  const f = useCurrentFrame();
  const a = masuk(f, 4, 24);
  return (
    <Lembut panjang={panjang}>
      <Peta panjang={panjang} zoom={1.05} redup={0.35} />
      <Kolom jarak={26}>
        <div style={{ opacity: a, transform: `translateY(${(1 - a) * 20}px)` }}>
          <div style={{ marginBottom: 24 }}>
            <Alis anak={T.alisJudul} />
          </div>
          <h1 style={{ fontFamily: judulFont, fontWeight: 900, fontSize: 100, lineHeight: 0.94, letterSpacing: "-0.04em", color: warna.kapur, margin: 0 }}>
            {T.judul.map((l, i) => (
              <React.Fragment key={l}>
                {i > 0 && <br />}
                {l}
              </React.Fragment>
            ))}
          </h1>
          <div style={{ marginTop: 28 }}>
            <Keterangan lebar={760} anak={T.subJudul} />
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Buka: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { T, koma } = useT();
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const b = masuk(f, Math.round(panjang * 0.72), 22);
  const nilai = interpolate(f, [10, 70], [0, D.total_gt.central], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const pk = D.tahun.indexOf(D.puncak.tahun);
  const top3 = [...D.co2_tahun].map((v, i) => [v, i]).sort((x, y) => y[0] - x[0]).slice(0, 3).map((x) => x[1]);
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Bkg sumber={T.sumberBuka} tampil={a} />
      <Kolom jarak={10}>
        <div style={{ opacity: a }}>
          <Alis anak={T.alisBuka} />
          <div style={{ display: "flex", alignItems: "baseline", gap: 26, marginTop: 12 }}>
            <Angka anak={koma(nilai, 1)} ukuran={150} />
            <div style={{ fontFamily: tubuhFont, fontSize: 34, color: warna.kapur }}>{T.satuanGt}</div>
          </div>
        </div>
        <BatangTahun
          tahun={D.tahun}
          nilai={D.co2_tahun}
          W={1700}
          H={360}
          tampil={(i) => masuk(f, Math.round(panjang * 0.12) + i * 5, 18)}
          sorot={(i) => top3.includes(i)}
          label={(i) => (top3.includes(i) ? `${koma(D.co2_tahun[i], 0)}${i === pk ? ` Mt · ${T.terburuk}` : ""}` : null)}
        />
        <div style={{ marginTop: 6 }}>
          <Garis anak={T.rentang(koma(D.total_gt.low, 1), koma(D.total_gt.high, 1))} tampil={b} lebar={1400} />
        </div>
      </Kolom>
    </Lembut>
  );
};

const Gambut: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { T, ribuan } = useT();
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const b = masuk(f, Math.round(panjang * 0.12), 40);
  const c = masuk(f, Math.round(panjang * 0.3), 40);
  const d = masuk(f, Math.round(panjang * 0.55), 22);
  const G = D.gambut;
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Bkg sumber={T.sumberGambut} tampil={a} />
      <Kolom jarak={44}>
        <div style={{ opacity: a }}>
          <Judul anak={T.judulGambut} ukuran={62} />
        </div>
        <Persen label={`${T.luasDarat} — ${T.gambut}`} pct={G.land_pct} tampil={b} warnaB={warna.gambut} lebar={1200} lokal={T.lokal} />
        <Persen label={`${T.emisi} — ${T.gambut}`} pct={G.emis_pct} tampil={c} lebar={1200} lokal={T.lokal} />
        <Garis anak={T.kali(String(G.kali), ribuan(G.t_per_km2_peat), komaL(G.t_per_km2_mineral, 0, T.lokal))} tampil={d} lebar={1400} ukuran={30} />
      </Kolom>
    </Lembut>
  );
};

const FaktorAdegan: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { T, koma } = useT();
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const c = masuk(f, Math.round(panjang * 0.75), 22);
  // bars follow the narration: drought, forest, access, palm, peat ... then the rest together
  const urutan = [0.22, 0.3, 0.42, 0.5, 0.55, 0.62, 0.62, 0.62, 0.62];
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Bkg sumber={T.sumberFaktor} tampil={a} />
      <Kolom jarak={22}>
        <div style={{ opacity: a }}>
          <Judul anak={T.judulFaktor} ukuran={56} />
          <div style={{ fontFamily: tubuhFont, fontSize: 22, color: warna.abu, marginTop: 10 }}>{T.ukuranFaktor}</div>
        </div>
        <Faktor tampil={(i) => masuk(f, Math.round(panjang * urutan[i]), 24)} />
        <div style={{ fontFamily: tubuhFont, fontSize: 22, color: warna.abu, opacity: c, maxWidth: 1500 }}>{T.catatanFaktor(koma(D.roc_auc, 2), D.block_km)}</div>
      </Kolom>
    </Lembut>
  );
};

const Sawit: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { T, ribuan } = useT();
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const c = masuk(f, Math.round(panjang * 0.7), 22);
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Bkg sumber={T.sumberSawit} tampil={a} />
      <Kolom jarak={18}>
        <div style={{ opacity: a }}>
          <Judul anak={T.judulSawit} ukuran={54} />
          <div style={{ fontFamily: tubuhFont, fontSize: 22, color: warna.abu, marginTop: 10 }}>
            {T.rasio} · {T.sumbuSawit}
          </div>
        </div>
        <GrafikSawit W={1500} H={420} tampil={(i) => masuk(f, Math.round(panjang * 0.12) + i * 22, 16)} />
        <Garis anak={T.catatanSawit(ribuan(D.palm_burned_max.km2), D.palm_burned_max.tahun)} tampil={c} lebar={1400} />
      </Kolom>
    </Lembut>
  );
};

const Ladang: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { T, koma } = useT();
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const L = D.ladang, G = D.gambut_viirs;
  const baris = [
    [`${koma(L.large_pct, 1)}%`, `${koma(G.large_pct, 1)}%`],
    [`×${koma(L.dry_over_wet, 1)}`, `×${koma(G.dry_over_wet, 0)}`],
    [`${koma(L.share_of_det_in_large_events_pct, 0)}%`, `${koma(G.share_of_det_in_large_events_pct, 0)}%`],
  ];
  const t = [0.25, 0.45, 0.7];
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Bkg sumber={T.sumberLadang} tampil={a} />
      <Kolom jarak={30}>
        <div style={{ opacity: a }}>
          <Judul anak={T.judulLadang} ukuran={56} />
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "620px 480px 480px", columnGap: 40, rowGap: 26, alignItems: "end" }}>
          <div />
          <div style={{ fontFamily: tubuhFont, fontSize: 26, fontWeight: 600, color: warna.kapur, opacity: a }}>{T.kolomLadang}</div>
          <div style={{ fontFamily: tubuhFont, fontSize: 26, fontWeight: 600, color: warna.bara, opacity: a }}>{T.kolomGambut}</div>
          {baris.map(([l, g], i) => {
            const o = masuk(f, Math.round(panjang * t[i]), 22);
            return (
              <React.Fragment key={i}>
                <div style={{ fontFamily: tubuhFont, fontSize: 28, color: warna.abu, opacity: o, paddingBottom: 10 }}>{T.barisLadang[i]}</div>
                <div style={{ opacity: o }}><Angka anak={l} ukuran={78} warnaA={warna.kapur} /></div>
                <div style={{ opacity: o }}><Angka anak={g} ukuran={78} warnaA={warna.bara} /></div>
              </React.Fragment>
            );
          })}
        </div>
      </Kolom>
    </Lembut>
  );
};

const Uji: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { T } = useT();
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const U = D.uji2026;
  const kel = [
    { nama: T.model, v5: U.dry.top5, v10: U.dry.top10, w: warna.bara },
    { nama: T.gambutRiwayat, v5: U.peat_recent.top5, v10: U.peat_recent.top10, w: warna.abu },
    { nama: T.gambutSaja, v5: U.peat_only.top5, v10: U.peat_only.top10, w: ABU_GELAP },
  ];
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Bkg sumber={T.sumberUji} tampil={a} />
      <Kolom jarak={26}>
        <div style={{ opacity: a }}>
          <Judul anak={T.judulUji} ukuran={54} />
          <div style={{ fontFamily: tubuhFont, fontSize: 24, color: warna.abu, marginTop: 12 }}>{T.tertangkap}</div>
        </div>
        {[
          { judul: T.atas5, k: "v5" as const, t: 0.45 },
          { judul: T.atas10, k: "v10" as const, t: 0.62 },
        ].map((blok) => (
          <div key={blok.k} style={{ opacity: masuk(f, Math.round(panjang * blok.t) - 20, 20) }}>
            <div style={{ fontFamily: tubuhFont, fontSize: 26, color: warna.kapur, marginBottom: 10 }}>{blok.judul}</div>
            {kel.map((g, j) => {
              const o = masuk(f, Math.round(panjang * (blok.k === "v10" && j > 0 ? 0.8 : blok.t)) + j * 6, 22);
              const v = g[blok.k];
              return (
                <div key={g.nama} style={{ display: "flex", alignItems: "center", gap: 18, marginBottom: 8 }}>
                  <div style={{ width: 520, fontFamily: tubuhFont, fontSize: 24, color: j === 0 ? warna.kapur : warna.abu }}>{g.nama}</div>
                  <div style={{ width: 900, height: 34, background: warna.arang }}>
                    <div style={{ width: (900 * v * o) / 100, height: 34, background: g.w }} />
                  </div>
                  <div style={{ ...angkaGaya, fontSize: 32, fontWeight: 600, color: j === 0 ? warna.bara : warna.abu, opacity: o }}>{komaL(v, 0, T.lokal)}%</div>
                </div>
              );
            })}
          </div>
        ))}
        <div style={{ fontFamily: tubuhFont, fontSize: 21, color: warna.samar }}>{T.catatanUji}</div>
      </Kolom>
    </Lembut>
  );
};

const Ramalan: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { T, koma, ribuan } = useT();
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const b = masuk(f, Math.round(panjang * 0.18), 22);
  const c = masuk(f, Math.round(panjang * 0.4), 22);
  const d = masuk(f, Math.round(panjang * 0.62), 22);
  const P = D.p2027;
  const usd = (s: "normal" | "dry") => D.harga.map((p) => ((v) => koma(v, v < 1 ? 2 : 1))((P.usd_bn as Record<string, Record<string, number>>)[s][String(p)])).join(" / ");
  const baris = T.dimanaBaris(koma(P.top5_status.APL, 0), koma(P.top5_status.HP, 0), koma(P.top5_peat_pct, 0), koma(P.top5_open_pct, 0), koma(P.top5_not_burned_pct, 0));
  return (
    <Lembut panjang={panjang}>
      <Peta panjang={panjang} zoom={1.03} />
      <AbsoluteFill style={{ background: `linear-gradient(90deg, ${warna.jelaga} 0%, ${warna.jelaga} 38%, rgba(10,12,15,0) 52%)` }} />
      <AbsoluteFill style={{ background: `linear-gradient(180deg, rgba(10,12,15,0) 80%, ${warna.jelaga} 92%)` }} />
      <Bkg sumber={T.sumberRamal} tampil={a} />
      <Kolom jarak={0}>
        <div style={{ width: 760, opacity: a }}>
          <Alis anak={T.alisRamal} />
          <div style={{ display: "flex", gap: 50, marginTop: 22 }}>
            {(["normal", "dry"] as const).map((s, k) => (
              <div key={s} style={{ opacity: k ? b : a }}>
                <div style={{ fontFamily: tubuhFont, fontSize: 24, color: k ? warna.bara : warna.abu }}>{k ? T.elNino : T.normal}</div>
                <Angka anak={ribuan(P.km2[s])} ukuran={84} warnaA={k ? warna.nyala : warna.kapur} />
                <div style={{ fontFamily: tubuhFont, fontSize: 21, color: warna.abu }}>{T.terbakar}</div>
                <div style={{ ...angkaGaya, fontSize: 34, color: k ? warna.nyala : warna.kapur, marginTop: 14 }}>{koma(P.mt[s], 0)}</div>
                <div style={{ fontFamily: tubuhFont, fontSize: 21, color: warna.abu }}>{T.satuanMt}</div>
              </div>
            ))}
          </div>
          <div style={{ marginTop: 26, opacity: c }}>
            <div style={{ fontFamily: tubuhFont, fontSize: 22, color: warna.abu }}>{T.harga}</div>
            {(["normal", "dry"] as const).map((s2, k) => (
              <div key={s2} style={{ display: "flex", alignItems: "baseline", gap: 14, marginTop: 6 }}>
                <span style={{ fontFamily: tubuhFont, fontSize: 22, color: k ? warna.bara : warna.abu, width: 190 }}>{k ? T.elNino : T.normal}</span>
                <span style={{ ...angkaGaya, fontSize: 30, color: k ? warna.nyala : warna.kapur }}>{usd(s2)}</span>
                <span style={{ fontFamily: tubuhFont, fontSize: 21, color: warna.abu }}>{T.miliar}</span>
              </div>
            ))}
          </div>
          <div style={{ marginTop: 26, opacity: d }}>
            <div style={{ fontFamily: tubuhFont, fontSize: 22, color: warna.abu, marginBottom: 8 }}>{T.dimana}</div>
            {baris.map((l) => (
              <div key={l} style={{ marginBottom: 6 }}>
                <Garis anak={l} tampil={d} lebar={760} ukuran={25} />
              </div>
            ))}
          </div>
          <div style={{ marginTop: 26, opacity: a }}>
            <Legenda />
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Tutup: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { T } = useT();
  const f = useCurrentFrame();
  const a = masuk(f, 4, 22);
  const b = masuk(f, Math.round(panjang * 0.15), 24);
  const c = masuk(f, Math.round(panjang * 0.45), 24);
  const d = masuk(f, Math.round(panjang * 0.62), 24);
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Kolom jarak={28}>
        <h1 style={{ fontFamily: judulFont, fontWeight: 900, fontSize: 60, lineHeight: 1.05, color: warna.abu, margin: 0, opacity: a }}>{T.tutup1}</h1>
        <div style={{ opacity: b, maxWidth: 1500, fontFamily: tubuhFont, fontSize: 42, color: warna.kapur, lineHeight: 1.3 }}>{T.tutup2}</div>
        <h2 style={{ fontFamily: judulFont, fontWeight: 900, fontSize: 64, lineHeight: 1.08, letterSpacing: "-0.02em", color: warna.bara, margin: 0, opacity: c, maxWidth: 1600 }}>{T.tutup3}</h2>
        <div style={{ opacity: d, borderLeft: `3px solid ${warna.garis}`, paddingLeft: 20, fontFamily: tubuhFont, fontSize: 25, color: warna.abu, lineHeight: 1.45, maxWidth: 1500, marginTop: 14 }}>
          {T.tutupCatat}
        </div>
      </Kolom>
    </Lembut>
  );
};

const KartuSumber: React.FC<{ panjang: number }> = () => {
  const { T } = useT();
  const f = useCurrentFrame();
  const a = masuk(f, 4, 20);
  return (
    <AbsoluteFill style={{ backgroundColor: warna.jelaga, opacity: a }}>
      <Kolom jarak={16}>
        <Alis anak={T.sumberData} />
        <div style={{ display: "flex", flexDirection: "column", gap: 10, width: 1680 }}>
          {T.barisSumber.map(([k, v]) => (
            <div key={k} style={{ display: "flex", gap: 28, alignItems: "baseline" }}>
              <div style={{ width: 240, fontFamily: tubuhFont, fontSize: 24, fontWeight: 600, color: warna.kapur }}>{k}</div>
              <div style={{ fontFamily: tubuhFont, fontSize: 24, color: warna.abu }}>{v}</div>
            </div>
          ))}
        </div>
        <div style={{ marginTop: 12, paddingTop: 16, borderTop: `2px solid ${warna.bara}`, fontFamily: tubuhFont, fontSize: 22, color: warna.kapur, lineHeight: 1.5, maxWidth: 1680 }}>
          {T.peringatan}
        </div>
      </Kolom>
    </AbsoluteFill>
  );
};

/* --------------------------------- film ------------------------------ */

const ADEGAN: Record<string, React.FC<{ panjang: number }>> = {
  "01-buka": Buka,
  "02-gambut": Gambut,
  "03-faktor": FaktorAdegan,
  "04-sawit": Sawit,
  "05-ladang": Ladang,
  "06-uji": Uji,
  "07-ramalan": Ramalan,
  "08-tutup": Tutup,
};

export const ApiFilm: React.FC<{ bahasa?: Bahasa }> = ({ bahasa = "id" }) => {
  const J = JADWAL_API[bahasa]!;
  const T = bahasa === "en" ? TEKS_EN : TEKS_ID;
  return (
    <Ctx.Provider value={bahasa}>
      <AbsoluteFill style={{ backgroundColor: warna.jelaga }}>
        <Audio src={staticFile(`${T.audio}/${T.musik}`)} />
        <Sequence durationInFrames={J.JUDUL_FRAME}>
          <KartuJudul panjang={J.JUDUL_FRAME} />
        </Sequence>
        {J.adegan.map((a) => {
          const K = ADEGAN[a.id];
          return (
            <Sequence key={a.id} from={a.mulai} durationInFrames={a.panjang}>
              <K panjang={a.panjang} />
              <Audio src={staticFile(`${T.audio}/${a.id}.mp3`)} />
            </Sequence>
          );
        })}
        <Sequence from={J.akhirNarasi} durationInFrames={J.TUTUP_FRAME}>
          <KartuSumber panjang={J.TUTUP_FRAME} />
        </Sequence>
      </AbsoluteFill>
    </Ctx.Provider>
  );
};

/* ------------------------------ infographic --------------------------- */

const Kotak: React.FC<{ judul: string; children: React.ReactNode }> = ({ judul, children }) => (
  <div style={{ borderTop: `2px solid ${warna.garis}`, paddingTop: 18 }}>
    <div style={{ fontFamily: tubuhFont, fontSize: 20, fontWeight: 600, letterSpacing: "0.16em", textTransform: "uppercase", color: warna.bara, marginBottom: 12 }}>{judul}</div>
    {children}
  </div>
);

/** Two 1080x1350 (4:5) pages: 1 = carbon and drivers, 2 = the 2027 risk map, what it means, sources. */
export const InfografisApi: React.FC<{ bahasa?: Bahasa; halaman?: 1 | 2 }> = ({ bahasa = "id", halaman = 1 }) => {
  const T = bahasa === "en" ? TEKS_EN : TEKS_ID;
  const ribuan = (n: number) => ribuanL(n, T.lokal);
  const koma = (n: number, d = 1) => komaL(n, d, T.lokal);
  const kecil = { fontFamily: tubuhFont, fontSize: 20, color: warna.abu, lineHeight: 1.4 } as React.CSSProperties;
  const kepala = (
    <div style={{ borderTop: `3px solid ${warna.bara}`, paddingTop: 16, display: "flex", justifyContent: "space-between" }}>
      <Alis anak={T.kiri} />
      <span style={{ fontFamily: tubuhFont, fontSize: 19, letterSpacing: "0.18em", color: warna.abu, textTransform: "uppercase" }}>
        {T.waktu} · {halaman}/2
      </span>
    </div>
  );
  const G = D.gambut;
  const pk = D.tahun.indexOf(D.puncak.tahun);
  const P = D.p2027;
  if (halaman === 1) {
    return (
      <Ctx.Provider value={bahasa}>
        <AbsoluteFill style={{ backgroundColor: warna.jelaga, padding: "46px 54px 36px", display: "flex", flexDirection: "column", gap: 18 }}>
          <div>
            {kepala}
            <h1 style={{ fontFamily: judulFont, fontWeight: 900, fontSize: 58, lineHeight: 0.98, letterSpacing: "-0.035em", color: warna.kapur, margin: "20px 0 0" }}>
              {T.judul.join(" ")}
            </h1>
          </div>
          <div style={{ display: "flex", gap: 34, alignItems: "flex-end" }}>
            <div style={{ width: 400 }}>
              <div style={{ ...kecil, color: warna.bara, fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase", fontSize: 18 }}>{T.alisBuka}</div>
              <Angka anak={koma(D.total_gt.central, 1)} ukuran={96} />
              <div style={{ fontFamily: tubuhFont, fontSize: 24, color: warna.kapur }}>{T.satuanGt}</div>
              <div style={{ ...kecil, fontSize: 18, marginTop: 6 }}>{T.rentang(koma(D.total_gt.low, 1), koma(D.total_gt.high, 1))}</div>
            </div>
            <BatangTahun tahun={D.tahun} nilai={D.co2_tahun} W={540} H={150} tampil={() => 1} sorot={(i) => i === pk} label={(i) => (i === pk ? `${koma(D.puncak.mt, 0)} Mt` : null)} ukuranLabel={18} />
          </div>
          <Kotak judul={T.judulGambut}>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <Persen label={`${T.luasDarat} — ${T.gambut}`} pct={G.land_pct} tampil={1} warnaB={warna.gambut} lebar={780} tinggi={30} ukuran={21} lokal={T.lokal} />
              <Persen label={`${T.emisi} — ${T.gambut}`} pct={G.emis_pct} tampil={1} lebar={780} tinggi={30} ukuran={21} lokal={T.lokal} />
            </div>
          </Kotak>
          <Kotak judul={T.judulFaktor}>
            <Faktor tampil={() => 1} lebarNama={480} lebarBatang={340} ukuran={20} tinggi={20} gap={7} />
            <div style={{ ...kecil, fontSize: 16, marginTop: 8 }}>
              {T.ukuranFaktor}. {T.catatanFaktor(koma(D.roc_auc, 2), D.block_km)}
            </div>
          </Kotak>
          <Kotak judul={T.catatan}>
            <div style={{ ...kecil, color: warna.kapur, fontSize: 19 }}>· {T.artinyaBaris[1]}</div>
            <div style={{ ...kecil, color: warna.kapur, fontSize: 19 }}>· {T.artinyaBaris[2]}</div>
          </Kotak>
          <div style={{ ...kecil, fontSize: 14, borderTop: `1px solid ${warna.garis}`, paddingTop: 10, marginTop: "auto" }}>
            {T.barisSumber.filter((_, i) => [0, 2, 3, 6].includes(i)).map(([k, v]) => `${k}: ${v}`).join(" · ")}
          </div>
        </AbsoluteFill>
      </Ctx.Provider>
    );
  }
  const usd = (s: "normal" | "dry") => D.harga.map((p) => ((v) => koma(v, v < 1 ? 2 : 1))((P.usd_bn as Record<string, Record<string, number>>)[s][String(p)])).join(" / ");
  const baris = T.dimanaBaris(koma(P.top5_status.APL, 0), koma(P.top5_status.HP, 0), koma(P.top5_peat_pct, 0), koma(P.top5_open_pct, 0), koma(P.top5_not_burned_pct, 0));
  return (
    <Ctx.Provider value={bahasa}>
      <AbsoluteFill style={{ backgroundColor: warna.jelaga, padding: "46px 54px 36px", display: "flex", flexDirection: "column", gap: 16 }}>
        <div>
          {kepala}
          <h1 style={{ fontFamily: judulFont, fontWeight: 900, fontSize: 48, lineHeight: 1, letterSpacing: "-0.03em", color: warna.kapur, margin: "18px 0 0" }}>{T.judulHal2}</h1>
        </div>
        <div style={{ position: "relative", height: 470, overflow: "hidden" }}>
          <Img src={staticFile("api/peta_risiko_ig.jpg")} style={{ position: "absolute", width: 972, height: 860, left: -80, top: -330 }} />
          <div style={{ position: "absolute", left: 0, top: 10 }}>
            <Legenda lebar={280} ukuran={17} />
          </div>
        </div>
        <div style={{ display: "flex", gap: 40 }}>
          {(["normal", "dry"] as const).map((s, k) => (
            <div key={s}>
              <div style={{ fontFamily: tubuhFont, fontSize: 21, color: k ? warna.bara : warna.abu }}>{k ? T.elNino : T.normal}</div>
              <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
                <Angka anak={ribuan(P.km2[s])} ukuran={56} warnaA={k ? warna.nyala : warna.kapur} />
                <span style={{ ...kecil, fontSize: 18 }}>{T.terbakar}</span>
              </div>
              <div style={{ ...kecil, fontSize: 18 }}>
                <span style={{ ...angkaGaya, color: k ? warna.nyala : warna.kapur }}>{koma(P.mt[s], 0)}</span> {T.satuanMt}
              </div>
              <div style={{ ...kecil, fontSize: 18 }}>
                US$ <span style={{ ...angkaGaya, color: k ? warna.nyala : warna.kapur }}>{usd(s)}</span> {T.miliar.replace("US$ ", "").replace(" US$", "")}
              </div>
            </div>
          ))}
        </div>
        <Kotak judul={T.dimana}>
          {baris.map((l) => (
            <div key={l} style={{ ...kecil, color: warna.kapur, fontSize: 20 }}>
              · {l}
            </div>
          ))}
        </Kotak>
        <Kotak judul={T.artinya}>
          {T.artinyaBaris.map((l) => (
            <div key={l} style={{ ...kecil, color: warna.kapur, fontSize: 19 }}>
              · {l}
            </div>
          ))}
        </Kotak>
        <div style={{ ...kecil, fontSize: 14, borderTop: `1px solid ${warna.garis}`, paddingTop: 10, marginTop: "auto" }}>
          {T.tutupCatat} {T.harga}: {T.sumberRamal.split("·")[1]?.trim()}. {T.barisSumber.filter((_, i) => [1, 4, 5].includes(i)).map(([k, v]) => `${k}: ${v}`).join(" · ")}. {T.peringatan}
        </div>
      </AbsoluteFill>
    </Ctx.Provider>
  );
};
