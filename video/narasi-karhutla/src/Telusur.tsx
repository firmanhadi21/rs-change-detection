/**
 * "Mengapa lebih parah?" — Part 2 of the concessions film.
 *
 * Part 1 found four concessions on the Ketapang coast holding an outsized
 * share of 2026's burn. Part 2 follows the evidence on why:
 *
 *   where fires started   VIIRS ignition lineage: most fire inside began
 *                         inside, but ignitions were no denser than outside
 *   what burned           almost no oil palm; PlanetScope before the fire
 *   land preparation?     2015 burns did not become palm (vs 22% elsewhere);
 *                         parcels are household-sized -> not supported
 *   PT AM                 most of it sits under pulpwood (HTI) permits
 *   why this year         record drought: 29 mm rain, Drought Code 718
 *   peat                  ~half of the burn (field-validated RF peat map);
 *                         in SKM and MKK peat inside burned 1.5-2x more
 *   like for like         2.3x shrinks to 1.4x after matching, but stays,
 *                         largest under forest, fires lasting longer
 *
 * Same palette, type, components and audio pipeline as Konsesi.tsx. Every
 * figure comes from telusurData.json (scripts/ketapang_film2_assets.py).
 * One component, two languages, as Part 1: every string lives in TEKS_ID /
 * TEKS_EN, and each language has its own measured schedule and audio.
 */

import React, { createContext, useContext } from "react";
import {
  AbsoluteFill,
  Audio,
  Img,
  interpolate,
  Sequence,
  staticFile,
  useCurrentFrame,
} from "remotion";
import { JADWAL_TELUSUR } from "./jadwalTelusur";
import type { Bahasa } from "./jadwalKonsesi";
import {
  Bingkai,
  Judul,
  Keterangan,
  Kolom,
  LatarDiam,
  Lembut,
  masuk,
  Penghitung,
} from "./komponen";
import {
  angkaGaya,
  judulFont,
  koma as komaId,
  ribuan as ribuanId,
  tubuhFont,
  warna,
} from "./teema";
import D from "./telusurData.json";

