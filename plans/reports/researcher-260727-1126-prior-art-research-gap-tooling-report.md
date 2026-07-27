# Prior-Art Survey: Research Gap Tooling & Knowledge Mapping Landscape
**Date:** 2026-07-27 | **Researcher:** Claude  
**Task:** Assess whether lacuna fills a genuine gap or rebuilds existing tooling.

---

## 1. Open Research Knowledge Graph (ORKG)

**What it does:** Encodes papers as RDF triples (problem, method, result, dataset, artifact) with provenance. Enables structured comparison, retrieval, and FAIR publication of research content.

**Data model:** Problem + method + result triples; curated comparisons; templates for domain-specific schemas (10K+ papers, 5K research problems, 1.2K research fields indexed).

**Gap modeling:** Acknowledges research problems as entities but does not systematically model gaps, white-space, or structural holes between literatures. No computed layer of unexplored combinations.

**API:** REST API available; data access documented but not detailed in current web presence.

**License:** See `/page/license` (not verified in this research).

**Liveness:** **ACTIVE.** Maintained by Yaser Jaradeh; releases v1.3.0 (Feb 2026), v1.2.0 (Jan 2026), v1.1.0 (Nov 2025); 5th anniversary symposium May 2026. Actively receiving contributions.

**Verdict:** **OVERLAPS (partial).** ORKG structures research outcomes but does not surface white-space. Lacuna could complement ORKG by feeding computed gaps back as first-class problem entities.

---

## 2. SciSciNet

**What it contains:** 250M+ academic works + funding, patents, citations, institutions, embeddings (1.7TB). Integrated metadata lake for science-of-science research. Latest snapshot from OpenAlex (v2, 2025).

**Size:** 117 GB parquet files; papers + embeddings on GCS / HuggingFace / BigQuery.

**License:** MIT (fully open).

**Update cadence:** Rebuilt with latest OpenAlex snapshots; no published schedule but implies semi-regular refreshes.

**Maintained:** **YES.** Recent v2 release; active GitHub repository (Northwestern-CSSI/SciSciNet).

**Verdict:** **COMPLEMENTS.** SciSciNet is data infrastructure (corpus + metadata). Lacuna is gap discovery logic. Could use SciSciNet as input or adopt its schema for reproducibility.

---

## 3. Semantic Scholar / S2AG API

**Coverage:** 200M+ papers, AI2-backed. Strong in CS, ML, medicine, biology; weaker in humanities, social sciences.

**vs. OpenAlex:** OpenAlex covers 250M+ works; both free but different strengths. Together they cover ~99% of indexed research.

**Rate limits & cost:** Free API with rate limits; Semantic Scholar free search. No API key required for basic access (as of 2026-02). No premium tier pricing found.

**Verdict:** **IRRELEVANT (for core gap discovery).** Both S2 and OpenAlex are data sources, not gap-discovery systems. Lacuna should select OpenAlex (more complete, truly open, lower lock-in) or ingest both.

---

## 4. Citation-Based Visualization Tools

### Connected Papers
- **Visualizes:** Paper similarity via citation co-occurrence + recency weighting.
- **Gap-oriented?** No. Finds related papers, not unexplored spaces.
- **Model:** SaaS (commercial). Free tier limited.
- **Status:** Active 2026.

### Research Rabbit
- **Visualizes:** Citation networks + reading list export.
- **Gap-oriented?** No. Discovery-focused, not gap-focused.
- **Model:** SaaS. 2025+ removed author search & free sharing.
- **Status:** Active but declining feature set.

### Litmaps
- **Visualizes:** Time-axis evolution of field. Citation-based.
- **Gap-oriented?** No. Shows field trajectory, not white-space.
- **Model:** SaaS, freemium ($10/mo annual). 
- **Status:** Active 2026.

### Inciteful
- **Visualizes:** Citation network analysis, no signup.
- **Gap-oriented?** No. Citation traversal only.
- **Model:** Free (no limits), no signup.
- **Status:** Active 2026.

### Open Knowledge Maps
- **Visualizes:** Conceptual clusters from 100 most relevant papers per query.
- **Gap-oriented?** Partial. Can show underexplored regions within clusters but limited to top 100 results + metadata.
- **Model:** Non-profit, open-source (Head Start framework), completely free.
- **Limitation:** Metadata only, no full-text analysis; visual maps limited to top 100 docs.
- **Status:** Active; part of EOSC/NFDI infrastructure.
- **License:** Open-source.

**Verdict:** **OVERLAPS (but orthogonal intent).** These visualize similarity / citation flow, not gaps. Complementary to lacuna: could consume their corpus to inject gap discovery.

---

## 5. Explicit Research Gap Tooling

### Academic Prototypes (Literature-Based Discovery)

**Arrowsmith** — Two-node ABC co-occurrence search (biomedics only). Closed discovery (finds hidden A-C links via B). Still alive (hosted publicly).

**BITOLA** — Generalized LBD using co-occurrence networks. Still maintained, broader than Arrowsmith.

**LION LBD** — Cancer biology specific. Functional but domain-scoped.

