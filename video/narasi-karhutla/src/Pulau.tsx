/**
 * "Benarkah Sawit Membakar Kalimantan?" — Part 4 of the concessions film.
 *
 * Parts 1–3 followed four Ketapang concessions that burned worse than the
 * land around them. Part 4 tests the question across Kalimantan:
 *
 *   compare        1,095 concessions vs similar unpermitted land, 200 m cells
 *   island-wide    oil palm x0.85, wood fibre x0.94; same in 2015/2019/2023
 *   the few        54 of 908 oil-palm units: 6% of units, 46% of burned area
 *   peat           excess follows peat share, not group / permit / RSPO
 *   clearing       no evidence: 2015 burns planted no more than unburned land
 *   timing         concession land starts burning at milder drought
 *   two seasons    the drought came from the south; where weather matched,
 *                  Indonesian land still burned ~4x more than Malaysian
 *
 * Same palette, type, components and audio pipeline as Radar.tsx. Every
 * figure comes from pulauData.json (scripts/kalimantan_film4_assets.py).
 */

import React from "react";
import { AbsoluteFill, Audio, Img, interpolate, Sequence, staticFile, useCurrentFrame } from "remotion";
import { JADWAL_PULAU } from "./jadwalPulau";
import { Bingkai, Judul, Keterangan, Kolom, LatarDiam, Lembut, masuk } from "./komponen";
import { angkaGaya, judulFont, koma, ribuan, tubuhFont, warna } from "./teema";
import D from "./pulauData.json";

const ABU_GELAP = "#3A424D";

