/**
 * The companion film's cut, built the same way as the main one.
 *
 * Separate schedule, shared mechanism: durations are ffprobe measurements
 * of the normalised mp3s, and bake_musik_bukti.py reads the same JSON, so
 * the bed cannot drift from the scenes.
 */

import data from "./jadwalBukti.json";

export const FPS = data.fps;
export const LEBAR = data.lebar;
export const TINGGI = data.tinggi;

export const durasi = data.durasi as Record<string, number>;
export type IdBukti = keyof typeof data.durasi;

const URUTAN = data.urutan as IdBukti[];

export const JUDUL_FRAME = Math.round(data.judul_detik * FPS);
export const TUTUP_FRAME = Math.round(data.tutup_detik * FPS);

export type Adegan = { id: IdBukti; mulai: number; panjang: number };

export const adegan: Adegan[] = (() => {
  let kursor = JUDUL_FRAME;
  return URUTAN.map((id) => {
    const panjang =
      Math.ceil(durasi[id] * FPS) + Math.round(data.jeda_detik * FPS);
    const a: Adegan = { id, mulai: kursor, panjang };
    kursor += panjang;
    return a;
  });
})();

const akhir = adegan[adegan.length - 1];
export const akhirNarasi = akhir.mulai + akhir.panjang;
export const TOTAL_FRAME = akhirNarasi + TUTUP_FRAME;
