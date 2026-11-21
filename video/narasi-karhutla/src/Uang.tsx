/**
 * "Ke Mana Uangnya?" — part 6 of the North Maluku series, plus a two-page infographic (InfografisUang):
 * did the nickel boom's value reach the people of North Maluku? Benefits (jobs, falling poverty) shown next to
 * the gap between production and household spending, and where the rest goes.
 *
 *   jobs       manufacturing employment 28,365 (Aug 2018) -> 163,650 (Feb 2025); park >81,000 (company)
 *   poverty    2019 -> 2025: Halteng 14.12 -> 9.16, Haltim 15.39 -> 10.54, Halsel 5.03 -> 4.81; non-mining -0.75 pp
 *   gap        Halteng production per person x19.7 (2019-2025), household spending x1.71; 3-5 per 100
 *   where      98 % of realised investment foreign; regency budget 3.3 % of its production; tax holidays
 *
 * Indonesian only (Bian). Every figure is from uangData.json (scripts/uang_film_assets.py, from
 * output/malut_forest/welfare/SOURCES.md). No company is named.
 */

import React from "react";
import { AbsoluteFill, Audio, Img, Sequence, staticFile, useCurrentFrame } from "remotion";
import { JADWAL_UANG } from "./jadwalUang";
import { Bingkai, Judul, Keterangan, Kolom, LatarDiam, Lembut, masuk } from "./komponen";
import { angkaGaya, judulFont, koma, ribuan, tubuhFont, warna } from "./teema";
import D from "./uangData.json";

const AUDIO = "audio/uang";
const MINING = ["Halmahera Tengah", "Halmahera Selatan", "Halmahera Timur"];
const POV = D.poverty as Record<string, number[]>;
const HP = D.halteng_pdrb_cap as Record<string, number>;
const HS = D.halteng_spend_year_thousand as Record<string, number>;
const JOBS = D.manuf_jobs as Record<string, number>;
const per100 = D.halteng_spend_per_100_production;

const T = {
  kiri: "Nikel Maluku Utara: ke mana uangnya?",
  waktu: "November 2026",
  labelSumber: "Sumber",
  sumberManfaat: "BPS Sakernas Agustus 2018–2022; BI (Feb 2025) · pekerja kawasan: pernyataan perusahaan (Juni 2025)",
  sumberMiskin: "BPS, persentase penduduk miskin (Maret), 2019 dan 2025",
  sumberJurang: "BPS, PDRB per kapita atas dasar harga berlaku · Susenas, pengeluaran per kapita (via Databoks)",
  sumberKemana: "BI, realisasi investasi Q2 2026 · APBD Halmahera Tengah 2026 (via Databoks) · keringanan pajak: Kemenkeu, PMK 130/2020",
  sumberBatas: "Penduduk: BPS (Susenas) dan Dukcapil (via Databoks)",
};

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
    <Img src={staticFile("uang/peta_tambang.jpg")} style={{ width: 1920, height: 1080 }} />
    <AbsoluteFill style={{ background: `linear-gradient(90deg, ${warna.jelaga} 0%, ${warna.jelaga} 33%, rgba(10,12,15,0) 42%)` }} />
  </AbsoluteFill>
);
const Gambar: React.FC<{ src: string; tanda?: string; isi?: boolean }> = ({ src, tanda, isi }) => (
  <AbsoluteFill style={{ backgroundColor: warna.jelaga }}>
    <div style={{ position: "absolute", left: 720, top: 0, width: 1200, height: 1080, overflow: "hidden" }}>
      <Img src={staticFile(`uang/${src}`)} style={{ position: "absolute", width: 1200, height: 1080, objectFit: isi ? "cover" : "contain" }} />
    </div>
    <AbsoluteFill style={{ background: `linear-gradient(90deg, ${warna.jelaga} 0%, ${warna.jelaga} 37%, rgba(10,12,15,0) 46%)` }} />
    {tanda ? (
      <div style={{ position: "absolute", right: 70, bottom: 110, ...angkaGaya, fontSize: 52, fontWeight: 600, color: warna.kapur, textShadow: "0 2px 18px rgba(0,0,0,0.85)" }}>{tanda}</div>
    ) : null}
  </AbsoluteFill>
);

