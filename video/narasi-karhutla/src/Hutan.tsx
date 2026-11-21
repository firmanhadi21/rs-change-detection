/**
 * "Apa yang Menggerus Hutan Maluku Utara?" / "What Is Clearing North Maluku's Forests?"
 * A standalone film, plus the infographic still (Infografis) built from the same figures.
 *
 *   province     302,686 ha tree-cover loss 2001-2025 (9.8% of 2000), 60% primary
 *   by year      peak 2015 (El Niño), 6-14 kha/yr since 2017
 *   drivers      WRI/Google 1 km classes: agriculture, shifting, logging, fire; mining 4%
 *   mining       383 -> 896 ha/yr (2001-18 vs 2019-24), share 2.9% -> 10.1%
 *   Weda Bay     Landsat timelapse 2000-2026; open ground 1,575 -> 8,046 ha (2019 -> 2026)
 *   Sagea Lake   close-up; open ground within 1 km of shore 16 -> 61 ha (2025 -> 2026)
 *
 * Same palette, type and audio pipeline as Pulau.tsx. Every figure is from hutanData.json
 * (scripts/malut_film_assets.py). No company is named.
 */

import React, { createContext, useContext } from "react";
import { AbsoluteFill, Audio, Img, interpolate, Sequence, staticFile, useCurrentFrame } from "remotion";
import { JADWAL_HUTAN } from "./jadwalHutan";
import type { Bahasa } from "./jadwalKonsesi";
import { Bingkai, Judul, Keterangan, Kolom, LatarDiam, Lembut, masuk } from "./komponen";
import { angkaGaya, judulFont, koma as komaL, ribuan as ribuanL, tubuhFont, warna } from "./teema";
import D from "./hutanData.json";

const HIJAU = "#3E7A55";
const ABU_GELAP = "#3A424D";

