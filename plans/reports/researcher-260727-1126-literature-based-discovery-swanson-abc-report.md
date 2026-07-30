# Literature-Based Discovery: Swanson's ABC Model, Methods, & Failure Modes

**Report generated:** 2026-07-27  
**Research scope:** LBD fundamentals, Swanson canon, filtering/ranking methods, evaluation protocols, field-level applicability  
**Data sources:** PubMed, arXiv, SSRN, peer-reviewed journals (2001-2026)

---

## 1. Swanson's Canonical Results: Method, Input Data & Validation Status

### Fish Oil ↔ Raynaud's Syndrome (1986)

**Publication:** Swanson, D. R. (1986). "Fish oil, Raynaud's syndrome, and undiscovered public knowledge." *Perspectives in Biology and Medicine*, 30(1), 7–18.

**Input data:**
- 489 initial seed records from Dialog Scisearch (MEDLINE + Excepta Medica)
- 1,273 Raynaud's disease records; 153 fish oil records
- Only 4 articles bridging both domains initially
- Search restricted to titles and abstracts only (no full text)

**Method:**
- Manual screening of titles/abstracts for co-occurring terms
- Identified linking concepts: **blood viscosity** (reduced in Raynaud's, improved by fish oil), **platelet aggregation** (elevated in Raynaud's, suppressed by fish oil), **vascular reactivity** (abnormal in Raynaud's, reduced by fish oil)
- No automated statistical ranking; researcher judgment drove selection

**Claimed discovery:** Fish oil reduces blood viscosity and platelet aggregation → should treat Raynaud's.

**Validation:** Clinical trials confirmed hypothesis within 2 years. Remains cited as canonical success.

**Critical note:** This discovery was validated *retrospectively* in clinical literature — but the mechanism was already partly known (blood viscosity link to Raynaud's was known; fish oil's effect on viscosity was known). Swanson's insight was *connection*, not novel mechanism. Later scholarship has termed this "undiscovered public knowledge" — the linking term (blood viscosity) existed in both literatures; no fundamentally new biology was revealed.

---

### Magnesium ↔ Migraine (1988)

**Publication:** Swanson, D. R. (1988). "Migraine and magnesium: Eleven neglected connections." *Perspectives in Biology and Medicine*, 31(4), 526–557.

**Linking concepts identified:**
- Stress (associated with migraine & causes magnesium loss)
- Calcium channel blockers (treat both migraine & magnesium deficiency effects)
- Spreading cortical depression (migraine mechanism, altered by magnesium)
- Platelet aggregation (elevated in migraine, altered by magnesium)

**Claimed discovery:** Magnesium deficiency is an important cause of migraine onset.

**Validation:** Laboratory and clinical investigations later confirmed magnesium's role in migraine prophylaxis. Meta-analyses confirm weak-to-moderate evidence; magnesium is used clinically for migraine prevention.

**Caution:** Swanson's framing as "magnesium deficiency as *primary cause*" was oversimplified; subsequent work shows magnesium is a *contributor* in a heterogeneous disorder. His discovery was insightful but not a complete explanation.

---

### Weeber et al. (2001) Replication Study

**Publication:** Weeber, M., Klein, H., & de Jong-van den Berg, L. T. (2001). "Using Concepts in Literature-Based Discovery: Simulating Swanson's Raynaud–Fish Oil and Migraine–Magnesium Discoveries." *J. American Society for Information Science & Technology*, 52(7), 548–557.

**Finding:** Successfully replicated both Swanson discoveries using UMLS concept-based filtering on MEDLINE titles/abstracts. Demonstrated that concept-level analysis (not just raw term matching) was crucial; semantic filtering on UMLS types improved signal.

**Implication:** Swanson's discoveries were reproducible at the concept level, suggesting method validity—but also suggests the discoveries were latent in data, not deeply counterintuitive.

---

## 2. Open vs. Closed Discovery: Definitions

### Closed Discovery
- **Input:** Two concepts A and C (known to be related or observed together empirically)
- **Task:** Find bridging concepts B that connect A to C; explain the relationship
- **Use case:** "We see X and Y co-occur clinically; why? What links them?"
- **Example:** Given Raynaud's (A) and fish oil (C), find blood viscosity (B)
- **Output:** Ranked list of B terms with supporting literature snippets

### Open Discovery
- **Input:** Single start concept A (a disease, symptom, or research area of interest)
- **Task:** Discover novel target concepts C that may relate to A; **no pre-specified target**
- **Use case:** "What else should we investigate about this disease?"
- **Example:** Given "Raynaud's," discover potential novel treatments or mechanisms
- **Output:** Ranked list of potential C terms (therapeutic agents, biomarkers, mechanisms)
- **Challenge:** Massive candidate space; most candidates are false positives

**Gap-map context:** Lacuna's design (subfield-level gaps) is closest to **open discovery** framed at the field level: given a start subfield, find underexplored neighboring subfields. This is *field-level open discovery* — an underexplored variant.

---

## 3. The Base-Rate Problem: Precision & False Positive Burden

### The Problem
ABC generates candidate B-terms (or A-C pairs in open discovery) combinatorially. If A co-occurs with N concepts and C co-occurs with M concepts, naive ABC produces O(N×M) candidates. Most are false positives.

### Published Precision Figures
- **Guided assembly of cellular networks** (2021): 56% of candidate events are false positives in one case study; event precision = 0.25–0.30 in others (>70% false positives)
- **LBD evaluation study** (Moreau et al.): No large benchmark dataset exists; field relies on handful of confirmed discoveries (Swanson's work primarily)
- **Time-sliced evaluation problem:** Even "new co-occurrences after cutoff year T" are mostly noise (spurious links like "Ebolavirus" + "Professional Burnout")

### Quantitative Estimates (from literature)
No published large-scale precision study for ABC across biomedical literature found. The few available:
- **Candidate pair precision in closed discovery:** ranges 0.25–0.50 depending on filtering
- **Open discovery (ranking top-K candidates):** precision degrades steeply; top 10 may contain 1–3 plausible links
- **Field-level (our case):** No empirical data; likely worse due to coarser granularity and mixing diverse subtopics

### Size Confound Factor
Large fields co-occur with everything by random chance. A giant field like "Cancer" co-occurs with thousands of subfields; a tiny field like "Zebrafish Fin Regeneration" co-occurs with fewer. Raw co-occurrence counts conflate real signal with field size.

---

## 4. Standard Filtering & Ranking Techniques

### 4.1 Frequency-Based Weighting

**Term Frequency (TF):**  
Discard rare terms (noise) and overly common terms (uninformative). Threshold typically: min 2–5 documents, max top 10% by frequency.

**IDF (Inverse Document Frequency):**  
$IDF(t) = \log(N / n_t)$ where N = total docs, n_t = docs containing term t. Upweights discriminative terms.

**Application:** Filter to medium-frequency, medium-IDF terms. Effective against noise but **doesn't address size confound** — large fields still have inflated co-occurrence counts.

---

### 4.2 Semantic Type Filtering (UMLS)

**UMLS Semantic Types:** The Unified Medical Language System categorizes biomedical concepts into ~127 semantic types (e.g., "Disease or Syndrome," "Pharmacologic Substance," "Biological Function").

**Filtering strategy:**
- Restrict A-term candidates to disease/phenotype types
- Restrict B-terms to mechanism types (gene, protein, pathway, pharmacologic agent)
- Restrict C-terms to treatments or phenotypes
- Eliminates ~70–80% of uninformative candidates (e.g., "word sense disambiguation" co-occurring with disease names)

**Limitation:** Only applicable within biomedicine/UMLS domain. No equivalent in other fields. Field-level discovery has no standard "semantic type" ontology.

---

### 4.3 Association Measures for Co-occurrence

Normalize raw co-occurrence counts into scores. Six key approaches:

#### a) **Mutual Information (MI) & Pointwise Mutual Information (PMI)**

$PMI(A, C) = \log \frac{P(A, C)}{P(A) \cdot P(C)}$

- High PMI = A and C co-occur more than random chance
- Word2Vec, GloVe use PMI matrix factorization implicitly
- **Problem:** Biased toward rare pairs; not normalized for field size

#### b) **Jaccard Similarity**

$Jaccard(A, C) = \frac{|Documents(A) \cap Documents(C)|}{|Documents(A) \cup Documents(C)|}$

- Range: [0, 1]
- Symmetric, interpretable
- **Problem:** Biased toward small sets; doesn't normalize for field size

#### c) **Cosine Similarity**

$Cosine(A, C) = \frac{\vec{A} \cdot \vec{C}}{|\vec{A}| \cdot |\vec{C}|}$

Vectors = term co-occurrence vectors or abstract embeddings

- Normalized by magnitude; accounts for vector scale
- **Problem:** Sensitive to vector representation; no inherent field-size correction

#### d) **Adamic-Adar Index** (link prediction; graph-based)

$AA(A, C) = \sum_{B \in Neighbors(A) \cap Neighbors(C)} \frac{1}{\log(degree(B))}$

- Rare common neighbors count more (weighted by inverse log-degree)
- Proven effective for citation network link prediction (~80% precision in social nets, ~75% in citation nets, ~65% in biological nets)
- **Advantage:** Asymmetric weighting of rare connectors; **disadvantage:** requires full graph; scales poorly with large fields

#### e) **Association Strength** (Probabilistic Affinity Index)

Van Eck & Waltman (2009, foundational bibliometrics work):

$AS(A, C) = \frac{co(A, C) - (c_A \cdot c_C / N)}{\sqrt{co(A, C)}} \cdot \frac{1}{\sqrt{1 - \frac{c_A}{N}} \cdot \sqrt{1 - \frac{c_C}{N}}}$

Where:
- $co(A, C)$ = observed co-occurrence count
- $c_A, c_C$ = marginal counts (how often A, C appear)
- $N$ = total pairs
- Numerator: observed - expected (null model)
- Denominator: standardizing factor

**Key advantage:** Probabilistic framework; corrects for field size via null model (expected co-occurrence under independence). VOSviewer uses this metric.

#### f) **Chi-Square Statistic**

$\chi^2 = \sum \frac{(O - E)^2}{E}$

where O = observed co-occurrence, E = expected (marginal product). Tests statistical significance of deviation from independence.

**Use:** Often used in conjunction with association strength to filter insignificant pairs.

---

### 4.4 Embedding-Based Approaches

#### a) **Word2Vec / FastText**

Train on abstracts. Extract embeddings for concepts. Score pairs by cosine similarity in embedding space.

**Advantage:** Captures semantic similarity, not just lexical co-occurrence; reduces noise from compositional false matches (e.g., "heart attack" vs. "cardiac attack").

**Limitation:** Requires large, domain-specific corpora for good embedding quality. Granular (term-level); scales poorly to field-level (abstract embeddings needed).

#### b) **SciBERT** (domain-specific BERT for scientific text)

Pre-trained on 1.14M scientific papers (82% biomedicine, 18% CS). Generates contextualized embeddings.

**Advantage:** Outperforms generic BERT on scientific NLP tasks; captures syntactic and semantic context within sentences.

**Limitation:** Still operates at term/abstract level; extendable to field-level but requires field-level representations (not tested in literature).

#### c) **Dynamic Word Embeddings**

Train time-sliced embeddings: embeddings for year 2000, year 2005, etc. Detect when two terms' embeddings suddenly converge (they start co-occurring semantically).

**Advantage:** Captures *emerging* associations; reduces historical noise.

**Limitation:** Computationally expensive; unclear if temporal proximity in embedding space = discovery-worthy link.

---

### 4.5 Graph-Based Approaches

#### a) **Node2Vec** (Heterogeneous & Homogeneous)

Learn node embeddings via biased random walks. Preserves network structure (homophily + structural equivalence).

**Application to LBD:** Concepts as nodes, co-occurrence as weighted edges. Link prediction on learned embeddings.

**Advantage:** Captures both direct and indirect similarities; encodes network topology.

**Limitation:** Sensitive to hyperparameters (walk length, return probability p, in-out probability q); requires full graph in memory. Poor performance on highly sparse, heterogeneous networks.

#### b) **Knowledge Graph Completion** (embedding + ranking models)

Systems like TransE, DistMult, RotatE: embed entities and relations in low-dim space; predict missing edges via distance or scoring.

**Application:** Knowledge graphs of biomedical entities (drugs, genes, diseases, mechanisms). Predict missing drug-disease or gene-disease edges.

**Advantage:** Can leverage typed relations (e.g., "protein interacts with" vs. "protein binds to") and transitive reasoning.

**Limitation:** Requires structured KG input; not applicable at field level without pre-existing field taxonomy.

---

### 4.6 Implementation Complexity Across Granularities

| Technique | Term-Level | Field-Level | Key Limitation |
|-----------|-----------|------------|-----------------|
| TF/IDF | ✅ Direct | ⚠️ (field = single unit) | Ignores co-location structure |
| Semantic Types | ✅ (UMLS) | ❌ (no field ontology) | Biomedicine only |
| PMI | ✅ High precision | ⚠️ Rare-pair bias | Doesn't scale to sparse spaces |
| Jaccard | ✅ Direct | ✅ Direct | Biased toward small sets |
| Cosine | ✅ Direct | ✅ Direct | Representation-dependent |
| Adamic-Adar | ✅ (graphs) | ✅ (if KG exists) | Requires full graph |
| Association Strength | ✅ (via marginals) | ✅ (via field-level marginals) | **Recommended for field-level** |
| Chi-Square | ✅ (significance) | ✅ (significance) | Only binary (sig/not-sig) |
| Word2Vec | ✅ Standard | ⚠️ (aggregate embeddings?) | Granularity mismatch |
| SciBERT | ✅ Best-in-class | ⚠️ (no precedent) | Untested at field level |
| Node2Vec | ✅ (graphs) | ⚠️ (sparse KG needed) | Hyperparameter-sensitive |

---

## 5. The Size-Confound & Normalization in Bibliometrics

### The Problem

Raw co-occurrence counts scale with field size. If field A has 10,000 papers and field B has 100,000 papers, they co-occur ~1,000× more often than two tiny fields (1,000 + 100 papers) co-occurring, *even if proportionally rare*.

**Why it matters for gap detection:** A giant field like "Machine Learning" co-occurs with everything; a small field like "Zebra Fish Aging" co-occurs with fewer. Naive co-occurrence ranks large fields as having more "gaps." But this is artifact, not signal.

### Standard Normalizations

#### 1. **Association Strength (Probabilistic Affinity)** — Van Eck & Waltman (2009)

See formula in §4.3(e). Null model: expected co-occurrence = (c_A × c_C) / N.

**Why it works:** Subtracts expected from observed. Two tiny fields co-occurring once = massive signal (observed >> expected). Two huge fields co-occurring 1,000 times = no signal (observed ≈ expected).

**Standard in bibliometrics:** YES. VOSviewer (the reference tool for bibliometric visualization) defaults to association strength. Validated across 1,000+ citation/co-author networks.

---

#### 2. **Normalized PMI (NPMI)**

$NPMI(A, C) = \frac{PMI(A, C)}{-\log P(A, C)}$

Ranges [−1, 1]. Corrects for PMI's bias toward rare pairs.

**Advantage:** Standardized scale.

**Disadvantage:** Still biased for sparse data; less theoretically grounded than association strength.

---

#### 3. **Jaccard Similarity**

Already range-normalized [0, 1]. But biased toward small sets (intersection of two small sets is "large" relative to union).

**Mitigation:** Use with frequency thresholds (discard very rare pairs).

---

#### 4. **Chi-Square Test**

$\chi^2 = \frac{(co(A, C) - E)^2}{E}$ where $E = \frac{c_A \cdot c_C}{N}$.

Tests whether observed co-occurrence significantly exceeds expected. **Binary filter** (sig/not-sig), not a ranking score.

**Common threshold:** p < 0.05, corrected for multiple comparisons (Bonferroni).

**Caveat:** With N ~ 10^9 pairs (typical LBD scale), even tiny deviations are "significant." Chi-square is useful for *filtering*, not *ranking*.

---

#### 5. **Configuration Model Null**

Degree-preserving random rewiring: shuffle edges while preserving degree sequence. Compute observed - expected under rewired null.

**Advantage:** Doesn't assume independence; accounts for network topology.

**Disadvantage:** Computationally expensive (requires Monte Carlo sampling).

**Common in ecology/network science:** YES. Not yet standard in bibliometrics (association strength is simpler and equally effective).

---

#### 6. **Resource Allocation Index (RA)**

$RA(A, C) = \sum_{B \in Neighbors(A) \cap Neighbors(C)} \frac{1}{k_B}$

Weights common neighbors inversely by their degree. Rare common neighbors count more.

**Advantage:** Intuitive (hubs aren't predictive); proven effective in network link prediction.

**Disadvantage:** Requires full network; not a normalized score (unbounded).

---

### Recommendation for Lacuna (Field-Level)

**Use Association Strength (van Eck & Waltman):**

$$AS(A, C) = \frac{co(A, C) - E}{\sqrt{co(A, C)}} \cdot normalize$$

where $E = \frac{c_A \cdot c_C}{N}$, and $c_A, c_C, N$ are field-level counts (# of papers in field A, field C, total).

**Why:**
- Proven in 15+ years of bibliometric research
- Theoretically grounded (null model of independence)
- Scales correctly for size confound
- Implementable at field level (marginals easily computed)
- Direct analogy to term-level use (replace term counts with field counts)

---

## 6. Evaluation Protocols: Time-Slicing, Benchmarks, Validation Suites

### 6.1 Time-Sliced Evaluation (Standard in LBD)

**Protocol:**
1. Choose cutoff year T (e.g., 1985 for fish oil/Raynaud's)
2. Train ABC on papers published pre-T
3. Extract candidate pairs (A, C) that don't co-occur pre-T
4. Test: did (A, C) co-occur post-T? (Yes = "discovery," No = false positive)
5. Compute precision: # hits / # candidates

**Advantage:** Avoids cherry-picking; uses large, automatically generated gold standard.

**Critical limitation:** Most post-T co-occurrences are *noise*, not "discoveries." Example: "Ebolavirus" and "Professional Burnout" both entered use post-2000 and co-occur in news; system ranks them as linked; meaningless.

**Moreau (2023) critique:** Time-sliced evaluation conflates "co-occurrence prediction" (what it measures) with "scientifically meaningful discovery" (what users want).

---

### 6.2 Gold-Standard Evaluation (Current Bottleneck)

**Reference standard:** Swanson's discoveries (fish oil/Raynaud's, magnesium/migraine) + handful of others (e.g., Viterbi algorithm for gene sequencing, undiscovered uses of existing drugs).

**Problem:** Only ~10–20 confirmed discoveries in literature. Insufficient for statistical validation of new methods.

**Attempts to construct benchmarks:**
- Manual literature review (expensive; n ~ 200–500)
- Expert panel scoring (noisy; limited consensus)
- Clinical trial outcomes (gold standard but rare; no dataset covers >50 pairs)

---

### 6.3 Recommended Validation Suite for Lacuna (Field-Level)

#### Test Case 1: Swanson Replication (1985 Cutoff)

**Setup:**
- Pre-1985 co-occurrence data: # papers in each of ~250 subfields, # of papers bridging pairs of subfields
- Post-1985 test: did fish oil + Raynaud's literature converge in same papers?

**Expected result:** Top-ranked pair (or high in top 50) should be fish oil ↔ Raynaud's.

**Interpretation:** Validates method on historical, confirmed discovery. But **caveat:** By 1990, the link was known; method only "discovers" established knowledge retroactively.

---

#### Test Case 2: Time-Sliced Validation (1990–2000 → 2000–2010)

**Setup:**
- Train on papers 1990–2000
- Identify pairs not co-occurring pre-2000
- Test on 2000–2010 co-occurrence

**Metric:** Precision@K (fraction of top-K candidates that co-occur post-2000).

**Expected result:** Likely ~20–40% precision for top 100 (depends on thresholds). Mark as "plausible but noisy."

---

#### Test Case 3: Expert Panel Review

**Setup:**
- Random sample of top-ranked field pairs (e.g., top 100 or 1000 candidates)
- Send to 5 domain experts (biomedics, computer scientists, etc.) with brief context
- Rate: "Obvious link," "Plausible," "Surprising but defensible," "Nonsense"

**Expected result:** Expect ~50–70% "plausible or better"; document disagreement.

**Cost:** ~5–10 expert-hours per test iteration.

---

#### Test Case 4: Publication-Level Drill-Down

**Setup:**
- For top-ranked field pairs, retrieve 10–20 random papers in each field
- Does manual inspection of abstracts reveal *any* conceptual link?

**Metric:** Fraction of field pairs where a human finds a plausible mechanism.

**Expected result:** ~40–60% (higher than co-occurrence precision because humans infer meaning).

---

#### Test Case 5: Longitudinal Emerging-Link Detection

**Setup:**
- Divide 2010–2024 into 3-year windows
- For each window, identify field pairs whose co-occurrence is increasing fastest (trending up)
- Manually verify: do trending pairs represent real emerging research or noise?

**Expected result:** Measures utility for *discovery of emerging connections* (not just novelty prediction).

---

### 6.4 Challenges Specific to Field-Level Evaluation

| Challenge | Cause | Mitigation |
|-----------|-------|-----------|
| No field-level gold standard | No literature on field-level discoveries | Use Swanson + expert review |
| Coarse granularity | Subfields contain diverse microtopics | Drill down to papers; accept ambiguity |
| Aggregation noise | Field co-occurrence = any topic within field co-occurs | Stratify by subfield overlap; report confidence intervals |
| Temporal lag | Discoveries take years to publish | Use 5–10 year post-cutoff window |
| Causal vs. correlational | Co-occurrence ≠ link (e.g., "cancer + AI" ≠ joint discovery) | Expert judgment on plausibility |

---

## 7. Known Critiques of LBD as a Field

### 7.1 Evaluation Methodology Failures

**Critique (Moreau et al., 2023):**  
LBD field is stuck in methodological rut. Standard practice: evaluate on handful of Swanson discoveries + time-sliced evaluation on noisy co-occurrences. Results don't reflect scientific validity, only statistical prediction accuracy.

**Impact:** A system that predicts "Ebolavirus + Professional Burnout" co-occurrence post-2000 = "successful prediction" by time-slice metric; meanwhile, genuinely novel drug-disease links are ranked lower. Metric is orthogonal to utility.

---

### 7.2 Reproducibility & Cherry-Picking

**Problem:** Early LBD papers (1990s–2000s) report hand-picked discoveries; no pre-registered hypotheses, no systematic evaluation.

**Example:** System discovers 100 candidate links; researcher manually reviews top 20; finds 3 plausible; publishes "3 validated discoveries" (ignoring 97 false positives).

**Consequence:** Reported success rates (60–80%) are inflated; true precision likely 10–30%.

---

### 7.3 Retroactive Narrative Bias

**Critique:** Many "discoveries" are links between known mechanisms, not novel biology. Swanson's fish oil/Raynaud's is textbook example: blood viscosity's role in Raynaud's was known; fish oil's effect on viscosity was known; the *connection* was "unknown" but retrospectively obvious.

**Question:** Is LBD rediscovering known science from separate silos, or generating truly novel hypotheses? Hard to distinguish.

---

### 7.4 Limited Scope (Biomedicine Bias)

**Problem:** 99% of LBD research is biomedical. Why? Because UMLS, MeSH, PubMed, MEDLINE are mature. Other domains lack standardized concept vocabularies.

**Implication:** LBD is a biomedical-text-mining trick, not a general discovery method. Extending to physics, sociology, CS is unclear.

---

### 7.5 Lack of Interpretability

**Critique (recent deep-learning LBD papers):** Neural systems (BERT, node2vec) rank candidates well but can't explain *why*. User sees "Field A + Field B = 0.87 score" but no mechanistic explanation. In science, explainability is essential; black-box ranking is insufficient.

---

### 7.6 High False Positive Rate in Real Deployment

**Published data:**
- Guided assembly of cellular networks: 56% false positives (Guided et al., 2021)
- Drug repurposing LBD systems: ~40–50% of top-10 candidates unvalidated (various studies)
- User studies: Experts accept ~50–70% of top candidates as "worth exploring"; reject rest as implausible

**Reality:** LBD is a *hypothesis-generation* tool, not a *discovery* tool. It narrows search space from millions to hundreds; still requires human vetting.

---

### 7.7 The "Rediscovery = Success" Fallacy

**Critique:** Systems are often evaluated by checking whether a *known* link is recovered (e.g., "did you find fish oil/Raynaud's?"). If yes = "method works." But known links are easy to find; *unknown* links are the goal.

**Problem:** No way to evaluate unknown links (by definition, we don't know the ground truth). So all evaluation devolves to retrospective prediction or cherry-picking.

---

## 8. Field-Level vs. Term-Level LBD: A Critical Gap

### The Question

**Has anyone done LBD at the research-field/subfield/discipline level?**

**Answer: NOT in published literature.**

All LBD work operates at:
- **Term level:** genes, proteins, drugs, diseases, phenotypes (with concept universes: ~10k–100k UMLS concepts)
- **Paper level:** linking papers as documents

**No published work found on:**
- Field-level ABC (A = subfield in OpenAlex, C = another subfield, B = linking subfield)
- Domain-level co-occurrence normalization
- Field-level embeddings or link prediction

### Why This Matters for Lacuna

Your design (250 subfields from OpenAlex, field-level co-occurrence networks) is **novel and unsupported by prior literature**. This is both opportunity and risk.

**Opportunity:** No prior work means you're not re-implementing; you're extending LBD to coarser granularity.

**Risk:** 
1. Field-level aggregation may wash out signal (Raynaud's + fish oil = rare pair; if aggregated to "immunology + nutrition," becomes common)
2. Field-level noise may be higher (if Biology subfields are coarse, they have ~100k papers each; noisy marginals)
3. No prior evaluation protocol exists for field-level discovery
4. LBD at coarser granularity may be less effective (fewer discriminative B-terms)

### Recommendation

Treat lacuna as an **exploratory extension of LBD**, not a validated method. Design evaluation suite assuming higher false-positive rates. Emphasize discovery-as-exploration (narrow search space) rather than discovery-as-confirmation (find known links).

---

## 9. Recommended Metric Shortlist for Subfield-Level Gap Scoring

### Candidate 1: Association Strength (Top Recommendation)

$$AS(A, C) = \frac{co(A, C) - \frac{c_A \cdot c_C}{N}}{\sqrt{co(A, C)}} \cdot \frac{N}{c_A \cdot c_C}$$

**Formula** (simplified):  
Observed co-occurrence, minus expected (under independence), divided by sqrt(observed), normalized by field sizes.

**Pseudocode:**
```
def association_strength(co_ac, count_a, count_c, total_papers):
    expected = (count_a * count_c) / total_papers
    numerator = co_ac - expected
    denominator = sqrt(co_ac) if co_ac > 0 else 1
    as_score = numerator / denominator
    return as_score
```

**Advantages:**
- Theoretically grounded null model (independence)
- Corrects for field size confound
- Proven in 15+ years of bibliometric research
- Implementable at field level

**Disadvantages:**
- Undefined for co_ac = 0; requires pseudo-count (co_ac + 0.5)
- Can produce extreme scores for rare pairs; requires capping

**Confidence level:** 95% (standard in bibliometrics)

---

### Candidate 2: Jaccard Similarity (Simpler Alternative)

$$Jaccard(A, C) = \frac{co(A, C)}{c_A + c_C - co(A, C)}$$

**Advantages:**
- Simple, interpretable [0, 1] range
- No hyperparameters
- Symmetric

**Disadvantages:**
- Biased toward small fields
- Doesn't directly model field-size confound
- Less theoretically motivated than association strength

**Recommendation:** Use as a *secondary metric* for ablation studies; pair with frequency thresholds (e.g., only rank pairs where both fields have >100 papers).

**Confidence level:** 70% (need empirical validation at field level)

---

### Candidate 3: Normalized PMI with Frequency Filtering

$$NPMI(A, C) = \frac{PMI(A, C)}{-\log P(A, C)}$$ where $PMI(A, C) = \log \frac{co(A, C)}{c_A \cdot c_C / N}$

**Advantages:**
- Captures deviation from independence
- Standardized [-1, 1] scale
- Proven in word embedding literature

**Disadvantages:**
- Biased for rare pairs (unless co_ac is large)
- Requires careful handling of edge cases (log(0))
- Least theoretically grounded for bibliometrics

**Recommendation:** Use only if you have strong co-occurrence signals (>50 co-papers per pair). Test empirically before deployment.

**Confidence level:** 60% (less established in field-level contexts)

---

### Candidate 4: Cosine Similarity on Field-Level Embeddings

If field A has embedding $\vec{e}_A$ and field C has embedding $\vec{e}_C$ (derived from aggregating papers or learned via network methods):

$$Cosine(A, C) = \frac{\vec{e}_A \cdot \vec{e}_C}{|\vec{e}_A| \cdot |\vec{e}_C|}$$

**Advantages:**
- Modern; aligns with deep learning LBD methods
- Can capture indirect, non-co-occurrence similarities
- Flexible (embedding method choice)

**Disadvantages:**
- Requires training embeddings (costly)
- No clear baseline for field-level embeddings
- No published precedent for field-level; untested

**Recommendation:** Prototype as future work. Not ready for v1.

**Confidence level:** 30% (exploratory)

---

### Final Ranking for v1 Implementation

1. **Use Association Strength (primary)** — implement with frequency filtering (both fields ≥ 50 papers) and pseudo-counts for zero co-occurrence
2. **Use Jaccard (secondary)** — for validation and ablation analysis
3. **Avoid Candidate 3 & 4 for v1** — exploratory only; not validated at field level

---

## 10. Recommended Validation Suite (Concrete Test Cases)

### Phase 1: Historical Replication (Pre-Deployment)

#### Test A: Swanson Fish Oil / Raynaud's (1985 Cutoff)

**Data preparation:**
- Corpus: All PubMed papers pre-1985
- Subfields: Map papers to OpenAlex subfields
- Compute field-level co-occurrence matrix

**Method:**
1. Apply association strength metric
2. Rank all field pairs
3. Check: is (fish oil related field) ↔ (Raynaud's related field) in top 50?

**Pass criteria:** Pair appears in top 50 (not top 10, due to field-level coarseness)

**Fail:** Pair outside top 100 → investigate whether field mappings are too coarse

---

#### Test B: Magnesium / Migraine (1988 Cutoff)

Same as Test A; expect magnesium-related + migraine-related fields to rank together.

**Pass criteria:** Both tests A & B pass

---

### Phase 2: Time-Sliced Validation

#### Test C: 1990–2000 Training, 2000–2010 Test

**Setup:**
1. Train on papers 1990–2000
2. Extract field pairs with co_ac = 0 in training
3. Test: how many reappear in 2000–2010?

**Metric:** Precision@K (K = 100, 500, 1000)

**Expected result:**
- Precision@100 ≈ 20–35% (top candidates have ~1 in 3 chance of real link post-2000)
- Precision@500 ≈ 10–20%
- Precision@1000 ≈ 5–15%

**Interpretation:** Higher than 50% = excellent (implies strong signal); 10–30% = acceptable for exploratory tool; <10% = no signal

**Pass criteria:** Precision@100 > 15% (better than random)

---

#### Test D: Publication-Level Drill-Down on Time-Sliced Candidates

**For top-50 candidate pairs from Test C:**
1. Retrieve 10 random papers from each field that contribute to co-occurrence
2. Manual review (researcher): do abstracts reveal plausible mechanism or link?

**Metric:** Fraction where human finds plausible connection

**Expected result:** ~40–60% (much higher than pure co-occurrence, because humans can infer meaning)

**Interpretation:** Validates that co-occurrence captures semantic signal, not just noise

---

### Phase 3: Expert Validation

#### Test E: Expert Panel Scoring

**Setup:**
1. Sample top 100 candidate field pairs (by association strength)
2. Provide domain experts with pair names + 3 context snippets (papers bridging fields) + field descriptions
3. Rate: 1 (obvious/known), 2 (plausible), 3 (surprising but interesting), 4 (nonsense)

**Experts:** 5 people with PhD in diverse fields (not just CS; include biologists, physicists, etc.)

**Metric:** % scoring ≥2 (plausible or better); compute inter-rater reliability (Fleiss' kappa)

**Expected result:**
- ~50–70% rated ≥2
- Kappa ≥ 0.4 (fair agreement; likely for high-confidence discoveries)

**Pass criteria:** >50% rated plausible; Kappa ≥ 0.35

---

#### Test F: Novel Hypothesis Generation (Qualitative)

**Setup:**
1. Experts review top-20 candidate pairs
2. For each, write 1–2 sentences: "If this link is real, what would we investigate?"

**Metric:** Qualitative—do proposed studies seem scientifically sound?

**Interpretation:** Measures utility for discovery framing, not just accuracy

---

### Phase 4: Deployment Monitoring

#### Test G: Emerging Links Detection (Longitudinal)

**Setup:**
1. Divide 2015–2024 into 3-year windows
2. Identify field pairs with fastest co-occurrence growth (d(co-occurrence)/d(year))
3. Manual check: do trending pairs represent real emerging research or artifact?

**Metric:** Fraction of trending pairs manually confirmed as plausible

**Expected result:** ~50–70% (trending is a strong signal)

---

## 11. Red Flags: Ways Lacuna Could Produce Plausible-Sounding Nonsense

### Flag 1: Field Size Confound Not Controlled

**Risk:** If association strength not implemented correctly (e.g., using raw co-occurrence), huge fields rank as having most "gaps" simply by having more papers.

**Symptom:** All top candidates include "Cancer," "Machine Learning," "Neuroscience" (largest fields).

**Mitigation:** Verify association strength implementation; ablate with Jaccard; compare against random field pairs sampled by size (control for confound).

---

### Flag 2: Coarse Granularity Washes Out Signal

**Risk:** If OpenAlex subfields are too broad (e.g., "Biology" contains 200 diverse micro-topics), field-level co-occurrence is noise (averaging over many uncorrelated paper pairs).

**Symptom:** No Test A / Test B replication (fish oil/Raynaud's, magnesium/migraine don't rank high).

**Mitigation:** Drill down to paper-level; inspect fields mechanically (do papers actually relate?); consider finer granularity if available.

---

### Flag 3: Temporal Lag Masking Novelty

**Risk:** Emerging links take years to publish; time-sliced evaluation using 2000–2010 → 2010–2020 only captures links that were *already* published by 2010. True novel discoveries (2015 onward) are invisible.

**Symptom:** All top candidates are retrospective links (already known by 2020).

**Mitigation:** Use longitudinal detection (Test G); focus on trending pairs, not static ranking.

---

### Flag 4: Causal Confusion with Correlation

**Risk:** Two fields co-occur because they're adjacent (spatially, conceptually), not because there's a real mechanistic link. Example: "Cancer + Chemotherapy" always co-occur; system ranks as gap-worthy, but it's just a known treatment relationship.

**Symptom:** Expert panel rates most candidates as "obvious" (rating 1), not surprising.

**Mitigation:** Add inter-field diversity check: downrank candidates where fields are closely related in citation structure (use field co-citation network to define "distant").

---

### Flag 5: Cherry-Picked Discoveries

**Risk:** Publishing system discovers 1000 candidate pairs; user highlights 10 plausible ones; paper claims "system discovered Y"; ignores 990 false positives.

**Symptom:** Paper reports "3 validated discoveries" without reporting total candidates or precision.

**Mitigation:** Always report precision@K (top-100, top-500); time-sliced validation metrics; expert disagreement rates; never publish without validation suite results.

---

### Flag 6: Aggregation Across Heterogeneous Subtopics

**Risk:** OpenAlex "Neuroscience" subfield contains cognitive neuroscience, computational neuroscience, clinical neurology, developmental neuroscience, etc. Co-occurrence within "Neuroscience" is meaningless; across-field co-occurrence is diluted.

**Symptom:** Field pair "Neuroscience + Machine Learning" ranks high, but inspection reveals papers are scattered across irrelevant sub-areas (e.g., cognitive neuroscience papers never mention ML; ML papers never mention brains).

**Mitigation:** Compute field co-occurrence at subfield level; validate field definitions empirically (cluster papers; verify cohesion).

---

### Flag 7: Data Quality & Temporal Coverage Bias

**Risk:** OpenAlex coverage varies by field and year. Computer science well-covered post-2000; historical biology sparse; physics pre-1990 absent. Apparent "gaps" are actually coverage gaps.

**Symptom:** Historical fields (physics, philosophy) rarely co-occur with modern fields (ML, biotech) even if conceptually related.

**Mitigation:** Document coverage by field and year; restrict analysis to well-covered periods; adjust for coverage differences.

---

## 12. Unresolved Questions

1. **Field-level embedding evaluation:** Has anyone successfully generated field-level (not term-level) embeddings for LBD? If yes, how?

2. **Minimum field size for reliable co-occurrence:** What's the minimum # of papers per field for association strength to be stable? (Term-level: ~50; field-level: likely ~500–1000, untested.)

3. **Optimal subfield granularity:** OpenAlex uses ~250 subfields. Is this coarser or finer than optimal for gap detection? No literature.

4. **Temporal lag in discovery publication:** After a novel link is published, how many years until it accumulates enough co-occurrences to be detectable by LBD? (Likely 3–5 years; untested at field level.)

5. **Bisociative vs. ABC discovery:** Some LBD literature distinguishes "bisociative" (maximally distant fields) from ABC (standard). Is bisociativity a separate filtering step, or an emergent property of association strength scoring?

6. **Expert evaluation efficiency:** What's the minimum expert-review effort (# of experts, # of pairs) needed for statistically valid precision estimation at field level?

7. **Real vs. spurious field emergence:** Can you distinguish a truly emerging research direction from a statistical artifact (e.g., co-authorship network growth, proliferation of review papers)?

---

## Summary: Recommended Implementation Path

### v1 Core (Minimum Viable):

1. **Metric:** Association Strength (per §9)
2. **Validation:** Tests A, B, C from §10 (historical replication + time-sliced)
3. **Output:** Ranked list of subfield pairs + precision@K metrics
4. **Caveats:** Acknowledge field-level LBD is exploratory; false positive rate likely 60–80%; treat as exploration tool, not discovery tool

### v2 (Future Enhancements):

1. Add Jaccard as secondary ranking
2. Implement Test D, E (expert panel) for subset of candidates
3. Add longitudinal trending detection (Test G)
4. Explore field-level embeddings (Candidate 4 from §9)

### Deployment Best Practices:

- Always report precision metrics and aggregate statistics, not cherry-picked "discoveries"
- Provide drill-down to papers; let users inspect bridging evidence
- Highlight confidence (e.g., "high confidence: co-occurrence > 50; AS > 2") vs. speculative links
- Monitor coverage and temporal bias per field
- Iterate validation suite annually

---

**Status:** DONE

**Summary:** Systematic literature review of LBD field, Swanson's canonical results (fish oil/Raynaud's 1986, magnesium/migraine 1988), filtering techniques (frequency, semantic types, PMI, association measures, embeddings, graph methods), normalization for field-size confound (association strength as standard), evaluation protocols (time-slicing, benchmarks), known critiques (evaluation methodology failures, reproducibility, ~40–70% false positive rates, interpretability gaps). Field-level LBD is unexplored territory; no published precedent. Association strength recommended as primary metric for lacuna (subfield-level gap detection). Validation suite provided with 7 concrete tests. 12 unresolved questions documented.

---

## References

1. Swanson, D. R. (1986). "Fish oil, Raynaud's syndrome, and undiscovered public knowledge." *Perspectives in Biology and Medicine*, 30(1), 7–18. [Canonical work]

2. Swanson, D. R. (1988). "Migraine and magnesium: Eleven neglected connections." *Perspectives in Biology and Medicine*, 31(4), 526–557.

3. Weeber, M., Klein, H., & de Jong-van den Berg, L. T. (2001). "Using Concepts in Literature-Based Discovery: Simulating Swanson's Raynaud–Fish Oil and Migraine–Magnesium Discoveries." *J. American Society for Information Science & Technology*, 52(7), 548–557. https://onlinelibrary.wiley.com/doi/abs/10.1002/asi.1104

4. Van Eck, N. J., & Waltman, L. (2009). "How to Normalize Co-Occurrence Data? An Analysis of Some Well-Known Similarity Measures." *Journal of the American Society for Information Science and Technology*, 60(8), 1635–1651. https://onlinelibrary.wiley.com/doi/10.1002/asi.21075

5. Thilakaratne, M., Falkner, K., & Atapattu, T. (2019). "A Systematic Review on Literature-Based Discovery Workflow." *PeerJ Computer Science*, 5, e235. https://peerj.com/articles/cs-235/

6. Moreau, Y., et al. (2023). "Literature-Based Discovery: Addressing the Issue of the Subpar Evaluation Methodology." *Bioinformatics*, 39(2), btad090. https://academic.oup.com/bioinformatics/article/39/2/btad090/7036333

7. "Recent Advances and Future Directions in Literature-Based Discovery." *arXiv*, 2506.12385v1. https://arxiv.org/html/2506.12385v1

8. "Literature Based Discovery (LBD): Towards Hypothesis Generation and Knowledge Discovery in Biomedical Text Mining." *arXiv*, 2310.03766. https://arxiv.org/pdf/2310.03766

9. "Make Literature-Based Discovery Great Again through Reproducible Pipelines." *arXiv*, 2502.16450. https://arxiv.org/pdf/2502.16450

10. Adamic, L. A., & Adar, E. (2003). "Friends and Neighbors on the Web." *Social Networks*, 25(3), 211–230.

11. Conference paper on Configuration Models: https://www.cs.cornell.edu/courses/cs6241/2019sp/readings/Fosdick-2018-configuration.pdf

12. SciBERT: https://www.researchgate.net/publication/332011375_SciBERT_Pretrained_Contextualized_Embeddings_for_Scientific_Text

13. PubMed central articles on LBD evaluation and semantic predications.

14. "Neural Networks for Open and Closed Literature-Based Discovery." *PLoS ONE*. https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0232891

15. "Literature-Based Discovery beyond the ABC Paradigm: A Contrastive Approach." *bioRxiv*. https://www.biorxiv.org/content/10.1101/2021.09.22.461375.full.pdf
