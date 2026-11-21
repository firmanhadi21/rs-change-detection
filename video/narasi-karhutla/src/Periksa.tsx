/**
 * "Memeriksa Peta Tambang Nikel" — a standalone film on checking the Weda Bay / Sagea open-ground
 * maps (AlphaEarth, TESSERA) against 300 hand labels and a blind recheck of 101 points.
 *
 *   first map     trained on hand-drawn boxes: 91–92 % on held-out boxes; 10,568–13,862 ha open
 *   hand labels   recall 1.0 but precision ~0.4: most "open" pixels were shrub and regrowth
 *   recheck       56/81 contested unchanged, 13 -> disturbed, controls 16/20 unchanged
 *   new estimate  4,533 ± 1,247 ha open (6,824 ± 1,554 with disturbed), Weda core 2025
 *   by year       AlphaEarth first change vs 2019: peak 2023
 *   Sagea         40–58 ha within 1 km of the lake in 2025, mostly before 2019
 *
 * Indonesian only (Bian). Same palette, type and audio pipeline as Hutan.tsx. Every figure is from
 * periksaData.json (scripts/periksa_film_assets.py). No company is named.
 */

import React from "react";
import { AbsoluteFill, Audio, Img, interpolate, Sequence, staticFile, useCurrentFrame } from "remotion";
import { JADWAL_PERIKSA } from "./jadwalPeriksa";
import { Bingkai, Judul, Keterangan, Kolom, LatarDiam, Lembut, masuk } from "./komponen";
import { angkaGaya, judulFont, ribuan, tubuhFont, warna } from "./teema";
import D from "./periksaData.json";

const ABU_GELAP = "#3A424D";
const AUDIO = "audio/periksa";
const persen = (x: number) => `${Math.round(x * 100)}%`;
const pm = (v: number[]) => `${ribuan(v[0])} ± ${ribuan(v[1])}`;

const T = {
  kiri: "Peta tambang nikel, Halmahera Tengah",
  waktu: "November 2026",
  labelSumber: "Sumber",
  alisJudul: "Analisis citra satelit dan model AI",
  judul: ["MEMERIKSA", "PETA TAMBANG", "NIKEL"],
  subJudul: "Tiga ratus titik yang diperiksa secara visual mengoreksi peta kecerdasan buatan di Teluk Weda dan Danau Sagea.",
  sumberCitra: "Sentinel-2 L2A (Copernicus), median 2025",
  sumberLama: "AlphaEarth 2025, random forest, 34 kotak latih",
  sumberLabel: "297 titik acak berlapis, ≥ 150 m dari kotak latih, dilabeli dari citra Sentinel-2 2025 tanpa melihat tebakan model",
  sumberUlang: "Pelabelan ulang buta: 81 titik yang diperdebatkan dan 20 titik kontrol, urutan diacak",
  sumberBaru: "Uji per blok 1 km · luas dari label, selang 95%",
  sumberTahun: "AlphaEarth, perubahan dibanding 2019",
  sumberSagea: "JRC GSW · rentang: AlphaEarth–TESSERA",
};

/* ------------------------------ furniture ----------------------------- */

const Bkg: React.FC<{ sumber?: string; tampil?: number }> = ({ sumber, tampil }) => (
  <Bingkai kiri={T.kiri} waktu={T.waktu} labelSumber={T.labelSumber} sumber={sumber} tampil={tampil} />
);

const Alis: React.FC<{ anak: string; w?: string }> = ({ anak, w = warna.bara }) => (
  <div style={{ fontFamily: tubuhFont, fontSize: 21, fontWeight: 600, letterSpacing: "0.22em", textTransform: "uppercase", color: w }}>{anak}</div>
);

const Angka: React.FC<{ anak: string; ukuran?: number; warnaA?: string }> = ({ anak, ukuran = 120, warnaA = warna.nyala }) => (
  <div style={{ ...angkaGaya, fontSize: ukuran, fontWeight: 600, color: warnaA, lineHeight: 1 }}>{anak}</div>
);

const Garis: React.FC<{ anak: React.ReactNode; tampil: number; lebar?: number }> = ({ anak, tampil, lebar = 620 }) => (
  <div style={{ borderLeft: `3px solid ${warna.bara}`, paddingLeft: 18, fontFamily: tubuhFont, fontSize: 26, color: warna.kapur, lineHeight: 1.35, maxWidth: lebar, opacity: tampil }}>
    {anak}
  </div>
);

