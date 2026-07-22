"""Stage 1.5 — Filter to research grants (Claude / Haiku classification).

Classifies each cleaned grant by its PRIMARY purpose and keeps only the ones
that are actually research. Non-research grants (training programs, conferences/
travel, education/curriculum, outreach, economic development) are moved to a
separate file — the source is never destroyed.

Policy is applied in CODE, not baked into the model: the model returns a
category; KEEP_TYPES decides what survives. Flip to "strict" or "flag for
review" by editing KEEP_TYPES — no re-classification needed.

Method: one Haiku call per grant via the Message Batches API (50% cheaper,
built for large one-time offline jobs). Requires Anthropic credentials
(ANTHROPIC_API_KEY or `ant auth login`).

Input:  data/processed/grants.clean.jsonl
Output: data/processed/grants.research.jsonl    (kept — feeds keyword extraction)
        data/processed/grants.excluded.jsonl    (removed, with type + rationale)
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

ROOT = Path(__file__).resolve().parent.parent
IN = ROOT / "data" / "processed" / "grants.clean.jsonl"
OUT_KEEP = ROOT / "data" / "processed" / "grants.research.jsonl"
OUT_DROP = ROOT / "data" / "processed" / "grants.excluded.jsonl"

MODEL = "claude-haiku-4-5"
ABSTRACT_CHARS = 1500   # enough of the abstract to judge primary purpose

# Inclusive policy: research-enabling work counts as research.
KEEP_TYPES = {"research", "tool_or_infrastructure", "evaluation_research"}

CATEGORIES = [
    "research", "tool_or_infrastructure", "evaluation_research",
    "training", "conference_or_travel", "education_or_curriculum",
    "outreach_or_broadening_participation", "economic_development", "other",
]

SCHEMA = {
    "type": "object",
    "properties": {
        "primary_type": {"type": "string", "enum": CATEGORIES},
        "rationale": {"type": "string"},
    },
    "required": ["primary_type", "rationale"],
    "additionalProperties": False,
}

PROMPT = """\
Classify this research-grant record by its PRIMARY purpose. Pick the single best category:

- research: conducts empirical or theoretical scientific/scholarly investigation (any field, including social science and humanities).
- tool_or_infrastructure: primarily builds a tool, software, platform, instrument, dataset, or archive that enables research.
- evaluation_research: research that studies or evaluates a program, intervention, or method.
- training: primary purpose is training/educating researchers or students (training programs, fellowships-as-training, REU sites).
- conference_or_travel: supports a conference, workshop, symposium, or travel.
- education_or_curriculum: primarily develops education, curriculum, teaching, or K-12/undergraduate instruction.
- outreach_or_broadening_participation: primarily outreach, public engagement, or broadening participation.
- economic_development: primarily economic, community, or business development.
- other: none of the above.

Judge the PRIMARY focus. Many research grants mention education, outreach, or
broader impacts as a secondary component — those are still "research".

TITLE: {title}
ABSTRACT: {abstract}

Return JSON: {{"primary_type": "<one category>", "rationale": "<= 12 words"}}"""


def main() -> int:
    records = [json.loads(line) for line in IN.open(encoding="utf-8")]
    by_id = {r["id"]: r for r in records}
    print(f"classifying {len(records)} grants with {MODEL} (Batches API) ...")

    client = anthropic.Anthropic()
    requests = [
        Request(
            custom_id=r["id"],
            params=MessageCreateParamsNonStreaming(
                model=MODEL,
                max_tokens=200,
                messages=[{"role": "user", "content": PROMPT.format(
                    title=r["title"], abstract=r["abstract"][:ABSTRACT_CHARS])}],
                output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
            ),
        )
        for r in records
    ]

    batch = client.messages.batches.create(requests=requests)
    print(f"batch {batch.id} submitted; polling ...")
    while True:
        b = client.messages.batches.retrieve(batch.id)
        if b.processing_status == "ended":
            break
        print(f"  status={b.processing_status} "
              f"done={b.request_counts.succeeded + b.request_counts.errored}/{len(records)}")
        time.sleep(30)

    verdict: dict[str, dict] = {}
    for res in client.messages.batches.results(batch.id):
        if res.result.type != "succeeded":
            continue
        text = next((blk.text for blk in res.result.message.content if blk.type == "text"), "")
        try:
            verdict[res.custom_id] = json.loads(text)
        except json.JSONDecodeError:
            pass

    kept = dropped = unclassified = 0
    from collections import Counter
    type_counts: Counter[str] = Counter()
    with OUT_KEEP.open("w", encoding="utf-8") as fk, OUT_DROP.open("w", encoding="utf-8") as fd:
        for r in records:
            v = verdict.get(r["id"])
            if v is None:
                unclassified += 1
                fk.write(json.dumps(r, ensure_ascii=False) + "\n")  # keep on failure
                continue
            ptype = v.get("primary_type", "other")
            type_counts[ptype] += 1
            if ptype in KEEP_TYPES:
                fk.write(json.dumps(r, ensure_ascii=False) + "\n")
                kept += 1
            else:
                rec = {**r, "excluded_type": ptype, "excluded_reason": v.get("rationale", "")}
                fd.write(json.dumps(rec, ensure_ascii=False) + "\n")
                dropped += 1

    print(f"\nkept (research):  {kept}")
    print(f"dropped:          {dropped}")
    if unclassified:
        print(f"unclassified (kept as fallback): {unclassified}")
    print("\ncategory breakdown:")
    for t, c in type_counts.most_common():
        mark = "keep" if t in KEEP_TYPES else "DROP"
        print(f"  {c:5d}  {t:38s} [{mark}]")
    print(f"\n-> {OUT_KEEP.relative_to(ROOT)}")
    print(f"-> {OUT_DROP.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
