/**
 * The concessions film's cut, built the same way as the other two.
 *
 * Durations are ffprobe measurements of the normalised mp3s, written by
 * tts_konsesi.py, and bake_musik_bukti.py --jadwal src/jadwalKonsesi.json
 * reads the same JSON, so the bed cannot drift from the scenes.
 */

import data from "./jadwalKonsesi.json";

export const FPS = data.fps;
export const LEBAR = data.lebar;
export const TINGGI = data.tinggi;

export const durasi = data.durasi as Record<string, number>;
export type IdKonsesi = keyof typeof data.durasi;

const URUTAN = data.urutan as IdKonsesi[];

export const JUDUL_FRAME = Math.round(data.judul_detik * FPS);
export const TUTUP_FRAME = Math.round(data.tutup_detik * FPS);

export type Adegan = { id: IdKonsesi; mulai: number; panjang: number };

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
