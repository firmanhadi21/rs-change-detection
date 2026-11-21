/**
 * The Kalimantan fire film's cut, built as jadwalHutan.ts builds its own: durations are ffprobe
 * measurements written by tts_konsesi.py --film api [--bahasa en].
 */

import id from "./jadwalApi.json";
import en from "./jadwalApiEN.json";
import type { Bahasa, Jadwal } from "./jadwalKonsesi";

type Data = typeof id;

const buat = (data: Data): Jadwal => {
  const FPS = data.fps;
  const durasi = data.durasi as Record<string, number>;
  const JUDUL_FRAME = Math.round(data.judul_detik * FPS);
  const TUTUP_FRAME = Math.round(data.tutup_detik * FPS);
  let kursor = JUDUL_FRAME;
  const adegan = (data.urutan as string[]).map((nama) => {
    if (!(nama in durasi)) {
      throw new Error(`durasi ${nama} belum diukur — jalankan tts_konsesi.py --film api`);
    }
    const panjang = Math.ceil(durasi[nama] * FPS) + Math.round(data.jeda_detik * FPS);
    const a = { id: nama, mulai: kursor, panjang };
    kursor += panjang;
    return a;
  });
  const akhir = adegan[adegan.length - 1];
  const akhirNarasi = akhir.mulai + akhir.panjang;
  return { FPS, LEBAR: data.lebar, TINGGI: data.tinggi, JUDUL_FRAME, TUTUP_FRAME, adegan, akhirNarasi, TOTAL_FRAME: akhirNarasi + TUTUP_FRAME };
};

export const JADWAL_API: Record<Bahasa, Jadwal> = {
  id: buat(id),
  en: buat(en as unknown as Data),
};
