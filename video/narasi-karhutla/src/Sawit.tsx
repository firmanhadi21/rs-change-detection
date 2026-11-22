/**
 * "Di mana akan ada kebun sawit baru?" / "Where will oil palm go next?" One infographic page (1080x1350)
 * per language: the top 10% oil-palm conversion risk (2022-2024, from end-2021) over the top 10% El Nino
 * 2027 fire risk, the factor ranking and the hindcast check.
 *
 * Every figure is from sawitData.json (scripts/sawit_infografis_assets.py, which reads the outputs of
 * scripts/kalimantan_palm_expansion.py). Same palette and type as Api.tsx. No company is named.
 *
 * SawitFilm (bottom of the file): the same story as a ~2.6 min film, Indonesian read by Bian, English
 * by Max (tts_konsesi.py --film sawit [--bahasa en]); map layers public/sawit/film_*.
 */

import React from "react";
import { AbsoluteFill, Audio, Img, Sequence, staticFile, useCurrentFrame } from "remotion";
import { JADWAL_SAWIT } from "./jadwalSawit";
import type { Bahasa } from "./jadwalKonsesi";
import { Bingkai, Judul, Keterangan, Kolom, LatarDiam, Lembut, masuk } from "./komponen";
import { angkaGaya, judulFont, koma as komaL, ribuan as ribuanL, tubuhFont, warna } from "./teema";
import D from "./sawitData.json";

const FAKTOR: Record<string, [string, string]> = {
  "closeness to existing palm": ["Kedekatan ke kebun sawit", "Closeness to existing palm"],
  "forest condition": ["Kondisi hutan", "Forest condition"],
  "access & terrain": ["Akses jalan/sungai & medan", "Access (roads, rivers) & terrain"],
  "climate (mean Jun-Oct rain)": ["Iklim (rata-rata hujan)", "Climate (mean rainfall)"],
  concessions: ["Konsesi", "Concessions"],
  "recent clearing": ["Pembukaan hutan baru", "Recent clearing"],
  "forest-area status (APL etc.)": ["Status kawasan (APL dll.)", "Forest-zone status (APL etc.)"],
  settlement: ["Permukiman", "Settlement"],
  peat: ["Gambut", "Peat"],
  fire: ["Riwayat kebakaran", "Fire history"],
};
const SOROT = new Set(["forest-area status (APL etc.)", "fire"]);

