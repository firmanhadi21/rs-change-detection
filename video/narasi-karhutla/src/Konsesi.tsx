/**
 * "Di dalam konsesi?" / "Inside the concessions?" — how much of
 * Kalimantan's 2026 burn fell inside oil-palm concessions.
 *
 * The argument is a comparison against chance: concessions cover 19.6% of
 * the land, so a fire that ignored their boundaries would put about that
 * share of its scars inside them. 2019 and 2023 sit right on it; 2026 is a
 * little over, and the excess is concentrated in four concessions on the
 * Ketapang coast. Three quarters of the burn is still outside.
 *
 * One component, two languages. Every on-screen string lives in TEKS below,
 * keyed by `bahasa`; layout and timing are shared, and each language has
 * its own measured schedule (jadwalKonsesi*.json) and audio folder.
 *
 * Concessions are named by acronym only. Two sensors appear and are never
 * added: MCD64A1 burned area (Jan–Aug) and FIRMS hotspots (Sep–Oct), each
 * with its own frame and its own source line.
 *
 * Every figure comes from konsesiData.json, written by
 * scripts/kalimantan_concession_film_assets.py.
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
import { Bahasa, JADWAL } from "./jadwalKonsesi";
import {
  Bingkai,
  Judul,
  Keterangan,
  Kolom,
  LatarDiam,
  Lembut,
  masuk,
  Penghitung,
} from "./komponen";
import {
  angkaGaya,
  judulFont,
  koma as komaId,
  ribuan as ribuanId,
  tubuhFont,
  warna,
} from "./teema";
import D from "./konsesiData.json";

const KONSESI_HIJAU = "#34493C";
const KINI = D.tahun.find((t) => t.tahun === 2026)!;

/* ------------------------------- the words ---------------------------- */

