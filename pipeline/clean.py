"""Stage 1 — Clean.

Two layers of cleaning:

(a) STRUCTURAL — regex removal of grant-writing scaffolding that isn't topical:
    - the leading "<award_id>  <PI name(s)>" prefix NSF abstracts carry
    - NSF's boilerplate "statutory mission / intellectual merit / broader
      impacts review criteria" sentences

(b) DATA-DRIVEN STOPLIST — terms that appear in a large fraction of abstracts
    are grant-generic filler ("research", "project", "study", ...), not signal.
    We compute per-corpus document frequency and emit the high-DF terms as an
    extra stopword list for stage 2 (KeyBERT). This is corpus-specific by design.

Dataset selection: set DATASET=<name> to read/write under
data/processed/<name>/ (default "grants").

Input:  data/processed/<DATASET>/grants.normalized.jsonl
Output: data/processed/<DATASET>/grants.clean.jsonl   (cleaned abstract text)
        data/processed/<DATASET>/stopwords.txt         (domain stopwords for stage 2)
"""

from __future__ import annotations

import html
import json
import os
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATASET = os.environ.get("DATASET", "grants")
PROC = ROOT / "data" / "processed" / DATASET
IN = PROC / "grants.normalized.jsonl"
OUT_DOCS = PROC / "grants.clean.jsonl"
OUT_STOP = PROC / "stopwords.txt"

# Terms appearing in >= this fraction of abstracts are treated as grant-generic
# filler and added to the domain stoplist. Tune after eyeballing the report.
HIGH_DF = 0.30

# A curated seed of grant-generic words to include even if below the DF cutoff.
SEED_STOPWORDS = {
    "research", "project", "study", "studies", "program", "proposal",
    "proposed", "investigate", "investigator", "investigators", "award",
    "grant", "funding", "support", "supported", "develop",
    "understanding", "approach", "goal", "goals", "objective", "objectives",
    "aim", "aims", "work", "results", "provide", "provides", "new", "novel",
    "important", "significant", "student", "students", "education",
    "educational", "broader", "impact", "impacts", "activities",
    # administrative / institutional boilerplate (manual overrides — these sit
    # below the data-driven DF cutoff but are clearly non-topical)
    "pi", "pis", "co", "nsf", "nih", "university", "universities",
    "northeastern", "foundation", "department",
    # generic attractors that formed incoherent clusters in stage 3, plus
    # leftover review-criteria boilerplate ("intellectual merit")
    "future", "topics", "topic", "explore", "fundamental", "national",
    "level", "levels", "availability", "intellectual", "merit",
    "practice", "guidelines",
}

# Content words that must SURVIVE even when high-DF: generic alone, but the
# backbone of real keyphrases ("data science", "control systems", ...). Stopping
# them would prevent those n-grams from ever forming in stage 2.
PROTECT = {
    "data", "systems", "system", "science", "development", "model", "models",
    "information", "materials", "design", "control", "network", "networks",
    "analysis", "methods", "method", "structure", "structures", "cell", "cells",
    "gene", "genes", "protein", "proteins", "software", "algorithm", "algorithms",
    "energy", "molecular", "quantum", "learning", "computing",
}

# Manual overrides — boilerplate phrases handled as full-sentence removals.
_BOILERPLATE_SENTENCE = re.compile(
    r"[^.]*(?:reflects\s+NSF['’]s\s+statutory\s+mission"
    r"|intellectual\s+merit\s+and\s+broader\s+impacts\s+review\s+criteria"
    r"|deemed\s+worthy\s+of\s+support\s+through\s+evaluation)[^.]*(?:\.|$)",
    re.IGNORECASE,
)

_AWARD_PREFIX = re.compile(r"^\s*(\d{5,})[\s.:\-]+")
_NAME = r"[A-Z][A-Za-z'’.\-]+,\s+[A-Z][A-Za-z'’.\-]+(?:\s+[A-Z]\.?)?"
_PI_PREFIX = re.compile(rf"^((?:{_NAME})(?:\s*(?:;|,|and|&)\s*(?:{_NAME}))*)\s+")

_WORD = re.compile(r"[a-z][a-z\-]{2,}")

