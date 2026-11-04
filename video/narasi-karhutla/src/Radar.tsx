/**
 * "Menembus asap" / "Through the smoke" — Part 3 of the concessions film.
 *
 * Part 2 found damaged peat inside four Ketapang concessions burning wider
 * and longer. Part 3 follows the fire through the 2026 season:
 *
 *   smoke          Sentinel-2 on 2 and 7 September: plumes, then haze
 *   the clock      VIIRS heat detections, one frame per day, Jul–Oct
 *   the radar      Sentinel-1 C-band loses coherence over peat in 12 days
 *                  (median 0.05); NISAR L-band keeps it (0.42)
 *   the check      NISAR coherence loss + backscatter change: ~80,000 ha,
 *                  7 in 10 match the Sentinel-2 burn (held-out blocks)
 *   week by week   both clocks agree: inside the four, fire arrived about
 *                  a week earlier than on unpermitted land around them
 *   the boundary   25 scars straddle a boundary: 8 inside first, 4 outside,
 *                  13 same window — radar cannot decide
 *
 * Same palette, type, components and audio pipeline as Telusur.tsx. Every
 * figure comes from radarData.json (scripts/ketapang_film3_assets.py).
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
import { JADWAL_RADAR } from "./jadwalRadar";
import type { Bahasa } from "./jadwalKonsesi";
import { Bingkai, Judul, Keterangan, Kolom, LatarDiam, Lembut, masuk, Penghitung } from "./komponen";
import { angkaGaya, judulFont, koma as komaId, ribuan as ribuanId, tubuhFont, warna } from "./teema";
import D from "./radarData.json";

const BEKAS = "#4A2C20";
const REDUP = "#8C3211"; // bara at 55%, as the frames draw past detections
const ABU_GELAP = "#3A424D";

const TEKS_ID = {
  lokal: "id-ID",
  audio: "audio/radar",
  musik: "musik-radar.mp3",
  labelSumber: "Sumber",
  kiri: "Karhutla Kalimantan · Bagian 3",
  waktu: "November 2026",
  alisJudul: "Di dalam konsesi · Bagian 3",
  judul: ["MENEMBUS", "ASAP"],
  subJudul: "Mengikuti jalannya api sepanjang musim 2026 di pesisir Ketapang, dengan titik panas dan radar NISAR.",
  kilas1: "Gambut rusak terbakar lebih luas, lebih lama.",
  kilas2: "Kapan api datang, dan ke mana ia bergerak?",
  sumberAsap: "Sentinel-2 L1C, warna asli, 2 dan 7 September 2026 · Copernicus",
  alisAsap: "Satelit optik",
  asap: "Asap menutup permukaan.",
  tanggalAsap: ["2 September 2026", "7 September 2026"],
  sumberJam:
    "VIIRS 375 m (S-NPP, NOAA-20), NASA LANCE · hari dalam WIB · deteksi digambar sebagai piksel 375 m",
  alisJam: "Titik panas, dua kali sehari",
  deteksi: "deteksi, Juli – Oktober 2026",
  perHari: "deteksi per hari",
  legendaJam: ["terdeteksi hari ini dan kemarin", "terdeteksi sebelumnya"],
  sumberRadar:
    "Sentinel-1 IW, koherensi 12 hari (rata-rata) · NISAR L2 GUNW (versi awal), 20 Jun – 2 Jul 2026, lintasan 90",
  alisRadar: "Koherensi radar",
  radarKet: "Keselarasan dua citra radar dari lintasan yang sama: 0 = acak, 1 = sama persis. Terang = selaras.",
  pita: [
    ["Sentinel-1", "pita C · 5,6 cm"],
    ["NISAR", "pita L · 24 cm"],
  ] as [string, string][],
  median: "median di darat",
  sumberPeta:
    "NISAR L2 GUNW + GCOV (versi awal), 4 lintasan, 35 pasang · diuji pada blok 5 km yang tidak dipakai menyetel · bekas bakar: Sentinel-2 dNBR",
  alisPeta: "Ditandai radar",
  hektare: "hektare bekas bakar: koherensi turun dan pantulan berubah",
  presisi: (n: string) => `${n} dari 10 piksel radar cocok dengan bekas bakar Sentinel-2`,
  recall: (p: string) => `radar menemukan ${p}% bekas bakar Sentinel-2`,
  legendaPeta: ["ditandai radar", "bekas bakar Sentinel-2 saja"],
  versiAwal: "Produk NISAR masih versi awal (provisional).",
  sumberPekan:
    "Radar: tengah jendela 12 hari, piksel yang ditandai radar · titik panas: deteksi pertama per sel 40 m · luar = lahan tanpa izin",
  alisPekan: "Pekan demi pekan",
  judulKurva: "Bagian bekas bakar musim ini, menurut tanggal radar",
  zona: ["keempat konsesi", "lahan tanpa izin"],
  sebelumSep: "lokasi api sudah menyala sebelum September (titik panas)",
  median2: (a: string, b: string) => `median: ${a} di dalam, ${b} di luar`,
  jamRadar: "radar",
  jamTitik: "titik panas",
  bulanPendek: ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"],
  sumberBatas:
    "Petak bekas bakar radar yang melintasi batas · 10% tanggal paling awal dalam pita 1 km di dalam vs di luar · selisih < 4 hari = jendela sama",
  judulBatas: "Api menyeberang dari mana?",
  kolomBatas: ["lebih dulu di dalam", "lebih dulu di luar", "jendela sama"],
  total: "Jumlah",
  batasKet: "Radar lewat setiap 12 hari; jendelanya terlalu lebar untuk memutuskan. Asal api tetap dibaca dari titik panas (Bagian 2).",
  tutup1: "Radar memastikan di mana; titik panas memberi kapan.",
  tutupKet: "Radar menembus asap, tetapi tanggalnya hanya setepat lintasannya: sekitar 12 hari.",
  tutup2: "Di dalam keempat konsesi, api datang sekitar seminggu lebih awal.",
  tutup3: "Gambut yang lebih kering lebih cepat terbakar — dugaan yang masih perlu diuji, bukan temuan.",
  sumberData: "Sumber data",
  baris: [
    ["Api", "VIIRS 375 m (S-NPP, NOAA-20), NASA LANCE"],
    ["Radar L", "NISAR L2 GUNW (koherensi 20 m) dan GCOV (HH/HV 20 m), versi awal, NASA/ISRO via ASF"],
    ["Radar C", "Sentinel-1 IW SLC, koherensi 12 hari, Copernicus"],
    ["Optik", "Sentinel-2 L1C (asap); Sentinel-2 dNBR (bekas bakar), Copernicus"],
    ["Air", "JRC Global Surface Water 1984–2021 (masker banjir)"],
    ["Izin", "Global Forest Watch: konsesi sawit (±2012)"],
  ] as [string, string][],
  peringatan:
    "Produk NISAR yang dipakai masih versi awal. Tanggal radar adalah jendela 12 hari, bukan hari kebakaran. Tiga dari sepuluh piksel radar tidak cocok dengan bekas bakar Sentinel-2. Lokasi dan waktu kebakaran bukan bukti siapa yang menyalakan api.",
};

type Teks = typeof TEKS_ID;

const TEKS_EN: Teks = {
  lokal: "en-GB",
  audio: "audio/radar-en",
  musik: "musik-radar-en.mp3",
  labelSumber: "Source",
  kiri: "Kalimantan fires · Part 3",
  waktu: "November 2026",
  alisJudul: "Inside the concessions · Part 3",
  judul: ["THROUGH", "THE SMOKE"],
  subJudul: "Following the 2026 fire season on the Ketapang coast with heat detections and NISAR radar.",
  kilas1: "Damaged peat burned wider and longer.",
  kilas2: "When did the fire arrive, and where did it go?",
  sumberAsap: "Sentinel-2 L1C, true colour, 2 and 7 September 2026 · Copernicus",
  alisAsap: "Optical satellites",
  asap: "Smoke hides the ground.",
  tanggalAsap: ["2 September 2026", "7 September 2026"],
  sumberJam:
    "VIIRS 375 m (S-NPP, NOAA-20), NASA LANCE · days in local time (WIB) · detections drawn as 375 m pixels",
  alisJam: "Heat detections, twice a day",
  deteksi: "detections, July – October 2026",
  perHari: "detections per day",
  legendaJam: ["detected today or yesterday", "detected earlier"],
  sumberRadar:
    "Sentinel-1 IW, 12-day coherence (mean) · NISAR L2 GUNW (provisional), 20 Jun – 2 Jul 2026, track 90",
  alisRadar: "Radar coherence",
  radarKet: "How alike two radar images from the same orbit are: 0 = random, 1 = identical. Bright = coherent.",
  pita: [
    ["Sentinel-1", "C-band · 5.6 cm"],
    ["NISAR", "L-band · 24 cm"],
  ],
  median: "median over land",
  sumberPeta:
    "NISAR L2 GUNW + GCOV (provisional), 4 tracks, 35 pairs · scored on 5 km blocks not used for tuning · burn: Sentinel-2 dNBR",
  alisPeta: "Flagged by radar",
  hektare: "hectares burned: coherence fell and the echo changed",
  presisi: (n: string) => `${n} in 10 radar pixels match the Sentinel-2 burn`,
  recall: (p: string) => `radar finds ${p}% of the Sentinel-2 burn`,
  legendaPeta: ["flagged by radar", "Sentinel-2 burn only"],
  versiAwal: "NISAR products are still provisional.",
  sumberPekan:
    "Radar: middle of the 12-day window, radar-flagged pixels · heat: first detection per 40 m cell · outside = unpermitted land",
  alisPekan: "Week by week",
  judulKurva: "Share of the season's burn, by radar date",
  zona: ["the four concessions", "unpermitted land"],
  sebelumSep: "of fire locations had ignited before September (heat detections)",
  median2: (a: string, b: string) => `median: ${a} inside, ${b} outside`,
  jamRadar: "radar",
  jamTitik: "heat detections",
  bulanPendek: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
  sumberBatas:
    "Radar burn scars crossing a boundary · earliest 10% of dates in the 1 km band inside vs outside · < 4 days apart = same window",
  judulBatas: "Which way did fire cross?",
  kolomBatas: ["inside first", "outside first", "same window"],
  total: "Total",
  batasKet: "Radar passes every 12 days; its windows are too wide to decide. Where fires began is still read from heat detections (Part 2).",
  tutup1: "Radar confirms where; heat detections give when.",
  tutupKet: "Radar sees through smoke, but its dates are only as fine as its revisit: about 12 days.",
  tutup2: "Inside the four concessions, fire arrived about a week earlier.",
  tutup3: "Drier peat catches fire sooner — a hypothesis still to be tested, not a finding.",
  sumberData: "Data sources",
  baris: [
    ["Fire", "VIIRS 375 m (S-NPP, NOAA-20), NASA LANCE"],
    ["L-band radar", "NISAR L2 GUNW (20 m coherence) and GCOV (20 m HH/HV), provisional, NASA/ISRO via ASF"],
    ["C-band radar", "Sentinel-1 IW SLC, 12-day coherence, Copernicus"],
    ["Optical", "Sentinel-2 L1C (smoke); Sentinel-2 dNBR (burned area), Copernicus"],
    ["Water", "JRC Global Surface Water 1984–2021 (flood mask)"],
    ["Permits", "Global Forest Watch: oil palm concessions (c. 2012)"],
  ],
  peringatan:
    "The NISAR products used are provisional. Radar dates are 12-day windows, not the day of the fire. Three in ten radar pixels do not match the Sentinel-2 burn. Where and when land burned is not proof of who lit the fire.",
};

const Ctx = createContext<Bahasa>("id");

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
  return <Bingkai kiri={t.kiri} waktu={t.waktu} labelSumber={t.labelSumber} sumber={sumber} tampil={tampil} />;
};

const Gambar: React.FC<{ berkas: string; panjang?: number; zoom?: number; redup?: number; gradasi?: boolean }> = ({
  berkas,
  panjang = 1,
  zoom = 1,
  redup = 0,
  gradasi = true,
}) => {
  const f = useCurrentFrame();
  const s = interpolate(f, [0, panjang], [1, zoom], { extrapolateRight: "clamp" });
  return (
    <AbsoluteFill style={{ backgroundColor: warna.jelaga, overflow: "hidden" }}>
      <Img
        src={staticFile(`radar/${berkas}`)}
        style={{ width: "100%", height: "100%", transform: `scale(${s})`, transformOrigin: "78% 55%", opacity: 1 - redup }}
      />
      {gradasi && (
        <AbsoluteFill
          style={{
            background: `linear-gradient(90deg, ${warna.jelaga} 0%, rgba(10,12,15,0.85) 30%, rgba(10,12,15,0) 48%)`,
          }}
        />
      )}
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

const Legenda: React.FC<{ isi: [string, string][]; tampil: number }> = ({ isi, tampil }) => (
  <div style={{ display: "flex", flexDirection: "column", gap: 12, opacity: tampil, fontFamily: tubuhFont, fontSize: 23, color: warna.kapur }}>
    {isi.map(([w, k]) => (
      <div key={k} style={{ display: "flex", alignItems: "center", gap: 14 }}>
        <div style={{ width: 26, height: 18, background: w, borderRadius: 2 }} />
        {k}
      </div>
    ))}
  </div>
);

const Catatan: React.FC<{ anak: string; tampil: number; lebar?: number }> = ({ anak, tampil, lebar = 700 }) => (
  <div style={{ fontFamily: tubuhFont, fontSize: 21, color: warna.samar, lineHeight: 1.4, maxWidth: lebar, opacity: tampil }}>
    {anak}
  </div>
);

const Angka: React.FC<{ anak: string; ukuran?: number; warnaA?: string }> = ({ anak, ukuran = 150, warnaA = warna.nyala }) => (
  <div style={{ ...angkaGaya, fontSize: ukuran, fontWeight: 600, color: warnaA, lineHeight: 1 }}>{anak}</div>
);

const Garis: React.FC<{ anak: string; tampil: number; lebar?: number }> = ({ anak, tampil, lebar = 560 }) => (
  <div
    style={{
      borderLeft: `3px solid ${warna.bara}`,
      paddingLeft: 18,
      fontFamily: tubuhFont,
      fontSize: 26,
      color: warna.kapur,
      lineHeight: 1.35,
      maxWidth: lebar,
      opacity: tampil,
    }}
  >
    {anak}
  </div>
);

const hari0 = new Date(`${D.hari_mulai}T00:00:00Z`);
const tanggal = (i: number, bulan: string[]) => {
  const d = new Date(hari0.getTime() + i * 86400000);
  return `${d.getUTCDate()} ${bulan[d.getUTCMonth()]}`;
};
const dariIso = (s: string, bulan: string[]) => {
  const d = new Date(`${s}T00:00:00Z`);
  return `${d.getUTCDate()} ${bulan[d.getUTCMonth()]}`;
};

/* ---------------------------------- scenes --------------------------- */

