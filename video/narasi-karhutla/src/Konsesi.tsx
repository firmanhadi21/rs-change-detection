/**
 * "Di dalam konsesi?" — how much of Kalimantan's 2026 burn fell inside
 * oil-palm concessions.
 *
 * The argument is a comparison against chance: concessions cover 19.6% of
 * the land, so a fire that ignored their boundaries would put about that
 * share of its scars inside them. 2019 and 2023 sit right on it; 2026 is a
 * little over, and the excess is concentrated in four concessions on the
 * Ketapang coast. Three quarters of the burn is still outside.
 *
 * Concessions are named by acronym only. Two sensors appear and are never
 * added: MCD64A1 burned area (Jan–Aug) and FIRMS hotspots (Sep–Oct), each
 * with its own frame and its own source line.
 *
 * Every figure comes from konsesiData.json, written by
 * scripts/kalimantan_concession_film_assets.py.
 */

import React from "react";
import {
  AbsoluteFill,
  Audio,
  Img,
  interpolate,
  Sequence,
  staticFile,
  useCurrentFrame,
} from "remotion";
import { adegan, akhirNarasi, JUDUL_FRAME, TUTUP_FRAME } from "./jadwalKonsesi";
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
import { angkaGaya, judulFont, koma, ribuan, tubuhFont, warna } from "./teema";
import D from "./konsesiData.json";

const WAKTU = "November 2026";
const KIRI = "Karhutla Kalimantan";
const KONSESI_HIJAU = "#34493C";
const KINI = D.tahun.find((t) => t.tahun === 2026)!;
const SUMBER_BA =
  "MODIS MCD64A1 500 m, Jan–Agu 2026 · konsesi sawit: Global Forest Watch (Kementerian Kehutanan ±2012)";

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

const Legenda: React.FC<{ t: number }> = ({ t }) => (
  <div
    style={{
      display: "flex",
      flexDirection: "column",
      gap: 12,
      opacity: t,
      fontFamily: tubuhFont,
      fontSize: 23,
      color: warna.kapur,
    }}
  >
    {(
      [
        [warna.bara, "terbakar, di dalam konsesi"],
        [warna.nyala, "terbakar, di luar konsesi"],
        [KONSESI_HIJAU, "konsesi sawit"],
      ] as [string, string][]
    ).map(([w, k]) => (
      <div key={k} style={{ display: "flex", alignItems: "center", gap: 14 }}>
        <div style={{ width: 26, height: 18, background: w, borderRadius: 2 }} />
        {k}
      </div>
    ))}
  </div>
);

/* ---------------------------------- scenes --------------------------- */

const KartuJudul: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 4, 24);
  return (
    <Lembut panjang={panjang}>
      <Peta berkas="peta.png" panjang={panjang} zoom={1.06} redup={0.35} />
      <Kolom jarak={26}>
        <div style={{ opacity: a, transform: `translateY(${(1 - a) * 20}px)` }}>
          <div style={{ marginBottom: 24 }}>
            <Alis anak="Karhutla Kalimantan · 2026" />
          </div>
          <h1
            style={{
              fontFamily: judulFont,
              fontWeight: 900,
              fontSize: 150,
              lineHeight: 0.9,
              letterSpacing: "-0.04em",
              color: warna.kapur,
              margin: 0,
            }}
          >
            DI DALAM
            <br />
            KONSESI?
          </h1>
          <div style={{ marginTop: 28 }}>
            <Keterangan
              lebar={700}
              anak="Bekas kebakaran tahun ini, dibandingkan dengan batas konsesi sawit."
            />
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Pertanyaan: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 4, 22);
  const b = masuk(f, 70, 22);
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Kolom jarak={18}>
        <h1
          style={{
            fontFamily: judulFont,
            fontWeight: 900,
            fontSize: 104,
            lineHeight: 1.02,
            letterSpacing: "-0.03em",
            color: warna.abu,
            margin: 0,
            opacity: a,
          }}
        >
          Kalimantan terbakar lagi.
        </h1>
        <h2
          style={{
            fontFamily: judulFont,
            fontWeight: 900,
            fontSize: 104,
            lineHeight: 1.02,
            letterSpacing: "-0.03em",
            color: warna.kapur,
            margin: 0,
            maxWidth: 1500,
            opacity: b,
            transform: `translateY(${(1 - b) * 18}px)`,
          }}
        >
          Berapa yang terbakar di dalam konsesi sawit?
        </h2>
      </Kolom>
    </Lembut>
  );
};