const Legenda: React.FC<{ isi: [string, string][]; tampil?: number }> = ({ isi, tampil = 1 }) => (
  <div style={{ display: "flex", gap: 22, flexWrap: "wrap", opacity: tampil, maxWidth: 640 }}>
    {isi.map(([k, w]) => (
      <div key={k} style={{ display: "flex", alignItems: "center", gap: 9, fontFamily: tubuhFont, fontSize: 20, color: warna.abu }}>
        <div style={{ width: 16, height: 16, background: w }} />
        {k}
      </div>
    ))}
  </div>
);

/** Pictures in the right part of the frame (720–1920 px), fitted whole, crossfading; optional caption. */
const Panel: React.FC<{ gambar: string[]; panjang: number; dari?: number; sampai?: number; tanda?: (i: number) => string; atas?: React.ReactNode }> = ({
  gambar,
  panjang,
  dari = 0.08,
  sampai = 0.7,
  tanda,
  atas,
}) => {
  const f = useCurrentFrame();
  const pos = gambar.length === 1 ? 0 : interpolate(f, [panjang * dari, panjang * sampai], [0, gambar.length - 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const i = Math.floor(pos);
  const frac = pos - i;
  const sekarang = Math.min(gambar.length - 1, Math.round(pos));
  const gaya: React.CSSProperties = { position: "absolute", width: 1200, height: 1080, objectFit: "contain", objectPosition: "72% 50%" };
  return (
    <AbsoluteFill style={{ backgroundColor: warna.jelaga }}>
      <div style={{ position: "absolute", left: 720, top: 0, width: 1200, height: 1080, overflow: "hidden" }}>
        <Img src={staticFile(`periksa/${gambar[i]}`)} style={gaya} />
        {i + 1 < gambar.length ? <Img src={staticFile(`periksa/${gambar[i + 1]}`)} style={{ ...gaya, opacity: frac }} /> : null}
        {atas}
      </div>
      <AbsoluteFill style={{ background: `linear-gradient(90deg, ${warna.jelaga} 0%, ${warna.jelaga} 37%, rgba(10,12,15,0) 48%)` }} />
      {tanda ? (
        <div style={{ position: "absolute", right: 70, bottom: 110, ...angkaGaya, fontSize: 64, fontWeight: 600, color: warna.kapur, textShadow: "0 2px 18px rgba(0,0,0,0.85)" }}>
          {tanda(sekarang)}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};

/** Horizontal bar: label, bar, value. */
const Batang: React.FC<{ label: string; nilai: number; maks: number; teks: string; w: string; tampil: number; lebar?: number }> = ({ label, nilai, maks, teks, w, tampil, lebar = 380 }) => (
  <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
    <div style={{ width: 250, fontFamily: tubuhFont, fontSize: 23, color: warna.kapur }}>{label}</div>
    <div style={{ width: lebar, height: 30, background: warna.arang }}>
      <div style={{ width: (lebar * nilai * tampil) / maks, height: 30, background: w }} />
    </div>
    <div style={{ ...angkaGaya, fontSize: 26, fontWeight: 600, color: w, opacity: tampil, whiteSpace: "nowrap" }}>{teks}</div>
  </div>
);

/** Vertical bars by year. */
const BatangTahun: React.FC<{ tahun: string[]; nilai: number[]; tampil: (i: number) => number; warnaI: (i: number) => string; label: (i: number) => string | null; W?: number; H?: number }> = ({
  tahun,
  nilai,
  tampil,
  warnaI,
  label,
  W = 620,
  H = 300,
}) => {
  const maks = Math.max(...nilai);
  const bw = W / nilai.length;
  return (
    <svg width={W} height={H + 70}>
      {nilai.map((v, i) => {
        const o = tampil(i);
        const h = (H * v * o) / maks;
        const lab = label(i);
        return (
          <g key={i}>
            <rect x={i * bw + bw * 0.14} y={H - h + 30} width={bw * 0.72} height={h} fill={warnaI(i)} />
            {lab && o > 0.5 ? (
              <text x={i * bw + bw / 2} y={H - h + 20} fill={warnaI(i)} fontSize={21} textAnchor="middle" fontFamily={angkaGaya.fontFamily as string} fontWeight={600}>
                {lab}
              </text>
            ) : null}
            <text x={i * bw + bw / 2} y={H + 62} fill={warna.samar} fontSize={19} textAnchor="middle" fontFamily={tubuhFont}>
              {tahun[i]}
            </text>
          </g>
        );
      })}
    </svg>
  );
};

/* ---------------------------------- scenes --------------------------- */

const KartuJudul: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 4, 24);
  return (
    <Lembut panjang={panjang}>
      <Panel gambar={["weda_s2.jpg"]} panjang={panjang} />
      <Kolom jarak={26}>
        <div style={{ opacity: a, transform: `translateY(${(1 - a) * 20}px)` }}>
          <div style={{ marginBottom: 24 }}>
            <Alis anak={T.alisJudul} />
          </div>
          <h1 style={{ fontFamily: judulFont, fontWeight: 900, fontSize: 96, lineHeight: 0.94, letterSpacing: "-0.04em", color: warna.kapur, margin: 0 }}>
            {T.judul.map((l, i) => (
              <React.Fragment key={l}>
                {i > 0 && <br />}
                {l}
              </React.Fragment>
            ))}
          </h1>
          <div style={{ marginTop: 28 }}>
            <Keterangan lebar={640} anak={T.subJudul} />
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Buka: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const b = masuk(f, Math.round(panjang * 0.4), 22);
  const c = masuk(f, Math.round(panjang * 0.55), 22);
  const kartu = (judul: string, asal: string, n: string, t: number) => (
    <div style={{ opacity: t, borderTop: `2px solid ${warna.garis}`, paddingTop: 14, width: 600 }}>
      <div style={{ fontFamily: judulFont, fontWeight: 800, fontSize: 40, color: warna.kapur }}>{judul}</div>
      <div style={{ fontFamily: tubuhFont, fontSize: 23, color: warna.abu, marginTop: 4 }}>{asal}</div>
      <div style={{ fontFamily: tubuhFont, fontSize: 23, color: warna.kapur, marginTop: 4 }}>
        <span style={{ ...angkaGaya, color: warna.nyala, fontWeight: 600 }}>{n}</span> angka per petak 10 m, setahun citra
      </div>
    </div>
  );
  return (
    <Lembut panjang={panjang}>
      <Panel gambar={["weda_s2.jpg"]} panjang={panjang} />
      <Bkg sumber={T.sumberCitra} tampil={a} />
      <Kolom jarak={22}>
        <div style={{ opacity: a, width: 620 }}>
          <Alis anak="Teluk Weda, Halmahera Tengah" />
          <div style={{ marginTop: 18 }}>
            <Judul anak="Seberapa luas lahan yang dibuka?" ukuran={54} />
          </div>
        </div>
        {kartu("AlphaEarth", "Google DeepMind", "64", b)}
        {kartu("TESSERA", "Universitas Cambridge", "128", c)}
      </Kolom>
    </Lembut>
  );
};

const Lama: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const b = masuk(f, Math.round(panjang * 0.3), 22);
  const c = masuk(f, Math.round(panjang * 0.6), 22);
  const [k1, k2] = D.lama.skor_kotak;
  const [h1, h2] = D.lama.weda_ha;
  return (
    <Lembut panjang={panjang}>
      <Panel gambar={["weda_s2.jpg", "weda_lama.jpg"]} panjang={panjang} dari={0.45} sampai={0.62} />
      <Bkg sumber={T.sumberLama} tampil={a} />
      <Kolom jarak={0}>
        <div style={{ width: 620, opacity: a }}>
          <Alis anak="Peta pertama" />
          <div style={{ marginTop: 18 }}>
            <Judul anak="Dilatih dari kotak yang digambar tangan" ukuran={48} />
          </div>
          <div style={{ marginTop: 40, opacity: b }}>
            <div style={{ fontFamily: tubuhFont, fontSize: 24, color: warna.abu }}>Skor uji pada kotak lain</div>
            <Angka anak={`${persen(k1)}–${persen(k2)}`} ukuran={86} warnaA={warna.kapur} />
          </div>
          <div style={{ marginTop: 34, opacity: c }}>
            <div style={{ fontFamily: tubuhFont, fontSize: 24, color: warna.abu }}>Lahan terbuka di Teluk Weda, 2025</div>
            <Angka anak={`${ribuan(h1)}–${ribuan(h2)}`} ukuran={66} warnaA={warna.bara} />
            <div style={{ fontFamily: tubuhFont, fontSize: 24, color: warna.kapur }}>hektare</div>
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const NAMA_KELAS: Record<string, string> = { bare: "tanah gundul", built: "bangunan", shrub: "semak, belukar", disturbed: "terganggu, menghijau", forest: "hutan", tree_crops: "kebun" };

const Label: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const b = masuk(f, Math.round(panjang * 0.42), 22);
  const c = masuk(f, Math.round(panjang * 0.62), 22);
  const presisi = (D.lama.presisi_tessera + D.lama.presisi_aef) / 2;
  const chips = D.chips.slice(0, 3);
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Bkg sumber={T.sumberLabel} tampil={a} />
      <Kolom jarak={0}>
        <div style={{ display: "flex", gap: 80, alignItems: "center" }}>
          <div style={{ width: 640, opacity: a }}>
            <Alis anak="Diperiksa secara visual" />
            <div style={{ marginTop: 18 }}>
              <Judul anak={`${D.titik} titik acak, dilabeli tanpa melihat tebakan model`} ukuran={46} />
            </div>
            <div style={{ marginTop: 40, display: "flex", flexDirection: "column", gap: 18 }}>
              <Batang label="Tertangkap peta" nilai={D.lama.recall} maks={1} teks="semua" w={warna.abu} tampil={b} lebar={250} />
              <Batang label="Tebakan “terbuka” yang benar" nilai={presisi} maks={1} teks="± 4 dari 10" w={warna.bara} tampil={c} lebar={250} />
            </div>
            <div style={{ marginTop: 30 }}>
              <Garis anak="Sisanya semak, rumput, dan belukar yang tumbuh kembali." tampil={c} />
            </div>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
            {chips.map((ch, i) => {
              const o = masuk(f, Math.round(panjang * 0.12) + i * 14, 18);
              return (
                <div key={ch.id} style={{ display: "flex", gap: 22, alignItems: "center", opacity: o }}>
                  <Img src={staticFile(`periksa/chip_${ch.id}.jpg`)} style={{ width: 260, height: 260 }} />
                  <div style={{ fontFamily: tubuhFont, fontSize: 24, lineHeight: 1.5 }}>
                    <div style={{ color: warna.abu }}>
                      Peta: <span style={{ color: warna.bara, fontWeight: 600 }}>terbuka</span>
                    </div>
                    <div style={{ color: warna.abu }}>
                      Label: <span style={{ color: warna.kapur, fontWeight: 600 }}>{NAMA_KELAS[ch.label1] ?? ch.label1}</span>
                    </div>
                  </div>
                </div>
              );
            })}
            <div style={{ fontFamily: tubuhFont, fontSize: 18, color: warna.samar }}>Sentinel-2 2025, 800 m; kotak kuning = piksel 10 m yang dilabeli</div>
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Ulang: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const U = D.cek_ulang;
  const lain = U.diperdebatkan - U.tetap - U.ke_terganggu;
  const segmen: [number, string, string][] = [
    [U.tetap, warna.abu, `${U.tetap} tetap sama`],
    [U.ke_terganggu, warna.nyala, `${U.ke_terganggu} → terganggu, menghijau`],
    [lain, ABU_GELAP, `${lain} berubah lain`],
  ];
  const W = 1500;
  const b = masuk(f, Math.round(panjang * 0.15), 30);
  const c = masuk(f, Math.round(panjang * 0.62), 22);
  let x = 0;
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Bkg sumber={T.sumberUlang} tampil={a} />
      <Kolom jarak={30}>
        <div style={{ opacity: a }}>
          <Alis anak="Apakah labelnya yang keliru?" />
          <div style={{ marginTop: 18 }}>
            <Judul anak={`${U.n} titik dilabeli ulang, dalam urutan baru`} ukuran={56} />
          </div>
        </div>
        <div>
          <div style={{ fontFamily: tubuhFont, fontSize: 25, color: warna.kapur, marginBottom: 12, opacity: b }}>{U.diperdebatkan} titik yang diperdebatkan</div>
          <svg width={W} height={60}>
            {segmen.map(([n, w], i) => {
              const lebar = (W * n * b) / U.diperdebatkan;
              const r = <rect key={i} x={x} y={0} width={Math.max(0, lebar - 4)} height={60} fill={w} />;
              x += lebar;
              return r;
            })}
          </svg>
          <div style={{ display: "flex", gap: 40, marginTop: 14, opacity: b }}>
            {segmen.map(([, w, t]) => (
              <div key={t} style={{ fontFamily: tubuhFont, fontSize: 25, color: w === ABU_GELAP ? warna.abu : w, fontWeight: 600 }}>
                {t}
              </div>
            ))}
          </div>
        </div>
        <div style={{ opacity: c, display: "flex", gap: 30, alignItems: "baseline" }}>
          <Angka anak={`${U.kontrol_tetap}/${U.kontrol}`} ukuran={86} warnaA={warna.kapur} />
          <div style={{ fontFamily: tubuhFont, fontSize: 27, color: warna.kapur, maxWidth: 900, lineHeight: 1.35 }}>
            titik kontrol tetap sama — tidak ada yang berpindah dari terbuka ke bervegetasi, atau sebaliknya
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const Baru: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const b = masuk(f, Math.round(panjang * 0.25), 22);
  const c = masuk(f, Math.round(panjang * 0.5), 22);
  const d = masuk(f, Math.round(panjang * 0.72), 22);
  const L = D.luas;
  const maks = D.lama.weda_ha[1];
  return (
    <Lembut panjang={panjang}>
      <Panel gambar={["weda_lama.jpg", "weda_baru.jpg"]} panjang={panjang} dari={0.25} sampai={0.42} tanda={(i) => (i === 0 ? "peta pertama" : "peta baru")} />
      <Bkg sumber={T.sumberBaru} tampil={a} />
      <Kolom jarak={0}>
        <div style={{ width: 640, opacity: a }}>
          <Alis anak="Dilatih ulang dengan label titik" />
          <div style={{ marginTop: 16, display: "flex", gap: 20, alignItems: "baseline" }}>
            <Angka anak={persen(D.baru_cv.aef.oa)} ukuran={80} warnaA={warna.kapur} />
            <div style={{ fontFamily: tubuhFont, fontSize: 24, color: warna.abu, maxWidth: 330 }}>tepat pada titik yang tidak dipakai melatih</div>
          </div>
          <div style={{ fontFamily: tubuhFont, fontSize: 24, color: warna.kapur, marginTop: 36, marginBottom: 14 }}>Lahan terbuka di Teluk Weda, 2025 (ha)</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <Batang label="Peta pertama" nilai={maks} maks={maks} teks={`${ribuan(D.lama.weda_ha[0])}–${ribuan(maks)}`} w={warna.abu} tampil={b} lebar={250} />
            <Batang label="Gundul + bangunan" nilai={L.weda_terbuka[0]} maks={maks} teks={pm(L.weda_terbuka)} w={warna.bara} tampil={c} lebar={250} />
            <Batang label="+ terganggu" nilai={L.weda_plus[0]} maks={maks} teks={pm(L.weda_plus)} w={warna.nyala} tampil={d} lebar={250} />
          </div>
          <div style={{ marginTop: 26 }}>
            <Legenda isi={[["Terbuka (gundul, bangunan)", warna.bara], ["Terganggu, menghijau", warna.nyala]]} tampil={c} />
          </div>
        </div>
      </Kolom>
    </Lembut>
  );
};

const THN = ["2019", "2020", "2021", "2022", "2023", "2024", "2025"];
const KUNCI = ["<=2019/unchanged", "2020", "2021", "2022", "2023", "2024", "2025"];

const Tahun: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const Y = D.tahun_weda_aef as Record<string, number>;
  const nilai = KUNCI.map((k) => Y[k]);
  const t0 = panjang * 0.08, t1 = panjang * 0.7;
  const jam = (i: number) => t0 + (i / (THN.length - 1)) * (t1 - t0);
  const puncak = nilai.indexOf(Math.max(...nilai.slice(1)));
  return (
    <Lembut panjang={panjang}>
      <Panel gambar={THN.map((y) => `weda_y${y}.jpg`)} panjang={panjang} dari={0.08} sampai={0.7} tanda={(i) => THN[i]} />
      <Bkg sumber={T.sumberTahun} tampil={a} />
      <Kolom jarak={0}>
        <div style={{ width: 640, opacity: a }}>
          <Alis anak="Kapan dibuka?" />
          <div style={{ fontFamily: tubuhFont, fontSize: 25, color: warna.kapur, marginTop: 20, marginBottom: 4 }}>Lahan terbuka dan terganggu 2025, menurut tahun pertama berubah (ha)</div>
          <BatangTahun
            tahun={["≤ 2019", ...THN.slice(1)]}
            nilai={nilai}
            tampil={(i) => masuk(f, jam(i), 14)}
            warnaI={(i) => (i === 0 ? ABU_GELAP : i === puncak ? warna.nyala : warna.bara)}
            label={(i) => (i === puncak || i === nilai.length - 1 ? ribuan(Math.round(nilai[i])) : null)}
          />
          <Legenda
            isi={[["Sudah terbuka 2019 / tak berubah", "#7E8792"], ["Dibuka tahun sebelumnya", warna.bara], ["Dibuka tahun ini", warna.nyala]]}
            tampil={a}
          />
        </div>
      </Kolom>
    </Lembut>
  );
};

const Sagea: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 6, 20);
  const c = masuk(f, Math.round(panjang * 0.6), 22);
  const Y = D.danau_aef as Record<string, number>;
  const nilai = KUNCI.map((k) => Y[k]);
  // lake centre in the contained 1260x1080 frame (bbox 128.035-128.105 E, 0.455-0.515 N), scaled to 1200 wide
  const s = 1200 / D.sagea.lebar;
  const top = (1080 - D.sagea.tinggi * s) / 2;
  const lx = ((128.0681 - 128.035) / 0.07) * 1200;
  const ly = top + ((0.515 - 0.4879) / 0.06) * D.sagea.tinggi * s;
  const penanda = (
    <div style={{ position: "absolute", left: lx - 80, top: ly - 120, opacity: a, fontFamily: tubuhFont, fontSize: 24, fontWeight: 600, color: warna.kapur, textShadow: "0 2px 10px rgba(0,0,0,0.9)" }}>
      Danau Sagea
    </div>
  );
  const [r1, r2] = D.danau_2025;
  return (
    <Lembut panjang={panjang}>
      <Panel gambar={THN.map((y) => `sagea_y${y}.jpg`)} panjang={panjang} dari={0.08} sampai={0.55} tanda={(i) => THN[i]} atas={penanda} />
      <Bkg sumber={T.sumberSagea} tampil={a} />
      <Kolom jarak={0}>
        <div style={{ width: 640, opacity: a }}>
          <Alis anak="Danau Sagea, Halmahera Tengah" />
          <div style={{ fontFamily: tubuhFont, fontSize: 25, color: warna.kapur, marginTop: 20 }}>Lahan terbuka dan terganggu dalam 1 km dari tepi danau, 2025</div>
          <Angka anak={`${Math.min(r1, r2)}–${Math.max(r1, r2)} ha`} ukuran={80} />
          <div style={{ fontFamily: tubuhFont, fontSize: 22, color: warna.abu, marginTop: 22 }}>Menurut tahun pertama berubah (ha, AlphaEarth)</div>
          <BatangTahun
            tahun={["≤ 2019", ...THN.slice(1)]}
            nilai={nilai}
            H={200}
            tampil={(i) => masuk(f, Math.round(panjang * 0.12) + i * 8, 14)}
            warnaI={(i) => (i === 0 ? ABU_GELAP : warna.bara)}
            label={(i) => (i === 0 || nilai[i] >= 3 ? ribuan(Math.round(nilai[i])) : null)}
          />
          <Garis anak={`Citra 2026 menunjukkan lonjakan (± ${D.danau_dw_2026} ha menurut Dynamic World), sesudah data model berakhir.`} tampil={c} />
        </div>
      </Kolom>
    </Lembut>
  );
};

const Tutup: React.FC<{ panjang: number }> = ({ panjang }) => {
  const f = useCurrentFrame();
  const a = masuk(f, 4, 22);
  const b = masuk(f, Math.round(panjang * 0.25), 24);
  const d = masuk(f, Math.round(panjang * 0.55), 24);
  return (
    <Lembut panjang={panjang}>
      <LatarDiam />
      <Kolom jarak={30}>
        <h1 style={{ fontFamily: judulFont, fontWeight: 900, fontSize: 62, lineHeight: 1.06, color: warna.kapur, margin: 0, opacity: a, maxWidth: 1500 }}>
          Skor tinggi pada data latih sendiri bisa menyesatkan.
        </h1>
        <h2 style={{ fontFamily: judulFont, fontWeight: 900, fontSize: 56, lineHeight: 1.08, color: warna.bara, margin: 0, opacity: b, maxWidth: 1500 }}>
          {D.titik} titik yang diperiksa dengan teliti memangkas perkiraan lahan terbuka lebih dari separuh.
        </h2>
        <div style={{ opacity: d, borderLeft: `3px solid ${warna.garis}`, paddingLeft: 20, fontFamily: tubuhFont, fontSize: 26, color: warna.abu, lineHeight: 1.45, maxWidth: 1400, marginTop: 10 }}>
          Label masih dari satu orang dan belum dicek di lapangan.
        </div>
      </Kolom>
    </Lembut>
  );
};

const BARIS_SUMBER: [string, string][] = [
  ["Citra", "Sentinel-2 L2A (Copernicus), median 2025, Cloud Score+"],
  ["Model", "AlphaEarth Foundations Satellite Embedding (Google DeepMind), 2019–2025; TESSERA (Universitas Cambridge), via geotessera"],
  ["Label", "300 titik acak berlapis dan 101 titik pelabelan ulang, dilabeli dari Sentinel-2 2025 (satu pelabel)"],
  ["Luas", "rata-rata berstrata dari label, selang 95%; peta: random forest, 10 m"],
  ["Batas", "FAO GAUL 2025; air: JRC Global Surface Water 1.4; Dynamic World (2026)"],
  ["Kode", "earthchange (PyPI) dan skrip proyek; analisis November 2026"],
];

const KartuSumber: React.FC<{ panjang: number }> = () => {
  const f = useCurrentFrame();
  const a = masuk(f, 4, 20);
  return (
    <AbsoluteFill style={{ backgroundColor: warna.jelaga, opacity: a }}>
      <Kolom jarak={18}>
        <Alis anak="Sumber data" />
        <div style={{ display: "flex", flexDirection: "column", gap: 11, width: 1680 }}>
          {BARIS_SUMBER.map(([k, v]) => (
            <div key={k} style={{ display: "flex", gap: 28, alignItems: "baseline" }}>
              <div style={{ width: 200, fontFamily: tubuhFont, fontSize: 24, fontWeight: 600, color: warna.kapur }}>{k}</div>
              <div style={{ fontFamily: tubuhFont, fontSize: 24, color: warna.abu }}>{v}</div>
            </div>
          ))}
        </div>
        <div style={{ marginTop: 12, paddingTop: 16, borderTop: `2px solid ${warna.bara}`, fontFamily: tubuhFont, fontSize: 22, color: warna.kapur, lineHeight: 1.5, maxWidth: 1680 }}>
          Lahan terbuka bukan bukti pelaku; sebagian adalah jalan, permukiman, dan kawasan industri. Angka satelit dapat berbeda dari data resmi. Tidak ada perusahaan yang disebut.
        </div>
      </Kolom>
    </AbsoluteFill>
  );
};

/* --------------------------------- film ------------------------------ */

const ADEGAN: Record<string, React.FC<{ panjang: number }>> = {
  "01-buka": Buka,
  "02-lama": Lama,
  "03-label": Label,
  "04-ulang": Ulang,
  "05-baru": Baru,
  "06-tahun": Tahun,
  "07-sagea": Sagea,
  "08-tutup": Tutup,
};

export const PeriksaFilm: React.FC = () => {
  const J = JADWAL_PERIKSA;
  return (
    <AbsoluteFill style={{ backgroundColor: warna.jelaga }}>
      <Audio src={staticFile(`${AUDIO}/musik-periksa.mp3`)} />
      <Sequence durationInFrames={J.JUDUL_FRAME}>
        <KartuJudul panjang={J.JUDUL_FRAME} />
      </Sequence>
      {J.adegan.map((a) => {
        const K = ADEGAN[a.id];
        return (
          <Sequence key={a.id} from={a.mulai} durationInFrames={a.panjang}>
            <K panjang={a.panjang} />
            <Audio src={staticFile(`${AUDIO}/${a.id}.mp3`)} />
          </Sequence>
        );
      })}
      <Sequence from={J.akhirNarasi} durationInFrames={J.TUTUP_FRAME}>
        <KartuSumber panjang={J.TUTUP_FRAME} />
      </Sequence>
    </AbsoluteFill>
  );
};
