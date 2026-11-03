import React from "react";
import { Composition } from "remotion";
import { FPS, LEBAR, TINGGI, TOTAL_FRAME } from "./jadwal";
import {
  FPS as FPS_B,
  LEBAR as LEBAR_B,
  TINGGI as TINGGI_B,
  TOTAL_FRAME as TOTAL_B,
} from "./jadwalBukti";
import { JADWAL } from "./jadwalKonsesi";
import { Narasi } from "./Narasi";
import { Bukti } from "./Bukti";
import { Konsesi } from "./Konsesi";

export const RemotionRoot: React.FC = () => (
  <>
    <Composition
      id="Narasi"
      component={Narasi}
      durationInFrames={TOTAL_FRAME}
      fps={FPS}
      width={LEBAR}
      height={TINGGI}
    />
    {/* Companion piece: the satellite evidence behind the main film's
        hectare claims. Shares palette, type and audio pipeline. */}
    <Composition
      id="Bukti"
      component={Bukti}
      durationInFrames={TOTAL_B}
      fps={FPS_B}
      width={LEBAR_B}
      height={TINGGI_B}
    />
    {/* Third piece: Kalimantan's 2026 burn against oil-palm concessions,
        in Indonesian and English. Same component, own cut per language. */}
    <Composition
      id="Konsesi"
      component={Konsesi}
      defaultProps={{ bahasa: "id" as const }}
      durationInFrames={JADWAL.id.TOTAL_FRAME}
      fps={JADWAL.id.FPS}
      width={JADWAL.id.LEBAR}
      height={JADWAL.id.TINGGI}
    />
    <Composition
      id="KonsesiEN"
      component={Konsesi}
      defaultProps={{ bahasa: "en" as const }}
      durationInFrames={JADWAL.en.TOTAL_FRAME}
      fps={JADWAL.en.FPS}
      width={JADWAL.en.LEBAR}
      height={JADWAL.en.TINGGI}
    />
  </>
);