/** Dumbbell chart: poverty 2019 (grey dot) -> 2025 (coloured dot) per regency. */
const Halter: React.FC<{ tampil: (i: number) => number; W?: number; baris?: number; ukuran?: number; labelW?: number }> = ({ tampil, W = 1100, baris = 52, ukuran = 22, labelW = 300 }) => {
  const names = Object.keys(POV).sort((a, b) => POV[b][0] - POV[a][0]);
  const mx = 20, plot = W - labelW - 60;   // 20 % leaves room for the value labels right of the dots
  const X = (v: number) => labelW + (plot * v) / mx;
  return (
    <svg width={W} height={names.length * baris + 50}>
      {[0, 5, 10, 15, 20].map((v) => (
        <g key={v}>
          <line x1={X(v)} x2={X(v)} y1={0} y2={names.length * baris} stroke={warna.garis} />
          <text x={X(v)} y={names.length * baris + 30} fill={warna.samar} fontSize={ukuran - 3} textAnchor="middle" fontFamily={tubuhFont}>
            {v}%
          </text>
        </g>
      ))}
      {names.map((n, i) => {
        const [a, b] = POV[n];
        const o = tampil(i);
        const m = MINING.includes(n);
        const y = i * baris + baris / 2;
        const bx = X(a) + (X(b) - X(a)) * o;
        return (
          <g key={n}>
            <text x={labelW - 16} y={y + 7} fill={m ? warna.kapur : warna.abu} fontSize={ukuran} fontWeight={m ? 600 : 400} textAnchor="end" fontFamily={tubuhFont}>
              {n}
            </text>
            <line x1={X(a)} x2={bx} y1={y} y2={y} stroke={m ? warna.nyala : "#5A626C"} strokeWidth={4} />
            <circle cx={X(a)} cy={y} r={8} fill="#7E8792" />
            <circle cx={bx} cy={y} r={9} fill={m ? warna.nyala : "#9AA3AD"} opacity={o} />
            {o > 0.9 ? (
              <text x={Math.max(X(a), X(b)) + 18} y={y + 7} fill={m ? warna.nyala : warna.abu} fontSize={ukuran - 2} fontFamily={angkaGaya.fontFamily as string}>
                {koma(a, 1)} → {koma(b, 1)}
              </text>
            ) : null}
          </g>
        );
      })}
    </svg>
  );
};

/** Two horizontal bars on one scale: production per person vs household spending per person (Rp juta/yr). */
const Jurang: React.FC<{ tahun: "2019" | "2025"; tampil: number; lebar?: number; ukuran?: number }> = ({ tahun, tampil, lebar = 1150, ukuran = 24 }) => {
  const prod = HP[tahun] / 1000, belanja = HS[tahun] / 1000, mx = 880;
  const bar = (v: number, w: string, label: string) => (
    <div style={{ display: "flex", alignItems: "center", gap: 18, marginTop: 8 }}>
      <div style={{ width: 300, fontFamily: tubuhFont, fontSize: ukuran, color: warna.abu }}>{label}</div>
      <div style={{ width: Math.max(4, (lebar * v * tampil) / mx), height: 34, background: w }} />
      <div style={{ ...angkaGaya, fontSize: ukuran + 2, fontWeight: 600, color: w, opacity: tampil }}>Rp {ribuan(v)} juta</div>
    </div>
  );
  return (
    <div>
      <div style={{ ...angkaGaya, fontSize: ukuran + 6, color: warna.kapur, fontWeight: 600 }}>{tahun}</div>
      {bar(prod, warna.nyala, "Nilai produksi per orang")}
      {bar(belanja, warna.bara, "Belanja rumah tangga per orang")}
    </div>
  );
};

/* ---------------------------------- scenes --------------------------- */