const TEKS_ID = {
  lokal: "id-ID",
  audio: "audio/hutan",
  musik: "musik-hutan.mp3",
  labelSumber: "Sumber",
  kiri: "Hutan Maluku Utara",
  waktu: "November 2026",
  alisJudul: "Analisis citra satelit 2000–2026",
  judul: ["APA YANG", "MENGGERUS HUTAN", "MALUKU UTARA?"],
  subJudul: "Dua puluh lima tahun kehilangan tutupan pohon, pemicunya, dan tambang nikel di Teluk Weda dan Danau Sagea.",
  ha: "ha",
  sumberPeta: "Hansen dkk. Global Forest Change v1.13 (tutupan pohon ≥ 30% pada 2000) · hutan primer: Turubanova dkk. 2018 · batas: FAO GAUL 2025",
  alisBuka: "Tutupan pohon hilang, 2001–2025",
  hilang: "hektare hilang",
  dariTutupan: (p: string) => `${p} dari tutupan pohon tahun 2000`,
  primer: (n: string) => `${n} ha di antaranya hutan primer`,
  legenda: [["2001–2010", "#9AA3AD"], ["2011–2020", warna.nyala], ["2021–2025", warna.bara]] as [string, string][],
  judulTahun: "Tutupan pohon hilang per tahun",
  elNino: "El Niño",
  sumberTahun: "Hansen dkk. Global Forest Change v1.13, tutupan pohon ≥ 30% pada 2000, seluruh Provinsi Maluku Utara",
  judulPemicu: "Pemicu utama kehilangan, 2001–2024",
  pemicu: {
    "Permanent agriculture": "Pertanian dan perkebunan menetap",
    "Shifting cultivation": "Ladang berpindah",
    Logging: "Penebangan kayu",
    Wildfire: "Kebakaran",
    "Hard commodities (mining, energy)": "Tambang dan energi",
    "Settlements & infrastructure": "Permukiman dan infrastruktur",
    "Other natural disturbances": "Gangguan alam lain",
  } as Record<string, string>,
  sumberPemicu: "WRI/Google Drivers of Forest Loss v1.2 (Sims dkk. 2025), pemicu dominan per sel 1 km, 2001–2024, dikalikan kehilangan Hansen 30 m",
  judulTambang: "Kehilangan di wilayah tambang, per tahun",
  rata: (a: string, b: string) => [`${a} ha/tahun`, `${b} ha/tahun`],
  periode: ["2001–2018", "2019–2024"],
  bagian: (a: string, b: string) => `Bagian dari seluruh kehilangan: ${a} → ${b}`,
  kabTambang: "Terbanyak di wilayah tambang:",
  sumberTambang: "Sel 1 km yang pemicu dominannya tambang/energi (WRI/Google v1.2); tahun dari Hansen GFC v1.13",
  alisWeda: "Teluk Weda, Halmahera Tengah",
  lahanTerbuka: "Lahan terbuka (tanah gundul + bangunan)",
  catatanWeda:
    "Hitungan mentah Dynamic World untuk seluruh kotak, termasuk kawasan industri. Setelah dicek dengan label, lahan terbuka di inti Teluk Weda (area lebih kecil) sekitar 4.500 ha pada 2025 — lihat film “Memeriksa Peta Tambang Nikel”.",
  sumberWeda: "Citra: Landsat 5/7/8/9 (USGS), komposit median 2 tahun berakhir pada tahun tertera · lahan terbuka: Dynamic World, modus tahunan, 2026 = Jan–Nov · kotak 55 × 50 km",
  alisSagea: "Danau Sagea, Halmahera Tengah",
  danau: "Danau Sagea",
  dalam1km: "Lahan terbuka dalam 1 km dari tepi danau",
  terdekat: (m: string) => `Tepi bukaan terdekat: ± ${m} m dari air`,
  keruh: "Warga melaporkan Sungai Sagea keruh hampir dua bulan pada 2023 dan mengaitkannya dengan tambang di hulu (Mongabay Indonesia).",
  sumberSagea: "Citra: Landsat (2000–2018), Sentinel-2 L2A Cloud Score+ (2019–2026), komposit tahunan · lahan terbuka: Dynamic World · danau: Sentinel-2 MNDWI, ± 152 ha",
  tutup1: "Apa yang menggerus hutan Maluku Utara?",
  tutup2: "Terutama pertanian, ladang, penebangan, dan kebakaran.",
  tutup3: "Tetapi tambang nikel tumbuh paling cepat, dan bekasnya paling terpusat: Teluk Weda, dan kini tepi Danau Sagea.",
  tutupCatat: "Analisis citra satelit, belum diperiksa di lapangan dan belum ditelaah sejawat. Kehilangan tutupan pohon termasuk kebun dan hutan tanaman; pemicu dipetakan per kilometer persegi.",
  sumberData: "Sumber data",
  barisSumber: [
    ["Tutupan pohon", "Hansen dkk., Global Forest Change v1.13 (UMD/Google), 2001–2025"],
    ["Hutan primer", "Turubanova dkk. 2018, hutan primer tropis lembap 2001"],
    ["Pemicu", "WRI/Google, Drivers of Forest Loss 1 km v1.2, 2001–2024"],
    ["Lahan terbuka", "Google/WRI Dynamic World v1, Sentinel-2, 2016–2026"],
    ["Citra", "Landsat 5/7/8/9 C2 L2 (USGS); Sentinel-2 L2A (Copernicus), Cloud Score+"],
    ["Batas", "FAO GAUL 2025; danau Sagea: OpenStreetMap dan Sentinel-2"],
    ["Liputan", "Mongabay Indonesia (2022–2026), Sungai Sagea dan tambang nikel"],
  ],
  peringatan: "Pemicu adalah klasifikasi model per kilometer persegi, bukan bukti pelaku. Angka satelit dapat berbeda dari data resmi. Tidak ada perusahaan yang disebut.",
  judulHal2: "Tambang nikel: bagian kecil, tumbuh paling cepat",
};

type Teks = typeof TEKS_ID;

