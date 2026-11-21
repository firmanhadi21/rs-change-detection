/**
 * "Jejak Tambang di Maluku Utara" — a standalone film, plus a two-page infographic (InfografisTambang),
 * on open and disturbed ground inside the WRI/Google mining cells of North Maluku, label-adjusted
 * with 150 hand-labelled check points outside Weda/Sagea.
 *
 *   cells        34,182 ha of land in mining cells (WRI/Google drivers v1.2, 2001-2024)
 *   check        60/60 map-open points labelled bare/built; 15/40 map-disturbed labelled bare
 *   area 2025    11,884 ± 873 ha open; 14,226 ± 1,787 ha with disturbed
 *   regencies    Tengah 5,821 · Selatan 4,292 · Timur 3,183 (open + disturbed)
 *   by year      peak 2023; Tengah falls after 2023, Selatan stays high, Timur rises to 2025
 *
 * Indonesian only (Bian). Same palette, type and audio pipeline as Periksa.tsx. Every figure is from
 * tambangData.json (scripts/tambang_film_assets.py). No company is named.
 */

import React from "react";
import { AbsoluteFill, Audio, Img, interpolate, Sequence, staticFile, useCurrentFrame } from "remotion";
import { JADWAL_TAMBANG } from "./jadwalTambang";
import { Bingkai, Judul, Keterangan, Kolom, LatarDiam, Lembut, masuk } from "./komponen";
import { angkaGaya, judulFont, ribuan, tubuhFont, warna } from "./teema";
import D from "./tambangData.json";

const ABU_GELAP = "#3A424D";
const AUDIO = "audio/tambang";
const pm = (v: number[]) => `${ribuan(v[0])} ± ${ribuan(v[1])}`;
const ratus = (n: number) => Math.round(n / 100) * 100;

