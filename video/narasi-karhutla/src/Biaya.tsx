/**
 * "Harga di Balik Nikel" — part 5 of the North Maluku series, plus a two-page infographic (InfografisBiaya):
 * the economic value of nickel mining and processing against its environmental costs, 2019-2025.
 *
 *   value added  mining + manufacturing, BPS regional GDP: Rp 7.1 tn (2019) -> 84.0 tn (2025)
 *   night lights VIIRS around Weda Bay x5.4 (2019 -> 2025)
 *   coal         captive capacity 1.87 GW (Jul 2023) -> 6.37 GW (Jul 2025); 2025 CO2 30-40 Mt
 *   valuation    Rp 127-169 tn at US EPA social cost of carbon; 40-54 tn at EU ETS; health ~17 (indicative);
 *                forest carbon 0.5-6; ecosystem services 0.8-1.9 per year
 *   who          DBH to the producing regency ~Rp 1.1 tn; climate cost global, pollution/forest/water local
 *
 * Indonesian only (Bian). Every figure is from biayaData.json (scripts/biaya_film_assets.py, from
 * output/malut_forest/economics/econ.json). Not a profit-and-loss account. No company is named.
 */

import React from "react";
import { AbsoluteFill, Audio, Img, interpolate, Sequence, staticFile, useCurrentFrame } from "remotion";
import { JADWAL_BIAYA } from "./jadwalBiaya";
import { Bingkai, Judul, Keterangan, Kolom, LatarDiam, Lembut, masuk } from "./komponen";
import { angkaGaya, judulFont, koma, ribuan, tubuhFont, warna } from "./teema";
import D from "./biayaData.json";

const ABU_GELAP = "#3A424D";
const AUDIO = "audio/biaya";
const NT = D.nilai_tambah as Record<string, number>;
const rentang = (v: number[]) => `${ribuan(v[0])}–${ribuan(v[1])}`;
const kaliMalam = D.malam["2025" as keyof typeof D.malam] / D.malam["2019" as keyof typeof D.malam];

const T = {
  kiri: "Nikel Maluku Utara: nilai dan biaya",
  waktu: "November 2026",
  labelSumber: "Sumber",
  sumberNilai: "BPS, PDRB Maluku Utara atas dasar harga berlaku: B Pertambangan + C Industri Pengolahan",
  sumberMalam: "NOAA VIIRS DNB, median bulanan (VCMSLCFG), radiansi total di sekitar Teluk Weda",
  sumberBatu: "CREA & Global Energy Monitor (Jan 2026): kapasitas PLTU captive Maluku Utara, Juli 2023 dan Juli 2025",
  sumberCo2: "CO₂ = kapasitas × beban 60–80% × 0,90 tCO₂/MWh (dari estimasi Climate Rights International) · SCC: US EPA 2023 · EU ETS 2025 · USD 1 = Rp 16.000",
  sumberHutan: "Karbon: IPCC (2006, 2019) · jasa ekosistem: de Groot dkk. (2012), Costanza dkk. (2014) · kesehatan: CREA & CELIOS (2024), indikatif",
  sumberSiapa: "DBH: Katadata/CERAH (2026) · royalti nasional: DEN (2025) · belum diverifikasi ke dokumen asli",
};

/* ------------------------------ furniture ----------------------------- */

