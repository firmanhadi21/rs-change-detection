#!/usr/bin/env python3
"""fire-brief — turn a chain run into one thing you can hand to somebody.

A full fire-and-smoke chain leaves seven folders, eighteen figures and sixteen
GeoTIFFs. That is a good evidence base and a bad deliverable: nobody reads
eighteen figures, and a reader given all of them cannot tell which six carry the
argument.

This assembles the argument. The chain's order is already causal -- it dried,
it became dangerous, the strictest designation was driest, the smoke left, it
landed on cities, it crossed a border -- so the brief walks that order, pulls
the numbers from each step's stats.json rather than restating them by hand, and
puts one figure under each claim.

Two outputs, because they are for different moments:

  brief.md    to paste into an email or a repository, images by relative path
  brief.html  self-contained, images inlined -- one file that survives being
              forwarded, which a folder of PNGs does not

What it deliberately leaves out: the CDI component maps, BUI and FWI panels, the
haze timeline, the exposure ranking chart. They are evidence, not argument, and
including them dilutes the six that matter. They stay in the run folder.

Every step's stats.json carries a `note` -- trajectories are not dispersion,
MODIS burned area is a lower bound, outdoor concentration is not inhaled dose.
Those are carried through verbatim. They are what make the numbers survive being
challenged, and a brief that drops them has thrown away the best part.

Usage:
    earthbrief output/chain
    earthbrief output/chain --title "Ketapang, Agustus 2026" --lang en
"""

import argparse
import base64
import datetime as dt
import glob
import json
import os

# Which figure carries each step's claim. First match wins, so the map is
# preferred over the chart wherever a step produces both.
FIGURE = {
    "drought": ("*peta_kekeringan*.png", "*drought_map*.png", "*peta_hujan*.png"),
    "fire-danger": ("*_dc.png",),
    "smoke-track:forward": ("*_smoke_track.png",),
    "smoke-exposure": ("*_exposure_map.png",),
    "smoke-track:backward": ("*_smoke_track.png",),
    "fire-record": ("*_fire_record_map.png", "*_fire_record.png"),
}

ORDER = ["drought", "fire-danger", "fire-record", "smoke-track:forward",
         "smoke-exposure", "smoke-track:backward"]

HEAD = {
    "id": {
        "drought": "1 · Apakah kering?",
        "fire-danger": "2 · Seberapa berbahaya, dan di kawasan siapa?",
        "fire-record": "3 · Kapan ambang dilampaui?",
        "smoke-track:forward": "4 · Ke mana asapnya pergi?",
        "smoke-exposure": "5 · Siapa yang menghirupnya?",
        "smoke-track:backward": "6 · Dari mana udara mereka datang?",
    },
    "en": {
        "drought": "1 · Was it dry?",
        "fire-danger": "2 · How dangerous, and on whose land?",
        "fire-record": "3 · When were the thresholds crossed?",
        "smoke-track:forward": "4 · Where did the smoke go?",
        "smoke-exposure": "5 · Who breathed it?",
        "smoke-track:backward": "6 · Where did their air come from?",
    },
}


def _key(st):
    """Steps are identified by scenario, and direction where it matters."""
    s = st.get("scenario", "")
    if s == "smoke-track":
        return f"{s}:{st.get('direction', 'forward')}"
    return s


def load(run_dir):
    """Every step in a chain run, keyed by scenario, with its chosen figure."""
    steps = {}
    for p in sorted(glob.glob(os.path.join(run_dir, "*", "stats.json"))):
        try:
            st = json.load(open(p))
        except Exception:                                          # noqa: BLE001
            continue
        d = os.path.dirname(p)
        k = _key(st)
        fig = None
        for pat in FIGURE.get(k, ()):
            hit = sorted(glob.glob(os.path.join(d, pat)))
            if hit:
                fig = hit[0]
                break
        steps[k] = {"stats": st, "dir": d, "figure": fig}
    return steps


# --------------------------------------------------------------------------
# One claim per step, built from the numbers rather than restated by hand
# --------------------------------------------------------------------------

def _n(x, nd=0):
    return f"{x:,.{nd}f}" if isinstance(x, (int, float)) else "—"


