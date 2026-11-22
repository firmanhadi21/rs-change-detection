/**
 * "Sawit Kalimantan 2030: Tiga Skenario" / "Kalimantan's Oil Palm in 2030: Three Scenarios".
 *
 * InfografisSawit2030: one infographic page (1080x1350) per language -- the three scenario maps side by side,
 * a comparison table, the model test and what it means.
 * Sawit2030Film: the same story as a ~2.6 min film, Indonesian read by Bian, English by Max
 * (tts_konsesi.py --film sawit2030 [--bahasa en]); map layers public/sawit2030/film_*.
 *
 * Scenarios come from scripts/kalimantan_palm_expansion.py --stage dynamic (the version-1 model stepped
 * forward in 3-year periods from the end of 2021); the test from scripts/kalimantan_palm_ca.py. Every
 * figure is from sawit2030Data.json (scripts/sawit2030_assets.py). Same palette and type as Sawit.tsx.
 * No company is named.
 */

import React from "react";
import { AbsoluteFill, Audio, Img, Sequence, staticFile, useCurrentFrame } from "remotion";
import { JADWAL_SAWIT2030 } from "./jadwalSawit2030";
import type { Bahasa } from "./jadwalKonsesi";
import { Bingkai, Judul, Keterangan, Kolom, LatarDiam, Lembut, masuk } from "./komponen";
import { angkaGaya, judulFont, koma as komaL, ribuan as ribuanL, tubuhFont, warna } from "./teema";
import D from "./sawit2030Data.json";

type Sk = "slow" | "boom" | "legal";
const SKEN: Sk[] = ["slow", "boom", "legal"];
const S = D.scenarios as Record<Sk, (typeof D.scenarios)["slow"]>;
const W = D.warna;
const HIJAU = W.p2;
const WARNA_SK: Record<Sk, string> = { slow: HIJAU, boom: warna.nyala, legal: "#7FB2E6" };

const teksDasar = (b: Bahasa) => {
  const id = b === "id";
  const L = id ? "id-ID" : "en-GB";
  return {
    id,
    L,
    r: (n: number) => ribuanL(n, L),
    k: (n: number, d = 1) => komaL(n, d, L),
    kiri: id ? "Sawit · Kalimantan 2030" : "Oil palm · Kalimantan 2030",
    waktu: "November 2026",
    nama: (id
      ? { slow: "Lambat", boom: "Ledakan", legal: "Hanya APL/HPK" }
      : { slow: "Slow", boom: "Boom", legal: "APL/HPK only" }) as Record<Sk, string>,
    laju: (id
      ? { slow: "laju 2017–19", boom: "laju 2011–16", legal: "laju lambat, kawasan hutan tertutup" }
      : { slow: "2017–19 pace", boom: "2011–16 pace", legal: "slow pace, forest estate closed" }) as Record<Sk, string>,
    perTahun: id ? "km²/tahun" : "km²/yr",
  };
};

/* ============================== infographic ============================== */

