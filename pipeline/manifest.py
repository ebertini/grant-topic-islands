"""Stage 5 — Manifest of available datasets.

Scans data/processed/<id>/topics.json for every processed dataset and writes a
manifest describing what's available. Each dataset is deployed as its own
static page (see pipeline/publish_docs.py) — separate, independently
shareable URLs — plus a landing page listing them, built from this manifest.

DATASET_META holds small per-dataset display config that can't be derived from
the data alone: a human label, a one-line description (for the landing page),
a URL `slug` for the deployed page name, and `excluded_years` — years to omit
from the per-keyword timeline because they reflect a partial collection
window, not a real activity drop-off (e.g. nsf-cise-21-25 only has partial
2020/2026 data). Add an entry here for any new dataset that needs any of
these; otherwise it falls back to a prettified id, no description, and no
excluded years.

Input:  data/processed/<id>/topics.json  (every dataset processed so far)
Output: data/processed/manifest.json
        [{id, label, description, slug, file, n_docs, n_topics, funders,
          excluded_years}, ...]
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "data" / "processed"
OUT = PROCESSED / "manifest.json"

DATASET_META = {
    "grants": {
        "label": "Northeastern University Faculty Awards",
        "description": "Grants awarded to Northeastern University faculty, across all "
                        "disciplines and funders (1995–2026).",
        "slug": "northeastern-awards",
        "excluded_years": [],
    },
    "nsf-cise-21-25": {
        "label": "NSF CISE 2021–2025",
        "description": "NSF Directorate for Computer & Information Science & "
                        "Engineering (CISE) awards, 2021–2025.",
        "slug": "nsf-cise-2021-2025",
        "excluded_years": [2020, 2026],  # partial collection window at both ends
    },
}


def main() -> int:
    entries = []
    for d in sorted(PROCESSED.iterdir()):
        topics_path = d / "topics.json"
        if not d.is_dir() or not topics_path.exists():
            continue
        meta = json.loads(topics_path.read_text(encoding="utf-8"))["meta"]
        cfg = DATASET_META.get(d.name, {})
        entries.append({
            "id": d.name,
            "label": cfg.get("label", d.name.replace("-", " ").replace("_", " ").title()),
            "description": cfg.get("description", ""),
            "slug": cfg.get("slug", d.name),
            "file": f"{d.name}/topics.json",
            "n_docs": meta["n_docs"],
            "n_topics": meta["n_topics"],
            "funders": meta["funders"],
            "excluded_years": cfg.get("excluded_years", []),
        })

    if not entries:
        print("WARNING: no datasets found under data/processed/*/topics.json")

    OUT.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"-> {OUT.relative_to(ROOT)} ({len(entries)} dataset(s))")
    for e in entries:
        print(f"   {e['id']:20s} {e['label']:30s} {e['n_docs']:5d} grants")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
