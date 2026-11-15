# earthchange for ordinary staff: QGIS plugin with a chat assistant

Status: plan, not yet built (2026-11-15).

## Why

earthchange exists so that staff with limited remote-sensing and GIS skills can run common, repetitive
analyses (deforestation, flood, burn area, urban growth, mining) and get a finished, cited result.

General GIS applications such as QGIS, GeoLibre and RustGIS give users a workspace: the user chooses the
data, the method and the thresholds. earthchange gives the answer. The remote-sensing decisions (sensor,
cloud masking, Sentinel-1 orbit consistency, thresholds, area statistics, stated limits) are built into each
scenario. That know-how is the niche; earthchange should not try to become another map viewer.

## Requirements

- Staff use only our app. No AI account, no Earth Engine account, no GIS or Python skills.
- Staff can ask in plain Indonesian ("Berapa luas banjir di Pining setelah 8 November?").
- **Analyses run locally, on the staff member's computer, not on our server.**
- Our server only does the language part, with our own LLM (DeepSeek Flash).

## Architecture

```
Office computer (all the analysis)                 Project server (language only)
┌───────────────────────────────────────┐          ┌───────────────────────────┐
│ QGIS + earthchange plugin             │ 1. text  │ small proxy               │
│  chat: "Banjir di Pining 8 Nov?" ─────┼────────► │  → DeepSeek Flash API     │
│                                       │          │  function calling only    │
│  ◄────────────────────────────────────┼──────────│                           │
│  2. {"scenario":"flood",              │          └───────────────────────────┘
│      "area":"Kec. Pining",            │            a few hundred tokens per
│      "event_date":"2026-11-08"}       │            request, no satellite data
│  3. confirmation card → [Ya]          │
│  4. local earthchange runs ───────────┼──► Planetary Computer / Earth Engine
│  5. layers + report on the QGIS map   │
└───────────────────────────────────────┘
```

### Flow

1. The staff member types a request in the plugin's chat panel. The plugin sends the text, the tool
   definitions and, if relevant, the current map extent or selected polygon to the proxy.
2. The LLM returns a proposed tool call, e.g.
   `run_analysis(scenario="flood", area="Kec. Pining, Gayo Lues", event_date="2026-11-08")`.
   It never writes code and never sets thresholds.
3. The plugin shows a confirmation card with the parsed parameters ("Analisis banjir · Kec. Pining ·
   sebelum 1–31 Okt · sesudah 8–12 Nov. Jalankan?"). This catches model mistakes before processing time
   is spent.
4. The plugin runs earthchange **locally** as a background task (QgsTask) with a progress bar.
5. Results are added to the QGIS map as styled layers, with hectares, the report and the limits text.
   A short summary goes back to the LLM so it can phrase the answer.

## Design decisions

### 1. earthchange runs in its own local Python, separate from QGIS's Python

QGIS (especially on Windows) ships its own Python; installing rasterio, Earth Engine and STAC tools into it
is fragile and breaks on QGIS updates. Instead:

- The installer ships a self-contained earthchange runtime (conda-pack or pixi) in its own folder.
- The plugin calls it as a separate process: `earthchange run --params job.json --out <folder>`.
- The plugin itself uses only what QGIS already provides.

### 2. The LLM only fills in a short form

- Tools take only: scenario (fixed list), area (must resolve to a known boundary or a user layer), dates.
- earthchange validates every value before running.
- Small, fast models sometimes misread requests; narrow tools plus the confirmation card make that harmless.

### 3. Area names are resolved locally

Indonesian province / regency / sub-district boundaries (GAUL or BIG) ship with the plugin. If a name
matches several places, the plugin asks the user to choose. Existing user layers (villages, concessions)
can be used as the area.

### 4. The server proxy holds keys, not data

- The DeepSeek API key stays on the server behind a small proxy (~50–100 lines of Python).
- The plugin carries only an install token; the proxy checks it, rate-limits per install, and only allows
  earthchange tool definitions. The proxy has no terminal, file access or agent memory.
- No satellite data passes through the server.

### 5. Do not route the plugin through a general agent (e.g. Hermes)

A general agent such as Hermes Agent can expose an OpenAI-compatible API, but it executes its own tools
(terminal, files, web) **on the server** and returns only the final answer; it does not hand tool calls back
to the client. That would (a) run analyses on the server, the opposite of the requirement, and (b) put a
key to a server-side agent with full access inside every distributed plugin. Keep such agents for personal
use; the plugin talks to the model through the restricted proxy above.

### 6. Keep a plain form as a fallback

The plugin has a "Formulir" tab (scenario, area, dates) that calls the same local runner. If the proxy or
LLM is unavailable, or the user prefers clicking, the work still gets done.

## Satellite data access

- **Planetary Computer** (default): no account. The computer downloads and processes the data. A
  sub-district takes minutes and a few hundred MB; cap the area size and warn before large jobs.
- **Earth Engine** (optional): Google does the processing, lighter on the computer, but each office needs
  its own key. Start with Planetary Computer scenarios only.

## Build order

1. **earthchange single entry point**: `earthchange run --params job.json` (and a Python `run()`), with a
   standard result folder (layers as COG, statistics JSON, report in Indonesian, limits). Today the scenario
   functions take the parsed CLI arguments (`p`); wrap them so every scenario returns the same result shape.
   Start with flood and deforestation on Planetary Computer.
2. **Standalone runtime package** for Windows, separate from QGIS.
3. **QGIS plugin**: chat panel, tool definitions, confirmation card, background task, layer loading and
   styling, Form tab.
4. **Server proxy**: DeepSeek Flash, Indonesian system prompt, returns tool calls only; install tokens and
   rate limits.
5. **Test** on a normal office laptop with one office (e.g. a BPBD or forestry office), then add scenarios
   (burn area, urban growth, mining).

## Open questions

- Which boundary source to ship (GAUL vs BIG), and how far down (village level?).
- Area-size cap per scenario for older laptops.
- Report templates matching office formats (BPBD flood situation report, forestry note, fire bulletin).
- Whether some offices will supply their own Earth Engine key.
