/**
 * "Di mana sawit tumbuh berikutnya?" / "Where will oil palm go next?" One infographic page (1080x1350)
 * per language: the top 10% oil-palm conversion risk (2022-2024, from end-2021) over the top 10% El Nino
 * 2027 fire risk, the factor ranking and the hindcast check.
 *
 * Every figure is from sawitData.json (scripts/sawit_infografis_assets.py, which reads the outputs of
 * scripts/kalimantan_palm_expansion.py). Same palette and type as Api.tsx. No company is named.
 */

import React from "react";
import { AbsoluteFill, Img, staticFile } from "remotion";
import type { Bahasa } from "./jadwalKonsesi";
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
    judul: id ? "Di mana sawit tumbuh berikutnya?" : "Where will oil palm go next?",
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
