import React from "react";
import { Composition, Still } from "remotion";
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
import { HutanFilm, Infografis } from "./Hutan";
import { JADWAL_HUTAN } from "./jadwalHutan";
import { PeriksaFilm } from "./Periksa";
import { JADWAL_PERIKSA } from "./jadwalPeriksa";
import { InfografisTambang, TambangFilm } from "./Tambang";
import { JADWAL_TAMBANG } from "./jadwalTambang";
import { AirFilm, InfografisAir } from "./Air";
import { JADWAL_AIR } from "./jadwalAir";
import { BiayaFilm, InfografisBiaya } from "./Biaya";
import { JADWAL_BIAYA } from "./jadwalBiaya";
import { InfografisUang, UangFilm } from "./Uang";
import { JADWAL_UANG } from "./jadwalUang";
import { ApiFilm, InfografisApi } from "./Api";
import { InfografisSawit } from "./Sawit";
import { JADWAL_API } from "./jadwalApi";

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
    {/* Sixth piece: a standalone film -- "Benarkah Sawit Membakar Kalimantan?", the
        Kalimantan-wide results. */}
    <Composition
      id="Pulau"
      component={PulauFilm}
      defaultProps={{ bahasa: "id" as const }}
      durationInFrames={JADWAL_PULAU.id.TOTAL_FRAME}
      fps={JADWAL_PULAU.id.FPS}
      width={JADWAL_PULAU.id.LEBAR}
      height={JADWAL_PULAU.id.TINGGI}
    />
    <Composition
      id="PulauEN"
      component={PulauFilm}
      defaultProps={{ bahasa: "en" as const }}
      durationInFrames={JADWAL_PULAU.en.TOTAL_FRAME}
      fps={JADWAL_PULAU.en.FPS}
      width={JADWAL_PULAU.en.LEBAR}
      height={JADWAL_PULAU.en.TINGGI}
    />
    {/* Seventh piece: a standalone film on North Maluku's forests and nickel mining,
        plus its infographic still. */}
    <Composition
      id="Hutan"
      component={HutanFilm}
      defaultProps={{ bahasa: "id" as const }}
      durationInFrames={JADWAL_HUTAN.id.TOTAL_FRAME}
      fps={JADWAL_HUTAN.id.FPS}
      width={JADWAL_HUTAN.id.LEBAR}
      height={JADWAL_HUTAN.id.TINGGI}
    />
    <Composition
      id="HutanEN"
      component={HutanFilm}
      defaultProps={{ bahasa: "en" as const }}
      durationInFrames={JADWAL_HUTAN.en.TOTAL_FRAME}
      fps={JADWAL_HUTAN.en.FPS}
      width={JADWAL_HUTAN.en.LEBAR}
      height={JADWAL_HUTAN.en.TINGGI}
    />
    {/* Eighth piece: checking the Weda Bay / Sagea mining maps against hand labels (Indonesian). */}
    <Composition
      id="Periksa"
      component={PeriksaFilm}
      durationInFrames={JADWAL_PERIKSA.TOTAL_FRAME}
      fps={JADWAL_PERIKSA.FPS}
      width={JADWAL_PERIKSA.LEBAR}
      height={JADWAL_PERIKSA.TINGGI}
    />
    {/* Ninth piece: mining footprint across North Maluku, label-adjusted (Indonesian), plus two infographic pages. */}
    <Composition
      id="Tambang"
      component={TambangFilm}
      durationInFrames={JADWAL_TAMBANG.TOTAL_FRAME}
      fps={JADWAL_TAMBANG.FPS}
      width={JADWAL_TAMBANG.LEBAR}
      height={JADWAL_TAMBANG.TINGGI}
    />
    {([1, 2] as const).map((h) => (
      <Still key={`tambang${h}`} id={`InfografisTambang${h}`} component={InfografisTambang} defaultProps={{ halaman: h }} width={1080} height={1350} />
    ))}
    {/* Tenth piece: part 4 of the North Maluku series, mining and turbidity in Weda Bay and Sagea Lake (Indonesian). */}
    <Composition
      id="Air"
      component={AirFilm}
      durationInFrames={JADWAL_AIR.TOTAL_FRAME}
      fps={JADWAL_AIR.FPS}
      width={JADWAL_AIR.LEBAR}
      height={JADWAL_AIR.TINGGI}
    />
    {([1, 2] as const).map((h) => (
      <Still key={`air${h}`} id={`InfografisAir${h}`} component={InfografisAir} defaultProps={{ halaman: h }} width={1080} height={1350} />
    ))}
    {/* Eleventh piece: part 5 of the North Maluku series, economic value vs environmental costs (Indonesian). */}
    <Composition
      id="Biaya"
      component={BiayaFilm}
      durationInFrames={JADWAL_BIAYA.TOTAL_FRAME}
      fps={JADWAL_BIAYA.FPS}
      width={JADWAL_BIAYA.LEBAR}
      height={JADWAL_BIAYA.TINGGI}
    />
    {([1, 2] as const).map((h) => (
      <Still key={`biaya${h}`} id={`InfografisBiaya${h}`} component={InfografisBiaya} defaultProps={{ halaman: h }} width={1080} height={1350} />
    ))}
    {/* Twelfth piece: part 6 of the North Maluku series, where the nickel money goes (Indonesian). */}
    <Composition
      id="Uang"
      component={UangFilm}
      durationInFrames={JADWAL_UANG.TOTAL_FRAME}
      fps={JADWAL_UANG.FPS}
      width={JADWAL_UANG.LEBAR}
      height={JADWAL_UANG.TINGGI}
    />
    {([1, 2] as const).map((h) => (
      <Still key={`uang${h}`} id={`InfografisUang${h}`} component={InfografisUang} defaultProps={{ halaman: h }} width={1080} height={1350} />
    ))}
    {/* Thirteenth piece: Kalimantan fire 2001-2027 -- carbon, drivers, oil palm, swidden, the 2027 forecast,
        in Indonesian (Bian) and English (Max), plus two infographic pages per language. */}
    {(["id", "en"] as const).map((b) => (
      <Composition
        key={`api${b}`}
        id={b === "en" ? "ApiEN" : "Api"}
        component={ApiFilm}
        defaultProps={{ bahasa: b }}
        durationInFrames={JADWAL_API[b].TOTAL_FRAME}
        fps={JADWAL_API[b].FPS}
        width={JADWAL_API[b].LEBAR}
        height={JADWAL_API[b].TINGGI}
      />
    ))}
    {(["id", "en"] as const).map((b) => (
      <Still key={`sawit${b}`} id={`InfografisSawit${b === "en" ? "EN" : ""}`} component={InfografisSawit} defaultProps={{ bahasa: b }} width={1080} height={1350} />
    ))}
    {(["id", "en"] as const).flatMap((b) =>
      ([1, 2] as const).map((h) => (
        <Still key={`api${b}${h}`} id={`InfografisApi${b === "en" ? "EN" : ""}${h}`} component={InfografisApi} defaultProps={{ bahasa: b, halaman: h }} width={1080} height={1350} />
      )),
    )}
    {(["id", "en"] as const).flatMap((b) =>
      ([1, 2] as const).map((h) => (
        <Still key={`${b}${h}`} id={`Infografis${b === "en" ? "EN" : ""}${h}`} component={Infografis} defaultProps={{ bahasa: b, halaman: h }} width={1080} height={1350} />
      )),
    )}
  </>
);
