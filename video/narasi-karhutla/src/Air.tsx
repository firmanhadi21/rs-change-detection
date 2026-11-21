/**
 * "Jejak di Perairan" — part 4 of the North Maluku series, plus a two-page infographic (InfografisAir):
 * from cleared ground to murkier water in Weda Bay, and no visible change in Sagea Lake.
 *
 *   SIRAD        Sentinel-1 VH drop >= 3 dB in the Weda Bay mining cells: 117 ha (2019) -> 2,019 ha (2026)
 *   turbidity    Sentinel-2 TSS (Nechad 2010), water <= 2 km from mining cells vs coast > 15 km away, same dates:
 *                ratio 1.35 (2019) -> 2.15-2.32 (2023-2025); +9 %/yr; +18 % per 1,000 ha open ground; rain no effect
 *   lake         Sagea Lake flat
 *   limits       metals need water samples; industrial park and ports drain to the same water; correlation only
 *
 * Indonesian only (Bian). Wording: "keruh", never "tercemar". Every figure is from airData.json
 * (scripts/air_film_assets.py). The analysis stops at June 2026 (radiometric break in Sentinel-2 after that).
 * No company is named.
 */

import React from "react";
import { AbsoluteFill, Audio, Img, interpolate, Sequence, staticFile, useCurrentFrame } from "remotion";
import { JADWAL_AIR } from "./jadwalAir";
import { Bingkai, Judul, Keterangan, Kolom, LatarDiam, Lembut, masuk } from "./komponen";
import { angkaGaya, judulFont, koma, ribuan, tubuhFont, warna } from "./teema";
import D from "./airData.json";

const ABU_GELAP = "#3A424D";
const AUDIO = "audio/air";
const PAL = ["#0b2a4a", "#1f5f8b", "#3f9ab0", "#8cc5a8", "#d9c27a", "#c98b3e", "#9c5a22", "#6b3412"];
const THN = ["2019", "2020", "2021", "2022", "2023", "2024", "2025"];
const rasio = THN.map((y) => (D.rasio as Record<string, number>)[y]);
const kali = (x: number) => `${koma(x, 1)}×`;

