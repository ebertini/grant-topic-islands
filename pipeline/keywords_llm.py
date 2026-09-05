"""Stage 2 (LLM) — Keyword extraction with Claude (Haiku).

Replaces the KeyBERT extraction. For each research grant, Claude returns a flat
list of distinctive, canonical scientific keyphrases with a salience score,
explicitly excluding generic grant/administrative language, institutions,
people, places, and funding-program names. Canonicalization (one form per
concept) reduces vocabulary fragmentation, which helps clustering downstream.

Same output schema as the KeyBERT stage, so cluster / seed / coverage are
unchanged. score = salience / 5 (0.2-1.0).

Method: one Haiku call per grant via the Message Batches API. Requires
Anthropic credentials.

Dataset selection: set DATASET=<name> to read/write under
data/processed/<name>/ (default "grants").

Input:  data/processed/<DATASET>/grants.research.jsonl
Output: data/processed/<DATASET>/grants.keywords.jsonl
        {id, title, funder, funder_code, year, keywords: [{text, score}, ...]}
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

ROOT = Path(__file__).resolve().parent.parent
DATASET = os.environ.get("DATASET", "grants")
PROC = ROOT / "data" / "processed" / DATASET
IN = PROC / "grants.research.jsonl"
OUT = PROC / "grants.keywords.jsonl"
BATCH_ID_FILE = PROC / "keywords_llm.batch_id.txt"

MODEL = "claude-haiku-4-5"
ABSTRACT_CHARS = 2500

SCHEMA = {
    "type": "object",
    "properties": {
        "keywords": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "salience": {"type": "integer", "enum": [1, 2, 3, 4, 5]},
                },
                "required": ["text", "salience"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["keywords"],
    "additionalProperties": False,
}

PROMPT = """\
Extract keyphrases from this research-grant abstract for a topic-mapping system.
Identify the SPECIFIC scientific content the work is about — concepts, methods,
materials, organisms, systems, phenomena, and theories.

Rules:
- Include only DISTINCTIVE scientific/technical terms. EXCLUDE generic grant and
  administrative language (research, project, study, applications, objectives,
  goals, findings, impact, broader impacts, intellectual merit, students,
  undergraduate, graduate, curriculum, workforce, outreach, training,
  collaboration, dissemination, novel, important, etc.).
- EXCLUDE institution names, people's names, places, dates, and funding-program
  names (CAREER, REU, GRFP, SBIR, PFI, I-Corps).
- Canonicalize: lowercase; singular where natural; expand or standardize
  acronyms (write 'machine learning' not 'ML'; keep a widely-standard acronym
  such as 'crispr', 'dna', 'mri' as the canonical form); merge variants to one.
- Return 3-12 keyphrases, ordered most -> least central. Return FEWER (even 1-2)
  when the abstract has little specific scientific content; never invent filler.
- salience: 5 = core topic of the grant, 1 = mentioned but peripheral.

TITLE: {title}
ABSTRACT: {abstract}

Return JSON: {{"keywords": [{{"text": "...", "salience": N}}, ...]}}"""

_WS = re.compile(r"\s+")


def main() -> int:
    records = [json.loads(line) for line in IN.open(encoding="utf-8")]
    by_id = {r["id"]: r for r in records}
    print(f"extracting keyphrases from {len(records)} grants with {MODEL} (Batches API) ...")

    client = anthropic.Anthropic()

    if BATCH_ID_FILE.exists():
        batch_id = BATCH_ID_FILE.read_text().strip()
        print(f"resuming existing batch {batch_id} (found {BATCH_ID_FILE.relative_to(ROOT)}) ...")
    else:
        requests = [
            Request(
                custom_id=r["id"],
                params=MessageCreateParamsNonStreaming(
                    model=MODEL,
                    max_tokens=500,
                    messages=[{"role": "user", "content": PROMPT.format(
                        title=r["title"], abstract=r["abstract"][:ABSTRACT_CHARS])}],
                    output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
                ),
            )
            for r in records
        ]
        batch = client.messages.batches.create(requests=requests)
        batch_id = batch.id
        BATCH_ID_FILE.write_text(batch_id)
        print(f"batch {batch_id} submitted; polling ...")

    while True:
        b = client.messages.batches.retrieve(batch_id)
        if b.processing_status == "ended":
            break
        print(f"  status={b.processing_status} "
              f"done={b.request_counts.succeeded + b.request_counts.errored}/{len(records)}")
        time.sleep(30)

    parsed: dict[str, list] = {}
    for res in client.messages.batches.results(batch_id):
        if res.result.type != "succeeded":
            continue
        text = next((blk.text for blk in res.result.message.content if blk.type == "text"), "")
        try:
            parsed[res.custom_id] = json.loads(text).get("keywords", [])
        except json.JSONDecodeError:
            parsed[res.custom_id] = []

    n_kw = 0
    empty = 0
    with OUT.open("w", encoding="utf-8") as out:
        for r in records:
            kws, seen = [], set()
            for k in parsed.get(r["id"], []):
                t = _WS.sub(" ", str(k.get("text", ""))).strip().lower()
                if len(t) < 2 or not any(c.isalpha() for c in t) or t in seen:
                    continue
                seen.add(t)
                sal = int(k.get("salience", 3))
                kws.append({"text": t, "score": round(sal / 5.0, 3)})
            n_kw += len(kws)
            empty += not kws
            out.write(json.dumps({
                "id": r["id"], "title": r["title"], "funder": r["funder"],
                "funder_code": r["funder_code"], "year": r["year"], "keywords": kws,
            }, ensure_ascii=False) + "\n")

    print(f"\ndocs: {len(records)} | avg keyphrases/doc: {n_kw / max(1, len(records)):.1f} | 0-kw docs: {empty}")
    print(f"-> {OUT.relative_to(ROOT)}")
    BATCH_ID_FILE.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