const KartuJudul: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 4, 24);
  return (
    <Lembut panjang={panjang}>
      <Gambar src="malam_2025.jpg" />
      <Kolom jarak={26}>
        <div style={{ opacity: a, transform: `translateY(${(1 - a) * 20}px)` }}>
          <div style={{ marginBottom: 24 }}>
            <Alis anak="Bagian 6 · Kesejahteraan dan pembagian" />
          </div>
          <h1 style={{ fontFamily: judulFont, fontWeight: 900, fontSize: 100, lineHeight: 0.94, letterSpacing: "-0.04em", color: warna.kapur, margin: 0 }}>
            KE MANA
            <br />
            UANGNYA?
          </h1>
          <div style={{ marginTop: 28 }}>
            <Keterangan lebar={600} anak="Apakah nilai dari nikel sampai ke warga Maluku Utara?" />
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Buka: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const seri = ["Apa yang menggerus hutan Maluku Utara?", "Memeriksa peta tambang nikel", "Jejak tambang di Maluku Utara", "Jejak di perairan", "Harga di balik nikel"];
  const c = masuk(f, Math.round(panjang * 0.5), 22);
  return (
    <Lembut panjang={panjang}>
      <Peta />
      <Bkg tampil={a} />
      <Kolom jarak={22}>
        <div style={{ width: 600 }}>
          {seri.map((t, i) => (
            <div key={t} style={{ display: "flex", gap: 18, alignItems: "baseline", marginBottom: 10, opacity: masuk(f, 6 + i * 8, 16) }}>
              <span style={{ ...angkaGaya, fontSize: 24, color: warna.samar }}>{i + 1}</span>
              <span style={{ fontFamily: tubuhFont, fontSize: 24, color: warna.abu }}>{t}</span>
            </div>
          ))}
          <div style={{ display: "flex", gap: 18, alignItems: "baseline", marginTop: 10, opacity: c }}>
            <span style={{ ...angkaGaya, fontSize: 30, color: warna.bara }}>6</span>
            <Judul anak="Ke mana uangnya pergi?" ukuran={50} />
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Manfaat: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const c = masuk(f, Math.round(panjang * 0.62), 22);
  const k = Object.keys(JOBS);
  const mx = 170000, H = 300, bw = 140;
  return (
    <Lembut panjang={panjang}>
      <Gambar src="weda_s2.jpg" tanda="Teluk Weda, 2025" isi />
      <Bkg sumber={T.sumberManfaat} tampil={a} />
      <Kolom jarak={0}>
        <div style={{ width: 640, opacity: a }}>
          <Alis anak="Ada manfaat yang nyata" />
          <div style={{ marginTop: 16 }}>
            <Judul anak="Pekerja industri pengolahan, Maluku Utara" ukuran={42} />
          </div>
          <svg width={600} height={H + 80} style={{ marginTop: 10 }}>
            {k.map((x, i) => {
              const o = masuk(f, Math.round(panjang * (0.08 + i * 0.1)), 16);
              const h = (H * JOBS[x] * o) / mx;
              return (
                <g key={x}>
                  <rect x={i * bw + 14} y={H - h + 34} width={bw * 0.7} height={h} fill={i === k.length - 1 ? warna.nyala : warna.bara} />
                  {o > 0.6 ? (
                    <text x={i * bw + 14 + bw * 0.35} y={H - h + 24} fill={warna.kapur} fontSize={22} textAnchor="middle" fontFamily={angkaGaya.fontFamily as string} fontWeight={600}>
                      {ribuan(Math.round(JOBS[x] / 1000))} rb
                    </text>
                  ) : null}
                  <text x={i * bw + 14 + bw * 0.35} y={H + 66} fill={warna.samar} fontSize={19} textAnchor="middle" fontFamily={tubuhFont}>
                    {x}
                  </text>
                </g>
              );
            })}
          </svg>
          <Garis anak={`Kawasan industri Teluk Weda: lebih dari ${ribuan(D.park.workers)} pekerja; ${D.park.malut_pct + D.park.around_mine_pct}% dari Maluku Utara, menurut perusahaan.`} tampil={c} ukuran={23} />
        </div>
      </Kolom>
    </Lembut>
  );
};

const Miskin: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const c = masuk(f, Math.round(panjang * 0.7), 22);
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Bkg sumber={T.sumberMiskin} tampil={a} />
      <Kolom jarak={0}>
        <div style={{ display: "flex", gap: 60, alignItems: "center" }}>
          <div style={{ width: 520, opacity: a }}>
            <Alis anak="Kemiskinan turun" />
            <div style={{ marginTop: 16 }}>
              <Judul anak="Penduduk miskin, 2019 → 2025" ukuran={46} />
            </div>
            <div style={{ fontFamily: tubuhFont, fontSize: 22, color: warna.abu, marginTop: 14 }}>
              <span style={{ color: warna.nyala }}>●</span> kabupaten tambang · <span style={{ color: "#9AA3AD" }}>●</span> lainnya
            </div>
            <div style={{ marginTop: 30 }}>
              <Garis
                anak={`Kabupaten tanpa tambang turun rata-rata ${koma(-D.poverty_change_2019_2025_pp.nonmining_mean, 1)} poin. Halmahera Tengah dan Timur turun hampir 5 poin, tetapi tetap di atas rata-rata provinsi (${koma(D.poverty_province[1], 1)}%).`}
                tampil={c}
                ukuran={23}
                lebar={500}
              />
            </div>
          </div>
          <Halter tampil={(i) => masuk(f, Math.round(panjang * 0.1) + i * 6, 18)} W={1060} baris={54} />
        </div>
      </Kolom>
    </Lembut>
  );
};