**Serendipity, SKiM-GPT** — Recent (2025) work enhancing LBD with LLM-based hypothesis evaluation.

**Verdict on LBD:** Mature for biomedics; methodology is well-studied (Swanson ABC model dominates). Main limitation: (a) single-domain focus; (b) pairwise co-occurrence has poor biological context; (c) no large-scale benchmark dataset for validation; (d) not web-accessible for general use.

### AI-Powered Commercial Tools (Gap-Adjacent)

**Undermind** — Multi-hop reasoning + citation tracking. Claims to find niche / long-tail papers and surface gaps/contradictions across 1000s of papers. **First tool to explicitly market gap-finding.** Pricing not disclosed; seems freemium or subscription.

**Elicit, Consensus, SciSpace, Scite** — Evidence synthesis, not gap discovery. Summarize existing literature, flag contradictions. Gap-detection is a side effect, not a first-class feature.

**Dimensions Research GPT** — Not found in 2026 data; unclear if product still exists.

**Verdict on Commercial Tools:** Undermind is the closest competitor. Focuses on niche paper discovery + contradiction surfacing. Does NOT systematically map white-space or compute unexplored combinations at scale.

### Research Gap Benchmarks

**Recent 2025-2026 benchmarks** (AutoResearchBench, ResearchBench, DiscoveryBench, DR³-Eval) focus on *hypothesis generation* and *literature retrieval* for known research goals, not on *gap discovery*. **No large-scale benchmark exists for automated gap discovery**—suggesting this is an unsolved problem in eval.

**Verdict:** Gap tooling exists in pockets (biomedics LBD, recent AI agents). No unified, domain-agnostic, scaled system for computed gap discovery. Research-grade benchmarks don't exist yet.

---

## 6. Open-Problem Catalogues

### Clay Millennium Problems
- 7 unsolved math problems, $1M prize each.
- Curated, not machine-readable at scale.
- Only 1 solved (Poincaré, 2010).
- **License:** Public knowledge.

### Wikipedia "Unsolved Problems in X" Lists
- Human-curated, inconsistent structure.
- Not machine-readable; no API.
- **Coverage:** Biased toward math/physics; weak in social sciences, applied fields.

### Open Problem Garden
- Academic initiative to crowdsource open problems.
- **Status:** Checked searches; project appears dormant (~2015 era).
- **Machine-readable?** No structured API found.

### arXiv Open Problems
- Researchers tag papers with "open problems" metadata.
- **Machine-readable:** Partially (searchable via arXiv API).
- **Scope:** CS-heavy; incomplete for other domains.

### NAE Grand Challenges, Gates Foundation Challenges
- Curated problem lists; not unified.
- No single machine-readable source.

**Verdict:** Open problem catalogues exist but are *curated, siloed, not machine-readable at scale, and not integrated*. No unified, programmatic registry of "acknowledged unsolved problems" exists. Lacuna's `open` category is a consolidation opportunity, not a rebuild.

---

## 7. Science-of-Science / Blind Spot Measurement Literature

**Key Finding (2024-2025 research):** Papers creating topological gaps in concept networks rank among most highly cited works. Computational topology can identify knowledge gaps at scale across millions of articles (120-year study cited).

**Referenced Studies:**
- "Opening Knowledge Gaps Drives Scientific Progress" (2025 arXiv)
- "Topological Blind Spots" in deep learning literature
- Scientometric analysis of LBD (1986-2020) — 2020 arXiv

**Gap Measurement Approaches:**
1. **Co-occurrence null models** — Identify unexpected absences of concept pairs.
2. **Topological data analysis** — Homology/cycles reveal structural holes in knowledge.
3. **Configuration models** — Null-hypothesis networks to flag anomalies.
4. **Novel recombination scoring** — Interdisciplinary term-pair rarity metrics.

**Maturity:** Active research area (2025-2026); methodologies are peer-reviewed and reproducible but not yet operationalized in production systems.

**Verdict:** Theory exists; no production implementation at web scale. Lacuna's `gap` layer (computed via Swanson-style co-occurrence) is a known methodology, not novel, but **operationalizing it at OpenAlex scale is engineering work, not conceptual work.**

---

## 8. Non-Academic Knowledge Coverage

### Local Contexts / TK Labels
- Provides digital-signifier labels for traditional knowledge.
- **Purpose:** Encodes Indigenous community protocols (sacred material, gender restrictions, seasonal conditions).
- **Scope:** Museums, archives, digital repositories.
- **Machine-readable?** Labels are structured metadata; community-customizable.
- **Integration with academic KGs?** No integration found; operates in parallel.

### Traditional Knowledge Digital Library (TKDL, India)
- Patent-mitigation initiative.
- Medicinal knowledge registry; prevents misappropriation.
- **Scope:** Indian traditional medicine.
- **Open API?** No public API found.

### Mukurtu CMS
- Open-source platform for managing cultural heritage.
- Uses TK Labels; supports structured metadata.
- **Status:** Active, community-maintained.

