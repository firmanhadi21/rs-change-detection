# earthchange — video series plan

**Working title:** *Satu Pertanyaan, Satu Perintah* / *One Question, One Command*

A twelve-part series taking a viewer from no account and no install to a
citable, defensible environmental assessment they can hand to somebody.

---

## Why this shape

Three decisions drive the running order, and each is worth stating because they
are not obvious:

**1. The first win comes before the sign-up.** Nine of the twenty-four
scenarios need no Earth Engine account — `smoke-video` needs none at all, and
eight run on Microsoft Planetary Computer with `--backend mpc`. Episodes 1–3
use only those. A viewer produces a real map, and a real animation, before
being asked to register for anything. Most remote-sensing tutorials lose their
audience at the credentials step; this series moves that step to episode 4,
once there is something to be motivated by.

**2. Teach on a closed season, demonstrate on a live one.** Every archive here
moves. ERA5-Land runs about a week behind and its trailing day arrives
piecemeal; FIRMS is a day or two behind; GDAS1 publishes weekly in arrears;
MODIS burned area lags three months. **A video with a hardcoded recent date
stops working within days of publication.** So the teaching examples use
**2019 Kalimantan**, a closed season whose numbers will be identical in five
years, and a separate episode (8) teaches the habit of *finding* today's usable
date rather than memorising one. This is the single most important production
decision in the series.

**3. The limits are a lesson, not a disclaimer.** Every scenario writes its own
caveats into `stats.json`, and the assembled brief carries them through
verbatim. That is the package's distinguishing feature and it gets a full
episode (12), not a footnote. A viewer who can say what their number does *not*
show is the one whose work survives being challenged.

---

## Audience and level

| | |
|---|---|
| **Primary** | Provincial and district staff (BPBD, Dinas Lingkungan Hidup), NGO analysts, environmental journalists |
| **Secondary** | Undergraduate and postgraduate students in geography, forestry, environmental science |
| **Assumed** | Comfortable opening a terminal and copying a command. **No** Python, GIS or remote-sensing background assumed |
| **Not assumed** | An Earth Engine account until episode 4; QGIS until episode 10 |
| **Language** | Bahasa Indonesia narration, English on-screen commands and captions. The package and its docs are already bilingual |

---

## Episode plan

### Arc 1 — Something on screen, no account (episodes 1–3)

---

#### Episode 1 · What this is, and what it is for
*Apa ini, dan untuk apa*

**Runtime** 8 min · **Prerequisite** none

**Aim** — Give the viewer an accurate mental model of the package before they
install anything.

**Objectives** — By the end, a viewer can:
- state what a *scenario* is: one question, one command, not one algorithm
- name the three families — hazard, impact, exposure and accountability
- decide which of the twenty-four scenarios their own job needs
- recognise which need an account and which do not

**Show** — The finished Kalimantan brief and the Bromo animation, up front, as
the destination. Then `earthchange --list`, and the tutorial's backend table.

**Explain** — Why "one command per question". Why the scenarios are named after
questions (*was it dry?*, *who breathed it?*) rather than after methods.

**Deliverable** — A viewer who knows which episode to skip to.

---

#### Episode 2 · An animation of the fires burning right now
*Animasi kebakaran yang sedang berlangsung*

**Runtime** 12 min · **Prerequisite** episode 1 · **Account** none

**Aim** — Produce a shareable video of the current fire season in one command.

**Objectives** —
- install with `pip install 'earthchange[video]'`, plus ffmpeg
- render an animation for the viewer's own region
- place city and landform labels themselves
- explain why this scenario **cannot** be run for a past season

**Run**
```bash
earthchange -s smoke-video --lat -7.942 --lon 112.65 --radius 120 -n Bromo \
  --video-title "WILDFIRE SMOKE" \
  --video-subtitle "GUNUNG BROMO · JAWA TIMUR · {period} · CAMS + VIIRS" \
  --video-cities "BROMO,112.953,-7.942,major; Malang,112.632,-7.981,major; …" \
  --video-labels "TENGGER,112.98,-7.75,major; SEMERU,112.922,-8.13,major; …"
```

