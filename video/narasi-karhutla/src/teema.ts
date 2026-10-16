/**
 * The film's palette and type, taken from the footage it sits over.
 *
 * The smoke animation is a near-black terrain map with orange fire pixels
 * and grey smoke, so the film borrows exactly that: soot ground, ash text,
 * ember as the single accent. Nothing here is a generic dark theme -- the
 * neutrals carry a slight blue bias so the ember reads warm against them.
 */

import { loadFont as loadArchivo } from "@remotion/google-fonts/Archivo";
import { loadFont as loadPlexMono } from "@remotion/google-fonts/IBMPlexMono";
import { loadFont as loadPlexSans } from "@remotion/google-fonts/IBMPlexSans";

// Load only the weights and the subset this film sets. Left unrestricted,
// each face fetches every weight and script -- hundreds of requests per
// render, and a face that fails to arrive falls back silently to a system
// font rather than erroring, which is the worst way to find out.
export const judulFont = loadArchivo("normal", {
  subsets: ["latin"],
  weights: ["800", "900"],
}).fontFamily;

export const angkaFont = loadPlexMono("normal", {
  subsets: ["latin"],
  weights: ["400", "600"],
}).fontFamily;

export const tubuhFont = loadPlexSans("normal", {
  subsets: ["latin"],
  weights: ["400", "600"],
}).fontFamily;

export const warna = {
  jelaga: "#0A0C0F", // soot -- the ground
  arang: "#161A20", // charcoal -- raised panels
  garis: "#262C35", // hairlines
  abu: "#7E8792", // ash -- secondary text
  samar: "#5A626C", // faint -- tertiary, units and footnotes
  kapur: "#E8EBEE", // chalk -- primary text
  bara: "#FF5A1F", // ember -- the one accent
  nyala: "#FFB020", // flame -- figures and highlights
  gambut: "#9A6530", // peat
} as const;

/** Digits must not jitter while a counter runs. */
export const angkaGaya: React.CSSProperties = {
  fontFamily: angkaFont,
  fontVariantNumeric: "tabular-nums",
  fontFeatureSettings: '"tnum" 1',
};

/** Indonesian uses "." for thousands. */
export const ribuan = (n: number): string =>
  Math.round(n).toLocaleString("id-ID");

export const koma = (n: number, d = 1): string =>
  n.toLocaleString("id-ID", { minimumFractionDigits: d, maximumFractionDigits: d });
