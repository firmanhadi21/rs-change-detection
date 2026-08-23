"""Assemble docs/flores_artifact.html with the maps embedded as data URIs.

An Artifact is served under a CSP that blocks every external host except
Google Fonts, and a relative path to docs/figures/ does not resolve once the
page is published. The figures therefore have to travel inside the HTML.

They are re-encoded as WebP rather than passed through as PNG. The five
figures are about 1.6 MB of PNG and base64 inflates by a third; WebP at
quality 82 brings the whole page to a fraction of that with no visible loss on
continuous-tone maps. A figure that was mostly flat colour would be better as
PNG, but these are all imagery.

    conda run -n insardev-test python scripts/build_flores_artifact.py
"""

import argparse
import base64
import io
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(_REPO_ROOT, "docs")
TEMPLATE = os.path.join(DOCS, "flores_artifact.template.html")
OUTPUT = os.path.join(DOCS, "flores_artifact.html")

FIGS = {
    "FIG1": "fig1_ascending_los.png",
    "FIG2": "fig2_profiles.png",
    "FIG3": "fig3_descending.png",
    "FIG4": "fig4_coherence.png",
    "FIG5": "fig5_coverage.png",
}


def encode(path, max_w, quality):
    from PIL import Image
    im = Image.open(path).convert("RGB")
    if im.width > max_w:
        h = round(im.height * max_w / im.width)
        im = im.resize((max_w, h), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="WEBP", quality=quality, method=6)
    raw = buf.getvalue()
    return ("data:image/webp;base64,"
            + base64.b64encode(raw).decode("ascii")), len(raw), im.size


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max-width", type=int, default=1500,
                    help="enough for a 1180 px column on a 2x display")
    ap.add_argument("--quality", type=int, default=82)
    ap.add_argument("--out", default=OUTPUT)
    a = ap.parse_args()

    if not os.path.exists(TEMPLATE):
        sys.exit(f"no template at {TEMPLATE}")
    html = open(TEMPLATE).read()

    total = 0
    for key, name in FIGS.items():
        p = os.path.join(DOCS, "figures", name)
        if not os.path.exists(p):
            sys.exit(f"missing figure: {p}")
        uri, nbytes, size = encode(p, a.max_width, a.quality)
        before = os.path.getsize(p)
        total += nbytes
        print(f"  {name:<26} {before/1e3:>7.0f} kB PNG -> "
              f"{nbytes/1e3:>6.0f} kB WebP  {size[0]}x{size[1]}")
        token = "{{" + key + "}}"
        if token not in html:
            sys.exit(f"template has no placeholder {token}")
        html = html.replace(token, uri)

    left = [k for k in FIGS if "{{" + k + "}}" in html]
    if left:
        sys.exit(f"unsubstituted placeholders: {left}")

    open(a.out, "w").write(html)
    size = os.path.getsize(a.out)
    print(f"\nimages {total/1e6:.2f} MB, page {size/1e6:.2f} MB")
    if size > 16e6:
        sys.exit("page exceeds the 16 MB artifact limit")
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
