"""Stage 5 — Manifest of available datasets, for the live dataset switcher.

Scans data/processed/<id>/topics.json for every processed dataset and writes a
manifest the frontend fetches at load time to populate its dataset dropdown.
Unlike the retired activate.py (which copied ONE dataset to a fixed path), the
frontend can now hold several datasets at once and switch between them live —
this script just tells it what's available and where.

DATASET_META holds small per-dataset display config that can't be derived from
the data alone: a human label, and `excluded_years` — years to omit from the
per-keyword timeline because they reflect a partial collection window, not a
real activity drop-off (e.g. nsf-cise-21-25 only has partial 2020/2026 data).
Add an entry here for any new dataset that needs either; otherwise it falls
back to a prettified id and no excluded years.

Input:  data/processed/<id>/topics.json  (every dataset processed so far)
Output: data/processed/manifest.json
        [{id, label, file, n_docs, n_topics, funders, excluded_years}, ...]
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "data" / "processed"
OUT = PROCESSED / "manifest.json"

DATASET_META = {
    "grants": {
        "label": "General Research Awards",
        "excluded_years": [],
    },
    "nsf-cise-21-25": {
        "label": "NSF CISE 2021–2025",
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
