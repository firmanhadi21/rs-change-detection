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
import { Telusur } from "./Telusur";
import { JADWAL_TELUSUR } from "./jadwalTelusur";
import { RadarFilm } from "./Radar";
import { JADWAL_RADAR } from "./jadwalRadar";
import { PulauFilm } from "./Pulau";
import { JADWAL_PULAU } from "./jadwalPulau";

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
    {/* Fourth piece: Part 2 of the concessions film -- why the four Ketapang
        concessions burned worse (ignitions, land use, drought, peat). */}
    <Composition
      id="Telusur"
      component={Telusur}
      defaultProps={{ bahasa: "id" as const }}
      durationInFrames={JADWAL_TELUSUR.id.TOTAL_FRAME}
      fps={JADWAL_TELUSUR.id.FPS}
      width={JADWAL_TELUSUR.id.LEBAR}
      height={JADWAL_TELUSUR.id.TINGGI}
    />
    <Composition
      id="TelusurEN"
      component={Telusur}
      defaultProps={{ bahasa: "en" as const }}
      durationInFrames={JADWAL_TELUSUR.en.TOTAL_FRAME}
      fps={JADWAL_TELUSUR.en.FPS}
      width={JADWAL_TELUSUR.en.LEBAR}
      height={JADWAL_TELUSUR.en.TINGGI}
    />
    {/* Fifth piece: Part 3 -- the fire through the season, VIIRS as the
        clock and NISAR L-band radar as the check under the smoke. */}
    <Composition
      id="Radar"
      component={RadarFilm}
      defaultProps={{ bahasa: "id" as const }}
      durationInFrames={JADWAL_RADAR.id.TOTAL_FRAME}
      fps={JADWAL_RADAR.id.FPS}
      width={JADWAL_RADAR.id.LEBAR}
      height={JADWAL_RADAR.id.TINGGI}
    />
    <Composition
      id="RadarEN"
      component={RadarFilm}
      defaultProps={{ bahasa: "en" as const }}
      durationInFrames={JADWAL_RADAR.en.TOTAL_FRAME}
      fps={JADWAL_RADAR.en.FPS}
      width={JADWAL_RADAR.en.LEBAR}
      height={JADWAL_RADAR.en.TINGGI}
    />
    {/* Sixth piece: Part 4 -- "Benarkah Sawit Membakar Kalimantan?", the
        Kalimantan-wide results. Indonesian only so far. */}
    <Composition
      id="Pulau"
      component={PulauFilm}
      durationInFrames={JADWAL_PULAU.id!.TOTAL_FRAME}
      fps={JADWAL_PULAU.id!.FPS}
      width={JADWAL_PULAU.id!.LEBAR}
      height={JADWAL_PULAU.id!.TINGGI}
    />
  </>
);
