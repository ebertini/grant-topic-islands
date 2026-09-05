# Grant Topic Islands

Visual analysis of a collection of research-grant abstracts: keyphrases are extracted per grant,
organized into a three-level topic hierarchy, and linked to the documents they cover. A single
static D3 view — **Topic Islands** — with a live dropdown to switch between datasets.

## Live site
Served from `docs/` via GitHub Pages: **https://USERNAME.github.io/grant-topic-islands/**
(replace `USERNAME`). The root page *is* the app (no separate landing page) — every processed
dataset ships with it, and a dropdown in the header switches between them client-side.

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

### Multiple datasets, switchable live on the site

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

Two more steps make a processed dataset available to the app, whether running locally
(`web/index.html`) or on the deployed site (`docs/index.html`):

```
./.venv/bin/python pipeline/manifest.py       # 5  scan data/processed/*/ -> data/processed/manifest.json
./.venv/bin/python pipeline/publish_docs.py   # 6  rebuild docs/ (copies every dataset + the app)
```

`ingest.py`'s raw-CSV adapter auto-detects the column layout (the original multi-agency
`grants.csv` schema, or an NSF award-search style export) — see the adapter docstrings in
`pipeline/ingest.py` for details of each. `manifest.py` also holds small per-dataset display
config (a human label, and which years to exclude from the activity timeline because they
reflect a partial collection window rather than a real drop-off) — add an entry there for any
new dataset that needs either.

The app itself never needs to know which datasets exist ahead of time: it fetches
`manifest.json` at load, populates the dropdown, and re-fetches the chosen dataset's
`topics.json` on every switch — entirely client-side, no rebuild required to change the default
view (only to add or update a dataset).

## View locally
```
python3 -m http.server 8137
# open http://localhost:8137/web/        (dev copy, reads ../data/processed/)
# open http://localhost:8137/docs/       (deploy copy, reads ./ — what's actually shipped)
```

## Deploying an update
After regenerating one or more datasets, refresh the manifest and rebuild `docs/`, then commit
and push — GitHub Pages redeploys automatically:
```
./.venv/bin/python pipeline/manifest.py
./.venv/bin/python pipeline/publish_docs.py
git add -A && git commit -m "Update datasets" && git push
```