const TEKS = {
  id: {
    lokal: "id-ID",
    audio: "audio/konsesi",
    kiri: "Karhutla Kalimantan",
    waktu: "November 2026",
    sumber: "Sumber",
    sumberBA:
      "MODIS MCD64A1 500 m, Jan–Agu 2026 · konsesi sawit: Global Forest Watch (Kementerian Kehutanan ±2012)",
    alisJudul: "Karhutla Kalimantan · 2026",
    judul: ["DI DALAM", "KONSESI?"],
    judulUkuran: 150,
    subJudul: "Bekas kebakaran tahun ini, dibandingkan dengan batas konsesi sawit.",
    tanya1: "Kalimantan terbakar lagi.",
    tanya2: "Berapa yang terbakar di dalam konsesi sawit?",
    janAgu: "Januari – Agustus 2026",
    haKal: "hektare terbakar di Kalimantan",
    legenda: ["terbakar, di dalam konsesi", "terbakar, di luar konsesi", "konsesi sawit"],
    tebal: "Di peta ini tiap bekas bakar ditebalkan ±1,5 km agar terlihat. Angka dihitung dari piksel asli.",
    sumberLahan: (n: string) =>
      `Global Forest Watch, ${n} poligon konsesi sawit di Kalimantan · luas daratan dari FAO GAUL 2025`,
    seperlima: "Konsesi sawit menutupi hampir seperlima daratan",
    jutaDari: (a: string, b: string) => `${a} juta dari ${b} juta hektare`,
    peluang: "Jika api tidak mengenal batas konsesi, kira-kira seperlima bekas bakar akan jatuh di dalamnya.",
    sumberTahun:
      "MODIS MCD64A1 500 m · 2019 dan 2023 setahun penuh, 2026 hanya Jan–Agu · konsesi: Global Forest Watch",
    bagianDalam: "Bagian bekas bakar yang jatuh di dalam konsesi",
    garisPeluang: (p: string) => `luas konsesi: ${p}% daratan`,
    catatanTahun: "* Januari–Agustus. Data luas bakar September–Oktober belum terbit.",
    pikselAsli: "piksel asli 500 m",
    ketapang: "Ketapang, Kalimantan Barat",
    empat: "Empat konsesi di satu pesisir",
    haEmpat: "hektare terbakar di dalam keempatnya",
    bagianAreal: "Bagian areal konsesi yang terbakar, Jan–Agu 2026",
    sepertiga: "sepertiga",
    dari: (a: string, b: string) => `${a} dari ${b} ha`,
    tetapi: "Tetapi",
    diLuar: "bekas bakar berada di luar konsesi",
    terbesar: "Kebakaran terbesar 2026",
    pctDalam: (p: string) => `${p}% di dalam konsesi`,
    sumberTitik: (w: string) =>
      `NASA FIRMS MODIS 1 km, keyakinan ≥ 30, ${w} 2026 · deteksi titik panas per piksel per hari, bukan luas terbakar`,
    titikKal: "deteksi titik panas di Kalimantan",
    dalam: "di dalam konsesi",
    sensorLain: "Sensor dan periode lain dari luas bakar — angkanya tidak dijumlahkan.",
    tutup1: "Lokasi bukan pembuktian.",
    tutupKet: "Batas konsesi dari data Kementerian Kehutanan sekitar 2012, dan api bisa menyeberang batas.",
    tutup2: "Peta ini menunjukkan di mana pemeriksaan harus dimulai.",
    sumberData: "Sumber data",
    baris: [
      ["Luas bakar", "MODIS MCD64A1 v6.1, 500 m, Jan–Agu 2026 (2019 dan 2023 setahun penuh)"],
      ["Titik panas", "NASA FIRMS MODIS 1 km, keyakinan ≥ 30, 1 Sep – 1 Nov 2026"],
      ["Konsesi", "Global Forest Watch, Indonesia oil palm concessions (Kementerian Kehutanan ±2012)"],
      ["Nama", "Konsesi disebut dengan singkatan huruf awal nama perusahaan"],
      ["Wilayah", "FAO GAUL 2025, lima provinsi Kalimantan"],
    ] as [string, string][],
    peringatan:
      "Bekas bakar di dalam batas konsesi menunjukkan lokasi api, bukan siapa yang menyalakannya. Batas konsesi bisa sudah berubah sejak 2012. MCD64A1 tidak menangkap kebakaran beberapa hektare, sehingga semua luas adalah batas bawah.",
  },
  en: {
    lokal: "en-GB",
    audio: "audio/konsesi-en",
    kiri: "Kalimantan fires",
    waktu: "November 2026",
    sumber: "Source",
    sumberBA:
      "MODIS MCD64A1 500 m, Jan–Aug 2026 · oil palm concessions: Global Forest Watch (Ministry of Forestry, c. 2012)",
    alisJudul: "Kalimantan fires · 2026",
    judul: ["INSIDE THE", "CONCESSIONS?"],
    judulUkuran: 100, // "CONCESSIONS?" is wider than "KONSESI?"; keep it off the map
    subJudul: "This year's burn scars, set against oil palm concession boundaries.",
    tanya1: "Kalimantan is burning again.",
    tanya2: "How much burned inside oil palm concessions?",
    janAgu: "January – August 2026",
    haKal: "hectares burned in Kalimantan",
    legenda: ["burned, inside a concession", "burned, outside", "oil palm concession"],
    tebal: "On this map each burn is drawn ~1.5 km wider so it can be seen. Figures use the true pixels.",
    sumberLahan: (n: string) =>
      `Global Forest Watch, ${n} oil palm concession polygons in Kalimantan · land area from FAO GAUL 2025`,
    seperlima: "Oil palm concessions cover almost a fifth of the land",
    jutaDari: (a: string, b: string) => `${a} million of ${b} million hectares`,
    peluang: "If fire ignored concession boundaries, roughly a fifth of the burn scars would fall inside them.",
    sumberTahun:
      "MODIS MCD64A1 500 m · 2019 and 2023 full years, 2026 Jan–Aug only · concessions: Global Forest Watch",
    bagianDalam: "Share of the burned area inside concessions",
    garisPeluang: (p: string) => `concessions: ${p}% of land`,
    catatanTahun: "* January–August. Burned-area data for September–October is not yet published.",
    pikselAsli: "true 500 m pixels",
    ketapang: "Ketapang, West Kalimantan",
    empat: "Four concessions on one coast",
    haEmpat: "hectares burned inside the four",
    bagianAreal: "Share of each concession that burned, Jan–Aug 2026",
    sepertiga: "one third",
    dari: (a: string, b: string) => `${a} of ${b} ha`,
    tetapi: "But",
    diLuar: "of the burned area lies outside concessions",
    terbesar: "Largest fire of 2026",
    pctDalam: (p: string) => `${p}% inside a concession`,
    sumberTitik: (w: string) =>
      `NASA FIRMS MODIS 1 km, confidence ≥ 30, ${w} 2026 · hotspot detections per pixel per day, not burned area`,
    titikKal: "hotspot detections in Kalimantan",
    dalam: "inside concessions",
    sensorLain: "A different sensor and period from the burned area — the numbers are never added.",
    tutup1: "Location is not proof.",
    tutupKet: "Concession boundaries are Ministry of Forestry data from around 2012, and fire crosses boundaries.",
    tutup2: "This map shows where the checking should begin.",
    sumberData: "Data sources",
    baris: [
      ["Burned area", "MODIS MCD64A1 v6.1, 500 m, Jan–Aug 2026 (2019 and 2023 full years)"],
      ["Hotspots", "NASA FIRMS MODIS 1 km, confidence ≥ 30, 1 Sep – 1 Nov 2026"],
      ["Concessions", "Global Forest Watch, Indonesia oil palm concessions (Ministry of Forestry, c. 2012)"],
      ["Names", "Concessions are given as the initials of the company name"],
      ["Area", "FAO GAUL 2025, the five provinces of Kalimantan"],
    ] as [string, string][],
    peringatan:
      "A burn inside a concession boundary shows where the fire was, not who lit it. Boundaries may have changed since 2012. MCD64A1 misses fires of a few hectares, so every area here is a lower bound.",
  },
};