const teks = (b: Bahasa) => {
  const id = b === "id";
  const L = id ? "id-ID" : "en-GB";
  const r = (n: number) => ribuanL(n, L);
  const k = (n: number, d = 0) => komaL(n, d, L);
  const H = D.hindcast as Record<string, { model: number; distance: number; km2: number }>;
  const O = D.observed_km2 as Record<string, number>;
  return {
    lokal: L,
    r,
    k,
    kiri: id ? "Sawit & karhutla · Kalimantan" : "Palm & fire · Kalimantan",
    waktu: id ? "November 2026" : "November 2026",
    judul: id ? "Di mana akan ada kebun sawit baru?" : "Where will oil palm go next?",
    sub: id
      ? "Peluang lahan menjadi kebun sawit dalam tiga tahun (2022–2024), ditumpangkan pada risiko kebakaran saat El Niño 2027"
      : "The chance that land becomes oil palm within three years (2022–2024), laid over fire risk in an El Niño 2027",
    legenda: [
      ["palm", id ? "Sawit hingga 2021" : "Oil palm by 2021"],
      ["risk", id ? "10% teratas risiko jadi sawit" : "Top 10% palm-conversion risk"],
      ["fire", id ? "10% teratas risiko api 2027 (El Niño)" : "Top 10% fire risk, El Niño 2027"],
      ["both", id ? `Keduanya · ${r(D.overlap.both_km2)} km²` : `Both · ${r(D.overlap.both_km2)} km²`],
    ] as [keyof typeof D.warna, string][],
    angka: [
      [`≈${r(Math.round(D.expected_km2 / 10) * 10)} km²`,
        id ? `sawit baru diperkirakan 2022–24 (2017–19: ${r(O["2017-2019"])}; 2011–13: ${r(O["2011-2013"])})`
          : `new palm expected 2022–24 (2017–19: ${r(O["2017-2019"])}; 2011–13: ${r(O["2011-2013"])})`],
      [`${D.near5_pct}%`, id ? "lahan berisiko tertinggi berada ≤5 km dari kebun yang sudah ada"
        : "of the highest-risk land lies within 5 km of existing palm"],
      [`${D.outside_conc_pct}%`, id ? "sawit baru diperkirakan di luar konsesi yang terpetakan"
        : "of expected new palm falls outside mapped concessions"],
    ],
    judulFaktor: id ? "Apa yang menentukan lokasi sawit baru" : "What predicts new palm",
    catatanFaktor: id
      ? `Penurunan PR-AUC bila faktor diacak · validasi silang blok 50 km · PR-AUC ${k(D.pr_auc, 2)} (acak: ${k(D.base_rate_pct / 100, 3)})`
      : `Loss in PR-AUC when the factor is shuffled · 50 km block cross-validation · PR-AUC ${k(D.pr_auc, 2)} (chance: ${k(D.base_rate_pct / 100, 3)})`,
    diuji: id ? "Diuji" : "Tested",
    diujiTeks: id
      ? `Dilatih dengan data hingga 2010, 10% lahan teratas menangkap ${k(H["2014-2016"].model)}% sawit baru 2014–16 dan ${k(H["2017-2019"].model)}% 2017–19. Jarak ke kebun saja: ${k(H["2014-2016"].distance)}% dan ${k(H["2017-2019"].distance)}%.`
      : `Trained on data up to 2010, the top 10% of land caught ${k(H["2014-2016"].model)}% of new palm in 2014–16 and ${k(H["2017-2019"].model)}% in 2017–19. Distance to palm alone: ${k(H["2014-2016"].distance)}% and ${k(H["2017-2019"].distance)}%.`,
    tumpang: id ? "Tumpang tindih dengan api" : "Overlap with fire",
    tumpangTeks: id
      ? `${k(D.overlap.pct_of_palm_top10)}% lahan berisiko sawit juga berisiko api tinggi (${k(D.overlap.apl_pct)}% APL, ${k(D.overlap.hp_pct)}% HP, ${k(D.overlap.peat_pct)}% gambut).`
      : `${k(D.overlap.pct_of_palm_top10)}% of high palm-risk land is also high fire-risk land (${k(D.overlap.apl_pct)}% APL, ${k(D.overlap.hp_pct)}% Production Forest, ${k(D.overlap.peat_pct)}% peat).`,
    artinya: id ? "Artinya" : "What it means",
    artinyaTeks: id
      ? [`Sawit baru melebar dari tepi kebun yang ada; api tidak memberi tanda lokasinya.`,
        `≈${r(Math.round(D.hp_km2 / 10) * 10)} km² (${D.hp_pct}%) diperkirakan di Hutan Produksi: perlu dicek izin pelepasannya.`]
      : [`New palm spreads out from existing plantation edges; fire does not flag where it goes.`,
        `≈${r(Math.round(D.hp_km2 / 10) * 10)} km² (${D.hp_pct}%) is expected in Production Forest: its release permits need checking.`],
    sumber: id
      ? "Sawit: Descals dkk. 2024 · Hutan: JRC TMF · Konsesi & kawasan hutan: GFW (KLHK 2017) · Gambut: BBSDLP · Api: MODIS MCD64A1, CHIRPS · Model: gradient boosting, sel 500 m. Catatan: sawit yang ditanam 2020–21 belum terdeteksi penuh; peta kawasan 2017; peta ini menunjukkan peluang, bukan rencana atau pelaku."
      : "Palm: Descals et al. 2024 · Forest: JRC TMF · Concessions & forest zones: GFW (KLHK 2017) · Peat: BBSDLP · Fire: MODIS MCD64A1, CHIRPS · Model: gradient boosting, 500 m cells. Note: palm planted in 2020–21 is under-detected; zoning map from 2017; the map shows likelihood, not plans or actors.",
  };
};

const Judul2: React.FC<{ anak: string }> = ({ anak }) => (
  <div style={{ fontFamily: tubuhFont, fontSize: 18, fontWeight: 600, letterSpacing: "0.16em", textTransform: "uppercase", color: warna.bara, marginBottom: 8 }}>{anak}</div>
);