const TEKS_EN: Teks = {
  ...TEKS_ID,
  lokal: "en-GB",
  audio: "audio/hutan-en",
  musik: "musik-hutan-en.mp3",
  labelSumber: "Source",
  kiri: "North Maluku forests",
  alisJudul: "A satellite analysis, 2000–2026",
  judul: ["WHAT IS", "CLEARING NORTH", "MALUKU'S FORESTS?"],
  subJudul: "Twenty-five years of tree-cover loss, what drives it, and nickel mining at Weda Bay and Sagea Lake.",
  sumberPeta: "Hansen et al. Global Forest Change v1.13 (tree cover ≥ 30% in 2000) · primary forest: Turubanova et al. 2018 · boundaries: FAO GAUL 2025",
  alisBuka: "Tree cover lost, 2001–2025",
  hilang: "hectares lost",
  dariTutupan: (p: string) => `${p} of the tree cover of 2000`,
  primer: (n: string) => `${n} ha of it primary forest`,
  judulTahun: "Tree cover lost each year",
  sumberTahun: "Hansen et al. Global Forest Change v1.13, tree cover ≥ 30% in 2000, all of North Maluku province",
  judulPemicu: "Main driver of loss, 2001–2024",
  pemicu: {
    "Permanent agriculture": "Permanent farming and plantations",
    "Shifting cultivation": "Shifting cultivation",
    Logging: "Logging",
    Wildfire: "Fire",
    "Hard commodities (mining, energy)": "Mining and energy",
    "Settlements & infrastructure": "Settlements and infrastructure",
    "Other natural disturbances": "Other natural disturbance",
  },
  sumberPemicu: "WRI/Google Drivers of Forest Loss v1.2 (Sims et al. 2025), dominant driver per 1 km cell, 2001–2024, applied to Hansen 30 m loss",
  judulTambang: "Loss in mining areas, each year",
  rata: (a: string, b: string) => [`${a} ha/yr`, `${b} ha/yr`],
  bagian: (a: string, b: string) => `Share of all loss: ${a} → ${b}`,
  kabTambang: "Most mining-area loss:",
  sumberTambang: "1 km cells whose dominant driver is mining/energy (WRI/Google v1.2); year of loss from Hansen GFC v1.13",
  alisWeda: "Weda Bay, Central Halmahera",
  lahanTerbuka: "Open ground (bare earth + buildings)",
  catatanWeda:
    "Raw Dynamic World count for the whole box, industrial park included. Checked against hand labels, open ground in the Weda Bay core (a smaller area) was about 4,500 ha in 2025 — see the follow-up film “Memeriksa Peta Tambang Nikel”.",
  sumberWeda: "Imagery: Landsat 5/7/8/9 (USGS), 2-year median ending in the year shown · open ground: Dynamic World annual mode, 2026 = Jan–Nov · box 55 × 50 km",
  alisSagea: "Sagea Lake, Central Halmahera",
  danau: "Sagea Lake",
  dalam1km: "Open ground within 1 km of the lake shore",
  terdekat: (m: string) => `Nearest clearing edge: about ${m} m from the water`,
  keruh: "Residents reported the Sagea river running muddy for almost two months in 2023 and link it to mining upstream (Mongabay Indonesia).",
  sumberSagea: "Imagery: Landsat (2000–2018), Sentinel-2 L2A Cloud Score+ (2019–2026), annual composites · open ground: Dynamic World · lake: Sentinel-2 MNDWI, about 152 ha",
  tutup1: "What is clearing North Maluku's forests?",
  tutup2: "Mostly farming, shifting cultivation, logging and fire.",
  tutup3: "But nickel mining is growing fastest, and its footprint is the most concentrated: Weda Bay, and now the edge of Sagea Lake.",
  tutupCatat: "A satellite analysis, not yet checked on the ground or peer reviewed. Tree-cover loss includes plantations and tree crops; drivers are mapped per square kilometre.",
  sumberData: "Data sources",
  barisSumber: [
    ["Tree cover", "Hansen et al., Global Forest Change v1.13 (UMD/Google), 2001–2025"],
    ["Primary forest", "Turubanova et al. 2018, humid tropical primary forest 2001"],
    ["Drivers", "WRI/Google, Drivers of Forest Loss 1 km v1.2, 2001–2024"],
    ["Open ground", "Google/WRI Dynamic World v1, Sentinel-2, 2016–2026"],
    ["Imagery", "Landsat 5/7/8/9 C2 L2 (USGS); Sentinel-2 L2A (Copernicus), Cloud Score+"],
    ["Boundaries", "FAO GAUL 2025; Sagea Lake: OpenStreetMap and Sentinel-2"],
    ["Reporting", "Mongabay Indonesia (2022–2026), Sagea river and nickel mining"],
  ],
  peringatan: "Drivers are a per-square-kilometre model classification, not proof of who cleared. Satellite figures may differ from official statistics. No company is named.",
  judulHal2: "Nickel mining: a small share, growing fastest",
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
      <Img src={staticFile("hutan/peta_provinsi.jpg")} style={{ width: "100%", height: "100%", transform: `scale(${0.86 * s})`, transformOrigin: "96% 58%", opacity: 1 - redup }} />
    </AbsoluteFill>
  );
};