const T = {
  kiri: "Tambang, Maluku Utara",
  waktu: "November 2026",
  labelSumber: "Sumber",
  alisJudul: "Analisis citra satelit dan model AI",
  judul: ["JEJAK", "TAMBANG DI", "MALUKU UTARA"],
  subJudul: "Berapa luas tanah yang dibuka di petak-petak tambang, diperiksa dengan 150 titik di luar Teluk Weda.",
  sumberSel: "WRI/Google, Drivers of Forest Loss 1 km v1.2 (2001–2024), kelas tambang & energi",
  sumberModel: "AlphaEarth 2025 · random forest dari 297 label Weda/Sagea · Sentinel-2 2025",
  sumberCek: "150 titik acak berlapis di luar Weda/Sagea, dilabeli dari Sentinel-2 2025 tanpa melihat tebakan model",
  sumberLuas: "Rata-rata berstrata dari label, selang 95%",
  sumberTahun: "AlphaEarth, tahun pertama berubah dibanding 2019, dikoreksi dengan label",
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

const Garis: React.FC<{ anak: React.ReactNode; tampil: number; lebar?: number }> = ({ anak, tampil, lebar = 620 }) => (
  <div style={{ borderLeft: `3px solid ${warna.bara}`, paddingLeft: 18, fontFamily: tubuhFont, fontSize: 26, color: warna.kapur, lineHeight: 1.35, maxWidth: lebar, opacity: tampil }}>
    {anak}
  </div>
);

const Legenda: React.FC<{ isi: [string, string][]; tampil?: number; ukuran?: number }> = ({ isi, tampil = 1, ukuran = 20 }) => (
  <div style={{ display: "flex", gap: 22, flexWrap: "wrap", opacity: tampil, maxWidth: 660 }}>
    {isi.map(([k, w]) => (
      <div key={k} style={{ display: "flex", alignItems: "center", gap: 9, fontFamily: tubuhFont, fontSize: ukuran, color: warna.abu }}>
        <div style={{ width: 16, height: 16, background: w }} />
        {k}
      </div>
    ))}
  </div>
);

/** Full-frame province map (map drawn in the right 60%), with the text column darkened. */
const Peta: React.FC = () => (
  <AbsoluteFill style={{ backgroundColor: warna.jelaga }}>
    <Img src={staticFile("tambang/peta_tambang.jpg")} style={{ width: 1920, height: 1080 }} />
    <AbsoluteFill style={{ background: `linear-gradient(90deg, ${warna.jelaga} 0%, ${warna.jelaga} 33%, rgba(10,12,15,0) 42%)` }} />
  </AbsoluteFill>
);

/** Pictures in the right part of the frame (720–1920 px), crossfading; optional label. */
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
  const gaya: React.CSSProperties = { position: "absolute", width: 1200, height: 1080, objectFit: "cover" };
  return (
    <AbsoluteFill style={{ backgroundColor: warna.jelaga }}>
      <div style={{ position: "absolute", left: 720, top: 0, width: 1200, height: 1080, overflow: "hidden" }}>
        <Img src={staticFile(`tambang/${gambar[i]}`)} style={gaya} />
        {i + 1 < gambar.length ? <Img src={staticFile(`tambang/${gambar[i + 1]}`)} style={{ ...gaya, opacity: frac }} /> : null}
      </div>
      <AbsoluteFill style={{ background: `linear-gradient(90deg, ${warna.jelaga} 0%, ${warna.jelaga} 37%, rgba(10,12,15,0) 48%)` }} />
      {tanda ? (
        <div style={{ position: "absolute", right: 70, bottom: 110, ...angkaGaya, fontSize: 52, fontWeight: 600, color: warna.kapur, textShadow: "0 2px 18px rgba(0,0,0,0.85)", textAlign: "right" }}>
          {tanda(sekarang)}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};

/** Horizontal bar with an optional ± whisker. */
const Batang: React.FC<{ label: string; nilai: number; maks: number; teks: string; w: string; tampil: number; lebar?: number; galat?: number; labelW?: number; ukuran?: number }> = ({
  label,
  nilai,
  maks,
  teks,
  w,
  tampil,
  lebar = 380,
  galat,
  labelW = 250,
  ukuran = 23,
}) => (
  <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
    <div style={{ width: labelW, fontFamily: tubuhFont, fontSize: ukuran, color: warna.kapur }}>{label}</div>
    <div style={{ width: lebar, height: 30, background: warna.arang, position: "relative" }}>
      <div style={{ width: (lebar * nilai * tampil) / maks, height: 30, background: w }} />
      {galat ? (
        <div
          style={{
            position: "absolute",
            top: 13,
            height: 4,
            left: (lebar * (nilai - galat)) / maks,
            width: (lebar * 2 * galat) / maks,
            background: warna.kapur,
            opacity: tampil > 0.95 ? 0.9 : 0,
          }}
        />
      ) : null}
    </div>
    <div style={{ ...angkaGaya, fontSize: ukuran + 3, fontWeight: 600, color: w, opacity: tampil, whiteSpace: "nowrap" }}>{teks}</div>
  </div>
);

/** Vertical bars by year. */
const BatangTahun: React.FC<{
  tahun: string[];
  nilai: number[];
  tampil: (i: number) => number;
  warnaI: (i: number) => string;
  label: (i: number) => string | null;
  W?: number;
  H?: number;
  maks?: number;
  ukuran?: number;
}> = ({ tahun, nilai, tampil, warnaI, label, W = 620, H = 300, maks, ukuran = 19 }) => {
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
    </svg>
  );
};

/** One 100%-wide stacked bar for a map class: labelled open / disturbed / vegetated. */
const Tumpuk: React.FC<{ judul: string; c: { terbuka: number; terganggu: number; vegetasi: number; n: number }; tampil: number; W?: number; ukuran?: number }> = ({
  judul,
  c,
  tampil,
  W = 1100,
  ukuran = 24,
}) => {
  const seg: [number, string][] = [
    [c.terbuka, warna.bara],
    [c.terganggu, warna.nyala],
    [c.vegetasi, ABU_GELAP],
  ];
  let x = 0;
  return (
    <div style={{ opacity: tampil }}>
      <div style={{ fontFamily: tubuhFont, fontSize: ukuran, color: warna.kapur, marginBottom: 8 }}>{judul}</div>
      <svg width={W} height={46}>
        {seg.map(([n, w], i) => {
          const lebar = (W * n * tampil) / c.n;
          const r = (
            <g key={i}>
              <rect x={x} y={0} width={Math.max(0, lebar - 4)} height={46} fill={w} />
              {n > 0 && lebar > 50 ? (
                <text x={x + 14} y={31} fill={i === 2 ? warna.kapur : warna.jelaga} fontSize={ukuran} fontFamily={angkaGaya.fontFamily as string} fontWeight={600}>
                  {n}
                </text>
              ) : null}
            </g>
          );
          x += lebar;
          return r;
        })}
      </svg>
    </div>
  );
};

const LEG_CEK: [string, string][] = [
  ["Dilabeli gundul / bangunan", warna.bara],
  ["Dilabeli terganggu, menghijau", warna.nyala],
  ["Dilabeli hutan, semak, kebun, air", ABU_GELAP],
];
const NAMA_KELAS: Record<string, string> = { bare: "tanah gundul", built: "bangunan", shrub: "semak, belukar", disturbed: "terganggu", forest: "hutan", tree_crops: "kebun" };
const NAMA_PETA: Record<string, string> = { open: "terbuka", disturbed: "terganggu", other: "lainnya" };

/* ---------------------------------- scenes --------------------------- */

const KartuJudul: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 4, 24);
  return (
    <Lembut panjang={panjang}>
      <Peta />
      <Kolom jarak={26}>
        <div style={{ opacity: a, transform: `translateY(${(1 - a) * 20}px)` }}>
          <div style={{ marginBottom: 24 }}>
            <Alis anak={T.alisJudul} />
          </div>
          <h1 style={{ fontFamily: judulFont, fontWeight: 900, fontSize: 92, lineHeight: 0.94, letterSpacing: "-0.04em", color: warna.kapur, margin: 0 }}>
            {T.judul.map((l, i) => (
              <React.Fragment key={l}>
                {i > 0 && <br />}
                {l}
              </React.Fragment>
            ))}
          </h1>
          <div style={{ marginTop: 28 }}>
            <Keterangan lebar={620} anak={T.subJudul} />
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Buka: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const b = masuk(f, Math.round(panjang * 0.3), 24);
  const c = masuk(f, Math.round(panjang * 0.72), 22);
  return (
    <Lembut panjang={panjang}>
      <Peta />
      <Bkg sumber={T.sumberSel} tampil={a} />
      <Kolom jarak={0}>
        <div style={{ width: 600, opacity: a }}>
          <Alis anak="Petak tambang, 1 km" />
          <div style={{ marginTop: 18 }}>
            <Judul anak="Tempat hutan hilang terutama karena tambang" ukuran={48} />
          </div>
          <div style={{ marginTop: 40, opacity: b }}>
            <Angka anak={ribuan(D.sel_ha * b)} ukuran={96} />
            <div style={{ fontFamily: tubuhFont, fontSize: 26, color: warna.kapur, marginTop: 6 }}>hektare daratan di dalam petak tambang</div>
          </div>
          <div style={{ marginTop: 34 }}>
            <Garis anak="Berapa yang kini benar-benar tanah terbuka?" tampil={c} lebar={560} />
          </div>
          <div style={{ marginTop: 26 }}>
            <Legenda isi={[["Petak tambang", warna.bara]]} tampil={a} />
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Model: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const b = masuk(f, Math.round(panjang * 0.45), 22);
  return (
    <Lembut panjang={panjang}>
      <Panel gambar={["tengah_2025.jpg", "tengah_peta.jpg"]} panjang={panjang} dari={0.4} sampai={0.58} tanda={(i) => (i === 0 ? "Sentinel-2 2025" : "Hasil model 2025") + " · Pulau Gebe"} />
      <Bkg sumber={T.sumberModel} tampil={a} />
      <Kolom jarak={0}>
        <div style={{ width: 620, opacity: a }}>
          <Alis anak="Model dari Teluk Weda" />
          <div style={{ marginTop: 18 }}>
            <Judul anak="Dilatih dari 300 titik yang dilabeli secara visual" ukuran={48} />
          </div>
          <div style={{ marginTop: 30 }}>
            <Garis anak="AlphaEarth merangkum citra satelit setahun penuh untuk setiap petak 10 × 10 m." tampil={a} />
          </div>
          <div style={{ marginTop: 34, opacity: b }}>
            <Legenda
              isi={[
                ["Tanah terbuka (gundul, bangunan)", warna.bara],
                ["Terganggu, mulai menghijau", warna.nyala],
                ["Batas petak tambang 1 km", warna.kapur],
              ]}
              ukuran={22}
            />
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Cek: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const C = D.cek as Record<string, { terbuka: number; terganggu: number; vegetasi: number; n: number }>;
  const t1 = masuk(f, Math.round(panjang * 0.3), 24);
  const t2 = masuk(f, Math.round(panjang * 0.55), 24);
  const t3 = masuk(f, Math.round(panjang * 0.72), 24);
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Bkg sumber={T.sumberCek} tampil={a} />
      <Kolom jarak={0}>
        <div style={{ display: "flex", gap: 70, alignItems: "center" }}>
          <div style={{ width: 1060 }}>
            <div style={{ opacity: a }}>
              <Alis anak="Apakah model bekerja di luar Weda?" />
              <div style={{ marginTop: 18 }}>
                <Judul anak={`${D.titik} titik acak di luar Weda, diperiksa secara visual`} ukuran={50} />
              </div>
            </div>
            <div style={{ marginTop: 40, display: "flex", flexDirection: "column", gap: 24 }}>
              <Tumpuk judul={`Peta: terbuka (${C.open.n} titik)`} c={C.open} tampil={t1} W={1000} />
              <Tumpuk judul={`Peta: terganggu (${C.disturbed.n} titik)`} c={C.disturbed} tampil={t2} W={1000} />
              <Tumpuk judul={`Peta: lainnya (${C.other.n} titik)`} c={C.other} tampil={t3} W={1000} />
            </div>
            <div style={{ marginTop: 22 }}>
              <Legenda isi={LEG_CEK} tampil={t1} ukuran={21} />
            </div>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {D.chips.slice(0, 3).map((ch, i) => {
              const o = masuk(f, Math.round(panjang * 0.1) + i * 14, 18);
              return (
                <div key={ch.id} style={{ display: "flex", gap: 18, alignItems: "center", opacity: o }}>
                  <Img src={staticFile(`tambang/chip_${ch.id}.jpg`)} style={{ width: 230, height: 230 }} />
                  <div style={{ fontFamily: tubuhFont, fontSize: 22, lineHeight: 1.5 }}>
                    <div style={{ color: warna.abu }}>
                      Peta: <span style={{ color: warna.bara, fontWeight: 600 }}>{NAMA_PETA[ch.peta]}</span>
                    </div>
                    <div style={{ color: warna.abu }}>
                      Label: <span style={{ color: warna.kapur, fontWeight: 600 }}>{NAMA_KELAS[ch.label] ?? ch.label}</span>
                    </div>
                  </div>
                </div>
              );
            })}
            <div style={{ fontFamily: tubuhFont, fontSize: 17, color: warna.samar, maxWidth: 420 }}>Sentinel-2 2025, 800 m; kotak kuning = piksel yang dilabeli</div>
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Luas: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const b = masuk(f, Math.round(panjang * 0.12), 24);
  const c = masuk(f, Math.round(panjang * 0.5), 24);
  const L = D.total;
  const maks = L.plus[0] + L.plus[1];
  return (
    <Lembut panjang={panjang}>
      <Panel gambar={["timur_2019.jpg", "timur_2025.jpg", "timur_peta.jpg"]} panjang={panjang} dari={0.12} sampai={0.75} tanda={(i) => ["2019", "2025", "Hasil model 2025"][i] + " · Halmahera Timur"} />
      <Bkg sumber={T.sumberLuas} tampil={a} />
      <Kolom jarak={0}>
        <div style={{ width: 640, opacity: a }}>
          <Alis anak="Setelah dikoreksi dengan label, 2025" />
          <div style={{ marginTop: 22, opacity: b }}>
            <Angka anak={`≈ ${ribuan(ratus(L.terbuka[0]))}`} ukuran={96} warnaA={warna.bara} />
            <div style={{ fontFamily: tubuhFont, fontSize: 26, color: warna.kapur, marginTop: 6 }}>hektare tanah gundul dan bangunan</div>
          </div>
          <div style={{ marginTop: 26, opacity: c }}>
            <Angka anak={`≈ ${ribuan(ratus(L.plus[0]))}`} ukuran={72} warnaA={warna.nyala} />
            <div style={{ fontFamily: tubuhFont, fontSize: 26, color: warna.kapur, marginTop: 6 }}>hektare termasuk yang mulai menghijau</div>
          </div>
          <div style={{ marginTop: 34, display: "flex", flexDirection: "column", gap: 12, opacity: c }}>
            <Batang label="Angka peta" nilai={L.peta_plus} maks={maks} teks={ribuan(L.peta_plus)} w={warna.abu} tampil={c} lebar={230} labelW={170} />
            <Batang label="Dari label" nilai={L.plus[0]} maks={maks} teks={pm(L.plus)} w={warna.nyala} tampil={c} lebar={230} galat={L.plus[1]} labelW={170} />
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Kabupaten: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const K = D.kabupaten;
  const maks = Math.max(...K.map((k) => k.plus[0] + k.plus[1]));
  return (
    <Lembut panjang={panjang}>
      <Panel gambar={["selatan_2019.jpg", "selatan_2025.jpg"]} panjang={panjang} dari={0.25} sampai={0.6} tanda={(i) => `${["2019", "2025"][i]} · Pulau Obi, Halmahera Selatan`} />
      <Bkg sumber={T.sumberLuas} tampil={a} />
      <Kolom jarak={0}>
        <div style={{ width: 700, opacity: a }}>
          <Alis anak="Per kabupaten, 2025" />
          <div style={{ marginTop: 18 }}>
            <Judul anak="Hampir semuanya di tiga kabupaten" ukuran={50} />
          </div>
          <div style={{ fontFamily: tubuhFont, fontSize: 22, color: warna.abu, marginTop: 24, marginBottom: 14 }}>Terbuka + terganggu, hektare (selang 95%)</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {K.map((k, i) => (
              <Batang
                key={k.nama}
                label={k.nama}
                nilai={k.plus[0]}
                maks={maks}
                teks={ribuan(k.plus[0])}
                w={i < 3 ? warna.bara : warna.abu}
                tampil={masuk(f, Math.round(panjang * 0.1) + i * 10, 18)}
                lebar={230}
                galat={k.plus[1]}
                labelW={230}
                ukuran={22}
              />
            ))}
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Tahun: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const nilai = D.tahun_plus;
  const t0 = panjang * 0.08, t1 = panjang * 0.6;
  const jam = (i: number) => t0 + (i / (nilai.length - 1)) * (t1 - t0);
  const puncak = nilai.indexOf(Math.max(...nilai.slice(1)));
  return (
    <Lembut panjang={panjang}>
      <Panel gambar={["tengah_2019.jpg", "tengah_2025.jpg"]} panjang={panjang} dari={0.2} sampai={0.6} tanda={(i) => `${["2019", "2025"][i]} · Pulau Gebe, Halmahera Tengah`} />
      <Bkg sumber={T.sumberTahun} tampil={a} />
      <Kolom jarak={0}>
        <div style={{ width: 660, opacity: a }}>
          <Alis anak="Kapan dibuka?" />
          <div style={{ fontFamily: tubuhFont, fontSize: 25, color: warna.kapur, marginTop: 20, marginBottom: 4 }}>Terbuka + terganggu 2025, menurut tahun pertama berubah (ha)</div>
          <BatangTahun
            tahun={D.tahun}
            nilai={nilai}
            W={640}
            tampil={(i) => masuk(f, jam(i), 14)}
            warnaI={(i) => (i === 0 ? ABU_GELAP : i === puncak ? warna.nyala : warna.bara)}
            label={(i) => (i === puncak || i === nilai.length - 1 ? ribuan(nilai[i]) : null)}
          />
          <Legenda isi={[["≤ 2019 atau tahun tak diketahui", "#7E8792"], ["Dibuka tahun itu", warna.bara], ["Puncak", warna.nyala]]} tampil={a} />
        </div>
      </Kolom>
    </Lembut>
  );
};

const Geser: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const tiga = D.kabupaten.slice(0, 3);
  const maks = Math.max(...tiga.flatMap((k) => k.tahun.slice(1)));
  const mulai = [0.12, 0.38, 0.62];
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Bkg sumber={T.sumberTahun} tampil={a} />
      <Kolom jarak={30}>
        <div style={{ opacity: a }}>
          <Alis anak="Polanya bergeser" />
          <div style={{ marginTop: 18 }}>
            <Judul anak="Dibuka per tahun, 2020–2025 (ha)" ukuran={52} />
          </div>
        </div>
        <div style={{ display: "flex", gap: 60 }}>
          {tiga.map((k, j) => {
            const o = masuk(f, Math.round(panjang * mulai[j]), 22);
            const v = k.tahun.slice(1);
            const pk = v.indexOf(Math.max(...v));
            return (
              <div key={k.nama} style={{ opacity: o }}>
                <div style={{ fontFamily: judulFont, fontWeight: 800, fontSize: 34, color: warna.kapur, marginBottom: 6 }}>{k.nama}</div>
                <BatangTahun
                  tahun={D.tahun.slice(1)}
                  nilai={v}
                  maks={maks}
                  W={500}
                  H={300}
                  tampil={(i) => masuk(f, Math.round(panjang * mulai[j]) + i * 5, 12)}
                  warnaI={(i) => (i === pk ? warna.nyala : warna.bara)}
                  label={(i) => (i === pk || i === v.length - 1 ? ribuan(v[i]) : null)}
                />
              </div>
            );
          })}
        </div>
      </Kolom>
    </Lembut>
  );
};

const Tutup: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 4, 22);
  const b = masuk(f, Math.round(panjang * 0.25), 24);
  const d = masuk(f, Math.round(panjang * 0.7), 24);
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Kolom jarak={30}>
        <h1 style={{ fontFamily: judulFont, fontWeight: 900, fontSize: 64, lineHeight: 1.06, color: warna.kapur, margin: 0, opacity: a, maxWidth: 1500 }}>
          Angka ini kemungkinan masih di bawah kenyataan.
        </h1>
        <h2 style={{ fontFamily: judulFont, fontWeight: 900, fontSize: 44, lineHeight: 1.12, color: warna.bara, margin: 0, opacity: b, maxWidth: 1500 }}>
          Petak tambang hanya menandai hutan yang hilang karena tambang sampai 2024. Tambang di lahan bukan hutan dan bukaan yang lebih baru belum terhitung.
        </h2>
        <div style={{ opacity: d, borderLeft: `3px solid ${warna.garis}`, paddingLeft: 20, fontFamily: tubuhFont, fontSize: 26, color: warna.abu, lineHeight: 1.45, maxWidth: 1400, marginTop: 10 }}>
          Label dibuat oleh satu orang dan belum dicek di lapangan.
        </div>
      </Kolom>
    </Lembut>
  );
};

