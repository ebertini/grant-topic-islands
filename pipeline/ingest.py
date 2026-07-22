"""Stage 0 — Ingest.

Normalize the raw grants.csv into a uniform record shape for the rest of the
pipeline. This stage does STRUCTURE only: it drops unusable rows and normalizes
metadata, but leaves the abstract text raw (text cleaning is stage 1).

Input:  data/raw/grants.csv
Output: data/processed/grants.normalized.jsonl
        one JSON object per line: {id, title, abstract, funder, funder_code, year}
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "grants.csv"
OUT = ROOT / "data" / "processed" / "grants.normalized.jsonl"

# csv fields can be large (abstracts run to several KB)
csv.field_size_limit(10_000_000)

_WS = re.compile(r"\s+")


def clean_ws(s: str) -> str:
    """Collapse runs of whitespace (titles/abstracts have doubled spaces)."""
    return _WS.sub(" ", (s or "").strip())


def normalize_funder(agencyname: str, agencycode: str) -> tuple[str, str]:
    """Return (label, code). Merge sub-award variants into their parent agency."""
    label = clean_ws(agencyname)
    # "National Institutes of Health - SubAward" -> parent agency
    label = re.sub(r"\s*-\s*Sub\s*Award$", "", label, flags=re.IGNORECASE)
    code = clean_ws(agencycode).upper()
    return label, code


def parse_year(row: dict) -> int | None:
    raw = clean_ws(row.get("startdateyear", ""))
    if raw.isdigit():
        y = int(raw)
        if 1950 <= y <= 2100:
            return y
    return None


def main() -> int:
    if not RAW.exists():
        print(f"ERROR: {RAW} not found", file=sys.stderr)
        return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)

    n_total = n_kept = n_no_abstract = n_short = 0
    funder_counts: Counter[str] = Counter()
    MIN_ABSTRACT_CHARS = 100  # very short abstracts carry little topical signal

    with RAW.open(newline="", encoding="utf-8-sig") as fh, OUT.open("w", encoding="utf-8") as out:
        reader = csv.DictReader(fh)
        for row in reader:
            n_total += 1
            abstract = clean_ws(row.get("abstract", ""))
            if not abstract:
                n_no_abstract += 1
                continue
            if len(abstract) < MIN_ABSTRACT_CHARS:
                n_short += 1
                continue

            title = clean_ws(row.get("grantname", "")) or clean_ws(row.get("title_from_abstract", ""))
            funder, funder_code = normalize_funder(
                row.get("agencyname", ""), row.get("agencycode", "")
            )
            rec = {
                "id": clean_ws(row.get("grant_id", "")),
                "title": title,
                "abstract": abstract,
                "funder": funder,
                "funder_code": funder_code,
                "year": parse_year(row),
            }
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n_kept += 1
            funder_counts[funder] += 1

    print(f"rows read:            {n_total}")
    print(f"dropped (no abstract):{n_no_abstract}")
    print(f"dropped (< {MIN_ABSTRACT_CHARS} chars): {n_short}")
    print(f"kept:                 {n_kept}")
    print(f"-> {OUT.relative_to(ROOT)}")
    print("\ntop funders:")
    for name, c in funder_counts.most_common(10):
        print(f"  {c:5d}  {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
