/**
 * The eight scenes, one per spoken line, plus the cards that open and close.
 *
 * Every figure on screen comes from src/narasi.json, which was written from
 * the analysis outputs by scratchpad/narr_facts.py. Nothing here is typed
 * from memory, and no scene shows a number its line does not say.
 */

import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import {
  Bingkai,
  Judul,
  Keterangan,
  Kolom,
  LatarDiam,
  Lembut,
  masuk,
  Penghitung,
  Rekaman,
} from "./komponen";
import { angkaGaya, judulFont, koma, ribuan, tubuhFont, warna } from "./teema";
import narasi from "./narasi.json";

const seg = (id: string) => {
  const s = narasi.segments.find((x) => x.id === id);
  if (!s) throw new Error(`segmen ${id} tidak ada di narasi.json`);
  return s;
};

/* ------------------------------------------------------------------ */
/* Kartu pembuka                                                        */
/* ------------------------------------------------------------------ */

export const KartuJudul: React.FC<{ panjang: number }> = ({ panjang }) => {
  const frame = useCurrentFrame();
  const a = masuk(frame, 6, 26);
  const b = masuk(frame, 22, 26);
  return (
    <Lembut panjang={panjang}>
      <Rekaman kecepatan={0.55} redup={0.42} penuh />
      <Kolom jarak={30}>
        <div style={{ opacity: a, transform: `translateY(${(1 - a) * 22}px)` }}>
          <div
            style={{
              fontFamily: tubuhFont,
              fontSize: 24,
              fontWeight: 600,
              letterSpacing: "0.3em",
              textTransform: "uppercase",
              color: warna.bara,
              marginBottom: 26,
            }}
          >
            Kebakaran hutan dan lahan · Indonesia
          </div>
          <h1
            style={{
              fontFamily: judulFont,
              fontWeight: 900,
              fontSize: 188,
              lineHeight: 0.88,
              letterSpacing: "-0.035em",
              color: warna.kapur,
              margin: 0,
            }}
          >
            MUSIM
            <br />
            TERBURUK
          </h1>
        </div>
        <div style={{ opacity: b, transform: `translateY(${(1 - b) * 18}px)` }}>
          <Keterangan anak="Apa yang direkam satelit di langit Indonesia, Oktober 2026 — dan apa yang tidak terjadi di bawahnya." />
        </div>
      </Kolom>
    </Lembut>
  );
};

/* ------------------------------------------------------------------ */
/* 01 — Ini bukan awan                                                  */
/* ------------------------------------------------------------------ */

export const AdeganBuka: React.FC<{ panjang: number }> = ({ panjang }) => {
  const frame = useCurrentFrame();
  const s = seg("01-buka");
  const a = masuk(frame, 4, 22);
  const b = masuk(frame, 40, 22);
  return (
    <Lembut panjang={panjang}>
      <Rekaman kecepatan={0.55} mulaiDetik={2.5} redup={0.22} penuh />
      <Kolom bawah jarak={18}>
        <h1
          style={{
            fontFamily: judulFont,
            fontWeight: 900,
            fontSize: 132,
            lineHeight: 0.95,
            letterSpacing: "-0.03em",
            color: warna.kapur,
            margin: 0,
            opacity: a,
            transform: `translateY(${(1 - a) * 24}px)`,
          }}
        >
          Ini bukan awan.
        </h1>
        <h2
          style={{
            fontFamily: judulFont,
            fontWeight: 900,
            fontSize: 132,
            lineHeight: 0.95,
            letterSpacing: "-0.03em",
            color: warna.bara,
            margin: 0,
            opacity: b,
            transform: `translateY(${(1 - b) * 24}px)`,
          }}
        >
          Ini asap.
        </h2>
      </Kolom>
      <Bingkai sumber={s.sumber} tampil={a * 0.9} />
    </Lembut>
  );
};

/* ------------------------------------------------------------------ */
/* 02 — Satu minggu, 262.176 titik                                      */
/* ------------------------------------------------------------------ */