const T = {
  audio: "audio/pulau",
  musik: "musik-pulau.mp3",
  kiri: "Karhutla Kalimantan · Bagian 4",
  waktu: "November 2026",
  alisJudul: "Di dalam konsesi · Bagian 4",
  judul: ["BENARKAH SAWIT", "MEMBAKAR", "KALIMANTAN?"],
  subJudul: "Lebih dari seribu konsesi di seluruh Kalimantan, dibandingkan dengan lahan serupa tanpa izin, musim kebakaran 2026.",
  kilas1: "Empat konsesi di Ketapang terbakar lebih parah.",
  kilas2: "Apakah itu terjadi di seluruh Kalimantan?",
  sumberPeta: "Konsesi: Global Forest Watch (sawit, c. 2012; HTI, KLHK 2010) · batas negara: Natural Earth",
  alisBanding: "Perbandingan setara",
  konsesi: "konsesi dianalisis",
  rincianKonsesi: `${D.per_concession["oil palm"].units} kebun sawit · ${D.per_concession.pulpwood.units} hutan tanaman industri`,
  petak: "petak 200 m",
  disamakan: "Disamakan dengan lahan tanpa izin:",
  strata: ["ada gambut atau tidak", "kedalaman gambut", "tutupan lahan", "riwayat kebakaran", "jarak ke sungai", "jarak ke permukiman"],
  sumberPulau:
    "2026: Sentinel-2 dNBR, terbakar bila ≥ separuh petak dan ada titik panas VIIRS · 2015–2023: MODIS MCD64A1 · pencocokan setara (CEM), selang 95% dari bootstrap blok 5 km",
  judulPulau: "Terbakar dibanding lahan serupa tanpa izin",
  baris: [
    ["Kebun sawit, 2026", "s", "oil palm"],
    ["Hutan tanaman industri, 2026", "s", "pulpwood"],
    ["Kebun sawit, 2015", "2015", "oil palm"],
    ["Kebun sawit, 2019", "2019", "oil palm"],
    ["Kebun sawit, 2023", "2023", "oil palm"],
    ["Kebun sawit, peta gambut lain", "g", "oil palm"],
  ] as [string, string, "oil palm" | "pulpwood"][],
  lebihSedikit: "← lebih sedikit",
  lebihBanyak: "lebih banyak →",
  sama: "sama",
  sumberSedikit:
    "Rasio tiap konsesi dengan lahan serupa; berlebih = selang 95% di atas 1 setelah koreksi uji berganda (Benjamini–Hochberg, q ≤ 0,05)",
  alisSedikit: "Terbakar berlebih",
  dariSawit: `dari ${D.per_concession["oil palm"].units} kebun sawit`,
  jumlah: "bagian dari jumlah konsesi",
  luas: "bagian dari luas bekas bakar di kebun sawit",
  hti: (n: number, dari: number, pct: string) => `Hutan tanaman industri: ${n} dari ${dari} konsesi, ${pct} luas bekas bakarnya.`,
  empat: "Keempat konsesi Ketapang termasuk di dalamnya.",
  sumberGambut:
    "Gambut: BBSDLP (Kementan) dan Greifswald Global Peatland Map 2.0 · grup, status izin: Global Forest Watch · RSPO: GFW 2020",
  judulGambut: "Kebun sawit yang terbakar berlebih, menurut luas gambut di dalamnya",
  sumbuGambut: "bagian konsesi yang bergambut",
  bukan: "Tidak membedakan:",
  bukanDaftar: ["grup perusahaan", "status izin", "sertifikat RSPO"],
  sumberBersih:
    "Penanaman: Descals dkk. 2024 (tahun tanam sawit, sampai 2021) · bekas bakar 2015: MODIS MCD64A1 · pembersihan: Sentinel-2 NDVI Des–Mar vs Mei–Jul 2026",
  judulBersih: "Apakah api dipakai untuk membuka lahan?",
  tanam: "Menjadi kebun sawit 2016–2021",
  tanamK: ["terbakar 2015", "tidak terbakar"],
  bersih: "Dibersihkan sebelum api 2026",
  bersihK: ["di kebun sawit", "lahan serupa"],
  bersihKet: "Tidak ada bukti pembukaan lahan dengan api.",
  sumberKering:
    "Drought Code (Van Wagner 1987) dihitung harian dari ERA5-Land · titik api baru: akar silsilah deteksi VIIRS, Jul–Okt 2026, per 1.000 km² per hari",
  judulKering: "Titik api baru, kebun sawit dibanding lahan terbuka",
  sumbuKering: "Drought Code hari itu",
  kaliLipat: "kali lipat",
  dcPertama: "Drought Code saat lahan sawit pertama terbakar, dibanding lahan serupa",
  lebihAwal: "Menyala lebih awal, saat kekeringan belum separah.",
  sumberBatas:
    "Hujan: CHIRPS, 1 Jul – 30 Sep 2026 dibanding rata-rata 2001–2025 · Drought Code: ERA5-Land · Malaysia: GFW / RimbaWatch 2025 · disamakan juga dengan tinggi, lereng, dan kekeringan",
  alisBatas: "Hujan Juli–September 2026, dibanding normal",
  wilayah: {
    "IDN|-4.5": "Kalimantan selatan",
    "IDN|-2.0": "Kalimantan tengah",
    "IDN|2.0": "Kalimantan utara",
    "MYS|2.0": "Sabah dan Sarawak",
  } as Record<string, string>,
  samaCuaca: "lebih banyak lahan terbakar di sisi Indonesia, di tempat yang cuacanya sama",
  tutup1: "Benarkah sawit membakar Kalimantan?",
  tutup2: "Tidak secara umum.",
  tutupKet: "Sekelompok kecil konsesi di atas gambut, yang mengering dan menyala lebih awal.",
  tutup3:
    "Gambut yang dikeringkan adalah penjelasan yang paling cocok, tetapi belum terukur langsung. Batas konsesi publik berasal dari 2012. Hasil ini belum melalui telaah sejawat.",
  sumberData: "Sumber data",
  barisSumber: [
    ["Bekas bakar", "Sentinel-2 L2A dNBR 2026 (Copernicus); MODIS MCD64A1 2015–2026 (NASA)"],
    ["Titik panas", "VIIRS 375 m, S-NPP dan NOAA-20 (NASA LANCE / FIRMS)"],
    ["Konsesi", "Global Forest Watch: sawit (c. 2012), HTI (KLHK 2010), RSPO (2020), Malaysia (RimbaWatch 2025)"],
    ["Gambut", "BBSDLP Kementan; Greifswald Global Peatland Map 2.0; PEATGRIDS"],
    ["Penanaman", "Descals dkk. 2024, Global Oil Palm Extent and Planting Year"],
    ["Cuaca", "ERA5-Land (ECMWF/Copernicus); CHIRPS (UCSB)"],
    ["Medan", "SRTM; Hansen dkk. Global Forest Change; GHSL"],
  ],
  peringatan:
    "Rasio membandingkan lahan dengan ciri yang sama, bukan bukti siapa yang menyalakan api. Batas konsesi publik berasal dari sekitar 2012. Hasil ini belum melalui telaah sejawat dan dapat berubah.",
};

