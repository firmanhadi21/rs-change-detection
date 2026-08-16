"""Teach an older MintPy to parse Sentinel-1C and 1D HyP3 product names.

MintPy identifies a HyP3 product by regex on the filename. Older releases were
written when Sentinel-1A and 1B were the whole constellation, so S1C and S1D
products raise

    ValueError: Failed to parse product name from filename:
        S1AD_20260603T212832_20260704T212750_..._unw_phase.tif

Not corrupt data: a parser that predates the satellites. It bites hardest on
the most RECENT acquisitions, and it breaks load_data outright rather than just
standalone prep_hyp3, because load_data calls prep_hyp3 internally.

Upgrading MintPy is the better fix where the environment allows it. Where it
does not -- a managed OpenScienceLab kernel, say -- this widens whatever
platform character class the installed version uses. Rather than assuming one
spelling, it finds the class, shows it, and rewrites it in place. If it cannot
find one it prints the relevant source so the situation is visible instead of
guessed at.

    python3 patch_mintpy_s1cd.py            # report what is there
    python3 patch_mintpy_s1cd.py --apply
"""

import argparse
import re
import shutil
import sys

# Any platform character class immediately after S1, e.g. S1[AB]{2}, S1[AB]
# repeated, or S1[A-B]{2}. Captures the class body so it can be widened.
CLASS_RE = re.compile(r"S1\[([A-Za-z\-]+)\]")
TARGET = "ABCD"

# MintPy rejects S1C/S1D in TWO places. Widening the filename regex gets past
# _get_product_name_and_type; add_hyp3_metadata then still raises
#   ValueError: Un-recognized Sentinel-1 satellite from S1D_IW_SLC__1SDV_...
# because it converts absolute to relative orbit with a per-satellite constant
# and only knows S1A and S1B. The constants below are taken from a current
# MintPy install, not derived here.
# The last satellite branch before the `else:` that raises, whatever shape it
# takes. MintPy has spelled this at least two ways --
#   elif ref_sat == 'S1B':                 rel_orbit = (abs_orbit - 202) % 175 + 1
#   elif ref_granule.startswith('S1C'):    meta['relative_orbit'] = ((abs_orbit - 172) % 175) + 1
# -- so the S1D branch is CLONED from the branch already present rather than
# written from a template. That keeps the condition style, the assignment
# target and the indentation identical to the surrounding code.
LAST_BRANCH = re.compile(
    r"(?P<ind>[ \t]+)elif (?P<cond>[^\n]*'?S1(?P<sat>[BC])'?[^\n]*):[ \t]*\n"
    r"(?P<bind>[ \t]+)(?P<body>[^\n]*(?:relative_orbit|rel_orbit)[^\n]*)\n"
    r"(?P<tail>(?:[ \t]*#[^\n]*\n)*)"          # any comment lines before else
    r"(?P=ind)else:"
)
S1D_CONSTANT = 42          # from a current MintPy install


def orbit_patch(text):
    """Add an S1D relative-orbit branch, cloned from the last one present.

    Returns None if no branch can be found, so the caller can say so instead of
    writing something invented.
    """
    m = LAST_BRANCH.search(text)
    if not m:
        return None

    cond = m.group("cond").replace(f"S1{m.group('sat')}", "S1D")
    # Swap only the leading orbit offset; the "% 175) + 1" tail must survive.
    body, n = re.subn(r"-\s*\d+", f"- {S1D_CONSTANT}", m.group("body"), count=1)
    if n != 1:
        return None

    branch = (f"{m.group('ind')}elif {cond}:\n"
              f"{m.group('bind')}{body}\n")
    # Insert ahead of any trailing comment block and the else itself.
    cut = m.start("tail") if m.group("tail") else m.end() - len("else:") - \
        len(m.group("ind"))
    return text[:cut] + branch + text[cut:]

NAMES = [
    "S1AA_20220823T212849_20220904T212850_VVP012_INT80_G_weF_455D_unw_phase.tif",
    "S1AD_20260603T212832_20260704T212750_VVP031_INT80_G_weF_4778_unw_phase.tif",
    "S1DD_20260701T101601_20260806T101603_VVR036_INT80_G_weF_1531_unw_phase.tif",
]


def selftest(module):
    fn = getattr(module, "_get_product_name_and_type", None)
    if fn is None:
        print("  (no _get_product_name_and_type to test)")
        return False
    all_ok = True
    for n in NAMES:
        try:
            _, job_type = fn(n)
            print(f"  OK   {n[:26]}...  -> {job_type}")
        except Exception as e:  # noqa: BLE001
            all_ok = False
            print(f"  FAIL {n[:26]}...  {type(e).__name__}")
    return all_ok


def show_context(text):
    """Print the lines mentioning S1 platform patterns, so the real shape is
    visible rather than inferred."""
    print("\n--- lines mentioning an S1 pattern ---")
    for i, line in enumerate(text.splitlines(), 1):
        if "S1" in line and ("re.match" in line or "r'" in line or 'r"' in line):
            print(f"  {i}: {line.strip()[:120]}")
    print("---")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    try:
        import mintpy.prep_hyp3 as m
    except ImportError:
        raise SystemExit("mintpy not importable — activate the MintPy "
                         "environment (in OpenScienceLab, switch the kernel)")

    path = m.__file__
    text = open(path).read()
    print(f"file: {path}")

    print("\ncurrent behaviour:")
    if selftest(m):
        print("\nalready parses S1C/S1D — nothing to do")
        return 0

    classes = set(CLASS_RE.findall(text))
    print(f"\nplatform character classes found: {sorted(classes) or 'NONE'}")

    todo = {c for c in classes if not set(TARGET) <= set(c.upper())}
    if not todo:
        # The class is already wide enough, so the failure is elsewhere --
        # a different regex shape, or a check further down the function.
        print("classes already include A-D, so the rejection is elsewhere.")
        show_context(text)
        raise SystemExit(
            "Cannot fix this automatically. Upgrade MintPy "
            "(pip install -U mintpy), or paste the lines above.")

    print(f"would widen: {sorted(todo)} -> {TARGET}")
    if not a.apply:
        show_context(text)
        print("\ndry run — rerun with --apply")
        return 1

    new_text = text
    for c in todo:
        new_text = new_text.replace(f"S1[{c}]", f"S1[{TARGET}]")
    if new_text == text:
        raise SystemExit("no substitution made — nothing written")

    # Site 2: the satellite -> relative-orbit table.
    if "S1D" not in new_text:
        patched = orbit_patch(new_text)
        if patched is None:
            print("  WARNING: could not find the S1B orbit branch to extend. "
                  "The filename regex will be widened, but add_hyp3_metadata "
                  "will still reject S1C/S1D.")
        else:
            new_text = patched
            print("  inserted S1C/S1D relative-orbit branches")

    # A syntax error here breaks all of MintPy, so refuse to write one.
    try:
        compile(new_text, path, "exec")
    except SyntaxError as e:
        raise SystemExit(f"patched source does not compile ({e}); "
                         f"nothing written. Upgrade MintPy instead.")

    shutil.copyfile(path, path + ".bak")
    open(path, "w").write(new_text)
    print(f"patched (backup at {path}.bak)")

    import importlib
    importlib.reload(m)
    print("\nafter patch:")
    if selftest(m):
        print("\nRestart the kernel, then rerun opensciencelab_run.py")
        return 0

    print("\nstill failing — restoring the original")
    shutil.copyfile(path + ".bak", path)
    show_context(text)
    return 1


if __name__ == "__main__":
    sys.exit(main())
