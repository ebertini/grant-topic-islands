# Grant Topic Islands — Development Plan

A visual analytics app to analyze a collection of grant abstracts from various
funding sources. An offline Python pipeline extracts keywords and a topic
hierarchy, emits a single JSON artifact, and a static D3 frontend renders it as
nested **text islands**.

## Settled decisions

| Question | Decision |
|---|---|
| Data scale | Low thousands (1k–10k abstracts) |
| Stack | Python pipeline (offline) + JS/D3 static frontend |
| Pipeline mode | Batch precompute → serve static `topics.json` |
| Island style | Nested circle packing, **text as the visual primitive**, loose packing |
| Step 2 embedder | KeyBERT (`all-MiniLM-L6-v2`) + KeyphraseVectorizers (POS noun-phrase candidates) |
| Step 3 embedder | **Same** `all-MiniLM-L6-v2`, for a consistent space |

## Architecture

```
abstracts (CSV/JSON, ~1–10k)
   │  [Python, offline, run once]
   ▼
 0 ingest → 1 clean → 2 KeyBERT → 3 hierarchical cluster → 4 label + seed coords
   │
   ▼  topics.json   (hierarchy + semantic seed coords + doc index)
   │  [static web app — D3 + Canvas/SVG]
   ▼
 nested text islands + zoom / hover / filter-by-funder
```

No web server required for the static build — the pipeline writes `topics.json`
and the frontend is served as static files. Add a thin FastAPI layer only if a
future "re-run a stage from the UI" path is wanted.

## The artifact schema (the contract — build first)

Single tree with strict containment (guaranteed by using one dendrogram in
step 3). `weight` → font size; `seed` → semantic placement; `docs`/`funder_mix`
→ interaction and the funder facet.

```jsonc
{
  "meta": { "n_docs": 4210, "funders": ["NSF","NIH","DOE"], "built": "..." },
  "topics": [                         // level 1
    { "id": "t3", "label": "neural computation",
      "seed": [0.42, 0.71],           // UMAP 2D for semantic placement
      "score": 812, "funder_mix": {"NSF":0.6,"NIH":0.4},
      "subtopics": [                  // level 2
        { "id": "t3.1", "label": "spiking models",           // c-TF-IDF label
          "llm_label": "Spiking Neural Models",             // Claude label (stage 3b)
          "terms": ["spiking","models","..."], "score": 190,
          "keywords": [               // level 3 = leaves (the text marks)
            { "text": "spiking neural network", "weight": 0.88,
              "doc_freq": 37, "docs": [1102, 88] }
          ]
        }
      ]
    }
  ],
  "docs": { "1102": { "title": "...", "funder": "NSF", "year": 2023 } }
}
```

## Pipeline stages

**0 · Ingest.** Normalize sources to `{id, title, abstract, funder, year}`.

