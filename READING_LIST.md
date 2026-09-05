# Reading list: prior art for the keyword-embedding-clustering pipeline

Pipeline under review: (1) extract keywords/keyphrases, (2) embed and cluster them,
(3) label clusters. Valued for transparency (traceable back to source keywords) and
for supporting an n-to-n topic-to-document relationship.

Legend: **[USER]** = marked by Enrico as to-read · **[SUGGESTED]** = surfaced by
Claude during research, not yet vetted by Enrico.

---

## 1. Direct match — extract keyphrases, then cluster the keyphrases with embeddings

The closest prior art to the actual pipeline: keyword/keyphrase-level clustering
(not document-level), with embeddings as the similarity measure.

- **[USER]** Sia, Dalmia & Mielke (EMNLP 2020), *"Tired of Topic Models? Clusters
  of Pretrained Word Embeddings Make for Fast and Good Topics too!"*
  https://arxiv.org/pdf/2004.14914
  Clusters pretrained word-type embeddings (spherical k-means over the
  vocabulary) and treats each cluster as a topic — the paper Enrico identified
  as the one clear match in the first pass. Caveat: it clusters the whole
  vocabulary rather than a pre-filtered set of extracted keyphrases, so it's
  adjacent to, not identical with, the pipeline's step 1 (targeted keyphrase
  extraction).

- **[SUGGESTED]** Li & Daoutis (SDU@AAAI 2021 workshop), *"Unsupervised
  Key-phrase Extraction and Clustering for Classification Scheme in Scientific
  Publications"*
  https://arxiv.org/abs/2101.09990
  Closest single-paper match found: unsupervised keyphrase extraction from
  scientific documents, embedding of the keyphrases themselves (compares
  ConceptNet semantic-network embeddings vs. contextualized/transformer
  embeddings), then semantic clustering of the keyphrases to build a
  classification scheme. Missing piece relative to the pipeline: no LLM-based
  cluster labeling step.

- **[SUGGESTED]** *"Contextual topic discovery using unsupervised keyphrase
  extraction and hierarchical semantic graph model"* (Journal of Big Data,
  2023)
  https://journalofbigdata.springeropen.com/articles/10.1186/s40537-023-00833-1
  Keyphrase extraction followed by a semantic graph built over the keyphrases,
  clustered hierarchically into topics. Couldn't get past the publisher
  paywall to verify firsthand — read the abstract before citing.

---

## 2. LLM-based cluster labeling (the pipeline's least-precedented step)

Papers/practices that automate the "give the cluster a representative label"
step — none of these cluster keyphrases (they cluster documents), but they're
the direct precedent for the labeling stage specifically.

- **[USER]** Eklund & Forsman (EMNLP 2022 Industry Track), *"Topic Modeling by
  Clustering Language Model Embeddings: Human Validation on an Industry
  Dataset"*
  https://aclanthology.org/2022.emnlp-industry.65/
  Directly clusters dimension-reduced language-model embeddings (document-level,
  not keyword-level) and validates the resulting topics against human judgment
  on an industry dataset. Relevant less for the extraction step and more as
  evidence that "embed → reduce dimensions → cluster → treat cluster as topic"
  is an accepted, human-validated methodology in an applied/industry setting —
  useful precedent if the project needs to defend the clustering stage on
  its own.

- **[SUGGESTED]** BERTopic (Grootendorst, 2022) — practitioner tool, not a
  peer-reviewed venue paper, but the de facto standard this pipeline should be
  compared against. Runs the steps in the *opposite* order: clusters document
  embeddings first, then extracts representative keywords per cluster
  (c-TF-IDF) for labeling, and LLM-based labeling is a common add-on in
  practice (feed top keywords + representative snippets to an LLM, ask for a
  label). Worth citing as the baseline this project's keyword-first ordering
  is positioned against.

---

## 3. Historical/bibliometric precedent (pre-embedding era, phrase-based)

Establishes that "cluster phrases, not documents, then label the clusters" is
a decades-old strategy — these predate embeddings but are the direct
conceptual ancestors of the pipeline.

- **[SUGGESTED]** Zamir & Etzioni (1998), Suffix Tree Clustering / Grouper
  https://www.researchgate.net/publication/2870958_Lingo_Search_Results_Clustering_Algorithm
  (Lingo paper above cites/builds on Grouper/STC; original STC paper itself is
  not open-access, this is the closest accessible reference.)
  Extracts frequently shared phrases from documents, clusters documents by
  shared phrases, labels clusters with the phrases themselves. Direct
  ancestor of the whole pipeline shape, minus embeddings.

- **[SUGGESTED]** Osiński & Weiss (2004), *Lingo: Search Results Clustering
  Algorithm*
  https://www.researchgate.net/publication/2870958_Lingo_Search_Results_Clustering_Algorithm
  Improves on STC using common-phrase discovery plus LSI. Same lineage;
  surviving open-source implementation is Carrot2.

- **[SUGGESTED]** VOSviewer (van Eck & Waltman) — bibliometric mapping tool,
  no single canonical paper link, see https://www.vosviewer.com/
  Term co-occurrence maps: extracts terms from titles/abstracts, builds a
  term co-occurrence network, clusters via modularity, visualizes as "term
  map" (the literal source of the "topic islands" visual metaphor). Documents
  are linked to clusters after the fact, giving natural many-to-many mapping —
  same design goal as the project's second motivating property.

- **[SUGGESTED]** CiteSpace (Chen, Drexel University) — see
  https://citespace.podia.com/ for documentation
  Same term-co-occurrence-clustering family as VOSviewer, adds time-sliced
  analysis (burst detection, betweenness centrality) and automated cluster
  labeling via LSI/log-likelihood ratio — the direct statistical-era ancestor
  of the pipeline's LLM-labeling step.

---

## 4. Adjacent, not a match (clustering used *within* a document, not across the corpus)

Surfaced in the same searches; worth knowing about but don't cite these as
prior art for the pipeline itself — they solve "pick k non-redundant
keyphrases for one document," not "cluster keyphrases across a corpus into
topics."

- **[SUGGESTED]** Alrehamy & Walker (2017), *SemCluster: Unsupervised
  Automatic Keyphrase Extraction Using Affinity Propagation*
  https://www.researchgate.net/publication/318436236_SemCluster_Unsupervised_Automatic_Keyphrase_Extraction_Using_Affinity_Propagation

- **[SUGGESTED]** *"Semantic Unsupervised Automatic Keyphrases Extraction by
  Integrating Word Embedding with Clustering Methods"* (MDPI, MTI 2020)
  https://www.mdpi.com/2414-4088/4/2/30

- **[SUGGESTED]** WEC (Word Embedding and Clustering) — frequency +
  co-occurrence + embedding-weighted clustering for per-document keyword
  extraction; specific citable paper not confirmed, flagging the method name
  only.