const Bkg: React.FC<{ sumber?: string; tampil?: number }> = ({ sumber, tampil }) => (
  <Bingkai kiri={T.kiri} waktu={T.waktu} labelSumber={T.labelSumber} sumber={sumber} tampil={tampil} />
);
const Alis: React.FC<{ anak: string; w?: string }> = ({ anak, w = warna.bara }) => (
  <div style={{ fontFamily: tubuhFont, fontSize: 21, fontWeight: 600, letterSpacing: "0.22em", textTransform: "uppercase", color: w }}>{anak}</div>
);
const Angka: React.FC<{ anak: string; ukuran?: number; warnaA?: string }> = ({ anak, ukuran = 120, warnaA = warna.nyala }) => (
  <div style={{ ...angkaGaya, fontSize: ukuran, fontWeight: 600, color: warnaA, lineHeight: 1 }}>{anak}</div>
);
const Garis: React.FC<{ anak: React.ReactNode; tampil: number; lebar?: number; ukuran?: number }> = ({ anak, tampil, lebar = 620, ukuran = 26 }) => (
  <div style={{ borderLeft: `3px solid ${warna.bara}`, paddingLeft: 18, fontFamily: tubuhFont, fontSize: ukuran, color: warna.kapur, lineHeight: 1.35, maxWidth: lebar, opacity: tampil }}>
    {anak}
  </div>
);
const Peta: React.FC = () => (
  <AbsoluteFill style={{ backgroundColor: warna.jelaga }}>
    <Img src={staticFile("biaya/peta_tambang.jpg")} style={{ width: 1920, height: 1080 }} />
    <AbsoluteFill style={{ background: `linear-gradient(90deg, ${warna.jelaga} 0%, ${warna.jelaga} 33%, rgba(10,12,15,0) 42%)` }} />
  </AbsoluteFill>
);
const Panel: React.FC<{ gambar: string[]; panjang: number; dari?: number; sampai?: number; tanda?: (i: number) => string; isi?: boolean }> = ({
  gambar,
  panjang,
  dari = 0.08,
  sampai = 0.7,
  tanda,
  isi,
}) => {
  const f = useCurrentFrame();
  const pos = gambar.length === 1 ? 0 : interpolate(f, [panjang * dari, panjang * sampai], [0, gambar.length - 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const i = Math.floor(pos);
  const frac = pos - i;
  const sekarang = Math.min(gambar.length - 1, Math.round(pos));
  const gaya: React.CSSProperties = { position: "absolute", width: 1200, height: 1080, objectFit: isi ? "cover" : "contain" };
  return (
    <AbsoluteFill style={{ backgroundColor: warna.jelaga }}>
      <div style={{ position: "absolute", left: 720, top: 0, width: 1200, height: 1080, overflow: "hidden" }}>
        <Img src={staticFile(`biaya/${gambar[i]}`)} style={gaya} />
        {i + 1 < gambar.length ? <Img src={staticFile(`biaya/${gambar[i + 1]}`)} style={{ ...gaya, opacity: frac }} /> : null}
      </div>
      <AbsoluteFill style={{ background: `linear-gradient(90deg, ${warna.jelaga} 0%, ${warna.jelaga} 37%, rgba(10,12,15,0) 46%)` }} />
      {tanda ? (
        <div style={{ position: "absolute", right: 70, bottom: 110, ...angkaGaya, fontSize: 56, fontWeight: 600, color: warna.kapur, textShadow: "0 2px 18px rgba(0,0,0,0.85)" }}>
          {tanda(sekarang)}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};

/** Horizontal bar with a range: solid to lo, pale to hi. */
const Rentang: React.FC<{ label: string; lo: number; hi: number; maks: number; w: string; tampil: number; lebar?: number; labelW?: number; ukuran?: number; catatan?: string; redup?: boolean }> = ({
  label,
  lo,
  hi,
  maks,
  w,
  tampil,
  lebar = 760,
  labelW = 380,
  ukuran = 24,
  catatan,
  redup,
}) => (
  <div style={{ display: "flex", alignItems: "center", gap: 20, opacity: redup ? 0.45 : 1 }}>
    <div style={{ width: labelW, fontFamily: tubuhFont, fontSize: ukuran, color: warna.kapur, lineHeight: 1.2 }}>
      {label}
      {catatan ? <div style={{ fontSize: ukuran - 6, color: warna.abu }}>{catatan}</div> : null}
    </div>
    <div style={{ width: lebar, height: 34, background: warna.arang, position: "relative" }}>
      <div style={{ position: "absolute", width: (lebar * hi * tampil) / maks, height: 34, background: w, opacity: 0.35 }} />
      <div style={{ position: "absolute", width: (lebar * lo * tampil) / maks, height: 34, background: w }} />
    </div>
    <div style={{ ...angkaGaya, fontSize: ukuran + 2, fontWeight: 600, color: w, opacity: tampil, whiteSpace: "nowrap" }}>
      {hi === lo ? ribuan(lo) : lo < 10 ? `${koma(lo, 1)}–${koma(hi, 1)}` : rentang([lo, hi])}
    </div>
  </div>
);

/** Stacked value-added bars by year (mining + manufacturing). */
const BatangNilai: React.FC<{ tampil: (i: number) => number; W?: number; H?: number; ukuran?: number }> = ({ tampil, W = 620, H = 300, ukuran = 19 }) => {
  const thn = D.tahun;
  const bw = W / thn.length, mx = 90;
  return (
    <svg width={W} height={H + 70}>
      {thn.map((y, i) => {
        const o = tampil(i);
        const a = ((D.tambang as Record<string, number>)[y] * H * o) / mx;
        const b = ((D.olah as Record<string, number>)[y] * H * o) / mx;
        return (
          <g key={y}>
            <rect x={i * bw + bw * 0.14} y={H - a + 30} width={bw * 0.72} height={a} fill={warna.nyala} />
            <rect x={i * bw + bw * 0.14} y={H - a - b + 30} width={bw * 0.72} height={b} fill={warna.bara} />
            {(i === 0 || i === thn.length - 1) && o > 0.5 ? (
              <text x={i * bw + bw / 2} y={H - a - b + 20} fill={warna.kapur} fontSize={ukuran + 3} textAnchor="middle" fontFamily={angkaGaya.fontFamily as string} fontWeight={600}>
                {koma(NT[y], 1)}
              </text>
            ) : null}
            <text x={i * bw + bw / 2} y={H + 62} fill={warna.samar} fontSize={ukuran} textAnchor="middle" fontFamily={tubuhFont}>
              {y}
            </text>
          </g>
        );
      })}
    </svg>
  );
};
const LegNilai: React.FC<{ ukuran?: number }> = ({ ukuran = 20 }) => (
  <div style={{ display: "flex", gap: 20, fontFamily: tubuhFont, fontSize: ukuran, color: warna.abu }}>
    <span>
      <span style={{ color: warna.bara }}>■</span> industri pengolahan
    </span>
    <span>
      <span style={{ color: warna.nyala }}>■</span> pertambangan
    </span>
  </div>
);

const s25 = (D.co2_scc as Record<string, number[]>)["2025"];
const e25 = (D.co2_eu as Record<string, number[]>)["2025"];
const c25 = (D.co2_mt as Record<string, number[]>)["2025"];
const BARIS: { label: string; lo: number; hi: number; w: string; catatan?: string }[] = [
  { label: "Nilai tambah tambang + pengolahan", lo: NT["2025"], hi: NT["2025"], w: warna.nyala },
  { label: "CO₂ batu bara, biaya sosial karbon", lo: s25[0], hi: s25[1], w: warna.bara, catatan: "US EPA" },
  { label: "CO₂ batu bara, harga pasar Eropa", lo: e25[0], hi: e25[1], w: "#c9502a", catatan: "EU ETS" },
  { label: "Polusi udara, kesehatan", lo: D.kesehatan, hi: D.kesehatan, w: "#9c5a22", catatan: "indikatif" },
  { label: "Karbon hutan yang dibuka", lo: D.karbon_hutan_2025[0], hi: D.karbon_hutan_2025[1], w: "#9AA3AD", catatan: "satu kali" },
  { label: "Jasa ekosistem hutan hilang", lo: D.ekosistem_2025[0], hi: D.ekosistem_2025[1], w: "#7E8792", catatan: "per tahun" },
];

/* ---------------------------------- scenes --------------------------- */

const KartuJudul: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 4, 24);
  return (
    <Lembut panjang={panjang}>
      <Panel gambar={["malam_2025.jpg"]} panjang={panjang} />
      <Kolom jarak={26}>
        <div style={{ opacity: a, transform: `translateY(${(1 - a) * 20}px)` }}>
          <div style={{ marginBottom: 24 }}>
            <Alis anak="Bagian 5 · Ekonomi dan lingkungan" />
          </div>
          <h1 style={{ fontFamily: judulFont, fontWeight: 900, fontSize: 96, lineHeight: 0.94, letterSpacing: "-0.04em", color: warna.kapur, margin: 0 }}>
            HARGA DI
            <br />
            BALIK NIKEL
          </h1>
          <div style={{ marginTop: 28 }}>
            <Keterangan lebar={600} anak="Nilai ekonomi tambang dan smelter nikel Maluku Utara, dibandingkan dengan biaya lingkungannya." />
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Buka: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const seri = ["Apa yang menggerus hutan Maluku Utara?", "Memeriksa peta tambang nikel", "Jejak tambang di Maluku Utara", "Jejak di perairan"];
  const c = masuk(f, Math.round(panjang * 0.55), 22);
  return (
    <Lembut panjang={panjang}>
      <Peta />
      <Bkg tampil={a} />
      <Kolom jarak={22}>
        <div style={{ width: 600 }}>
          {seri.map((t, i) => (
            <div key={t} style={{ display: "flex", gap: 18, alignItems: "baseline", marginBottom: 12, opacity: masuk(f, 8 + i * 10, 18) }}>
              <span style={{ ...angkaGaya, fontSize: 26, color: warna.samar }}>{i + 1}</span>
              <span style={{ fontFamily: tubuhFont, fontSize: 26, color: warna.abu }}>{t}</span>
            </div>
          ))}
          <div style={{ display: "flex", gap: 18, alignItems: "baseline", marginTop: 10, opacity: c }}>
            <span style={{ ...angkaGaya, fontSize: 30, color: warna.bara }}>5</span>
            <Judul anak="Berapa nilainya, berapa biayanya?" ukuran={48} />
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Nilai: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const t0 = panjang * 0.15, t1 = panjang * 0.75;
  return (
    <Lembut panjang={panjang}>
      <Panel gambar={["weda_s2.jpg"]} panjang={panjang} tanda={() => "Teluk Weda, 2025"} isi />
      <Bkg sumber={T.sumberNilai} tampil={a} />
      <Kolom jarak={0}>
        <div style={{ width: 640, opacity: a }}>
          <Alis anak="Ekonomi tumbuh cepat" />
          <div style={{ marginTop: 16 }}>
            <Judul anak="Nilai tambah tambang dan pengolahan (Rp triliun)" ukuran={42} />
          </div>
          <div style={{ marginTop: 12 }}>
            <BatangNilai tampil={(i) => masuk(f, t0 + (i / 6) * (t1 - t0), 14)} />
          </div>
          <LegNilai />
        </div>
      </Kolom>
    </Lembut>
  );
};

const Cahaya: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const b = masuk(f, Math.round(panjang * 0.55), 22);
  return (
    <Lembut panjang={panjang}>
      <Panel gambar={["malam_2019.jpg", "malam_2025.jpg"]} panjang={panjang} dari={0.25} sampai={0.5} tanda={(i) => String(D.malam_tahun[i])} />
      <Bkg sumber={T.sumberMalam} tampil={a} />
      <Kolom jarak={0}>
        <div style={{ width: 620, opacity: a }}>
          <Alis anak="Terlihat dari luar angkasa" />
          <div style={{ marginTop: 16 }}>
            <Judul anak="Cahaya malam di sekitar Teluk Weda" ukuran={46} />
          </div>
          <div style={{ marginTop: 40, opacity: b }}>
            <Angka anak={`×${koma(kaliMalam, 1)}`} ukuran={140} />
            <div style={{ fontFamily: tubuhFont, fontSize: 27, color: warna.kapur, marginTop: 8 }}>lebih terang pada 2025 dibanding 2019</div>
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const BatuBara: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const b = masuk(f, Math.round(panjang * 0.35), 30);
  const c = masuk(f, Math.round(panjang * 0.6), 30);
  const K = D.kapasitas_gw as Record<string, number>;
  const H = 520, mx = 7;
  const kol = (y: string, t: number, w: string) => (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "flex-end", height: H + 90, width: 220 }}>
      <div style={{ ...angkaGaya, fontSize: 52, fontWeight: 600, color: w, opacity: t }}>{koma(K[y], 2)} GW</div>
      <div style={{ width: 160, height: (H * K[y] * t) / mx, background: w, marginTop: 10 }} />
      <div style={{ fontFamily: tubuhFont, fontSize: 24, color: warna.abu, marginTop: 12 }}>Juli {y}</div>
    </div>
  );
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Bkg sumber={T.sumberBatu} tampil={a} />
      <Kolom jarak={0}>
        <div style={{ display: "flex", gap: 100, alignItems: "center" }}>
          <div style={{ width: 640, opacity: a }}>
            <Alis anak="Listrik untuk smelter" />
            <div style={{ marginTop: 16 }}>
              <Judul anak="Pembangkit batu bara milik kawasan industri" ukuran={48} />
            </div>
            <div style={{ marginTop: 30 }}>
              <Garis anak="PLTU captive tidak masuk jaringan PLN: listriknya hanya untuk smelter di kawasan itu." tampil={b} ukuran={24} />
            </div>
          </div>
          <div style={{ display: "flex", gap: 40, alignItems: "flex-end" }}>
            {kol("2023", b, warna.abu)}
            {kol("2025", c, warna.bara)}
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Co2: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const r = [masuk(f, Math.round(panjang * 0.1), 24), masuk(f, Math.round(panjang * 0.3), 30), masuk(f, Math.round(panjang * 0.72), 24)];
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Bkg sumber={T.sumberCo2} tampil={a} />
      <Kolom jarak={26}>
        <div style={{ opacity: a }}>
          <Alis anak="2025, Rp triliun" />
          <div style={{ marginTop: 16, display: "flex", alignItems: "baseline", gap: 22 }}>
            <Angka anak={`${Math.round(c25[0])}–${Math.round(c25[1])}`} ukuran={84} warnaA={warna.bara} />
            <span style={{ fontFamily: tubuhFont, fontSize: 30, color: warna.kapur }}>juta ton CO₂ dari PLTU captive</span>
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 22, marginTop: 10 }}>
          {BARIS.slice(0, 3).map((x, i) => (
            <Rentang key={x.label} {...x} maks={175} tampil={r[i]} />
          ))}
        </div>
      </Kolom>
    </Lembut>
  );
};

