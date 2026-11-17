"""Hyphenation exceptions for Indonesian → buku/hyphenation/pemenggalan.tex (loaded by both PDFs).

TeX's Indonesian patterns get some breaks wrong; this fixes them word by word for every word of the book's prose
(code skipped) that needs it, as \\babelhyphenation (in the preamble: inside \\AtBeginDocument it has no effect):

1. Suffix -kan stays whole: the patterns split by -an, so "dijalank-an", "ditampilk-an" → "dijalan-kan", "ditampil-kan"
   (also -kannya, -kanlah). Roots ending in k plus -an (tindak-an, didik-an) keep the pattern's break: AKAR_K_AN.
2. A consonant cluster after a prefix stays together: "dip-rak-tik-kan" → "di-prak-tik-kan", "memp-rak" → "mem-prak".
3. A consonant on its own joins the next syllable: "ber-s-truk-tur" → "ber-struk-tur".
4. No break between "me" and "m": "me-ma-kai", "me-mu-at-nya" → "mema-kai", "memu-at-nya".


Run again after adding text:  ~/miniforge3/bin/python buku/hyphenation/buat.py
"""
import re
import subprocess
import tempfile
from pathlib import Path

from kandidat import BERKAS, prosa

SINI = Path(__file__).parent
REPO = SINI.parents[1]
OUT = SINI / "pemenggalan.tex"
# root ending in k + suffix -an (or -an + -nya): the pattern's break is already right
AKAR_K_AN = {"berantakan", "contekan", "cuplikan", "kebalikannya", "kebijakan", "kecocokannya", "lonjakan",
             "pendidikan", "penumpukan", "rujukan", "tindakannya",
             "tindakan", "gerakan", "masukan", "pemasukan", "kerusakan", "cetakan", "didikan", "kebijakannya",
             "pendidikannya", "gerakannya", "peletakan", "teriakan", "kecocokan"}
AWALAN = ("meng", "peng", "mem", "men", "pem", "pen", "ber", "ter", "di", "me", "pe", "ke")
# look prefixed but are roots: the pattern's break is right (dis-kret, dis-tri-bu-si, mes-ki)
BUKAN_AWALAN = {"diskret", "distribusi", "distribusinya", "meski"}
VOKAL = re.compile(r"[aiueo]")
# consonant clusters that open a syllable in (loan)words: pr-, tr-, kl-, str-, spr-, ...
KLUSTER = re.compile(r"(?:s?[pt]r|[kgbf][rl]|pl|dr|s[kpt]|sk[rl])[aiueo]")


def semua_kata(berkas):
    return {w.lower() for f in berkas for w in re.findall(r"[A-Za-z]+", prosa(f.read_text())) if len(w) > 4}


def akademik():
    teks = (SINI / "akademik.txt").read_text()
    return {w.lower() for b in teks.splitlines() if not b.startswith("#") for w in b.split() if len(w) > 4}


def pola_tex(kata):
    """Hyphenation of each word by LuaLaTeX's Indonesian patterns, as 'di-ja-lank-an'."""
    tex = ("\\documentclass{article}\\usepackage[indonesian]{babel}\\begin{document}\n"
           + "\n".join(f"\\showhyphens{{{k}}}" for k in kata) + "\n\\end{document}\n")
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "uji.tex").write_text(tex)
        subprocess.run(["/Library/TeX/texbin/lualatex", "-interaction=batchmode", "uji.tex"], cwd=d,
                       capture_output=True)
        log = (Path(d) / "uji.log").read_text()
    hasil = re.findall(r"^\[\] \\TU/\S+ (\S+)$", log, flags=re.M)
    assert len(hasil) == len(kata), (len(hasil), len(kata))
    return dict(zip(kata, hasil))


def betulkan(kata, h):
    # 1. suffix -kan whole
    if kata not in AKAR_K_AN:
        h = re.sub(r"k-an((?:-nya|-lah)?)$", r"-kan\1", h)
    s = h.split("-")
    if kata in BUKAN_AWALAN:
        return h
    # 2. prefix + the first consonant of an onset cluster in one piece ("dip-rak", "memp-rak"): move it on
    if len(s) > 1 and s[0] not in AWALAN:
        for a in AWALAN:
            c = s[0][len(a):]
            if s[0].startswith(a) and c and not VOKAL.search(c) and KLUSTER.match(c + s[1]):
                s = [a, c + s[1], *s[2:]]
                break
    # 3. a lone consonant right after a prefix joins the next syllable ("ber-s-truk" → "ber-struk")
    if len(s) > 2 and s[0] in AWALAN and not VOKAL.search(s[1]) and KLUSTER.match(s[1] + s[2]):
        s = [s[0], s[1] + s[2], *s[3:]]
    # 4. no break between "me" and "m"
    if len(s) > 1 and s[0] == "me" and re.match(r"m[aiueo]", s[1]):
        s = [s[0] + s[1], *s[2:]]
    return "-".join(s)


# words the patterns break wrongly in other ways (ng-j, f-s, diphthongs ai/au split): written out by hand
TANGAN = {
    "dipertanggungjawabkan": "di-per-tang-gung-ja-wab-kan",
    "ditafsirkan": "di-taf-sir-kan", "menafsirkan": "me-naf-sir-kan",
    "terapkan": "te-rap-kan",
    "menaikkan": "me-naik-kan", "menaikkannya": "me-naik-kan-nya", "menautkan": "me-naut-kan",
    "menyesuaikan": "me-nye-su-ai-kan", "sesuaikan": "se-su-ai-kan",
    "memakainya": "mema-kai-nya", "memindainya": "memin-dai-nya", "mengabaikan": "meng-a-bai-kan",
    # pr after re- (not an Indonesian prefix, so rule 2 does not see it)
    "reproduksibilitas": "re-pro-duk-si-bi-li-tas", "reproduktibilitas": "re-pro-duk-ti-bi-li-tas",
    "reprodusibel": "re-pro-du-si-bel",
    "skripsi": "skrip-si", "skripsinya": "skrip-si-nya", "peramban": "pe-ram-ban", "berisiko": "be-ri-si-ko",
    "keterkaitan": "ke-ter-kait-an",
}

def daftar(kata):
    """Corrected hyphenations of the words the patterns get wrong, as \\babelhyphenation lines."""
    kata = sorted(kata)
    pola = pola_tex(kata)
    ubah = {k: TANGAN.get(k, betulkan(k, h)) for k, h in pola.items()}
    return {k: h for k, h in ubah.items() if h != pola[k]}


def tulis(ubah, out, asal):
    baris = [f"% Generated by buku/hyphenation/buat.py from {asal}: Indonesian hyphenation fixes",
             "% (-kan whole: dijalan-kan; a cluster after a prefix together: di-prak-tik; no me-m).",
             "% Load in the PREAMBLE (inside \\AtBeginDocument it has no effect). Do not edit; run buat.py again.",
             "\\babelhyphenation[indonesian]{"]
    baris += [f"  {h}" for h in ubah.values()]
    baris.append("}")
    out.write_text("\n".join(baris) + "\n")
    print(f"{len(ubah):4d} kata dibetulkan → {out.relative_to(REPO)}")


buku = semua_kata(BERKAS)
tulis(daftar(buku), OUT, "the book's prose")