export const InfografisSawit: React.FC<{ bahasa?: Bahasa }> = ({ bahasa = "id" }) => {
  const T = teks(bahasa);
  const kecil: React.CSSProperties = { fontFamily: tubuhFont, fontSize: 18, color: warna.abu, lineHeight: 1.35 };
  const maks = D.factors[0].v;
  return (
    <AbsoluteFill style={{ backgroundColor: warna.jelaga, padding: "40px 54px 30px", display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ borderTop: `3px solid ${warna.bara}`, paddingTop: 14, display: "flex", justifyContent: "space-between" }}>
        <span style={{ fontFamily: tubuhFont, fontSize: 19, fontWeight: 600, letterSpacing: "0.2em", textTransform: "uppercase", color: warna.bara }}>{T.kiri}</span>
        <span style={{ fontFamily: tubuhFont, fontSize: 18, letterSpacing: "0.18em", color: warna.abu, textTransform: "uppercase" }}>{T.waktu}</span>
      </div>
      <div>
        <h1 style={{ fontFamily: judulFont, fontWeight: 900, fontSize: 52, lineHeight: 1, letterSpacing: "-0.03em", color: warna.kapur, margin: 0, whiteSpace: "nowrap" }}>{T.judul}</h1>
        <div style={{ ...kecil, fontSize: 21, color: warna.kapur, marginTop: 8, maxWidth: 940 }}>{T.sub}</div>
      </div>
      <div style={{ position: "relative", width: 972, height: 598, overflow: "hidden", flexShrink: 0 }}>
        <Img src={staticFile("sawit/peta_sawit_ig.jpg")} style={{ position: "absolute", left: 150, top: -34, width: 782 }} />
        <div style={{ position: "absolute", left: 0, top: 4, display: "flex", flexDirection: "column", gap: 7, background: "rgba(10,12,15,0.82)", padding: "10px 14px" }}>
          {T.legenda.map(([w, l]) => (
            <div key={w} style={{ display: "flex", alignItems: "center", gap: 10, fontFamily: tubuhFont, fontSize: 17, color: warna.kapur }}>
              <span style={{ width: 20, height: 14, background: D.warna[w], display: "inline-block" }} />
              {l}
            </div>
          ))}
        </div>
      </div>
      <div style={{ display: "flex", gap: 28, borderTop: `2px solid ${warna.garis}`, paddingTop: 14 }}>
        {T.angka.map(([a, l], i) => (
          <div key={i} style={{ flex: 1 }}>
            <div style={{ ...angkaGaya, fontSize: 48, fontWeight: 600, color: warna.nyala, lineHeight: 1 }}>{a}</div>
            <div style={{ ...kecil, fontSize: 17, marginTop: 4 }}>{l}</div>
          </div>
        ))}
      </div>
      <div style={{ display: "flex", gap: 30, borderTop: `2px solid ${warna.garis}`, paddingTop: 14 }}>
        <div style={{ width: 520 }}>
          <Judul2 anak={T.judulFaktor} />
          {D.factors.map((f) => (
            <div key={f.k} style={{ display: "flex", alignItems: "center", gap: 8, height: 19 }}>
              <span style={{ width: 250, fontFamily: tubuhFont, fontSize: 15, color: SOROT.has(f.k) ? warna.nyala : warna.kapur }}>{FAKTOR[f.k][bahasa === "id" ? 0 : 1]}</span>
              <span style={{ width: Math.max(2, (200 * f.v) / maks), height: 12, background: SOROT.has(f.k) ? warna.nyala : f.k === D.factors[0].k ? "#3FBF7F" : warna.abu }} />
              <span style={{ ...angkaGaya, fontSize: 14, color: warna.abu }}>{T.k(f.v, 3)}</span>
            </div>
          ))}
          <div style={{ ...kecil, fontSize: 13, marginTop: 4 }}>{T.catatanFaktor}</div>
        </div>
        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 10 }}>
          <div>
            <Judul2 anak={T.diuji} />
            <div style={{ ...kecil, fontSize: 16, color: warna.kapur }}>{T.diujiTeks}</div>
          </div>
          <div>
            <Judul2 anak={T.tumpang} />
            <div style={{ ...kecil, fontSize: 16, color: warna.kapur }}>{T.tumpangTeks}</div>
          </div>
          <div>
            <Judul2 anak={T.artinya} />
            {T.artinyaTeks.map((l) => (
              <div key={l} style={{ ...kecil, fontSize: 16, color: warna.kapur }}>· {l}</div>
            ))}
          </div>
        </div>
      </div>
      <div style={{ ...kecil, fontSize: 13, borderTop: `1px solid ${warna.garis}`, paddingTop: 8, marginTop: "auto" }}>{T.sumber}</div>
    </AbsoluteFill>
  );
};

/* ================================ film ================================ */

const HIJAU = D.warna.risk;
const H = D.hindcast as Record<string, { model: number; distance: number; km2: number }>;
const OBS = D.observed_km2 as Record<string, number>;