**Explain** — The FIRMS public feed is a **rolling seven days**: that is why this
is the only scenario that reaches yesterday, and why it can never show 2015.
Why labels are explicit rather than geocoded. What to do when the terrain comes
out black (no Vulkan device — the CPU hillshade takes over and says so).

**Deliverable** — An MP4 and GIF of the viewer's own region, ready to post.

---

#### Episode 3 · Detecting change without an account
*Deteksi perubahan tanpa akun*

**Runtime** 14 min · **Prerequisite** episode 2 · **Account** none

**Aim** — Map deforestation and flooding with `--backend mpc`.

**Objectives** —
- run `deforestation`, `flood` and `burn` on Planetary Computer
- read a GeoTIFF, a quick-look PNG and `stats.json`
- choose `--pre` and `--post` windows that are actually comparable
- say why the two backends will not agree to the pixel

**Run**
```bash
earthchange -s deforestation --lat -3.333 --lon 122.25 --backend mpc \
  --pre 2023-01-01:2023-12-31 --post 2025-01-01:2025-12-31
```

**Explain** — What NDVI loss is and what it is not. Why cloud and shadow create
false positives, and what `--min-obs` does about it: a pixel seen once has a
median of one image, and shadow depresses NDVI, so it mimics loss and never
gain.

**Deliverable** — A change map of the viewer's own district.

---

### Arc 2 — Earth Engine, and the fire season (episodes 4–7)

---

#### Episode 4 · Getting an Earth Engine account, once
*Mendapatkan akun Earth Engine, sekali saja*

**Runtime** 10 min · **Prerequisite** episode 3

**Aim** — Get past the credentials step without mystery.

**Objectives** —
- register and create a service-account key
- place the key so `earthchange` finds it, three ways
- read the authentication error and know what it is asking for
- understand that there is **no automatic fallback** to MPC, and why that is
  deliberate

**Explain** — Which fifteen scenarios need this and why: ERA5-Land, CAMS, FIRMS,
MODIS, WorldPop, CHIRPS and GAUL are not in Planetary Computer's catalogue. It
is a catalogue limit, not an unfinished port.

**Deliverable** — A working key, verified with one small run.

---

#### Episode 5 · Is it dangerous? Fire danger rating
*Seberapa berbahaya? Sistem peringkat bahaya kebakaran*

**Runtime** 16 min · **Prerequisite** episode 4

**Aim** — Produce a fire danger assessment and read it correctly.

**Objectives** —
- run `fire-danger` for a district or province
- read DC, BUI and FWI, and say which one leads in Indonesia
- interpret the BMKG class breaks rather than the Canadian ones
- find the dry pocket, and know why an area average hides it

**Run**
```bash
earthchange -s fire-danger --admin Ketapang -n Ketapang \
  --date 2019-09-30 --spinup 60
```

**Explain** — **The most important teaching moment in the series.** On
30 September 2015, the peak of Indonesia's worst haze disaster in decades, this
returns **DC 293 but FWI 5.9** — because FWI is dominated by ISI, which responds
to wind and fine fuels within hours. Reporting FWI as the headline would have
called that day "Moderate". Peat fire is driven by deep drying, which is what
DC tracks. Teach viewers to lead with DC.

Also: why `--spinup` matters. DC has a ~52-day time lag, so a short run reports
little more than its starting constant.

**Deliverable** — Three maps and a per-designation table, if the viewer has a
zone layer.

---

#### Episode 6 · Was it dry first? Drought before fire
*Apakah kering lebih dulu? Kekeringan sebelum kebakaran*

**Runtime** 12 min · **Prerequisite** episode 5

**Aim** — Establish the precondition, and meet the peat signature.

**Objectives** —
- run `drought` with `--cdi`
- distinguish meteorological from agricultural drought
- explain a case where rainfall is the 3rd driest in 46 years and vegetation
  health says "no drought"

**Explain** — Kalimantan Tengah, August 2026: rain at 62% of normal, 3rd driest
in 46 years, DC 238 — yet VHI 80, vegetation unstressed. **Deep drying without a
surface signal is the peat pattern.** A vegetation-health index alone would have
reported "no drought" and been wrong about the fire risk.

**Deliverable** — A drought map plus the CDI components.

---

#### Episode 7 · The accountability record
*Catatan pertanggungjawaban*