const JurangAdegan: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const b = masuk(f, Math.round(panjang * 0.12), 26);
  const c = masuk(f, Math.round(panjang * 0.35), 30);
  const d = masuk(f, Math.round(panjang * 0.7), 22);
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Bkg sumber={T.sumberJurang} tampil={a} />
      <Kolom jarak={34}>
        <div style={{ opacity: a }}>
          <Alis anak="Halmahera Tengah, per orang per tahun" />
          <div style={{ marginTop: 16 }}>
            <Judul anak="Produksi melonjak, belanja warga tidak" ukuran={52} />
          </div>
        </div>
        <Jurang tahun="2019" tampil={b} />
        <Jurang tahun="2025" tampil={c} />
        <div style={{ opacity: d, display: "flex", gap: 30, alignItems: "baseline" }}>
          <Angka anak={`Rp ${per100[0].toFixed(0)}–${per100[1].toFixed(0)}`} ukuran={84} warnaA={warna.bara} />
          <div style={{ fontFamily: tubuhFont, fontSize: 28, color: warna.kapur, maxWidth: 800 }}>dibelanjakan rumah tangga warga dari setiap Rp 100 yang diproduksi (2025)</div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Kemana: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const F = D.fiscal;
  const blok = (angka: string, teks: string, t: number, w: string) => (
    <div style={{ opacity: t, borderTop: `2px solid ${warna.garis}`, paddingTop: 14, width: 520 }}>
      <Angka anak={angka} ukuran={80} warnaA={w} />
      <div style={{ fontFamily: tubuhFont, fontSize: 25, color: warna.kapur, marginTop: 10, lineHeight: 1.35 }}>{teks}</div>
    </div>
  );
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Bkg sumber={T.sumberKemana} tampil={a} />
      <Kolom jarak={36}>
        <div style={{ opacity: a }}>
          <Alis anak="Ke mana sisanya?" />
        </div>
        <div style={{ display: "flex", gap: 60 }}>
          {blok(`${koma(D.pma_share_pct, 0)}%`, "investasi di Maluku Utara berasal dari luar negeri (Q2 2026)", masuk(f, Math.round(panjang * 0.05), 22), warna.bara)}
          {blok("tax holiday", "keringanan pajak penghasilan bertahun-tahun untuk sebagian smelter", masuk(f, Math.round(panjang * 0.3), 22), warna.nyala)}
          {blok(`${koma(F.apbd_share_pct, 1)}%`, `anggaran Kabupaten Halmahera Tengah (Rp ${koma(F.apbd_halteng_2026_rp_bn / 1000, 1)} triliun) dibanding nilai produksinya (Rp ${ribuan(F.pdrb_halteng_2025_rp_bn / 1000)} triliun)`, masuk(f, Math.round(panjang * 0.6), 22), warna.kapur)}
        </div>
      </Kolom>
    </Lembut>
  );
};