**Verdict:** Infrastructure exists for encoding non-academic knowledge but is siloed from scholarly literature. Lacuna could model this gap: *documented knowledge in craft/indigenous/practitioner domains that hasn't entered academic discourse*. No prior system integrates both layers.

---

## Synthesis: Honest Verdict

### What EXISTS (Abundance)
1. **Citation-based visualization** (Connected Papers, Litmaps, etc.) — mature, commoditized.
2. **AI-powered literature synthesis** (Elicit, Scite, Consensus, Undermind) — emerging, well-funded, fast-growing.
3. **Literature-based discovery for biomedics** (Arrowsmith, BITOLA, SKiM-GPT) — mature methodology, narrow scope.
4. **Science-of-science datasets** (SciSciNet, OpenAlex, S2AG) — freely available, well-maintained.
5. **Research problem catalogues** (ORKG, Clay Millennium, etc.) — curated, incomplete, not unified.

### What's MISSING (The Real Gap)

1. **No production system for computed gap discovery at web scale.**
   - Swanson ABC co-occurrence logic exists in academic papers; not operationalized.
   - No benchmarks for gap-discovery evaluation.
   - Commercial gap-finding (Undermind) is incidental, not systematic.

2. **No unified, machine-readable registry of research gaps.**
   - `open` category (acknowledged unsolved problems) is fragmented across 50+ siloed sources.
   - No single source-of-truth for "what problems are known to be unsolved?"

3. **No structured mapping of under-explored combinations.**
   - Citation networks show what's connected; don't show what's conspicuously *absent*.
   - Topological null models exist (academic); not operational.

4. **No integration of non-academic knowledge gaps.**
   - Indigenous/craft/practitioner knowledge is tracked separately (TK Labels, TKDL).
   - No system bridges academic + non-academic blind spots.

5. **No static-artifact approach (permissionless, censorship-resistant).**
   - Existing systems require logins, APIs, or SaaS subscriptions.
   - No public "map of unknowns" that can be forked, cited, archived.

---

## Reusable Assets Lacuna Should Stand On

1. **OpenAlex API** — 250M+ works, CC0 license, free, no key required. Use as primary corpus.
2. **SciSciNet v2** — Embeddings + metadata lake (MIT). Can ingest as pre-computed features.
3. **ORKG problem registry** — Import curated problems; extend with lacuna-computed gaps.
4. **Semantic Scholar / S2AG** — Backup corpus for cross-validation; especially strong in CS/ML.
5. **arXiv metadata** — Free, structured, 2.3M papers. Subset easily processable.
6. **TK Labels schema** — Adopt for non-academic knowledge layer; partner with Local Contexts.

---

## Differentiation: What Lacuna Would Be First/Best At

1. **Systematic, automated gap discovery at web scale.** No competitor computes `gap` layer using co-occurrence null models across all domains.

2. **Unified, public, citable gap catalogue.** First to offer "map of research unknowns" as machine-readable, versionable, forkable artifact (not SaaS).

3. **Three-layer model (open + gap + blocked).** No existing system distinguishes:
   - Acknowledged unsolved (curated).
   - Computed unexplored (computed).
   - Known-impossible (curated, e.g., instrumentation limits).

4. **Free, permissionless access.** No login, no API key, no rate limits. Cacheable, archivable static data.

5. **Integration of non-academic knowledge.** First to map gaps in academic + craft/indigenous domains together.

---

## Honest Assessment

**Is there a real gap in the tooling landscape?**

**Yes, but with caveats:**
- The gap is real: no production system maps computed research gaps at scale.
- But the gap is *engineering work*, not conceptual work. Swanson method is 40 years old; topological null models are peer-reviewed; methodology is known.
- Competitors (especially Undermind) approach the space asymptotically but don't own it.
- This is a **timing + execution gap**, not a **knowledge gap**.

**Risk:** If lacuna launches, Undermind (or an OpenAI research agent) could backfill this niche within 12–18 months by adding systematic gap modeling to existing infrastructure.

**Upside:** Lacuna's static-artifact + non-academic-knowledge differentiator is defensible. If lacuna becomes the *Wikidata-for-unknowns*, network effects make it hard to displace.

---

## Unresolved Questions

1. **Does OpenAlex include preprints equally to peer-reviewed work?** (Affects `gap` layer bias.)
2. **What is Undermind's technical approach to gap-finding?** (Patent filings, publications not found in public data.)
3. **Is ORKG's `/page/license` open enough for derivative work?** (Need to verify before importing problem entities.)
4. **Can TK Labels be integrated with academic metadata without colonizing indigenous knowledge?** (Ethical framing matters.)
5. **What's the expected tail of co-occurrence gaps when using only term-pair frequency vs. embedding-based models?** (Methodological choice impacts false-positive rate.)

---

**Status:** DONE | **Summary:** Real gap exists in operationalized, large-scale gap discovery at the intersection of computed + curated + non-academic knowledge. Methodology is known; execution is the differentiator. No direct clone of lacuna exists, but Undermind + OpenAlex + future AI agents pose asymptotic competition risk.
