/**
 * "Buktinya" — the companion film: how we know the scars are real.
 *
 * The main film asserts hectares. This one shows the ground they were
 * measured on, and is honest about which instrument can say what:
 * PlanetScope has no SWIR, so it cannot produce a severity figure, and
 * every number spoken here that has a threshold in it comes from
 * Sentinel-2. That division is the film's argument, not a footnote.
 *
 * Shares teema.ts and komponen.tsx with the main film on purpose — two
 * companion pieces should look like one body of work.
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
import {
  adegan,
  akhirNarasi,
  JUDUL_FRAME,
  TUTUP_FRAME,
} from "./jadwalBukti";
import { Judul, Keterangan, Kolom, Lembut, masuk } from "./komponen";
import { angkaGaya, judulFont, koma, ribuan, tubuhFont, warna } from "./teema";
import D from "./buktiData.json";

const KM2 = D.lokasi.blok_km2;

/* -------- a satellite frame, drifting slowly so it is not a slide ------- */
const Citra: React.FC<{
  id: string;
  panjang: number;
  zoom?: number;
  redup?: number;
}> = ({ id, panjang, zoom = 1.06, redup = 0.25 }) => {
  const frame = useCurrentFrame();
  const s = interpolate(frame, [0, panjang], [1, zoom], {
    extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill style={{ backgroundColor: warna.jelaga, overflow: "hidden" }}>
      <Img
        src={staticFile(`bukti/${id}.jpg`)}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          transform: `scale(${s})`,
        }}
      />
      <AbsoluteFill
        style={{
          background: `linear-gradient(180deg, rgba(10,12,15,${0.55 + redup}) 0%, rgba(10,12,15,${redup}) 34%, rgba(10,12,15,${redup}) 58%, rgba(10,12,15,${0.78 + redup * 0.3}) 100%)`,
        }}
      />
    </AbsoluteFill>
  );
};

/** The standing date stamp on an image scene. */
const Cap: React.FC<{ tanggal: string; ket: string; awan: number; n: number }> =
  ({ tanggal, ket, awan, n }) => (
    <AbsoluteFill style={{ padding: "96px" }}>
      <div style={{ position: "absolute", left: 96, bottom: 88 }}>
        <div
          style={{
            fontFamily: judulFont,
            fontWeight: 900,
            fontSize: 92,
            lineHeight: 1,
            letterSpacing: "-0.03em",
            color: warna.kapur,
          }}
        >
          {tanggal}
        </div>
        <div
          style={{
            fontFamily: tubuhFont,
            fontSize: 30,
            color: warna.bara,
            marginTop: 12,
          }}
        >
          {ket}
        </div>
      </div>
      <div
        style={{
          position: "absolute",
          right: 96,
          bottom: 92,
          textAlign: "right",
          fontFamily: tubuhFont,
          fontSize: 21,
          lineHeight: 1.6,
          color: warna.abu,
        }}
      >
        PlanetScope 3 m · mosaik {n} strip, satu tanggal
        <br />
        {awan}% tertutup awan (UDM2)
      </div>
    </AbsoluteFill>
  );

/* ---------------------------------- scenes --------------------------- */

const KartuJudul: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 4, 24);
  return (
    <Lembut panjang={panjang}>
      <Citra id="29agt" panjang={panjang} zoom={1.1} redup={0.46} />
      <Kolom jarak={26}>
        <div style={{ opacity: a, transform: `translateY(${(1 - a) * 20}px)` }}>
          <div
            style={{
              fontFamily: tubuhFont,
              fontSize: 23,
              fontWeight: 600,
              letterSpacing: "0.3em",
              textTransform: "uppercase",
              color: warna.bara,
              marginBottom: 24,
            }}
          >
            Karhutla Indonesia · berkas pendamping
          </div>
          <h1
            style={{
              fontFamily: judulFont,
              fontWeight: 900,
              fontSize: 196,
              lineHeight: 0.88,
              letterSpacing: "-0.04em",
              color: warna.kapur,
              margin: 0,
            }}
          >
            BUKTINYA
          </h1>
          <div style={{ marginTop: 26 }}>
            <Keterangan anak="Tiga satelit, satu petak gambut di Kalimantan Tengah, dan pertanyaan paling sederhana: dari mana kita tahu tanah itu benar-benar terbakar?" />
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Angka: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 4, 22);
  const b = masuk(f, 46, 22);
  return (
    <Lembut panjang={panjang}>
      <AbsoluteFill style={{ backgroundColor: warna.jelaga }} />
      <Kolom jarak={16}>
        <h1
          style={{
            fontFamily: judulFont,
            fontWeight: 900,
            fontSize: 112,
            lineHeight: 1.02,
            letterSpacing: "-0.03em",
            color: warna.abu,
            margin: 0,
            opacity: a,
          }}
        >
          Angka bisa diperdebatkan.
        </h1>
        <h2
          style={{
            fontFamily: judulFont,
            fontWeight: 900,
            fontSize: 112,
            lineHeight: 1.02,
            letterSpacing: "-0.03em",
            color: warna.kapur,
            margin: 0,
            opacity: b,
            transform: `translateY(${(1 - b) * 18}px)`,
          }}
        >
          Citra satelit lebih sulit dibantah.
        </h2>
      </Kolom>
    </Lembut>
  );
};