const KartuJudul: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { t } = useT();
  const f = useCurrentFrame();
  const a = masuk(f, 4, 24);
  return (
    <Lembut panjang={panjang}>
      <Gambar berkas="peta_radar.jpg" panjang={panjang} zoom={1.06} redup={0.35} />
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
  const { t } = useT();
  const f = useCurrentFrame();
  const a = masuk(f, 4, 22);
  const b = masuk(f, Math.round(panjang * 0.5), 22);
  const besar: React.CSSProperties = {
    fontFamily: judulFont,
    fontWeight: 900,
    fontSize: 96,
    lineHeight: 1.04,
    letterSpacing: "-0.03em",
    margin: 0,
    maxWidth: 1600,
  };
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Kolom jarak={22}>
        <h1 style={{ ...besar, color: warna.abu, opacity: a }}>{t.kilas1}</h1>
        <h2 style={{ ...besar, color: warna.kapur, opacity: b, transform: `translateY(${(1 - b) * 18}px)` }}>{t.kilas2}</h2>
      </Kolom>
    </Lembut>
  );
};

const Asap: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { t } = useT();
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  // tile geometry from ketapang_film3_assets.py (hh 0.56, gap 0.012)
  const kiri = [760, 1323];
  const b = masuk(f, Math.round(panjang * 0.55), 24);
  return (
    <Lembut panjang={panjang}>
      <AbsoluteFill style={{ backgroundColor: warna.jelaga }}>
        <Img src={staticFile("radar/asap.jpg")} style={{ width: "100%", height: "100%" }} />
        {/* the second tile arrives with "five days later" */}
        <div
          style={{ position: "absolute", left: kiri[1] - 4, top: 230, width: 548, height: 620, background: warna.jelaga, opacity: 1 - b }}
        />
      </AbsoluteFill>
      <Bkg sumber={t.sumberAsap} tampil={a} />
      {t.tanggalAsap.map((s, i) => (
        <div
          key={s}
          style={{
            position: "absolute",
            left: kiri[i],
            top: 858,
            fontFamily: tubuhFont,
            fontSize: 24,
            fontWeight: 600,
            color: warna.kapur,
            opacity: i ? b : a,
          }}
        >
          {s}
        </div>
      ))}
      <Kolom jarak={0}>
        <div style={{ opacity: a, width: 560 }}>
          <Alis anak={t.alisAsap} />
          <h1
            style={{
              fontFamily: judulFont,
              fontWeight: 900,
              fontSize: 76,
              lineHeight: 1.05,
              letterSpacing: "-0.03em",
              color: warna.kapur,
              margin: "18px 0 0",
            }}
          >
            {t.asap}
          </h1>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Sparkline: React.FC<{ hari: number; tampil: number }> = ({ hari, tampil }) => {
  const W = 520;
  const H = 120;
  const v = D.viirs_harian;
  const maks = Math.max(...v);
  const x = (i: number) => (i / (v.length - 1)) * W;
  const y = (n: number) => H - (n / maks) * (H - 6);
  const n = Math.max(1, Math.min(hari, v.length - 1));
  const d = v
    .slice(0, n + 1)
    .map((q, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(q).toFixed(1)}`)
    .join(" ");
  const semua = v.map((q, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(q).toFixed(1)}`).join(" ");
  return (
    <svg width={W} height={H + 4} style={{ opacity: tampil, overflow: "visible" }}>
      <path d={semua} fill="none" stroke={warna.garis} strokeWidth={2} />
      <path d={`${d} L${x(n)},${H} L0,${H} Z`} fill={REDUP} opacity={0.5} />
      <path d={d} fill="none" stroke={warna.nyala} strokeWidth={2.5} />
      <line x1={x(n)} x2={x(n)} y1={0} y2={H} stroke={warna.kapur} strokeWidth={1.5} />
    </svg>
  );
};

const Jam: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { t, ribuan } = useT();
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const AWAL = 20;
  const AKHIR = 40;
  const hari = Math.round(
    interpolate(f, [AWAL, panjang - AKHIR], [0, D.hari_n - 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })
  );
  const kumulatif = D.viirs_harian.slice(0, hari + 1).reduce((s, q) => s + q, 0);
  return (
    <Lembut panjang={panjang}>
      <Gambar berkas={`jam/d${String(hari).padStart(3, "0")}.jpg`} />
      <Bkg sumber={t.sumberJam} tampil={a} />
      <Kolom jarak={0}>
        <div style={{ opacity: a, width: 600 }}>
          <Alis anak={t.alisJam} />
          <div style={{ ...angkaGaya, fontFamily: judulFont, fontWeight: 900, fontSize: 104, color: warna.kapur, marginTop: 14, lineHeight: 1 }}>
            {tanggal(hari, t.bulanPendek)}
          </div>
          <div style={{ marginTop: 26, display: "flex", alignItems: "baseline", gap: 14 }}>
            <Angka anak={ribuan(kumulatif)} ukuran={64} />
          </div>
          <div style={{ fontFamily: tubuhFont, fontSize: 26, color: warna.kapur, marginTop: 4 }}>{t.deteksi}</div>
          <div style={{ marginTop: 30 }}>
            <Sparkline hari={hari} tampil={masuk(f, 14, 20)} />
            <div style={{ fontFamily: tubuhFont, fontSize: 20, color: warna.samar, marginTop: 6 }}>{t.perHari}</div>
          </div>
          <div style={{ marginTop: 30 }}>
            <Legenda
              isi={[
                [warna.nyala, t.legendaJam[0]],
                [REDUP, t.legendaJam[1]],
              ]}
              tampil={masuk(f, 30, 20)}
            />
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Radar: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { t, koma } = useT();
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  // tile geometry from ketapang_film3_assets.py (hh 0.56, gap 0.014)
  const kiri = [750, 1320];
  const nilai = [D.koherensi_s1, D.koherensi_nisar];
  const muncul = [masuk(f, Math.round(panjang * 0.12), 24), masuk(f, Math.round(panjang * 0.52), 24)];
  return (
    <Lembut panjang={panjang}>
      <AbsoluteFill style={{ backgroundColor: warna.jelaga }}>
        <Img src={staticFile("radar/koherensi.jpg")} style={{ width: "100%", height: "100%" }} />
        {muncul.map((m, i) => (
          <div
            key={i}
            style={{ position: "absolute", left: kiri[i] - 4, top: 250, width: 552, height: 625, background: warna.jelaga, opacity: 1 - m }}
          />
        ))}
      </AbsoluteFill>
      <Bkg sumber={t.sumberRadar} tampil={a} />
      {t.pita.map(([nama, pita], i) => (
        <div key={nama} style={{ position: "absolute", left: kiri[i], top: 150, opacity: muncul[i] }}>
          <div style={{ fontFamily: judulFont, fontWeight: 800, fontSize: 34, color: warna.kapur }}>{nama}</div>
          <div style={{ fontFamily: tubuhFont, fontSize: 22, color: warna.abu, marginTop: 2 }}>{pita}</div>
        </div>
      ))}
      {nilai.map((v, i) => (
        <div key={i} style={{ position: "absolute", left: kiri[i], top: 878, display: "flex", alignItems: "baseline", gap: 12, opacity: muncul[i] }}>
          <div style={{ ...angkaGaya, fontSize: 44, fontWeight: 600, color: i ? warna.nyala : warna.abu }}>{koma(v, 2)}</div>
          <div style={{ fontFamily: tubuhFont, fontSize: 20, color: warna.samar }}>{t.median}</div>
        </div>
      ))}
      <Kolom jarak={0}>
        <div style={{ opacity: a, width: 540 }}>
          <Alis anak={t.alisRadar} />
          <div style={{ marginTop: 22 }}>
            <Garis anak={t.radarKet} tampil={masuk(f, 20, 20)} lebar={540} />
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Peta: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { t, koma, ribuan } = useT();
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  return (
    <Lembut panjang={panjang}>
      <Gambar berkas="peta_radar.jpg" panjang={panjang} zoom={1.04} />
      <Bkg sumber={t.sumberPeta} tampil={a} />
      <Kolom jarak={0}>
        <div style={{ opacity: a, width: 680 }}>
          <Alis anak={t.alisPeta} />
          <div style={{ marginTop: 18 }}>
            <Penghitung ke={Math.round(D.terkonfirmasi_ha / 1000) * 1000} mulai={Math.round(panjang * 0.2)} panjang={50} ukuran={120} lokal={t.lokal} />
          </div>
          <div style={{ fontFamily: tubuhFont, fontSize: 28, color: warna.kapur, marginTop: 6, lineHeight: 1.3 }}>{t.hektare}</div>
          <div style={{ marginTop: 32 }}>
            <Garis anak={t.presisi(koma(D.terkonfirmasi_presisi * 10, 0))} tampil={masuk(f, Math.round(panjang * 0.5), 22)} lebar={640} />
          </div>
          <div style={{ ...angkaGaya, fontSize: 23, color: warna.abu, marginTop: 14, opacity: masuk(f, Math.round(panjang * 0.58), 22) }}>
            {t.recall(koma(D.terkonfirmasi_recall * 100, 0))}
          </div>
          <div style={{ marginTop: 30 }}>
            <Legenda
              isi={[
                [warna.bara, t.legendaPeta[0]],
                [BEKAS, t.legendaPeta[1]],
              ]}
              tampil={masuk(f, 30, 20)}
            />
          </div>
          <div style={{ marginTop: 22 }}>
            <Catatan anak={t.versiAwal} tampil={masuk(f, Math.round(panjang * 0.8), 20)} lebar={640} />
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Kurva: React.FC<{ minggu: number; tampil: number }> = ({ minggu, tampil }) => {
  const { t } = useT();
  const W = 560;
  const H = 230;
  const L = 60;
  const P = D.pekanan;
  const seri = (k: "empat" | "luar") => {
    const tot = P.reduce((s, r) => s + r[k], 0);
    let c = 0;
    return P.map((r) => (c += r[k]) / tot);
  };
  const s4 = seri("empat");
  const sL = seri("luar");
  const x = (i: number) => L + ((i + 1) / P.length) * (W - L - 6);
  const y = (v: number) => H - 28 - v * (H - 40);
  const jalur = (s: number[]) =>
    [`M${L},${y(0)}`, ...s.slice(0, minggu + 1).map((v, i) => `L${x(i).toFixed(1)},${y(v).toFixed(1)}`)].join(" ");
  const bulanX = [
    ["Jul", 0],
    ["Agu", 30 / 7],
    ["Sep", 61 / 7],
    ["Okt", 91 / 7],
  ] as [string, number][];
  return (
    <svg width={W} height={H} style={{ opacity: tampil }}>
      {[0, 0.5, 1].map((v) => (
        <g key={v}>
          <line x1={L} x2={W - 6} y1={y(v)} y2={y(v)} stroke={warna.garis} strokeWidth={1} />
          <text x={L - 8} y={y(v) + 6} fill={warna.samar} fontSize={17} textAnchor="end" fontFamily={tubuhFont}>
            {v * 100}%
          </text>
        </g>
      ))}
      {bulanX.map(([m, w], i) => (
        <text key={m} x={L + (w / P.length) * (W - L - 6)} y={H - 6} fill={warna.samar} fontSize={17} fontFamily={tubuhFont}>
          {t.bulanPendek[6 + i]}
        </text>
      ))}
      <path d={jalur(sL)} fill="none" stroke={warna.abu} strokeWidth={3} />
      <path d={jalur(s4)} fill="none" stroke={warna.bara} strokeWidth={4.5} />
    </svg>
  );
};

const Pekan: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { t, koma } = useT();
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const NW = D.pekanan.length;
  const minggu = Math.round(
    interpolate(f, [15, panjang * 0.62], [0, NW - 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })
  );
  const W = D.waktu;
  const b = masuk(f, Math.round(panjang * 0.4), 22);
  const c = masuk(f, Math.round(panjang * 0.66), 22);
  return (
    <Lembut panjang={panjang}>
      <Gambar berkas={`pekan/w${String(minggu).padStart(2, "0")}.jpg`} />
      <Bkg sumber={t.sumberPekan} tampil={a} />
      <Kolom jarak={0}>
        <div style={{ opacity: a, width: 620 }}>
          <Alis anak={t.alisPekan} />
          <div style={{ ...angkaGaya, fontFamily: judulFont, fontWeight: 900, fontSize: 64, color: warna.kapur, marginTop: 10 }}>
            {dariIso(D.pekanan[minggu].mulai, t.bulanPendek)}
          </div>
          <div style={{ fontFamily: tubuhFont, fontSize: 21, color: warna.abu, marginTop: 16, marginBottom: 6 }}>{t.judulKurva}</div>
          <Kurva minggu={minggu} tampil={masuk(f, 10, 20)} />
          <div style={{ display: "flex", gap: 26, marginTop: 4, fontFamily: tubuhFont, fontSize: 21, color: warna.kapur }}>
            {[warna.bara, warna.abu].map((w, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <div style={{ width: 24, height: 4, background: w }} />
                {t.zona[i]}
              </div>
            ))}
          </div>
          <div style={{ display: "flex", gap: 40, marginTop: 28, opacity: b }}>
            {[
              [W.four.viirs_first_share_by_end_aug, warna.nyala, t.zona[0]],
              [W.unc.viirs_first_share_by_end_aug, warna.abu, t.zona[1]],
            ].map(([v, w, k]) => (
              <div key={k as string} style={{ borderTop: `3px solid ${w}`, paddingTop: 10 }}>
                <Angka anak={`${koma((v as number) * 100, 0)}%`} ukuran={60} warnaA={w as string} />
                <div style={{ fontFamily: tubuhFont, fontSize: 20, color: warna.abu, marginTop: 4 }}>{k as string}</div>
              </div>
            ))}
          </div>
          <div style={{ fontFamily: tubuhFont, fontSize: 21, color: warna.kapur, marginTop: 10, opacity: b, maxWidth: 600 }}>
            {t.sebelumSep}
          </div>
          <div style={{ ...angkaGaya, fontSize: 18, color: warna.abu, marginTop: 16, lineHeight: 1.5, opacity: c, width: 680 }}>
            {t.jamTitik} — {t.median2(dariIso(W.four.viirs_first_median, t.bulanPendek), dariIso(W.unc.viirs_first_median, t.bulanPendek))}
            <br />
            {t.jamRadar} — {t.median2(dariIso(W.four.radar_mid_median, t.bulanPendek), dariIso(W.unc.radar_mid_median, t.bulanPendek))}
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Batas: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { t } = useT();
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const warnaK = [warna.bara, warna.abu, ABU_GELAP];
  const SKALA = 70; // px per scar
  const baris = [...D.batas, { akronim: t.total, ...D.batas_total }];
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Bkg sumber={t.sumberBatas} tampil={a} />
      <Kolom jarak={0}>
        <div style={{ opacity: a, width: 1600 }}>
          <Judul anak={t.judulBatas} ukuran={60} />
          <div style={{ display: "flex", gap: 30, marginTop: 30, fontFamily: tubuhFont, fontSize: 23, color: warna.kapur }}>
            {t.kolomBatas.map((k, i) => (
              <div key={k} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <div style={{ width: 26, height: 18, background: warnaK[i], borderRadius: 2 }} />
                {k}
              </div>
            ))}
          </div>
          <div style={{ marginTop: 30, display: "flex", flexDirection: "column", gap: 16 }}>
            {baris.map((r, j) => {
              const n = masuk(f, Math.round(panjang * 0.14) + j * 12, 26);
              const total = j === baris.length - 1;
              const skala = total ? SKALA * 0.5 : SKALA;
              return (
                <div key={r.akronim} style={{ display: "flex", alignItems: "center", height: total ? 64 : 52, marginTop: total ? 18 : 0 }}>
                  <div style={{ width: 200, fontFamily: judulFont, fontWeight: 800, fontSize: total ? 30 : 27, color: warna.kapur }}>
                    {r.akronim}
                  </div>
                  {[r.dalam, r.luar, r.sama].map((v, i) => (
                    <div
                      key={i}
                      style={{
                        width: v * skala * n,
                        height: total ? 48 : 36,
                        background: warnaK[i],
                        marginRight: v ? 4 : 0,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        ...angkaGaya,
                        fontSize: total ? 28 : 22,
                        fontWeight: 600,
                        color: i === 0 ? warna.jelaga : warna.kapur,
                        overflow: "hidden",
                      }}
                    >
                      {v && n > 0.6 ? v : ""}
                    </div>
                  ))}
                </div>
              );
            })}
          </div>
          <div style={{ marginTop: 40 }}>
            <Garis anak={t.batasKet} tampil={masuk(f, Math.round(panjang * 0.62), 22)} lebar={1300} />
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Tutup: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { t } = useT();
  const f = useCurrentFrame();
  const a = masuk(f, 4, 22);
  const b = masuk(f, Math.round(panjang * 0.38), 24);
  const c = masuk(f, Math.round(panjang * 0.66), 24);
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Kolom jarak={28}>
        <h1
          style={{
            fontFamily: judulFont,
            fontWeight: 900,
            fontSize: 80,
            lineHeight: 1.04,
            letterSpacing: "-0.03em",
            color: warna.kapur,
            margin: 0,
            maxWidth: 1600,
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
  const { t } = useT();
  const f = useCurrentFrame();
  const a = masuk(f, 4, 20);
  return (
    <AbsoluteFill style={{ backgroundColor: warna.jelaga, opacity: a }}>
      <Kolom jarak={18}>
        <Alis anak={t.sumberData} />
        <div style={{ display: "flex", flexDirection: "column", gap: 11, width: 1620 }}>
          {t.baris.map(([k, v]) => (
            <div key={k} style={{ display: "flex", gap: 28, alignItems: "baseline" }}>
              <div style={{ width: 220, fontFamily: tubuhFont, fontSize: 24, fontWeight: 600, color: warna.kapur }}>{k}</div>
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
  "02-asap": Asap,
  "03-jam": Jam,
  "04-radar": Radar,
  "05-peta": Peta,
  "06-pekan": Pekan,
  "07-batas": Batas,
  "08-tutup": Tutup,
};

export const RadarFilm: React.FC<{ bahasa?: Bahasa }> = ({ bahasa = "id" }) => {
  const J = JADWAL_RADAR[bahasa];
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