const Hutan: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const c = masuk(f, Math.round(panjang * 0.6), 22);
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Bkg sumber={T.sumberHutan} tampil={a} />
      <Kolom jarak={26}>
        <Alis anak="2025, Rp triliun" />
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          {BARIS.map((x, i) => (
            <Rentang key={x.label} {...x} maks={175} tampil={i < 3 ? 1 : masuk(f, Math.round(panjang * (0.05 + (i - 3) * 0.12)), 22)} redup={i > 0 && i < 3} />
          ))}
        </div>
        <Garis anak="Biaya hutan memakai rata-rata global per hektare, dan tidak menghitung kehidupan yang bergantung pada hutan itu." tampil={c} lebar={1400} ukuran={24} />
      </Kolom>
    </Lembut>
  );
};

const Siapa: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const b = masuk(f, Math.round(panjang * 0.4), 24);
  const kartu = (judul: string, w: string, isi: [string, string][], t: number) => (
    <div style={{ width: 760, opacity: t, borderTop: `3px solid ${w}`, paddingTop: 18 }}>
      <div style={{ fontFamily: judulFont, fontWeight: 900, fontSize: 46, color: w }}>{judul}</div>
      {isi.map(([k, v]) => (
        <div key={k} style={{ marginTop: 16 }}>
          <div style={{ fontFamily: tubuhFont, fontSize: 27, fontWeight: 600, color: warna.kapur }}>{k}</div>
          <div style={{ fontFamily: tubuhFont, fontSize: 23, color: warna.abu, marginTop: 2 }}>{v}</div>
        </div>
      ))}
    </div>
  );
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Bkg sumber={T.sumberSiapa} tampil={a} />
      <Kolom jarak={0}>
        <div style={{ display: "flex", gap: 80 }}>
          {kartu(
            "Yang menikmati",
            warna.nyala,
            [
              [`Nilai tambah Rp ${koma(NT["2025"], 0)} triliun`, "upah, laba, pajak; sebagian besar laba ke pemilik di luar provinsi"],
              [`Dana bagi hasil ± Rp ${koma(D.dbh_halteng, 1)} triliun`, "untuk kabupaten penghasil, per tahun"],
              [`Royalti nikel ± Rp ${D.royalti_nasional_2025} triliun`, "untuk negara, seluruh Indonesia, 2025"],
            ],
            a,
          )}
          {kartu(
            "Yang menanggung",
            warna.bara,
            [
              ["Kerugian iklim", "dunia, termasuk Indonesia"],
              ["Polusi udara", "warga di sekitar kawasan industri"],
              ["Hutan hilang, air keruh", "warga, petani, dan nelayan di sekitar tambang"],
            ],
            b,
          )}
        </div>
      </Kolom>
    </Lembut>
  );
};