export const AdeganSepekan: React.FC<{ panjang: number }> = ({ panjang }) => {
  const frame = useCurrentFrame();
  const s = seg("02-sepekan");
  const a = masuk(frame, 8, 20);
  return (
    <Lembut panjang={panjang}>
      <Rekaman kecepatan={0.5} mulaiDetik={6} redup={0.56} penuh />
      <Kolom jarak={10}>
        <div style={{ opacity: a }}>
          <div
            style={{
              fontFamily: tubuhFont,
              fontSize: 30,
              letterSpacing: "0.18em",
              textTransform: "uppercase",
              color: warna.abu,
              marginBottom: 18,
            }}
          >
            {s.judul}
          </div>
          <Penghitung ke={s.angka as number} mulai={26} panjang={150} ukuran={268} />
          <div
            style={{
              fontFamily: judulFont,
              fontWeight: 800,
              fontSize: 54,
              color: warna.kapur,
              marginTop: 22,
            }}
          >
            {s.satuan}
          </div>
          <div
            style={{
              fontFamily: tubuhFont,
              fontSize: 30,
              color: warna.abu,
              marginTop: 10,
            }}
          >
            {s.ket}
          </div>
        </div>
      </Kolom>
      <Bingkai sumber={s.sumber} tampil={a} />
    </Lembut>
  );
};

/* ------------------------------------------------------------------ */
/* 03 — Di mana (batang per pulau)                                      */
/* ------------------------------------------------------------------ */

export const AdeganPulau: React.FC<{ panjang: number }> = ({ panjang }) => {
  const frame = useCurrentFrame();
  const s = seg("03-pulau");
  const batang = s.batang!;
  const maks = Math.max(...batang.map((b) => b.titik));
  const a = masuk(frame, 6, 18);
  const sorot = masuk(frame, 330, 26);

  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Kolom jarak={0}>
        <div style={{ opacity: a, width: 1560 }}>
          <Judul anak="Tiga pulau menanggung hampir semuanya" ukuran={62} />
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 20,
              marginTop: 44,
            }}
          >
            {batang.map((b, i) => {
              const t = masuk(frame, 26 + i * 12, 34);
              const utama = i < 3;
              // Fixed tracks, not content-sized ones: a bar at full width
              // would otherwise push its own labels off the grid and wrap
              // them, which is exactly what the longest bar did.
              return (
                <div
                  key={b.nama}
                  style={{ display: "flex", alignItems: "center", gap: 22 }}
                >
                  <div
                    style={{
                      width: 206,
                      flex: "0 0 auto",
                      fontFamily: tubuhFont,
                      fontSize: 29,
                      fontWeight: utama ? 600 : 400,
                      color: utama ? warna.kapur : warna.abu,
                      textAlign: "right",
                    }}
                  >
                    {b.nama}
                  </div>
                  <div style={{ width: 940, flex: "0 0 auto" }}>
                    <div
                      style={{
                        width: (b.titik / maks) * 940 * t,
                        height: 44,
                        background: utama
                          ? `linear-gradient(90deg, ${warna.bara} 0%, ${warna.nyala} 100%)`
                          : warna.garis,
                        borderRadius: 2,
                      }}
                    />
                  </div>
                  <div
                    style={{
                      ...angkaGaya,
                      width: 168,
                      flex: "0 0 auto",
                      textAlign: "right",
                      fontSize: 32,
                      fontWeight: 600,
                      color: utama ? warna.nyala : warna.abu,
                      opacity: t,
                    }}
                  >
                    {ribuan(b.titik * t)}
                  </div>
                  <div
                    style={{
                      width: 210,
                      flex: "0 0 auto",
                      whiteSpace: "nowrap",
                      fontFamily: tubuhFont,
                      fontSize: 22,
                      color: warna.samar,
                      opacity: t,
                    }}
                  >
                    {koma(b.kerapatan)} / 1.000 km²
                  </div>
                </div>
              );
            })}
          </div>

          {/* The density outlier the bar lengths hide: Papua's south-east.
              The wrapper reserves its height from the first frame, so the
              centred column does not jump when the callout arrives. */}
          <div
            style={{
              marginTop: 40,
              marginLeft: 228,
              minHeight: 96,
              borderLeft: `3px solid ${warna.bara}`,
              paddingLeft: 22,
              opacity: sorot,
              transform: `translateX(${(1 - sorot) * -14}px)`,
            }}
          >
            <div
              style={{
                fontFamily: tubuhFont,
                fontSize: 27,
                color: warna.kapur,
                lineHeight: 1.4,
                maxWidth: 1180,
              }}
            >
              {s.sorot}
            </div>
          </div>
        </div>
      </Kolom>
      <Bingkai kiri="Sepekan · per pulau" sumber={s.sumber} tampil={a} />
    </Lembut>
  );
};

