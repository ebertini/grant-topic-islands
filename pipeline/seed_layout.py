"""Stage 4a — Semantic seed coordinates + document index.

Adds the pieces the frontend needs that aren't semantic-free:
  - `seed: [x, y]` on each level-1 topic: a 2D embedding of the topic centroids
    (MDS on cosine distance) so semantically-near islands sit near each other.
    MDS (not UMAP) because there are only ~18 centroids — UMAP is unstable at
    that size; MDS on a precomputed distance matrix is deterministic and apt.
  - `docs`: an index {id: {title, funder, funder_code, year}} for the grants
    referenced by kept keywords, so clicking a keyword can list its source
    grants.
  - `funder` on each keyword leaf: the dominant funder among its source docs,
    for the frontend's funder colour/facet.

Input:  data/processed/topics.json
        data/processed/topic_centroids.npy
        data/processed/grants.keywords.jsonl   (doc metadata)
Output: data/processed/topics.json  (updated in place: seed, docs, kw funder)
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np
from sklearn.manifold import MDS

ROOT = Path(__file__).resolve().parent.parent
TOPICS = ROOT / "data" / "processed" / "topics.json"
CENTROIDS = ROOT / "data" / "processed" / "topic_centroids.npy"
KEYWORDS = ROOT / "data" / "processed" / "grants.keywords.jsonl"
RESEARCH = ROOT / "data" / "processed" / "grants.research.jsonl"


def seed_coords(centroids: np.ndarray) -> np.ndarray:
    """2D MDS of L2-normalized centroids on cosine distance, scaled to [0,1]."""
    unit = centroids / (np.linalg.norm(centroids, axis=1, keepdims=True) + 1e-9)
    dist = 1.0 - (unit @ unit.T)
    np.fill_diagonal(dist, 0.0)
    dist = np.clip(dist, 0.0, None)
    xy = MDS(n_components=2, dissimilarity="precomputed", random_state=42,
             normalized_stress="auto").fit_transform(dist)
    lo, hi = xy.min(axis=0), xy.max(axis=0)
    return (xy - lo) / (hi - lo + 1e-9)


def main() -> int:
    data = json.loads(TOPICS.read_text(encoding="utf-8"))
    centroids = np.load(CENTROIDS)

    xy = seed_coords(centroids)
    for t, (x, y) in zip(data["topics"], xy):
        t["seed"] = [round(float(x), 4), round(float(y), 4)]

    # cleaned abstracts (for the frontend's expandable-abstract + keyphrase highlighting)
    abstracts: dict[str, str] = {}
    if RESEARCH.exists():
        for line in RESEARCH.open(encoding="utf-8"):
            r = json.loads(line)
            abstracts[r["id"]] = r.get("abstract", "")

    # doc metadata index
    doc_meta: dict[str, dict] = {}
    for line in KEYWORDS.open(encoding="utf-8"):
        r = json.loads(line)
        doc_meta[r["id"]] = {
            "title": r["title"],
            "funder": r["funder"],
            "funder_code": r["funder_code"],
            "year": r["year"],
            "abstract": abstracts.get(r["id"], ""),
        }

    # dominant funder per keyword leaf + collect referenced docs
    referenced: set[str] = set()
    for t in data["topics"]:
        for s in t["subtopics"]:
            for k in s["keywords"]:
                referenced.update(k["docs"])
                codes = Counter(
                    doc_meta[d]["funder_code"] for d in k["docs"] if d in doc_meta
                )
                k["funder"] = codes.most_common(1)[0][0] if codes else "?"

    data["docs"] = {d: doc_meta[d] for d in sorted(referenced) if d in doc_meta}

    TOPICS.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"seed coords: {len(data['topics'])} topics")
    print(f"docs index:  {len(data['docs'])} grants")
    print(f"-> {TOPICS.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
