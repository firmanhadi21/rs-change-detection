/**
 * Cut of 'Memeriksa Peta Tambang Nikel', built as jadwalHutan.ts builds the forest film's:
 * durations are ffprobe measurements written by tts_konsesi.py --film periksa.
 */

import id from "./jadwalPeriksa.json";
import type { Jadwal } from "./jadwalKonsesi";

const FPS = id.fps;
const durasi = id.durasi as Record<string, number>;
const JUDUL_FRAME = Math.round(id.judul_detik * FPS);
const TUTUP_FRAME = Math.round(id.tutup_detik * FPS);
let kursor = JUDUL_FRAME;
const adegan = (id.urutan as string[]).map((nama) => {
  if (!(nama in durasi)) {
    throw new Error(`durasi ${nama} belum diukur — jalankan tts_konsesi.py --film periksa`);
  }
  const panjang = Math.ceil(durasi[nama] * FPS) + Math.round(id.jeda_detik * FPS);
  const a = { id: nama, mulai: kursor, panjang };
  kursor += panjang;
  return a;
});
const akhirNarasi = kursor;

export const JADWAL_PERIKSA: Jadwal = {
  FPS,
  LEBAR: id.lebar,
  TINGGI: id.tinggi,
  JUDUL_FRAME,
  TUTUP_FRAME,
  adegan,
  akhirNarasi,
  TOTAL_FRAME: akhirNarasi + TUTUP_FRAME,
};