/* ------------------------------------------------------------------ */
/* 04 — Rekor (kolom 2015–2026)                                         */
/* ------------------------------------------------------------------ */

export const AdeganRekor: React.FC<{ panjang: number }> = ({ panjang }) => {
  const frame = useCurrentFrame();
  const s = seg("04-rekor");
  const deret = s.deret!;
  const maks = Math.max(...deret.map((d) => d.nilai));
  const rerata =
    deret.filter((d) => d.tahun < 2026).reduce((x, d) => x + d.nilai, 0) /
    deret.filter((d) => d.tahun < 2026).length;
  const a = masuk(frame, 6, 18);
  // A column is its figure, its bar and its year stacked. The track has to
  // hold all three, not just the bar, or the tallest column climbs out of
  // the chart and into the headline.
  const TINGGI_BAGAN = 430;
  const TINGGI_TRAK = TINGGI_BAGAN + 110;
  const garisRerata = masuk(frame, 230, 26);

  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Kolom jarak={0}>
        <div style={{ opacity: a, width: 1620 }}>
          <Judul anak="Tahun ini memecahkan rekor sebelas tahun" ukuran={62} />
          <div
            style={{
              fontFamily: tubuhFont,
              fontSize: 27,
              color: warna.abu,
              marginTop: 14,
            }}
          >
            Titik panas di Kalimantan, jendela musim 1 Agustus – 13 Oktober
          </div>

          <div
            style={{
              position: "relative",
              height: TINGGI_TRAK,
              marginTop: 34,
              display: "flex",
              alignItems: "flex-end",
              gap: 20,
            }}
          >
            {/* Eleven-year mean, so the 2026 column has something to beat.
                Offset by the year label's own band so it lands on the bars. */}
            <div
              style={{
                position: "absolute",
                left: 0,
                right: 0,
                bottom: (rerata / maks) * TINGGI_BAGAN + 47,
                borderTop: `2px dashed ${warna.abu}`,
                opacity: garisRerata * 0.8,
              }}
            >
              {/* Sits over the 2020-2022 trough, the one stretch of the
                  chart where nothing reaches the mean. Right-aligned it
                  landed squarely on the 2026 column. */}
              <span
                style={{
                  position: "absolute",
                  left: "47%",
                  top: -36,
                  whiteSpace: "nowrap",
                  fontFamily: tubuhFont,
                  fontSize: 22,
                  color: warna.abu,
                  background: warna.jelaga,
                  padding: "2px 12px",
                  borderRadius: 2,
                }}
              >
                rata-rata 2015–2025 · {ribuan(rerata)}
              </span>
            </div>

            {deret.map((d, i) => {
              const t = masuk(frame, 24 + i * 9, 30);
              const ini = d.tahun === 2026;
              return (
                <div
                  key={d.tahun}
                  style={{
                    flex: 1,
                    height: TINGGI_TRAK,
                    display: "flex",
                    flexDirection: "column",
                    justifyContent: "flex-end",
                    alignItems: "center",
                    gap: 12,
                  }}
                >
                  <div
                    style={{
                      ...angkaGaya,
                      height: 38,
                      display: "flex",
                      alignItems: "flex-end",
                      fontSize: ini ? 34 : 22,
                      fontWeight: 600,
                      color: ini ? warna.nyala : warna.abu,
                      opacity: t,
                    }}
                  >
                    {ribuan(d.nilai * t)}
                  </div>
                  <div
                    style={{
                      width: "100%",
                      height: (d.nilai / maks) * TINGGI_BAGAN * t,
                      background: ini
                        ? `linear-gradient(180deg, ${warna.nyala} 0%, ${warna.bara} 100%)`
                        : warna.garis,
                      borderRadius: "3px 3px 0 0",
                    }}
                  />
                  <div
                    style={{
                      ...angkaGaya,
                      height: 35,
                      fontSize: 23,
                      fontWeight: ini ? 600 : 400,
                      color: ini ? warna.kapur : warna.abu,
                    }}
                  >
                    {d.tahun}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </Kolom>
      <Bingkai kiri="Musim 2026 · Kalimantan" sumber={s.sumber} tampil={a} />
    </Lembut>
  );
};

/* ------------------------------------------------------------------ */
/* 05 — Gambut                                                          */
/* ------------------------------------------------------------------ */

export const AdeganGambut: React.FC<{ panjang: number }> = ({ panjang }) => {
  const frame = useCurrentFrame();
  const s = seg("05-gambut");
  const { min, maks } = s.donat!;
  const a = masuk(frame, 6, 18);
  const pita = masuk(frame, 150, 44);
  const LEBAR_PITA = 1300;

  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Kolom jarak={0}>
        <div style={{ opacity: a, width: 1560 }}>
          <Judul anak="Yang terbakar bukan tanah biasa" ukuran={62} />

          <div style={{ display: "flex", alignItems: "flex-end", gap: 58, marginTop: 40 }}>
            <div>
              <Penghitung ke={s.angka as number} mulai={26} panjang={120} ukuran={150} />
              <div
                style={{
                  fontFamily: tubuhFont,
                  fontSize: 29,
                  color: warna.kapur,
                  marginTop: 14,
                }}
              >
                {s.satuan}
              </div>
              <div
                style={{
                  fontFamily: tubuhFont,
                  fontSize: 24,
                  color: warna.abu,
                  marginTop: 4,
                  maxWidth: 560,
                }}
              >
                {s.ket}
              </div>
            </div>
          </div>

          {/* The peat share is a range, not a number: three peat maps
              disagree, so the band is drawn and both ends are labelled. */}
          <div style={{ marginTop: 56, width: LEBAR_PITA }}>
            <div
              style={{
                position: "relative",
                height: 68,
                background: warna.garis,
                borderRadius: 3,
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  position: "absolute",
                  inset: 0,
                  width: `${min * pita}%`,
                  background: `linear-gradient(90deg, ${warna.gambut} 0%, ${warna.bara} 100%)`,
                }}
              />
              <div
                style={{
                  position: "absolute",
                  top: 0,
                  bottom: 0,
                  left: `${min * pita}%`,
                  width: `${(maks - min) * pita}%`,
                  background: `repeating-linear-gradient(135deg, ${warna.bara} 0 6px, rgba(255,90,31,0.35) 6px 12px)`,
                }}
              />
            </div>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                marginTop: 16,
                opacity: pita,
              }}
            >
              <div
                style={{
                  ...angkaGaya,
                  fontSize: 44,
                  fontWeight: 600,
                  color: warna.nyala,
                }}
              >
                {koma(min)}–{koma(maks)}%
                <span
                  style={{
                    fontFamily: tubuhFont,
                    fontSize: 27,
                    fontWeight: 400,
                    color: warna.kapur,
                    marginLeft: 16,
                  }}
                >
                  gambut
                </span>
              </div>
              <div
                style={{
                  fontFamily: tubuhFont,
                  fontSize: 23,
                  color: warna.abu,
                  alignSelf: "flex-end",
                  maxWidth: 520,
                  textAlign: "right",
                  lineHeight: 1.35,
                }}
              >
                Rentang, bukan satu angka: tiga peta gambut memberi tiga
                jawaban berbeda
              </div>
            </div>
          </div>
        </div>
      </Kolom>
      <Bingkai kiri="Bekas kebakaran 2015–2025" sumber={s.sumber} tampil={a} />
    </Lembut>
  );
};