const T = {
  kiri: "Tambang dan perairan, Maluku Utara",
  waktu: "November 2026",
  labelSumber: "Sumber",
  sumberRadar: "Sentinel-1 GRD, VH, orbit menurun 17 · SIRAD (J. Doblas, ISA): rerata periode, penurunan ≥ 3 dB dibanding 2017–2018 · petak tambang WRI/Google",
  sumberSedimen: "Sentinel-2 L2A, median 2 tahun · TSS: Nechad dkk. (2010), 665/865 nm · tanpa kalibrasi lapangan",
  sumberBanding: "Rasio kekeruhan median, tanggal yang sama · dekat: ≤ 2 km dari petak tambang · jauh: > 15 km · s.d. Juni 2026",
  sumberTumbuh: "Regresi per tanggal, kesalahan Newey–West, hujan 7 hari ERA5-Land sebagai kontrol · lahan terbuka: Dynamic World",
  sumberDanau: "Sentinel-2, 20 m dari tepi danau · lahan terbuka di DAS (HydroBASINS lv. 10): Dynamic World",
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
const Legenda: React.FC<{ isi: [string, string][]; tampil?: number; ukuran?: number }> = ({ isi, tampil = 1, ukuran = 20 }) => (
  <div style={{ display: "flex", gap: 20, flexWrap: "wrap", opacity: tampil, maxWidth: 660 }}>
    {isi.map(([k, w]) => (
      <div key={k} style={{ display: "flex", alignItems: "center", gap: 9, fontFamily: tubuhFont, fontSize: ukuran, color: warna.abu }}>
        <div style={{ width: 16, height: 16, background: w }} />
        {k}
      </div>
    ))}
  </div>
);
/** Colour ramp for TSS, clear (left) to murky (right). */
const Skala: React.FC<{ lebar?: number; tampil?: number }> = ({ lebar = 560, tampil = 1 }) => (
  <div style={{ opacity: tampil }}>
    <div style={{ width: lebar, height: 22, background: `linear-gradient(90deg, ${PAL.join(", ")})` }} />
    <div style={{ display: "flex", justifyContent: "space-between", width: lebar, fontFamily: tubuhFont, fontSize: 19, color: warna.abu, marginTop: 6 }}>
      <span>jernih · 1 g/m³</span>
      <span>5</span>
      <span>keruh · 20 g/m³</span>
    </div>
  </div>
);

const Peta: React.FC = () => (
  <AbsoluteFill style={{ backgroundColor: warna.jelaga }}>
    <Img src={staticFile("air/peta_tambang.jpg")} style={{ width: 1920, height: 1080 }} />
    <AbsoluteFill style={{ background: `linear-gradient(90deg, ${warna.jelaga} 0%, ${warna.jelaga} 33%, rgba(10,12,15,0) 42%)` }} />
  </AbsoluteFill>
);

/** Pictures in the right part of the frame (720–1920 px), fitted whole, crossfading; optional label. */
const Panel: React.FC<{ gambar: string[]; panjang: number; dari?: number; sampai?: number; tanda?: (i: number) => string }> = ({
  gambar,
  panjang,
  dari = 0.08,
  sampai = 0.7,
  tanda,
}) => {
  const f = useCurrentFrame();
  const pos = gambar.length === 1 ? 0 : interpolate(f, [panjang * dari, panjang * sampai], [0, gambar.length - 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const i = Math.floor(pos);
  const frac = pos - i;
  const sekarang = Math.min(gambar.length - 1, Math.round(pos));
  const gaya: React.CSSProperties = { position: "absolute", width: 1200, height: 1080, objectFit: "contain" };
  return (
    <AbsoluteFill style={{ backgroundColor: warna.jelaga }}>
      <div style={{ position: "absolute", left: 720, top: 0, width: 1200, height: 1080, overflow: "hidden" }}>
        <Img src={staticFile(`air/${gambar[i]}`)} style={gaya} />
        {i + 1 < gambar.length ? <Img src={staticFile(`air/${gambar[i + 1]}`)} style={{ ...gaya, opacity: frac }} /> : null}
      </div>
      <AbsoluteFill style={{ background: `linear-gradient(90deg, ${warna.jelaga} 0%, ${warna.jelaga} 37%, rgba(10,12,15,0) 46%)` }} />
      {tanda ? (
        <div style={{ position: "absolute", right: 70, bottom: 110, ...angkaGaya, fontSize: 48, fontWeight: 600, color: warna.kapur, textShadow: "0 2px 18px rgba(0,0,0,0.85)", textAlign: "right" }}>
          {tanda(sekarang)}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};

/** Vertical bars by year, optional reference line. */
const BatangTahun: React.FC<{
  tahun: string[];
  nilai: number[];
  tampil: (i: number) => number;
  warnaI: (i: number) => string;
  label: (i: number) => string | null;
  W?: number;
  H?: number;
  maks?: number;
  garis?: { nilai: number; teks: string };
  ukuran?: number;
}> = ({ tahun, nilai, tampil, warnaI, label, W = 620, H = 300, maks, garis, ukuran = 19 }) => {
  const mx = maks ?? Math.max(...nilai);
  const bw = W / nilai.length;
  return (
    <svg width={W} height={H + 70}>
      {nilai.map((v, i) => {
        const o = tampil(i);
        const h = (H * v * o) / mx;
        const lab = label(i);
        return (
          <g key={i}>
            <rect x={i * bw + bw * 0.14} y={H - h + 30} width={bw * 0.72} height={h} fill={warnaI(i)} />
            {lab && o > 0.5 ? (
              <text x={i * bw + bw / 2} y={H - h + 20} fill={warnaI(i)} fontSize={ukuran + 2} textAnchor="middle" fontFamily={angkaGaya.fontFamily as string} fontWeight={600}>
                {lab}
              </text>
            ) : null}
            <text x={i * bw + bw / 2} y={H + 62} fill={warna.samar} fontSize={ukuran} textAnchor="middle" fontFamily={tubuhFont}>
              {tahun[i]}
            </text>
          </g>
        );
      })}
      {garis ? (
        <g>
          {/* label goes under the chart (tahun row), not on the line, so it never sits on a bar */}
          <line x1={0} x2={W} y1={H - (H * garis.nilai) / mx + 30} y2={H - (H * garis.nilai) / mx + 30} stroke={warna.kapur} strokeDasharray="6 6" strokeWidth={1.5} />
        </g>
      ) : null}
    </svg>
  );
};

/** Scatter: open ground (x) vs near/far ratio (y), years labelled. */
const Sebar: React.FC<{ tampil: (i: number) => number; W?: number; H?: number; ukuran?: number }> = ({ tampil, W = 700, H = 420, ukuran = 20 }) => {
  const xs = THN.map((y) => (D.terbuka as Record<string, number>)[y]);
  const pad = 60;
  const xmax = 3500, ymin = 0.8, ymax = 2.6;
  const X = (v: number) => pad + ((W - pad - 20) * v) / xmax;
  const Y = (v: number) => H - pad - ((H - pad - 20) * (v - ymin)) / (ymax - ymin);
  return (
    <svg width={W} height={H}>
      <line x1={pad} x2={W - 20} y1={H - pad} y2={H - pad} stroke={warna.garis} />
      <line x1={pad} x2={pad} y1={20} y2={H - pad} stroke={warna.garis} />
      <line x1={pad} x2={W - 20} y1={Y(1)} y2={Y(1)} stroke={warna.samar} strokeDasharray="5 6" />
      {[0, 1000, 2000, 3000].map((v) => (
        <text key={v} x={X(v)} y={H - pad + 26} fill={warna.samar} fontSize={ukuran - 2} textAnchor="middle" fontFamily={tubuhFont}>
          {ribuan(v)}
        </text>
      ))}
      {[1, 1.5, 2, 2.5].map((v) => (
        <text key={v} x={pad - 10} y={Y(v) + 6} fill={warna.samar} fontSize={ukuran - 2} textAnchor="end" fontFamily={tubuhFont}>
          {kali(v)}
        </text>
      ))}
      <text x={(W + pad) / 2} y={H - 8} fill={warna.abu} fontSize={ukuran - 1} textAnchor="middle" fontFamily={tubuhFont}>
        lahan terbuka di petak tambang (ha)
      </text>
      {THN.map((y, i) => {
        const o = tampil(i);
        return (
          <g key={y} opacity={o}>
            <circle cx={X(xs[i])} cy={Y(rasio[i])} r={9} fill={i >= 4 ? warna.bara : warna.nyala} />
            <text x={X(xs[i]) + (y === "2019" ? -13 : 13)} y={Y(rasio[i]) - 9} fill={warna.kapur} fontSize={ukuran - 2} fontFamily={tubuhFont} textAnchor={y === "2019" ? "end" : "start"}>
              {y}
            </text>
          </g>
        );
      })}
    </svg>
  );
};

/* ---------------------------------- scenes --------------------------- */

const KartuJudul: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 4, 24);
  return (
    <Lembut panjang={panjang}>
      <Panel gambar={["sedimen_2024.jpg"]} panjang={panjang} />
      <Kolom jarak={26}>
        <div style={{ opacity: a, transform: `translateY(${(1 - a) * 20}px)` }}>
          <div style={{ marginBottom: 24 }}>
            <Alis anak="Bagian 4 · Analisis citra satelit" />
          </div>
          <h1 style={{ fontFamily: judulFont, fontWeight: 900, fontSize: 104, lineHeight: 0.94, letterSpacing: "-0.04em", color: warna.kapur, margin: 0 }}>
            JEJAK DI
            <br />
            PERAIRAN
          </h1>
          <div style={{ marginTop: 28 }}>
            <Keterangan lebar={600} anak="Dari tanah yang dibuka tambang ke air yang makin keruh di Teluk Weda." />
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Buka: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const seri: [string, string][] = [
    ["1", "Apa yang menggerus hutan Maluku Utara?"],
    ["2", "Memeriksa peta tambang nikel"],
    ["3", "Jejak tambang di Maluku Utara"],
  ];
  const c = masuk(f, Math.round(panjang * 0.6), 22);
  return (
    <Lembut panjang={panjang}>
      <Peta />
      <Bkg tampil={a} />
      <Kolom jarak={22}>
        <div style={{ width: 600 }}>
          {seri.map(([n, t], i) => (
            <div key={n} style={{ display: "flex", gap: 18, alignItems: "baseline", marginBottom: 14, opacity: masuk(f, 8 + i * 12, 18) }}>
              <span style={{ ...angkaGaya, fontSize: 26, color: warna.samar }}>{n}</span>
              <span style={{ fontFamily: tubuhFont, fontSize: 26, color: warna.abu }}>{t}</span>
            </div>
          ))}
          <div style={{ display: "flex", gap: 18, alignItems: "baseline", marginTop: 10, opacity: c }}>
            <span style={{ ...angkaGaya, fontSize: 30, color: warna.bara }}>4</span>
            <Judul anak="Ke mana tanahnya pergi?" ukuran={50} />
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Radar: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const yrs = ["2017", "2018", "2019", "2020", "2021", "2022", "2023", "2024", "2025", "2026"];
  const v = yrs.map((y) => (D.sirad as Record<string, number>)[y]);
  const t0 = panjang * 0.25, t1 = panjang * 0.8;
  return (
    <Lembut panjang={panjang}>
      <Panel gambar={["sirad.png"]} panjang={panjang} tanda={() => "SIRAD · Teluk Weda bagian selatan"} />
      <Bkg sumber={T.sumberRadar} tampil={a} />
      <Kolom jarak={0}>
        <div style={{ width: 640, opacity: a }}>
          <Alis anak="Radar menembus awan" />
          <div style={{ marginTop: 16 }}>
            <Judul anak="Hutan menjadi tanah terbuka (ha)" ukuran={44} />
          </div>
          <div style={{ marginTop: 12 }}>
            <BatangTahun
              tahun={yrs.map((y) => `’${y.slice(2)}`)}
              nilai={v}
              W={620}
              H={260}
              tampil={(i) => masuk(f, t0 + (i / (v.length - 1)) * (t1 - t0), 14)}
              warnaI={(i) => (i === v.length - 1 ? warna.nyala : warna.bara)}
              label={(i) => (i === 2 || i === v.length - 1 ? ribuan(v[i]) : null)}
            />
          </div>
          <div style={{ fontFamily: tubuhFont, fontSize: 20, color: warna.abu, marginTop: 4, lineHeight: 1.45 }}>
            Gambar: merah = 2019, hijau = 2023, biru = 2026. Abu-abu = tidak berubah; warna = berubah.
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Sedimen: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const b = masuk(f, Math.round(panjang * 0.55), 22);
  return (
    <Lembut panjang={panjang}>
      {/* one period only: a per-pixel two-year median mixes different scene sets, so a before/after pair of maps would
          suggest a bay-wide change that the same-date near/far comparison does not show */}
      <Panel gambar={["sedimen_2024.jpg"]} panjang={panjang} tanda={() => "Median 2024–2025"} />
      <Bkg sumber={T.sumberSedimen} tampil={a} />
      <Kolom jarak={0}>
        <div style={{ width: 620, opacity: a }}>
          <Alis anak="Membaca sedimen dari warna air" />
          <div style={{ marginTop: 16 }}>
            <Judul anak="Tanah terbuka tergerus hujan dan terbawa ke laut" ukuran={44} />
          </div>
          <div style={{ marginTop: 36 }}>
            <Skala lebar={560} />
          </div>
          <div style={{ marginTop: 30 }}>
            <Garis anak="Median dua tahun dari semua tanggal yang cerah. Kekeruhan (TSS) dihitung dari pantulan merah dan inframerah dekat." tampil={b} ukuran={23} />
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Banding: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const t0 = panjang * 0.35, t1 = panjang * 0.85;
  return (
    <Lembut panjang={panjang}>
      <Panel gambar={["zona.jpg"]} panjang={panjang} tanda={() => "Teluk Weda"} />
      <Bkg sumber={T.sumberBanding} tampil={a} />
      <Kolom jarak={0}>
        <div style={{ width: 640, opacity: a }}>
          <Alis anak="Dekat tambang dibanding jauh" />
          <div style={{ marginTop: 16 }}>
            <Judul anak="Berapa kali lebih keruh di dekat tambang?" ukuran={44} />
          </div>
          <div style={{ marginTop: 14 }}>
            <Legenda isi={[["≤ 2 km dari petak tambang", warna.nyala], ["pesisir > 15 km dari tambang", "#9AA3AD"], ["petak tambang", warna.bara]]} ukuran={19} />
          </div>
          <div style={{ marginTop: 6 }}>
            <BatangTahun
              tahun={THN}
              nilai={rasio}
              W={620}
              H={250}
              maks={2.6}
              garis={{ nilai: 1, teks: "sama keruh" }}
              tampil={(i) => masuk(f, t0 + (i / (THN.length - 1)) * (t1 - t0), 14)}
              warnaI={(i) => (i >= 4 ? warna.bara : warna.nyala)}
              label={(i) => kali(rasio[i])}
            />
            <div style={{ fontFamily: tubuhFont, fontSize: 19, color: warna.abu }}>Garis putus-putus = sama keruh (1×)</div>
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Tumbuh: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const b = masuk(f, Math.round(panjang * 0.45), 22);
  const c = masuk(f, Math.round(panjang * 0.7), 22);
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Bkg sumber={T.sumberTumbuh} tampil={a} />
      <Kolom jarak={0}>
        <div style={{ display: "flex", gap: 80, alignItems: "center" }}>
          <div style={{ opacity: a }}>
            <Sebar tampil={(i) => masuk(f, Math.round(panjang * 0.08) + i * 8, 14)} />
          </div>
          <div style={{ width: 620 }}>
            <Alis anak="Naik seiring tanah terbuka" />
            <div style={{ marginTop: 20, opacity: b }}>
              <Angka anak={`+${D.per1000}%`} ukuran={110} warnaA={warna.bara} />
              <div style={{ fontFamily: tubuhFont, fontSize: 27, color: warna.kapur, marginTop: 8 }}>lebih keruh per tambahan 1.000 ha tanah terbuka</div>
              <div style={{ fontFamily: tubuhFont, fontSize: 20, color: warna.abu, marginTop: 6 }}>
                selang 95%: +{D.per1000_ci[0]}% s.d. +{D.per1000_ci[1]}% · {D.n_pasang} tanggal
              </div>
            </div>
            <div style={{ marginTop: 30 }}>
              <Garis anak="Hujan tidak menjelaskan perbedaan ini: pengaruhnya sama di dekat dan jauh dari tambang." tampil={c} ukuran={24} />
            </div>
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Danau: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const c = masuk(f, Math.round(panjang * 0.5), 22);
  const lk = THN.map((y) => (D.danau as Record<string, number>)[y] ?? 0);
  return (
    <Lembut panjang={panjang}>
      <Panel gambar={["sagea.jpg"]} panjang={panjang} tanda={() => "Danau Sagea, 2025"} />
      <Bkg sumber={T.sumberDanau} tampil={a} />
      <Kolom jarak={0}>
        <div style={{ width: 620, opacity: a }}>
          <Alis anak="Danau Sagea" />
          <div style={{ marginTop: 16 }}>
            <Judul anak="Satelit tidak melihat perubahan" ukuran={46} />
          </div>
          <div style={{ fontFamily: tubuhFont, fontSize: 22, color: warna.abu, marginTop: 22 }}>Kekeruhan danau, median per tahun (g/m³)</div>
          <BatangTahun
            tahun={THN}
            nilai={lk}
            W={600}
            H={180}
            maks={10}
            tampil={(i) => masuk(f, Math.round(panjang * 0.1) + i * 7, 14)}
            warnaI={() => "#2a7fb8"}
            label={(i) => koma(lk[i], 1)}
          />
          <Garis anak="Bukan berarti sungainya jernih: sungai terlalu sempit untuk citra ini, dan awan sering menutupi saat air keruh datang." tampil={c} ukuran={23} />
        </div>
      </Kolom>
    </Lembut>
  );
};

const Batas: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 4, 20);
  const isi: [string, string][] = [
    ["Logam dan zat terlarut", "hanya bisa diukur dengan sampel air"],
    ["Sumber lain", "kawasan industri, pelabuhan, reklamasi, dan kapal juga bermuara di air yang sama"],
    ["Keterkaitan, bukan bukti sebab", "angka ini menunjukkan air makin keruh seiring tambang meluas"],
  ];
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Kolom jarak={30}>
        <div style={{ opacity: a }}>
          <Alis anak="Yang tidak bisa dilihat satelit" />
        </div>
        {isi.map(([k, v], i) => {
          const o = masuk(f, Math.round(panjang * (0.12 + i * 0.25)), 20);
          return (
            <div key={k} style={{ opacity: o, borderTop: `2px solid ${warna.garis}`, paddingTop: 16, maxWidth: 1400 }}>
              <div style={{ fontFamily: judulFont, fontWeight: 800, fontSize: 44, color: warna.kapur }}>{k}</div>
              <div style={{ fontFamily: tubuhFont, fontSize: 28, color: warna.abu, marginTop: 6 }}>{v}</div>
            </div>
          );
        })}
      </Kolom>
    </Lembut>
  );
};

const Tutup: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const langkah: [string, string, string][] = [
    ["Hutan dibuka", "Maluku Utara, sejak 2001", warna.abu],
    ["Tanah terbuka meluas", `${ribuan((D.terbuka as Record<string, number>)["2017"])} → ${ribuan((D.terbuka as Record<string, number>)["2026"])} ha di petak tambang Teluk Weda`, warna.nyala],
    ["Perairan makin keruh", `${kali(rasio[0])} → ${kali(Math.max(...rasio.slice(4)))} lebih keruh di dekat tambang`, warna.bara],
  ];
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Kolom jarak={26}>
        {langkah.map(([k, v, w], i) => {
          const o = masuk(f, Math.round(panjang * (0.05 + i * 0.22)), 20);
          return (
            <div key={k} style={{ opacity: o, display: "flex", gap: 30, alignItems: "baseline" }}>
              <div style={{ width: 700, fontFamily: judulFont, fontWeight: 900, fontSize: 60, color: w, lineHeight: 1.05 }}>{k}</div>
              <div style={{ fontFamily: tubuhFont, fontSize: 28, color: warna.kapur }}>{v}</div>
            </div>
          );
        })}
      </Kolom>
    </Lembut>
  );
};

const BARIS_SUMBER: [string, string][] = [
  ["Radar", "Sentinel-1 GRD (Copernicus), VH, orbit menurun 17 · SIRAD (Juan Doblas, Instituto Socioambiental)"],
  ["Kekeruhan", "Sentinel-2 L2A, Cloud Score+ · TSS: Nechad dkk. (2010), 665/865 nm · tanpa sampel lapangan"],
  ["Lahan terbuka", "Google/WRI Dynamic World v1 · petak tambang: WRI/Google Drivers of Forest Loss v1.2"],
  ["Hujan", "ERA5-Land harian (ECMWF), 7 hari sebelum citra"],
  ["Periode", "2019 – Juni 2026; sesudahnya pemrosesan Sentinel-2 berubah dan air laut lepas tampak dua kali lebih terang, jadi tidak dipakai"],
  ["Batas", "FAO GAUL 2025 · HydroBASINS · JRC Global Surface Water · analisis November 2026"],
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
          Kekeruhan bukan ukuran pencemaran logam. Angka satelit dapat berbeda dari pengukuran lapangan. Tidak ada perusahaan yang disebut.
        </div>
      </Kolom>
    </AbsoluteFill>
  );
};

/* --------------------------------- film ------------------------------ */

const ADEGAN: Record<string, React.FC<{ panjang: number }>> = {
  "01-buka": Buka,
  "02-radar": Radar,
  "03-sedimen": Sedimen,
  "04-banding": Banding,
  "05-tumbuh": Tumbuh,
  "06-danau": Danau,
  "07-batas": Batas,
  "08-tutup": Tutup,
};

export const AirFilm: React.FC = () => {
  const J = JADWAL_AIR;
  return (
    <AbsoluteFill style={{ backgroundColor: warna.jelaga }}>
      <Audio src={staticFile(`${AUDIO}/musik-air.mp3`)} />
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

/** Two 1080x1350 (4:5) pages: 1 = forest becomes open ground, 2 = the sea beside the mines grows murkier. */
export const InfografisAir: React.FC<{ halaman?: 1 | 2 }> = ({ halaman = 1 }) => {
  const kecil = { fontFamily: tubuhFont, fontSize: 20, color: warna.abu, lineHeight: 1.4 } as React.CSSProperties;
  const kepala = (
    <div style={{ borderTop: `3px solid ${warna.bara}`, paddingTop: 16, display: "flex", justifyContent: "space-between" }}>
      <Alis anak="Jejak di Perairan · bagian 4" />
      <span style={{ fontFamily: tubuhFont, fontSize: 19, letterSpacing: "0.18em", color: warna.abu, textTransform: "uppercase" }}>
        {T.waktu} · {halaman}/2
      </span>
    </div>
  );
  const kaki = (n: number) => (
    <div style={{ ...kecil, fontSize: 15, borderTop: `1px solid ${warna.garis}`, paddingTop: 12, marginTop: "auto" }}>
      {BARIS_SUMBER.slice(0, n).map(([k, v]) => `${k}: ${v}`).join(" · ")}. Kekeruhan bukan ukuran pencemaran logam. Tidak ada perusahaan yang disebut.
    </div>
  );
  const op = D.terbuka as Record<string, number>;
  const sd = D.sirad as Record<string, number>;
  const yrs = ["2017", "2018", "2019", "2020", "2021", "2022", "2023", "2024", "2025", "2026"];
  if (halaman === 1) {
    return (
      <AbsoluteFill style={{ backgroundColor: warna.jelaga, padding: "46px 54px 40px", display: "flex", flexDirection: "column", gap: 20 }}>
        <div>
          {kepala}
          <h1 style={{ fontFamily: judulFont, fontWeight: 900, fontSize: 60, lineHeight: 0.98, letterSpacing: "-0.035em", color: warna.kapur, margin: "22px 0 0" }}>
            Hutan menjadi tanah terbuka
          </h1>
        </div>
        <div style={{ display: "flex", gap: 40, alignItems: "flex-end" }}>
          <div>
            <div style={{ ...kecil, color: warna.kapur, fontSize: 22 }}>Lahan terbuka di petak tambang Teluk Weda</div>
            <div style={{ display: "flex", alignItems: "baseline", gap: 18 }}>
              <Angka anak={ribuan(op["2017"])} ukuran={56} warnaA={warna.abu} />
              <span style={{ fontFamily: tubuhFont, fontSize: 36, color: warna.abu }}>→</span>
              <Angka anak={ribuan(op["2026"])} ukuran={86} />
              <span style={{ fontFamily: tubuhFont, fontSize: 26, color: warna.kapur }}>ha</span>
            </div>
            <div style={{ ...kecil, fontSize: 21 }}>2017 → 2026 (Jan–Nov) · Dynamic World</div>
          </div>
        </div>
        <Kotak judul="Per tahun (ha) · Dynamic World dan radar SIRAD">
          <svg width={970} height={270}>
            {yrs.map((y, i) => {
              const bw = 97, H = 210, mx = 4400;
              const h1 = (H * op[y]) / mx, h2 = (H * sd[y]) / mx;
              return (
                <g key={y}>
                  <rect x={i * bw + 12} y={H - h1 + 20} width={bw * 0.72} height={h1} fill={warna.nyala} />
                  <rect x={i * bw + 30} y={H - h2 + 20} width={bw * 0.36} height={h2} fill={ABU_GELAP} />
                  <text x={i * bw + 47} y={H - h1 + 12} fill={warna.nyala} fontSize={17} textAnchor="middle" fontFamily={angkaGaya.fontFamily as string}>
                    {ribuan(op[y])}
                  </text>
                  <text x={i * bw + 47} y={H + 46} fill={warna.samar} fontSize={17} textAnchor="middle" fontFamily={tubuhFont}>
                    {y}
                  </text>
                </g>
              );
            })}
          </svg>
          <Legenda isi={[["Lahan terbuka (Dynamic World)", warna.nyala], ["Hutan → tanah terbuka menurut radar (SIRAD, turun ≥ 3 dB)", ABU_GELAP]]} ukuran={18} />
        </Kotak>
        <Kotak judul="Radar SIRAD, Teluk Weda bagian selatan">
          <Img src={staticFile("air/sirad.png")} style={{ width: 970, height: 400, objectFit: "cover", objectPosition: "50% 30%" }} />
          <div style={{ ...kecil, fontSize: 18, marginTop: 8 }}>Merah = 2019, hijau = 2023, biru = 2026. Abu-abu = tidak berubah; warna = permukaan berubah (dibuka, dibangun).</div>
        </Kotak>
        {kaki(1)}
      </AbsoluteFill>
    );
  }
  const lk = THN.map((y) => (D.danau as Record<string, number>)[y] ?? 0);
  return (
    <AbsoluteFill style={{ backgroundColor: warna.jelaga, padding: "46px 54px 40px", display: "flex", flexDirection: "column", gap: 18 }}>
      <div>
        {kepala}
        <h1 style={{ fontFamily: judulFont, fontWeight: 900, fontSize: 50, lineHeight: 1, letterSpacing: "-0.03em", color: warna.kapur, margin: "22px 0 0" }}>
          Laut di samping tambang makin keruh
        </h1>
      </div>
      <div style={{ display: "flex", gap: 14 }}>
        <div>
          <Img src={staticFile("air/sedimen_2024.jpg")} style={{ width: 600, height: 300, objectFit: "cover" }} />
          <div style={{ ...kecil, fontSize: 18, marginTop: 4 }}>Kekeruhan air, median 2024–2025, Teluk Weda bagian selatan</div>
        </div>
        <div>
          <Img src={staticFile("air/zona.jpg")} style={{ width: 356, height: 300, objectFit: "cover", objectPosition: "30% 40%" }} />
          <div style={{ ...kecil, fontSize: 18, marginTop: 4 }}>
            <span style={{ color: warna.nyala }}>■</span> ≤ 2 km dari tambang · <span style={{ color: "#9AA3AD" }}>■</span> &gt; 15 km
          </div>
        </div>
      </div>
      <Skala lebar={970} />
      <Kotak judul="Berapa kali lebih keruh di dekat tambang (≤ 2 km) dibanding pesisir jauh (> 15 km)">
        <BatangTahun
          tahun={THN}
          nilai={rasio}
          W={970}
          H={150}
          maks={2.6}
          garis={{ nilai: 1, teks: "sama keruh" }}
          tampil={() => 1}
          warnaI={(i) => (i >= 4 ? warna.bara : warna.nyala)}
          label={(i) => kali(rasio[i])}
          ukuran={18}
        />
        <div style={{ ...kecil, fontSize: 17 }}>Garis putus-putus = sama keruh (1×)</div>
        <div style={{ ...kecil, color: warna.kapur, fontSize: 21 }}>
          Naik seiring tanah terbuka: <span style={{ ...angkaGaya, color: warna.bara, fontWeight: 600 }}>+{D.per1000}%</span> lebih keruh per tambahan 1.000 ha. Hujan tidak menjelaskan perbedaan ini.
        </div>
      </Kotak>
      <div style={{ display: "flex", gap: 30 }}>
        <div style={{ width: 470 }}>
          <Kotak judul="Danau Sagea">
            <div style={{ ...kecil, color: warna.kapur, fontSize: 20 }}>
              Tidak terlihat perubahan: {koma(Math.min(...lk), 1)}–{koma(Math.max(...lk), 1)} g/m³ per tahun, 2019–2025. Bukan berarti sungainya jernih; sungai terlalu sempit untuk citra ini.
            </div>
          </Kotak>
        </div>
        <div style={{ width: 470 }}>
          <Kotak judul="Tidak terlihat satelit">
            <div style={{ ...kecil, color: warna.kapur, fontSize: 20 }}>Logam dan zat terlarut perlu sampel air. Kawasan industri dan pelabuhan juga bermuara di air yang sama.</div>
          </Kotak>
        </div>
      </div>
      {kaki(5)}
    </AbsoluteFill>
  );
};