/* ------------------------------ furniture ----------------------------- */

const Bkg: React.FC<{ sumber?: string; tampil?: number }> = ({ sumber, tampil }) => (
  <Bingkai kiri={T.kiri} waktu={T.waktu} labelSumber="Sumber" sumber={sumber} tampil={tampil} />
);

const Gambar: React.FC<{ berkas: string; panjang?: number; zoom?: number; redup?: number }> = ({
  berkas,
  panjang = 1,
  zoom = 1,
  redup = 0,
}) => {
  const f = useCurrentFrame();
  const s = interpolate(f, [0, panjang], [1, zoom], { extrapolateRight: "clamp" });
  return (
    <AbsoluteFill style={{ backgroundColor: warna.jelaga, overflow: "hidden" }}>
      <Img
        src={staticFile(`pulau/${berkas}`)}
        style={{ width: "100%", height: "100%", transform: `scale(${s})`, transformOrigin: "72% 60%", opacity: 1 - redup }}
      />
      <AbsoluteFill
        style={{ background: `linear-gradient(90deg, ${warna.jelaga} 0%, rgba(10,12,15,0.9) 32%, rgba(10,12,15,0) 50%)` }}
      />
    </AbsoluteFill>
  );
};

const Alis: React.FC<{ anak: string }> = ({ anak }) => (
  <div style={{ fontFamily: tubuhFont, fontSize: 21, fontWeight: 600, letterSpacing: "0.22em", textTransform: "uppercase", color: warna.bara }}>
    {anak}
  </div>
);

const Angka: React.FC<{ anak: string; ukuran?: number; warnaA?: string }> = ({ anak, ukuran = 150, warnaA = warna.nyala }) => (
  <div style={{ ...angkaGaya, fontSize: ukuran, fontWeight: 600, color: warnaA, lineHeight: 1 }}>{anak}</div>
);

const Garis: React.FC<{ anak: string; tampil: number; lebar?: number }> = ({ anak, tampil, lebar = 620 }) => (
  <div
    style={{
      borderLeft: `3px solid ${warna.bara}`,
      paddingLeft: 18,
      fontFamily: tubuhFont,
      fontSize: 27,
      color: warna.kapur,
      lineHeight: 1.35,
      maxWidth: lebar,
      opacity: tampil,
    }}
  >
    {anak}
  </div>
);

const kali = (x: number, d = 2) => `×${koma(x, d)}`;

/* ---------------------------------- scenes --------------------------- */

const KartuJudul: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 4, 24);
  return (
    <Lembut panjang={panjang}>
      <Gambar berkas="peta_berlebih.jpg" panjang={panjang} zoom={1.05} redup={0.4} />
      <Kolom jarak={26}>
        <div style={{ opacity: a, transform: `translateY(${(1 - a) * 20}px)` }}>
          <div style={{ marginBottom: 24 }}>
            <Alis anak={T.alisJudul} />
          </div>
          <h1 style={{ fontFamily: judulFont, fontWeight: 900, fontSize: 104, lineHeight: 0.94, letterSpacing: "-0.04em", color: warna.kapur, margin: 0 }}>
            {T.judul.map((l, i) => (
              <React.Fragment key={l}>
                {i > 0 && <br />}
                {l}
              </React.Fragment>
            ))}
          </h1>
          <div style={{ marginTop: 28 }}>
            <Keterangan lebar={720} anak={T.subJudul} />
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Kilas: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 4, 22);
  const b = masuk(f, Math.round(panjang * 0.45), 22);
  const besar: React.CSSProperties = { fontFamily: judulFont, fontWeight: 900, fontSize: 92, lineHeight: 1.04, letterSpacing: "-0.03em", margin: 0, maxWidth: 1600 };
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Kolom jarak={22}>
        <h1 style={{ ...besar, color: warna.abu, opacity: a }}>{T.kilas1}</h1>
        <h2 style={{ ...besar, color: warna.kapur, opacity: b, transform: `translateY(${(1 - b) * 18}px)` }}>{T.kilas2}</h2>
      </Kolom>
    </Lembut>
  );
};

