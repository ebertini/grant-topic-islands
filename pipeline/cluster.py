"""Stage 3 — Hierarchical clustering into a 3-level topic tree.

Build a global keyword vocabulary (phrases occurring in >= MIN_DF grants), embed
each with the SAME sentence-transformer used by KeyBERT in stage 2, and cluster
with a single Ward-linkage dendrogram. Cutting that one tree at two `maxclust`
levels guarantees strict containment (level-2 clusters nest inside level-1),
which is exactly what the nested-island layout needs.

Each cluster is labelled by its medoid (member keyword nearest the centroid) and
carries aggregate score, document frequency, and funder mix.

Dataset selection: set DATASET=<name> to read/write under
data/processed/<name>/ (default "grants").

Input:  data/processed/<DATASET>/grants.keywords.jsonl
Output: data/processed/<DATASET>/topics.json           (hierarchy; seed coords added in stage 4)
        data/processed/<DATASET>/topic_centroids.npy    (level-1 centroids, for stage 4 UMAP)
"""

from __future__ import annotations

import json
import math
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import torch
from scipy.cluster.hierarchy import fcluster, linkage
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parent.parent
DATASET = os.environ.get("DATASET", "grants")
PROC = ROOT / "data" / "processed" / DATASET
IN = PROC / "grants.keywords.jsonl"
OUT = PROC / "topics.json"
OUT_CENTROIDS = PROC / "topic_centroids.npy"

MODEL_NAME = "all-MiniLM-L6-v2"   # clean LLM keyphrases cluster well here
MIN_DF = 3          # keep phrases occurring in >= this many grants
N_TOP = 18          # level-1 topics
N_SUB = 90          # level-2 subtopics (nested within topics)
LABEL_TERMS = 6     # c-TF-IDF terms kept per node (first 3 form the label)

_TOK = re.compile(r"[a-z][a-z]{2,}")


def ctfidf_labels(cluster_tokens: dict[int, Counter]) -> dict[int, list[str]]:
    """Class-based TF-IDF (BERTopic-style) over the tokens of each cluster's
    member keyphrases. A term scores high when frequent within its cluster but
    rare across the sibling clusters, giving distinctive labels.

    tf-idf(t,c) = f(t,c) * log(1 + A / f(t))  where A = mean tokens per cluster.
    """
    global_freq: Counter = Counter()
    for cnt in cluster_tokens.values():
        global_freq.update(cnt)
    n = len(cluster_tokens) or 1
    A = (sum(global_freq.values()) / n) or 1.0
    labels: dict[int, list[str]] = {}
    for cid, cnt in cluster_tokens.items():
        scored = {t: w * math.log(1 + A / global_freq[t]) for t, w in cnt.items()}
        labels[cid] = sorted(scored, key=lambda t: (-scored[t], t))[:LABEL_TERMS]
    return labels


def funder_mix(doc_ids: list[str], doc_funder: dict[str, str]) -> dict[str, float]:
    c = Counter(doc_funder.get(d, "?") for d in doc_ids)
    total = sum(c.values()) or 1
    return {k: round(v / total, 3) for k, v in c.most_common()}


