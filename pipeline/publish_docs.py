"""Stage 6 — Publish the multi-dataset app to docs/ for GitHub Pages.

Unlike the retired activate.py (which copied ONE dataset to a fixed path for a
single-dataset frontend), the app now holds several datasets at once and lets
the visitor switch live via a dropdown (see web/index.html's dataset select).
This script builds the whole docs/ deploy folder to match:

  - copies every dataset's topics.json into docs/datasets/<id>.json
  - writes docs/manifest.json (same shape as data/processed/manifest.json, but
    with paths relative to docs/ instead of data/processed/)
  - writes docs/index.html: web/index.html with its DATA_DIR constant swapped
    from "../data/processed" (dev, relative to web/) to "." (deployed, relative
    to docs/) — the one line that differs between the two copies
  - removes obsolete pages from earlier site structures (cards.html,
    islands.html, and the old two-page landing index.html) if present

Run pipeline/manifest.py first (or after adding/reprocessing a dataset) so
data/processed/manifest.json is current.

Input:  data/processed/manifest.json, data/processed/<id>/topics.json,
        web/index.html
Output: docs/index.html, docs/manifest.json, docs/datasets/<id>.json
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "data" / "processed"
MANIFEST = PROCESSED / "manifest.json"
WEB_APP = ROOT / "web" / "index.html"
DOCS = ROOT / "docs"

OBSOLETE = ["cards.html", "islands.html"]  # earlier multi-page site structure


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

    docs_manifest = []
    for e in entries:
        src = PROCESSED / e["file"]
        dst = DOCS / "datasets" / f"{e['id']}.json"
        shutil.copyfile(src, dst)
        docs_manifest.append({**e, "file": f"datasets/{e['id']}.json"})
    (DOCS / "manifest.json").write_text(
        json.dumps(docs_manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    app_html = WEB_APP.read_text(encoding="utf-8")
    marker = 'const DATA_DIR="../data/processed";'
    if marker not in app_html:
        print(f"ERROR: expected to find {marker!r} in {WEB_APP} — app structure changed?")
        return 1
    (DOCS / "index.html").write_text(
        app_html.replace(marker, 'const DATA_DIR=".";'), encoding="utf-8")

    removed = []
    for name in OBSOLETE:
        p = DOCS / name
        if p.exists():
            p.unlink()
            removed.append(name)

    print(f"-> docs/index.html  (app, DATA_DIR=\".\")")
    print(f"-> docs/manifest.json  ({len(docs_manifest)} dataset(s))")
    for e in docs_manifest:
        print(f"   docs/{e['file']}  ({e['n_docs']} grants)")
    if removed:
        print(f"removed obsolete: {', '.join(removed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
