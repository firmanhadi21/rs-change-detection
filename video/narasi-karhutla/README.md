# narasi-karhutla

Two films, one project, sharing palette, type and audio pipeline:

| Composition | Length | What it does |
|---|---|---|
| `Narasi` | 2 min 14 s | The season: how much burnt, on what ground, how often before |
| `Bukti` | 1 min 49 s | The evidence: how we know a given scar is real |

```
npm run build          # Narasi -> out/narasi-karhutla.mp4
npm run build:bukti    # Bukti  -> out/bukti-karhutla.mp4
```

`Bukti` is the companion piece. It takes one 20 × 20 km block of drained
peat in Central Kalimantan and walks three same-date PlanetScope mosaics
(21 Jul → 18 Aug → 29 Aug 2026) against a Sentinel-2 dNBR severity map.
Its argument is the division of labour between the instruments:
**PlanetScope has no SWIR**, so it cannot produce a severity figure at
all; every thresholded number spoken in it comes from Sentinel-2. It also
carries the finding that the burn never saturates — widening the box from
12 to 60 km takes burnt area from 8,573 to 55,383 ha without ever
flattening, so there is no natural boundary, only the frame you pick.

Its schedule is `src/jadwalBukti.json`, its figures `src/buktiData.json`,
its script `src/narasiBukti.json`, its bed `bake_musik_bukti.py` — the same
mechanisms as the main film, with the bed reusing the main film's
normalised score (sped up rather than slowed, since this film is shorter)
so the two sound like one body of work.

## Api — what makes Kalimantan burn (standalone, Indonesian + English)

