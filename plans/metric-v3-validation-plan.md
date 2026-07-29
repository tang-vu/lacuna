# Metric v3 validation plan

**Status:** proposal only — no v3 metric has been implemented or tuned.

## Why a redesign is required

The failed v1 and v2 experiments established that a global OpenAlex topic-pair ranking is dominated
by adjacent specialties that the classifier treats as alternatives. Completing the same sweep or
adding an LLM cannot repair that construct-validity failure.

Metric v3 must test a narrower claim: whether term-level, time-appropriate biomedical indexing can
recover literature-based discoveries across multiple historical cases without ranking ontology
siblings and unrelated pairs as gaps.

## Data path

- Use the free MEDLINE/PubMed baseline files and the MeSH descriptor assigned in each publication
  year for candidate generation and retrospective validation.
- Use OpenAlex only as a complementary source for stable work links, citation context, and the
  project taxonomy. Do not project OpenAlex's modern topics backward and call them historical
  indexing.
- Pin the exact MEDLINE release, MeSH vocabulary year, query, date slice, and checksum for every
  benchmark artifact.
- Start with a biomedical pilot. Do not claim that its validity transfers to other domains.

## Benchmark before metric

Create a benchmark of at least:

- eight positive cases where a bridge was published after a documented cutoff, including but not
  limited to fish oil and Raynaud's syndrome;
- eight hard negatives drawn from nearby specialties and ontology siblings;
- eight distant negatives;
- two discovery cutoffs that were not used while choosing formula parameters.

Map every case to period-appropriate MeSH descriptors before computing a score. Record ambiguous
mappings rather than choosing the mapping that ranks best.

Split cases into development and held-out sets. The fish-oil/Raynaud case may remain a development
diagnostic, but it cannot be the sole or final acceptance test.

## Candidate families

Evaluate these as separately pre-registered candidates:

1. Degree-corrected two-hop path surprise over MeSH descriptor co-occurrence.
2. Open-discovery ABC ranking conditioned on a seed literature rather than all-pairs global
   ranking.
3. A temporal link-prediction baseline that predicts edges first appearing after the cutoff.

All candidates must:

- exclude synonyms, parent/child descriptors, and near-duplicate ontology siblings;
- control descriptor degree and publication volume;
- report exact co-occurrence rather than top-k API ceilings;
- expose the intermediate B terms responsible for every score;
- avoid LLM-generated features in the measured score.

## Pre-registered evaluation

Choose thresholds before running the held-out set:

- positive-case recall at top 1%, 5%, and 100 candidates;
- rank distribution for adjacent-specialty and distant negatives;
- precision from a blinded manual audit of 30 randomly sampled top candidates;
- sensitivity across time cutoff, vocabulary year, and minimum-support settings.

The minimum shipping gate is:

- at least 50% of held-out positives in the top 5%;
- no hard negative in the top 5%;
- at least 50% manual-audit precision with a documented adjudication procedure;
- stable conclusions across the declared sensitivity range.

Failure at this gate is another publishable negative result, not permission to revise thresholds
after seeing them.

## Sequencing

1. Freeze this plan after review.
2. Build the benchmark and mapping audit.
3. Pre-register candidate formulas and thresholds.
4. Implement the smallest MEDLINE/MeSH pipeline needed for the benchmark.
5. Run development cases, make at most one documented revision, then freeze.
6. Run held-out cases and the manual audit.
7. Only after a pass, design the LLM interpretation schema and pair-detail UI.

No API credits, frontend expansion, or hypothesis generation are required before step 4.
