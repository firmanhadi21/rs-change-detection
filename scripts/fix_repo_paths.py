"""Replace the hardcoded ~/GitHub/rs-change-detection with the real repo root.

Twenty-nine scripts resolved their paths through
os.path.expanduser("~/GitHub/rs-change-detection"). There are two independent
clones of this repository on this machine -- one on the internal disk and one
on an external SSD -- so a script run from either wrote its outputs into the
home copy regardless. Work done from the SSD checkout silently landed
somewhere else, and because output/ is gitignored, git could never reveal the
split.

THE SUBSTITUTION. Every occurrence of the opening literal

    "~/GitHub/rs-change-detection

becomes

    _REPO_ROOT + "

which is correct for all four shapes the path appears in, including the two
that a naive regex on a whole path would break:

    expanduser("~/.../rs-change-detection")          -> _REPO_ROOT + ""
    expanduser("~/.../rs-change-detection/data/x")   -> _REPO_ROOT + "/data/x"
    expanduser(
        "~/.../rs-change-detection/output/x")        -> continuation line, fine
    expanduser("~/.../rs-change-detection/out/"
               "file.txt")                           -> adjacent literals are
                                                        joined BEFORE the +,
                                                        so this still works

expanduser() on an already-absolute path is a no-op, so the surrounding call
can stay and the diff stays small.

~/GitHub/InSARdev is deliberately untouched: it is a different repository, not
a second copy of this one.

Every modified file is compiled before being written back; a file that will
not parse is left alone and reported.

    python3 scripts/fix_repo_paths.py            # dry run
    python3 scripts/fix_repo_paths.py --apply
"""

import argparse
import glob
import os
import re
import sys

NEEDLE = '"~/GitHub/rs-change-detection'
REPLACE = '_REPO_ROOT + "'
DEFN = ('_REPO_ROOT = os.path.dirname(os.path.dirname('
        'os.path.abspath(__file__)))')


def insert_defn(src):
    """Put the definition after the last top-level import.

    Located with ast, not a regex. Matching `^(import |from )` on raw lines
    also matches inside a module docstring -- several scripts here document
    their usage with an unindented `from ... import ...` example -- and
    inserting a statement there splits the docstring and breaks the file.
    Four files failed to parse for exactly that reason before this changed.
    """
    import ast
    if "_REPO_ROOT =" in src:
        return src, False
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return src, False
    last = None
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            last = getattr(node, "end_lineno", node.lineno) - 1
    if last is None:
        return src, False
    lines = src.splitlines(keepends=True)
    j = last + 1
    while j < len(lines) and lines[j].strip() == "":
        j += 1
    lines.insert(j, "\n# Repo root from THIS file's location, never from the\n"
                    "# home directory: two clones of this repository exist on\n"
                    "# this machine and a hardcoded ~ path wrote to whichever\n"
                    "# one was not being used.\n" + DEFN + "\n")
    return "".join(lines), True


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dir", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "scripts"))
    a = ap.parse_args()

    files = sorted(glob.glob(os.path.join(a.dir, "*.py")))
    hits, changed, failed = 0, [], []
    for f in files:
        if os.path.basename(f) == "fix_repo_paths.py":
            continue
        src = open(f).read()
        n = src.count(NEEDLE)
        if not n:
            continue
        hits += n
        new = src.replace(NEEDLE, REPLACE)
        new, added = insert_defn(new)
        if "import os" not in new and "\nimport os\n" not in new:
            failed.append((f, "no `import os`"))
            continue
        try:
            compile(new, f, "exec")
        except SyntaxError as e:                       # noqa: PERF203
            failed.append((f, f"would not parse: {e}"))
            continue
        changed.append((f, n, added))
        if a.apply:
            open(f, "w").write(new)

    for f, n, added in changed:
        print(f"  {n:>2} path(s){'  +defn' if added else '        '}  "
              f"{os.path.basename(f)}")
    print(f"\n{len(changed)} files, {hits} occurrences")
    if failed:
        print(f"\n{len(failed)} SKIPPED:")
        for f, why in failed:
            print(f"  {os.path.basename(f)}: {why}")
    if not a.apply:
        print("\ndry run — rerun with --apply")
    else:
        print("\napplied")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