const HTI = "#5FA8D3";
const TEKS_ID = {
  lokal: "id-ID",
  audio: "audio/telusur",
  musik: "musik-telusur.mp3",
  planet: "planet.png",
  labelSumber: "Sumber",
  kiri: "Karhutla Kalimantan · Bagian 2",
  waktu: "November 2026",
  alisJudul: "Di dalam konsesi · Bagian 2",
  judul: ["MENGAPA", "LEBIH PARAH?"],
  subJudul:
    "Menelusuri asal api, apa yang terbakar, dan mengapa empat konsesi di pesisir Ketapang terbakar lebih luas.",
  kilas1: "Empat konsesi, satu pesisir.",
  kilas2: "Sengaja dibakar untuk ditanami sawit?",
  sumberApi:
    "VIIRS 375 m (S-NPP, NOAA-20), Jul–Okt 2026 · titik awal = deteksi tanpa api lain dalam 1,5 km dan 96 jam sebelumnya",
  alisApi: "Juli – Oktober 2026",
  titikAwal: "titik awal api di dalam keempat konsesi",
  dariDalam: "api di dalam konsesi yang bermula dari dalam",
  kepadatan: (a: string, b: string) =>
    `Kepadatan titik awal di dalam konsesi: ${a}–${b} × lahan tanpa izin di sekitarnya`,
  legendaApi: ["titik awal di dalam keempat konsesi", "titik awal di luar"],
  sumberSawit:
    "PlanetScope 3 m © Planet Labs PBC, 30 Jun – 10 Jul 2026 · sawit: Descals dkk. 2024 · bekas bakar: Sentinel-2 dNBR",
  alisSawit: "Sebelum kebakaran",
  sawit: "bekas bakar berupa kebun sawit",
  sawitDari: (a: string, b: string) => `${a} dari ${b} hektare`,
  sawitKet: "Tiga petak yang kemudian terbakar, dan sebuah kebun sawit sebagai pembanding.",
  sumberSiap:
    "MODIS MCD64A1 2015 · tahun tanam sawit Descals dkk. 2024 (s.d. 2021) · petak: PlanetScope 3 m",
  judulSiap: "Lahan terbakar 2015 yang menjadi sawit pada 2021",
  barisSiap: ["Konsesi lain di sekitarnya", "Keempat konsesi", "Lahan tanpa izin"],
  petak: (h: string) =>
    `Petak yang dibuka di PT MKK umumnya ${h} hektare — ukuran kebun warga, bukan blok perusahaan (25–30 ha).`,
  sumberIzin:
    "Izin HTI: Kementerian Kehutanan 2010 via Global Forest Watch · konsesi sawit: GFW (±2012) · bekas bakar: Sentinel-2",
  izin: "areal PT AM tumpang tindih dengan izin hutan tanaman industri",
  izinBakar: (p: string) => `${p}% bekas bakarnya berada di dalam izin HTI`,
  legendaIzin: ["izin HTI (kebun kayu)", "terbakar 2026"],
  sumberKemarau:
    "Hujan: CHIRPS · Kode Kekeringan (DC): sistem FWI seperti SPBK BMKG, ERA5-Land, 3 titik di atas konsesi",
  alisKemarau: "Mengapa tahun ini?",
  hujan: "hujan, 1 Juli – 15 September 2026",
  hujanLain: (a: string, b: string) => `2019: ${a} mm · 2015: ${b} mm`,
  judulDC: "Kode Kekeringan (DC), pesisir Ketapang",
  ekstrem: "ambang ekstrem BMKG",
  bulan: ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"],
  sumberGambut:
    "Gambut: random forest diuji titik lapangan (25 m) · luar = gambut tanpa izin dalam 10 km · bekas bakar: Sentinel-2 dNBR",
  gambut: "bekas bakar berada di atas gambut",
  gambutBaris: "Bagian gambut yang terbakar",
  dalamLuar: ["di dalam", "di luar"],
  legendaGambut: ["gambut", "terbakar 2026"],
  sumberSetara:
    "Pencocokan setara (CEM), 5 km block bootstrap · VIIRS, Sentinel-2, Descals 2024, Hansen GFC, GHSL",
  judulSetara: "Dibandingkan dengan lahan serupa",
  mentah: "tanpa penyetaraan",
  setara: "setelah disetarakan",
  setaraKet:
    "disetarakan: gambut, kedalaman, tutupan lahan, riwayat kebakaran 2015–2023, jarak ke air dan permukiman, kepadatan titik awal",
  ci: (a: string, b: string) => `selang 95%: ${a}–${b}×`,
  hutan: "di bawah tegakan hutan",
  lama: "lama api menyala per sel",
  tutup1: "Tidak tampak penyiapan lahan sawit.",
  tutupKet: "Data satelit menunjukkan di mana api bermula dan apa yang terbakar — bukan siapa yang menyalakannya.",
  tutup2: "Gambut rusak di dalam konsesi terbakar lebih luas dan lebih lama.",
  tutup3:
    "UU 32/2009 Pasal 88: pemegang izin bertanggung jawab mutlak atas kebakaran di arealnya. Berikutnya: jalannya api dari radar NISAR, menembus asap.",
  sumberData: "Sumber data",
  baris: [
    ["Api", "VIIRS 375 m (S-NPP, NOAA-20), NASA LANCE; MODIS FIRMS 2014–2026"],
    ["Bekas bakar", "Sentinel-2 dNBR (Apr–Jul vs Sep–Okt 2026); MODIS MCD64A1 2015, 2019, 2023"],
    ["Citra", "PlanetScope 3 m © Planet Labs PBC (2023, 2025, 2026)"],
    ["Sawit", "Descals dkk. 2024, tutupan dan tahun tanam s.d. 2021"],
    ["Hutan", "Hansen Global Forest Change v1.12"],
    ["Gambut", "Random forest (Earth Engine), diuji pada titik lapangan; pembanding BBSDLP"],
    ["Cuaca", "ERA5-Land, CHIRPS; sistem FWI dengan kelas BMKG"],
    ["Izin", "Global Forest Watch: konsesi sawit (±2012), HTI (2010)"],
  ] as [string, string][],
  peringatan:
    "Lokasi dan kondisi lahan bukan bukti siapa yang menyalakan api. Batas izin berasal dari data sekitar 2010–2012. Peta sawit berakhir 2021. Titik awal yang tertutup awan atau asap dapat tercatat sebagai api baru.",
};

type Teks = typeof TEKS_ID;

