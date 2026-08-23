"""Render docs/flores_artifact.html to paginated PNGs via headless Chrome.

The design lives in HTML and CSS, so the pages are captured from it rather
than rebuilt in matplotlib -- a reimplementation would lose the typography,
the palette and the layout, which are the point of a designed version.

HOW THE PAGE BREAKS ARE CHOSEN. Not by slicing a tall image into equal
strips, which cuts through figures and mid-sentence. A measuring pass runs
first: Chrome loads the page with an injected script that records the pixel
offset of every top-level section, dumps the DOM, and those offsets become the
cut lines. Sections are grouped so each PNG is a coherent spread.

Two Chrome details that matter:

  --virtual-time-budget is required, or --dump-dom returns the DOM before the
  injected script has run and before webfonts have settled.

  --hide-scrollbars, or a 15 px gutter appears down the right edge of every
  capture.

    conda run -n insardev-test python scripts/render_artifact_pages.py
    conda run -n insardev-test python scripts/render_artifact_pages.py --theme dark
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(_REPO_ROOT, "docs")
SRC = os.path.join(DOCS, "flores_artifact.html")
OUTDIR = os.path.join(DOCS, "pages")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# Which top-level blocks open each page. Block 0 is the hero.
GROUPS = [[0, 1], [2, 3], [4, 5], [6, 7]]

MEASURE = """
<style>
  html,body{background:%(bg)s !important}
  /* Freeze the hero animation so repeated runs are reproducible. */
  *{animation:none !important; transition:none !important}
</style>
<script>
window.addEventListener('load', function(){
  setTimeout(function(){
    var els = document.querySelectorAll('.wrap > *');
    var out = [];
    for (var i = 0; i < els.length; i++){
      var r = els[i].getBoundingClientRect();
      out.push(Math.round(r.top + window.scrollY) + ':' +
               Math.round(r.bottom + window.scrollY));
    }
    var m = document.createElement('div');
    m.id = 'measure-out';
    m.textContent = 'OFFSETS[' + out.join(',') + ']TOTAL[' +
                    document.documentElement.scrollHeight + ']';
    document.body.appendChild(m);
  }, 900);
});
</script>
"""


def chrome(args, timeout=240):
    return subprocess.run([CHROME, "--headless=new", "--disable-gpu",
                           "--hide-scrollbars", "--force-color-profile=srgb",
                           *args], capture_output=True, text=True,
                          timeout=timeout)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--width", type=int, default=1240)
    ap.add_argument("--scale", type=int, default=2,
                    help="device pixel ratio; 2 gives retina-sharp text")
    ap.add_argument("--theme", default="light", choices=["light", "dark"])
    ap.add_argument("--outdir", default=OUTDIR)
    ap.add_argument("--pad", type=int, default=28)
    a = ap.parse_args()

    if not os.path.exists(CHROME):
        sys.exit(f"Chrome not found at {CHROME}")
    if not os.path.exists(SRC):
        sys.exit(f"no artifact HTML at {SRC}")

    html = open(SRC).read()
    bg = "#eef1f4" if a.theme == "light" else "#10141c"
    inject = (MEASURE % {"bg": bg}) + \
        f'<script>document.documentElement.setAttribute(' \
        f'"data-theme","{a.theme}");</script>'
    html = inject + html

    tmp = tempfile.mkdtemp(prefix="floresrender_")
    try:
        page = os.path.join(tmp, "page.html")
        open(page, "w").write(html)
        url = "file://" + page

        r = chrome([f"--window-size={a.width},1200",
                    "--virtual-time-budget=12000", "--dump-dom", url])
        m = re.search(r"OFFSETS\[([^\]]*)\]TOTAL\[(\d+)\]", r.stdout or "")
        if not m:
            sys.exit("measuring pass failed; Chrome returned no offsets")
        spans = [tuple(int(x) for x in s.split(":"))
                 for s in m.group(1).split(",") if ":" in s]
        total = int(m.group(2))
        print(f"{len(spans)} top-level blocks, page height {total} px")

        shot = os.path.join(tmp, "full.png")
        r = chrome([f"--window-size={a.width},{total}",
                    f"--force-device-scale-factor={a.scale}",
                    "--virtual-time-budget=12000",
                    f"--screenshot={shot}", url])
        if not os.path.exists(shot):
            sys.exit(f"screenshot failed: {(r.stderr or '')[-400:]}")

        from PIL import Image
        im = Image.open(shot)
        print(f"captured {im.width} x {im.height} px (scale {a.scale}x)")
        s = a.scale
        os.makedirs(a.outdir, exist_ok=True)

        for n, grp in enumerate(GROUPS, start=1):
            grp = [i for i in grp if i < len(spans)]
            if not grp:
                continue
            top = max(0, spans[grp[0]][0] - a.pad)
            bot = min(total, spans[grp[-1]][1] + a.pad)
            box = (0, top * s, im.width, min(im.height, bot * s))
            if box[3] <= box[1]:
                print(f"  page {n}: empty range, skipped")
                continue
            out = os.path.join(a.outdir, f"flores_page{n}_{a.theme}.png")
            im.crop(box).save(out, optimize=True)
            print(f"  page {n}: blocks {grp}  {box[3]-box[1]} px  -> "
                  f"{os.path.basename(out)}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
