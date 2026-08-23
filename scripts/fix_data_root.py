"""Point data/ and output/ at the external SSD, leaving code where it is.

Those two trees are about 63 GB each and the internal disk has run as low as
12 GiB free, so they belong on the external volume. Everything else -- code,
docs, figures -- stays with the checkout it is run from, which is what
_REPO_ROOT already does.

So this is deliberately NOT a blanket redirect. It rewrites only the path
joins that address data/ or output/:

    os.path.join(_REPO_ROOT, "data/x")   -> os.path.join(_DATA_ROOT, "data/x")
    _REPO_ROOT + "/output/x"             -> _DATA_ROOT + "/output/x"

and leaves docs/, scripts/ and bare _REPO_ROOT references untouched.

_DATA_ROOT RESOLVES AT RUNTIME, in three steps, so an unmounted volume
degrades instead of crashing:

    RSCD_DATA_ROOT if set        -- an explicit override for other machines
    the SSD path if it exists    -- the normal case here
    _REPO_ROOT otherwise         -- SSD unplugged; falls back to local

Hardcoding the SSD path alone would make every script fail on a machine that
has never seen that volume, and silently write to the wrong disk if it were
ever mounted elsewhere.

    python3 scripts/fix_data_root.py            # dry run
    python3 scripts/fix_data_root.py --apply
"""

import argparse
import ast
import glob
import os
import re
import sys

SSD = "/Volumes/ExtremeSSD/Dropbox/GitHub/rs-change-detection"

DEFN = '''
# data/ and output/ are ~63 GB each and live on the external SSD; the internal
# disk has run to 12 GiB free. Resolved at runtime so an unmounted volume
# falls back to this checkout instead of failing.
_SSD_ROOT = "%s"
_DATA_ROOT = (os.environ.get("RSCD_DATA_ROOT")
              or (_SSD_ROOT if os.path.isdir(_SSD_ROOT) else _REPO_ROOT))
''' % SSD

PATTERNS = [
    (re.compile(r'os\.path\.join\(\s*_REPO_ROOT\s*,\s*"(data|output)'),
     lambda m: m.group(0).replace("_REPO_ROOT", "_DATA_ROOT")),
    (re.compile(r'_REPO_ROOT\s*\+\s*"/(data|output)'),
     lambda m: m.group(0).replace("_REPO_ROOT", "_DATA_ROOT")),
]


def insert_defn(src):
    if "_DATA_ROOT =" in src:
        return src, False
    lines = src.splitlines(keepends=True)
    # Anchor on the _REPO_ROOT assignment, which the earlier migration placed
    # after the import block; _DATA_ROOT references it, so it must follow.
    idx = None
    for i, ln in enumerate(lines):
        if ln.startswith("_REPO_ROOT ="):
            idx = i
    if idx is None:
        return src, False
    lines.insert(idx + 1, DEFN)
    return "".join(lines), True


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dir", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "scripts"))
    a = ap.parse_args()

    changed, failed = [], []
    for f in sorted(glob.glob(os.path.join(a.dir, "*.py"))):
        if os.path.basename(f) in ("fix_data_root.py", "fix_repo_paths.py"):
            continue
        src = open(f).read()
        new, n = src, 0
        for rx, fn in PATTERNS:
            new, k = rx.subn(fn, new)
            n += k
        if not n:
            continue
        new, added = insert_defn(new)
        if not added and "_DATA_ROOT =" not in new:
            failed.append((f, "no _REPO_ROOT assignment to anchor to"))
            continue
        try:
            ast.parse(new)
        except SyntaxError as e:
            failed.append((f, f"would not parse: {e}"))
            continue
        changed.append((f, n))
        if a.apply:
            open(f, "w").write(new)

    for f, n in changed:
        print(f"  {n:>2} path(s)  {os.path.basename(f)}")
    print(f"\n{len(changed)} files, "
          f"{sum(n for _, n in changed)} redirected joins")
    if failed:
        print(f"\n{len(failed)} SKIPPED:")
        for f, why in failed:
            print(f"  {os.path.basename(f)}: {why}")
    print("\napplied" if a.apply else "\ndry run — rerun with --apply")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