const Tutup: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 4, 22);
  const b = masuk(f, Math.round(panjang * 0.3), 24);
  const d = masuk(f, Math.round(panjang * 0.6), 24);
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Kolom jarak={28}>
        <h1 style={{ fontFamily: judulFont, fontWeight: 900, fontSize: 62, lineHeight: 1.06, color: warna.kapur, margin: 0, opacity: a, maxWidth: 1500 }}>
          Biaya terbesar bukan yang terlihat di hutan,
        </h1>
        <h2 style={{ fontFamily: judulFont, fontWeight: 900, fontSize: 62, lineHeight: 1.06, color: warna.bara, margin: 0, opacity: b, maxWidth: 1500 }}>
          melainkan asap dari pembangkit batu bara.
        </h2>
        <div style={{ opacity: d, borderLeft: `3px solid ${warna.garis}`, paddingLeft: 20, fontFamily: tubuhFont, fontSize: 25, color: warna.abu, lineHeight: 1.45, maxWidth: 1450, marginTop: 10 }}>
          Ini bukan neraca laba rugi. Nilai tambah bukan laba, dan biaya sosial karbon adalah kerugian global, bukan tagihan. Rentang ketidakpastian besar.
        </div>
      </Kolom>
    </Lembut>
  );
};

const BARIS_SUMBER: [string, string][] = [
  ["Nilai tambah", "BPS, PDRB Provinsi Maluku Utara menurut lapangan usaha (harga berlaku), 2017–2025"],
  ["PLTU captive", "CREA & Global Energy Monitor (Jan 2026); Climate Rights International (Jun 2025); Ember (Sep 2026)"],
  ["Harga karbon", "US EPA (2023) biaya sosial karbon, diskonto 2%; EU ETS 2025 (ICAP)"],
  ["Hutan", "kehilangan hutan karena tambang: Hansen/UMD × WRI/Google; biomassa IPCC 2006/2019; jasa ekosistem de Groot (2012), Costanza (2014)"],
  ["Kesehatan", "CREA & CELIOS (2024), proyeksi 3 provinsi, diskalakan dengan kapasitas (indikatif)"],
  ["Asumsi", "USD 1 = Rp 16.000; harga dinyatakan dalam USD 2025; rincian di economics/RESULTS.md · analisis November 2026"],
];

