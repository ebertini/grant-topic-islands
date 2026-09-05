# Grant Topic Islands

Visual analysis of a collection of research-grant abstracts: keyphrases are extracted per grant,
organized into a three-level topic hierarchy, and linked to the documents they cover — rendered
as a static D3 **Topic Islands** view.

## Live site
Served from `docs/` via GitHub Pages: **https://USERNAME.github.io/grant-topic-islands/**
(replace `USERNAME`). Each dataset is its **own page**, independently shareable:

- `northeastern-awards.html` — grants awarded to Northeastern University faculty
- `nsf-cise-2021-2025.html` — NSF CISE directorate awards, 2021–2025

The root `index.html` is a small landing page linking to both.

## Pipeline (offline, regenerates `data/processed/<DATASET>/topics.json`)
```
./.venv/bin/python pipeline/ingest.py           # 0    normalize raw CSV
python3            pipeline/clean.py             # 1    clean text + stopwords
./.venv/bin/python pipeline/filter_research.py   # 1.5 keep research grants (Claude Haiku)
./.venv/bin/python pipeline/keywords_llm.py      # 2   keyphrase extraction (Claude Haiku)
./.venv/bin/python pipeline/cluster.py           # 3   3-level tree + c-TF-IDF labels (MiniLM)
./.venv/bin/python pipeline/label_llm.py         # 3b  topic labels (Claude Opus)
./.venv/bin/python pipeline/seed_layout.py       # 4a  MDS seed coords, doc + abstract index
./.venv/bin/python pipeline/coverage.py          # 4b  document coverage per topic/subtopic
```
LLM stages need `anthropic` in the venv and credentials (`ANTHROPIC_API_KEY` or a local
`.env.local`, which is gitignored). See `PLAN.md` for the design and `NOTES.md` for open issues.

### Multiple datasets, each its own page

Every stage above is scoped by a `DATASET` env var (default `grants`): raw input is
`data/raw/<DATASET>.csv`, and everything the pipeline produces lives under
`data/processed/<DATASET>/`, keeping each dataset's full artifact chain independent and on disk
at the same time.

```
DATASET=nsf_cise ./.venv/bin/python pipeline/ingest.py
DATASET=nsf_cise python3            pipeline/clean.py
DATASET=nsf_cise ./.venv/bin/python pipeline/filter_research.py
DATASET=nsf_cise ./.venv/bin/python pipeline/keywords_llm.py
DATASET=nsf_cise ./.venv/bin/python pipeline/cluster.py
DATASET=nsf_cise ./.venv/bin/python pipeline/label_llm.py
DATASET=nsf_cise ./.venv/bin/python pipeline/seed_layout.py
DATASET=nsf_cise ./.venv/bin/python pipeline/coverage.py
```

Two more steps turn processed datasets into the deployed site:

```
./.venv/bin/python pipeline/manifest.py       # 5  scan data/processed/*/ -> data/processed/manifest.json
./.venv/bin/python pipeline/publish_docs.py   # 6  build docs/: one page per dataset + a landing page
```

`ingest.py`'s raw-CSV adapter auto-detects the column layout (the original multi-agency
`grants.csv` schema, or an NSF award-search style export) — see the adapter docstrings in
`pipeline/ingest.py` for details of each. `manifest.py` also holds small per-dataset display
config: a human **label** and one-line **description** (used on the landing page), a URL
**slug** (the deployed page's filename), and which **years to exclude** from the activity
timeline because they reflect a partial collection window rather than a real drop-off. Add an
entry there for any new dataset that needs any of these — otherwise it falls back to a
prettified id, no description, and no excluded years.

`publish_docs.py` generates `docs/<slug>.html` per dataset by cloning `web/index.html` with its
`ENTRY` constant (which dataset this page shows) and `DATA_DIR` swapped for the deploy path —
each page is fully self-contained, with no dependency on the others or on a shared switcher.
`docs/index.html` is a small landing page linking to every generated page.

## View locally
```
python3 -m http.server 8137
# dev copy (reads ../data/processed/grants/, hardcoded in web/index.html's ENTRY constant):
# open http://localhost:8137/web/
# deploy copy — what's actually shipped, one URL per dataset:
# open http://localhost:8137/docs/                          (landing page)
# open http://localhost:8137/docs/northeastern-awards.html
# open http://localhost:8137/docs/nsf-cise-2021-2025.html
```

## Deploying an update
After regenerating one or more datasets, refresh the manifest and rebuild `docs/`, then commit
and push — GitHub Pages redeploys automatically:
```
./.venv/bin/python pipeline/manifest.py
./.venv/bin/python pipeline/publish_docs.py
git add -A && git commit -m "Update datasets" && git push
```