export const InfografisSawit2030: React.FC<{ bahasa?: Bahasa }> = ({ bahasa = "id" }) => {
  const B = teksDasar(bahasa);
  const { id, r, k } = B;
  const kecil: React.CSSProperties = { fontFamily: tubuhFont, fontSize: 18, color: warna.abu, lineHeight: 1.35 };
  const T2 = D.test_2016_2019;
  const judulKotak = (s: string) => (
    <div style={{ fontFamily: tubuhFont, fontSize: 18, fontWeight: 600, letterSpacing: "0.16em", textTransform: "uppercase", color: warna.bara, marginBottom: 8 }}>{s}</div>
  );
  const baris: [string, (s: Sk) => string, (s: Sk) => boolean][] = [
    [id ? "Sawit baru 2022–2030" : "New palm 2022–2030", (s) => `${r(S[s].total_km2)} km²`, () => false],
    [id ? "di hutan yang masih utuh (2021)" : "in forest still intact (2021)", (s) => `${k(S[s].intact_pct)}%`, (s) => s !== "slow"],
    [id ? "   = hutan utuh terbuka" : "   = intact forest opened", (s) => `${r(S[s].intact_km2)} km²`, (s) => s !== "slow"],
    [id ? "di gambut" : "on peat", (s) => `${k(S[s].peat_pct)}%`, (s) => s === "boom"],
    [id ? "di APL" : "on APL land", (s) => `${k(S[s].apl_pct)}%`, () => false],
    [id ? "di Hutan Produksi (HP)" : "in Production Forest (HP)", (s) => `${k(S[s].hp_pct)}%`, (s) => s === "legal"],
    [id ? "di 10% lahan paling rawan api" : "in the 10% most fire-prone land", (s) => `${k(S[s].fire_top10_pct)}%`, () => false],
    [id ? "di luar konsesi terpetakan" : "outside mapped concessions", (s) => `${k(S[s].outside_conc_pct)}%`, () => false],
  ];
  const uji: [string, number][] = [
    [id ? "Model ini (dipakai di sini)" : "This model (used here)", T2.static],
    [id ? "Otomata seluler (CA)" : "Cellular automaton (CA)", T2.ca],
    [id ? "JST + CA-Markov" : "Neural net + CA-Markov", T2.ann_ca_markov],
    [id ? "Tebakan acak" : "Random guess", T2.random],
  ];
  const artinya = id
    ? [
        `Laju menentukan: ledakan berarti ${k(S.boom.total_km2 / S.slow.total_km2)}× lebih luas dan ≈${r(Math.round(S.boom.intact_km2 / 100) * 100)} km² hutan utuh terbuka.`,
        `Menutup kawasan hutan saja tidak cukup: hutan utuh yang terbuka naik dari ${r(S.slow.intact_km2)} ke ${r(S.legal.intact_km2)} km².`,
        `Sekitar sepertiga sawit baru berada di lahan paling rawan api.`,
      ]
    : [
        `Pace decides: a boom means ${k(S.boom.total_km2 / S.slow.total_km2)}× more palm and ≈${r(Math.round(S.boom.intact_km2 / 100) * 100)} km² of intact forest opened.`,
        `Closing the forest estate alone is not enough: intact forest opened rises from ${r(S.slow.intact_km2)} to ${r(S.legal.intact_km2)} km².`,
        `About a third of new palm lands on the most fire-prone land.`,
      ];
  return (
    <AbsoluteFill style={{ backgroundColor: warna.jelaga, padding: "40px 54px 30px", display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ borderTop: `3px solid ${warna.bara}`, paddingTop: 14, display: "flex", justifyContent: "space-between" }}>
        <span style={{ fontFamily: tubuhFont, fontSize: 19, fontWeight: 600, letterSpacing: "0.2em", textTransform: "uppercase", color: warna.bara }}>{B.kiri}</span>
        <span style={{ fontFamily: tubuhFont, fontSize: 18, letterSpacing: "0.18em", color: warna.abu, textTransform: "uppercase" }}>{B.waktu}</span>
      </div>
      <div>
        <h1 style={{ fontFamily: judulFont, fontWeight: 900, fontSize: 50, lineHeight: 1, letterSpacing: "-0.03em", color: warna.kapur, margin: 0, whiteSpace: "nowrap" }}>
          {id ? "Sawit Kalimantan 2030: tiga skenario" : "Kalimantan’s oil palm in 2030"}
        </h1>
        <div style={{ ...kecil, fontSize: 21, color: warna.kapur, marginTop: 8 }}>
          {id
            ? "Berapa luas kebun sawit baru sampai 2030, dan di mana, bila lajunya lambat, kembali meledak, atau dibatasi ke APL dan HPK"
            : "Three scenarios: how much new oil palm by 2030, and where, if the pace stays slow, returns to boom, or is limited to APL and HPK land"}
        </div>
      </div>
      <div style={{ display: "flex", flexShrink: 0 }}>
        {SKEN.map((s) => (
          <div key={s} style={{ width: 324, paddingLeft: 8 }}>
            <div style={{ fontFamily: tubuhFont, fontSize: 20, fontWeight: 600, letterSpacing: "0.12em", textTransform: "uppercase", color: WARNA_SK[s] }}>{B.nama[s]}</div>
            <div style={{ ...kecil, fontSize: 16 }}>
              <span style={{ ...angkaGaya, color: warna.kapur }}>{r(S[s].per_yr_km2)}</span> {B.perTahun} · {B.laju[s]}
            </div>
          </div>
        ))}
      </div>
      <div style={{ width: 972, height: 290, flexShrink: 0 }}>
        <Img src={staticFile("sawit2030/peta_ig.jpg")} style={{ width: 972, height: 290 }} />
      </div>
      <div style={{ display: "flex", gap: 22, fontFamily: tubuhFont, fontSize: 16, color: warna.kapur }}>
        {(
          [
            [W.palm, id ? "Sawit hingga 2021" : "Oil palm by 2021"],
            [HIJAU, id ? "Sawit baru 2022–2030 (model)" : "New oil palm 2022–2030 (model)"],
          ] as [string, string][]
        ).map(([w, l]) => (
          <span key={l} style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ width: 18, height: 12, background: w, display: "inline-block" }} />
            {l}
          </span>
        ))}
        <span style={{ color: warna.samar }}>{id ? "· warna makin pekat = makin rapat" : "· denser colour = more of the pixel"}</span>
      </div>
      <div style={{ borderTop: `2px solid ${warna.garis}`, paddingTop: 10, flexShrink: 0 }}>
        {baris.map(([label, nilai, sorot], i) => (
          <div key={label} style={{ display: "flex", alignItems: "center", height: i === 0 ? 48 : 36, borderBottom: `1px solid ${warna.garis}` }}>
            <span style={{ width: 330, whiteSpace: "pre", fontFamily: tubuhFont, fontSize: i === 0 ? 20 : 18, fontWeight: i === 0 ? 600 : 400, color: i === 0 ? warna.kapur : warna.abu }}>{label}</span>
            {SKEN.map((s) => (
              <span
                key={s}
                style={{
                  width: 214,
                  ...angkaGaya,
                  fontSize: i === 0 ? 30 : 22,
                  fontWeight: 600,
                  color: i === 0 ? WARNA_SK[s] : sorot(s) ? warna.nyala : warna.kapur,
                }}
              >
                {nilai(s)}
              </span>
            ))}
          </div>
        ))}
      </div>
      <div style={{ display: "flex", gap: 30, paddingTop: 4 }}>
        <div style={{ width: 470 }}>
          {judulKotak(id ? "Diuji pada 2016–2019" : "Tested on 2016–2019")}
          {uji.map(([n, v], i) => (
            <div key={n} style={{ display: "flex", alignItems: "center", gap: 8, height: 24 }}>
              <span style={{ width: 210, fontFamily: tubuhFont, fontSize: 15, color: i === 0 ? warna.kapur : warna.abu }}>{n}</span>
              <span style={{ width: Math.max(2, (190 * v) / T2.static), height: 12, background: i === 0 ? HIJAU : warna.abu }} />
              <span style={{ ...angkaGaya, fontSize: 14, color: warna.abu }}>{k(v, 3)}</span>
            </div>
          ))}
          <div style={{ ...kecil, fontSize: 13, marginTop: 4 }}>
            {id
              ? `Figure of merit: sel yang tepat ÷ semua sel yang diprediksi atau benar-benar berubah. Rantai Markov 2013–16 memperkirakan ${k(D.markov_ratio)}× terlalu banyak sawit baru 2016–19.`
              : `Figure of merit: cells placed right ÷ all cells predicted or actually changed. A 2013–16 Markov chain predicted ${k(D.markov_ratio)}× too much new palm for 2016–19.`}
          </div>
        </div>
        <div style={{ flex: 1 }}>
          {judulKotak(id ? "Artinya" : "What it means")}
          {artinya.map((l) => (
            <div key={l} style={{ ...kecil, fontSize: 16, color: warna.kapur, marginBottom: 4 }}>· {l}</div>
          ))}
        </div>
      </div>
      <div style={{ ...kecil, fontSize: 13, borderTop: `1px solid ${warna.garis}`, paddingTop: 8, marginTop: "auto" }}>
        {id
          ? "Model: gradient boosting di sel 500 m, dijalankan maju 3 tahun sekali dari akhir 2021; hutan dan api dianggap tetap seperti 2021. Peta sesudah 2025 menunjukkan arah, bukan petak. Sawit: Descals dkk. 2024 · Hutan: JRC TMF · Kawasan hutan: KLHK 2017 via GFW · Konsesi: GFW · Gambut: BBSDLP · Api: MODIS MCD64A1. Sawit tanam 2020–21 belum terdeteksi penuh. Peluang, bukan rencana atau pelaku."
          : "Model: gradient boosting on 500 m cells, stepped forward 3 years at a time from end-2021; forest and fire held at their 2021 state. Maps beyond 2025 show direction, not parcels. Palm: Descals et al. 2024 · Forest: JRC TMF · Forest zones: KLHK 2017 via GFW · Concessions: GFW · Peat: BBSDLP · Fire: MODIS MCD64A1. Palm planted 2020–21 is under-detected. Likelihood, not plans or actors."}
      </div>
    </AbsoluteFill>
  );
};