const KartuSumber: React.FC<{ panjang: number }> = () => {
  const f = useCurrentFrame();
  const a = masuk(f, 4, 20);
  return (
    <AbsoluteFill style={{ backgroundColor: warna.jelaga, opacity: a }}>
      <Kolom jarak={16}>
        <Alis anak="Sumber data" />
        <div style={{ display: "flex", flexDirection: "column", gap: 10, width: 1680 }}>
          {BARIS_SUMBER.map(([k, v]) => (
            <div key={k} style={{ display: "flex", gap: 28, alignItems: "baseline" }}>
              <div style={{ width: 220, fontFamily: tubuhFont, fontSize: 23, fontWeight: 600, color: warna.kapur }}>{k}</div>
              <div style={{ fontFamily: tubuhFont, fontSize: 23, color: warna.abu }}>{v}</div>
            </div>
          ))}
        </div>
        <div style={{ marginTop: 10, paddingTop: 16, borderTop: `2px solid ${warna.bara}`, fontFamily: tubuhFont, fontSize: 22, color: warna.kapur, lineHeight: 1.5, maxWidth: 1680 }}>
          Biaya kualitas air dan keanekaragaman hayati belum dinilai dalam rupiah. Tidak ada perusahaan yang disebut.
        </div>
      </Kolom>
    </AbsoluteFill>
  );
};