/* ------------------------------------------------------------------ */
/* 06 — Di dalam kawasan lindung                                        */
/* ------------------------------------------------------------------ */

export const AdeganKhg: React.FC<{ panjang: number }> = ({ panjang }) => {
  const frame = useCurrentFrame();
  const s = seg("06-khg");
  const banding = s.banding!;
  const maks = Math.max(...banding.map((b) => b.nilai));
  const a = masuk(frame, 6, 18);
  const kali = masuk(frame, 420, 30);
  const TINGGI_BAGAN = 330;
  const TINGGI_TRAK = TINGGI_BAGAN + 130; // figure above, label below

  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Kolom jarak={0}>
        <div style={{ opacity: a, width: 1560 }}>
          <Judul anak="Paling parah justru di kawasan yang dilindungi" ukuran={62} />
          <div
            style={{
              fontFamily: tubuhFont,
              fontSize: 27,
              color: warna.abu,
              marginTop: 14,
            }}
          >
            {s.ket}
          </div>

          <div
            style={{
              display: "flex",
              alignItems: "flex-end",
              gap: 86,
              marginTop: 44,
              height: TINGGI_TRAK,
            }}
          >
            {banding.map((b, i) => {
              const t = masuk(frame, 40 + i * 26, 38);
              const dalam = i === 0;
              return (
                <div
                  key={b.nama}
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    justifyContent: "flex-end",
                    alignItems: "center",
                    gap: 14,
                    width: 280,
                    height: TINGGI_TRAK,
                  }}
                >
                  <div
                    style={{
                      ...angkaGaya,
                      height: 66,
                      display: "flex",
                      alignItems: "flex-end",
                      fontSize: 62,
                      fontWeight: 600,
                      color: dalam ? warna.bara : warna.abu,
                      opacity: t,
                    }}
                  >
                    {koma(b.nilai * t, 1)}%
                  </div>
                  <div
                    style={{
                      width: "100%",
                      height: (b.nilai / maks) * TINGGI_BAGAN * t,
                      background: dalam
                        ? `linear-gradient(180deg, ${warna.bara} 0%, ${warna.gambut} 100%)`
                        : warna.garis,
                      borderRadius: "3px 3px 0 0",
                    }}
                  />
                  <div
                    style={{
                      height: 38,
                      fontFamily: tubuhFont,
                      fontSize: 27,
                      fontWeight: dalam ? 600 : 400,
                      color: dalam ? warna.kapur : warna.abu,
                      textAlign: "center",
                    }}
                  >
                    {b.nama}
                  </div>
                </div>
              );
            })}

            <div
              style={{
                opacity: kali,
                transform: `translateX(${(1 - kali) * -18}px)`,
                paddingBottom: 74,
              }}
            >
              <div
                style={{
                  fontFamily: judulFont,
                  fontWeight: 900,
                  fontSize: 104,
                  color: warna.nyala,
                  lineHeight: 1,
                }}
              >
                6,5×
              </div>
              <div
                style={{
                  fontFamily: tubuhFont,
                  fontSize: 27,
                  color: warna.kapur,
                  maxWidth: 420,
                  marginTop: 10,
                  lineHeight: 1.35,
                }}
              >
                lebih sering terbakar di dalam kawasan yang ditetapkan untuk
                dipulihkan
              </div>
            </div>
          </div>
        </div>
      </Kolom>
      <Bingkai kiri="Kesatuan Hidrologis Gambut" sumber={s.sumber} tampil={a} />
    </Lembut>
  );
};

