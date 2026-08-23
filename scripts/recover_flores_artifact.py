"""Rebuild the artifact source and its figures from the published page.

WHY THIS EXISTS. The artifact source, its template, five figures and three
build scripts were written into the external-SSD checkout and never
committed. Something mirrors the home checkout onto the SSD one and deletes
whatever is not in the source, so the next sync erased all of it. The only
surviving copy of the design was the published artifact itself.

The published HTML carries the five figures inline as WebP data URIs, so both
the page and the imagery can be recovered from it. This script:

  strips the platform's injected frame-runtime preamble, which is prepended at
  publish time and is not part of the source;

  extracts each data URI back to docs/figures/*.png;

  replaces them with {{FIGn}} placeholders to reconstitute the template that
  build_flores_artifact.py consumes.

The recovered figures are WebP-decoded, so they are not bit-identical to the
matplotlib originals -- quality 82, resized to 1500 px wide. They are fine for
the page and for re-rendering pages from it. Regenerating pristine figures
needs flores_report_figures.py, which is gone and would have to be rewritten.

    python3 scripts/recover_flores_artifact.py --src <saved-artifact.html>
"""

import argparse
import base64
import io
import os
import re
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(_REPO_ROOT, "docs")

# Order matters: the placeholders are re-inserted in document order, which is
# the order the template declared them.
NAMES = ["fig1_ascending_los", "fig2_profiles", "fig3_descending",
         "fig4_coherence", "fig5_coverage"]
START = "<title>The Flores Shortfall</title>"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", required=True,
                    help="the artifact HTML saved by the read action")
    a = ap.parse_args()

    if not os.path.exists(a.src):
        sys.exit(f"no such file: {a.src}")
    raw = open(a.src, encoding="utf-8", errors="replace").read()

    i = raw.find(START)
    if i < 0:
        sys.exit("could not find the source start marker; "
                 "was this page published from this template?")
    body = raw[i:]
    # The platform closes the document it opened; our source did not.
    for tail in ("</body></html>", "</body>\n</html>", "</html>"):
        if body.rstrip().endswith(tail):
            body = body.rstrip()[: -len(tail)].rstrip() + "\n"
            break

    uris = re.findall(r'src="(data:image/webp;base64,[A-Za-z0-9+/=]+)"', body)
    print(f"found {len(uris)} embedded figures")
    if len(uris) != len(NAMES):
        print(f"  WARNING: expected {len(NAMES)}; naming what is present")

    from PIL import Image
    os.makedirs(os.path.join(DOCS, "figures"), exist_ok=True)
    template = body
    for n, uri in enumerate(uris):
        name = NAMES[n] if n < len(NAMES) else f"fig{n+1}_recovered"
        blob = base64.b64decode(uri.split(",", 1)[1])
        im = Image.open(io.BytesIO(blob)).convert("RGB")
        out = os.path.join(DOCS, "figures", name + ".png")
        im.save(out, optimize=True)
        print(f"  {name:<22} {im.width}x{im.height}  "
              f"{os.path.getsize(out)/1e3:.0f} kB")
        token = "{{" + (NAMES[n].split("_")[0].upper()
                        if n < len(NAMES) else f"FIG{n+1}") + "}}"
        template = template.replace(uri, token, 1)

    built = os.path.join(DOCS, "flores_artifact.html")
    tmpl = os.path.join(DOCS, "flores_artifact.template.html")
    open(built, "w").write(body)
    open(tmpl, "w").write(template)
    left = len(re.findall(r"data:image/webp", template))
    print(f"\nwrote {built}  ({os.path.getsize(built)/1e6:.2f} MB)")
    print(f"wrote {tmpl}  ({os.path.getsize(tmpl)/1e3:.0f} kB, "
          f"{left} data URIs remaining)")
    if left:
        print("  WARNING: some images were not turned back into placeholders")
    return 0


if __name__ == "__main__":
    sys.exit(main())
