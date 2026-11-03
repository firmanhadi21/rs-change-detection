/**
 * The concessions film's cut, one per language, built the same way as the
 * other two films.
 *
 * Durations are ffprobe measurements of the normalised mp3s, written by
 * tts_konsesi.py [--bahasa en], and bake_musik_bukti.py --jadwal <json>
 * reads the same JSON, so the bed cannot drift from the scenes. The two
 * languages share scene ids and order; only the lengths differ.
 */

import id from "./jadwalKonsesi.json";
import en from "./jadwalKonsesiEN.json";

export type Bahasa = "id" | "en";

type Data = typeof id;

export type Adegan = { id: string; mulai: number; panjang: number };

export type Jadwal = {
  FPS: number;
  LEBAR: number;
  TINGGI: number;
  JUDUL_FRAME: number;
  TUTUP_FRAME: number;
  adegan: Adegan[];
  akhirNarasi: number;
  TOTAL_FRAME: number;
};

const buat = (data: Data): Jadwal => {
  const FPS = data.fps;
  const durasi = data.durasi as Record<string, number>;
  const JUDUL_FRAME = Math.round(data.judul_detik * FPS);
  const TUTUP_FRAME = Math.round(data.tutup_detik * FPS);
  let kursor = JUDUL_FRAME;
  const adegan = (data.urutan as string[]).map((nama) => {
    if (!(nama in durasi)) {
      throw new Error(`durasi ${nama} belum diukur — jalankan tts_konsesi.py`);
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

export const JADWAL: Record<Bahasa, Jadwal> = {
  id: buat(id),
  en: buat(en as Data),
};