/* ------------------------------------------------------------------ */
/* 07 — Dan terbakar lagi                                               */
/* ------------------------------------------------------------------ */

export const AdeganBerulang: React.FC<{ panjang: number }> = ({ panjang }) => {
  const frame = useCurrentFrame();
  const s = seg("07-berulang");
  const a = masuk(frame, 6, 18);

  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Kolom jarak={0}>
        <div style={{ opacity: a, width: 1560 }}>
          <Judul anak="Dan terbakar lagi. Dan lagi." ukuran={62} />

          <div style={{ marginTop: 40 }}>
            <Penghitung ke={s.angka as number} mulai={24} panjang={110} ukuran={168} />
            <div
              style={{
                fontFamily: tubuhFont,
                fontSize: 31,
                color: warna.kapur,
                marginTop: 16,
              }}
            >
              {s.satuan}
            </div>
            <div
              style={{
                fontFamily: tubuhFont,
                fontSize: 25,
                color: warna.abu,
                marginTop: 6,
              }}
            >
              {s.ket}
            </div>
          </div>

          {/* Eight marks, lighting one at a time: the same ground, burnt
              over and over across eleven seasons. */}
          <div style={{ display: "flex", gap: 18, marginTop: 56, alignItems: "flex-end" }}>
            {Array.from({ length: 8 }, (_, i) => {
              const t = masuk(frame, 150 + i * 20, 14);
              return (
                <div
                  key={i}
                  style={{
                    width: 112,
                    height: 112,
                    borderRadius: 3,
                    border: `2px solid ${warna.garis}`,
                    background: `rgba(255,90,31,${0.14 + 0.1 * i})`,
                    opacity: 0.18 + 0.82 * t,
                    transform: `scale(${0.9 + 0.1 * t})`,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    ...angkaGaya,
                    fontSize: 40,
                    fontWeight: 600,
                    color: warna.kapur,
                  }}
                >
                  {i + 1}
                </div>
              );
            })}
            <div
              style={{
                fontFamily: tubuhFont,
                fontSize: 26,
                color: warna.abu,
                maxWidth: 400,
                paddingLeft: 20,
                paddingBottom: 12,
                lineHeight: 1.35,
                opacity: masuk(frame, 300, 24),
              }}
            >
              kali terbakar di petak yang sama, 2015–2025
            </div>
          </div>
        </div>
      </Kolom>
      <Bingkai kiri="Kebakaran berulang" sumber={s.sumber} tampil={a} />
    </Lembut>
  );
};