`Api` / `ApiEN` ("Api, Gambut, dan Sawit: Apa yang Membuat Kalimantan Terbakar?" / "Fire, Peat and Palm:
What Makes Kalimantan Burn?", about 4 min 12 s / 4 min 10 s; Indonesian read by Bian, English by Max) and two
infographic pages per language, `InfografisApi1/2` and `InfografisApiEN1/2` (1080 × 1350): Kalimantan fire
emissions 2001–2025 (peat 9% of land, ~86% of emissions), which factors predict where fire breaks out
(drought, forest condition, access, oil palm and concessions, peat; forest-area status such as APL near the
bottom), fire around the oil-palm planting year, swidden-like mosaic vs peat fires (VIIRS), the 2026 test, and
the 2027 normal vs El Niño scenarios priced at US$5 / 51 / 185 per tonne CO₂.

```
conda run -n base python -I ../../scripts/api_film_assets.py      # public/api/, src/apiData.json
uv run --no-project --with elevenlabs python3 tts_konsesi.py --film api [--bahasa en]   # narration + jadwalApi[EN].json
python3 bake_musik_bukti.py --jadwal src/jadwalApi.json \
    --keluar public/audio/api/musik-api.mp3 --sambung 70           # and jadwalApiEN.json -> api-en/musik-api-en.mp3
npm run build:api && npm run build:api-en                          # or build:infografis-api for the four pages
```

Figures come from `output/fire/kalimantan_palm_panel/` (scripts/kalimantan_palm_fire_panel.py,
kalimantan_fire_factors.py, kalimantan_fire_carbon.py): MCD64A1 burned area on the 500 m MODIS grid, IPCC
2006/2013 emission factors with ESA CCI biomass, a gradient-boosting model checked on 50 km blocks it never saw,
and 2026 checked against MCD64A1 January–September. Emissions are likely underestimated (MODIS misses small
and smouldering peat fires); peat burn depth is the main uncertainty; adat territories are not yet included.
No company is named.

## Periksa — checking the nickel-mining maps (standalone, Indonesian)

`Periksa` ("Memeriksa Peta Tambang Nikel", about 3 min 8 s, read by Bian): the
Weda Bay / Sagea open-ground maps from AlphaEarth and TESSERA, checked against
300 hand labels and a blind recheck of 101 points; the label-based 2025 area,
open ground by first year of change since 2019, and the 1 km ring around Lake Sagea.

```
conda run -n base python -I ../../scripts/periksa_film_assets.py  # public/periksa/, src/periksaData.json
python3 tts_konsesi.py --film periksa                              # narration + jadwalPeriksa.json
python3 bake_musik_bukti.py --jadwal src/jadwalPeriksa.json \
    --keluar public/audio/periksa/musik-periksa.mp3 --sambung 70
npm run build:periksa
```

Figures come from `output/malut_forest/embeddings/labeller/` (label_eval.json,
recheck_eval.json, map2025/expansion.json). One labeller, no field check. No
company is named.

## Uang — "Ke Mana Uangnya?", part 6 (standalone, Indonesian)

`Uang` (2 min 50 s, read by Bian) and two infographic pages `InfografisUang1/2` (1080 × 1350): did the value of the
nickel boom reach the people of North Maluku? The benefits (manufacturing jobs, poverty falling fastest in
Halmahera Tengah and Timur) are shown next to the gap between production per person and household spending
(Halmahera Tengah ×19.7 vs ×1.7, 2019–2025), where the rest goes, and a comparison with China's reform era.

```
python3 -I ../../scripts/uang_film_assets.py   # public/uang/, src/uangData.json, output/.../welfare/welfare.json
python3 tts_konsesi.py --film uang             # narration + jadwalUang.json
python3 bake_musik_bukti.py --jadwal src/jadwalUang.json \
    --keluar public/audio/uang/musik-uang.mp3 --sambung 70
npm run build:uang
```

Figures come from `output/malut_forest/welfare/` (SOURCES.md with evidence grades, RESULTS.md). No company is named.

## Biaya — "Harga di Balik Nikel", part 5 (standalone, Indonesian)

`Biaya` (2 min 25 s, read by Bian) and two infographic pages `InfografisBiaya1/2` (1080 × 1350): the value added by
nickel mining and processing in North Maluku (BPS regional GDP) against its environmental costs in 2025, shown as
ranges: captive-coal CO₂ at the US EPA social cost of carbon and at the EU ETS price, indicative health costs, forest
carbon and lost ecosystem services; VIIRS night lights around Weda Bay; who gains and who pays.

```
conda run -n base python -I ../../scripts/biaya_film_assets.py   # public/biaya/, src/biayaData.json
python3 tts_konsesi.py --film biaya                               # narration + jadwalBiaya.json
python3 bake_musik_bukti.py --jadwal src/jadwalBiaya.json \
    --keluar public/audio/biaya/musik-biaya.mp3 --sambung 70
npm run build:biaya
```

Figures come from `output/malut_forest/economics/` (econ.json from tmp/malut/econ_analysis.py; inputs graded in
SOURCES.md; caveats in RESULTS.md). It is not a profit-and-loss account: value added is not profit and the social
cost of carbon is a global damage estimate. Royalty and DBH figures are graded (b)/(c) and should be checked
against the original documents before publication. No company is named.

## Air — "Jejak di Perairan", part 4 (standalone, Indonesian)

`Air` (2 min 27 s, read by Bian) and two infographic pages `InfografisAir1/2` (1080 × 1350): from cleared ground
(SIRAD radar and Dynamic World in the Weda Bay mining cells) to murkier water next to the mines (Sentinel-2 TSS,
Nechad 2010; water ≤ 2 km from mining cells vs coast > 15 km away on the same dates), and no visible change in
Sagea Lake. Wording is "keruh" (turbidity), never "tercemar": satellites do not see metals.

```
conda run -n base python -I ../../scripts/air_film_assets.py   # public/air/, src/airData.json
python3 tts_konsesi.py --film air                               # narration + jadwalAir.json
python3 bake_musik_bukti.py --jadwal src/jadwalAir.json \
    --keluar public/audio/air/musik-air.mp3 --sambung 70
npm run build:air
```

Figures come from `output/malut_forest/water/` (RESULTS.md, analysis.json, pressure.json). The analysis stops at
June 2026: after that, Sentinel-2 processing baselines 05.12/05.13 double the reflectance of deep open sea
(deepsea_check.json). Only one sediment map (2024–25) is shown, not a before/after pair: per-pixel two-year medians
mix different scene sets and would suggest a bay-wide change the same-date comparison does not show.

## Tambang — mining footprint across North Maluku (standalone, Indonesian)

`Tambang` ("Jejak Tambang di Maluku Utara", 2 min 40 s, read by Bian) and two infographic
pages `InfografisTambang1/2` (1080 × 1350): open and disturbed ground in 2025 inside the
WRI/Google mining cells, from the Weda-trained AlphaEarth model, label-adjusted with 150
hand-labelled check points outside Weda/Sagea; per regency, and by first year of change.

```
conda run -n base python -I ../../scripts/tambang_film_assets.py  # public/tambang/, src/tambangData.json
python3 tts_konsesi.py --film tambang                              # narration + jadwalTambang.json
python3 bake_musik_bukti.py --jadwal src/jadwalTambang.json \
    --keluar public/audio/tambang/musik-tambang.mp3 --sambung 70
npm run build:tambang
```

Figures come from `output/malut_forest/mining_malut/` (areas.json, check_eval.json,
years_adjusted.json). One labeller, no field check. No company is named.

## Hutan — North Maluku's forests (standalone)

`Hutan` / `HutanEN` ("Apa yang Menggerus Hutan Maluku Utara?" / "What Is
Clearing North Maluku's Forests?", 2 min 57 s / 2 min 51 s) and the
two-page infographic stills `Infografis1/2`, `InfografisEN1/2` (1080 × 1350).
Indonesian is read by Bian, English by Max.

```
conda run -n base python ../../scripts/malut_film_assets.py   # public/hutan/, src/hutanData.json
python3 tts_konsesi.py --film hutan [--bahasa en]               # narration + jadwalHutan[EN].json
python3 bake_musik_bukti.py --jadwal src/jadwalHutan.json \
    --keluar public/audio/hutan/musik-hutan.mp3 --sambung 70
npm run build:hutan && npm run build:hutan-en && npm run build:infografis
```

Figures come from `output/malut_forest/` (Earth Engine runs: Hansen GFC
v1.13, WRI/Google drivers, Dynamic World, Landsat and Sentinel-2 frames);
the same province totals are reproducible with
`earthchange -s forest-account --admin "Maluku Utara"`. No company is
named; the Sagea river turbidity is attributed to residents (Mongabay
Indonesia reporting).

---


A narrated Indonesian explainer that accompanies
`output/smoke_video_indonesia/indonesia_wildfire_smoke.mp4`. The smoke video
shows *where* Indonesia is burning this week; this one says *how much*, *on
what ground*, and *how often the same ground has burnt before*.

Built with Remotion. 1920×1080, 30 fps, 4017 frames (2 min 14 s).

```
npm install
./siapkan.sh          # copy the footage, extract the backdrop still
./normalisasi.sh      # level the audio (only needed once, after a fresh fetch)
npm start             # Remotion studio, for previewing
npm run build         # render to out/narasi-karhutla.mp4
```

## How the cut works

`src/jadwal.json` holds the measured length of each narration mp3;
`jadwal.ts` derives every scene's start frame from it. Nothing is positioned
by hand. Change a line of narration, re-measure the mp3, update one number
in `durasi`, re-run `bake_musik.py`, and the whole film re-cuts around it.

## The audio, and two things that had to be fixed

As generated, the narration sat at −26.8 LUFS and the music at −14.1 — the
bed was louder than the voice. Even ducked to a fifth of its gain it ended
up only **1.3 LU** below the narration, which is nowhere near enough to
speak over. `normalisasi.sh` levels both once with two-pass `loudnorm`
(voice −16 LUFS / −1.5 dBTP, bed −30 LUFS / −6 dBTP), so the 14 LU of
separation lives in the asset and the Remotion side can use plain unity
gain. It keeps the untouched downloads in `public/audio/mentah/` and fails
loudly if any file's duration shifts, because the cut is measured off them.

`bake_musik.py` then writes `musik-mix.mp3`, which is what the film actually
plays, with all of the score's automation already in it:

- **stretched** to `atempo=0.952`. Its 135 s hold only about 127.5 s of real
  content before decaying to nothing, which left the closing line and the
  whole sources card running over dead air. `atempo` preserves pitch, which
  Remotion's `playbackRate` does not.
- **lifted** 2.5× over the title and sources cards, ducked to unity under
  the narration, faded at both ends.

That automation was a per-frame `volume` function in `Narasi.tsx` first.
Remotion compiles one of those into a single ffmpeg `volume` expression
with a clause per distinct value, and over 134 s of fades it grew past what
ffmpeg's parser accepts (`Missing ')' or too many args`). The render failed
*and left the previous mp4 in place*, so it looked like it had worked. If
you reintroduce a volume curve here, check the render log, not the file's
existence.

`bake_musik.py` reads `src/jadwal.json` — the same file `jadwal.ts` builds
the cut from — so the duck cannot drift away from the scene it ducks under.

## Where the numbers come from

`src/narasi.json` is the single source of truth: it holds both the words Bian
speaks and the figures each line puts on screen, so the two cannot drift
apart. Every figure in it was derived by `narr_facts.py` from the
`fire-national` and `fire-zones` run outputs, not typed from memory.

**Two sensors appear in this film and must never be added together:**

| Scenes | Source | What it measures |
|---|---|---|
| 2, 3 | NASA FIRMS **VIIRS** 375 m, 6–12 Oct 2026 | one week of national detections |
| 4 | NASA FIRMS **MODIS** 1 km, 1 Aug – 13 Oct | the season, back to 2015 |
| 5, 6, 7 | **MCD64A1** 500 m, 2015–2025 | burn scars and repeat burning |

That is why every scene burns its own source line into the frame rather than
crediting everything once at the end. The sources card repeats the warning in
full.

Two things the data cannot support, stated on the card and worth repeating:
hotspots are pixel-day detection counts and not burnt area, and MCD64A1 at
500 m misses fires of a few hectares, so every area figure is a lower bound —
most severely for smallholder burning.

### Why there is no 2026 hectare figure

The film gives 2026 as hotspots and never as area, because **no burnt-area
measurement of the 2026 season exists.** Checked against Earth Engine on
13 Oct 2026: the newest `MODIS/061/MCD64A1` granule is dated **2026-07-01**,
104 days behind, and the 1 Aug – 13 Oct window contains **zero** granules.
At that lag the full season becomes computable around **January 2027**.

The only measured 2026 hectares are January–July, over the same five
provinces: **31,192 ha** — already the highest Jan–Jul in the twelve-year
record and 2.2× the 2015–2025 mean of 14,450 ha. It is a pre-season figure
and excludes everything this film is about, so it is not shown.

Estimating the season from its hotspot count was tried and rejected. A
log–log fit over the eleven paired seasons is decent (R² = 0.875), but
2026's 260,365 detections sit 1.7× beyond anything previously observed, and
the 95 % prediction interval comes out at **461,000 – 13,280,000 ha** — a
29-fold range whose upper end is a quarter of Kalimantan. Not publishable.

Sentinel-2 dNBR (this repo's `burn` scenario) is not lag-bound and could
measure 2026 directly, but a 10 m dNBR area cannot be charted against a
500 m MCD64A1 series without committing exactly the sensor-mixing error
this film warns about — and October smoke and cloud badly limit optical
burn mapping over Kalimantan.

### Peat

The peat share is given as a range (74,0–78,3 %) rather than one number
because three peat maps disagree, and on the provinces where an official
figure exists they fail in opposite directions. Pass an official KLHK/BBSDLP
map to `fire-national --peat-file` for a citable single number.

## Assets not in the repo

`.gitignore` excludes `node_modules/`, `public/asap.mp4`, `public/latar.png`,
`out/` and all mp3s.

- **Footage and backdrop** — rebuilt by `./siapkan.sh` from the smoke-video
  run. Note that smoke-video reads FIRMS' rolling 7-day feed, so re-running it
  renders *this* week, not the week in the film.
- **Narration and music** — generated once via ElevenLabs (`eleven_v4`, voice
  `1k39YpzqXZn52BgyLyGO`; score `eleven_music_v2_5`). Regenerating costs
  credits and will not reproduce the same takes, and the cut depends on their
  exact lengths, so keep a backup of `public/audio/` rather than rebuilding
  it. The script each clip speaks is in `src/narasi.json` under `teks`.