const FILM_ID = {
  lokal: "id-ID",
  audio: "audio/sawit",
  musik: "musik-sawit.mp3",
  labelSumber: "Sumber",
  kiri: "Sawit & karhutla · Kalimantan",
  waktu: "November 2026",
  alisJudul: "Analisis citra satelit 2000–2021",
  judul: ["DI MANA AKAN", "ADA KEBUN", "SAWIT BARU?"],
  subJudul: "Peluang lahan Kalimantan menjadi kebun sawit dalam tiga tahun, dan di mana peluang itu bertemu risiko kebakaran.",
  alisBuka: "Kalimantan, sel 500 meter",
  judulBuka: "Kebun sawit hingga 2021, dan lahan yang paling mungkin menyusul",
  barisBuka: "Model: peluang sel menjadi ≥ 50% sawit dalam tiga tahun, dari kondisi lahan akhir 2021",
  sumberBuka: "Peta sawit Descals dkk. 2024 (tahun tanam 2000–2021) · model gradient boosting di grid MODIS 500 m",
  judulLaju: "Sawit baru melambat",
  satuanLaju: "km² lahan yang menjadi sawit dalam tiga tahun",
  perkiraan: "perkiraan",
  catatanLaju: "Perkiraan 2022–2024 dari kondisi akhir 2021. Sawit yang ditanam 2020–2021 belum terdeteksi penuh di peta.",
  sumberLaju: "Peta sawit Descals dkk. 2024 · sel MODIS 500 m yang melewati 50% sawit",
  judulFaktor: "Apa yang menentukan lokasi sawit baru?",
  ukuranFaktor: "Seberapa turun ketepatan model (PR-AUC) jika faktor itu diacak · validasi silang blok 50 km",
  sumberFaktor: "Sawit Descals dkk. · hutan JRC TMF · konsesi & kawasan hutan GFW (KLHK 2017) · gambut BBSDLP · api MCD64A1 · GRIP4 · SRTM",
  judulUji: "Ujian: dilatih sampai 2010, diuji sesudahnya",
  ujiLabel: "bagian sawit baru yang berada di 10% lahan paling berisiko",
  modelL: "Model",
  jarakL: "Jarak ke kebun saja",
  catatanUji: (p: string) => `Validasi silang blok 50 km: PR-AUC ${p}, sedangkan tebakan acak hanya ${komaL(D.base_rate_pct / 100, 3, "id-ID")}.`,
  sumberUji: "Hindcast: model dilatih dengan kondisi 2002–2010, dinilai pada sawit baru 2014–2016 dan 2017–2019",
  alisPeta: "10% lahan paling berisiko, 2022–2024",
  petaBaris: [
    ["dekat", "berada ≤ 5 km dari kebun yang sudah ada"],
    ["luar", "sawit baru diperkirakan di luar konsesi terpetakan"],
    ["hp", "diperkirakan di Hutan Produksi: izinnya perlu diperiksa"],
  ] as [string, string][],
  sumberPeta: "Risiko konversi dari akhir 2021 · konsesi sawit GFW (± 2012) · kawasan hutan KLHK 2017 via GFW",
  alisApi: "Tumpang tindih dengan risiko api El Niño 2027",
  satuanApi: "km² masuk keduanya",
  apiBaris: (p: string, apl: string, hp: string, g: string) => [
    `${p}% lahan berisiko sawit juga berisiko api tinggi`,
    `${apl}% APL · ${hp}% Hutan Produksi · ${g}% gambut`,
  ],
  sumberApi: "Risiko api: model MCD64A1, skenario hujan tahun kering · 10% teratas seluruh daratan",
  legenda: [
    ["palm", "Sawit hingga 2021"],
    ["risk", "10% teratas risiko jadi sawit"],
    ["fire", "10% teratas risiko api 2027 (El Niño)"],
    ["both", "Keduanya"],
  ] as [keyof typeof D.warna, string][],
  tutup1: "Di mana akan ada kebun sawit baru?",
  tutup2: "Hampir selalu di samping sawit yang sudah ada: di lahan terbuka atau hutan rusak, dekat jalan dan sungai.",
  tutup3: "Di tempat sawit dan api bertemu, pencegahan dan pemeriksaan izin paling diperlukan.",
  tutupCatat:
    "Peta ini menunjukkan peluang, bukan rencana atau pelaku. Sawit yang ditanam 2020–2021 belum terdeteksi penuh; peta kawasan hutan dari 2017; konsesi terpetakan ± 2012. Belum ditelaah sejawat.",
  sumberData: "Sumber data",
  barisSumber: [
    ["Sawit", "Descals dkk. 2024, peta sawit industri & rakyat dengan tahun tanam 2000–2021"],
    ["Hutan", "JRC Tropical Moist Forest 1990–2024"],
    ["Kawasan", "KLHK kawasan hutan 2017 (via Global Forest Watch); konsesi sawit & HTI GFW"],
    ["Gambut", "BBSDLP (via GFW)"],
    ["Api", "MODIS MCD64A1 v6.1 (NASA), 500 m; hujan CHIRPS"],
    ["Akses", "GRIP4 jalan; WWF Free-Flowing Rivers; SRTM"],
  ],
  peringatan: "Hasil model statistik, bukan bukti pelanggaran. Tidak ada perusahaan yang disebut.",
};

type FilmTeks = typeof FILM_ID;

