"""Stage 2 — Keyword extraction (vanilla KeyBERT).

For each cleaned abstract, extract the top-N keyphrases with KeyBERT using the
default `all-MiniLM-L6-v2` sentence-transformer. Candidates are grammatically
valid noun phrases from KeyphraseVectorizers (spaCy POS pattern
`<J.*>*<N.*>+` = optional adjectives + nouns), which avoids the stopword-gluing
"word salad" a plain CountVectorizer produces. Stopwords are sklearn's English
list UNION the domain stopwords from stage 1. MMR (diversity 0.5) reduces
near-duplicates.

The SAME model is reused in stage 3 for clustering, so the extraction and
hierarchy live in one embedding space (see PLAN.md).

Dataset selection: set DATASET=<name> to read/write under
data/processed/<name>/ (default "grants").

Input:  data/processed/<DATASET>/grants.clean.jsonl
        data/processed/<DATASET>/stopwords.txt
Output: data/processed/<DATASET>/grants.keywords.jsonl
        one object per doc: {id, title, funder, funder_code, year,
                             keywords: [{text, score}, ...]}
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import torch
from keybert import KeyBERT
from keybert.backend import BaseEmbedder
from keyphrase_vectorizers import KeyphraseCountVectorizer
from sentence_transformers import SentenceTransformer
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

ROOT = Path(__file__).resolve().parent.parent
DATASET = os.environ.get("DATASET", "grants")
PROC = ROOT / "data" / "processed" / DATASET
IN = PROC / "grants.clean.jsonl"
STOP = PROC / "stopwords.txt"
OUT = PROC / "grants.keywords.jsonl"

MODEL_NAME = "intfloat/e5-large-v2"   # scientific-capable retrieval embedder
TOP_N = 15            # keyphrases kept per abstract
DIVERSITY = 0.5       # MMR diversity
CHUNK = 200           # docs per batch (for progress + incremental save)

# spaCy POS pattern for candidate noun phrases: optional adjectives + noun(s)
POS_PATTERN = "<J.*>*<N.*>+"
SPACY_PIPELINE = "en_core_web_sm"


def pick_device() -> str:
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


class E5Embedder(BaseEmbedder):
    """KeyBERT backend for E5. E5 expects asymmetric prefixes — long texts
    (documents) get 'passage: ', short texts (candidate phrases) get 'query: '.
    KeyBERT calls embed() for both docs and candidates, so we route by word
    count (abstracts are long; candidate noun phrases are <= a few words)."""

    def __init__(self, model_name: str, device: str):
        super().__init__()
        self.model = SentenceTransformer(model_name, device=device)

    def embed(self, documents, verbose=False):
        texts = [("passage: " if len(str(d).split()) > 8 else "query: ") + str(d)
                 for d in documents]
        return self.model.encode(texts, batch_size=64, normalize_embeddings=True,
                                 show_progress_bar=False)


def clean_phrase(p: str) -> str:
    """Normalize a keyphrase: rejoin spaCy-split hyphens ('extra - cellular' ->
    'extra-cellular'), collapse whitespace, and trim stray edge punctuation."""
    p = p.replace(" - ", "-")
    p = re.sub(r"\s+", " ", p).strip(" -")
    return p


def keep_phrase(p: str) -> bool:
    """Drop empties, single chars, and punctuation-only tokens."""
    return len(p) >= 2 and any(c.isalpha() for c in p)


def load_stopwords() -> list[str]:
    domain = {
        line.strip()
        for line in STOP.open(encoding="utf-8")
        if line.strip() and not line.startswith("#")
    }
    return sorted(ENGLISH_STOP_WORDS | domain)


def main() -> int:
    records = [json.loads(line) for line in IN.open(encoding="utf-8")]
    n = len(records)
    stop_words = load_stopwords()
    print(f"docs: {n} | stopwords (english + domain): {len(stop_words)}")

    vectorizer = KeyphraseCountVectorizer(
        spacy_pipeline=SPACY_PIPELINE,
        pos_pattern=POS_PATTERN,
        stop_words=stop_words,
        lowercase=True,
    )

    device = pick_device()
    print(f"loading model {MODEL_NAME} on {device} ...")
    kb = KeyBERT(model=E5Embedder(MODEL_NAME, device))

    with OUT.open("w", encoding="utf-8") as out:
        for start in range(0, n, CHUNK):
            chunk = records[start : start + CHUNK]
            docs = [r["abstract"] for r in chunk]
            batch = kb.extract_keywords(
                docs,
                vectorizer=vectorizer,
                use_mmr=True,
                diversity=DIVERSITY,
                top_n=TOP_N,
            )
            # KeyBERT returns a flat list (not list-of-lists) when given a single
            # doc; normalize so we always iterate per-doc.
            if docs and batch and not isinstance(batch[0], list):
                batch = [batch]
            for rec, kws in zip(chunk, batch):
                cleaned = []
                seen = set()
                for t, s in kws:
                    ct = clean_phrase(t)
                    if keep_phrase(ct) and ct not in seen:
                        seen.add(ct)
                        cleaned.append({"text": ct, "score": round(float(s), 4)})
                out.write(json.dumps({
                    "id": rec["id"],
                    "title": rec["title"],
                    "funder": rec["funder"],
                    "funder_code": rec["funder_code"],
                    "year": rec["year"],
                    "keywords": cleaned,
                }, ensure_ascii=False) + "\n")
            print(f"  {min(start + CHUNK, n):5d}/{n} docs")

    print(f"-> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