const PetaBakar: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  return (
    <Lembut panjang={panjang}>
      <Peta berkas="peta.png" panjang={panjang} zoom={1.05} />
      <Bingkai kiri={KIRI} waktu={WAKTU} sumber={SUMBER_BA} tampil={a} />
      <Kolom jarak={22}>
        <div style={{ opacity: a, width: 640 }}>
          <Alis anak="Januari – Agustus 2026" />
          <div style={{ marginTop: 22 }}>
            <Penghitung ke={KINI.terbakar_ha} mulai={10} panjang={70} ukuran={128} />
          </div>
          <div
            style={{
              fontFamily: tubuhFont,
              fontSize: 32,
              color: warna.kapur,
              marginTop: 8,
            }}
          >
            hektare terbakar di Kalimantan
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
            Di peta ini tiap bekas bakar ditebalkan ±1,5 km agar terlihat.
            Angka dihitung dari piksel asli.
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Seperlima: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const t = masuk(f, 40, 50);
  const pct = D.konsesi_pct;
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Bingkai
        kiri={KIRI}
        waktu={WAKTU}
        sumber={`Global Forest Watch, ${ribuan(D.poligon_konsesi)} poligon konsesi sawit di Kalimantan · luas daratan dari FAO GAUL 2025`}
        tampil={a}
      />
      <Kolom jarak={0}>
        <div style={{ opacity: a, width: 1600 }}>
          <Judul anak="Konsesi sawit menutupi hampir seperlima daratan" ukuran={64} />
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
              {koma(pct * t)}%
            </div>
            <div style={{ fontFamily: tubuhFont, fontSize: 30, color: warna.abu }}>
              {koma(D.konsesi_ha / 1e6)} juta dari {koma(D.daratan_ha / 1e6)} juta hektare
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
                width: `${pct * t}%`,
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
            Jika api tidak mengenal batas konsesi, kira-kira seperlima bekas
            bakar akan jatuh di dalamnya.
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const TigaTahun: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const TINGGI = 400;
  const SKALA = 30; // percent at the top of the chart
  const garis = (D.konsesi_pct / SKALA) * TINGGI;
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Bingkai
        kiri={KIRI}
        waktu={WAKTU}
        sumber="MODIS MCD64A1 500 m · 2019 dan 2023 setahun penuh, 2026 hanya Jan–Agu · konsesi: Global Forest Watch"
        tampil={a}
      />
      <Kolom jarak={0}>
        <div style={{ opacity: a, width: 1600 }}>
          <Judul anak="Bagian bekas bakar yang jatuh di dalam konsesi" ukuran={60} />
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
                luas konsesi: {koma(D.konsesi_pct)}% daratan
              </div>
            </div>
            {D.tahun.map((y, i) => {
              const t = masuk(f, 50 + i * 40, 34);
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
                      height: (y.dalam_pct / SKALA) * TINGGI * t,
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
                        opacity: t,
                      }}
                    >
                      {koma(y.dalam_pct * t)}%
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
            * Januari–Agustus. Data luas bakar September–Oktober belum terbit.
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Ketapang: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const daftar = D.konsesi_teratas;
  return (
    <Lembut panjang={panjang}>
      <Peta berkas="ketapang.png" panjang={panjang} zoom={1.06} />
      <Bingkai kiri={KIRI} waktu={WAKTU} sumber={`${SUMBER_BA} · piksel asli 500 m`} tampil={a} />
      <Kolom jarak={0}>
        <div style={{ opacity: a, width: 820 }}>
          <Alis anak="Ketapang, Kalimantan Barat" />
          <div style={{ marginTop: 18 }}>
            <Judul anak="Empat konsesi di satu pesisir" ukuran={60} />
          </div>
          <div style={{ marginTop: 34 }}>
            <Penghitung
              ke={D.konsesi_teratas_total_ha}
              mulai={150}
              panjang={60}
              ukuran={110}
            />
          </div>
          <div style={{ fontFamily: tubuhFont, fontSize: 28, color: warna.kapur, marginTop: 6 }}>
            hektare terbakar di dalam keempatnya
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
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const LEBAR = 900;
  const SKALA = 45; // percent at the right edge
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Bingkai kiri={KIRI} waktu={WAKTU} sumber={SUMBER_BA} tampil={a} />
      <Kolom jarak={0}>
        <div style={{ opacity: a, width: 1600 }}>
          <Judul anak="Bagian areal konsesi yang terbakar, Jan–Agu 2026" ukuran={56} />
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
                sepertiga
              </div>
            </div>
            {D.konsesi_teratas.map((c, i) => {
              const t = masuk(f, 20 + i * 14, 34);
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
                      width: (c.terbakar_pct / SKALA) * LEBAR * t,
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
                      opacity: t,
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
                      {koma(c.terbakar_pct * t, 0)}%
                    </div>
                    <div style={{ ...angkaGaya, fontSize: 24, color: warna.abu }}>
                      {ribuan(c.terbakar_ha)} dari {ribuan(c.luas_ha)} ha
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
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const b = masuk(f, 150, 24);
  const p = D.patch_terbesar;
  return (
    <Lembut panjang={panjang}>
      <Peta berkas="peta.png" panjang={panjang} zoom={1.05} redup={0.2} />
      <Bingkai kiri={KIRI} waktu={WAKTU} sumber={SUMBER_BA} tampil={a} />
      <Kolom jarak={0}>
        <div style={{ opacity: a, width: 700 }}>
          <Alis anak="Tetapi" />
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
            bekas bakar berada di luar konsesi
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
            <div style={{ fontFamily: tubuhFont, fontSize: 21, letterSpacing: "0.18em", textTransform: "uppercase", color: warna.abu }}>
              Kebakaran terbesar 2026
            </div>
            <div style={{ ...angkaGaya, fontSize: 52, fontWeight: 600, color: warna.kapur, marginTop: 8 }}>
              {ribuan(p.luas_ha)} ha
            </div>
            <div style={{ fontFamily: tubuhFont, fontSize: 26, color: warna.abu, marginTop: 4 }}>
              {p.kabupaten}, {p.provinsi}
              <br />
              {koma((100 * p.dalam_ha) / p.luas_ha, 0)}% di dalam konsesi
            </div>
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const September: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const [w0, w1] = D.titik_jendela;
  const tgl = (s: string) =>
    new Date(s + "T00:00:00Z").toLocaleDateString("id-ID", {
      day: "numeric",
      month: "short",
      timeZone: "UTC",
    });
  return (
    <Lembut panjang={panjang}>
      <Peta berkas="peta_titik.png" panjang={panjang} zoom={1.05} />
      <Bingkai
        kiri={KIRI}
        waktu={WAKTU}
        sumber={`NASA FIRMS MODIS 1 km, keyakinan ≥ 30, ${tgl(w0)} – ${tgl(w1)} 2026 · deteksi titik panas per piksel per hari, bukan luas terbakar`}
        tampil={a}
      />
      <Kolom jarak={0}>
        <div style={{ opacity: a, width: 660 }}>
          <Alis anak={`${tgl(w0)} – ${tgl(w1)} 2026`} />
          <div style={{ marginTop: 22 }}>
            <Penghitung ke={D.titik.total} mulai={90} panjang={70} ukuran={124} />
          </div>
          <div style={{ fontFamily: tubuhFont, fontSize: 30, color: warna.kapur, marginTop: 6 }}>
            deteksi titik panas di Kalimantan
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
              di dalam konsesi
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
            Sensor dan periode lain dari luas bakar — angkanya tidak dijumlahkan.
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Tutup: React.FC<{ panjang: number }> = ({ panjang }) => {
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
          Lokasi bukan pembuktian.
        </h1>
        <div style={{ opacity: a, maxWidth: 1300 }}>
          <Keterangan
            lebar={1300}
            anak="Batas konsesi dari data Kementerian Kehutanan sekitar 2012, dan api bisa menyeberang batas."
          />
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
          Peta ini menunjukkan di mana pemeriksaan harus dimulai.
        </h2>
      </Kolom>
    </Lembut>
  );
};

const KartuSumber: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 4, 20);
  const baris: [string, string][] = [
    ["Luas bakar", "MODIS MCD64A1 v6.1, 500 m, Jan–Agu 2026 (2019 dan 2023 setahun penuh)"],
    ["Titik panas", "NASA FIRMS MODIS 1 km, keyakinan ≥ 30, 1 Sep – 1 Nov 2026"],
    ["Konsesi", "Global Forest Watch, Indonesia oil palm concessions (Kementerian Kehutanan ±2012)"],
    ["Nama", "Konsesi disebut dengan singkatan huruf awal nama perusahaan"],
    ["Wilayah", "FAO GAUL 2025, lima provinsi Kalimantan"],
  ];
  return (
    <AbsoluteFill style={{ backgroundColor: warna.jelaga, opacity: a }}>
      <Kolom jarak={20}>
        <Alis anak="Sumber data" />
        <div style={{ display: "flex", flexDirection: "column", gap: 13, width: 1620 }}>
          {baris.map(([k, v]) => (
            <div key={k} style={{ display: "flex", gap: 28, alignItems: "baseline" }}>
              <div style={{ width: 230, fontFamily: tubuhFont, fontSize: 25, fontWeight: 600, color: warna.kapur }}>
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
          Bekas bakar di dalam batas konsesi menunjukkan lokasi api, bukan
          siapa yang menyalakannya. Batas konsesi bisa sudah berubah sejak
          2012. MCD64A1 tidak menangkap kebakaran beberapa hektare, sehingga
          semua luas adalah batas bawah.
        </div>
      </Kolom>
    </AbsoluteFill>
  );
};

/* --------------------------------- film ------------------------------ */

const PETA: Record<string, React.FC<{ panjang: number }>> = {
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

export const Konsesi: React.FC = () => (
  <AbsoluteFill style={{ backgroundColor: warna.jelaga }}>
    <Audio src={staticFile("audio/konsesi/musik-konsesi.mp3")} />

    <Sequence durationInFrames={JUDUL_FRAME}>
      <KartuJudul panjang={JUDUL_FRAME} />
    </Sequence>

    {adegan.map((a) => {
      const K = PETA[a.id as string];
      return (
        <Sequence key={a.id} from={a.mulai} durationInFrames={a.panjang}>
          <K panjang={a.panjang} />
          <Audio src={staticFile(`audio/konsesi/${a.id}.mp3`)} />
        </Sequence>
      );
    })}

    <Sequence from={akhirNarasi} durationInFrames={TUTUP_FRAME}>
      <KartuSumber panjang={TUTUP_FRAME} />
    </Sequence>
  </AbsoluteFill>
);