const FILM_EN: FilmTeks = {
  ...FILM_ID,
  lokal: "en-GB",
  audio: "audio/sawit-en",
  musik: "musik-sawit-en.mp3",
  labelSumber: "Source",
  kiri: "Palm & fire · Kalimantan",
  alisJudul: "Satellite analysis 2000–2021",
  judul: ["WHERE WILL", "OIL PALM", "GO NEXT?"],
  subJudul: "The chance that land in Kalimantan becomes oil palm within three years, and where that chance meets fire risk.",
  alisBuka: "Kalimantan, 500-metre cells",
  judulBuka: "Oil palm by 2021, and the land most likely to follow",
  barisBuka: "Model: the chance a cell becomes ≥ 50% oil palm within three years, from the land as it was at the end of 2021",
  sumberBuka: "Oil palm map: Descals et al. 2024 (planting years 2000–2021) · gradient boosting on the MODIS 500 m grid",
  judulLaju: "New oil palm has slowed",
  satuanLaju: "km² of land that became oil palm within three years",
  perkiraan: "expected",
  catatanLaju: "2022–2024 expected from the end-2021 state. Palm planted in 2020–2021 is not yet fully detected in the map.",
  sumberLaju: "Oil palm map: Descals et al. 2024 · MODIS 500 m cells passing 50% oil palm",
  judulFaktor: "What decides where new oil palm goes?",
  ukuranFaktor: "How much the model's accuracy (PR-AUC) drops when the factor is shuffled · 50 km block cross-validation",
  sumberFaktor: "Palm: Descals et al. · forest: JRC TMF · concessions & forest zones: GFW (KLHK 2017) · peat: BBSDLP · fire: MCD64A1 · GRIP4 · SRTM",
  judulUji: "The test: trained up to 2010, checked on the years after",
  ujiLabel: "share of new oil palm inside the riskiest 10% of land",
  modelL: "Model",
  jarakL: "Distance to plantations alone",
  catatanUji: (p: string) => `50 km block cross-validation: PR-AUC ${p}, against ${komaL(D.base_rate_pct / 100, 3, "en-GB")} for a random guess.`,
  sumberUji: "Hindcast: model trained on 2002–2010 states, scored on new oil palm in 2014–2016 and 2017–2019",
  alisPeta: "Riskiest 10% of land, 2022–2024",
  petaBaris: [
    ["dekat", "lies within 5 km of existing plantations"],
    ["luar", "of expected new palm falls outside mapped concessions"],
    ["hp", "expected in Production Forest: permits need checking"],
  ],
  sumberPeta: "Conversion risk from end-2021 · oil palm concessions GFW (c. 2012) · forest zones KLHK 2017 via GFW",
  alisApi: "Overlap with El Niño 2027 fire risk",
  satuanApi: "km² fall in both",
  apiBaris: (p: string, apl: string, hp: string, g: string) => [
    `${p}% of high palm-risk land is also high fire-risk land`,
    `${apl}% APL · ${hp}% Production Forest · ${g}% peat`,
  ],
  sumberApi: "Fire risk: MCD64A1 model, dry-year rainfall scenario · top 10% of all land",
  legenda: [
    ["palm", "Oil palm by 2021"],
    ["risk", "Top 10% palm-conversion risk"],
    ["fire", "Top 10% fire risk, El Niño 2027"],
    ["both", "Both"],
  ],
  tutup1: "Where will oil palm go next?",
  tutup2: "Almost always next to the oil palm already there: on open land or damaged forest, near roads and rivers.",
  tutup3: "Where new palm and fire risk meet, prevention and permit checks matter most.",
  tutupCatat:
    "This map shows likelihood, not plans or who is responsible. Palm planted in 2020–2021 is under-detected; the forest-zone map is from 2017; mapped concessions date from about 2012. Not yet peer reviewed.",
  sumberData: "Data sources",
  barisSumber: [
    ["Oil palm", "Descals et al. 2024, industrial & smallholder oil palm with planting years 2000–2021"],
    ["Forest", "JRC Tropical Moist Forest 1990–2024"],
    ["Zoning", "KLHK forest areas 2017 (via Global Forest Watch); GFW oil palm & pulpwood concessions"],
    ["Peat", "BBSDLP (via GFW)"],
    ["Fire", "MODIS MCD64A1 v6.1 (NASA), 500 m; CHIRPS rainfall"],
    ["Access", "GRIP4 roads; WWF Free-Flowing Rivers; SRTM"],
  ],
  peringatan: "Statistical model results, not evidence of wrongdoing. No company is named.",
};

const FCtx = React.createContext<Bahasa>("id");
const useF = () => {
  const b = React.useContext(FCtx);
  const T = b === "en" ? FILM_EN : FILM_ID;
  return { T, b, koma: (n: number, d = 0) => komaL(n, d, T.lokal), ribuan: (n: number) => ribuanL(n, T.lokal) };
};

const FBkg: React.FC<{ sumber?: string; tampil?: number }> = ({ sumber, tampil }) => {
  const { T } = useF();
  return <Bingkai kiri={T.kiri} waktu={T.waktu} labelSumber={T.labelSumber} sumber={sumber} tampil={tampil} />;
};