const Petak: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 6, 22);
  return (
    <Lembut panjang={panjang}>
      <Citra id="21jul" panjang={panjang} zoom={1.08} redup={0.4} />
      <Kolom jarak={20}>
        <div style={{ opacity: a }}>
          <Judul anak="Satu petak, dua puluh kali dua puluh kilometer" ukuran={66} />
          <div
            style={{
              display: "flex",
              gap: 64,
              marginTop: 40,
              fontFamily: tubuhFont,
            }}
          >
            {[
              ["Lokasi", `${koma(Math.abs(D.lokasi.lat), 3)}°S  ${koma(D.lokasi.lon, 3)}°E`],
              ["Luas", `${ribuan(KM2)} km²`],
              ["Lahan", "Gambut terdrainase"],
            ].map(([k, v]) => (
              <div key={k}>
                <div
                  style={{
                    fontSize: 19,
                    letterSpacing: "0.22em",
                    textTransform: "uppercase",
                    color: warna.bara,
                    marginBottom: 10,
                  }}
                >
                  {k}
                </div>
                <div style={{ ...angkaGaya, fontSize: 36, color: warna.kapur }}>
                  {v}
                </div>
              </div>
            ))}
          </div>
          <div
            style={{
              marginTop: 34,
              borderLeft: `3px solid ${warna.bara}`,
              paddingLeft: 20,
              fontFamily: tubuhFont,
              fontSize: 27,
              color: warna.kapur,
              maxWidth: 1100,
              lineHeight: 1.4,
            }}
          >
            Garis-garis lurus itu kanal drainase — gambut yang dikeringkan
            terbakar jauh lebih mudah daripada gambut basah.
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Tanggal: React.FC<{ panjang: number; i: number }> = ({ panjang, i }) => {
  const c = D.citra[i];
  return (
    <Lembut panjang={panjang}>
      <Citra id={c.id} panjang={panjang} zoom={1.07} redup={0.16} />
      <Cap tanggal={c.tanggal} ket={c.ket} awan={c.awan} n={c.n} />
    </Lembut>
  );
};

const Keparahan: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const d = D.dnbr;
  const bar = [
    ["tinggi", d.tinggi_ha, warna.nyala],
    ["sedang-tinggi", 5121, warna.bara],
    ["sedang-rendah", 3750, "#B4541F"],
    ["rendah*", d.rendah_ha, "#5A4632"],
    ["tidak terbakar", d.tidak_terbakar_ha, "#14323C"],
  ] as [string, number, string][];
  return (
    <Lembut panjang={panjang}>
      {/* The severity map is high-chroma edge to edge, so it needs a
          heavier wash than a satellite frame before type sits on it. */}
      <Citra id="dnbr" panjang={panjang} zoom={1.05} redup={0.74} />
      <Kolom jarak={0}>
        <div style={{ opacity: a, width: 1500 }}>
          <div
            style={{
              fontFamily: tubuhFont,
              fontSize: 22,
              letterSpacing: "0.22em",
              textTransform: "uppercase",
              color: warna.bara,
              marginBottom: 16,
            }}
          >
            Sentinel-2 · dNBR · ambang USGS
          </div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 24 }}>
            <div
              style={{
                ...angkaGaya,
                fontSize: 168,
                fontWeight: 600,
                color: warna.nyala,
                lineHeight: 1,
              }}
            >
              {ribuan(interpolate(f, [16, 120], [0, d.sedang_plus_ha], {
                extrapolateLeft: "clamp", extrapolateRight: "clamp",
              }))}
            </div>
            <div style={{ fontFamily: tubuhFont, fontSize: 34, color: warna.kapur }}>
              hektare
            </div>
          </div>
          <div
            style={{
              fontFamily: tubuhFont,
              fontSize: 29,
              color: warna.kapur,
              marginTop: 10,
            }}
          >
            terbakar sedang ke atas — {koma(d.sedang_plus_pct)}% dari petak
          </div>

          <div style={{ display: "flex", marginTop: 40, height: 56, width: 1400 }}>
            {bar.map(([nama, ha, w], i) => {
              const t = masuk(f, 60 + i * 10, 26);
              return (
                <div
                  key={nama}
                  style={{
                    width: `${(ha / d.total_ha) * 100}%`,
                    background: w,
                    opacity: 0.25 + 0.75 * t,
                    borderRight: `2px solid ${warna.jelaga}`,
                  }}
                />
              );
            })}
          </div>
          <div
            style={{
              display: "flex",
              marginTop: 12,
              width: 1400,
              fontFamily: tubuhFont,
              fontSize: 17,
              color: warna.abu,
            }}
          >
            {bar.map(([nama, ha]) => (
              <div key={nama} style={{ width: `${(ha / d.total_ha) * 100}%` }}>
                {nama}
              </div>
            ))}
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const DuaSatelit: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  return (
    <Lembut panjang={panjang}>
      <AbsoluteFill style={{ backgroundColor: warna.jelaga }} />
      <Kolom jarak={0}>
        <div style={{ opacity: a, width: 1620 }}>
          <Judul anak="Dua satelit, dua tugas berbeda" ukuran={64} />
          <div style={{ display: "flex", gap: 60, marginTop: 46 }}>
            {D.sensor.map((s, i) => {
              const t = masuk(f, 30 + i * 22, 28);
              return (
                <div
                  key={s.nama}
                  style={{
                    flex: 1,
                    opacity: t,
                    transform: `translateY(${(1 - t) * 16}px)`,
                    borderTop: `3px solid ${s.bisa_dnbr ? warna.bara : warna.garis}`,
                    paddingTop: 22,
                  }}
                >
                  <div
                    style={{
                      fontFamily: judulFont,
                      fontWeight: 800,
                      fontSize: 52,
                      color: warna.kapur,
                    }}
                  >
                    {s.nama}
                  </div>
                  <div
                    style={{
                      ...angkaGaya,
                      fontSize: 30,
                      color: warna.nyala,
                      marginTop: 8,
                    }}
                  >
                    {s.res}
                  </div>
                  <div
                    style={{
                      fontFamily: tubuhFont,
                      fontSize: 25,
                      color: warna.abu,
                      marginTop: 18,
                      lineHeight: 1.45,
                    }}
                  >
                    {s.kanal}
                    <br />
                    {s.tugas}
                  </div>
                  <div
                    style={{
                      marginTop: 22,
                      fontFamily: tubuhFont,
                      fontSize: 25,
                      fontWeight: 600,
                      color: s.bisa_dnbr ? warna.bara : warna.samar,
                    }}
                  >
                    {s.bisa_dnbr ? "bisa mengukur dNBR" : "tidak bisa mengukur dNBR"}
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

const TanpaTepi: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const maks = Math.max(...D.cincin.map((c) => c.terbakar_ha));
  const TINGGI = 320;
  return (
    <Lembut panjang={panjang}>
      <AbsoluteFill style={{ backgroundColor: warna.jelaga }} />
      <Kolom jarak={0}>
        <div style={{ opacity: a, width: 1620 }}>
          <Judul anak="Petak ini bukan batas kebakarannya" ukuran={64} />
          <div
            style={{
              fontFamily: tubuhFont,
              fontSize: 26,
              color: warna.abu,
              marginTop: 12,
            }}
          >
            Luas terbakar (dNBR ≥ 0,27) saat kotak diperlebar dari pusat yang sama
          </div>
          <div
            style={{
              display: "flex",
              alignItems: "flex-end",
              gap: 46,
              marginTop: 46,
              height: TINGGI + 110,
            }}
          >
            {D.cincin.map((c, i) => {
              const t = masuk(f, 40 + i * 20, 32);
              const ini = c.sisi_km === 20;
              return (
                <div
                  key={c.sisi_km}
                  style={{
                    flex: 1,
                    height: TINGGI + 110,
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
                      fontSize: 28,
                      fontWeight: 600,
                      color: ini ? warna.nyala : warna.abu,
                      opacity: t,
                    }}
                  >
                    {ribuan(c.terbakar_ha * t)}
                  </div>
                  <div
                    style={{
                      width: "100%",
                      height: (c.terbakar_ha / maks) * TINGGI * t,
                      background: ini
                        ? `linear-gradient(180deg, ${warna.nyala} 0%, ${warna.bara} 100%)`
                        : warna.garis,
                      borderRadius: "3px 3px 0 0",
                    }}
                  />
                  <div
                    style={{
                      ...angkaGaya,
                      height: 34,
                      fontSize: 24,
                      fontWeight: ini ? 600 : 400,
                      color: ini ? warna.kapur : warna.abu,
                    }}
                  >
                    {c.sisi_km} km
                  </div>
                </div>
              );
            })}
          </div>
          <div
            style={{
              marginTop: 12,
              fontFamily: tubuhFont,
              fontSize: 27,
              color: warna.kapur,
              opacity: masuk(f, 330, 26),
            }}
          >
            Tidak pernah mendatar. Tidak ada tepi — yang ada hanya bingkai yang
            kita pilih sendiri.
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Tutup: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 6, 24);
  const b = masuk(f, 110, 28);
  return (
    <Lembut panjang={panjang}>
      <Citra id="29agt" panjang={panjang} zoom={1.09} redup={0.58} />
      <Kolom jarak={24}>
        <h1
          style={{
            fontFamily: judulFont,
            fontWeight: 900,
            fontSize: 92,
            lineHeight: 1.04,
            letterSpacing: "-0.03em",
            color: warna.kapur,
            margin: 0,
            maxWidth: 1600,
            opacity: a,
          }}
        >
          Tiga satelit berbeda merekam peristiwa yang sama.
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
            maxWidth: 1560,
            opacity: b,
            transform: `translateY(${(1 - b) * 18}px)`,
          }}
        >
          Yang diperdebatkan bukan lagi apakah ini terjadi.
        </h2>
      </Kolom>
    </Lembut>
  );
};

const KartuSumber: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 4, 20);
  const baris: [string, string][] = [
    ["Citra 3 m", "PlanetScope PSScene, 8 kanal surface reflectance, dipotong ke blok"],
    ["Tanggal", "21 Jul · 18 Agt · 29 Agt 2026 — tiap panel satu tanggal, tidak dicampur"],
    ["Keparahan", "Sentinel-2 B8/B12, komposit 1 Sep – 13 Okt, ambang USGS"],
    ["Awan", "UDM2 per strip (Planet) dan SCL (Sentinel-2)"],
    ["Titik panas", "NASA FIRMS — dipakai untuk memilih lokasi, bukan mengukurnya"],
  ];
  return (
    <AbsoluteFill style={{ backgroundColor: warna.jelaga, opacity: a }}>
      <Kolom jarak={20}>
        <div
          style={{
            fontFamily: tubuhFont,
            fontSize: 22,
            fontWeight: 600,
            letterSpacing: "0.28em",
            textTransform: "uppercase",
            color: warna.bara,
          }}
        >
          Sumber data
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 13, width: 1620 }}>
          {baris.map(([k, v]) => (
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
              <div style={{ fontFamily: tubuhFont, fontSize: 25, color: warna.abu }}>
                {v}
              </div>
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
          PlanetScope tidak memiliki kanal SWIR, sehingga dNBR tidak dapat
          dihitung darinya. Semua angka keparahan di film ini berasal dari
          Sentinel-2. *Kelas rendah (dNBR 0,10–0,27) tidak diklaim terbakar:
          di gambut yang mengering NBR turun tanpa api.
        </div>
      </Kolom>
    </AbsoluteFill>
  );
};

/* --------------------------------- film ------------------------------ */

const PETA: Record<string, React.FC<{ panjang: number }>> = {
  "01-angka": Angka,
  "02-petak": Petak,
  "03-21jul": (p) => <Tanggal {...p} i={0} />,
  "04-18agt": (p) => <Tanggal {...p} i={1} />,
  "05-29agt": (p) => <Tanggal {...p} i={2} />,
  "06-keparahan": Keparahan,
  "07-dua-satelit": DuaSatelit,
  "08-tanpa-tepi": TanpaTepi,
  "09-tutup": Tutup,
};

export const Bukti: React.FC = () => (
  <AbsoluteFill style={{ backgroundColor: warna.jelaga }}>
    {/* Bed already carries its automation, as in the main film. */}
    <Audio src={staticFile("audio/bukti/musik-bukti.mp3")} />

    <Sequence durationInFrames={JUDUL_FRAME}>
      <KartuJudul panjang={JUDUL_FRAME} />
    </Sequence>

    {adegan.map((a) => {
      const K = PETA[a.id as string];
      return (
        <Sequence key={a.id} from={a.mulai} durationInFrames={a.panjang}>
          <K panjang={a.panjang} />
          <Audio src={staticFile(`audio/bukti/${a.id}.mp3`)} />
        </Sequence>
      );
    })}

    <Sequence from={akhirNarasi} durationInFrames={TUTUP_FRAME}>
      <KartuSumber panjang={TUTUP_FRAME} />
    </Sequence>
  </AbsoluteFill>
);