**1 · Clean.** (a) Standard: lowercase-fold, stopwords, noun-phrase candidates.
(b) Grant boilerplate ("broader impacts", "intellectual merit", "this award
reflects the agency's statutory mission", …) removed **data-driven**: any
term/phrase with document frequency above ~40–50% of the corpus is boilerplate,
not signal. Keep a small manual override list for agency-specific formulas.

**2 · Keyword extraction — vanilla KeyBERT.** `KeyBERT()` with the default
`all-MiniLM-L6-v2`. Candidates via `CountVectorizer` n-grams (1,3) filtered by
the step-1 stoplist; rank by cosine to the doc embedding; **MMR (diversity ≈
0.5)** to avoid redundant variants. Keep top-k keywords per abstract.
- **M2 validation checkpoint:** eyeball keywords for ~30 abstracts before
  building anything downstream.

**3 · 3-level hierarchy — same `all-MiniLM-L6-v2`.** Collapse all keywords into a
global vocabulary; merge near-duplicates (lemma + cosine > ~0.9). Embed each
unique keyword with the **same** sentence-transformer (reuse KeyBERT's candidate
embeddings where possible) → one **agglomerative tree** (Ward linkage,
L2-normalized vectors) → cut at **two heights** for exactly 3 display levels.
Using a single dendrogram guarantees the strict nesting the layout needs.
Target ~8–15 top topics, a handful of subtopics each. Each internal node keeps
**two labels**: `label` from **c-TF-IDF** (distinctive tokens, computed in
stage 3) and `llm_label` from **Claude** (stage 3b, `pipeline/label_llm.py` —
`claude-opus-4-8` + structured outputs, all nodes in one batched call). The LLM
labels are far more readable (`theory quantum string` → "Theoretical Physics &
Mathematics"). `label_llm.py` needs Anthropic credentials (`ANTHROPIC_API_KEY`
or `ant auth login`).

**4 · Layout seeds.** Precompute only the semantic part: UMAP the top-level topic
centroids → 2D `seed` coords so semantically-near islands sit near each other.
Sub-level packing and text placement happen in the browser.

## Frontend — text-filled nested islands

- Skeleton from `d3.hierarchy().sum(weight)` → `d3.pack()` with generous
  `.padding()` for the loose feel. Override level-1 circle **centers** with the
  UMAP `seed` coords (settle with a light `d3-force` + collision) so the
  top-level arrangement is semantic, not arbitrary.
- Circles stay **invisible** — containers only. Level-3 keywords render as
  **text**, font size ∝ `weight`. Level-1/2 nodes get header labels behind the
  words. Optional soft hull/blob outline per island for the "map" read.
- Within a sub-island, place keyword strings via `d3-force` with **rectangular
  (bounding-box) collision** on the text — loose packing makes this easy.
- **Interactions:** semantic zoom / LOD (topic labels far out, keywords appear on
  zoom — non-optional at 10k keywords); hover → highlight + `doc_freq`; click a
  keyword → source grants; color/filter by funder via `funder_mix`. Render text
  on Canvas if SVG gets sluggish past a few thousand labels.

## Phasing

- **M0** — Freeze `topics.json` schema; hand-write a synthetic sample; get D3
  rendering nested text from it. (Unblocks the frontend immediately.)
- **M1** — Cleaning + candidate generation.
- **M2** — Vanilla KeyBERT; **validate keyword quality** before proceeding.
- **M3** — Clustering + labeling → real `topics.json`.
- **M4** — UMAP seeds + full island layout & LOD.
- **M5** — Funder facet, source-grant drill-down, polish.

## Risks

1. Boilerplate is corpus-specific → go data-driven (doc-frequency threshold).
2. Label overlap at scale → LOD/semantic zoom is designed in from M0.
3. Cluster granularity → keep the two cut heights and topic counts as params.
4. `all-MiniLM-L6-v2` is domain-general → hierarchy may group some jargon
   loosely; acceptable for the baseline (see upgrade path).

## Upgrade path (after seeing baseline results)

Because steps 2 and 3 share **one** embedding model behind a `.embed(texts)`
wrapper, swapping is a single-line change:
- **`intfloat/e5-large-v2`** — query/passage retrieval embedder; short phrases
  *and* abstracts both in-distribution; domain-general. Default upgrade. (Needs
  `"query:"`/`"passage:"` prefixes.)
- **`pritamdeka/S-PubMedBert-MS-MARCO`** — if the corpus is NIH/biomedical-heavy.
- **SPECTER2** — demote to an optional *document-level* map of abstracts
  (grants-as-points), separate from the keyword/hierarchy path. Not used for
  phrases (off-distribution for short spans).

## Running the pipeline & viz

Pipeline (offline, in order):
```
./.venv/bin/python pipeline/ingest.py         # 0    raw csv -> normalized.jsonl
python3            pipeline/clean.py           # 1    clean + stopwords
./.venv/bin/python pipeline/filter_research.py # 1.5 keep research grants (Haiku; needs API creds)
./.venv/bin/python pipeline/keywords.py        # 2   keyphrases  (reads grants.research.jsonl)
./.venv/bin/python pipeline/cluster.py         # 3   3-level tree + c-TF-IDF labels
./.venv/bin/python pipeline/label_llm.py       # 3b  Claude llm_label (needs API creds)
./.venv/bin/python pipeline/seed_layout.py     # 4a  MDS seed coords + docs index
./.venv/bin/python pipeline/coverage.py        # 4b  doc coverage per topic/subtopic
```
LLM stages (`filter_research`, `label_llm`, and the planned Claude extraction)
need `pip install anthropic` in the venv and Anthropic credentials
(`ANTHROPIC_API_KEY` or `ant auth login`).
Viz (static): serve the project root and open the page —
```
python3 -m http.server 8137
# then open  http://localhost:8137/web/
```
The frontend (`web/index.html`, D3) reads `data/processed/topics.json`. Text
islands positioned by semantic `seed`; d3.pack interiors (loose); keyword text
sized by weight; semantic-zoom LOD (topic → subtopic → keyword); hover for
grant count; click a keyword to list its source grants; funder facet (filter +
optional color-by-funder). Colors: validated categorical slots (NSF/NIH/Other).