const China: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 4, 20);
  const rows: [string, string, string][] = [
    ["Pemilik pabrik", "perusahaan dalam negeri", "sebagian besar modal asing"],
    ["Laba", "ditanam kembali di dalam negeri", "mengalir ke pemilik modal, sebagian besar di luar provinsi"],
    ["Teknologi", "dipelajari, kini membuat smelter sendiri", "dibawa pemilik"],
    ["Polusi", "dibersihkan setelah kaya", "ditanggung warga sekitar"],
  ];
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Kolom jarak={14}>
        <div style={{ opacity: a, display: "flex", gap: 30, fontFamily: tubuhFont, fontSize: 24, color: warna.abu, letterSpacing: "0.16em", textTransform: "uppercase" }}>
          <div style={{ width: 300 }} />
          <div style={{ width: 600, color: warna.abu }}>Tiongkok, sejak 1978</div>
          <div style={{ width: 640, color: warna.bara }}>Nikel Maluku Utara</div>
        </div>
        {rows.map(([k, c, m], i) => (
          <div key={k} style={{ display: "flex", gap: 30, opacity: masuk(f, Math.round(panjang * (0.08 + i * 0.16)), 18), borderTop: `2px solid ${warna.garis}`, paddingTop: 16 }}>
            <div style={{ width: 300, fontFamily: judulFont, fontWeight: 800, fontSize: 36, color: warna.kapur }}>{k}</div>
            <div style={{ width: 600, fontFamily: tubuhFont, fontSize: 28, color: warna.abu }}>{c}</div>
            <div style={{ width: 640, fontFamily: tubuhFont, fontSize: 28, color: warna.kapur }}>{m}</div>
          </div>
        ))}
      </Kolom>
    </Lembut>
  );
};

const Batas: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 4, 20);
  const isi: [string, string][] = [
    ["Jumlah penduduk berbeda", "BPS sekitar 61 ribu (2025), catatan sipil 106 ribu (2024): produksi per orang 19 sampai 33 kali belanja warga"],
    ["Pekerja pendatang", "survei rumah tangga tidak mencakup sebagian besar pekerja kawasan industri"],
    ["Data tidak lengkap", "kemiskinan Halmahera Tengah 2023 tidak ditemukan; sebagian angka 2023–2024 dari sumber sekunder"],
  ];
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Bkg sumber={T.sumberBatas} tampil={a} />
      <Kolom jarak={28}>
        <div style={{ opacity: a }}>
          <Alis anak="Batas angka ini" />
        </div>
        {isi.map(([k, v], i) => (
          <div key={k} style={{ opacity: masuk(f, Math.round(panjang * (0.1 + i * 0.25)), 20), borderTop: `2px solid ${warna.garis}`, paddingTop: 16, maxWidth: 1450 }}>
            <div style={{ fontFamily: judulFont, fontWeight: 800, fontSize: 42, color: warna.kapur }}>{k}</div>
            <div style={{ fontFamily: tubuhFont, fontSize: 27, color: warna.abu, marginTop: 6 }}>{v}</div>
          </div>
        ))}
      </Kolom>
    </Lembut>
  );
};

const Tutup: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 4, 22);
  const b = masuk(f, Math.round(panjang * 0.4), 24);
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Kolom jarak={28}>
        <h1 style={{ fontFamily: judulFont, fontWeight: 900, fontSize: 60, lineHeight: 1.08, color: warna.kapur, margin: 0, opacity: a, maxWidth: 1500 }}>
          Ini bukan menolak pembangunan. Pertanyaannya: siapa yang mendapat manfaat, dan siapa yang menanggung biayanya?
        </h1>
        <h2 style={{ fontFamily: judulFont, fontWeight: 900, fontSize: 52, lineHeight: 1.1, color: warna.bara, margin: 0, opacity: b, maxWidth: 1500 }}>
          Produksinya melonjak, tetapi sebagian besar nilainya tidak tinggal di Maluku Utara.
        </h2>
      </Kolom>
    </Lembut>
  );
};