/** Annual frames on the right of the frame, crossfading; the year in large type. */
const Selang: React.FC<{ folder: string; tahun: number[]; panjang: number; akhir?: number; penanda?: React.ReactNode }> = ({
  folder,
  tahun,
  panjang,
  akhir = 0.72,
  penanda,
}) => {
  const f = useCurrentFrame();
  const t0 = Math.round(panjang * 0.06);
  const t1 = Math.round(panjang * akhir);
  const pos = interpolate(f, [t0, t1], [0, tahun.length - 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const i = Math.floor(pos);
  const frac = pos - i;
  const tahunIni = tahun[Math.min(tahun.length - 1, Math.round(pos))];
  return (
    <AbsoluteFill style={{ backgroundColor: warna.jelaga }}>
      <div style={{ position: "absolute", left: 720, top: 0, width: 1200, height: 1080, overflow: "hidden" }}>
        <Img src={staticFile(`hutan/${folder}/${tahun[i]}.jpg`)} style={{ position: "absolute", width: 1200, height: 1080, objectFit: "cover" }} />
        {i + 1 < tahun.length ? (
          <Img src={staticFile(`hutan/${folder}/${tahun[i + 1]}.jpg`)} style={{ position: "absolute", width: 1200, height: 1080, objectFit: "cover", opacity: frac }} />
        ) : null}
        {penanda}
      </div>
      <AbsoluteFill style={{ background: `linear-gradient(90deg, ${warna.jelaga} 0%, ${warna.jelaga} 37%, rgba(10,12,15,0) 50%)` }} />
      <div style={{ position: "absolute", right: 70, bottom: 120, ...angkaGaya, fontSize: 96, fontWeight: 600, color: warna.kapur, textShadow: "0 2px 18px rgba(0,0,0,0.8)" }}>
        {tahunIni}
      </div>
    </AbsoluteFill>
  );
};

/** Small vertical bar chart: years along the bottom, value on top of the last bar. */
const BatangTahun: React.FC<{ tahun: (number | string)[]; nilai: number[]; tampil: (i: number) => number; sorot?: (i: number) => boolean; W?: number; H?: number; label?: (i: number) => string | null }> = ({
  tahun,
  nilai,
  tampil,
  sorot = () => false,
  W = 1100,
  H = 420,
  label = () => null,
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
              <text x={i * bw + bw / 2} y={H - h + 18} fill={s ? warna.bara : warna.abu} fontSize={22} textAnchor="middle" fontFamily={angkaGaya.fontFamily as string} fontWeight={600}>
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
  const { T, koma, ribuan } = useT();
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const b = masuk(f, Math.round(panjang * 0.4), 22);
  const c = masuk(f, Math.round(panjang * 0.7), 22);
  const nilai = interpolate(f, [10, 70], [0, D.loss_total], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <Lembut panjang={panjang}>
      <Peta panjang={panjang} />
      <Bkg sumber={T.sumberPeta} tampil={a} />
      <Kolom jarak={0}>
        <div style={{ width: 760, opacity: a }}>
          <Alis anak={T.alisBuka} />
          <div style={{ marginTop: 14 }}>
            <Angka anak={ribuan(nilai)} ukuran={140} />
          </div>
          <div style={{ fontFamily: tubuhFont, fontSize: 28, color: warna.kapur, marginTop: 6 }}>{T.hilang}</div>
          <div style={{ marginTop: 34, opacity: b }}>
            <Garis anak={T.dariTutupan(`${koma(D.loss_pct, 1)}%`)} tampil={b} />
          </div>
          <div style={{ marginTop: 18 }}>
            <Garis anak={T.primer(ribuan(D.loss_primary))} tampil={c} />
          </div>
          <div style={{ display: "flex", gap: 26, marginTop: 44, opacity: a }}>
            {T.legenda.map(([k, w]) => (
              <div key={k} style={{ display: "flex", alignItems: "center", gap: 10, fontFamily: tubuhFont, fontSize: 21, color: warna.abu }}>
                <div style={{ width: 18, height: 18, background: w }} />
                {k}
              </div>
            ))}
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Tahun: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { T, ribuan } = useT();
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const pk = D.tahun.indexOf(D.puncak.tahun);
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Bkg sumber={T.sumberTahun} tampil={a} />
      <Kolom jarak={30}>
        <div style={{ opacity: a }}>
          <Judul anak={T.judulTahun} ukuran={58} />
        </div>
        <BatangTahun
          tahun={D.tahun}
          nilai={D.loss_tahun}
          W={1600}
          H={480}
          tampil={(i) => masuk(f, Math.round(panjang * 0.08) + i * 4, 18)}
          sorot={(i) => i === pk}
          label={(i) => (i === pk ? `${ribuan(D.puncak.ha)} ha · ${T.elNino}` : null)}
        />
      </Kolom>
    </Lembut>
  );
};

const Pemicu: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { T, koma } = useT();
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const lebar = 760;
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Bkg sumber={T.sumberPemicu} tampil={a} />
      <Kolom jarak={22}>
        <div style={{ opacity: a, marginBottom: 12 }}>
          <Judul anak={T.judulPemicu} ukuran={58} />
        </div>
        {D.drivers.slice(0, 6).map((d, i) => {
          const o = masuk(f, Math.round(panjang * 0.2) + i * 12, 24);
          const tambang = d.k.startsWith("Hard");
          const w = tambang ? warna.bara : i < 4 ? warna.abu : ABU_GELAP;
          return (
            <div key={d.k} style={{ display: "flex", alignItems: "center", gap: 24 }}>
              <div style={{ width: 520, fontFamily: tubuhFont, fontSize: 28, color: tambang ? warna.bara : warna.kapur, fontWeight: tambang ? 600 : 400 }}>{T.pemicu[d.k]}</div>
              <div style={{ width: lebar, height: 38, background: warna.arang }}>
                <div style={{ width: (lebar * d.pct * o) / 40, height: 38, background: w }} />
              </div>
              <div style={{ ...angkaGaya, fontSize: 36, fontWeight: 600, color: w, opacity: o, width: 150 }}>{koma(d.pct, 1)}%</div>
            </div>
          );
        })}
      </Kolom>
    </Lembut>
  );
};

const Tambang: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { T, koma, ribuan } = useT();
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const b = masuk(f, Math.round(panjang * 0.35), 22);
  const c = masuk(f, Math.round(panjang * 0.7), 22);
  const M = D.mining;
  const tahun = D.tahun.slice(0, 24);
  const [r1, r2] = T.rata(ribuan(M.early_per_yr), ribuan(M.late_per_yr));
  const top = D.kabupaten.slice().sort((x, y) => y.mining - x.mining).slice(0, 3);
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Bkg sumber={T.sumberTambang} tampil={a} />
      <Kolom jarak={26}>
        <div style={{ opacity: a }}>
          <Judul anak={T.judulTambang} ukuran={56} />
        </div>
        <div style={{ display: "flex", gap: 70, alignItems: "flex-end" }}>
          <BatangTahun
            tahun={tahun}
            nilai={D.mining_year}
            W={1050}
            H={400}
            tampil={(i) => masuk(f, Math.round(panjang * 0.06) + i * 4, 18)}
            sorot={(i) => tahun[i] >= 2019}
            label={(i) => (tahun[i] === M.peak_year ? ribuan(M.peak_ha) : null)}
          />
          <div style={{ marginBottom: 60 }}>
            {[0, 1].map((k) => (
              <div key={k} style={{ marginTop: k ? 30 : 0, opacity: k ? b : a }}>
                <div style={{ fontFamily: tubuhFont, fontSize: 22, color: warna.abu }}>{T.periode[k]}</div>
                <Angka anak={k ? r2 : r1} ukuran={54} warnaA={k ? warna.bara : warna.abu} />
              </div>
            ))}
            <div style={{ marginTop: 30 }}>
              <Garis anak={T.bagian(`${koma(M.early_share_pct, 1)}%`, `${koma(M.late_share_pct, 1)}%`)} tampil={b} lebar={480} />
            </div>
          </div>
        </div>
        <div style={{ display: "flex", gap: 34, alignItems: "baseline", opacity: c, fontFamily: tubuhFont, fontSize: 25 }}>
          <span style={{ color: warna.abu }}>{T.kabTambang}</span>
          {top.map((k) => (
            <span key={k.nama} style={{ color: warna.kapur }}>
              {k.nama} <span style={{ ...angkaGaya, color: warna.nyala }}>{ribuan(k.mining)} ha</span>
            </span>
          ))}
        </div>
      </Kolom>
    </Lembut>
  );
};