const Ctx = createContext<Bahasa>("id");

/** The words and number formatting for the film being rendered. */
const useB = () => {
  const b = useContext(Ctx);
  const t = TEKS[b];
  return {
    t,
    ribuan: (n: number) => ribuanId(n, t.lokal),
    koma: (n: number, d = 1) => komaId(n, d, t.lokal),
    // en-GB abbreviates September as "Sept"; the sources card says "Sep".
    tgl: (s: string) =>
      new Date(s + "T00:00:00Z")
        .toLocaleDateString(t.lokal, {
          day: "numeric",
          month: "short",
          timeZone: "UTC",
        })
        .replace("Sept", "Sep"),
  };
};

/** The standing frame, in the film's language. */
const Bkg: React.FC<{ sumber?: string; tampil?: number }> = ({ sumber, tampil }) => {
  const { t } = useB();
  return (
    <Bingkai
      kiri={t.kiri}
      waktu={t.waktu}
      labelSumber={t.sumber}
      sumber={sumber}
      tampil={tampil}
    />
  );
};

/* ------------- a map still, drifting slowly so it is not a slide -------- */
const Peta: React.FC<{
  berkas: string;
  panjang: number;
  zoom?: number;
  redup?: number;
}> = ({ berkas, panjang, zoom = 1.04, redup = 0 }) => {
  const f = useCurrentFrame();
  const s = interpolate(f, [0, panjang], [1, zoom], {
    extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill style={{ backgroundColor: warna.jelaga, overflow: "hidden" }}>
      <Img
        src={staticFile(`konsesi/${berkas}`)}
        style={{
          width: "100%",
          height: "100%",
          transform: `scale(${s})`,
          transformOrigin: "78% 55%",
          opacity: 1 - redup,
        }}
      />
      {/* keep the left column readable where the map reaches into it */}
      <AbsoluteFill
        style={{
          background: `linear-gradient(90deg, ${warna.jelaga} 0%, rgba(10,12,15,0.85) 30%, rgba(10,12,15,0) 48%)`,
        }}
      />
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

const Legenda: React.FC<{ t: number }> = ({ t: tampil }) => {
  const { t } = useB();
  const warnaL = [warna.bara, warna.nyala, KONSESI_HIJAU];
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 12,
        opacity: tampil,
        fontFamily: tubuhFont,
        fontSize: 23,
        color: warna.kapur,
      }}
    >
      {t.legenda.map((k, i) => (
        <div key={k} style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <div style={{ width: 26, height: 18, background: warnaL[i], borderRadius: 2 }} />
          {k}
        </div>
      ))}
    </div>
  );
};