const Banding: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const b = masuk(f, Math.round(panjang * 0.18), 20);
  return (
    <Lembut panjang={panjang}>
      <Gambar berkas="peta_semua.jpg" panjang={panjang} zoom={1.04} />
      <Bkg sumber={T.sumberPeta} tampil={a} />
      <Kolom jarak={0}>
        <div style={{ width: 680, opacity: a }}>
          <Alis anak={T.alisBanding} />
          <div style={{ display: "flex", gap: 44, marginTop: 16, alignItems: "flex-end" }}>
            <div>
              <Angka anak={ribuan(D.units_total)} ukuran={110} />
              <div style={{ fontFamily: tubuhFont, fontSize: 22, color: warna.abu, marginTop: 6 }}>{T.konsesi}</div>
            </div>
            <div style={{ opacity: b }}>
              <div style={{ whiteSpace: "nowrap" }}>
                <Angka anak={`${koma(D.cells_millions, 1)} juta`} ukuran={62} warnaA={warna.kapur} />
              </div>
              <div style={{ fontFamily: tubuhFont, fontSize: 22, color: warna.abu, marginTop: 6 }}>{T.petak}</div>
            </div>
          </div>
          <div style={{ fontFamily: tubuhFont, fontSize: 21, color: warna.abu, marginTop: 10 }}>{T.rincianKonsesi}</div>
          <div style={{ fontFamily: tubuhFont, fontSize: 24, color: warna.kapur, marginTop: 34, marginBottom: 12 }}>{T.disamakan}</div>
          {T.strata.map((s, i) => {
            const o = masuk(f, Math.round(panjang * 0.3) + i * 14, 16);
            return (
              <div key={s} style={{ display: "flex", alignItems: "center", gap: 14, opacity: o, fontFamily: tubuhFont, fontSize: 26, color: warna.kapur, marginTop: 8 }}>
                <div style={{ width: 10, height: 10, background: warna.bara, transform: "rotate(45deg)" }} />
                {s}
              </div>
            );
          })}
        </div>
      </Kolom>
    </Lembut>
  );
};

/** Ratio forest plot, log x from 0.4 to 1.6, line at 1. */
const Hutan: React.FC<{ tampil: number; f: number; mulai: number }> = ({ tampil, f, mulai }) => {
  const W = 1500;
  const L = 520;
  const R = 200;
  const lo = Math.log(0.4);
  const hi = Math.log(1.6);
  const x = (v: number) => L + ((Math.log(v) - lo) / (hi - lo)) * (W - L - R);
  const tinggiBaris = 74;
  const nilai = (kode: string, jenis: "oil palm" | "pulpwood") => {
    if (kode === "s") return D.matched[jenis];
    if (kode === "g") return D.gpm[jenis];
    return D.seasons[kode as "2015" | "2019" | "2023"][jenis];
  };
  const H = T.baris.length * tinggiBaris + 70;
  return (
    <svg width={W} height={H} style={{ opacity: tampil }}>
      <line x1={x(1)} x2={x(1)} y1={0} y2={H - 50} stroke={warna.abu} strokeWidth={2} strokeDasharray="6 6" />
      <text x={x(1) + 10} y={H - 54} fill={warna.abu} fontSize={22} textAnchor="start" fontFamily={tubuhFont}>
        {T.sama}
      </text>
      <text x={x(1) - 16} y={H - 14} fill={warna.samar} fontSize={22} textAnchor="end" fontFamily={tubuhFont}>
        {T.lebihSedikit}
      </text>
      <text x={x(1) + 16} y={H - 14} fill={warna.samar} fontSize={22} textAnchor="start" fontFamily={tubuhFont}>
        {T.lebihBanyak}
      </text>
      {[0.5, 0.75, 1.25, 1.5].map((v) => (
        <line key={v} x1={x(v)} x2={x(v)} y1={0} y2={H - 50} stroke={warna.garis} strokeWidth={1} />
      ))}
      {T.baris.map(([lab, kode, jenis], i) => {
        const r = nilai(kode, jenis);
        const o = masuk(f, mulai + i * 10, 16);
        const y = 30 + i * tinggiBaris;
        const utama = kode === "s";
        const w = jenis === "pulpwood" ? warna.abu : warna.nyala;
        return (
          <g key={lab} opacity={o}>
            <text x={0} y={y + 8} fill={utama ? warna.kapur : warna.abu} fontSize={utama ? 28 : 25} fontFamily={tubuhFont} fontWeight={utama ? 600 : 400}>
              {lab}
            </text>
            <line x1={x(r.ci[0])} x2={x(r.ci[1])} y1={y} y2={y} stroke={w} strokeWidth={4} />
            <circle cx={x(r.ratio)} cy={y} r={utama ? 13 : 10} fill={w} />
            <text x={W - R + 30} y={y + 9} fill={w} fontSize={30} fontFamily={angkaGaya.fontFamily as string} fontWeight={600}>
              {kali(r.ratio)}
            </text>
          </g>
        );
      })}
    </svg>
  );
};