const FAlis: React.FC<{ anak: string }> = ({ anak }) => (
  <div style={{ fontFamily: tubuhFont, fontSize: 21, fontWeight: 600, letterSpacing: "0.22em", textTransform: "uppercase", color: warna.bara }}>{anak}</div>
);

/** The map, layer by layer; each prop is that layer's opacity. */
const PetaLapis: React.FC<{ sawit?: number; risiko?: number; api?: number; keduanya?: number; redup?: number }> = ({
  sawit = 0,
  risiko = 0,
  api = 0,
  keduanya = 0,
  redup = 0,
}) => (
  <AbsoluteFill style={{ backgroundColor: warna.jelaga }}>
    <AbsoluteFill style={{ opacity: 1 - redup }}>
      <Img src={staticFile("sawit/film_dasar.jpg")} style={{ width: "100%", height: "100%" }} />
      {(
        [
          ["sawit", sawit],
          ["risiko", risiko],
          ["api", api],
          ["keduanya", keduanya],
        ] as [string, number][]
      ).map(([n, o]) =>
        o > 0 ? <Img key={n} src={staticFile(`sawit/film_${n}.png`)} style={{ position: "absolute", inset: 0, width: "100%", height: "100%", opacity: o }} /> : null,
      )}
    </AbsoluteFill>
    <AbsoluteFill style={{ background: `linear-gradient(90deg, ${warna.jelaga} 0%, ${warna.jelaga} 30%, rgba(10,12,15,0) 44%)` }} />
  </AbsoluteFill>
);

const FLegenda: React.FC<{ tampil: (k: string) => number }> = ({ tampil }) => {
  const { T } = useF();
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {T.legenda.map(([w, l]) => (
        <div key={w} style={{ display: "flex", alignItems: "center", gap: 12, fontFamily: tubuhFont, fontSize: 22, color: warna.kapur, opacity: tampil(w) }}>
          <span style={{ width: 26, height: 16, background: D.warna[w], display: "inline-block" }} />
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
      <PetaLapis sawit={1} risiko={1} redup={0.45} />
      <Kolom jarak={26}>
        <div style={{ opacity: a, transform: `translateY(${(1 - a) * 20}px)` }}>
          <div style={{ marginBottom: 24 }}>
            <FAlis anak={T.alisJudul} />
          </div>
          <h1 style={{ fontFamily: judulFont, fontWeight: 900, fontSize: 88, lineHeight: 0.94, letterSpacing: "-0.04em", color: warna.kapur, margin: 0 }}>
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

const FBuka: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { T } = useF();
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const s = masuk(f, 10, 30);
  const r = masuk(f, Math.round(panjang * 0.55), 30);
  return (
    <Lembut panjang={panjang}>
      <PetaLapis sawit={s} risiko={r} />
      <FBkg sumber={T.sumberBuka} tampil={a} />
      <Kolom jarak={26}>
        <div style={{ width: 680, opacity: a }}>
          <FAlis anak={T.alisBuka} />
          <div style={{ marginTop: 16 }}>
            <Judul anak={T.judulBuka} ukuran={54} />
          </div>
        </div>
        <div style={{ width: 680, opacity: r, borderLeft: `3px solid ${HIJAU}`, paddingLeft: 18, fontFamily: tubuhFont, fontSize: 27, color: warna.kapur, lineHeight: 1.35 }}>
          {T.barisBuka}
        </div>
        <FLegenda tampil={(k) => (k === "palm" ? s : k === "risk" ? r : 0)} />
      </Kolom>
    </Lembut>
  );
};

const FLaju: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { T, ribuan } = useF();
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const per = ["2011-2013", "2014-2016", "2017-2019"];
  const nilai = [...per.map((p) => OBS[p]), Math.round(D.expected_km2 / 10) * 10];
  const label = ["2011–13", "2014–16", "2017–19", "2022–24"];
  const mulai = [0.12, 0.24, 0.36, 0.62];
  const maks = Math.max(...nilai);
  const Hb = 420;
  const c = masuk(f, Math.round(panjang * 0.75), 22);
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <FBkg sumber={T.sumberLaju} tampil={a} />
      <Kolom jarak={30}>
        <div style={{ opacity: a }}>
          <Judul anak={T.judulLaju} ukuran={62} />
          <div style={{ fontFamily: tubuhFont, fontSize: 24, color: warna.abu, marginTop: 10 }}>{T.satuanLaju}</div>
        </div>
        <div style={{ display: "flex", alignItems: "flex-end", gap: 70, height: Hb + 120 }}>
          {nilai.map((v, i) => {
            const t = masuk(f, Math.round(panjang * mulai[i]), 26);
            const kira = i === 3;
            return (
              <div key={i} style={{ display: "flex", flexDirection: "column", alignItems: "center", width: 240, opacity: Math.min(1, t * 2) }}>
                <div style={{ ...angkaGaya, fontSize: 46, fontWeight: 600, color: kira ? HIJAU : warna.nyala, marginBottom: 10 }}>
                  {kira ? "≈" : ""}
                  {ribuan(v * t)}
                </div>
                <div
                  style={{
                    width: 200,
                    height: (Hb * v * t) / maks,
                    background: kira ? "transparent" : warna.abu,
                    border: kira ? `3px dashed ${HIJAU}` : "none",
                  }}
                />
                <div style={{ fontFamily: tubuhFont, fontSize: 26, color: warna.kapur, marginTop: 12 }}>{label[i]}</div>
                <div style={{ fontFamily: tubuhFont, fontSize: 20, color: HIJAU, height: 26 }}>{kira ? T.perkiraan : ""}</div>
              </div>
            );
          })}
        </div>
        <div style={{ fontFamily: tubuhFont, fontSize: 22, color: warna.abu, opacity: c, maxWidth: 1500 }}>{T.catatanLaju}</div>
      </Kolom>
    </Lembut>
  );
};

const FFaktor: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { T, b, koma } = useF();
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const maks = D.factors[0].v;
  // follows the narration: closeness, forest, access, the rest; status and fire last
  const kapan = (k: string, i: number) =>
    k === "forest-area status (APL etc.)" ? 0.58 : k === "fire" ? 0.72 : [0.14, 0.3, 0.44][i] ?? 0.5;
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <FBkg sumber={T.sumberFaktor} tampil={a} />
      <Kolom jarak={22}>
        <div style={{ opacity: a }}>
          <Judul anak={T.judulFaktor} ukuran={56} />
          <div style={{ fontFamily: tubuhFont, fontSize: 22, color: warna.abu, marginTop: 10 }}>{T.ukuranFaktor}</div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
          {D.factors.map((x, i) => {
            const t = masuk(f, Math.round(panjang * kapan(x.k, i)), 24);
            const sorot = SOROT.has(x.k);
            const w = sorot ? warna.nyala : i === 0 ? HIJAU : warna.abu;
            return (
              <div key={x.k} style={{ display: "flex", alignItems: "center", gap: 18, height: 40, opacity: Math.max(0.25, Math.min(1, t * 1.5)) }}>
                <span style={{ width: 560, fontFamily: tubuhFont, fontSize: 28, color: sorot ? warna.nyala : warna.kapur }}>{FAKTOR[x.k][b === "id" ? 0 : 1]}</span>
                <span style={{ width: Math.max(4, ((900 * x.v) / maks) * t), height: 26, background: w }} />
                <span style={{ ...angkaGaya, fontSize: 26, color: sorot ? warna.nyala : warna.abu, opacity: t }}>{koma(x.v, 3)}</span>
              </div>
            );
          })}
        </div>
      </Kolom>
    </Lembut>
  );
};