/* ---------------------------------- scenes --------------------------- */

const KartuJudul: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { t } = useB();
  const f = useCurrentFrame();
  const a = masuk(f, 4, 24);
  return (
    <Lembut panjang={panjang}>
      <Peta berkas="peta.png" panjang={panjang} zoom={1.06} redup={0.35} />
      <Kolom jarak={26}>
        <div style={{ opacity: a, transform: `translateY(${(1 - a) * 20}px)` }}>
          <div style={{ marginBottom: 24 }}>
            <Alis anak={t.alisJudul} />
          </div>
          <h1
            style={{
              fontFamily: judulFont,
              fontWeight: 900,
              fontSize: t.judulUkuran,
              lineHeight: 0.9,
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
            <Keterangan lebar={700} anak={t.subJudul} />
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Pertanyaan: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { t } = useB();
  const f = useCurrentFrame();
  const a = masuk(f, 4, 22);
  const b = masuk(f, 70, 22);
  const besar: React.CSSProperties = {
    fontFamily: judulFont,
    fontWeight: 900,
    fontSize: 104,
    lineHeight: 1.02,
    letterSpacing: "-0.03em",
    margin: 0,
  };
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Kolom jarak={18}>
        <h1 style={{ ...besar, color: warna.abu, opacity: a }}>{t.tanya1}</h1>
        <h2
          style={{
            ...besar,
            color: warna.kapur,
            maxWidth: 1500,
            opacity: b,
            transform: `translateY(${(1 - b) * 18}px)`,
          }}
        >
          {t.tanya2}
        </h2>
      </Kolom>
    </Lembut>
  );
};

const PetaBakar: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { t } = useB();
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  return (
    <Lembut panjang={panjang}>
      <Peta berkas="peta.png" panjang={panjang} zoom={1.05} />
      <Bkg sumber={t.sumberBA} tampil={a} />
      <Kolom jarak={22}>
        <div style={{ opacity: a, width: 640 }}>
          <Alis anak={t.janAgu} />
          <div style={{ marginTop: 22 }}>
            <Penghitung
              ke={KINI.terbakar_ha}
              mulai={10}
              panjang={70}
              ukuran={128}
              lokal={t.lokal}
            />
          </div>
          <div style={{ fontFamily: tubuhFont, fontSize: 32, color: warna.kapur, marginTop: 8 }}>
            {t.haKal}
          </div>
          <div style={{ marginTop: 52 }}>
            <Legenda t={masuk(f, 60, 24)} />
          </div>
          <div
            style={{
              marginTop: 28,
              fontFamily: tubuhFont,
              fontSize: 19,
              color: warna.samar,
              lineHeight: 1.4,
              opacity: masuk(f, 80, 24),
            }}
          >
            {t.tebal}
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Seperlima: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { t, koma, ribuan } = useB();
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const n = masuk(f, 40, 50);
  const pct = D.konsesi_pct;
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Bkg sumber={t.sumberLahan(ribuan(D.poligon_konsesi))} tampil={a} />
      <Kolom jarak={0}>
        <div style={{ opacity: a, width: 1600 }}>
          <Judul anak={t.seperlima} ukuran={64} />
          <div style={{ display: "flex", alignItems: "baseline", gap: 22, marginTop: 40 }}>
            <div
              style={{
                ...angkaGaya,
                fontSize: 150,
                fontWeight: 600,
                color: warna.nyala,
                lineHeight: 1,
              }}
            >
              {koma(pct * n)}%
            </div>
            <div style={{ fontFamily: tubuhFont, fontSize: 30, color: warna.abu }}>
              {t.jutaDari(koma(D.konsesi_ha / 1e6), koma(D.daratan_ha / 1e6))}
            </div>
          </div>
          <div
            style={{
              position: "relative",
              marginTop: 40,
              height: 60,
              width: 1500,
              background: "#1B2029",
              borderRadius: 3,
              overflow: "hidden",
            }}
          >
            <div
              style={{
                width: `${pct * n}%`,
                height: "100%",
                background: KONSESI_HIJAU,
                borderRight: `3px solid ${warna.nyala}`,
              }}
            />
          </div>
          <div
            style={{
              marginTop: 30,
              borderLeft: `3px solid ${warna.bara}`,
              paddingLeft: 20,
              fontFamily: tubuhFont,
              fontSize: 29,
              color: warna.kapur,
              maxWidth: 1250,
              lineHeight: 1.4,
              opacity: masuk(f, 150, 24),
            }}
          >
            {t.peluang}
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const TigaTahun: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { t, koma } = useB();
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const TINGGI = 400;
  const SKALA = 30; // percent at the top of the chart
  const garis = (D.konsesi_pct / SKALA) * TINGGI;
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Bkg sumber={t.sumberTahun} tampil={a} />
      <Kolom jarak={0}>
        <div style={{ opacity: a, width: 1600 }}>
          <Judul anak={t.bagianDalam} ukuran={60} />
          <div
            style={{
              position: "relative",
              display: "flex",
              alignItems: "flex-end",
              gap: 160,
              marginTop: 50,
              height: TINGGI + 120,
              paddingLeft: 40,
            }}
          >
            {/* chance line: the concessions' share of land */}
            <div
              style={{
                position: "absolute",
                left: 0,
                right: 0,
                bottom: 60 + garis,
                borderTop: `2px dashed ${warna.abu}`,
                opacity: masuk(f, 20, 20),
              }}
            >
              <div
                style={{
                  position: "absolute",
                  right: 0,
                  top: -40,
                  fontFamily: tubuhFont,
                  fontSize: 22,
                  color: warna.abu,
                }}
              >
                {t.garisPeluang(koma(D.konsesi_pct))}
              </div>
            </div>
            {D.tahun.map((y, i) => {
              const n = masuk(f, 50 + i * 40, 34);
              const ini = y.tahun === 2026;
              return (
                <div
                  key={y.tahun}
                  style={{
                    width: 300,
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    gap: 12,
                  }}
                >
                  <div
                    style={{
                      width: "100%",
                      height: (y.dalam_pct / SKALA) * TINGGI * n,
                      background: ini
                        ? `linear-gradient(180deg, ${warna.nyala} 0%, ${warna.bara} 100%)`
                        : "#3A424D",
                      borderRadius: "3px 3px 0 0",
                      display: "flex",
                      justifyContent: "center",
                      paddingTop: 70,
                    }}
                  >
                    {/* below the chance line, so the two never collide */}
                    <div
                      style={{
                        ...angkaGaya,
                        fontSize: 46,
                        fontWeight: 600,
                        color: ini ? warna.jelaga : warna.kapur,
                        opacity: n,
                      }}
                    >
                      {koma(y.dalam_pct * n)}%
                    </div>
                  </div>
                  <div
                    style={{
                      ...angkaGaya,
                      height: 34,
                      fontSize: 30,
                      fontWeight: ini ? 600 : 400,
                      color: ini ? warna.kapur : warna.abu,
                    }}
                  >
                    {y.tahun}
                    {ini ? "*" : ""}
                  </div>
                </div>
              );
            })}
          </div>
          <div style={{ fontFamily: tubuhFont, fontSize: 21, color: warna.samar, marginTop: 6 }}>
            {t.catatanTahun}
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Ketapang: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { t } = useB();
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const daftar = D.konsesi_teratas;
  return (
    <Lembut panjang={panjang}>
      <Peta berkas="ketapang.png" panjang={panjang} zoom={1.06} />
      <Bkg sumber={`${t.sumberBA} · ${t.pikselAsli}`} tampil={a} />
      <Kolom jarak={0}>
        <div style={{ opacity: a, width: 820 }}>
          <Alis anak={t.ketapang} />
          <div style={{ marginTop: 18 }}>
            <Judul anak={t.empat} ukuran={60} />
          </div>
          <div style={{ marginTop: 34 }}>
            <Penghitung
              ke={D.konsesi_teratas_total_ha}
              mulai={150}
              panjang={60}
              ukuran={110}
              lokal={t.lokal}
            />
          </div>
          <div style={{ fontFamily: tubuhFont, fontSize: 28, color: warna.kapur, marginTop: 6 }}>
            {t.haEmpat}
          </div>
          <div style={{ display: "flex", gap: 22, marginTop: 34, flexWrap: "wrap" }}>
            {daftar.map((c, i) => (
              <div
                key={c.akronim}
                style={{
                  fontFamily: judulFont,
                  fontWeight: 800,
                  fontSize: 34,
                  color: warna.kapur,
                  borderTop: `3px solid ${warna.bara}`,
                  paddingTop: 8,
                  opacity: masuk(f, 190 + i * 38, 18),
                }}
              >
                {c.akronim}
              </div>
            ))}
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Sepertiga: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { t, koma, ribuan } = useB();
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const LEBAR = 900;
  const SKALA = 45; // percent at the right edge
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Bkg sumber={t.sumberBA} tampil={a} />
      <Kolom jarak={0}>
        <div style={{ opacity: a, width: 1600 }}>
          <Judul anak={t.bagianAreal} ukuran={56} />
          <div style={{ position: "relative", marginTop: 54 }}>
            {/* one-third marker */}
            <div
              style={{
                position: "absolute",
                left: 260 + (100 / 3 / SKALA) * LEBAR,
                top: -34,
                bottom: -10,
                borderLeft: `2px dashed ${warna.abu}`,
                opacity: masuk(f, 30, 20),
              }}
            >
              <div
                style={{
                  position: "absolute",
                  top: -8,
                  left: 10,
                  fontFamily: tubuhFont,
                  fontSize: 21,
                  color: warna.abu,
                  whiteSpace: "nowrap",
                }}
              >
                {t.sepertiga}
              </div>
            </div>
            {D.konsesi_teratas.map((c, i) => {
              const n = masuk(f, 20 + i * 14, 34);
              const lewat = c.terbakar_pct > 100 / 3;
              return (
                <div
                  key={c.akronim}
                  style={{
                    position: "relative",
                    display: "flex",
                    alignItems: "center",
                    height: 92,
                  }}
                >
                  <div
                    style={{
                      width: 260,
                      fontFamily: judulFont,
                      fontWeight: 800,
                      fontSize: 38,
                      color: warna.kapur,
                    }}
                  >
                    {c.akronim}
                  </div>
                  <div
                    style={{
                      width: (c.terbakar_pct / SKALA) * LEBAR * n,
                      height: 48,
                      background: lewat ? warna.bara : "#B4541F",
                      borderRadius: "0 3px 3px 0",
                    }}
                  />
                  {/* labels in a fixed column past the longest bar, so the
                      one-third marker never runs through them */}
                  <div
                    style={{
                      position: "absolute",
                      left: 260 + LEBAR + 30,
                      display: "flex",
                      alignItems: "baseline",
                      gap: 24,
                      opacity: n,
                    }}
                  >
                    <div
                      style={{
                        ...angkaGaya,
                        width: 90,
                        textAlign: "right",
                        fontSize: 34,
                        fontWeight: 600,
                        color: lewat ? warna.nyala : warna.kapur,
                      }}
                    >
                      {koma(c.terbakar_pct * n, 0)}%
                    </div>
                    <div style={{ ...angkaGaya, fontSize: 24, color: warna.abu }}>
                      {t.dari(ribuan(c.terbakar_ha), ribuan(c.luas_ha))}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const DiLuar: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { t, koma, ribuan } = useB();
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const b = masuk(f, 150, 24);
  const p = D.patch_terbesar;
  return (
    <Lembut panjang={panjang}>
      <Peta berkas="peta.png" panjang={panjang} zoom={1.05} redup={0.2} />
      <Bkg sumber={t.sumberBA} tampil={a} />
      <Kolom jarak={0}>
        <div style={{ opacity: a, width: 700 }}>
          <Alis anak={t.tetapi} />
          <div
            style={{
              ...angkaGaya,
              fontSize: 170,
              fontWeight: 600,
              color: warna.nyala,
              lineHeight: 1,
              marginTop: 14,
            }}
          >
            {koma(D.luar_pct * masuk(f, 10, 60), 0)}%
          </div>
          <div style={{ fontFamily: tubuhFont, fontSize: 34, color: warna.kapur, marginTop: 6 }}>
            {t.diLuar}
          </div>
          <div
            style={{
              marginTop: 56,
              borderLeft: `3px solid ${warna.bara}`,
              paddingLeft: 22,
              opacity: b,
              transform: `translateY(${(1 - b) * 14}px)`,
            }}
          >
            <div
              style={{
                fontFamily: tubuhFont,
                fontSize: 21,
                letterSpacing: "0.18em",
                textTransform: "uppercase",
                color: warna.abu,
              }}
            >
              {t.terbesar}
            </div>
            <div style={{ ...angkaGaya, fontSize: 52, fontWeight: 600, color: warna.kapur, marginTop: 8 }}>
              {ribuan(p.luas_ha)} ha
            </div>
            <div style={{ fontFamily: tubuhFont, fontSize: 26, color: warna.abu, marginTop: 4 }}>
              {p.kabupaten}, {p.provinsi}
              <br />
              {t.pctDalam(koma((100 * p.dalam_ha) / p.luas_ha, 0))}
            </div>
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const September: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { t, koma, tgl } = useB();
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const [w0, w1] = D.titik_jendela;
  const jendela = `${tgl(w0)} – ${tgl(w1)}`;
  return (
    <Lembut panjang={panjang}>
      <Peta berkas="peta_titik.png" panjang={panjang} zoom={1.05} />
      <Bkg sumber={t.sumberTitik(jendela)} tampil={a} />
      <Kolom jarak={0}>
        <div style={{ opacity: a, width: 660 }}>
          <Alis anak={`${jendela} 2026`} />
          <div style={{ marginTop: 22 }}>
            <Penghitung
              ke={D.titik.total}
              mulai={90}
              panjang={70}
              ukuran={124}
              lokal={t.lokal}
            />
          </div>
          <div style={{ fontFamily: tubuhFont, fontSize: 30, color: warna.kapur, marginTop: 6 }}>
            {t.titikKal}
          </div>
          <div
            style={{
              marginTop: 48,
              display: "flex",
              alignItems: "baseline",
              gap: 18,
              opacity: masuk(f, 200, 22),
            }}
          >
            <div style={{ ...angkaGaya, fontSize: 84, fontWeight: 600, color: warna.nyala }}>
              {koma(D.titik.dalam_pct)}%
            </div>
            <div style={{ fontFamily: tubuhFont, fontSize: 28, color: warna.kapur }}>
              {t.dalam}
            </div>
          </div>
          <div
            style={{
              marginTop: 26,
              fontFamily: tubuhFont,
              fontSize: 21,
              color: warna.samar,
              lineHeight: 1.4,
              opacity: masuk(f, 230, 22),
            }}
          >
            {t.sensorLain}
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Tutup: React.FC<{ panjang: number }> = ({ panjang }) => {
  const { t } = useB();
  const f = useCurrentFrame();
  const a = masuk(f, 4, 22);
  const b = masuk(f, Math.round(panjang * 0.62), 24);
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Kolom jarak={30}>
        <h1
          style={{
            fontFamily: judulFont,
            fontWeight: 900,
            fontSize: 96,
            lineHeight: 1.04,
            letterSpacing: "-0.03em",
            color: warna.kapur,
            margin: 0,
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
            fontSize: 66,
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
      </Kolom>
    </Lembut>
  );
};

const KartuSumber: React.FC<{ panjang: number }> = () => {
  const { t } = useB();
  const f = useCurrentFrame();
  const a = masuk(f, 4, 20);
  return (
    <AbsoluteFill style={{ backgroundColor: warna.jelaga, opacity: a }}>
      <Kolom jarak={20}>
        <Alis anak={t.sumberData} />
        <div style={{ display: "flex", flexDirection: "column", gap: 13, width: 1620 }}>
          {t.baris.map(([k, v]) => (
            <div key={k} style={{ display: "flex", gap: 28, alignItems: "baseline" }}>
              <div
                style={{
                  width: 230,
                  fontFamily: tubuhFont,
                  fontSize: 25,
                  fontWeight: 600,
                  color: warna.kapur,
                }}
              >
                {k}
              </div>
              <div style={{ fontFamily: tubuhFont, fontSize: 25, color: warna.abu }}>{v}</div>
            </div>
          ))}
        </div>
        <div
          style={{
            marginTop: 14,
            paddingTop: 18,
            borderTop: `2px solid ${warna.bara}`,
            fontFamily: tubuhFont,
            fontSize: 23,
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
  "01-pertanyaan": Pertanyaan,
  "02-peta": PetaBakar,
  "03-seperlima": Seperlima,
  "04-tiga-tahun": TigaTahun,
  "05-ketapang": Ketapang,
  "06-sepertiga": Sepertiga,
  "07-di-luar": DiLuar,
  "08-september": September,
  "09-tutup": Tutup,
};

export const Konsesi: React.FC<{ bahasa?: Bahasa }> = ({ bahasa = "id" }) => {
  const j = JADWAL[bahasa];
  const dir = TEKS[bahasa].audio;
  const musik = bahasa === "id" ? "musik-konsesi.mp3" : "musik-konsesi-en.mp3";
  return (
    <Ctx.Provider value={bahasa}>
      <AbsoluteFill style={{ backgroundColor: warna.jelaga }}>
        <Audio src={staticFile(`${dir}/${musik}`)} />

        <Sequence durationInFrames={j.JUDUL_FRAME}>
          <KartuJudul panjang={j.JUDUL_FRAME} />
        </Sequence>

        {j.adegan.map((a) => {
          const K = ADEGAN[a.id];
          return (
            <Sequence key={a.id} from={a.mulai} durationInFrames={a.panjang}>
              <K panjang={a.panjang} />
              <Audio src={staticFile(`${dir}/${a.id}.mp3`)} />
            </Sequence>
          );
        })}

        <Sequence from={j.akhirNarasi} durationInFrames={j.TUTUP_FRAME}>
          <KartuSumber panjang={j.TUTUP_FRAME} />
        </Sequence>
      </AbsoluteFill>
    </Ctx.Provider>
  );
};
