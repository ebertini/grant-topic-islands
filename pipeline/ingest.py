"""Stage 0 — Ingest.

Normalize a raw grants CSV into a uniform record shape for the rest of the
pipeline. This stage does STRUCTURE only: it drops unusable rows and normalizes
metadata, but leaves the abstract text raw (text cleaning is stage 1).

Different sources ship different column layouts, so this stage picks a column
ADAPTER by detecting which columns are present in the header — the rest of the
pipeline only ever sees the uniform {id, title, abstract, funder, funder_code,
year} shape, so it doesn't care which source produced it.

Known adapters:
  - "legacy"          the original multi-agency grants.csv
                       (grant_id, grantname, agencyname, agencycode, abstract,
                       startdateyear)
  - "nsf_award_export" NSF award-search style export (awd_id, awd_titl_txt,
                       corpus, div_abbr, org_div_long_name, awd_eff_year).
                       `abstract` in this export is pre-lowercased/depunctuated
                       (upstream processing artifact); `corpus` is the original
                       title+abstract concatenated with NO separator, so the
                       true abstract is recovered by stripping the title
                       prefix off `corpus`. funder/funder_code are mapped from
                       the CISE *division* (div_abbr / org_div_long_name), not
                       agency, since agency is constant ("NSF") in this export.

Dataset selection: set DATASET=<name> to read data/raw/<name>.csv and write
under data/processed/<name>/ (default "grants" — the original corpus).

Input:  data/raw/<DATASET>.csv
Output: data/processed/<DATASET>/grants.normalized.jsonl
        one JSON object per line: {id, title, abstract, funder, funder_code, year}
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATASET = os.environ.get("DATASET", "grants")
RAW = ROOT / "data" / "raw" / f"{DATASET}.csv"
OUT = ROOT / "data" / "processed" / DATASET / "grants.normalized.jsonl"

# csv fields can be large (abstracts run to several KB)
csv.field_size_limit(10_000_000)

_WS = re.compile(r"\s+")


def clean_ws(s: str) -> str:
    """Collapse runs of whitespace (titles/abstracts have doubled spaces)."""
    return _WS.sub(" ", (s or "").strip())


# ---------------------------------------------------------------------------
# Adapters — each maps one raw CSV row to the uniform pre-clean field set:
# (id, title, abstract, funder, funder_code, year). Values are cleaned/typed
# uniformly by the caller; adapters just pick/derive the right raw values.
# ---------------------------------------------------------------------------


def adapt_legacy(row: dict) -> tuple[str, str, str, str, str, str]:
    title = row.get("grantname", "") or row.get("title_from_abstract", "")
    funder = clean_ws(row.get("agencyname", ""))
    # "National Institutes of Health - SubAward" -> parent agency
    funder = re.sub(r"\s*-\s*Sub\s*Award$", "", funder, flags=re.IGNORECASE)
    funder_code = clean_ws(row.get("agencycode", "")).upper()
    return (
        row.get("grant_id", ""),
        title,
        row.get("abstract", ""),
        funder,
        funder_code,
        row.get("startdateyear", ""),
    )


def adapt_nsf_award_export(row: dict) -> tuple[str, str, str, str, str, str]:
    title = row.get("awd_titl_txt", "")
    corpus = row.get("corpus", "") or ""
    # corpus = title + original abstract, concatenated with no separator;
    # row["abstract"] is a lowercased/depunctuated derivative, not the source text.
    abstract = corpus[len(title):] if corpus.startswith(title) else corpus
    funder = clean_ws(row.get("org_div_long_name", ""))
    funder_code = clean_ws(row.get("div_abbr", "")).upper()
    return (
        row.get("awd_id", ""),
        title,
        abstract,
        funder,
        funder_code,
        row.get("awd_eff_year", ""),
    )


def detect_adapter(fieldnames: list[str]):
    fields = set(fieldnames or [])
    if {"grant_id", "abstract", "agencyname"} <= fields:
        return adapt_legacy
    if {"awd_id", "corpus", "div_abbr"} <= fields:
        return adapt_nsf_award_export
    print(f"ERROR: no known column adapter matches header: {sorted(fields)}", file=sys.stderr)
    sys.exit(1)


def parse_year(raw: str) -> int | None:
    raw = clean_ws(raw)
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

    n_total = n_kept = n_no_abstract = n_short = n_duplicate = 0
    funder_counts: Counter[str] = Counter()
    MIN_ABSTRACT_CHARS = 100  # very short abstracts carry little topical signal
    # Dedup by title: sources like the NSF award export split one "Collaborative Research"
    # project into a separate award/row per participating institution, all sharing the same
    # title (and abstract) — left in, those duplicates inflate keyphrase doc_freq and can push
    # otherwise-marginal terms over the downstream min_df cluster threshold.
    seen_titles: set[str] = set()

    with RAW.open(newline="", encoding="utf-8-sig") as fh, OUT.open("w", encoding="utf-8") as out:
        reader = csv.DictReader(fh)
        adapt = detect_adapter(reader.fieldnames)
        print(f"adapter: {adapt.__name__}")

        for row in reader:
            n_total += 1
            raw_id, raw_title, raw_abstract, raw_funder, funder_code, raw_year = adapt(row)

            title = clean_ws(raw_title)
            title_key = title.lower()
            if title_key and title_key in seen_titles:
                n_duplicate += 1
                continue

            abstract = clean_ws(raw_abstract)
            if not abstract:
                n_no_abstract += 1
                continue
            if len(abstract) < MIN_ABSTRACT_CHARS:
                n_short += 1
                continue

            if title_key:
                seen_titles.add(title_key)

            funder = clean_ws(raw_funder)
            rec = {
                "id": clean_ws(raw_id),
                "title": title,
                "abstract": abstract,
                "funder": funder,
                "funder_code": funder_code,
                "year": parse_year(raw_year),
            }
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n_kept += 1
            funder_counts[funder] += 1

    print(f"rows read:            {n_total}")
    print(f"dropped (duplicate title): {n_duplicate}")
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