const BARIS_SUMBER: [string, string][] = [
  ["PDRB", "BPS, PDRB Kabupaten/Kota 2021–2025 dan Maluku Utara Dalam Angka (harga berlaku)"],
  ["Kemiskinan", "BPS, persentase penduduk miskin Maret 2019 dan 2025 (Data dan Informasi Kemiskinan 2025)"],
  ["Belanja warga", "Susenas, pengeluaran per kapita Halmahera Tengah (via Databoks); kabupaten lain 2025 dari ringkasan pencarian"],
  ["Pekerjaan", "BPS Sakernas Agustus 2018–2022; Bank Indonesia (Feb 2025); pekerja kawasan: pernyataan perusahaan (Juni 2025)"],
  ["Investasi, anggaran", "Bank Indonesia, Laporan Perekonomian Maluku Utara Agustus 2026; APBD via Databoks; keringanan pajak: PMK 130/2020"],
  ["Catatan", "Tiongkok: reformasi ekonomi sejak 1978 · rincian di output/malut_forest/welfare/SOURCES.md · analisis November 2026"],
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
              <div style={{ width: 240, fontFamily: tubuhFont, fontSize: 23, fontWeight: 600, color: warna.kapur }}>{k}</div>
              <div style={{ fontFamily: tubuhFont, fontSize: 23, color: warna.abu }}>{v}</div>
            </div>
          ))}
        </div>
        <div style={{ marginTop: 10, paddingTop: 16, borderTop: `2px solid ${warna.bara}`, fontFamily: tubuhFont, fontSize: 22, color: warna.kapur, lineHeight: 1.5, maxWidth: 1680 }}>
          Nilai produksi (PDRB) dan belanja rumah tangga adalah ukuran yang berbeda; perbandingannya menunjukkan skala, bukan neraca. Tidak ada perusahaan yang disebut.
        </div>
      </Kolom>
    </AbsoluteFill>
  );
};

const ADEGAN: Record<string, React.FC<{ panjang: number }>> = {
  "01-buka": Buka,
  "02-manfaat": Manfaat,
  "03-miskin": Miskin,
  "04-jurang": JurangAdegan,
  "05-kemana": Kemana,
  "06-china": China,
  "07-batas": Batas,
  "08-tutup": Tutup,
};

