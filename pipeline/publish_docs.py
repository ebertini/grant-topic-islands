"""Stage 6 — Publish one static page per dataset, plus a landing page.

Each dataset gets its OWN page at its own URL — separate, independently
shareable links (docs/<slug>.html) — rather than one page with a live
switcher. A small landing page (docs/index.html) lists them.

For each dataset this:
  - copies its topics.json into docs/datasets/<id>.json
  - writes docs/<slug>.html: web/index.html with its DATA_DIR constant swapped
    from "../data/processed" (dev, relative to web/) to "." (deployed,
    relative to docs/), and its ENTRY constant swapped to that dataset's
    {id, label, file, excluded_years} — the two lines that differ between
    the dev template and any given deployed page.
Then writes docs/index.html as a landing page linking to every <slug>.html,
using each entry's label/description/n_docs from the manifest.

Run pipeline/manifest.py first (or after adding/reprocessing a dataset) so
data/processed/manifest.json is current.

Input:  data/processed/manifest.json, data/processed/<id>/topics.json,
        web/index.html
Output: docs/<slug>.html (one per dataset), docs/index.html (landing),
        docs/datasets/<id>.json, docs/manifest.json
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "data" / "processed"
MANIFEST = PROCESSED / "manifest.json"
WEB_APP = ROOT / "web" / "index.html"
DOCS = ROOT / "docs"

# earlier site structures — remove if present so stale pages don't linger
OBSOLETE = ["cards.html", "islands.html", "topics.json"]

DATA_DIR_MARKER = 'const DATA_DIR="../data/processed";'
ENTRY_RE = re.compile(r'const ENTRY=\{.*?\};')


def build_page(entry: dict) -> str:
    html = WEB_APP.read_text(encoding="utf-8")
    if DATA_DIR_MARKER not in html:
        raise RuntimeError(f"expected to find {DATA_DIR_MARKER!r} in {WEB_APP} — app structure changed?")
    html = html.replace(DATA_DIR_MARKER, 'const DATA_DIR=".";')

    page_entry = {
        "id": entry["id"], "label": entry["label"],
        "file": f"datasets/{entry['id']}.json", "excluded_years": entry["excluded_years"],
    }
    new_entry_line = "const ENTRY=" + json.dumps(page_entry, ensure_ascii=False) + ";"
    html, n = ENTRY_RE.subn(new_entry_line, html)
    if n != 1:
        raise RuntimeError(f"expected exactly one ENTRY constant in {WEB_APP}, found {n}")
    return html


def build_landing(entries: list[dict]) -> str:
    cards = "\n".join(
        f'    <a class="card" href="{e["slug"]}.html">\n'
        f'      <h2>{e["label"]} →</h2>\n'
        f'      <p>{e["description"] or ""}</p>\n'
        f'      <p class="n">{e["n_docs"]:,} grants · {e["n_topics"]} topics</p>\n'
        f'    </a>'
        for e in entries
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Grant Topic Islands</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fira+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root {{ --ink:#0b0b0b; --muted:#6b6a64; --hair:#e3e2dd; --blue:#5079a8; }}
  * {{ box-sizing:border-box; }}
  html,body {{ margin:0; min-height:100%; font-family:"Fira Sans",-apple-system,BlinkMacSystemFont,sans-serif;
    color:var(--ink); background:radial-gradient(125% 105% at 50% 32%,#ffffff 0%,#f1f0ec 100%); }}
  main {{ max-width:760px; margin:0 auto; padding:72px 24px; }}
  h1 {{ font-size:30px; font-weight:700; margin:0 0 6px; }}
  p.lede {{ color:var(--muted); font-size:16px; line-height:1.55; margin:0 0 36px; }}
  .cards {{ display:grid; grid-template-columns:1fr 1fr; gap:18px; }}
  a.card {{ display:block; text-decoration:none; color:inherit; border:1px solid var(--hair);
    border-radius:12px; padding:22px 22px 24px; background:#fff;
    box-shadow:0 1px 3px rgba(0,0,0,.05); transition:box-shadow .15s,border-color .15s; }}
  a.card:hover {{ box-shadow:0 4px 14px rgba(0,0,0,.09); border-color:var(--blue); }}
  a.card h2 {{ font-size:18px; margin:0 0 6px; color:var(--blue); }}
  a.card p {{ margin:0 0 4px; font-size:13.5px; color:var(--muted); line-height:1.5; }}
  a.card p.n {{ font-size:11.5px; color:#9a9a92; margin-top:8px; }}
  footer {{ margin-top:44px; font-size:12.5px; color:var(--muted); line-height:1.6; }}
  @media (max-width:560px){{ .cards{{grid-template-columns:1fr;}} }}
</style>
</head>
<body>
<main>
  <h1>Grant Topic Islands</h1>
  <p class="lede">A visual analysis of research-grant abstracts. Keyphrases were extracted per
  grant, organized into a three-level topic hierarchy, and linked to the documents they cover.
  Each dataset below is its own page.</p>
  <div class="cards">
{cards}
  </div>
  <footer>Built from an offline Python pipeline (research-grant filtering, keyphrase extraction,
  hierarchical clustering, and topic labeling). Static site — no server required.</footer>
</main>
</body>
</html>
"""


def main() -> int:
    if not MANIFEST.exists():
        print(f"ERROR: {MANIFEST} not found — run pipeline/manifest.py first")
        return 1
    entries = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if not entries:
        print("ERROR: manifest is empty — nothing to publish")
        return 1

    DOCS.mkdir(exist_ok=True)
    (DOCS / "datasets").mkdir(exist_ok=True)
    (DOCS / ".nojekyll").touch()

    for name in OBSOLETE:
        p = DOCS / name
        if p.exists():
            p.unlink()

    for e in entries:
        shutil.copyfile(PROCESSED / e["file"], DOCS / "datasets" / f"{e['id']}.json")
        (DOCS / f"{e['slug']}.html").write_text(build_page(e), encoding="utf-8")

    (DOCS / "manifest.json").write_text(
        json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    (DOCS / "index.html").write_text(build_landing(entries), encoding="utf-8")

    print(f"-> docs/index.html  (landing, {len(entries)} dataset(s))")
    for e in entries:
        print(f"-> docs/{e['slug']}.html  ({e['n_docs']} grants)  <- docs/datasets/{e['id']}.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