/* --------------------------------- film ------------------------------ */

const ADEGAN: Record<string, React.FC<{ panjang: number }>> = {
  "01-buka": Buka,
  "02-nilai": Nilai,
  "03-cahaya": Cahaya,
  "04-batubara": BatuBara,
  "05-co2": Co2,
  "06-hutan": Hutan,
  "07-siapa": Siapa,
  "08-tutup": Tutup,
};

export const BiayaFilm: React.FC = () => {
  const J = JADWAL_BIAYA;
  return (
    <AbsoluteFill style={{ backgroundColor: warna.jelaga }}>
      <Audio src={staticFile(`${AUDIO}/musik-biaya.mp3`)} />
      <Sequence durationInFrames={J.JUDUL_FRAME}>
        <KartuJudul panjang={J.JUDUL_FRAME} />
      </Sequence>
      {J.adegan.map((a) => {
        const K = ADEGAN[a.id];
        return (
          <Sequence key={a.id} from={a.mulai} durationInFrames={a.panjang}>
            <K panjang={a.panjang} />
            <Audio src={staticFile(`${AUDIO}/${a.id}.mp3`)} />
          </Sequence>
        );
      })}
      <Sequence from={J.akhirNarasi} durationInFrames={J.TUTUP_FRAME}>
        <KartuSumber panjang={J.TUTUP_FRAME} />
      </Sequence>
    </AbsoluteFill>
  );
};