const TEKS_EN: Teks = {
  lokal: "en-GB",
  audio: "audio/telusur-en",
  musik: "musik-telusur-en.mp3",
  planet: "planet_en.png",
  labelSumber: "Source",
  kiri: "Kalimantan fires · Part 2",
  waktu: "November 2026",
  alisJudul: "Inside the concessions · Part 2",
  judul: ["WHY", "WORSE?"],
  subJudul:
    "Tracing where the fires began, what burned, and why four concessions on the Ketapang coast burned more widely.",
  kilas1: "Four concessions, one coast.",
  kilas2: "Burned on purpose, to plant oil palm?",
  sumberApi:
    "VIIRS 375 m (S-NPP, NOAA-20), Jul–Oct 2026 · fire start = a detection with no other fire within 1.5 km in the 96 h before",
  alisApi: "July – October 2026",
  titikAwal: "points where fire began inside the four concessions",
  dariDalam: "fire inside each concession that started inside it",
  kepadatan: (a: string, b: string) =>
    `Fire starts per km² inside the concessions: ${a}–${b} × the unpermitted land around them`,
  legendaApi: ["fire start inside the four concessions", "fire start outside"],
  sumberSawit:
    "PlanetScope 3 m © Planet Labs PBC, 30 Jun – 10 Jul 2026 · oil palm: Descals et al. 2024 · burn: Sentinel-2 dNBR",
  alisSawit: "Before the fires",
  sawit: "of the burn was oil palm plantation",
  sawitDari: (a: string, b: string) => `${a} of ${b} hectares`,
  sawitKet: "Three plots that later burned, and an oil palm plantation for comparison.",
  sumberSiap:
    "MODIS MCD64A1 2015 · oil palm planting year, Descals et al. 2024 (to 2021) · plots: PlanetScope 3 m",
  judulSiap: "Land burned in 2015 that was oil palm by 2021",
  barisSiap: ["Other concessions nearby", "The four concessions", "Unpermitted land"],
  petak: (h: string) =>
    `Plots cleared in PT MKK are mostly ${h} hectare — family-farm size, not a company block (25–30 ha).`,
  sumberIzin:
    "Pulpwood (HTI) permits: Ministry of Forestry 2010 via Global Forest Watch · oil palm: GFW (c. 2012) · burn: Sentinel-2",
  izin: "of PT AM overlaps a pulpwood (HTI) plantation permit",
  izinBakar: (p: string) => `${p}% of its burn lies inside the pulpwood permit`,
  legendaIzin: ["pulpwood (HTI) permit", "burned 2026"],
  sumberKemarau:
    "Rain: CHIRPS · Drought Code (DC): FWI system as in BMKG's SPBK, ERA5-Land, 3 points over the concessions",
  alisKemarau: "Why this year?",
  hujan: "of rain, 1 July – 15 September 2026",
  hujanLain: (a: string, b: string) => `2019: ${a} mm · 2015: ${b} mm`,
  judulDC: "Drought Code (DC), Ketapang coast",
  ekstrem: "BMKG extreme threshold",
  bulan: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
  sumberGambut:
    "Peat: random forest validated at field points (25 m) · outside = unpermitted peat within 10 km · burn: Sentinel-2 dNBR",
  gambut: "of the burn was on peat",
  gambutBaris: "Share of peat that burned",
  dalamLuar: ["inside", "outside"],
  legendaGambut: ["peat", "burned 2026"],
  sumberSetara:
    "Coarsened exact matching (CEM), 5 km block bootstrap · VIIRS, Sentinel-2, Descals 2024, Hansen GFC, GHSL",
  judulSetara: "Compared like for like",
  mentah: "raw",
  setara: "after matching",
  setaraKet:
    "matched on: peat, peat depth, land cover, fire history 2015–2023, distance to water and settlements, density of fire starts",
  ci: (a: string, b: string) => `95% interval: ${a}–${b}×`,
  hutan: "under forest canopy",
  lama: "days burning per cell",
  tutup1: "No sign of land being prepared for oil palm.",
  tutupKet: "Satellite data shows where fire began and what burned — not who lit it.",
  tutup2: "Damaged peat inside the concessions burned wider and longer.",
  tutup3:
    "Indonesian Law 32/2009, Art. 88: permit holders bear strict liability for fires on their land. Next: the fire's spread from NISAR radar, through the smoke.",
  sumberData: "Data sources",
  baris: [
    ["Fire", "VIIRS 375 m (S-NPP, NOAA-20), NASA LANCE; MODIS FIRMS 2014–2026"],
    ["Burned area", "Sentinel-2 dNBR (Apr–Jul vs Sep–Oct 2026); MODIS MCD64A1 2015, 2019, 2023"],
    ["Imagery", "PlanetScope 3 m © Planet Labs PBC (2023, 2025, 2026)"],
    ["Oil palm", "Descals et al. 2024, extent and planting year to 2021"],
    ["Forest", "Hansen Global Forest Change v1.12"],
    ["Peat", "Random forest (Earth Engine), validated at field points; BBSDLP for comparison"],
    ["Weather", "ERA5-Land, CHIRPS; FWI system with BMKG classes"],
    ["Permits", "Global Forest Watch: oil palm concessions (c. 2012), pulpwood HTI (2010)"],
  ] as [string, string][],
  peringatan:
    "Where land burned and what condition it was in is not proof of who lit the fire. Permit boundaries date from around 2010–2012. The oil palm map ends in 2021. Fire starts hidden by cloud or smoke can be recorded as new fires.",
};

const Ctx = createContext<Bahasa>("id");

/** The words and number formatting for the film being rendered. */
const useT = () => {
  const t = useContext(Ctx) === "en" ? TEKS_EN : TEKS_ID;
  return {
    t,
    koma: (n: number, d = 1) => komaId(n, d, t.lokal),
    ribuan: (n: number) => ribuanId(n, t.lokal),
  };
};

/* ------------------------------ furniture ----------------------------- */

const Bkg: React.FC<{ sumber?: string; tampil?: number }> = ({ sumber, tampil }) => {
  const { t } = useT();
  return (
    <Bingkai kiri={t.kiri} waktu={t.waktu} labelSumber={t.labelSumber} sumber={sumber} tampil={tampil} />
  );
};

const Peta: React.FC<{ berkas: string; panjang: number; zoom?: number; redup?: number }> = ({
  berkas,
  panjang,
  zoom = 1.04,
  redup = 0,
}) => {
  const f = useCurrentFrame();
  const s = interpolate(f, [0, panjang], [1, zoom], { extrapolateRight: "clamp" });
  return (
    <AbsoluteFill style={{ backgroundColor: warna.jelaga, overflow: "hidden" }}>
      <Img
        src={staticFile(`telusur/${berkas}`)}
        style={{
          width: "100%",
          height: "100%",
          transform: `scale(${s})`,
          transformOrigin: "78% 55%",
          opacity: 1 - redup,
        }}
      />
      <AbsoluteFill
        style={{
          background: `linear-gradient(90deg, ${warna.jelaga} 0%, rgba(10,12,15,0.85) 30%, rgba(10,12,15,0) 48%)`,
        }}
      />
    </AbsoluteFill>
  );
};