# HTML noise. Source abstracts carry both literal tags (<br/>) and "and-mangled"
# entities where "&" was rewritten to "and" upstream (&lt; -> "andlt").
# Collapse the <br> break patterns as a UNIT first so a legitimate standalone
# "Br" (bromine) survives; then unescape real entities, strip tags, and remove
# any leftover mangled-entity tokens.
_HTML_BREAK = re.compile(r"(?:andlt|&lt;)\s*br\s*/?\s*(?:andgt|&gt;)", re.IGNORECASE)
_HTML_TAG = re.compile(r"<[^>]+>")
# mangled entities never occur inside real English words -> substring removal
_MANGLED_ENTITY = re.compile(r"and(?:lt|gt|amp|quot|apos)", re.IGNORECASE)
# tag remnants like "br/" or "/br" (but not a standalone "Br" = bromine)
_BR_REMNANT = re.compile(r"\bbr\s*/|/\s*br\b", re.IGNORECASE)


def sanitize_html(text: str) -> str:
    text = _HTML_BREAK.sub(" ", text)   # "andlt br andgt" / "<br/>"-as-mangled
    text = html.unescape(text)          # real &lt; &gt; &amp; -> < > &
    text = _HTML_TAG.sub(" ", text)     # literal <br/>, <p>, ...
    text = _MANGLED_ENTITY.sub(" ", text)  # stray andlt/andgt/andamp tokens
    text = _BR_REMNANT.sub(" ", text)   # leftover br/ or /br tag remnants
    return text


def strip_structural(text: str) -> tuple[str, bool, bool]:
    """Remove award-id/PI prefix and NSF boilerplate sentences.

    Returns (cleaned_text, had_award_prefix, had_boilerplate).
    """
    had_award = had_boiler = False

    text = sanitize_html(text)

    m = _AWARD_PREFIX.match(text)
    if m:
        had_award = True
        rest = text[m.end():]
        # Only strip PI names when the award-id header signalled the NSF format,
        # to avoid eating real sentence text.
        nm = _PI_PREFIX.match(rest)
        if nm:
            rest = rest[nm.end():]
        text = rest

    new_text, n = _BOILERPLATE_SENTENCE.subn(" ", text)
    if n:
        had_boiler = True
        text = new_text

    return re.sub(r"\s+", " ", text).strip(), had_award, had_boiler


def main() -> int:
    records = [json.loads(line) for line in IN.open(encoding="utf-8")]
    n = len(records)

    df: Counter[str] = Counter()
    n_award = n_boiler = 0

    with OUT_DOCS.open("w", encoding="utf-8") as out:
        for rec in records:
            cleaned, had_award, had_boiler = strip_structural(rec["abstract"])
            n_award += had_award
            n_boiler += had_boiler
            rec["abstract"] = cleaned
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")

            for tok in set(_WORD.findall(cleaned.lower())):
                df[tok] += 1

    cutoff = int(HIGH_DF * n)
    data_driven = {t for t, c in df.items() if c >= cutoff} - PROTECT
    stopwords = sorted((data_driven | SEED_STOPWORDS) - PROTECT)

    with OUT_STOP.open("w", encoding="utf-8") as fh:
        fh.write("# domain stopwords for stage 2 (union with sklearn 'english')\n")
        fh.write(f"# data-driven: df >= {HIGH_DF:.0%} ({cutoff}/{n} docs); plus curated seed\n")
        for w in stopwords:
            fh.write(w + "\n")

    print(f"docs cleaned:            {n}")
    print(f"  award/PI prefix removed: {n_award}")
    print(f"  boilerplate sentence(s): {n_boiler}")
    print(f"data-driven stopwords (df >= {HIGH_DF:.0%} = {cutoff} docs): {len(data_driven)}")
    print(f"total domain stopwords:  {len(stopwords)}")
    print(f"-> {OUT_DOCS.relative_to(ROOT)}")
    print(f"-> {OUT_STOP.relative_to(ROOT)}")

    print("\ntop 40 terms by document frequency (eyeball the cutoff):")
    for tok, c in df.most_common(40):
        if tok in PROTECT:
            mark = "  <- protected (phrase backbone)"
        elif c >= cutoff:
            mark = "  <- STOP"
        else:
            mark = ""
        print(f"  {c/n:5.1%}  {tok}{mark}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