/* ================================ film ================================ */

const FILM_ID = {
  lokal: "id-ID",
  audio: "audio/sawit2030",
  musik: "musik-sawit2030.mp3",
  labelSumber: "Sumber",
  alisJudul: "Tiga skenario",
  judul: ["SAWIT", "KALIMANTAN", "2030"],
  subJudul: "Berapa luas kebun sawit baru sampai 2030, dan di mana: bila lajunya lambat, kembali meledak, atau dibatasi ke APL dan HPK.",
  alisBuka: "Model yang sama, dijalankan maju",
  judulBuka: "Tiga tahun sekali, sampai 2030",
  barisBuka: "Setiap langkah: sawit baru ditempatkan di lahan paling berisiko, lalu jarak ke kebun dihitung ulang dari peta baru",
  periode: ["2022–2024", "2025–2027", "2028–2030"],
  sumberBuka: "Model gradient boosting, peluang sel menjadi ≥ 50% sawit dalam 3 tahun · peta sawit Descals dkk. 2024",
  judulSk: "Berapa luas? Tergantung lajunya",
  satuanSk: "km² sawit baru 2022–2030",
  sumberSk: "Laju lambat = rata-rata sawit baru 2017–2019; ledakan = 2011–2016 · sel MODIS 500 m yang melewati 50% sawit",
  utuh: "di hutan yang masih utuh (2021)",
  gambut: "di gambut",
  apl: "di APL",
  hp: "di Hutan Produksi",
  api: "di 10% lahan paling rawan api, El Niño 2027",
  naikDari: (a: string, b: string) => `naik dari ${a}% (${b} km²) di skenario lambat`,
  sumberPeta: "Skenario dari akhir 2021 · kawasan hutan KLHK 2017 via GFW · hutan utuh: JRC TMF ≥ 90% tak terganggu · gambut BBSDLP",
  judulUji: "Diuji pada data lama",
  ujiLabel: "Figure of merit: sel yang tepat ÷ semua sel yang diprediksi atau benar-benar berubah",
  modelSekali: "Model ini, sekali jalan",
  modelBertahap: "Model ini, bertahap",
  ca: "Otomata seluler (CA)",
  annca: "JST + CA-Markov",
  catatanCA: "* parameter CA disetel pada periode yang sama",
  markov: (x: string) => `Rantai Markov 2013–16 memperkirakan ${x}× terlalu banyak sawit baru 2016–19`,
  sumberUji: "Jumlah sawit baru diberikan sesuai kenyataan; yang diuji adalah letaknya",
  tutup1: "Sawit Kalimantan 2030",
  tutup2: "Peta sampai 2030 menunjukkan arah, bukan petak. Hutan dan api dianggap tetap seperti 2021.",
  tutup3: "Laju pembukaan menentukan apakah hutan utuh dan gambut ikut terbuka. Batas status kawasan saja tidak menjaganya.",
  tutupCatat:
    "Peta ini menunjukkan peluang, bukan rencana atau pelaku. Sawit yang ditanam 2020–2021 belum terdeteksi penuh; peta kawasan hutan dari 2017. Belum ditelaah sejawat.",
  sumberData: "Sumber data",
  barisSumber: [
    ["Sawit", "Descals dkk. 2024, peta sawit industri & rakyat dengan tahun tanam 2000–2021"],
    ["Hutan", "JRC Tropical Moist Forest 1990–2024"],
    ["Kawasan", "KLHK kawasan hutan 2017 (via Global Forest Watch); konsesi sawit & HTI GFW"],
    ["Gambut", "BBSDLP (via GFW)"],
    ["Api", "MODIS MCD64A1 v6.1 (NASA), 500 m; hujan CHIRPS"],
    ["Model", "Gradient boosting, dibandingkan dengan otomata seluler dan JST + CA-Markov (figure of merit)"],
  ],
  peringatan: "Hasil model statistik, bukan bukti pelanggaran. Tidak ada perusahaan yang disebut.",
};