const BARIS_SUMBER: [string, string][] = [
  ["Petak tambang", "WRI/Google, Drivers of Forest Loss 1 km v1.2 (2001–2024), kelas tambang & energi"],
  ["Model", "AlphaEarth Foundations Satellite Embedding 2019–2025 (Google DeepMind); random forest dari 297 label Weda/Sagea"],
  ["Citra", "Sentinel-2 L2A (Copernicus), median tahunan, Cloud Score+"],
  ["Pemeriksaan", "150 titik acak berlapis di luar Weda/Sagea, dilabeli dari Sentinel-2 2025 (satu pelabel)"],
  ["Luas", "rata-rata berstrata dari label, selang 95%; per kabupaten memakai laju galat se-provinsi"],
  ["Batas", "FAO GAUL 2025; air: JRC Global Surface Water 1.4 · analisis November 2026"],
];

const KartuSumber: React.FC<{ panjang: number }> = () => {
  const f = useCurrentFrame();
  const a = masuk(f, 4, 20);
  return (
    <AbsoluteFill style={{ backgroundColor: warna.jelaga, opacity: a }}>
      <Kolom jarak={18}>
        <Alis anak="Sumber data" />
        <div style={{ display: "flex", flexDirection: "column", gap: 11, width: 1680 }}>
          {BARIS_SUMBER.map(([k, v]) => (
            <div key={k} style={{ display: "flex", gap: 28, alignItems: "baseline" }}>
              <div style={{ width: 220, fontFamily: tubuhFont, fontSize: 24, fontWeight: 600, color: warna.kapur }}>{k}</div>
              <div style={{ fontFamily: tubuhFont, fontSize: 24, color: warna.abu }}>{v}</div>
            </div>
          ))}
        </div>
        <div style={{ marginTop: 12, paddingTop: 16, borderTop: `2px solid ${warna.bara}`, fontFamily: tubuhFont, fontSize: 22, color: warna.kapur, lineHeight: 1.5, maxWidth: 1680 }}>
          Lahan terbuka bukan bukti pelaku; sebagian adalah jalan, permukiman, dan kawasan industri di dalam petak tambang. Angka satelit dapat berbeda dari data resmi. Tidak ada perusahaan yang disebut.
        </div>
      </Kolom>
    </AbsoluteFill>
  );
};