const Pulau: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Bkg sumber={T.sumberPulau} tampil={a} />
      <Kolom jarak={34}>
        <div style={{ opacity: a }}>
          <Judul anak={T.judulPulau} ukuran={58} />
        </div>
        <Hutan tampil={a} f={f} mulai={Math.round(panjang * 0.12)} />
      </Kolom>
    </Lembut>
  );
};

const Batang: React.FC<{ label: string; nilai: number; maks: number; warnaB: string; tampil: number; lebar?: number; teks: string }> = ({
  label,
  nilai,
  maks,
  warnaB,
  tampil,
  lebar = 560,
  teks,
}) => (
  <div style={{ marginTop: 18 }}>
    <div style={{ fontFamily: tubuhFont, fontSize: 22, color: warna.abu, marginBottom: 8 }}>{label}</div>
    <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
      <div style={{ width: lebar, height: 34, background: warna.arang }}>
        <div style={{ width: (lebar * nilai * tampil) / maks, height: 34, background: warnaB }} />
      </div>
      <div style={{ ...angkaGaya, fontSize: 36, fontWeight: 600, color: warnaB, opacity: tampil }}>{teks}</div>
    </div>
  </div>
);

const Sedikit: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const b = masuk(f, Math.round(panjang * 0.3), 30);
  const c = masuk(f, Math.round(panjang * 0.62), 22);
  const d = masuk(f, Math.round(panjang * 0.82), 22);
  const P = D.per_concession;
  return (
    <Lembut panjang={panjang}>
      <Gambar berkas="peta_berlebih.jpg" panjang={panjang} zoom={1.05} />
      <Bkg sumber={T.sumberSedikit} tampil={a} />
      <Kolom jarak={0}>
        <div style={{ width: 700, opacity: a }}>
          <Alis anak={T.alisSedikit} />
          <div style={{ display: "flex", alignItems: "baseline", gap: 18, marginTop: 12 }}>
            <Angka anak={ribuan(P["oil palm"].excess)} ukuran={140} warnaA={warna.bara} />
            <div style={{ fontFamily: tubuhFont, fontSize: 28, color: warna.kapur }}>{T.dariSawit}</div>
          </div>
          <Batang label={T.jumlah} nilai={P["oil palm"].excess_pct} maks={100} warnaB={warna.abu} tampil={b} teks={`${koma(P["oil palm"].excess_pct, 0)}%`} />
          <Batang label={T.luas} nilai={P["oil palm"].excess_share_pct} maks={100} warnaB={warna.bara} tampil={b} teks={`${koma(P["oil palm"].excess_share_pct, 0)}%`} />
          <div style={{ marginTop: 34 }}>
            <Garis
              anak={T.hti(P.pulpwood.excess, P.pulpwood.units, `${koma(P.pulpwood.excess_share_pct, 0)}%`)}
              tampil={c}
            />
          </div>
          <div style={{ fontFamily: tubuhFont, fontSize: 25, color: warna.nyala, marginTop: 22, opacity: d }}>{T.empat}</div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Gambut: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const c = masuk(f, Math.round(panjang * 0.05), 20);
  const B = D.peat_bins;
  const maks = 25;
  const H = 360;
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Bkg sumber={T.sumberGambut} tampil={a} />
      <Kolom jarak={30}>
        <div style={{ opacity: a }}>
          <Judul anak={T.judulGambut} ukuran={50} />
        </div>
        <div style={{ display: "flex", gap: 120, alignItems: "flex-end" }}>
          <div>
            <div style={{ display: "flex", gap: 34, alignItems: "flex-end", height: H + 60 }}>
              {B.map((b, i) => {
                const o = masuk(f, Math.round(panjang * 0.35) + i * 9, 22);
                const h = (H * b.excess_pct * o) / maks;
                const w = b.excess_pct > 15 ? warna.bara : warna.abu;
                return (
                  <div key={b.label} style={{ display: "flex", flexDirection: "column", alignItems: "center", width: 140 }}>
                    <div style={{ ...angkaGaya, fontSize: 34, fontWeight: 600, color: w, opacity: o, marginBottom: 8 }}>
                      {koma(b.excess_pct, 0)}%
                    </div>
                    <div style={{ width: 110, height: h, background: w }} />
                    <div style={{ fontFamily: tubuhFont, fontSize: 24, color: warna.kapur, marginTop: 12 }}>{b.label}%</div>
                  </div>
                );
              })}
            </div>
            <div style={{ fontFamily: tubuhFont, fontSize: 22, color: warna.abu, marginTop: 10 }}>{T.sumbuGambut}</div>
          </div>
          <div style={{ opacity: c, marginBottom: 60 }}>
            <div style={{ fontFamily: tubuhFont, fontSize: 24, color: warna.abu, marginBottom: 14 }}>{T.bukan}</div>
            {T.bukanDaftar.map((k, i) => (
              <div
                key={k}
                style={{
                  fontFamily: judulFont,
                  fontWeight: 800,
                  fontSize: 40,
                  color: warna.samar,
                  textDecoration: "line-through",
                  textDecorationColor: warna.bara,
                  textDecorationThickness: 4,
                  marginTop: 10,
                  opacity: masuk(f, Math.round(panjang * 0.05) + i * 12, 16),
                }}
              >
                {k}
              </div>
            ))}
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Pasangan: React.FC<{ judul: string; nilai: [number, number]; label: [string, string]; tampil: number }> = ({ judul, nilai, label, tampil }) => {
  const maks = 4;
  const H = 300;
  return (
    <div style={{ width: 520 }}>
      <div style={{ fontFamily: tubuhFont, fontSize: 26, color: warna.kapur, marginBottom: 22, minHeight: 70 }}>{judul}</div>
      <div style={{ display: "flex", gap: 40, alignItems: "flex-end", height: H + 50 }}>
        {nilai.map((v, i) => (
          <div key={i} style={{ display: "flex", flexDirection: "column", alignItems: "center", width: 180 }}>
            <div style={{ ...angkaGaya, fontSize: 44, fontWeight: 600, color: i ? warna.abu : warna.nyala, opacity: tampil, marginBottom: 8 }}>
              {koma(v, 1)}%
            </div>
            <div style={{ width: 130, height: (H * v * tampil) / maks, background: i ? ABU_GELAP : warna.nyala }} />
          </div>
        ))}
      </div>
      <div style={{ display: "flex", gap: 40, marginTop: 12 }}>
        {label.map((l) => (
          <div key={l} style={{ width: 180, textAlign: "center", fontFamily: tubuhFont, fontSize: 22, color: warna.abu }}>
            {l}
          </div>
        ))}
      </div>
    </div>
  );
};

const Bersih: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const b = masuk(f, Math.round(panjang * 0.25), 30);
  const c = masuk(f, Math.round(panjang * 0.6), 30);
  const d = masuk(f, Math.round(panjang * 0.82), 22);
  const L = D.landprep;
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Bkg sumber={T.sumberBersih} tampil={a} />
      <Kolom jarak={34}>
        <div style={{ opacity: a }}>
          <Judul anak={T.judulBersih} ukuran={58} />
        </div>
        <div style={{ display: "flex", gap: 120 }}>
          <Pasangan judul={T.tanam} nilai={[L.planted_burned_pct, L.planted_unburned_pct]} label={T.tanamK as [string, string]} tampil={b} />
          <Pasangan judul={T.bersih} nilai={[L.cleared_pct, L.cleared_ctl_pct]} label={T.bersihK as [string, string]} tampil={c} />
        </div>
        <Garis anak={T.bersihKet} tampil={d} lebar={1200} />
      </Kolom>
    </Lembut>
  );
};