export const UangFilm: React.FC = () => {
  const J = JADWAL_UANG;
  return (
    <AbsoluteFill style={{ backgroundColor: warna.jelaga }}>
      <Audio src={staticFile(`${AUDIO}/musik-uang.mp3`)} />
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

/** Two 1080x1350 pages: 1 = the benefits (jobs, poverty), 2 = the gap and where the value goes. */
export const InfografisUang: React.FC<{ halaman?: 1 | 2 }> = ({ halaman = 1 }) => {
  const kecil = { fontFamily: tubuhFont, fontSize: 20, color: warna.abu, lineHeight: 1.4 } as React.CSSProperties;
  const kepala = (
    <div style={{ borderTop: `3px solid ${warna.bara}`, paddingTop: 16, display: "flex", justifyContent: "space-between" }}>
      <Alis anak="Ke Mana Uangnya? · bagian 6" />
      <span style={{ fontFamily: tubuhFont, fontSize: 19, letterSpacing: "0.18em", color: warna.abu, textTransform: "uppercase" }}>
        {T.waktu} · {halaman}/2
      </span>
    </div>
  );
  const kaki = (
    <div style={{ ...kecil, fontSize: 15, borderTop: `1px solid ${warna.garis}`, paddingTop: 12, marginTop: "auto" }}>
      {BARIS_SUMBER.slice(0, 5).map(([k, v]) => `${k}: ${v}`).join(" · ")}. Tidak ada perusahaan yang disebut.
    </div>
  );
  if (halaman === 1) {
    const k = Object.keys(JOBS);
    return (
      <AbsoluteFill style={{ backgroundColor: warna.jelaga, padding: "46px 54px 40px", display: "flex", flexDirection: "column", gap: 20 }}>
        <div>
          {kepala}
          <h1 style={{ fontFamily: judulFont, fontWeight: 900, fontSize: 56, lineHeight: 1, letterSpacing: "-0.03em", color: warna.kapur, margin: "22px 0 0" }}>
            Ada manfaat: pekerjaan dan kemiskinan turun
          </h1>
        </div>
        <Kotak judul="Pekerja industri pengolahan, Maluku Utara">
          <div style={{ display: "flex", gap: 30, alignItems: "flex-end" }}>
            {k.map((x, i) => (
              <div key={x} style={{ width: 200 }}>
                <div style={{ ...angkaGaya, fontSize: 30, fontWeight: 600, color: i === k.length - 1 ? warna.nyala : warna.kapur }}>{ribuan(Math.round(JOBS[x] / 1000))} rb</div>
                <div style={{ height: (150 * JOBS[x]) / 170000, background: i === k.length - 1 ? warna.nyala : warna.bara, marginTop: 6 }} />
                <div style={{ ...kecil, fontSize: 18, marginTop: 6 }}>{x}</div>
              </div>
            ))}
          </div>
          <div style={{ ...kecil, color: warna.kapur, fontSize: 20, marginTop: 10 }}>
            Kawasan industri Teluk Weda: lebih dari {ribuan(D.park.workers)} pekerja, {D.park.malut_pct + D.park.around_mine_pct}% dari Maluku Utara (menurut perusahaan).
          </div>
        </Kotak>
        <Kotak judul="Penduduk miskin (%), 2019 → 2025">
          <Halter tampil={() => 1} W={970} baris={44} ukuran={19} labelW={260} />
          <div style={{ ...kecil, fontSize: 19, color: warna.kapur }}>
            Turun paling cepat di Halmahera Tengah dan Timur (hampir 5 poin), tetapi tetap di atas rata-rata provinsi. Di Halmahera Selatan hampir tidak berubah.
          </div>
        </Kotak>
        {kaki}
      </AbsoluteFill>
    );
  }
  const F = D.fiscal;
  return (
    <AbsoluteFill style={{ backgroundColor: warna.jelaga, padding: "46px 54px 40px", display: "flex", flexDirection: "column", gap: 20 }}>
      <div>
        {kepala}
        <h1 style={{ fontFamily: judulFont, fontWeight: 900, fontSize: 54, lineHeight: 1, letterSpacing: "-0.03em", color: warna.kapur, margin: "22px 0 0" }}>
          Produksi melonjak, belanja warga tidak
        </h1>
      </div>
      <Kotak judul="Halmahera Tengah, per orang per tahun">
        <Jurang tahun="2019" tampil={1} lebar={560} ukuran={20} />
        <div style={{ height: 12 }} />
        <Jurang tahun="2025" tampil={1} lebar={560} ukuran={20} />
        <div style={{ display: "flex", gap: 20, alignItems: "baseline", marginTop: 16 }}>
          <Angka anak={`Rp ${per100[0].toFixed(0)}–${per100[1].toFixed(0)}`} ukuran={60} warnaA={warna.bara} />
          <div style={{ ...kecil, color: warna.kapur, fontSize: 21 }}>dibelanjakan rumah tangga warga dari setiap Rp 100 yang diproduksi (2025)</div>
        </div>
      </Kotak>
      <Kotak judul="Ke mana sisanya?">
        <div style={{ display: "flex", gap: 30 }}>
          {[
            [`${koma(D.pma_share_pct, 0)}%`, "investasi berasal dari luar negeri (Q2 2026)"],
            ["tax holiday", "keringanan pajak penghasilan bertahun-tahun untuk sebagian smelter"],
            [`${koma(F.apbd_share_pct, 1)}%`, "anggaran kabupaten dibanding nilai produksinya"],
          ].map(([a, b]) => (
            <div key={a} style={{ width: 300 }}>
              <Angka anak={a} ukuran={44} />
              <div style={{ ...kecil, color: warna.kapur, fontSize: 19, marginTop: 6 }}>{b}</div>
            </div>
          ))}
        </div>
      </Kotak>
      <Kotak judul="Bedanya dengan Tiongkok">
        <div style={{ ...kecil, color: warna.kapur, fontSize: 20 }}>
          Tiongkok juga menanggung polusi batu bara, tetapi pabriknya milik sendiri, labanya ditanam kembali di dalam negeri, dan teknologinya dipelajari. Di Maluku Utara, sebagian besar modal asing dan labanya mengalir keluar, sementara polusinya tinggal.
        </div>
      </Kotak>
      {kaki}
    </AbsoluteFill>
  );
};