type FilmTeks = typeof FILM_ID;

const FILM_EN: FilmTeks = {
  ...FILM_ID,
  lokal: "en-GB",
  audio: "audio/sawit2030-en",
  musik: "musik-sawit2030-en.mp3",
  labelSumber: "Source",
  alisJudul: "Three scenarios",
  judul: ["KALIMANTAN’S", "OIL PALM", "IN 2030"],
  subJudul: "How much new oil palm by 2030, and where: if the pace stays slow, returns to boom, or is limited to APL and HPK land.",
  alisBuka: "The same model, run forward",
  judulBuka: "Three years at a time, to 2030",
  barisBuka: "At each step, new palm goes onto the land most at risk, then distance to plantations is recomputed from the new map",
  sumberBuka: "Gradient boosting: chance a cell becomes ≥ 50% oil palm within 3 years · oil palm map Descals et al. 2024",
  judulSk: "How much? It depends on the pace",
  satuanSk: "km² of new oil palm 2022–2030",
  sumberSk: "Slow = mean new palm 2017–2019; boom = 2011–2016 · MODIS 500 m cells passing 50% oil palm",
  utuh: "in forest still intact (2021)",
  gambut: "on peat",
  apl: "on APL land",
  hp: "in Production Forest",
  api: "in the 10% most fire-prone land, El Niño 2027",
  naikDari: (a: string, b: string) => `up from ${a}% (${b} km²) in the slow scenario`,
  sumberPeta: "Scenarios from end-2021 · forest zones KLHK 2017 via GFW · intact forest: JRC TMF ≥ 90% undisturbed · peat BBSDLP",
  judulUji: "Tested on past data",
  ujiLabel: "Figure of merit: cells placed right ÷ all cells predicted or actually changed",
  modelSekali: "This model, one step",
  modelBertahap: "This model, stepped",
  ca: "Cellular automaton (CA)",
  annca: "Neural net + CA-Markov",
  catatanCA: "* CA settings were tuned on the same period",
  markov: (x: string) => `A 2013–16 Markov chain predicted ${x}× too much new palm for 2016–19`,
  sumberUji: "Each model is given the true amount of new palm; what is tested is where it goes",
  tutup1: "Kalimantan’s oil palm in 2030",
  tutup2: "The maps to 2030 show direction, not parcels. Forest and fire are held at their 2021 state.",
  tutup3: "The pace of clearing decides whether intact forest and peat are opened. Zoning limits alone do not protect them.",
  tutupCatat:
    "These maps show likelihood, not plans or who is responsible. Palm planted in 2020–2021 is under-detected; the forest-zone map is from 2017. Not yet peer reviewed.",
  sumberData: "Data sources",
  barisSumber: [
    ["Oil palm", "Descals et al. 2024, industrial & smallholder oil palm with planting years 2000–2021"],
    ["Forest", "JRC Tropical Moist Forest 1990–2024"],
    ["Zoning", "KLHK forest areas 2017 (via Global Forest Watch); GFW oil palm & pulpwood concessions"],
    ["Peat", "BBSDLP (via GFW)"],
    ["Fire", "MODIS MCD64A1 v6.1 (NASA), 500 m; CHIRPS rainfall"],
    ["Model", "Gradient boosting, compared with cellular automata and neural net + CA-Markov (figure of merit)"],
  ],
  peringatan: "Statistical model results, not evidence of wrongdoing. No company is named.",
};

