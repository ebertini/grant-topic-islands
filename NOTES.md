# Open Issues & Notes

Running list of things to revisit. Most important / most recently raised first.

---

## 0. Topic Cards removed; each dataset is its own shareable page (2026-09-05)

Removed the Topic Cards view entirely (`web/cards.html`, `docs/cards.html`) — kept only
**Topic Islands**. First pass gave it a live in-page dataset dropdown; reverted per Enrico's
request (2026-09-05) to **one static page per dataset** instead, so each can be shared as its
own URL: `docs/northeastern-awards.html` and `docs/nsf-cise-2021-2025.html`, plus a small
`docs/index.html` landing page linking to both. Also fixed the "grants" dataset's public label —
it's **awards to Northeastern University faculty**, not a generic "General Research Awards".

Mechanism: `web/index.html` bakes in a single `ENTRY` constant (`{id, label, file,
excluded_years}`) naming which dataset that page shows; `pipeline/publish_docs.py` generates
each deployed page by substituting `ENTRY` (and `DATA_DIR`) into a copy of the template — no
shared runtime state between pages, no dropdown. `pipeline/manifest.py` still scans
`data/processed/*/` for available datasets and now also carries a `slug` (page filename) and
`description` (landing-page copy) per dataset. `pipeline/activate.py` (the original
single-active-dataset copy) remains retired.

Verified with a real headless-Chrome run (Puppeteer, installed ad hoc — not a project
dependency) against the landing page and both actual deployed dataset pages: zero console
errors on any of the three; each dataset page loads only its own data (no stale dropdown, no
cross-page dependency); drill-down, keyphrase→grant lookup, and highlighted-abstract expansion
all confirmed working on the deployed CISE page specifically.

---

## 1. Topic↔document linking is too restrictive  — DEFERRED (raised 2026-07-21)

**The step:** `pipeline/coverage.py` (and the `docs` lists) defines how a grant is
linked to a topic/subtopic/keyphrase. Currently: a grant is linked to a keyphrase
**iff that keyphrase was one of the ~10 the LLM extracted from its abstract AND
that keyphrase survived the df≥3 clustering cut.** Grant→subtopic/topic = shares
≥1 such keyphrase (binary, unweighted, union up the tree). So the link is
**extraction-mediated + lexical**, not semantic.

**Why it's unsatisfying (measured on the current 1,654-grant run):**
- **281 grants (17%) link to ZERO topics** — they have keyphrases, but none passed
  df≥3, so they're invisible in coverage and drill-down.
- **Only ~21% of a grant's keyphrases are used** — the other ~79% (the rarer, often
  most specific terms) are dropped by df≥3 and contribute nothing to the link.
- **Binary & unweighted** — one peripheral keyphrase counts the same as eight core ones.
- **Purely lexical** — a grant semantically about a topic but phrased differently
  doesn't link.

**Root cause:** the link is a *byproduct of the clustering vocabulary*, not a
first-class step. We filter to df≥3 (right for clean clusters), then define doc
membership as intersection with that same filtered set. `MIN_DF` is the wrong
lever (lowering it helps sparsity but degrades clustering). **The real fix is to
decouple linking from clustering:** keep df≥3 clusters as topic *definitions*,
but link documents with more than that intersection.

**Candidate mechanisms (to decide later):**
1. **Keyphrase recovery (lexical+, transparent):** map *every* extracted keyphrase
   to a topic — in-vocab directly, out-of-vocab via nearest vocab keyphrase
   (MiniLM). Strength = salience-weighted count. Kills orphans, uses full signal,
   keeps "which keyphrases" provenance. Local, cheap.
2. **Semantic document→topic (SPECTER2):** embed each abstract (SPECTER2's real
   strength — whole documents) and each topic; link by cosine (top-k / threshold).
   Covers all docs, catches non-lexical matches; less transparent about *why*.
3. **LLM per-document assignment (Haiku):** Claude assigns each doc to topic(s)
   from the label list. Most accurate; extra pass; detaches from keyphrase evidence.

**Open decisions before implementing:**
- **Link semantics:** weighted multi-membership (strength per topic) vs single
  primary-topic (hard classification) vs keep binary presence.
- **Mechanism:** which of 1/2/3 above.

---

## 2. Residual catch-all topic "Social Systems & Risk" (185 grants)

The one loose top-level cluster, as of the original 1,654-grant `grants` run. Holds genuine
mis-clusters (cp violation → physics, coxeter groups → math, beamforming → signal processing,
javascript → PL, preterm birth → biomedical; one subtopic literally auto-labeled "Mixed
Mechanisms"). Likely fix: bump `N_TOP` 18 → ~24 in `cluster.py` so it splits and strays rejoin
real topics; optionally `MIN_DF` 3 → 2 for richer leaves now that keyphrases are clean. ~2-min
re-run of cluster→label→seed→coverage. **Note:** the `grants` dataset has since been
reprocessed (now 1,537 docs, not 1,654) — re-check whether this catch-all still exists before
acting on the fix above.

## 4. Embedder decision (resolved, for the record)

Tried E5-large-v2 for extraction+clustering → **worse** than MiniLM here
(retrieval ranking surfaced generic phrases; short-phrase clustering grouped by
surface form / acronym soup). Reverted to MiniLM. The Claude-based extraction
(`keywords_llm.py`) is what actually fixed keyword quality. SPECTER2
doc-centroid clustering idea was proposed but not tried. Saved trees:
`data/processed/topics.e5.json`, `topics.minilm.json` (pre-LLM MiniLM baseline).

## 5. Complementary document-level map (idea)

SPECTER2 "grants-as-points" 2D map of abstracts, separate from the keyword
hierarchy — a different lens on the corpus. Deferred idea, not started.

---

## Setup notes
- LLM pipeline stages (`filter_research.py`, `keywords_llm.py`, `label_llm.py`)
  need `anthropic` in the venv + credentials via `.env.local`
  (`set -a; . ./.env.local; set +a` before running). `.env*` is gitignored.
- Static viz server: `python3 -m http.server 8137` from project root.
