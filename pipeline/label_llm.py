"""Stage 3b — LLM topic labels (Claude).

Adds an `llm_label` to every topic and subtopic in topics.json, alongside the
existing c-TF-IDF `label`. Each cluster's c-TF-IDF terms and top member
keywords are sent to Claude, which returns a concise human-readable label.

All nodes are labelled in a SINGLE batched request using structured outputs
(client.messages.parse with a schema), so the run is one API call.

Auth: uses the standard Anthropic credential chain (ANTHROPIC_API_KEY, or an
`ant auth login` profile). If none is configured, this stage cannot run — set a
key or run `ant auth login` first.

Dataset selection: set DATASET=<name> to read/write under
data/processed/<name>/ (default "grants").

Input/Output: data/processed/<DATASET>/topics.json (updated in place, adds `llm_label`)
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import anthropic
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
DATASET = os.environ.get("DATASET", "grants")
TOPICS = ROOT / "data" / "processed" / DATASET / "topics.json"

MODEL = "claude-opus-4-8"
TOP_KEYWORDS = 10   # member keywords shown to Claude per cluster


class Label(BaseModel):
    id: str
    label: str


class LabelSet(BaseModel):
    labels: list[Label]


def build_payload(data: dict) -> list[dict]:
    """One entry per cluster (topics + subtopics) with terms + top keywords."""
    nodes = []
    for t in data["topics"]:
        # aggregate the highest-weighted keywords across the topic's subtopics
        kws = sorted(
            (k for s in t["subtopics"] for k in s["keywords"]),
            key=lambda k: -k["weight"],
        )
        nodes.append({
            "id": t["id"],
            "level": "topic",
            "terms": t.get("terms", []),
            "keywords": [k["text"] for k in kws[:TOP_KEYWORDS]],
        })
        for s in t["subtopics"]:
            nodes.append({
                "id": s["id"],
                "level": "subtopic",
                "terms": s.get("terms", []),
                "keywords": [k["text"] for k in s["keywords"][:TOP_KEYWORDS]],
            })
    return nodes


PROMPT = """\
You are labelling clusters of keywords extracted from research-grant abstracts \
(NSF, NIH, and other funders). Each cluster below has an id, a list of \
distinctive `terms` (from c-TF-IDF), and representative member `keywords`.

For each cluster, write a concise, human-readable topic label:
- 2-5 words, Title Case, no trailing punctuation.
- Name the actual research area (e.g. "Molecular & Cellular Biology", \
"Wireless Networking", "STEM Education & Outreach").
- "topic" clusters are broad research areas; "subtopic" clusters are narrower \
themes within them — label at the appropriate granularity.
- If a cluster is grant-administrative or logistical rather than a research \
area, say so plainly (e.g. "Program Administration", "Place Names").

Return a label for every cluster id.

Clusters:
{clusters}
"""


def main() -> int:
    data = json.loads(TOPICS.read_text(encoding="utf-8"))
    nodes = build_payload(data)

    client = anthropic.Anthropic()
    response = client.messages.parse(
        model=MODEL,
        max_tokens=8000,
        messages=[{
            "role": "user",
            "content": PROMPT.format(clusters=json.dumps(nodes, ensure_ascii=False, indent=2)),
        }],
        output_format=LabelSet,
    )
    labels = {l.id: l.label for l in response.parsed_output.labels}
    print(f"received {len(labels)} labels for {len(nodes)} clusters")

    missing = 0
    for t in data["topics"]:
        if t["id"] in labels:
            t["llm_label"] = labels[t["id"]]
        else:
            missing += 1
        for s in t["subtopics"]:
            if s["id"] in labels:
                s["llm_label"] = labels[s["id"]]
            else:
                missing += 1
    if missing:
        print(f"WARNING: {missing} clusters got no label")

    TOPICS.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"-> {TOPICS.relative_to(ROOT)} (added llm_label)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