const FCtx = React.createContext<Bahasa>("id");
const useF = () => {
  const b = React.useContext(FCtx);
  const T = b === "en" ? FILM_EN : FILM_ID;
  return { T, B: teksDasar(b), koma: (n: number, d = 1) => komaL(n, d, T.lokal), ribuan: (n: number) => ribuanL(n, T.lokal) };
};

const FBkg: React.FC<{ sumber?: string; tampil?: number }> = ({ sumber, tampil }) => {
  const { T, B } = useF();
  return <Bingkai kiri={B.kiri} waktu={B.waktu} labelSumber={T.labelSumber} sumber={sumber} tampil={tampil} />;
};

const FAlis: React.FC<{ anak: string; w?: string }> = ({ anak, w = warna.bara }) => (
  <div style={{ fontFamily: tubuhFont, fontSize: 21, fontWeight: 600, letterSpacing: "0.22em", textTransform: "uppercase", color: w }}>{anak}</div>
);

/** Base map, palm by 2021, and one scenario's three periods; each value is that layer's opacity. */
const Peta: React.FC<{ sawit?: number; sk?: Sk; p?: [number, number, number]; redup?: number }> = ({ sawit = 0, sk = "slow", p = [0, 0, 0], redup = 0 }) => (
  <AbsoluteFill style={{ backgroundColor: warna.jelaga }}>
    <AbsoluteFill style={{ opacity: 1 - redup }}>
      <Img src={staticFile("sawit2030/film_dasar.jpg")} style={{ width: "100%", height: "100%" }} />
      {sawit > 0 && <Img src={staticFile("sawit2030/film_sawit.png")} style={{ position: "absolute", inset: 0, width: "100%", height: "100%", opacity: sawit }} />}
      {p.map((o, i) =>
        o > 0 ? <Img key={i} src={staticFile(`sawit2030/film_${sk}_${i + 1}.png`)} style={{ position: "absolute", inset: 0, width: "100%", height: "100%", opacity: o }} /> : null,
      )}
    </AbsoluteFill>
    <AbsoluteFill style={{ background: `linear-gradient(90deg, ${warna.jelaga} 0%, ${warna.jelaga} 30%, rgba(10,12,15,0) 44%)` }} />
  </AbsoluteFill>
);

const Legenda: React.FC<{ tampil?: number[] }> = ({ tampil = [1, 1, 1, 1] }) => {
  const { T, B } = useF();
  const item: [string, string][] = [
    [W.palm, B.id ? "Sawit hingga 2021" : "Oil palm by 2021"],
    [W.p1, `${B.id ? "Baru" : "New"} ${T.periode[0]}`],
    [W.p2, `${B.id ? "Baru" : "New"} ${T.periode[1]}`],
    [W.p3, `${B.id ? "Baru" : "New"} ${T.periode[2]}`],
  ];
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {item.map(([w, l], i) => (
        <div key={l} style={{ display: "flex", alignItems: "center", gap: 12, fontFamily: tubuhFont, fontSize: 22, color: warna.kapur, opacity: tampil[i] }}>
          <span style={{ width: 26, height: 16, background: w, display: "inline-block" }} />
          {l}
        </div>
      ))}
    </div>
  );
};