const OG_TAHUN = [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026];

const Weda: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { T, ribuan } = useT();
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const tahun = Array.from({ length: 27 }, (_, i) => 2000 + i);
  const og = D.open_ground.weda as Record<string, number>;
  const nilai = OG_TAHUN.map((y) => og[String(y)]);
  // bars follow the timelapse clock: a year's bar appears when the frame reaches it
  const t0 = Math.round(panjang * 0.06), t1 = Math.round(panjang * 0.72);
  const jam = (y: number) => t0 + ((y - 2000) / 26) * (t1 - t0);
  return (
    <Lembut panjang={panjang}>
      <Selang folder="weda" tahun={tahun} panjang={panjang} />
      <Bkg sumber={T.sumberWeda} tampil={a} />
      <Kolom jarak={0}>
        <div style={{ width: 640, opacity: a }}>
          <Alis anak={T.alisWeda} />
          <div style={{ fontFamily: tubuhFont, fontSize: 26, color: warna.kapur, marginTop: 26, marginBottom: 6 }}>{T.lahanTerbuka}</div>
          <BatangTahun
            tahun={OG_TAHUN}
            nilai={nilai}
            W={620}
            H={300}
            tampil={(i) => masuk(f, jam(OG_TAHUN[i]), 14)}
            sorot={(i) => OG_TAHUN[i] >= 2019}
            label={(i) => (OG_TAHUN[i] === 2019 || OG_TAHUN[i] === 2026 ? `${ribuan(nilai[i])}` : null)}
          />
          <div style={{ fontFamily: tubuhFont, fontSize: 20, color: warna.samar }}>{T.ha}</div>
          <div style={{ marginTop: 22 }}>
            <Garis anak={T.catatanWeda} tampil={masuk(f, Math.round(panjang * 0.74), 22)} lebar={620} ukuran={21} />
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const SAGEA_TAHUN = [2000, 2005, 2010, 2013, 2015, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026];

const Sagea: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { T, ribuan, koma } = useT();
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const c = masuk(f, Math.round(panjang * 0.62), 22);
  const d = masuk(f, Math.round(panjang * 0.78), 22);
  const w1 = D.sagea.within_1km as Record<string, number>;
  const nilai = OG_TAHUN.map((y) => w1[String(y)]);
  // lake centre in the 1200x1080 close-up: box 128.02-128.12 E, 0.44-0.53 N
  const lx = ((128.0684 - 128.02) / 0.1) * 1200;
  const ly = ((0.53 - 0.4874) / 0.09) * 1080;
  const penanda = (
    <div style={{ position: "absolute", left: lx - 130, top: ly - 170, opacity: a, fontFamily: tubuhFont, fontSize: 24, fontWeight: 600, color: warna.kapur, textShadow: "0 2px 10px rgba(0,0,0,0.9)" }}>
      {T.danau}
    </div>
  );
  return (
    <Lembut panjang={panjang}>
      <Selang folder="sagea" tahun={SAGEA_TAHUN} panjang={panjang} akhir={0.6} penanda={penanda} />
      <Bkg sumber={T.sumberSagea} tampil={a} />
      <Kolom jarak={0}>
        <div style={{ width: 640, opacity: a }}>
          <Alis anak={T.alisSagea} />
          <div style={{ fontFamily: tubuhFont, fontSize: 26, color: warna.kapur, marginTop: 26, marginBottom: 6 }}>{T.dalam1km}</div>
          <BatangTahun
            tahun={OG_TAHUN}
            nilai={nilai}
            W={620}
            H={260}
            tampil={(i) => masuk(f, Math.round(panjang * 0.1) + i * 9, 16)}
            sorot={(i) => OG_TAHUN[i] === 2026}
            label={(i) => (OG_TAHUN[i] >= 2025 ? `${koma(nilai[i], 0)} ha` : null)}
          />
          <div style={{ marginTop: 18 }}>
            <Garis anak={T.terdekat(ribuan(Math.round(D.sagea.nearest_m_2026 / 10) * 10))} tampil={c} lebar={620} />
          </div>
          <div style={{ marginTop: 18, fontFamily: tubuhFont, fontSize: 21, color: warna.abu, lineHeight: 1.4, opacity: d, maxWidth: 620 }}>{T.keruh}</div>
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
  const d = masuk(f, Math.round(panjang * 0.7), 24);
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Kolom jarak={28}>
        <h1 style={{ fontFamily: judulFont, fontWeight: 900, fontSize: 60, lineHeight: 1.05, color: warna.abu, margin: 0, opacity: a }}>{T.tutup1}</h1>
        <div style={{ opacity: b, maxWidth: 1500, fontFamily: tubuhFont, fontSize: 42, color: warna.kapur, lineHeight: 1.3 }}>{T.tutup2}</div>
        <h2 style={{ fontFamily: judulFont, fontWeight: 900, fontSize: 64, lineHeight: 1.08, letterSpacing: "-0.02em", color: warna.bara, margin: 0, opacity: c, maxWidth: 1600 }}>{T.tutup3}</h2>
        <div style={{ opacity: d, borderLeft: `3px solid ${warna.garis}`, paddingLeft: 20, fontFamily: tubuhFont, fontSize: 25, color: warna.abu, lineHeight: 1.45, maxWidth: 1400, marginTop: 14 }}>
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
      <Kolom jarak={18}>
        <Alis anak={T.sumberData} />
        <div style={{ display: "flex", flexDirection: "column", gap: 11, width: 1680 }}>
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
  "02-tahun": Tahun,
  "03-penyebab": Pemicu,
  "04-tambang": Tambang,
  "05-weda": Weda,
  "06-sagea": Sagea,
  "07-tutup": Tutup,
};

export const HutanFilm: React.FC<{ bahasa?: Bahasa }> = ({ bahasa = "id" }) => {
  const J = JADWAL_HUTAN[bahasa]!;
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
  <div style={{ borderTop: `2px solid ${warna.garis}`, paddingTop: 22 }}>
    <div style={{ fontFamily: tubuhFont, fontSize: 22, fontWeight: 600, letterSpacing: "0.16em", textTransform: "uppercase", color: warna.bara, marginBottom: 16 }}>{judul}</div>
    {children}
  </div>
);

const Pasang: React.FC<{ folder: string; a: number; b: number; tinggi?: number; potong?: [number, number, number, number] }> = ({ folder, a, b, tinggi = 420, potong }) => {
  // potong = [x0, y0, x1, y1] as fractions of the frame to show
  const [x0, y0, x1, y1] = potong ?? [0, 0, 1, 1];
  const w = 472;
  const skala = w / (1200 * (x1 - x0));
  const h = Math.min(tinggi, 1080 * (y1 - y0) * skala);
  return (
    <div style={{ display: "flex", gap: 28 }}>
      {[a, b].map((y) => (
        <div key={y}>
          <div style={{ width: w, height: h, overflow: "hidden", position: "relative" }}>
            <Img src={staticFile(`hutan/${folder}/${y}.jpg`)} style={{ position: "absolute", width: 1200 * skala, height: 1080 * skala, left: -x0 * 1200 * skala, top: -y0 * 1080 * skala }} />
          </div>
          <div style={{ ...angkaGaya, fontSize: 30, fontWeight: 600, color: warna.kapur, marginTop: 8 }}>{y}</div>
        </div>
      ))}
    </div>
  );
};

/** Two 1080x1350 (4:5) pages: 1 = the province, 2 = nickel at Weda Bay and Sagea Lake. */
export const Infografis: React.FC<{ bahasa?: Bahasa; halaman?: 1 | 2 }> = ({ bahasa = "id", halaman = 1 }) => {
  const T = bahasa === "en" ? TEKS_EN : TEKS_ID;
  const ribuan = (n: number) => ribuanL(n, T.lokal);
  const koma = (n: number, d = 1) => komaL(n, d, T.lokal);
  const M = D.mining;
  const og = D.open_ground.weda as Record<string, number>;
  const w1 = D.sagea.within_1km as Record<string, number>;
  const pk = D.tahun.indexOf(D.puncak.tahun);
  const kecil = { fontFamily: tubuhFont, fontSize: 21, color: warna.abu, lineHeight: 1.4 } as React.CSSProperties;
  const kepala = (
    <div style={{ borderTop: `3px solid ${warna.bara}`, paddingTop: 16, display: "flex", justifyContent: "space-between" }}>
      <Alis anak={T.kiri} />
      <span style={{ fontFamily: tubuhFont, fontSize: 19, letterSpacing: "0.18em", color: warna.abu, textTransform: "uppercase" }}>
        {T.waktu} · {halaman}/2
      </span>
    </div>
  );
  const [r1, r2] = T.rata(ribuan(M.early_per_yr), ribuan(M.late_per_yr));
  if (halaman === 1) {
    return (
      <AbsoluteFill style={{ backgroundColor: warna.jelaga, padding: "46px 54px 40px", display: "flex", flexDirection: "column", gap: 20 }}>
        <div>
          {kepala}
          <h1 style={{ fontFamily: judulFont, fontWeight: 900, fontSize: 64, lineHeight: 0.96, letterSpacing: "-0.035em", color: warna.kapur, margin: "22px 0 0" }}>
            {T.judul.join(" ")}
          </h1>
        </div>
        <div style={{ display: "flex", gap: 20, alignItems: "center" }}>
          <div style={{ width: 520 }}>
            <Angka anak={ribuan(D.loss_total)} ukuran={88} />
            <div style={{ fontFamily: tubuhFont, fontSize: 26, color: warna.kapur }}>{T.hilang}, 2001–2025</div>
            <div style={{ ...kecil, fontSize: 23, marginTop: 12, color: warna.kapur }}>{T.dariTutupan(`${koma(D.loss_pct, 1)}%`)}</div>
            <div style={{ ...kecil, fontSize: 23, marginTop: 4, color: warna.kapur }}>{T.primer(ribuan(D.loss_primary))}</div>
            <div style={{ display: "flex", gap: 16, marginTop: 16, flexWrap: "wrap" }}>
              {T.legenda.map(([k, w]) => (
                <div key={k} style={{ display: "flex", alignItems: "center", gap: 8, ...kecil, fontSize: 18 }}>
                  <div style={{ width: 15, height: 15, background: w }} />
                  {k}
                </div>
              ))}
            </div>
          </div>
          <div style={{ width: 430, height: 400, overflow: "hidden", position: "relative" }}>
            <Img src={staticFile("hutan/peta_provinsi.jpg")} style={{ position: "absolute", width: 726, height: 408, left: -338, top: -4 }} />
          </div>
        </div>
        <Kotak judul={T.judulTahun}>
          <BatangTahun tahun={D.tahun} nilai={D.loss_tahun} W={970} H={105} tampil={() => 1} sorot={(i) => i === pk} label={(i) => (i === pk ? `${ribuan(D.puncak.ha)} ha · El Niño` : null)} />
        </Kotak>
        <Kotak judul={T.judulPemicu}>
          {D.drivers.slice(0, 5).map((d) => {
            const tambang = d.k.startsWith("Hard");
            const w = tambang ? warna.bara : warna.abu;
            return (
              <div key={d.k} style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 5 }}>
                <div style={{ width: 400, fontFamily: tubuhFont, fontSize: 22, color: tambang ? warna.bara : warna.kapur, fontWeight: tambang ? 600 : 400 }}>{T.pemicu[d.k]}</div>
                <div style={{ width: 430, height: 22, background: warna.arang }}>
                  <div style={{ width: (430 * d.pct) / 40, height: 22, background: w }} />
                </div>
                <div style={{ ...angkaGaya, fontSize: 25, fontWeight: 600, color: w }}>{koma(d.pct, 1)}%</div>
              </div>
            );
          })}
          <div style={{ ...kecil, marginTop: 10, color: warna.kapur, fontSize: 22 }}>
            {T.judulTambang}: <span style={{ ...angkaGaya, color: warna.abu }}>{r1}</span> ({T.periode[0]}) →{" "}
            <span style={{ ...angkaGaya, color: warna.bara, fontWeight: 600 }}>{r2}</span> ({T.periode[1]})
          </div>
        </Kotak>
        <div style={{ ...kecil, fontSize: 16, borderTop: `1px solid ${warna.garis}`, paddingTop: 12, marginTop: "auto" }}>
          {T.barisSumber.slice(0, 3).map(([k, v]) => `${k}: ${v}`).join(" · ")}
        </div>
      </AbsoluteFill>
    );
  }
  return (
    <AbsoluteFill style={{ backgroundColor: warna.jelaga, padding: "46px 54px 40px", display: "flex", flexDirection: "column", gap: 20 }}>
      <div>
        {kepala}
        <h1 style={{ fontFamily: judulFont, fontWeight: 900, fontSize: 50, lineHeight: 1, letterSpacing: "-0.03em", color: warna.kapur, margin: "20px 0 0" }}>{T.judulHal2}</h1>
      </div>
      <Kotak judul={T.alisWeda}>
        <Pasang folder="weda" a={2018} b={2026} tinggi={300} potong={[0.0, 0.15, 0.7, 0.8]} />
        <div style={{ ...kecil, color: warna.kapur, fontSize: 22, marginTop: 10 }}>
          {T.lahanTerbuka}: <span style={{ ...angkaGaya }}>{ribuan(og["2019"])} ha</span> (2019) → <span style={{ ...angkaGaya, color: warna.bara, fontWeight: 600 }}>{ribuan(og["2026"])} ha</span> (2026)
        </div>
        <div style={{ ...kecil, fontSize: 18, marginTop: 6 }}>{T.catatanWeda}</div>
      </Kotak>
      <Kotak judul={T.alisSagea}>
        <Pasang folder="sagea" a={2025} b={2026} tinggi={262} potong={[0.32, 0.3, 0.78, 0.64]} />
        <div style={{ ...kecil, color: warna.kapur, fontSize: 22, marginTop: 10 }}>
          {T.dalam1km}: <span style={{ ...angkaGaya }}>{koma(w1["2025"], 0)} ha</span> (2025) → <span style={{ ...angkaGaya, color: warna.bara, fontWeight: 600 }}>{koma(w1["2026"], 0)} ha</span> (2026) · {T.terdekat(ribuan(Math.round(D.sagea.nearest_m_2026 / 10) * 10))}
        </div>
      </Kotak>
      <div style={{ ...kecil, fontSize: 16, borderTop: `1px solid ${warna.garis}`, paddingTop: 12, marginTop: "auto" }}>
        {T.barisSumber.slice(3).map(([k, v]) => `${k}: ${v}`).join(" · ")}. {T.peringatan}
      </div>
    </AbsoluteFill>
  );
};