const Kering: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const b = masuk(f, Math.round(panjang * 0.3), Math.round(panjang * 0.4));
  const c = masuk(f, Math.round(panjang * 0.05), 22);
  const I = D.ignitions_by_dc;
  const r = I.ratio_oil_palm;
  const W = 960;
  const H = 440;
  const L = 70;
  const x = (i: number) => L + (i / (r.length - 1)) * (W - L - 30);
  const y = (v: number) => H - 50 - (v / 3.4) * (H - 80);     // headroom over x3 for the 2.7 label
  const n = Math.max(1, Math.round(b * (r.length - 1)) + 1);
  const jalur = r.slice(0, n).map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const pita = I.bands.map((s) => s.replace("-2000", "+").replace("-", "–"));
  const W2 = D.drought_first_fire;
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Bkg sumber={T.sumberKering} tampil={a} />
      <Kolom jarak={26}>
        <div style={{ opacity: a }}>
          <Judul anak={T.judulKering} ukuran={54} />
        </div>
        <div style={{ display: "flex", gap: 90, alignItems: "flex-start" }}>
          <svg width={W} height={H} style={{ opacity: a }}>
            {[1, 2, 3].map((v) => (
              <g key={v}>
                <line x1={L} x2={W - 30} y1={y(v)} y2={y(v)} stroke={v === 1 ? warna.abu : warna.garis} strokeWidth={v === 1 ? 2 : 1} strokeDasharray={v === 1 ? "6 6" : undefined} />
                <text x={L - 12} y={y(v) + 8} fill={warna.samar} fontSize={22} textAnchor="end" fontFamily={tubuhFont}>
                  ×{v}
                </text>
              </g>
            ))}
            {pita.map((p, i) => (
              <text key={p} x={x(i)} y={H - 14} fill={warna.abu} fontSize={22} textAnchor="middle" fontFamily={tubuhFont}>
                {p}
              </text>
            ))}
            <path d={jalur} fill="none" stroke={warna.bara} strokeWidth={6} strokeLinejoin="round" />
            {r.slice(0, n).map((v, i) => (
              <g key={i}>
                <circle cx={x(i)} cy={y(v)} r={9} fill={warna.bara} />
                <text x={x(i)} y={y(v) - 20} fill={warna.kapur} fontSize={24} textAnchor="middle" fontFamily={angkaGaya.fontFamily as string}>
                  {koma(v, 1)}
                </text>
              </g>
            ))}
          </svg>
          <div style={{ width: 520, opacity: c, marginTop: 30 }}>
            <Angka anak={`${W2.gap > 0 ? "+" : "−"}${koma(Math.abs(W2.gap), 0)}`} ukuran={120} warnaA={warna.nyala} />
            <div style={{ fontFamily: tubuhFont, fontSize: 24, color: warna.abu, marginTop: 10, lineHeight: 1.4 }}>{T.dcPertama}</div>
            <div style={{ marginTop: 30 }}>
              <Garis anak={T.lebihAwal} tampil={c} lebar={500} />
            </div>
          </div>
        </div>
        <div style={{ fontFamily: tubuhFont, fontSize: 22, color: warna.abu, opacity: a }}>{T.sumbuKering}</div>
      </Kolom>
    </Lembut>
  );
};