def _ordinal(n):
    """1st, 2nd, 3rd, 4th … including the 11th-13th exceptions."""
    if not isinstance(n, int):
        return str(n)
    if 11 <= n % 100 <= 13:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }".replace(
        " ", "")


def _claim_drought(s, lang):
    r = s.get("rainfall", {}) or {}
    v = s.get("vegetation", {}) or {}
    rank, yrs = s.get("rank_driest_of_record"), s.get("years_in_record")
    bits = []
    if r.get("pct_of_normal") is not None:
        bits.append(
            f"Curah hujan {_n(r.get('current_mm'))} mm, "
            f"**{_n(r.get('pct_of_normal'))}% dari normal** "
            f"({_n(r.get('normal_mm'))} mm), z {r.get('z')} — {r.get('class')}."
            if lang == "id" else
            f"Rainfall {_n(r.get('current_mm'))} mm, "
            f"**{_n(r.get('pct_of_normal'))}% of normal** "
            f"({_n(r.get('normal_mm'))} mm), z {r.get('z')} — {r.get('class')}.")
    if rank and yrs:
        bits.append(f"Peringkat terkering ke-{rank} dari {yrs} tahun."
                    if lang == "id" else
                    f"The {_ordinal(rank)} driest in {yrs} years of record.")
    if v.get("vhi") is not None:
        bits.append(
            f"Namun VHI {_n(v.get('vhi'))} — {v.get('class')}: vegetasi belum "
            "tertekan. Pengeringan dalam tanpa tanda di permukaan adalah pola "
            "gambut."
            if lang == "id" else
            f"Yet VHI {_n(v.get('vhi'))} — {v.get('class')}: the vegetation is "
            "not stressed. Deep drying without a surface signal is the peat "
            "pattern.")
    return " ".join(bits)


def _claim_danger(s, lang):
    dc = (s.get("indices", {}) or {}).get("DC")
    pct = s.get("dc_class_pct", {}) or {}
    fwi = s.get("fwi_class_pct", {}) or {}
    pocket = s.get("dry_pocket", {}) or {}
    bits = []
    if dc is not None:
        bits.append(f"Drought Code **{_n(dc, 1)}** pada {s.get('date')}."
                    if lang == "id" else
                    f"Drought Code **{_n(dc, 1)}** on {s.get('date')}.")
    hi = (pct.get("Tinggi") or 0) + (pct.get("Ekstrem") or 0)
    if hi:
        bits.append(f"**{_n(hi)}% wilayah pada kelas Tinggi atau lebih** (DC); "
                    f"FWI Ekstrem {_n(fwi.get('Ekstrem') or 0)}%."
                    if lang == "id" else
                    f"**{_n(hi)}% of the area at Tinggi or above** on DC; "
                    f"FWI Ekstrem {_n(fwi.get('Ekstrem') or 0)}%.")
    if pocket.get("area_ha"):
        bits.append(
            f"Sepersepuluh terkering: {_n(pocket['area_ha'])} ha di sekitar "
            f"{pocket.get('centroid_lat')}, {pocket.get('centroid_lon')}."
            if lang == "id" else
            f"Driest tenth: {_n(pocket['area_ha'])} ha around "
            f"{pocket.get('centroid_lat')}, {pocket.get('centroid_lon')}.")
    worst = _driest_zone(s)
    if worst:
        nm, share = worst
        bits.append(f"Kawasan terkering: **{nm}**, {_n(share)}% pada Tinggi."
                    if lang == "id" else
                    f"Driest designation: **{nm}**, {_n(share)}% at Tinggi.")
    return " ".join(bits)


MIN_ZONE_SHARE = 0.01      # of the total zoned area


def _material(entries, area_key):
    """Drop zones too small to headline a brief.

    A designation layer contains slivers -- LAUT/AIR came to 276 ha against a
    3.4 million ha district, and being a puddle it had the highest Drought Code
    of any zone. Ranked naively it becomes the finding, which is both absurd and
    the kind of thing that discredits everything around it.
    """
    total = sum((r.get(area_key) or 0) for r in entries.values()
                if isinstance(r, dict))
    floor = total * MIN_ZONE_SHARE
    return {nm: r for nm, r in entries.items()
            if isinstance(r, dict) and (r.get(area_key) or 0) >= floor}