const FUji: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { T, koma } = useF();
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const c = masuk(f, Math.round(panjang * 0.8), 22);
  const per: [string, string, number][] = [
    ["2014-2016", "2014–16", 0.3],
    ["2017-2019", "2017–19", 0.55],
  ];
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <FBkg sumber={T.sumberUji} tampil={a} />
      <Kolom jarak={34}>
        <div style={{ opacity: a }}>
          <Judul anak={T.judulUji} ukuran={58} />
          <div style={{ fontFamily: tubuhFont, fontSize: 24, color: warna.abu, marginTop: 10 }}>{T.ujiLabel}</div>
        </div>
        {per.map(([k, l, m]) => {
          const t = masuk(f, Math.round(panjang * m), 30);
          const t2 = masuk(f, Math.round(panjang * 0.78), 30);
          return (
            <div key={k} style={{ display: "flex", gap: 30, alignItems: "center", opacity: Math.min(1, t * 2) }}>
              <div style={{ width: 170, fontFamily: tubuhFont, fontSize: 32, fontWeight: 600, color: warna.kapur }}>{l}</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {(
                  [
                    [T.modelL, H[k].model, HIJAU, t],
                    [T.jarakL, H[k].distance, warna.abu, t2],
                  ] as [string, number, string, number][]
                ).map(([n, v, w, tt]) => (
                  <div key={n} style={{ display: "flex", alignItems: "center", gap: 16, opacity: Math.max(0.15, tt) }}>
                    <span style={{ width: 360, fontFamily: tubuhFont, fontSize: 24, color: warna.abu }}>{n}</span>
                    <span style={{ width: 1000, height: 30, background: warna.garis, position: "relative" }}>
                      <span style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: `${v * tt}%`, background: w }} />
                    </span>
                    <span style={{ ...angkaGaya, fontSize: 36, fontWeight: 600, color: w === HIJAU ? HIJAU : warna.kapur, width: 110 }}>{koma(v * tt, 0)}%</span>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
        <div style={{ fontFamily: tubuhFont, fontSize: 22, color: warna.abu, opacity: c }}>{T.catatanUji(koma(D.pr_auc, 2))}</div>
      </Kolom>
    </Lembut>
  );
};

const FPeta: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { T, ribuan } = useF();
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const angka: Record<string, string> = {
    dekat: `${D.near5_pct}%`,
    luar: `${D.outside_conc_pct}%`,
    hp: `≈${ribuan(Math.round(D.hp_km2 / 10) * 10)} km²`,
  };
  const mulai = [0.25, 0.48, 0.66];
  return (
    <Lembut panjang={panjang}>
      <PetaLapis sawit={1} risiko={1} />
      <FBkg sumber={T.sumberPeta} tampil={a} />
      <Kolom jarak={30}>
        <div style={{ opacity: a }}>
          <FAlis anak={T.alisPeta} />
        </div>
        {T.petaBaris.map(([k, l], i) => {
          const t = masuk(f, Math.round(panjang * mulai[i]), 22);
          return (
            <div key={k} style={{ width: 660, opacity: t, transform: `translateY(${(1 - t) * 14}px)` }}>
              <div style={{ ...angkaGaya, fontSize: 84, fontWeight: 600, color: k === "hp" ? warna.nyala : HIJAU, lineHeight: 1 }}>{angka[k]}</div>
              <div style={{ fontFamily: tubuhFont, fontSize: 27, color: warna.kapur, marginTop: 6, lineHeight: 1.3 }}>{l}</div>
            </div>
          );
        })}
        <FLegenda tampil={(k) => (k === "palm" || k === "risk" ? a : 0)} />
      </Kolom>
    </Lembut>
  );
};

const FApi: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { T, ribuan, koma } = useF();
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const api = masuk(f, Math.round(panjang * 0.08), 36);
  const dua = masuk(f, Math.round(panjang * 0.38), 30);
  const c = masuk(f, Math.round(panjang * 0.55), 22);
  const O = D.overlap;
  const baris = T.apiBaris(koma(O.pct_of_palm_top10), koma(O.apl_pct), koma(O.hp_pct), koma(O.peat_pct));
  return (
    <Lembut panjang={panjang}>
      <PetaLapis sawit={1} risiko={1} api={api} keduanya={dua} />
      <FBkg sumber={T.sumberApi} tampil={a} />
      <Kolom jarak={26}>
        <div style={{ width: 660, opacity: a }}>
          <FAlis anak={T.alisApi} />
        </div>
        <div style={{ opacity: dua }}>
          <div style={{ ...angkaGaya, fontSize: 110, fontWeight: 600, color: warna.bara, lineHeight: 1 }}>{ribuan(O.both_km2 * dua)}</div>
          <div style={{ fontFamily: tubuhFont, fontSize: 28, color: warna.kapur }}>{T.satuanApi}</div>
        </div>
        {baris.map((l) => (
          <div key={l} style={{ width: 660, opacity: c, borderLeft: `3px solid ${warna.bara}`, paddingLeft: 18, fontFamily: tubuhFont, fontSize: 27, color: warna.kapur, lineHeight: 1.35 }}>
            {l}
          </div>
        ))}
        <div style={{ marginTop: 10 }}>
          <FLegenda tampil={(k) => (k === "fire" ? api : k === "both" ? dua : 1)} />
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
  const c = masuk(f, Math.round(panjang * 0.55), 24);
  const d = masuk(f, Math.round(panjang * 0.05), 24);
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Kolom jarak={28}>
        <h1 style={{ fontFamily: judulFont, fontWeight: 900, fontSize: 60, lineHeight: 1.05, color: warna.abu, margin: 0, opacity: a }}>{T.tutup1}</h1>
        <div style={{ opacity: c, maxWidth: 1500, fontFamily: tubuhFont, fontSize: 42, color: warna.kapur, lineHeight: 1.3 }}>{T.tutup2}</div>
        <h2 style={{ fontFamily: judulFont, fontWeight: 900, fontSize: 60, lineHeight: 1.08, letterSpacing: "-0.02em", color: warna.bara, margin: 0, opacity: c, maxWidth: 1600 }}>{T.tutup3}</h2>
        <div style={{ opacity: Math.min(d, 1) * b, borderLeft: `3px solid ${warna.garis}`, paddingLeft: 20, fontFamily: tubuhFont, fontSize: 25, color: warna.abu, lineHeight: 1.45, maxWidth: 1500, marginTop: 14 }}>
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
  "02-laju": FLaju,
  "03-faktor": FFaktor,
  "04-uji": FUji,
  "05-peta": FPeta,
  "06-api": FApi,
  "07-tutup": FTutup,
};

export const SawitFilm: React.FC<{ bahasa?: Bahasa }> = ({ bahasa = "id" }) => {
  const J = JADWAL_SAWIT[bahasa]!;
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
