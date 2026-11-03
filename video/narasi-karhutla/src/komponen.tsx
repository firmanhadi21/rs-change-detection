/**
 * The pieces every scene shares: the ground it sits on, the counter, and
 * the source line.
 *
 * The source line is not decoration. Two different sensors appear in this
 * film -- VIIRS at 375 m for the one-week national counts, MODIS at 1 km
 * and MCD64A1 at 500 m for the season and the burn scars -- and their
 * numbers must never be added together. Burning the sensor into every
 * frame is what stops a viewer doing that.
 */

import React from "react";
import {
  AbsoluteFill,
  Easing,
  Img,
  interpolate,
  OffthreadVideo,
  staticFile,
  useCurrentFrame,
} from "remotion";
import { angkaGaya, judulFont, ribuan, tubuhFont, warna } from "./teema";

/** Ease that starts fast and settles, for counters and bars. */
const mulus = Easing.bezier(0.16, 1, 0.3, 1);

export const masuk = (frame: number, mulai = 0, panjang = 18) =>
  interpolate(frame, [mulai, mulai + panjang], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: mulus,
  });

/** Fade the whole scene in and out so cuts never flash. */
export const Lembut: React.FC<{
  panjang: number;
  children: React.ReactNode;
}> = ({ panjang, children }) => {
  const frame = useCurrentFrame();
  const o = interpolate(
    frame,
    [0, 12, panjang - 12, panjang],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );
  return <AbsoluteFill style={{ opacity: o }}>{children}</AbsoluteFill>;
};

/**
 * The smoke animation itself, as the film's ground.
 *
 * It is 2880x1108 -- 2.6:1 -- and it is the evidence, so it is never
 * cropped to fill a 16:9 frame. It sits as a full-width band and the rest
 * of the frame stays soot.
 */
export const Rekaman: React.FC<{
  kecepatan?: number;
  mulaiDetik?: number;
  redup?: number;
  kabur?: number;
  penuh?: boolean;
}> = ({ kecepatan = 0.6, mulaiDetik = 0, redup = 0.5, kabur = 0, penuh = false }) => (
  <AbsoluteFill style={{ backgroundColor: warna.jelaga }}>
    <AbsoluteFill
      style={{
        alignItems: "center",
        justifyContent: "center",
        filter: kabur ? `blur(${kabur}px)` : undefined,
      }}
    >
      <OffthreadVideo
        src={staticFile("asap.mp4")}
        playbackRate={kecepatan}
        startFrom={Math.round(mulaiDetik * 24)}
        muted
        style={{
          width: penuh ? "132%" : "100%",
          height: "auto",
          opacity: 1 - redup,
        }}
      />
    </AbsoluteFill>
    {/*
      Soot wash, and a deliberate one.

      The smoke animation carries its own furniture -- a title block across
      the top, a scale bar and an attribution along the bottom -- which
      would otherwise sit underneath this film's own title and source line,
      two sets of captions fighting in the same corner. The opaque bands
      below are sized to swallow exactly those strips, so the map body and
      its full 47 degrees of longitude survive while the duplicate
      furniture does not. The middle stays only lightly washed, because
      that is where the evidence is.
    */}
    <AbsoluteFill
      style={{
        background: `linear-gradient(180deg,
          ${warna.jelaga} 0%,
          ${warna.jelaga} 17%,
          rgba(10,12,15,0.30) 28%,
          rgba(10,12,15,0.30) 70%,
          ${warna.jelaga} 88%,
          ${warna.jelaga} 100%)`,
      }}
    />
  </AbsoluteFill>
);

/** A still from the same footage, blurred to near-texture, for chart scenes. */
export const LatarDiam: React.FC = () => (
  <AbsoluteFill style={{ backgroundColor: warna.jelaga }}>
    <Img
      src={staticFile("latar.png")}
      style={{
        width: "116%",
        height: "116%",
        objectFit: "cover",
        opacity: 0.17,
        filter: "blur(26px) saturate(1.3)",
        transform: "translate(-7%, -7%)",
      }}
    />
    <AbsoluteFill
      style={{
        background: `radial-gradient(120% 90% at 18% 10%, rgba(255,90,31,0.07) 0%, rgba(10,12,15,0) 55%), linear-gradient(180deg, rgba(10,12,15,0.55) 0%, rgba(10,12,15,0.88) 100%)`,
      }}
    />
  </AbsoluteFill>
);