/* ------------------------------ infographic --------------------------- */

const Kotak: React.FC<{ judul: string; children: React.ReactNode }> = ({ judul, children }) => (
  <div style={{ borderTop: `2px solid ${warna.garis}`, paddingTop: 18 }}>
    <div style={{ fontFamily: tubuhFont, fontSize: 20, fontWeight: 600, letterSpacing: "0.16em", textTransform: "uppercase", color: warna.bara, marginBottom: 12 }}>{judul}</div>
    {children}
  </div>
);

/** Two 1080x1350 pages: 1 = value vs costs in 2025, 2 = coal, night lights, who gains and who pays. */
export const InfografisBiaya: React.FC<{ halaman?: 1 | 2 }> = ({ halaman = 1 }) => {
  const kecil = { fontFamily: tubuhFont, fontSize: 20, color: warna.abu, lineHeight: 1.4 } as React.CSSProperties;
  const kepala = (
    <div style={{ borderTop: `3px solid ${warna.bara}`, paddingTop: 16, display: "flex", justifyContent: "space-between" }}>
      <Alis anak="Harga di Balik Nikel · bagian 5" />
      <span style={{ fontFamily: tubuhFont, fontSize: 19, letterSpacing: "0.18em", color: warna.abu, textTransform: "uppercase" }}>
        {T.waktu} · {halaman}/2
      </span>
    </div>
  );
  const kaki = (
    <div style={{ ...kecil, fontSize: 15, borderTop: `1px solid ${warna.garis}`, paddingTop: 12, marginTop: "auto" }}>
      {BARIS_SUMBER.map(([k, v]) => `${k}: ${v}`).join(" · ")}. Tidak ada perusahaan yang disebut.
    </div>
  );
  if (halaman === 1) {
    return (
      <AbsoluteFill style={{ backgroundColor: warna.jelaga, padding: "46px 54px 40px", display: "flex", flexDirection: "column", gap: 22 }}>
        <div>
          {kepala}
          <h1 style={{ fontFamily: judulFont, fontWeight: 900, fontSize: 54, lineHeight: 1, letterSpacing: "-0.03em", color: warna.kapur, margin: "22px 0 0" }}>
            Nilai nikel Maluku Utara vs biaya lingkungannya, 2025
          </h1>
        </div>
        <Kotak judul="Rp triliun per tahun · batang pucat = rentang">
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {BARIS.map((x) => (
              <Rentang key={x.label} {...x} maks={175} tampil={1} lebar={420} labelW={330} ukuran={20} />
            ))}
          </div>
        </Kotak>
        <div style={{ ...kecil, color: warna.kapur, fontSize: 23, lineHeight: 1.45 }}>
          Kerugian iklim dari {Math.round(c25[0])}–{Math.round(c25[1])} juta ton CO₂ batu bara, dinilai dengan biaya sosial karbon, <span style={{ color: warna.bara, fontWeight: 600 }}>lebih besar dari seluruh nilai tambah</span> tambang dan pengolahan nikel.
        </div>
        <Kotak judul="Nilai tambah per tahun (Rp triliun)">
          <BatangNilai tampil={() => 1} W={970} H={170} ukuran={18} />
          <LegNilai ukuran={18} />
        </Kotak>
        <div style={{ ...kecil, fontSize: 18 }}>Bukan neraca laba rugi: nilai tambah bukan laba, dan biaya sosial karbon adalah kerugian global, bukan tagihan. Air keruh dan keanekaragaman hayati belum dinilai.</div>
        {kaki}
      </AbsoluteFill>
    );
  }
  const K = D.kapasitas_gw as Record<string, number>;
  return (
    <AbsoluteFill style={{ backgroundColor: warna.jelaga, padding: "46px 54px 40px", display: "flex", flexDirection: "column", gap: 20 }}>
      <div>
        {kepala}
        <h1 style={{ fontFamily: judulFont, fontWeight: 900, fontSize: 50, lineHeight: 1, letterSpacing: "-0.03em", color: warna.kapur, margin: "22px 0 0" }}>
          Batu bara, cahaya, dan siapa yang menanggung
        </h1>
      </div>
      <Kotak judul={`Cahaya malam sekitar Teluk Weda · ×${koma(kaliMalam, 1)}`}>
        <div style={{ display: "flex", gap: 14 }}>
          {D.malam_tahun.map((y) => (
            <div key={y}>
              <Img src={staticFile(`biaya/malam_${y}.jpg`)} style={{ width: 478, height: 240, objectFit: "cover" }} />
              <div style={{ ...angkaGaya, fontSize: 24, fontWeight: 600, color: warna.kapur, marginTop: 4 }}>{y}</div>
            </div>
          ))}
        </div>
      </Kotak>
      <Kotak judul="PLTU captive Maluku Utara">
        <div style={{ display: "flex", gap: 50, alignItems: "baseline" }}>
          <div>
            <Angka anak={`${koma(K["2023"], 2)} → ${koma(K["2025"], 2)} GW`} ukuran={44} warnaA={warna.bara} />
            <div style={{ ...kecil, fontSize: 19 }}>Juli 2023 → Juli 2025</div>
          </div>
          <div style={{ ...kecil, color: warna.kapur, fontSize: 21 }}>
            CO₂: {(D.co2_mt as Record<string, number[]>)["2023"].map((v) => koma(v, 0)).join("–")} juta ton (2023) → {c25.map((v) => koma(v, 0)).join("–")} juta ton (2025)
          </div>
        </div>
      </Kotak>
      <div style={{ display: "flex", gap: 30 }}>
        <div style={{ width: 470 }}>
          <Kotak judul="Yang menikmati">
            <div style={{ ...kecil, color: warna.kapur, fontSize: 20 }}>
              Nilai tambah Rp {koma(NT["2025"], 0)} triliun (upah, laba, pajak; sebagian besar laba ke pemilik di luar provinsi). Dana bagi hasil kabupaten penghasil ± Rp {koma(D.dbh_halteng, 1)} triliun per tahun.
            </div>
          </Kotak>
        </div>
        <div style={{ width: 470 }}>
          <Kotak judul="Yang menanggung">
            <div style={{ ...kecil, color: warna.kapur, fontSize: 20 }}>Kerugian iklim: dunia. Polusi udara, hutan hilang, dan air keruh: warga, petani, dan nelayan di sekitar tambang dan kawasan industri.</div>
          </Kotak>
        </div>
      </div>
      {kaki}
    </AbsoluteFill>
  );
};