const Alis: React.FC<{ anak: string }> = ({ anak }) => (
  <div
    style={{
      fontFamily: tubuhFont,
      fontSize: 21,
      fontWeight: 600,
      letterSpacing: "0.22em",
      textTransform: "uppercase",
      color: warna.bara,
    }}
  >
    {anak}
  </div>
);

const Legenda: React.FC<{ isi: [string, string, boolean?][]; tampil: number }> = ({ isi, tampil }) => (
  <div
    style={{
      display: "flex",
      flexDirection: "column",
      gap: 12,
      opacity: tampil,
      fontFamily: tubuhFont,
      fontSize: 23,
      color: warna.kapur,
    }}
  >
    {isi.map(([w, k, bulat]) => (
      <div key={k} style={{ display: "flex", alignItems: "center", gap: 14 }}>
        <div
          style={{
            width: bulat ? 16 : 26,
            height: bulat ? 16 : 18,
            background: w,
            borderRadius: bulat ? 8 : 2,
          }}
        />
        {k}
      </div>
    ))}
  </div>
);

const Catatan: React.FC<{ anak: string; tampil: number; lebar?: number }> = ({ anak, tampil, lebar = 700 }) => (
  <div
    style={{
      fontFamily: tubuhFont,
      fontSize: 21,
      color: warna.samar,
      lineHeight: 1.4,
      maxWidth: lebar,
      opacity: tampil,
    }}
  >
    {anak}
  </div>
);

const Angka: React.FC<{ anak: string; ukuran?: number; warnaA?: string }> = ({
  anak,
  ukuran = 150,
  warnaA = warna.nyala,
}) => (
  <div style={{ ...angkaGaya, fontSize: ukuran, fontWeight: 600, color: warnaA, lineHeight: 1 }}>{anak}</div>
);

/* ---------------------------------- scenes --------------------------- */

const KartuJudul: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { t, koma, ribuan } = useT();
  const f = useCurrentFrame();
  const a = masuk(f, 4, 24);
  return (
    <Lembut panjang={panjang}>
      <Peta berkas="peta_api.png" panjang={panjang} zoom={1.06} redup={0.35} />
      <Kolom jarak={26}>
        <div style={{ opacity: a, transform: `translateY(${(1 - a) * 20}px)` }}>
          <div style={{ marginBottom: 24 }}>
            <Alis anak={t.alisJudul} />
          </div>
          <h1
            style={{
              fontFamily: judulFont,
              fontWeight: 900,
              fontSize: 132,
              lineHeight: 0.92,
              letterSpacing: "-0.04em",
              color: warna.kapur,
              margin: 0,
            }}
          >
            {t.judul[0]}
            <br />
            {t.judul[1]}
          </h1>
          <div style={{ marginTop: 28 }}>
            <Keterangan lebar={760} anak={t.subJudul} />
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Kilas: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { t, koma, ribuan } = useT();
  const f = useCurrentFrame();
  const a = masuk(f, 4, 22);
  const b = masuk(f, Math.round(panjang * 0.45), 22);
  const besar: React.CSSProperties = {
    fontFamily: judulFont,
    fontWeight: 900,
    fontSize: 104,
    lineHeight: 1.02,
    letterSpacing: "-0.03em",
    margin: 0,
  };
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Kolom jarak={18}>
        <h1 style={{ ...besar, color: warna.abu, opacity: a }}>{t.kilas1}</h1>
        <h2
          style={{
            ...besar,
            color: warna.kapur,
            maxWidth: 1500,
            opacity: b,
            transform: `translateY(${(1 - b) * 18}px)`,
          }}
        >
          {t.kilas2}
        </h2>
      </Kolom>
    </Lembut>
  );
};