/** Standing furniture: the hairline, the eyebrow, the source credit. */
export const Bingkai: React.FC<{
  kiri?: string;
  sumber?: string;
  tampil?: number;
  waktu?: string;
  labelSumber?: string;
}> = ({
  kiri,
  sumber,
  tampil = 1,
  waktu = "Oktober 2026",
  labelSumber = "Sumber",
}) => (
  <AbsoluteFill style={{ opacity: tampil }}>
    <div
      style={{
        position: "absolute",
        left: 96,
        right: 96,
        top: 72,
        display: "flex",
        justifyContent: "space-between",
        alignItems: "baseline",
        borderTop: `2px solid ${warna.bara}`,
        paddingTop: 18,
      }}
    >
      <span
        style={{
          fontFamily: tubuhFont,
          fontSize: 21,
          fontWeight: 600,
          letterSpacing: "0.22em",
          textTransform: "uppercase",
          color: warna.bara,
        }}
      >
        {kiri ?? "Karhutla Indonesia"}
      </span>
      <span
        style={{
          fontFamily: tubuhFont,
          fontSize: 19,
          letterSpacing: "0.18em",
          textTransform: "uppercase",
          color: warna.abu,
        }}
      >
        {waktu}
      </span>
    </div>
    {sumber ? (
      <div
        style={{
          position: "absolute",
          left: 96,
          right: 96,
          bottom: 56,
          borderTop: `1px solid ${warna.garis}`,
          paddingTop: 14,
          fontFamily: tubuhFont,
          fontSize: 20,
          lineHeight: 1.35,
          color: warna.abu,
        }}
      >
        <span style={{ color: warna.garis, marginRight: 12 }}>{labelSumber}</span>
        {sumber}
      </div>
    ) : null}
  </AbsoluteFill>
);

/** A figure that counts up, then holds. Digits are tabular so it cannot jitter. */
export const Penghitung: React.FC<{
  ke: number;
  mulai?: number;
  panjang?: number;
  ukuran?: number;
  warnaAngka?: string;
  lokal?: string;
}> = ({
  ke,
  mulai = 0,
  panjang = 48,
  ukuran = 190,
  warnaAngka = warna.nyala,
  lokal = "id-ID",
}) => {
  const frame = useCurrentFrame();
  const nilai = interpolate(frame, [mulai, mulai + panjang], [0, ke], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: mulus,
  });
  return (
    <div
      style={{
        ...angkaGaya,
        fontSize: ukuran,
        fontWeight: 600,
        lineHeight: 0.95,
        color: warnaAngka,
        letterSpacing: "-0.02em",
      }}
    >
      {ribuan(nilai, lokal)}
    </div>
  );
};

export const Judul: React.FC<{
  anak: string;
  ukuran?: number;
  warnaTeks?: string;
}> = ({ anak, ukuran = 76, warnaTeks = warna.kapur }) => (
  <h1
    style={{
      fontFamily: judulFont,
      fontWeight: 800,
      fontSize: ukuran,
      lineHeight: 1.03,
      letterSpacing: "-0.02em",
      color: warnaTeks,
      margin: 0,
      textWrap: "balance",
      maxWidth: 1180,
    }}
  >
    {anak}
  </h1>
);

export const Keterangan: React.FC<{ anak: string; lebar?: number }> = ({
  anak,
  lebar = 980,
}) => (
  <p
    style={{
      fontFamily: tubuhFont,
      fontSize: 30,
      lineHeight: 1.45,
      color: warna.abu,
      margin: 0,
      maxWidth: lebar,
    }}
  >
    {anak}
  </p>
);

/** The scene's content column: one grid, one gap, no stacked margins. */
export const Kolom: React.FC<{
  children: React.ReactNode;
  jarak?: number;
  bawah?: boolean;
}> = ({ children, jarak = 26, bawah = false }) => (
  <AbsoluteFill
    style={{
      display: "flex",
      flexDirection: "column",
      justifyContent: bawah ? "flex-end" : "center",
      alignItems: "flex-start",
      gap: jarak,
      padding: "150px 96px 150px",
    }}
  >
    {children}
  </AbsoluteFill>
);
