/**
 * Part 3's cut, one per language, built exactly as jadwalKonsesi.ts builds
 * Part 1's: durations are ffprobe measurements written by
 * tts_konsesi.py --film radar [--bahasa en], and bake_musik_bukti.py
 * --jadwal <json> reads the same JSON. Both languages share scene ids.
 */

import id from "./jadwalRadar.json";
import en from "./jadwalRadarEN.json";
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
      throw new Error(`durasi ${nama} belum diukur — jalankan tts_konsesi.py --film radar`);
    }
    const panjang =
      Math.ceil(durasi[nama] * FPS) + Math.round(data.jeda_detik * FPS);
    const a = { id: nama, mulai: kursor, panjang };
    kursor += panjang;
    return a;
  });
  const akhir = adegan[adegan.length - 1];
  const akhirNarasi = akhir.mulai + akhir.panjang;
  return {
    FPS,
    LEBAR: data.lebar,
    TINGGI: data.tinggi,
    JUDUL_FRAME,
    TUTUP_FRAME,
    adegan,
    akhirNarasi,
    TOTAL_FRAME: akhirNarasi + TUTUP_FRAME,
  };
};

export const JADWAL_RADAR: Record<Bahasa, Jadwal> = {
  id: buat(id),
  en: buat(en as unknown as Data),
};
