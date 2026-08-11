# Shooting scripts — *Satu Pertanyaan, Satu Perintah*

Twelve shot-by-shot scripts for the series planned in
[`../VIDEO_SERIES.md`](../VIDEO_SERIES.md). That document decides *what* the
series teaches and in what order. These decide *what is on screen and what is
said, second by second*.

| | |
|---|---|
| [EP01](EP01.md) | What this is, and what it is for · 8 min |
| [EP02](EP02.md) | An animation of the fires burning right now · 12 min |
| [EP03](EP03.md) | Detecting change without an account · 14 min |
| [EP04](EP04.md) | Getting an Earth Engine account, once · 10 min |
| [EP05](EP05.md) | Is it dangerous? Fire danger rating · 16 min |
| [EP06](EP06.md) | Was it dry first? Drought before fire · 12 min |
| [EP07](EP07.md) | The accountability record · 18 min |
| [EP08](EP08.md) | Finding today's usable date · 9 min |
| [EP09](EP09.md) | Who breathed it, and where the smoke went · 20 min |
| [EP10](EP10.md) | The whole chain in one command · 15 min |
| [EP11](EP11.md) | Turning it into something you can hand over · 14 min |
| [EP12](EP12.md) | Saying what your number does not show · 16 min |

---

## How to read a script

Every scene is a numbered block with a timecode range. Inside it:

| Tag | Meaning |
|---|---|
| **SCREEN** | What the camera or capture shows. Shot type, what is on the terminal, any motion. |
| **VO (ID)** | The spoken line, Bahasa Indonesia. **This is the take.** |
| **VO (EN)** | The same line in English — for the subtitle track, and for an English dub if one is ever recorded. Not spoken in the Indonesian cut. |
| **TYPE** | Typed on screen, verbatim. Never paraphrase; the viewer is copying it. |
| **OUTPUT** | What the terminal prints. Where it is quoted from a real run, it is marked ✓. |
| **LOWER-3** | Burnt-in graphic text: lower third, callout, or full card. |
| **NOTE** | Direction to the presenter or editor. Never spoken, never on screen. |

Scene headings read `## 4 · 03:10–04:35 · Heading`. The timecodes are a budget,
not a stopwatch — but the episode total is the contract, and nothing runs over
20 minutes.

---

## The one rule that matters

**Every number spoken on screen comes from a run that was actually made.**
Numbers in these scripts marked ✓ are quoted from `stats.json` or a `.md` report
in `output/chain/` and from the published tutorial, and the run that produced
each one is named in the script. If a re-shoot produces a different number,
**change the script, not the number.** The whole argument of this package is
that its outputs are checkable; a series that rounds a figure for narrative
convenience gives that away for nothing.

Two consequences for production:

1. **Read the number off the screen you are showing.** If the take shows
   `DC 258.8`, say two hundred fifty-nine, not "about two-sixty".
2. **When a run fails, keep the take.** See "Show the failures" below.

---

## Two worked examples, and why there are exactly two

**Ketapang, Kalimantan Barat — a live 2026 season.** Steps 1–7 of the chain were
run end to end on **9 August 2026** over Ketapang, and every episode from 5
onward draws its screens and its numbers from that one run
(`output/chain/`). Using a single coherent run rather than a fresh one per
episode is deliberate: the numbers in episode 5 are the same numbers the viewer
will see again in episode 10, and the argument accumulates.

**30 September 2015 and 20 October 2019 — closed history.** Used only in
episode 5, for the two teaching contrasts that need a season whose outcome is
already known and can never change.

Everything else — the viewer's own district — is theirs.

---

## The terminal

- **Font 20 pt or larger.** Assume a phone screen. Anything a viewer has to
  squint at is a viewer who stops copying and starts watching.
- **80 columns, dark background, no theme with a busy prompt.** Set
  `PS1='$ '`. A prompt with a git branch and a hostname in it is noise that
  every viewer has to mentally subtract.
- **Never speed up a command that is thinking.** Cut to the result, or hold and
  talk over the wait — but a 4× ramp on a progress bar teaches viewers to expect
  a run that finishes in eight seconds. Say the real duration out loud.
- **Show the run directory in a file manager** at least once per episode. Most
  of this audience will not find the outputs otherwise.

## Bilingual policy

Narration is **Bahasa Indonesia**. Commands, flags, filenames and terminal
output stay **English**, because that is what the viewer will type and see —
translating a flag name in narration and not on screen would strand them.
Burn in Indonesian subtitles for every explanation segment.

The package's own report text follows `--lang`, and the chain run used `--lang
id`, so the reports on screen are in Indonesian while the terminal around them
is English. Say so once, in episode 5, and never again.

## Show the failures

The refusal messages are among the best-designed parts of the package and they
teach the domain better than a slide would. **Do not edit them out, and do not
re-shoot to avoid them.** Three are scripted deliberately (episodes 4, 8 and 9);
if an unscripted one appears during a take, keep it and narrate it — an
unrehearsed recovery is the most useful thing in any tutorial.

## Deliverables per episode

- 1 master cut, 1080p minimum, Indonesian subtitles burnt in
- 1 vertical 60-second cut for X / Instagram (the "social pull" named at the
  foot of each script)
- The exact commands as a copy-paste block in the description
- The `run_id` of every run shown, so a viewer can ask what produced a figure

---

## Recurring graphics

Build these once and reuse; they appear in more than one episode.

| ID | What it is | First used |
|---|---|---|
| `GFX-CHAIN` | The six-link causal chain: dry → dangerous → burning → smoke leaves → smoke lands → smoke crosses a border | EP01, full in EP10 |
| `GFX-FWI` | The FWI component tree: FFMC + DMC + DC → ISI + BUI → FWI, with time constants on each branch | EP05 |
| `GFX-LAG` | Six archive timelines against today's date, each ending on a different day | EP08 |
| `GFX-BACKEND` | The scenario table split by backend: no account / MPC / Earth Engine | EP01, EP04 |
| `GFX-PERSONDAY` | 40,000 people × 3 days = 120,000 person-days | EP09 |

Keep one visual grammar across all five: hazard in orange (`#e6550d`), burden
and population in purple (`#4d004b`), so a viewer reads which is which before
the narration says it.
