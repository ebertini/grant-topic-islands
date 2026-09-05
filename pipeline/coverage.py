"""Stage 4b — Document coverage per topic / subtopic.

A grant is *covered by* a subtopic if it contains >= 1 of that subtopic's
keyphrases (the union / "at least one keyphrase" rule). A topic's covered set is
the union of its subtopics' covered grants. Counts are exact distinct-document
counts computed from the FULL keyword->document links in grants.keywords.jsonl
(stage 3 caps each keyword's stored `docs` list at 50, so this can't be done
correctly in the browser).

Notes:
  - Topics overlap: a grant whose keyphrases span topics is counted in each, so
    the topic counts sum to more than n_docs.
  - Nesting holds: a topic's doc_count == |union of its subtopics' doc sets|,
    which is <= the sum of subtopic counts.

Adds `doc_count` to every topic and subtopic, and a deduplicated `docs` id list
to every subtopic (for topic/subtopic drill-down; topic lists are the union of
these in the frontend).

Dataset selection: set DATASET=<name> to read/write under
data/processed/<name>/ (default "grants").

Input:  data/processed/<DATASET>/topics.json
        data/processed/<DATASET>/grants.keywords.jsonl
Output: data/processed/<DATASET>/topics.json  (updated in place)
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATASET = os.environ.get("DATASET", "grants")
PROC = ROOT / "data" / "processed" / DATASET
TOPICS = PROC / "topics.json"
KEYWORDS = PROC / "grants.keywords.jsonl"


def main() -> int:
    data = json.loads(TOPICS.read_text(encoding="utf-8"))

    # keyphrase text -> (subtopic id, topic id); each vocab phrase is in one cluster
    kw_to_sub: dict[str, str] = {}
    kw_to_top: dict[str, str] = {}
    for t in data["topics"]:
        for s in t["subtopics"]:
            for k in s["keywords"]:
                kw_to_sub[k["text"]] = s["id"]
                kw_to_top[k["text"]] = t["id"]

    sub_docs: dict[str, set[str]] = defaultdict(set)
    top_docs: dict[str, set[str]] = defaultdict(set)
    for line in KEYWORDS.open(encoding="utf-8"):
        r = json.loads(line)
        doc_id = r["id"]
        subs, tops = set(), set()
        for kw in r["keywords"]:
            sid = kw_to_sub.get(kw["text"])
            if sid is not None:
                subs.add(sid)
                tops.add(kw_to_top[kw["text"]])
        for sid in subs:
            sub_docs[sid].add(doc_id)
        for tid in tops:
            top_docs[tid].add(doc_id)

    for t in data["topics"]:
        t["doc_count"] = len(top_docs.get(t["id"], ()))
        for s in t["subtopics"]:
            docs = sorted(sub_docs.get(s["id"], ()))
            s["doc_count"] = len(docs)
            s["docs"] = docs

    TOPICS.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    n = data["meta"]["n_docs"]
    total = sum(t["doc_count"] for t in data["topics"])
    print(f"n_docs: {n} | sum of topic coverage: {total} (overlap => > n_docs)")
    print("top topics by coverage:")
    for t in sorted(data["topics"], key=lambda t: -t["doc_count"])[:6]:
        print(f"  {t['doc_count']:5d}  {t['llm_label']}")
    print(f"-> {TOPICS.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