**Runtime** 18 min · **Prerequisite** episodes 5–6 · **Needs** your own zone layer

**Aim** — Produce a citable, re-runnable record of a fire season, per named
party.

**Objectives** —
- supply `--zones` and `--zone-field` from a KLHK forest-designation layer
- read the Markdown record and the two-panel map
- explain why the scenario **refuses to run** without a zone layer
- recognise a censored crossing date

**Run**
```bash
earthchange -s fire-record --admin Ketapang -n Ketapang \
  --season 2019-05-04:2019-11-30 \
  --zones data/forest.gpkg --zone-field FUNGSI_HTN
```

**Explain** — "Southern Kalimantan is red" has no addressee. "Cagar Alam crossed
Tinggi on 17 August, 1,994 hotspots followed, 22,224 ha burned — 14.5% of it,
the largest proportional loss of any designation" does. That is why `--zones` is
mandatory: a record with no named party is the artefact that already exists and
gets ignored.

Also teach the window trap: too short and every zone appears to cross on day
one, because that is the window's left edge, not a finding.

**Deliverable** — A Markdown record that a journalist or auditor could check.

---

### Arc 3 — Who is affected (episodes 8–9)

---

#### Episode 8 · Finding today's usable date
*Menemukan tanggal yang bisa dipakai hari ini*

**Runtime** 9 min · **Prerequisite** episode 5

**Aim** — Make the viewer independent of any date written in these videos.

**Objectives** —
- explain that six archives end on six different days
- read the error messages, which name the last complete day
- pick an `--end` that satisfies the whole chain

**Explain** — ERA5-Land about a week behind; ERA5 hourly the same but its
trailing day arrives a few hours at a time; GDAS1 published weekly in arrears;
FIRMS a day or two; CAMS a *forecast*, so it runs **ahead**; MODIS burned area
three months. The binding date is not "the newest data" but the newest day for
which `--end` plus `--track-hours` is *fully* covered.

Show the real refusals:
```
ERA5 100 m wind holds 48 hourly images where this run needs 49.
The last complete day is 2026-08-03. End the run on or before it.
```

**Deliverable** — A habit, not a file. This is the episode that keeps the rest
of the series usable after it ages.

---

#### Episode 9 · Who breathed it, and where the smoke went
*Siapa yang menghirupnya, dan ke mana asapnya pergi*

**Runtime** 20 min · **Prerequisite** episode 8

**Aim** — Connect fire to population, and source to receptor.

**Objectives** —
- run `smoke-exposure` and explain a person-day
- run `smoke-track` forward, and read it as an illustration
- run it backward with HYSPLIT, and explain why that one is defensible
- install HYSPLIT, including the macOS quarantine step

**Run**
```bash
earthchange -s smoke-exposure --bbox 108.8,-4.3,117.0,2.2 -n Kalimantan \
  --season 2019-08-01:2019-11-30 --pop-year 2020

earthchange -s smoke-track --bbox 108.8,-4.3,117.0,2.2 -n Kalimantan \
  --date 2019-09-15 --engine hysplit --direction backward
```

**Explain** — A person-day is one person, one day: 40,000 people for 3 days is
120,000 person-days, which is how a long moderate episode is compared with a
short severe one.

Why the kinematic engine says *illustration, not attribution* and the HYSPLIT
one does not — and the measurement behind it: on the same day with the same
seeds, HYSPLIT paths run **25% farther** and reach **seven districts the
kinematic run never touches, and none in reverse**. Those seven are the
populated northwest coast. The single-level fan does not merely lose precision;
**it under-reaches in one direction, and that direction is where the people
are.**

**Deliverable** — The finding that fires and exposure are in different places.

---

### Arc 4 — Putting it together (episodes 10–12)

---

#### Episode 10 · The whole chain in one command
*Seluruh rantai dalam satu perintah*

**Runtime** 15 min · **Prerequisite** episodes 5–9

**Aim** — Run a complete assessment and understand its causal order.

**Objectives** —
- run `earthchain` end to end
- explain why the order is causal, not arbitrary
- know why `fire-record` is not in the default step list
- use `--dry-run` to lift a single step out