const Batas: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const c = masuk(f, Math.round(panjang * 0.7), 24);
  const kunci = ["IDN|-4.5", "IDN|-2.0", "IDN|2.0", "MYS|2.0"];
  const baris = kunci.map((k) => {
    const [iso, lat] = k.split("|");
    const r = D.rain.find((x) => x.iso === iso && Math.abs(x.lat[0] - Number(lat)) < 1e-6)!;
    return { k, pct: r.pct, iso };
  });
  const N = D.national.same_drought_lt300;
  return (
    <Lembut panjang={panjang}>
      <Gambar berkas="peta_kemarau.jpg" panjang={panjang} zoom={1.04} />
      <Bkg sumber={T.sumberBatas} tampil={a} />
      <Kolom jarak={0}>
        <div style={{ width: 700, opacity: a }}>
          <Alis anak={T.alisBatas} />
          {baris.map((b, i) => (
            <Batang
              key={b.k}
              label={T.wilayah[b.k]}
              nilai={b.pct}
              maks={100}
              warnaB={b.pct < 30 ? warna.bara : b.iso === "MYS" ? warna.kapur : warna.abu}
              tampil={masuk(f, Math.round(panjang * 0.18) + i * 14, 24)}
              teks={`${koma(b.pct, 0)}%`}
              lebar={480}
            />
          ))}
          <div style={{ display: "flex", alignItems: "baseline", gap: 20, marginTop: 44, opacity: c }}>
            <Angka anak={kali(N.ratio, 0)} ukuran={110} warnaA={warna.bara} />
            <div style={{ fontFamily: tubuhFont, fontSize: 25, color: warna.kapur, lineHeight: 1.35, maxWidth: 440 }}>{T.samaCuaca}</div>
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Tutup: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 4, 22);
  const b = masuk(f, Math.round(panjang * 0.12), 24);
  const c = masuk(f, Math.round(panjang * 0.55), 24);
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Kolom jarak={28}>
        <h1 style={{ fontFamily: judulFont, fontWeight: 900, fontSize: 62, lineHeight: 1.05, color: warna.abu, margin: 0, opacity: a }}>{T.tutup1}</h1>
        <h2
          style={{
            fontFamily: judulFont,
            fontWeight: 900,
            fontSize: 110,
            lineHeight: 1,
            letterSpacing: "-0.03em",
            color: warna.bara,
            margin: 0,
            opacity: b,
            transform: `translateY(${(1 - b) * 18}px)`,
          }}
        >
          {T.tutup2}
        </h2>
        <div style={{ opacity: b, maxWidth: 1400, fontFamily: tubuhFont, fontSize: 40, color: warna.kapur, lineHeight: 1.3 }}>{T.tutupKet}</div>
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
            marginTop: 14,
          }}
        >
          {T.tutup3}
        </div>
      </Kolom>
    </Lembut>
  );
};

const KartuSumber: React.FC<{ panjang: number }> = () => {
  const f = useCurrentFrame();
  const a = masuk(f, 4, 20);
  return (
    <AbsoluteFill style={{ backgroundColor: warna.jelaga, opacity: a }}>
      <Kolom jarak={18}>
        <Alis anak={T.sumberData} />
        <div style={{ display: "flex", flexDirection: "column", gap: 11, width: 1680 }}>
          {T.barisSumber.map(([k, v]) => (
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
            maxWidth: 1680,
          }}
        >
          {T.peringatan}
        </div>
      </Kolom>
    </AbsoluteFill>
  );
};

/* --------------------------------- film ------------------------------ */

const ADEGAN: Record<string, React.FC<{ panjang: number }>> = {
  "01-kilas": Kilas,
  "02-banding": Banding,
  "03-pulau": Pulau,
  "04-sedikit": Sedikit,
  "05-gambut": Gambut,
  "06-bersih": Bersih,
  "07-kering": Kering,
  "08-batas": Batas,
  "09-tutup": Tutup,
};

export const PulauFilm: React.FC = () => {
  const J = JADWAL_PULAU.id!;
  return (
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
  );
};
