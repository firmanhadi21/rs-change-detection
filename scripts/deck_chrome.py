"""Shared furniture for the printed-page decks in this repo.

Two decks now render from this: the weekly Borneo hotspot set and the
West Sumatra burn-to-palm set. They are about different things but they
are the same publication, and a reader who sees both should not be able
to tell they were written a month apart.

Everything here is language-agnostic. Strings live in each deck's own
text module; what lives here is the palette, the page geometry, and the
three or four primitives that kept getting re-tuned in parallel and
drifting -- most of all notes_block, which exists because hand-tuned
leading silently pushed the last paragraph under the footer the first
time a translation ran a fifth longer than the English.
"""

import os

# Pale green-grey forest paper, deep forest ink, fire in clay and amber,
# protected forest in teal. Chosen against the subject rather than
# inherited from a chart library.
C = {
    "ground": "#E9EDE8", "surface": "#F5F7F3", "sunk": "#DFE5DE",
    "ink": "#16231D", "muted": "#64756C", "rule": "#C8D2C8",
    "ember": "#C8471B", "flame": "#DE8A22", "canopy": "#2F6A5B",
    "deep": "#1D4A54", "hpk": "#B0533C", "cons": "#1F5140",
    "water": "#7E9AA6", "sea": "#D6E2E6", "land": "#E4EADF",
}
PAGE = (11.0, 15.6)          # inches; A4-ish portrait
SERIF = "DejaVu Serif"
SANS = "DejaVu Sans"


def page():
    import matplotlib.pyplot as plt
    return plt.figure(figsize=PAGE, facecolor=C["ground"])


def header(fig, eyebrow, title, sub=None, y=0.955):
    fig.text(0.07, y, eyebrow.upper(), fontsize=10.5, color=C["muted"],
             fontweight="bold", family=SANS)
    fig.text(0.07, y - 0.032, title, fontsize=30, color=C["ink"],
             family=SERIF, va="top")
    if sub:
        fig.text(0.07, y - 0.072, sub, fontsize=12.5, color=C["muted"],
                 family=SANS, va="top", wrap=True)


def footer(fig, n, total, source):
    fig.text(0.07, 0.028, source, fontsize=9, color=C["muted"])
    fig.text(0.93, 0.028, f"{n} / {total}", fontsize=9, color=C["muted"],
             ha="right")


def section(fig, y, label):
    """A small caps label with a hairline rule under it."""
    import matplotlib.patches as mp
    fig.text(0.07, y, label, fontsize=10, color=C["muted"],
             fontweight="bold", family=SANS)
    ax = fig.add_axes([0.07, y - 0.012, 0.86, 0.0012]); ax.set_axis_off()
    ax.add_patch(mp.Rectangle((0, 0), 1, 1, color=C["rule"]))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)


def rule(fig, top, height, color=None):
    """The short vertical rule that brackets a pull quote."""
    import matplotlib.patches as mp
    ax = fig.add_axes([0.068, top - height, 0.004, height])
    ax.set_axis_off()
    ax.add_patch(mp.Rectangle((0, 0), 1, 1, color=color or C["ember"]))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)


def quote(fig, text, top, size=15, width=68, x=0.09):
    """A bracketed pull quote that wraps rather than being hand-broken,
    with its rule sized to the wrap. Returns the y it ends at."""
    import textwrap
    body = textwrap.fill(text, width)
    h = (body.count("\n") + 1) * size * 1.32 / 72 / PAGE[1]
    rule(fig, top, h)
    fig.text(x, top, body, fontsize=size, color=C["ink"], family=SERIF,
             va="top")
    return top - h


def notes_block(fig, notes, top, floor=0.044, width=108):
    """A stack of bold-headed notes that always clears the footer.

    Hand-tuned leading worked while there was one language. Indonesian
    runs roughly a fifth longer than the English for the same content,
    which pushed the last note off the page -- so the block measures
    itself and steps the type down until it fits. Returns the final y.
    """
    import textwrap
    # A note with no heading is a plain paragraph and must not reserve a
    # line for the heading it does not have, or the block opens with a
    # gap the eye reads as a missing title.
    head = [0.0165 if b else 0.0 for b, _ in notes]
    for size, lead, wrap in ((11.0, 0.0185, width), (10.5, 0.0175, width + 6),
                             (10.0, 0.0166, width + 12),
                             (9.5, 0.0158, width + 18)):
        bodies = [textwrap.fill(b, wrap) for _, b in notes]
        need = sum(h + lead * (b.count("\n") + 1) + 0.0075
                   for h, b in zip(head, bodies))
        if top - need >= floor:
            break
    y = top
    for (bold, _), body, h in zip(notes, bodies, head):
        if bold:
            fig.text(0.07, y, bold, fontsize=size, color=C["ink"],
                     fontweight="bold")
        fig.text(0.07, y - h, body, fontsize=size - 0.5,
                 color=C["muted"], va="top")
        y -= h + lead * (body.count("\n") + 1) + 0.0075
    return y


def save(fig, path, dpi=140):
    fig.savefig(path, dpi=dpi, format="jpg", facecolor=C["ground"],
                pil_kwargs={"quality": 92, "optimize": True})
    import matplotlib.pyplot as plt
    plt.close(fig)
    print(f"  wrote {os.path.basename(path)} "
          f"({os.path.getsize(path)/1024:.0f} KB)")


# --- numbers ---------------------------------------------------------
# Indonesian writes 1.234 and 3,45 where English writes 1,234 and 3.45,
# and no format spec expresses both, so numbers are formatted before they
# reach a template. Getting this wrong is not cosmetic: "3.45" read as
# Indonesian is three thousand four hundred and fifty.
def ribuan(n, lang):
    s = f"{int(round(n)):,}"
    return s.replace(",", ".") if lang == "id" else s


def desimal(v, lang, d=1):
    s = f"{v:.{d}f}"
    return s.replace(".", ",") if lang == "id" else s