def _driest_zone(s):
    """The designation with the largest share at Tinggi or above."""
    z = ((s.get("zones") or {}).get("zones")) or {}
    if not isinstance(z, dict):
        return None
    best = None
    for nm, row in _material(z, "total_ha").items():
        p = row.get("pct_by_class") or {}
        share = (p.get("Tinggi") or 0) + (p.get("Ekstrem") or 0)
        if share and (best is None or share > best[1]):
            best = (nm, share)
    return best


def _claim_record(s, lang):
    zones = _material(s.get("zones", {}) or {}, "area_ha")
    top = None
    for nm, r in zones.items():
        if r.get("dc_peak") is not None:
            if top is None or r["dc_peak"] > top[1].get("dc_peak", -1):
                top = (nm, r)
    if not top:
        return ""
    nm, r = top
    crossed = r.get("first_crossed", {}) or {}
    cens = r.get("first_crossed_censored", {}) or {}
    when = [f"{lvl} {d}{' (sebelum)' if cens.get(lvl) else ''}"
            for lvl, d in crossed.items() if d]
    bits = [f"**{nm}** memuncak pada DC {_n(r.get('dc_peak'))} "
            f"({r.get('dc_class_at_peak')})." if lang == "id" else
            f"**{nm}** peaked at DC {_n(r.get('dc_peak'))} "
            f"({r.get('dc_class_at_peak')})."]
    if when:
        bits.append(("Ambang dilampaui: " if lang == "id"
                     else "Thresholds crossed: ") + "; ".join(when) + ".")
    if r.get("hotspots_total"):
        bits.append(f"{_n(r['hotspots_total'])} titik panas di dalamnya."
                    if lang == "id" else
                    f"{_n(r['hotspots_total'])} hotspots inside it.")
    if r.get("burned_ha"):
        bits.append(f"{_n(r['burned_ha'])} ha terbakar (MODIS, batas bawah)."
                    if lang == "id" else
                    f"{_n(r['burned_ha'])} ha burned (MODIS, a lower bound).")
    return " ".join(bits)


def _claim_track(s, lang):
    cr = list((s.get("districts_crossed") or {}).items())[:3]
    where = ", ".join(f"{k} ({v})" for k, v in cr)
    back = s.get("direction") == "backward"
    eng = s.get("engine")
    if back:
        rec = s.get("receptors") or []
        who = ", ".join(f"{r['name']} {r.get('pm25')} µg/m³" for r in rec[:4])
        lead = (f"Udara yang tiba pada {s.get('day')} berasal dari arah yang "
                f"melintasi {where}." if lang == "id" else
                f"Air arriving {s.get('day')} came in across {where}.")
        return " ".join([lead,
                         (f"Reseptor: {who}." if lang == "id"
                          else f"Receptors: {who}.") if rec else "",
                         (f"Mesin {eng}, panjang lintasan median "
                          f"{_n(s.get('median_path_km'))} km."
                          if lang == "id" else
                          f"{eng} engine, median path "
                          f"{_n(s.get('median_path_km'))} km.")]).strip()
    return " ".join([
        (f"Parsel dari titik api {s.get('day')} terbawa {s.get('hours')} jam "
         f"dan melintasi {where}." if lang == "id" else
         f"Parcels from the fires of {s.get('day')} travelled {s.get('hours')} h "
         f"and crossed {where}."),
        (f"Panjang lintasan median {_n(s.get('median_path_km'))} km "
         f"(mesin {eng})." if lang == "id" else
         f"Median path {_n(s.get('median_path_km'))} km ({eng} engine)."),
    ])


def _worst_districts(districts, lang, n=3):
    """The heaviest-burden list, named districts with real exposure only.

    A placeholder name or a zero has no business in a sentence that says
    "heaviest burden". On a day when only two districts have any exposure, the
    third slot otherwise fell to "Administrative unit not available (0.0M)".
    """
    from .gee_utils import is_named

    top = sorted(((k, v.get("person_days_unhealthy") or 0)
                  for k, v in districts.items()
                  if isinstance(v, dict) and is_named(k)
                  and (v.get("person_days_unhealthy") or 0) > 0),
                 key=lambda kv: -kv[1])[:n]
    unit = "juta" if lang == "id" else "M"
    return ", ".join(f"{k} ({_n(pd / 1e6, 1)}{'' if unit == 'M' else ' '}{unit})"
                     for k, pd in top)