const Api: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { t, koma, ribuan } = useT();
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const urut = [...D.konsesi].sort((x, y) => y.dari_dalam_pct - x.dari_dalam_pct);
  return (
    <Lembut panjang={panjang}>
      <Peta berkas="peta_api.png" panjang={panjang} zoom={1.05} />
      <Bkg sumber={t.sumberApi} tampil={a} />
      <Kolom jarak={0}>
        <div style={{ opacity: a, width: 720 }}>
          <Alis anak={t.alisApi} />
          <div style={{ marginTop: 18 }}>
            <Penghitung ke={D.titik_awal_total} mulai={10} panjang={50} ukuran={120} lokal={t.lokal} />
          </div>
          <div style={{ fontFamily: tubuhFont, fontSize: 30, color: warna.kapur, marginTop: 6 }}>
            {t.titikAwal}
          </div>
          <div
            style={{
              marginTop: 34,
              fontFamily: tubuhFont,
              fontSize: 21,
              letterSpacing: "0.12em",
              textTransform: "uppercase",
              color: warna.abu,
              opacity: masuk(f, Math.round(panjang * 0.2), 20),
            }}
          >
            {t.dariDalam}
          </div>
          <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 10 }}>
            {urut.map((c, i) => {
              const n = masuk(f, Math.round(panjang * 0.22) + i * 14, 30);
              return (
                <div key={c.akronim} style={{ display: "flex", alignItems: "center", gap: 18, height: 40 }}>
                  <div style={{ width: 150, fontFamily: judulFont, fontWeight: 800, fontSize: 28, color: warna.kapur }}>
                    {c.akronim}
                  </div>
                  <div style={{ width: 380, height: 22, background: "#1B2029", borderRadius: 2 }}>
                    <div
                      style={{
                        width: `${c.dari_dalam_pct * n}%`,
                        height: "100%",
                        background: warna.bara,
                        borderRadius: 2,
                      }}
                    />
                  </div>
                  <div style={{ ...angkaGaya, fontSize: 28, fontWeight: 600, color: warna.nyala, opacity: n }}>
                    {koma(c.dari_dalam_pct * n, 0)}%
                  </div>
                </div>
              );
            })}
          </div>
          <div
            style={{
              marginTop: 30,
              borderLeft: `3px solid ${warna.bara}`,
              paddingLeft: 18,
              fontFamily: tubuhFont,
              fontSize: 26,
              color: warna.kapur,
              lineHeight: 1.35,
              opacity: masuk(f, Math.round(panjang * 0.72), 22),
            }}
          >
            {t.kepadatan(koma(D.rasio_titik_min), koma(D.rasio_titik_maks))}
          </div>
          <div style={{ marginTop: 26 }}>
            <Legenda
              isi={[
                [warna.nyala, t.legendaApi[0], true],
                [warna.abu, t.legendaApi[1], true],
              ]}
              tampil={masuk(f, 40, 20)}
            />
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Sawit: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { t, koma, ribuan } = useT();
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  return (
    <Lembut panjang={panjang}>
      <Peta berkas={t.planet} panjang={panjang} zoom={1.03} />
      <Bkg sumber={t.sumberSawit} tampil={a} />
      <Kolom jarak={0}>
        <div style={{ opacity: a, width: 640 }}>
          <Alis anak={t.alisSawit} />
          <div style={{ marginTop: 18 }}>
            <Angka anak={`${koma(D.sawit_pct * masuk(f, 14, 50))}%`} ukuran={170} />
          </div>
          <div style={{ fontFamily: tubuhFont, fontSize: 32, color: warna.kapur, marginTop: 8 }}>{t.sawit}</div>
          <div style={{ ...angkaGaya, fontSize: 26, color: warna.abu, marginTop: 10 }}>
            {t.sawitDari(ribuan(Math.round(D.sawit_ha / 10) * 10), ribuan(Math.round(D.terbakar_ha / 100) * 100))}
          </div>
          <div style={{ marginTop: 40 }}>
            <Catatan anak={t.sawitKet} tampil={masuk(f, Math.round(panjang * 0.45), 22)} lebar={600} />
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Penyiapan: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { t, koma, ribuan } = useT();
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const nilai = [D.jadi_sawit_2015.konsesi_lain, D.jadi_sawit_2015.empat, D.jadi_sawit_2015.luar_konsesi];
  const warnaB = [warna.nyala, warna.bara, "#3A424D"];
  const SKALA = 25;
  const LEBAR = 1000;
  const mulaiB = [Math.round(panjang * 0.2), Math.round(panjang * 0.45), Math.round(panjang * 0.5)];
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Bkg sumber={t.sumberSiap} tampil={a} />
      <Kolom jarak={0}>
        <div style={{ opacity: a, width: 1600 }}>
          <Judul anak={t.judulSiap} ukuran={58} />
          <div style={{ marginTop: 56, display: "flex", flexDirection: "column", gap: 22 }}>
            {t.barisSiap.map((k, i) => {
              const n = masuk(f, mulaiB[i], 34);
              return (
                <div key={k} style={{ display: "flex", alignItems: "center", height: 70 }}>
                  <div style={{ width: 420, fontFamily: tubuhFont, fontSize: 30, color: warna.kapur }}>{k}</div>
                  <div
                    style={{
                      width: Math.max((nilai[i] / SKALA) * LEBAR * n, 4),
                      height: 50,
                      background: warnaB[i],
                      borderRadius: "0 3px 3px 0",
                      opacity: n > 0 ? 1 : 0,
                    }}
                  />
                  <div style={{ ...angkaGaya, marginLeft: 24, fontSize: 44, fontWeight: 600, color: warna.kapur, opacity: n }}>
                    {koma(nilai[i] * n)}%
                  </div>
                </div>
              );
            })}
          </div>
          <div
            style={{
              marginTop: 54,
              borderLeft: `3px solid ${warna.bara}`,
              paddingLeft: 20,
              fontFamily: tubuhFont,
              fontSize: 29,
              color: warna.kapur,
              maxWidth: 1300,
              lineHeight: 1.4,
              opacity: masuk(f, Math.round(panjang * 0.72), 24),
            }}
          >
            {t.petak(`< ${koma(Math.ceil(D.petak_mkk_median_ha), 0)}`)}
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Izin: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { t, koma, ribuan } = useT();
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  return (
    <Lembut panjang={panjang}>
      <Peta berkas="peta_izin.png" panjang={panjang} zoom={1.05} />
      <Bkg sumber={t.sumberIzin} tampil={a} />
      <Kolom jarak={0}>
        <div style={{ opacity: a, width: 620 }}>
          <Alis anak="PT AM" />
          <div style={{ marginTop: 18 }}>
            <Angka anak={`${koma(D.am_hti_pct * masuk(f, 14, 50), 0)}%`} ukuran={170} />
          </div>
          <div style={{ fontFamily: tubuhFont, fontSize: 31, color: warna.kapur, marginTop: 8, lineHeight: 1.3 }}>
            {t.izin}
          </div>
          <div
            style={{
              marginTop: 30,
              fontFamily: tubuhFont,
              fontSize: 26,
              color: warna.abu,
              opacity: masuk(f, Math.round(panjang * 0.55), 22),
            }}
          >
            {t.izinBakar(koma(D.am_hti_bakar_pct, 0))}
          </div>
          <div style={{ marginTop: 40 }}>
            <Legenda
              isi={[
                [HTI, t.legendaIzin[0]],
                [warna.bara, t.legendaIzin[1]],
              ]}
              tampil={masuk(f, 40, 20)}
            />
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const GrafikDC: React.FC<{ f: number; mulai: number; panjang: number }> = ({ f, mulai, panjang }) => {
  const { t, koma, ribuan } = useT();
  const W = 1080;
  const H = 500;
  const L = 70;
  const B = 50;
  const MAX = 750;
  const x = (h: number) => L + ((h - 1) / 365) * (W - L - 10);
  const y = (v: number) => H - B - (v / MAX) * (H - B - 20);
  const seri = D.dc_seri as Record<string, { h: number; v: number }[]>;
  const gaya: Record<string, [string, number]> = {
    "2015": ["#59606B", 2.5],
    "2019": ["#8D96A1", 2.5],
    "2023": ["#3E454F", 2.5],
    "2026": [warna.bara, 5],
  };
  const jalur = (pts: { h: number; v: number }[], frac: number) => {
    const n = Math.max(2, Math.round(pts.length * frac));
    return pts
      .slice(0, n)
      .map((p, i) => `${i ? "L" : "M"}${x(p.h).toFixed(1)},${y(p.v).toFixed(1)}`)
      .join(" ");
  };
  const lain = masuk(f, mulai, 30);
  const kini = masuk(f, mulai + 30, panjang);
  return (
    <svg width={W} height={H}>
      {[0, 250, 500, 750].map((v) => (
        <g key={v}>
          <line x1={L} x2={W - 10} y1={y(v)} y2={y(v)} stroke={warna.garis} strokeWidth={1} />
          <text x={L - 12} y={y(v) + 7} fill={warna.samar} fontSize={20} textAnchor="end" fontFamily={tubuhFont}>
            {v}
          </text>
        </g>
      ))}
      <line
        x1={L}
        x2={W - 10}
        y1={y(D.dc_ekstrem)}
        y2={y(D.dc_ekstrem)}
        stroke="#E03131"
        strokeWidth={2}
        strokeDasharray="8 7"
      />
      <text x={L + 8} y={y(D.dc_ekstrem) - 10} fill="#E03131" fontSize={20} fontFamily={tubuhFont}>
        {t.ekstrem} ({D.dc_ekstrem})
      </text>
      {t.bulan.map((m, i) => (
        <text
          key={m}
          x={x(i * 30.4 + 15)}
          y={H - 16}
          fill={warna.samar}
          fontSize={19}
          textAnchor="middle"
          fontFamily={tubuhFont}
        >
          {m}
        </text>
      ))}
      {["2023", "2015", "2019"].map((k) => (
        <path key={k} d={jalur(seri[k], lain)} fill="none" stroke={gaya[k][0]} strokeWidth={gaya[k][1]} />
      ))}
      <path d={jalur(seri["2026"], kini)} fill="none" stroke={gaya["2026"][0]} strokeWidth={gaya["2026"][1]} />
      {(["2015", "2019", "2023"] as const).map((k) => {
        const p = seri[k].reduce((m, q) => (q.v > m.v ? q : m), seri[k][0]);
        return (
          <text
            key={k}
            x={x(p.h) + 10}
            y={y(p.v) - 8}
            fill={gaya[k][0] === "#3E454F" ? warna.samar : gaya[k][0]}
            fontSize={21}
            fontFamily={tubuhFont}
            opacity={lain}
          >
            {k}
          </text>
        );
      })}
      {(() => {
        const p = seri["2026"].reduce((m, q) => (q.v > m.v ? q : m), seri["2026"][0]);
        return (
          <text
            x={x(p.h) - 10}
            y={y(p.v) - 14}
            fill={warna.nyala}
            fontSize={26}
            fontWeight={600}
            textAnchor="end"
            fontFamily={tubuhFont}
            opacity={masuk(f, mulai + 30 + panjang - 10, 20)}
          >
            2026 · {ribuan(D.dc_puncak["2026"])}
          </text>
        );
      })()}
    </svg>
  );
};

const Kemarau: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { t, koma, ribuan } = useT();
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const h = D.hujan_jul_sep;
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Bkg sumber={t.sumberKemarau} tampil={a} />
      <Kolom jarak={0}>
        <div style={{ opacity: a, display: "flex", gap: 60, alignItems: "flex-start" }}>
          <div style={{ width: 420 }}>
            <Alis anak={t.alisKemarau} />
            <div style={{ marginTop: 22, display: "flex", alignItems: "baseline", gap: 12 }}>
              <Angka anak={ribuan(h["2026"] * masuk(f, 20, 40))} ukuran={150} />
              <div style={{ ...angkaGaya, fontSize: 48, color: warna.nyala }}>mm</div>
            </div>
            <div style={{ fontFamily: tubuhFont, fontSize: 28, color: warna.kapur, marginTop: 8, lineHeight: 1.3 }}>
              {t.hujan}
            </div>
            <div
              style={{ ...angkaGaya, fontSize: 24, color: warna.abu, marginTop: 16, opacity: masuk(f, 60, 20) }}
            >
              {t.hujanLain(ribuan(h["2019"]), ribuan(h["2015"]))}
            </div>
          </div>
          <div style={{ opacity: masuk(f, Math.round(panjang * 0.3), 20) }}>
            <div style={{ fontFamily: tubuhFont, fontSize: 24, color: warna.abu, marginBottom: 10, marginLeft: 70 }}>
              {t.judulDC}
            </div>
            <GrafikDC f={f} mulai={Math.round(panjang * 0.3)} panjang={Math.round(panjang * 0.4)} />
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Gambut: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { t, koma, ribuan } = useT();
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const SKALA = 65;
  return (
    <Lembut panjang={panjang}>
      <Peta berkas="peta_gambut.png" panjang={panjang} zoom={1.05} />
      <Bkg sumber={t.sumberGambut} tampil={a} />
      <Kolom jarak={0}>
        <div style={{ opacity: a, width: 720 }}>
          <Angka anak={`${koma(D.gambut_pct * masuk(f, 10, 45), 0)}%`} ukuran={150} />
          <div style={{ fontFamily: tubuhFont, fontSize: 30, color: warna.kapur, marginTop: 6 }}>{t.gambut}</div>
          <div
            style={{
              marginTop: 40,
              fontFamily: tubuhFont,
              fontSize: 21,
              letterSpacing: "0.12em",
              textTransform: "uppercase",
              color: warna.abu,
              opacity: masuk(f, Math.round(panjang * 0.35), 20),
            }}
          >
            {t.gambutBaris}
          </div>
          <div style={{ marginTop: 14, display: "flex", flexDirection: "column", gap: 14 }}>
            {D.gambut_dalam_luar.map((c, i) => {
              const n = masuk(f, Math.round(panjang * 0.38) + i * 10, 28);
              return (
                <div key={c.akronim} style={{ display: "flex", alignItems: "center", gap: 14 }}>
                  <div style={{ width: 130, fontFamily: judulFont, fontWeight: 800, fontSize: 26, color: warna.kapur }}>
                    {c.akronim}
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    {[
                      [c.dalam, warna.bara],
                      [c.luar, "#4A515C"],
                    ].map(([v, w], j) => (
                      <div key={j} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        <div
                          style={{
                            width: ((v as number) / SKALA) * 380 * n,
                            height: 16,
                            background: w as string,
                            borderRadius: 2,
                          }}
                        />
                        <div style={{ ...angkaGaya, fontSize: 20, color: j ? warna.abu : warna.nyala, opacity: n }}>
                          {koma(v as number, 0)}% {t.dalamLuar[j]}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
          <div style={{ marginTop: 30 }}>
            <Legenda
              isi={[
                [warna.gambut, t.legendaGambut[0]],
                [warna.bara, t.legendaGambut[1]],
              ]}
              tampil={masuk(f, 30, 20)}
            />
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Setara: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { t, koma, ribuan } = useT();
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const S = D.setara;
  const SKALA = 2.8;
  const LEBAR = 900;
  const n1 = masuk(f, 20, 30);
  const n2 = masuk(f, Math.round(panjang * 0.32), 40);
  const bar = (v: number, n: number, w: string, label: string) => (
    <div style={{ display: "flex", alignItems: "center", height: 84 }}>
      <div style={{ width: 360, fontFamily: tubuhFont, fontSize: 29, color: warna.kapur }}>{label}</div>
      <div style={{ width: (v / SKALA) * LEBAR * n, height: 56, background: w, borderRadius: "0 3px 3px 0" }} />
      <div style={{ ...angkaGaya, marginLeft: 24, fontSize: 52, fontWeight: 600, color: warna.kapur, opacity: n }}>
        {koma(v * n)}×
      </div>
    </div>
  );
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Bkg sumber={t.sumberSetara} tampil={a} />
      <Kolom jarak={0}>
        <div style={{ opacity: a, width: 1620 }}>
          <Judul anak={t.judulSetara} ukuran={60} />
          <div style={{ marginTop: 44 }}>
            {bar(S.mentah, n1, "#3A424D", t.mentah)}
            {bar(S.setara, n2, warna.bara, t.setara)}
          </div>
          <div style={{ ...angkaGaya, fontSize: 22, color: warna.abu, marginLeft: 360, opacity: n2 }}>
            {t.ci(koma(S.setara_ci[0]), koma(S.setara_ci[1]))}
          </div>
          <div style={{ marginTop: 18, maxWidth: 1400 }}>
            <Catatan anak={t.setaraKet} tampil={n2} lebar={1400} />
          </div>
          <div style={{ display: "flex", gap: 90, marginTop: 44 }}>
            {[
              [S.hutan, t.hutan],
              [S.lama, t.lama],
            ].map(([v, k], i) => (
              <div
                key={k as string}
                style={{
                  borderTop: `3px solid ${warna.bara}`,
                  paddingTop: 14,
                  opacity: masuk(f, Math.round(panjang * (0.58 + i * 0.08)), 22),
                }}
              >
                <Angka anak={`${koma(v as number)}×`} ukuran={72} />
                <div style={{ fontFamily: tubuhFont, fontSize: 26, color: warna.kapur, marginTop: 6 }}>{k}</div>
              </div>
            ))}
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Tutup: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { t, koma, ribuan } = useT();
  const f = useCurrentFrame();
  const a = masuk(f, 4, 22);
  const b = masuk(f, Math.round(panjang * 0.3), 24);
  const c = masuk(f, Math.round(panjang * 0.58), 24);
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Kolom jarak={28}>
        <h1
          style={{
            fontFamily: judulFont,
            fontWeight: 900,
            fontSize: 88,
            lineHeight: 1.04,
            letterSpacing: "-0.03em",
            color: warna.kapur,
            margin: 0,
            opacity: a,
          }}
        >
          {t.tutup1}
        </h1>
        <div style={{ opacity: a, maxWidth: 1300 }}>
          <Keterangan lebar={1300} anak={t.tutupKet} />
        </div>
        <h2
          style={{
            fontFamily: judulFont,
            fontWeight: 900,
            fontSize: 62,
            lineHeight: 1.1,
            letterSpacing: "-0.02em",
            color: warna.bara,
            margin: 0,
            maxWidth: 1500,
            opacity: b,
            transform: `translateY(${(1 - b) * 18}px)`,
          }}
        >
          {t.tutup2}
        </h2>
        <div
          style={{
            opacity: c,
            borderLeft: `3px solid ${warna.garis}`,
            paddingLeft: 20,
            fontFamily: tubuhFont,
            fontSize: 26,
            color: warna.abu,
            lineHeight: 1.45,
            maxWidth: 1400,
          }}
        >
          {t.tutup3}
        </div>
      </Kolom>
    </Lembut>
  );
};

const KartuSumber: React.FC<{ panjang: number }> = () => {
  const { t, koma, ribuan } = useT();
  const f = useCurrentFrame();
  const a = masuk(f, 4, 20);
  return (
    <AbsoluteFill style={{ backgroundColor: warna.jelaga, opacity: a }}>
      <Kolom jarak={18}>
        <Alis anak={t.sumberData} />
        <div style={{ display: "flex", flexDirection: "column", gap: 11, width: 1620 }}>
          {t.baris.map(([k, v]) => (
            <div key={k} style={{ display: "flex", gap: 28, alignItems: "baseline" }}>
              <div style={{ width: 200, fontFamily: tubuhFont, fontSize: 24, fontWeight: 600, color: warna.kapur }}>{k}</div>
              <div style={{ fontFamily: tubuhFont, fontSize: 24, color: warna.abu }}>{v}</div>
            </div>
          ))}
        </div>
        <div
          style={{
            marginTop: 12,
            paddingTop: 16,
            borderTop: `2px solid ${warna.bara}`,
            fontFamily: tubuhFont,
            fontSize: 22,
            color: warna.kapur,
            lineHeight: 1.5,
            maxWidth: 1620,
          }}
        >
          {t.peringatan}
        </div>
      </Kolom>
    </AbsoluteFill>
  );
};

/* --------------------------------- film ------------------------------ */

const ADEGAN: Record<string, React.FC<{ panjang: number }>> = {
  "01-kilas": Kilas,
  "02-api": Api,
  "03-sawit": Sawit,
  "04-penyiapan": Penyiapan,
  "05-izin": Izin,
  "06-kemarau": Kemarau,
  "07-gambut": Gambut,
  "08-setara": Setara,
  "09-tutup": Tutup,
};

export const Telusur: React.FC<{ bahasa?: Bahasa }> = ({ bahasa = "id" }) => {
  const J = JADWAL_TELUSUR[bahasa];
  const t = bahasa === "en" ? TEKS_EN : TEKS_ID;
  return (
    <Ctx.Provider value={bahasa}>
      <AbsoluteFill style={{ backgroundColor: warna.jelaga }}>
        <Audio src={staticFile(`${t.audio}/${t.musik}`)} />
        <Sequence durationInFrames={J.JUDUL_FRAME}>
          <KartuJudul panjang={J.JUDUL_FRAME} />
        </Sequence>
        {J.adegan.map((a) => {
          const K = ADEGAN[a.id];
          return (
            <Sequence key={a.id} from={a.mulai} durationInFrames={a.panjang}>
              <K panjang={a.panjang} />
              <Audio src={staticFile(`${t.audio}/${a.id}.mp3`)} />
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
