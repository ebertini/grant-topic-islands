# Grant Topic Islands

Visual analysis of a collection of research-grant abstracts: keyphrases are extracted per grant,
organized into a three-level topic hierarchy, and linked to the documents they cover. Two static
D3 views — **Topic Islands** (semantic map, drill-down) and **Topic Cards** (sortable topic grid).

## Live site
Served from `docs/` via GitHub Pages: **https://USERNAME.github.io/grant-topic-islands/**
(replace `USERNAME`). The `docs/` folder is self-contained — `index.html`, `islands.html`,
`cards.html`, and `topics.json`.

## Pipeline (offline, regenerates `data/processed/topics.json`)
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

## View locally
```
python3 -m http.server 8137
# open http://localhost:8137/web/   (or /docs/ for the deploy build)
```