**Run**
```bash
earthchain --end 2019-11-30 --admin Ketapang --name Ketapang \
  --zones data/forest.gpkg --zone-field FUNGSI_HTN \
  --wide 107.0,-4.0,115.0,3.0 --steps 1,2,3,4,5,6,7,8
```

**Explain** — It dried → it became dangerous → the strictest designation was
driest → the smoke left → it landed on cities → it crossed a border. One `--end`
drives every derived date.

**Deliverable** — Seven folders, eighteen figures, forty-seven GeoTIFFs.

---

#### Episode 11 · Turning it into something you can hand over
*Menjadikannya sesuatu yang bisa diserahkan*

**Runtime** 14 min · **Prerequisite** episode 10

**Aim** — Go from evidence base to deliverable.

**Objectives** —
- run `earthbrief` and read the assembled argument
- know which six figures carry it, and why the other twelve do not
- adapt the brief for three audiences
- take the GeoTIFFs into QGIS

**Explain** — Nobody reads eighteen figures. Six carry the argument, in the
chain's own order. The rest are the evidence base and belong in an appendix.
Operational readers want steps 2–3; accountability readers want the record;
press want the exposure map and the trajectories.

**Emphasise** — The brief writes the numbers and the caveats. It cannot write
the sentence that matters: *the province with the hazard is not the province
with the burden*. That is the viewer's job.

**Deliverable** — `brief.md` and a self-contained `brief.html`.

---

#### Episode 12 · Saying what your number does not show
*Mengatakan apa yang tidak ditunjukkan angka Anda*

**Runtime** 16 min · **Prerequisite** episode 11

**Aim** — Make the viewer's work survive being challenged.

**Objectives** —
- find and read the `note` field in every `stats.json`
- state the four limits that matter most in this domain
- know when to escalate to HYSPLIT dispersion or FLEXPART
- re-run someone else's result from their `run_id`

**Explain, one at a time** —
- hotspot counts are **pixel-days, not fires and not area**; one fire seen on
  four days counts four times
- MODIS burned area **under-detects smouldering peat** and is a lower bound
- outdoor concentration is **not inhaled dose**; person-days are a hazard count,
  not a health outcome
- a trajectory **does not spread or deposit**, so crossing a district is not the
  same as depositing smoke on it
- CAMS at ~44 km is **coarser than most districts**, so zooming in adds
  interpolation, not information

**Deliverable** — A viewer who can be argued with and hold their ground.

---

## Production notes

**Reproducibility.** Teaching examples use **2019 Kalimantan** and
**2019 Ketapang** throughout — a closed season, so every number a viewer sees
will still be true years from now. Only episodes 2 and 8 use live dates, and
episode 8 exists precisely to teach that skill.

**Show the failures.** The refusal messages are among the best-designed parts of
the package and they teach the domain: the ERA5 hour-count error explains
reanalysis latency better than a slide would. Do not edit them out.

**Bilingual.** Narrate in Bahasa Indonesia; keep commands, flags and output in
English, since that is what viewers will type and see. Burn in Indonesian
subtitles for the explanation segments.

**Runtime.** Twelve episodes, roughly 2 hours 45 minutes total. Nothing over
20 minutes.

**Split for social.** Each episode yields one 60-second cut for X or Instagram:
the DC 293 / FWI 5.9 contrast, the fires-and-exposure-in-different-places map,
the 25% under-reach measurement. These are data-forward and stand alone.

**What to record.** Terminal at large font, output folder in a file manager, and
the figures full-screen. Avoid slides except for the FWI component diagram in
episode 5 and the causal chain in episode 10.

---

## Open questions for the author

1. **Ketapang or a viewer's own district as the running example?** Ketapang is
   well-characterised through the whole series, but a viewer may engage more
   with somewhere they know. Suggest: Ketapang throughout, with episode 3 as the
   "now do your own" moment.
2. **How much QGIS?** Currently one segment in episode 11. Could be its own
   episode if the audience is GIS-first.
3. **Should episode 7 require a zone layer the viewer may not have?** The KLHK
   forest layer is not redistributable. Consider shipping a small synthetic
   example layer for teaching.
4. **English-narrated version?** The commands and outputs are already English;
   only the narration would need re-recording.