/* ------------------------------------------------------------------ */
/* 08 — Penutup                                                         */
/* ------------------------------------------------------------------ */

export const AdeganTutup: React.FC<{ panjang: number }> = ({ panjang }) => {
  const frame = useCurrentFrame();
  const s = seg("08-tutup");
  const a = masuk(frame, 6, 24);
  const b = masuk(frame, 108, 30);
  return (
    <Lembut panjang={panjang}>
      <Rekaman kecepatan={0.45} mulaiDetik={10} redup={0.6} penuh />
      <Kolom jarak={26}>
        <h1
          style={{
            fontFamily: judulFont,
            fontWeight: 900,
            // Sized so "Satelitnya merekam tiap hari." holds one line.
            // At 104 it dropped "hari." onto a third line by itself, a
            // widow on the one sentence the film is built to deliver.
            fontSize: 94,
            lineHeight: 1.04,
            letterSpacing: "-0.03em",
            color: warna.kapur,
            margin: 0,
            maxWidth: 1660,
            opacity: a,
            transform: `translateY(${(1 - a) * 20}px)`,
          }}
        >
          Datanya terbuka. Satelitnya merekam tiap hari.
        </h1>
        <h2
          style={{
            fontFamily: judulFont,
            fontWeight: 900,
            fontSize: 70,
            lineHeight: 1.1,
            letterSpacing: "-0.02em",
            color: warna.bara,
            margin: 0,
            maxWidth: 1480,
            opacity: b,
            transform: `translateY(${(1 - b) * 20}px)`,
          }}
        >
          Yang belum ada hanya tanggapan yang sepadan.
        </h2>
      </Kolom>
      <Bingkai kiri="Karhutla Indonesia" sumber={s.sumber} tampil={a * 0.9} />
    </Lembut>
  );
};