def _claim_exposure(s, lang):
    t = s.get("totals", {}) or {}
    by = t.get("person_days_by_class", {}) or {}
    unhealthy = t.get("person_days_unhealthy")
    who = _worst_districts(s.get("districts") or {}, lang)
    bits = []
    if unhealthy:
        bits.append(
            f"**{_n(unhealthy)} person-day** pada Tidak Sehat atau lebih buruk, "
            f"atas {_n(t.get('population'))} jiwa — {_n(t.get('under5'))} balita "
            f"dan {_n(t.get('over65'))} lansia."
            if lang == "id" else
            f"**{_n(unhealthy)} person-days** at Unhealthy or worse, across "
            f"{_n(t.get('population'))} people — {_n(t.get('under5'))} under 5 "
            f"and {_n(t.get('over65'))} over 65.")
    if who:
        bits.append((f"Beban terberat: {who}." if lang == "id"
                     else f"Heaviest burden: {who}."))
    # Classes nobody spent a day in are noise in a summary; the report has them.
    hit = {k: v for k, v in by.items() if v}
    if hit:
        bits.append(("Kelas ISPU: " if lang == "id" else "By ISPU class: ")
                    + ", ".join(f"{k} {_n(v)}" for k, v in hit.items()) + ".")
    return " ".join(bits)


CLAIM = {"drought": _claim_drought, "fire-danger": _claim_danger,
         "fire-record": _claim_record, "smoke-track:forward": _claim_track,
         "smoke-track:backward": _claim_track,
         "smoke-exposure": _claim_exposure}


# --------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------

def build_markdown(steps, title, lang, run_dir):
    id_ = lang == "id"
    L = [f"# {title}", ""]
    L.append(("Disusun " if id_ else "Assembled ")
             + dt.date.today().isoformat()
             + (" dengan `earthbrief` dari keluaran `earthchange`."
                if id_ else " with `earthbrief` from `earthchange` output."))
    L.append("")
    L.append(("Setiap angka di bawah berasal dari `stats.json` langkah yang "
              "bersangkutan dan dapat dihitung ulang dengan perintah di bagian "
              "akhir." if id_ else
              "Every number below is read from that step's `stats.json` and can "
              "be recomputed with the commands at the end."))
    L.append("")

    for k in ORDER:
        step = steps.get(k)
        if not step:
            continue
        L.append(f"## {HEAD[lang][k]}")
        L.append("")
        claim = CLAIM[k](step["stats"], lang)
        if claim:
            L.append(claim)
            L.append("")
        if step["figure"]:
            rel = os.path.relpath(step["figure"], run_dir)
            L.append(f"![{HEAD[lang][k]}]({rel})")
            L.append("")

    L.append("## " + ("Batasan" if id_ else "Limits"))
    L.append("")
    L.append(("Dibawa apa adanya dari tiap langkah. Inilah yang membuat "
              "angka-angka di atas bertahan saat diuji."
              if id_ else
              "Carried verbatim from each step. These are what make the numbers "
              "above survive being challenged."))
    L.append("")
    for k in ORDER:
        step = steps.get(k)
        note = (step or {}).get("stats", {}).get("note")
        if note:
            L.append(f"- **{k}** — {note}")
    L.append("")

    L.append("## " + ("Cara menghitung ulang" if id_ else "How to recompute"))
    L.append("")
    L.append("```")
    for k in ORDER:
        step = steps.get(k)
        if step:
            L.append(f"# {k}")
            L.append(f"run_id: {step['stats'].get('run_id', '?')}")
    L.append("```")
    L.append("")
    L.append(("Raster GeoTIFF tiap langkah ada di folder yang sama dan siap "
              "dibuka di QGIS." if id_ else
              "Each step's GeoTIFFs sit in the same folder, ready for QGIS."))
    return "\n".join(L) + "\n"