def main() -> int:
    recs = [json.loads(line) for line in IN.open(encoding="utf-8")]
    n_docs = len(recs)

    # aggregate per keyword across the corpus
    kw_docs: dict[str, list[str]] = defaultdict(list)
    kw_score: dict[str, float] = defaultdict(float)
    doc_funder: dict[str, str] = {}
    for r in recs:
        doc_funder[r["id"]] = r["funder_code"]
        for k in r["keywords"]:
            kw_docs[k["text"]].append(r["id"])
            kw_score[k["text"]] += k["score"]

    vocab = sorted(t for t, docs in kw_docs.items() if len(set(docs)) >= MIN_DF)
    print(f"docs: {n_docs} | vocab (df>={MIN_DF}): {len(vocab)}")

    device = ("mps" if torch.backends.mps.is_available()
              else "cuda" if torch.cuda.is_available() else "cpu")
    print(f"embedding {len(vocab)} keyphrases with {MODEL_NAME} on {device} ...")
    model = SentenceTransformer(MODEL_NAME, device=device)
    emb = model.encode(vocab, normalize_embeddings=True,
                       batch_size=256, show_progress_bar=False).astype(np.float32)

    print("clustering (ward) ...")
    Z = linkage(emb, method="ward")
    l1 = fcluster(Z, N_TOP, criterion="maxclust")
    l2 = fcluster(Z, N_SUB, criterion="maxclust")

    # group vocab indices by (level-1, level-2) — nesting is guaranteed by the
    # shared linkage, so each l2 belongs to exactly one l1.
    by_l1: dict[int, list[int]] = defaultdict(list)
    by_l2: dict[int, list[int]] = defaultdict(list)
    l2_to_l1: dict[int, int] = {}
    for i in range(len(vocab)):
        by_l1[l1[i]].append(i)
        by_l2[l2[i]].append(i)
        l2_to_l1[l2[i]] = l1[i]

    # per-keyword document frequency and tokens (for c-TF-IDF labelling)
    df_i = [len(set(kw_docs[vocab[i]])) for i in range(len(vocab))]
    toks_i = [_TOK.findall(vocab[i]) for i in range(len(vocab))]

    def token_weights(groups: dict[int, list[int]]) -> dict[int, Counter]:
        out: dict[int, Counter] = {}
        for cid, idx in groups.items():
            c: Counter = Counter()
            for i in idx:
                for tok in toks_i[i]:
                    c[tok] += df_i[i]      # weight tokens by keyword doc frequency
            out[cid] = c
        return out

    l1_labels = ctfidf_labels(token_weights(by_l1))
    l2_labels = ctfidf_labels(token_weights(by_l2))

    def kw_leaf(i: int) -> dict:
        docs = sorted(set(kw_docs[vocab[i]]))
        return {
            "text": vocab[i],
            "weight": round(kw_score[vocab[i]], 3),
            "doc_freq": len(docs),
            "docs": docs,
        }

    def cluster_docs(idx: list[int]) -> list[str]:
        d: list[str] = []
        for i in idx:
            d.extend(kw_docs[vocab[i]])
        return d

    topics = []
    centroids = []
    # order level-1 clusters by aggregate score (biggest topics first)
    l1_order = sorted(by_l1, key=lambda c: -sum(kw_score[vocab[i]] for i in by_l1[c]))
    for ti, c1 in enumerate(l1_order, 1):
        idx1 = by_l1[c1]
        centroids.append(emb[idx1].mean(axis=0))
        subs = []
        sub_ids = sorted((c2 for c2, p in l2_to_l1.items() if p == c1),
                         key=lambda c2: -sum(kw_score[vocab[i]] for i in by_l2[c2]))
        for si, c2 in enumerate(sub_ids, 1):
            idx2 = by_l2[c2]
            leaves = sorted((kw_leaf(i) for i in idx2),
                            key=lambda k: (-k["doc_freq"], -k["weight"]))
            subs.append({
                "id": f"t{ti}.{si}",
                "label": " ".join(l2_labels[c2][:3]),
                "terms": l2_labels[c2],
                "score": round(sum(kw_score[vocab[i]] for i in idx2), 3),
                "funder_mix": funder_mix(cluster_docs(idx2), doc_funder),
                "keywords": leaves,
            })
        topics.append({
            "id": f"t{ti}",
            "label": " ".join(l1_labels[c1][:3]),
            "terms": l1_labels[c1],
            "score": round(sum(kw_score[vocab[i]] for i in idx1), 3),
            "funder_mix": funder_mix(cluster_docs(idx1), doc_funder),
            "subtopics": subs,
        })

    funders = sorted({f for f in doc_funder.values()})
    out = {
        "meta": {
            "n_docs": n_docs,
            "n_keywords": len(vocab),
            "min_df": MIN_DF,
            "n_topics": len(topics),
            "n_subtopics": sum(len(t["subtopics"]) for t in topics),
            "funders": funders,
        },
        "topics": topics,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    np.save(OUT_CENTROIDS, np.array(centroids, dtype=np.float32))

    print(f"-> {OUT.relative_to(ROOT)}  ({len(topics)} topics, "
          f"{out['meta']['n_subtopics']} subtopics)")
    print(f"-> {OUT_CENTROIDS.relative_to(ROOT)}")
    print("\n=== level-1 topics (label | #subtopics | #keywords | top funder) ===")
    for t in topics:
        nk = sum(len(s["keywords"]) for s in t["subtopics"])
        top_funder = next(iter(t["funder_mix"]), "?")
        print(f"  {t['label'][:38]:38s} | {len(t['subtopics']):2d} sub | "
              f"{nk:4d} kw | {top_funder}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