const FJudulKartu: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { T } = useF();
  const f = useCurrentFrame();
  const a = masuk(f, 4, 24);
  return (
    <Lembut panjang={panjang}>
      <Peta sawit={1} sk="boom" p={[1, 1, 1]} redup={0.45} />
      <Kolom jarak={26}>
        <div style={{ opacity: a, transform: `translateY(${(1 - a) * 20}px)` }}>
          <div style={{ marginBottom: 24 }}>
            <FAlis anak={T.alisJudul} />
          </div>
          <h1 style={{ fontFamily: judulFont, fontWeight: 900, fontSize: 96, lineHeight: 0.94, letterSpacing: "-0.04em", color: warna.kapur, margin: 0 }}>
            {T.judul.map((l, i) => (
              <React.Fragment key={l}>
                {i > 0 && <br />}
                {l}
              </React.Fragment>
            ))}
          </h1>
          <div style={{ marginTop: 28 }}>
            <Keterangan lebar={700} anak={T.subJudul} />
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const FBuka: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { T } = useF();
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const s = masuk(f, 10, 30);
  const p = [0.42, 0.58, 0.74].map((m) => masuk(f, Math.round(panjang * m), 24)) as [number, number, number];
  return (
    <Lembut panjang={panjang}>
      <Peta sawit={s} sk="slow" p={p} />
      <FBkg sumber={T.sumberBuka} tampil={a} />
      <Kolom jarak={26}>
        <div style={{ width: 680, opacity: a }}>
          <FAlis anak={T.alisBuka} />
          <div style={{ marginTop: 16 }}>
            <Judul anak={T.judulBuka} ukuran={56} />
          </div>
        </div>
        <div style={{ width: 680, opacity: p[0], borderLeft: `3px solid ${HIJAU}`, paddingLeft: 18, fontFamily: tubuhFont, fontSize: 26, color: warna.kapur, lineHeight: 1.35 }}>
          {T.barisBuka}
        </div>
        <Legenda tampil={[s, ...p]} />
      </Kolom>
    </Lembut>
  );
};

const FSkenario: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { T, B, ribuan } = useF();
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const mulai: Record<Sk, number> = { slow: 0.18, boom: 0.6, legal: 0.86 };
  const maks = Math.max(...SKEN.map((s) => S[s].total_km2));
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <FBkg sumber={T.sumberSk} tampil={a} />
      <Kolom jarak={34}>
        <div style={{ opacity: a }}>
          <Judul anak={T.judulSk} ukuran={62} />
          <div style={{ fontFamily: tubuhFont, fontSize: 24, color: warna.abu, marginTop: 10 }}>{T.satuanSk}</div>
        </div>
        {SKEN.map((s) => {
          const t = masuk(f, Math.round(panjang * mulai[s]), 30);
          return (
            <div key={s} style={{ display: "flex", alignItems: "center", gap: 28, opacity: Math.max(0.12, Math.min(1, t * 2)) }}>
              <div style={{ width: 380 }}>
                <div style={{ fontFamily: tubuhFont, fontSize: 32, fontWeight: 600, color: WARNA_SK[s] }}>{B.nama[s]}</div>
                <div style={{ fontFamily: tubuhFont, fontSize: 21, color: warna.abu }}>
                  {ribuan(S[s].per_yr_km2)} {B.perTahun} · {B.laju[s]}
                </div>
              </div>
              <span style={{ width: Math.max(4, (980 * S[s].total_km2 * t) / maks), height: 44, background: WARNA_SK[s] }} />
              <span style={{ ...angkaGaya, fontSize: 48, fontWeight: 600, color: warna.kapur }}>{ribuan(S[s].total_km2 * t)}</span>
            </div>
          );
        })}
      </Kolom>
    </Lembut>
  );
};

/** One scenario on the map, a headline number and three timed lines. */
const Skenario: React.FC<{ panjang: number; sk: Sk; besar: string; kecilBesar: string; baris: [string, string, boolean][]; mulai: number[] }> = ({
  panjang,
  sk,
  besar,
  kecilBesar,
  baris,
  mulai,
}) => {
  const { T, B, ribuan } = useF();
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const p = [0.04, 0.1, 0.16].map((m) => masuk(f, Math.round(panjang * m), 24)) as [number, number, number];
  return (
    <Lembut panjang={panjang}>
      <Peta sawit={1} sk={sk} p={p} />
      <FBkg sumber={T.sumberPeta} tampil={a} />
      <Kolom jarak={24}>
        <div style={{ opacity: a }}>
          <FAlis anak={`${B.nama[sk]} · ${ribuan(S[sk].per_yr_km2)} ${B.perTahun}`} w={WARNA_SK[sk]} />
        </div>
        <div style={{ opacity: a }}>
          <div style={{ ...angkaGaya, fontSize: 104, fontWeight: 600, color: WARNA_SK[sk], lineHeight: 1 }}>{besar}</div>
          <div style={{ fontFamily: tubuhFont, fontSize: 26, color: warna.kapur }}>{kecilBesar}</div>
        </div>
        {baris.map(([n, l, sorot], i) => {
          const t = masuk(f, Math.round(panjang * mulai[i]), 22);
          return (
            <div key={l} style={{ width: 660, opacity: t, transform: `translateY(${(1 - t) * 12}px)`, display: "flex", alignItems: "baseline", gap: 16 }}>
              <span style={{ ...angkaGaya, fontSize: 52, fontWeight: 600, color: sorot ? warna.nyala : warna.kapur, minWidth: 190 }}>{n}</span>
              <span style={{ fontFamily: tubuhFont, fontSize: 25, color: warna.kapur, lineHeight: 1.3 }}>{l}</span>
            </div>
          );
        })}
        <div style={{ marginTop: 6 }}>
          <Legenda />
        </div>
      </Kolom>
    </Lembut>
  );
};

