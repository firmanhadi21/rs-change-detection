"""List the words in the book's prose that end in -kan (also -kannya, -kanlah), with their counts.
Code blocks and inline code are skipped. Used to review which ones are root+k + -an (keep TeX's break) and which
take the suffix -kan (break before "kan"); see buat.py.

  python buku/hyphenation/kandidat.py
"""
import re
from collections import Counter
from pathlib import Path

BUKU = Path(__file__).resolve().parents[1]
BERKAS = [BUKU / "index.qmd", *sorted((BUKU / "bab").glob("*.qmd"))]
KAN = re.compile(r"kan(nya|lah)?$")


def prosa(teks):
    teks = re.sub(r"^(```|~~~).*?^\1", "", teks, flags=re.S | re.M)   # fenced code
    return re.sub(r"`[^`\n]*`", "", teks)                              # inline code


def kata_kan():
    hitung = Counter()
    for f in BERKAS:
        for w in re.findall(r"[A-Za-z]+", prosa(f.read_text())):
            w = w.lower()
            if len(w) > 5 and KAN.search(w):
                hitung[w] += 1
    return hitung


if __name__ == "__main__":
    h = kata_kan()
    print(len(h), "kata")
    print(" ".join(sorted(h)))
