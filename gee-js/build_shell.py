"""Extract the parent tutorial's sidebar and layout, for the GEE pages to reuse.

The GEE pages should render INSIDE the parent site's content column, with the
parent's own sidebar still on the left -- not with a Quarto sidebar imitating
it. That means reusing the parent's actual markup and CSS rather than
re-describing them, so the two cannot drift apart when the tutorial's nav
changes.

Writes three files that _quarto.yml pulls in:

  _shell-open.html    <div class="wrap"><nav class="side">…parent nav…</nav><main>
  _shell-close.html   </main></div>
  parent.css          the parent's design tokens and .wrap/.side/main layout

Run this again whenever docs/index.html's sidebar changes.

    python3 gee-js/build_shell.py
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARENT = os.path.join(ROOT, "docs", "index.html")
OUT = os.path.join(ROOT, "gee-js")


def main():
    html = open(PARENT, errors="ignore").read()

    # --- the sidebar, verbatim -------------------------------------------
    m = re.search(r'(<nav class="side">.*?</nav>)', html, re.S)
    if not m:
        raise SystemExit("could not find <nav class=\"side\"> in the parent")
    side = m.group(1)

    # Links in the parent are relative to docs/; these pages live in
    # docs/gee-js/, so one level up. Anchors on the parent page need the page
    # too, or they resolve against the GEE page and go nowhere.
    side = re.sub(r'href="#', 'href="../index.html#', side)
    side = re.sub(r'href="(?!http|\.\./|#)([^"]+)"', r'href="../\1"', side)
    # The parent marks the GEE entry as current; that is now where we are.
    side = side.replace('href="../gee-js/"', 'href="index.html"')

    # A small block of our own, so the workshop's pages are reachable from
    # inside the parent's furniture rather than replacing it.
    ours = """
<h2>Workshop GEE</h2>
<a href="index.html">Beranda</a>
<a href="hari-1.html">Hari 1 &middot; Konsep</a>
<a href="hari-2.html">Hari 2 &middot; Praktik</a>
<a href="slides.html">Slides</a>
<a href="skrip.html">Skrip</a>
<a href="rujukan.html">Rujukan</a>
"""
    side = side.replace("</nav>", ours + "</nav>")

    # The sidebar entry still advertises the old 90-minute course.
    side = side.replace("90-minute beginner course (ID)",
                        "Two-day webinar (ID)")
    side = side.replace("Kursus pemula 90 menit", "Webinar dua hari")

    open(f"{OUT}/_shell-open.html", "w").write(
        '<div class="wrap">\n' + side + '\n<main>\n')

    # The parent's EN/ID toggle is CSS-driven: `.id, html.lang-id .en {display:none}`
    # with a class on <html>. Without the script that sets it, BOTH languages
    # render at once -- every label doubled. Carried over so the toggle in the
    # injected sidebar actually works.
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.S)
    toggle = "\n".join(s for s in scripts if "lang-id" in s or "data-lang" in s)
    close = "</main>\n</div>\n"
    if toggle:
        close += f"<script>\n{toggle}\n</script>\n"
    else:
        # Fall back to a minimal equivalent rather than shipping doubled text.
        close += """<script>
(function () {
  var html = document.documentElement;
  function set (l) {
    html.classList.toggle('lang-id', l === 'id');
    try { localStorage.setItem('lang', l); } catch (e) {}
    document.querySelectorAll('.langtoggle button').forEach(function (b) {
      b.classList.toggle('active', b.dataset.lang === l);
    });
  }
  document.querySelectorAll('.langtoggle button').forEach(function (b) {
    b.addEventListener('click', function () { set(b.dataset.lang); });
  });
  var saved = 'id';
  try { saved = localStorage.getItem('lang') || 'id'; } catch (e) {}
  set(saved);
})();
</script>
"""
    open(f"{OUT}/_shell-close.html", "w").write(close)
    print(f"language toggle: {'parent script reused' if toggle else 'fallback written'}")

    # --- the parent's CSS, verbatim --------------------------------------
    styles = re.findall(r"<style[^>]*>(.*?)</style>", html, re.S)
    if not styles:
        raise SystemExit("no <style> block found in the parent")
    css = "\n".join(styles)

    # Quarto emits its own page container; neutralise it so our grid governs.
    css += """
/* --- added for the Quarto pages inside this shell --- */
.quarto-container, .page-columns, #quarto-content,
.quarto-title-banner, .content { max-width: none !important; padding: 0 !important; }
main .quarto-title-block { margin-bottom: 1rem; }
main #title-block-header h1 { margin-top: 0; }
main pre { background: var(--code-bg); border: 1px solid var(--line);
           border-radius: 8px; padding: 12px 14px; }
main table { width: 100%; border-collapse: collapse; }
main th { text-align: left; color: var(--muted);
          border-bottom: 2px solid var(--line); padding: 8px 10px; }
main td { border-bottom: 1px solid var(--line); padding: 8px 10px; }
main .callout { border: 1px solid var(--line); border-radius: 10px;
                background: var(--card); margin: 1.3rem 0; }
/* Quarto's own nav must not appear -- the parent's sidebar is the nav. */
.navbar, #quarto-sidebar, .sidebar-navigation, #quarto-margin-sidebar { display: none !important; }
"""
    open(f"{OUT}/parent.css", "w").write(css)

    print(f"sidebar: {len(side):,} chars")
    print(f"css    : {len(css):,} chars")
    print(f"wrote _shell-open.html, _shell-close.html, parent.css in {OUT}")
    n = len(re.findall(r"<a ", side))
    print(f"sidebar links carried over: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