/* --------------------------------- film ------------------------------ */

const ADEGAN: Record<string, React.FC<{ panjang: number }>> = {
  "01-buka": Buka,
  "02-model": Model,
  "03-cek": Cek,
  "04-luas": Luas,
  "05-kabupaten": Kabupaten,
  "06-tahun": Tahun,
  "07-geser": Geser,
  "08-tutup": Tutup,
};

export const TambangFilm: React.FC = () => {
  const J = JADWAL_TAMBANG;
  return (
    <AbsoluteFill style={{ backgroundColor: warna.jelaga }}>
      <Audio src={staticFile(`${AUDIO}/musik-tambang.mp3`)} />
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
  <div style={{ borderTop: `2px solid ${warna.garis}`, paddingTop: 20 }}>
    <div style={{ fontFamily: tubuhFont, fontSize: 21, fontWeight: 600, letterSpacing: "0.16em", textTransform: "uppercase", color: warna.bara, marginBottom: 14 }}>{judul}</div>
    {children}
  </div>
);

/** Two 1080x1350 (4:5) pages: 1 = how much and where, 2 = when, and how it was checked. */
export const InfografisTambang: React.FC<{ halaman?: 1 | 2 }> = ({ halaman = 1 }) => {
  const kecil = { fontFamily: tubuhFont, fontSize: 20, color: warna.abu, lineHeight: 1.4 } as React.CSSProperties;
  const L = D.total;
  const K = D.kabupaten;
  const kepala = (
    <div style={{ borderTop: `3px solid ${warna.bara}`, paddingTop: 16, display: "flex", justifyContent: "space-between" }}>
      <Alis anak={T.kiri} />
      <span style={{ fontFamily: tubuhFont, fontSize: 19, letterSpacing: "0.18em", color: warna.abu, textTransform: "uppercase" }}>
        {T.waktu} · {halaman}/2
      </span>
    </div>
  );
  const kaki = (
    <div style={{ ...kecil, fontSize: 15, borderTop: `1px solid ${warna.garis}`, paddingTop: 12, marginTop: "auto" }}>
      {(halaman === 1 ? BARIS_SUMBER : BARIS_SUMBER.slice(0, 4)).map(([k, v]) => `${k}: ${v}`).join(" · ")}. Satu pelabel, tanpa cek lapangan. Tidak ada perusahaan yang disebut.
    </div>
  );
  if (halaman === 1) {
    const maks = Math.max(...K.map((k) => k.plus[0] + k.plus[1]));
    return (
      <AbsoluteFill style={{ backgroundColor: warna.jelaga, padding: "46px 54px 40px", display: "flex", flexDirection: "column", gap: 22 }}>
        <div>
          {kepala}
          <h1 style={{ fontFamily: judulFont, fontWeight: 900, fontSize: 62, lineHeight: 0.96, letterSpacing: "-0.035em", color: warna.kapur, margin: "22px 0 0" }}>
            Jejak tambang di Maluku Utara
          </h1>
        </div>
        <div style={{ display: "flex", gap: 24, alignItems: "center" }}>
          <div style={{ width: 520 }}>
            <div style={{ ...kecil, color: warna.kapur, fontSize: 22 }}>Tanah terbuka di petak tambang, 2025</div>
            <Angka anak={ribuan(ratus(L.plus[0]))} ukuran={92} />
            <div style={{ fontFamily: tubuhFont, fontSize: 24, color: warna.kapur }}>hektare, termasuk yang mulai menghijau</div>
            <div style={{ ...kecil, fontSize: 21, marginTop: 10 }}>selang 95%: {ribuan(L.plus[0] - L.plus[1])}–{ribuan(L.plus[0] + L.plus[1])} ha</div>
            <div style={{ ...kecil, fontSize: 22, marginTop: 14, color: warna.kapur }}>
              Gundul dan bangunan saja: <span style={{ ...angkaGaya, color: warna.bara, fontWeight: 600 }}>{pm(L.terbuka)}</span> ha
            </div>
            <div style={{ ...kecil, fontSize: 21, marginTop: 14 }}>Petak tambang (1 km) mencakup {ribuan(D.sel_ha)} ha daratan.</div>
          </div>
          <div style={{ width: 430, height: 470, overflow: "hidden", position: "relative" }}>
            <Img src={staticFile("tambang/peta_tambang_kecil.jpg")} style={{ position: "absolute", width: 430, height: 470 }} />
          </div>
        </div>
        <Kotak judul="Per kabupaten · terbuka + terganggu (ha)">
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {K.map((k, i) => (
              <Batang key={k.nama} label={k.nama} nilai={k.plus[0]} maks={maks} teks={pm(k.plus)} w={i < 3 ? warna.bara : warna.abu} tampil={1} lebar={390} galat={k.plus[1]} labelW={240} ukuran={21} />
            ))}
          </div>
        </Kotak>
        <div style={{ ...kecil, fontSize: 21, color: warna.kapur }}>
          Angka ini kemungkinan di bawah kenyataan: petak tambang hanya menandai hutan yang hilang karena tambang sampai 2024.
        </div>
        {kaki}
      </AbsoluteFill>
    );
  }
  const C = D.cek as Record<string, { terbuka: number; terganggu: number; vegetasi: number; n: number }>;
  const nilai = D.tahun_plus;
  const pk = nilai.indexOf(Math.max(...nilai.slice(1)));
  const tiga = K.slice(0, 3);
  const mx = Math.max(...tiga.flatMap((k) => k.tahun.slice(1)));
  return (
    <AbsoluteFill style={{ backgroundColor: warna.jelaga, padding: "46px 54px 36px", display: "flex", flexDirection: "column", gap: 16 }}>
      <div>
        {kepala}
        <h1 style={{ fontFamily: judulFont, fontWeight: 900, fontSize: 48, lineHeight: 1, letterSpacing: "-0.03em", color: warna.kapur, margin: "20px 0 0" }}>
          Kapan dibuka, dan bagaimana diperiksa
        </h1>
      </div>
      <Kotak judul="Terbuka + terganggu 2025, menurut tahun pertama berubah (ha)">
        <BatangTahun
          tahun={D.tahun}
          nilai={nilai}
          W={970}
          H={150}
          tampil={() => 1}
          warnaI={(i) => (i === 0 ? ABU_GELAP : i === pk ? warna.nyala : warna.bara)}
          label={(i) => ribuan(nilai[i])}
        />
        <div style={{ ...kecil, fontSize: 18 }}>≤ 2019 termasuk bukaan yang tahunnya tak diketahui.</div>
      </Kotak>
      <Kotak judul="Polanya bergeser · dibuka per tahun 2020–2025 (ha)">
        <div style={{ display: "flex", gap: 20 }}>
          {tiga.map((k) => {
            const v = k.tahun.slice(1);
            const p = v.indexOf(Math.max(...v));
            return (
              <div key={k.nama}>
                <div style={{ fontFamily: tubuhFont, fontWeight: 600, fontSize: 21, color: warna.kapur }}>{k.nama}</div>
                <BatangTahun
                  tahun={["20", "21", "22", "23", "24", "25"]}
                  nilai={v}
                  maks={mx}
                  W={310}
                  H={110}
                  ukuran={17}
                  tampil={() => 1}
                  warnaI={(i) => (i === p ? warna.nyala : warna.bara)}
                  label={(i) => (i === p || i === v.length - 1 ? ribuan(v[i]) : null)}
                />
              </div>
            );
          })}
        </div>
      </Kotak>
      <Kotak judul={`Diperiksa: ${D.titik} titik acak di luar Teluk Weda`}>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <Tumpuk judul={`Peta: terbuka (${C.open.n})`} c={C.open} tampil={1} W={970} ukuran={20} />
          <Tumpuk judul={`Peta: terganggu (${C.disturbed.n})`} c={C.disturbed} tampil={1} W={970} ukuran={20} />
          <Tumpuk judul={`Peta: lainnya (${C.other.n})`} c={C.other} tampil={1} W={970} ukuran={20} />
        </div>
        <div style={{ marginTop: 10 }}>
          <Legenda isi={LEG_CEK} ukuran={18} />
        </div>
      </Kotak>
      {kaki}
    </AbsoluteFill>
  );
};