const FLambat: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { T, koma, ribuan } = useF();
  const x = S.slow;
  return (
    <Skenario
      panjang={panjang}
      sk="slow"
      besar={`${ribuan(x.total_km2)} km²`}
      kecilBesar={T.satuanSk}
      baris={[
        [`${koma(x.apl_pct, 0)}%`, `${T.apl} · ${koma(x.hp_pct, 0)}% ${T.hp}`, false],
        [`${koma(x.intact_pct)}%`, T.utuh, false],
        [`${koma(x.peat_pct)}%`, T.gambut, false],
      ]}
      mulai={[0.3, 0.62, 0.8]}
    />
  );
};

const FLedakan: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { T, koma, ribuan } = useF();
  const x = S.boom;
  return (
    <Skenario
      panjang={panjang}
      sk="boom"
      besar={`${ribuan(x.total_km2)} km²`}
      kecilBesar={T.satuanSk}
      baris={[
        [`${koma(x.intact_pct)}%`, `${T.utuh} · ≈${ribuan(Math.round(x.intact_km2 / 10) * 10)} km²`, true],
        [`${koma(x.peat_pct)}%`, T.gambut, true],
        [`${koma(x.fire_top10_pct, 0)}%`, T.api, false],
      ]}
      mulai={[0.3, 0.55, 0.76]}
    />
  );
};

const FLegal: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { T, koma, ribuan } = useF();
  const x = S.legal;
  return (
    <Skenario
      panjang={panjang}
      sk="legal"
      besar={`${koma(x.hp_pct, 0)}%`}
      kecilBesar={T.hp}
      baris={[
        [`${koma(x.apl_pct, 0)}%`, T.apl, false],
        [`${koma(x.intact_pct)}%`, `${T.utuh} · ${T.naikDari(koma(S.slow.intact_pct), ribuan(S.slow.intact_km2))}`, true],
      ]}
      mulai={[0.3, 0.5]}
    />
  );
};

