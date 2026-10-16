/**
 * The whole film: a title card, eight narrated scenes, a sources card.
 *
 * The cut is driven entirely by src/jadwal.ts, which is built from the
 * measured length of each narration mp3 -- so changing a line of narration
 * and re-measuring re-cuts the film, rather than requiring every scene to
 * be nudged by hand.
 */

import React from "react";
import { AbsoluteFill, Audio, Sequence, staticFile } from "remotion";
import {
  adegan,
  akhirNarasi,
  JUDUL_FRAME,
  TUTUP_FRAME,
} from "./jadwal";
import {
  AdeganBerulang,
  AdeganBuka,
  AdeganGambut,
  AdeganKhg,
  AdeganPulau,
  AdeganRekor,
  AdeganSepekan,
  AdeganTutup,
  KartuJudul,
  KartuSumber,
} from "./adegan";
import { warna } from "./teema";

const PETA = {
  "01-buka": AdeganBuka,
  "02-sepekan": AdeganSepekan,
  "03-pulau": AdeganPulau,
  "04-rekor": AdeganRekor,
  "05-gambut": AdeganGambut,
  "06-khg": AdeganKhg,
  "07-berulang": AdeganBerulang,
  "08-tutup": AdeganTutup,
} as const;

export const Narasi: React.FC = () => (
  <AbsoluteFill style={{ backgroundColor: warna.jelaga }}>
    {/*
      The bed plays flat, because all of its automation is already in the
      file. bake_musik.py stretches it over the film, lifts it for the two
      cards, ducks it under the narration and fades both ends.

      It was a per-frame volume function here first. Remotion compiles one
      of those into a single ffmpeg `volume` expression with a clause per
      distinct value, and over 134 seconds of fades that expression grew
      past what ffmpeg's parser accepts. The render failed, and failed
      quietly enough to leave a stale mp4 looking like a finished one.
    */}
    <Audio src={staticFile("audio/musik-mix.mp3")} />

    <Sequence durationInFrames={JUDUL_FRAME}>
      <KartuJudul panjang={JUDUL_FRAME} />
    </Sequence>

    {adegan.map((a) => {
      const Komponen = PETA[a.id];
      return (
        <Sequence key={a.id} from={a.mulai} durationInFrames={a.panjang}>
          <Komponen panjang={a.panjang} />
          <Audio src={staticFile(`audio/${a.id}.mp3`)} volume={1} />
        </Sequence>
      );
    })}

    <Sequence from={akhirNarasi} durationInFrames={TUTUP_FRAME}>
      <KartuSumber panjang={TUTUP_FRAME} />
    </Sequence>
  </AbsoluteFill>
);
