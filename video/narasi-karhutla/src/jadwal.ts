/**
 * The cut, derived from the narration rather than guessed.
 *
 * Each scene lasts exactly as long as the line Bian speaks over it, plus a
 * beat of silence before the next one. The durations live in jadwal.json
 * and are ffprobe measurements of the downloaded mp3s, not figures read off
 * the API -- the edit is cut to them. bake_musik.py reads that same file,
 * so the music's duck cannot drift away from the scenes it ducks under.
 */

import data from "./jadwal.json";

export const FPS = data.fps;
export const LEBAR = data.lebar;
export const TINGGI = data.tinggi;

export const durasi = data.durasi as Record<string, number>;
export type IdAdegan = keyof typeof data.durasi;

const URUTAN = data.urutan as IdAdegan[];

/** Title card before the first word, end card after the last. */
export const JUDUL_FRAME = Math.round(data.judul_detik * FPS);
export const TUTUP_FRAME = Math.round(data.tutup_detik * FPS);

export type Adegan = {
  id: IdAdegan;
  mulai: number; // first frame of the scene
  panjang: number; // scene length including the trailing beat
  suaraPanjang: number; // frames of actual speech
};

export const adegan: Adegan[] = (() => {
  let kursor = JUDUL_FRAME;
  return URUTAN.map((id) => {
    const suaraPanjang = Math.ceil(durasi[id] * FPS);
    const panjang = suaraPanjang + Math.round(data.jeda_detik * FPS);
    const a: Adegan = { id, mulai: kursor, panjang, suaraPanjang };
    kursor += panjang;
    return a;
  });
})();

const terakhir = adegan[adegan.length - 1];
export const akhirNarasi = terakhir.mulai + terakhir.panjang;
export const TOTAL_FRAME = akhirNarasi + TUTUP_FRAME;