const FUji: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { T, koma } = useF();
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const c = masuk(f, Math.round(panjang * 0.66), 24);
  const A = D.test_2010_2016;
  const Bt = D.test_2016_2019;
  const grup: [string, number, [string, number, boolean][]][] = [
    ["2010 → 2016", 0.16, [[T.modelSekali, A.one_shot, true], [T.modelBertahap, A.stepped, true], [`${T.ca} *`, A.ca, false]]],
    ["2016 → 2019", 0.34, [[T.modelSekali, Bt.static, true], [T.ca, Bt.ca, false], [T.annca, Bt.ann_ca_markov, false]]],
  ];
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <FBkg sumber={T.sumberUji} tampil={a} />
      <Kolom jarak={22}>
        <div style={{ opacity: a }}>
          <Judul anak={T.judulUji} ukuran={58} />
          <div style={{ fontFamily: tubuhFont, fontSize: 22, color: warna.abu, marginTop: 10 }}>{T.ujiLabel}</div>
        </div>
        {grup.map(([g, m, rows]) => {
          const t = masuk(f, Math.round(panjang * m), 30);
          return (
            <div key={g} style={{ display: "flex", gap: 30, alignItems: "center", opacity: Math.max(0.15, Math.min(1, t * 2)) }}>
              <div style={{ width: 230, fontFamily: tubuhFont, fontSize: 30, fontWeight: 600, color: warna.kapur }}>{g}</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {rows.map(([n, v, kita]) => (
                  <div key={n} style={{ display: "flex", alignItems: "center", gap: 16 }}>
                    <span style={{ width: 380, fontFamily: tubuhFont, fontSize: 24, color: kita ? warna.kapur : warna.abu }}>{n}</span>
                    <span style={{ width: Math.max(4, 1500 * v * t), height: 26, background: kita ? HIJAU : warna.abu }} />
                    <span style={{ ...angkaGaya, fontSize: 28, fontWeight: 600, color: kita ? HIJAU : warna.kapur }}>{koma(v, 3)}</span>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
        <div style={{ fontFamily: tubuhFont, fontSize: 20, color: warna.samar }}>{T.catatanCA}</div>
        <div style={{ opacity: c, borderLeft: `3px solid ${warna.bara}`, paddingLeft: 18, fontFamily: tubuhFont, fontSize: 30, color: warna.kapur, maxWidth: 1500 }}>
          {T.markov(koma(D.markov_ratio))}
        </div>
      </Kolom>
    </Lembut>
  );
};

const FTutup: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { T } = useF();
  const f = useCurrentFrame();
  const a = masuk(f, 4, 22);
  const b = masuk(f, Math.round(panjang * 0.15), 24);
  const c = masuk(f, Math.round(panjang * 0.45), 24);
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Kolom jarak={28}>
        <h1 style={{ fontFamily: judulFont, fontWeight: 900, fontSize: 60, lineHeight: 1.05, color: warna.abu, margin: 0, opacity: a }}>{T.tutup1}</h1>
        <div style={{ opacity: b, maxWidth: 1500, fontFamily: tubuhFont, fontSize: 40, color: warna.kapur, lineHeight: 1.3 }}>{T.tutup2}</div>
        <h2 style={{ fontFamily: judulFont, fontWeight: 900, fontSize: 58, lineHeight: 1.08, letterSpacing: "-0.02em", color: warna.bara, margin: 0, opacity: c, maxWidth: 1600 }}>{T.tutup3}</h2>
        <div style={{ opacity: b, borderLeft: `3px solid ${warna.garis}`, paddingLeft: 20, fontFamily: tubuhFont, fontSize: 24, color: warna.abu, lineHeight: 1.45, maxWidth: 1500, marginTop: 14 }}>
          {T.tutupCatat}
        </div>
      </Kolom>
    </Lembut>
  );
};

const FSumber: React.FC<{ panjang: number }> = () => {
  const { T } = useF();
  const f = useCurrentFrame();
  const a = masuk(f, 4, 20);
  return (
    <AbsoluteFill style={{ backgroundColor: warna.jelaga, opacity: a }}>
      <Kolom jarak={16}>
        <FAlis anak={T.sumberData} />
        <div style={{ display: "flex", flexDirection: "column", gap: 10, width: 1680 }}>
          {T.barisSumber.map(([k, v]) => (
            <div key={k} style={{ display: "flex", gap: 28, alignItems: "baseline" }}>
              <div style={{ width: 200, fontFamily: tubuhFont, fontSize: 25, fontWeight: 600, color: warna.kapur }}>{k}</div>
              <div style={{ fontFamily: tubuhFont, fontSize: 25, color: warna.abu }}>{v}</div>
            </div>
          ))}
        </div>
        <div style={{ marginTop: 12, paddingTop: 16, borderTop: `2px solid ${warna.bara}`, fontFamily: tubuhFont, fontSize: 23, color: warna.kapur, lineHeight: 1.5, maxWidth: 1680 }}>
          {T.peringatan}
        </div>
      </Kolom>
    </AbsoluteFill>
  );
};

const FADEGAN: Record<string, React.FC<{ panjang: number }>> = {
  "01-buka": FBuka,
  "02-skenario": FSkenario,
  "03-lambat": FLambat,
  "04-ledakan": FLedakan,
  "05-legal": FLegal,
  "06-uji": FUji,
  "07-tutup": FTutup,
};

export const Sawit2030Film: React.FC<{ bahasa?: Bahasa }> = ({ bahasa = "id" }) => {
  const J = JADWAL_SAWIT2030[bahasa]!;
  const T = bahasa === "en" ? FILM_EN : FILM_ID;
  return (
    <FCtx.Provider value={bahasa}>
      <AbsoluteFill style={{ backgroundColor: warna.jelaga }}>
        <Audio src={staticFile(`${T.audio}/${T.musik}`)} />
        <Sequence durationInFrames={J.JUDUL_FRAME}>
          <FJudulKartu panjang={J.JUDUL_FRAME} />
        </Sequence>
        {J.adegan.map((a) => {
          const K = FADEGAN[a.id];
          return (
            <Sequence key={a.id} from={a.mulai} durationInFrames={a.panjang}>
              <K panjang={a.panjang} />
              <Audio src={staticFile(`${T.audio}/${a.id}.mp3`)} />
            </Sequence>
          );
        })}
        <Sequence from={J.akhirNarasi} durationInFrames={J.TUTUP_FRAME}>
          <FSumber panjang={J.TUTUP_FRAME} />
        </Sequence>
      </AbsoluteFill>
    </FCtx.Provider>
  );
};