/* ------------------------------------------------------------------ */
/* Kartu penutup: sumber, metode, batasan                               */
/* ------------------------------------------------------------------ */

export const KartuSumber: React.FC<{ panjang: number }> = ({ panjang }) => {
  const frame = useCurrentFrame();
  const a = masuk(frame, 4, 20);
  const baris: [string, string][] = [
    ["Titik panas sepekan", "NASA FIRMS VIIRS 375 m (SNPP, NOAA-20, NOAA-21), 6–12 Okt 2026"],
    ["Titik panas musim", "NASA FIRMS MODIS 1 km, jendela 1 Agt – 13 Okt, 2015–2026"],
    ["Bekas kebakaran", "MODIS MCD64A1 500 m, 11 musim 2015–2025"],
    ["Gambut", "3 peta: raster KLHK, OpenLandMap SOC, PEATGRIDS — karena itu rentang"],
    ["Asap", "CAMS aerosol optical depth via Open-Meteo"],
    ["Kawasan", "Kesatuan Hidrologis Gambut — 865 unit nasional"],
  ];
  return (
    <AbsoluteFill style={{ backgroundColor: warna.jelaga, opacity: a }}>
      <Kolom jarak={22}>
        <div
          style={{
            fontFamily: tubuhFont,
            fontSize: 23,
            fontWeight: 600,
            letterSpacing: "0.28em",
            textTransform: "uppercase",
            color: warna.bara,
          }}
        >
          Sumber data
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 13, width: 1560 }}>
          {baris.map(([k, v]) => (
            <div key={k} style={{ display: "flex", gap: 28, alignItems: "baseline" }}>
              <div
                style={{
                  width: 330,
                  fontFamily: tubuhFont,
                  fontSize: 25,
                  fontWeight: 600,
                  color: warna.kapur,
                }}
              >
                {k}
              </div>
              <div style={{ fontFamily: tubuhFont, fontSize: 25, color: warna.abu }}>
                {v}
              </div>
            </div>
          ))}
        </div>
        {/* The question this film invites and cannot answer, answered
            here rather than left for the viewer to wonder about: there is
            no hectare figure for the 2026 season because the burnt-area
            product does not reach it yet. */}
        <div
          style={{
            marginTop: 16,
            paddingTop: 20,
            borderTop: `2px solid ${warna.bara}`,
            fontFamily: tubuhFont,
            fontSize: 24,
            color: warna.kapur,
            lineHeight: 1.45,
            maxWidth: 1560,
          }}
        >
          <strong style={{ color: warna.bara }}>
            Mengapa tidak ada angka hektare untuk musim 2026?
          </strong>{" "}
          MCD64A1 baru terbit sampai Juli 2026 — tertinggal sekitar 100 hari —
          sehingga jendela 1 Agustus – 13 Oktober 2026 belum terukur sama
          sekali. Angka 2026 dalam film ini adalah titik panas, bukan hektare.
          Luas musim 2026 baru dapat dihitung sekitar Januari 2027.
        </div>

        <div
          style={{
            paddingTop: 16,
            fontFamily: tubuhFont,
            fontSize: 21,
            color: warna.abu,
            lineHeight: 1.5,
            maxWidth: 1560,
          }}
        >
          Titik panas adalah jumlah deteksi piksel, bukan luas terbakar.
          MCD64A1 beresolusi 500 m, sehingga kebakaran kecil tidak terdeteksi —
          angka luas di sini adalah batas bawah. Titik panas VIIRS dan MODIS
          berasal dari sensor berbeda dan tidak boleh dijumlahkan.
        </div>
      </Kolom>
    </AbsoluteFill>
  );
};
