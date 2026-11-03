import React from "react";
import { Composition } from "remotion";
import { FPS, LEBAR, TINGGI, TOTAL_FRAME } from "./jadwal";
import {
  FPS as FPS_B,
  LEBAR as LEBAR_B,
  TINGGI as TINGGI_B,
  TOTAL_FRAME as TOTAL_B,
} from "./jadwalBukti";
import {
  FPS as FPS_K,
  LEBAR as LEBAR_K,
  TINGGI as TINGGI_K,
  TOTAL_FRAME as TOTAL_K,
} from "./jadwalKonsesi";
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
    {/* Third piece: Kalimantan's 2026 burn against oil-palm concessions. */}
    <Composition
      id="Konsesi"
      component={Konsesi}
      durationInFrames={TOTAL_K}
      fps={FPS_K}
      width={LEBAR_K}
      height={TINGGI_K}
    />
  </>
);