CSS = """
:root { color-scheme: light dark; }
body { font: 16px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
       max-width: 62rem; margin: 3rem auto; padding: 0 1.4rem;
       background: #faf8f4; color: #1c1a17; }
h1 { font-size: 1.9rem; line-height: 1.25; margin-bottom: .3rem; }
h2 { font-size: 1.2rem; margin-top: 2.6rem; border-top: 1px solid #e2ddd4;
     padding-top: 1.1rem; }
img { width: 100%; height: auto; border: 1px solid #e2ddd4; border-radius: 4px;
      margin: 1rem 0; }
code, pre { background: #f0ece4; border-radius: 3px; }
pre { padding: .8rem 1rem; overflow-x: auto; }
code { padding: .1rem .3rem; }
li { margin: .45rem 0; }
.sub { color: #6b655c; font-size: .92rem; }
@media (prefers-color-scheme: dark) {
  body { background: #17150f; color: #eee8dd; }
  h2 { border-color: #35302a; } img { border-color: #35302a; }
  code, pre { background: #221f19; } .sub { color: #a49d92; }
}
"""


def build_html(title, md_text, run_dir):
    """Self-contained: images inlined so one file survives being forwarded."""
    import re

    body = []
    for line in md_text.splitlines():
        if line.startswith("# "):
            body.append(f"<h1>{line[2:]}</h1>")
        elif line.startswith("## "):
            body.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("- "):
            body.append(f"<li>{_inline(line[2:])}</li>")
        elif line.startswith("!["):
            m = re.match(r"!\[(.*?)\]\((.*?)\)", line)
            if m:
                body.append(_img(os.path.join(run_dir, m.group(2)),
                                 m.group(1)))
        elif line.strip() in ("```", ""):
            continue
        else:
            body.append(f"<p>{_inline(line)}</p>")
    return (f"<!doctype html><html><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{title}</title><style>{CSS}</style></head>"
            f"<body>{''.join(body)}</body></html>")


def _inline(s):
    import re
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    return re.sub(r"`(.+?)`", r"<code>\1</code>", s)


def _img(path, alt):
    """Inline one figure, resolved by PATH.

    An earlier version matched figures by basename, and both smoke-track steps
    write <name>_smoke_track.png -- so the forward figure was inlined under the
    backward heading too, and the backward one never appeared at all. The
    markdown was correct throughout, which is what made it easy to miss: the two
    outputs disagreed and only the one nobody diffs was wrong.
    """
    if not os.path.exists(path):
        return ""
    with open(path, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode()
    return f"<img alt='{alt}' src='data:image/png;base64,{b64}'>"


def run(run_dir, title=None, lang="id"):
    steps = load(run_dir)
    if not steps:
        raise SystemExit(
            f"No chain output found under {run_dir}. Expected step folders each "
            "holding a stats.json, as scripts/fire_smoke_chain.sh writes.")
    name = next((s["stats"].get("name") for s in steps.values()
                 if s["stats"].get("name")), os.path.basename(run_dir))
    title = title or (f"Kebakaran dan asap — {name}" if lang == "id"
                      else f"Fire and smoke — {name}")

    md = build_markdown(steps, title, lang, run_dir)
    md_path = os.path.join(run_dir, "brief.md")
    with open(md_path, "w") as f:
        f.write(md)
    html_path = os.path.join(run_dir, "brief.html")
    with open(html_path, "w") as f:
        f.write(build_html(title, md, run_dir))

    used = [k for k in ORDER if k in steps]
    missing = [k for k in ORDER if k not in steps]
    print(f"  {len(used)}/6 steps found: {', '.join(used)}")
    if missing:
        print(f"  not run, so left out: {', '.join(missing)}")
    print(f"\n  {md_path}")
    print(f"  {html_path}  "
          f"({os.path.getsize(html_path) / 2**20:.1f} MiB, self-contained)")
    return md_path, html_path


def main():
    ap = argparse.ArgumentParser(
        description="Assemble a fire-and-smoke chain run into one brief.",
        epilog="Example: earthbrief output/chain --lang en")
    ap.add_argument("run_dir", help="the chain output folder holding 1_… 7_…")
    ap.add_argument("--title", help="override the heading")
    ap.add_argument("--lang", choices=("id", "en"), default="id")
    a = ap.parse_args()
    run(a.run_dir, a.title, a.lang)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
