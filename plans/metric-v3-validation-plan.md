# Metric v3 validation plan

**Status:** proposal only — no v3 metric has been implemented or tuned.

## Why a redesign is required

The failed v1 and v2 experiments established that a global OpenAlex topic-pair ranking is dominated
by adjacent specialties that the classifier treats as alternatives. Completing the same sweep or
adding an LLM cannot repair that construct-validity failure.

Metric v3 must test a narrower claim: whether term-level, time-appropriate biomedical indexing can
recover literature-based discoveries across multiple historical cases without ranking ontology
siblings and unrelated pairs as gaps.

## Feasibility correction: "historical MeSH" is not in the current baseline

The first draft assumed that filtering current PubMed records by publication year preserved the
MeSH vocabulary assigned in that year. NLM's own baseline documentation says the opposite: before
each annual baseline, records are maintained to reflect the **next year's MeSH vocabulary**. The
current baseline and E-utilities therefore expose maintained indexing, not a frozen 1986 view.

NLM's MEDLINE/PubMed Baseline Repository documented annual static views only from 2002 onward. Its
reference material also states that each baseline had already undergone year-end processing for
that baseline's vocabulary year. However, the documented `mbr.nlm.nih.gov` download host no longer
resolved when checked on 2026-07-29, and the surviving reference URL redirected to an Archive-It
HTML wrapper rather than raw baseline data. Public production-year MeSH files remain reachable;
the required 2006, 2010, 2011, and 2012 descriptor archives were parsed and pinned by SHA-256 on
2026-07-29 in `benchmarks/v3/sources.json`.
This has four consequences:

- no pre-2002 experiment may be called period-appropriate unless a separate contemporaneous
  MEDLINE source is acquired and pinned;
- the fish-oil/Raynaud and magnesium/migraine cases remain useful development diagnostics, but a
  run over today's PubMed indexing is not a historical replication;
- genuinely held-out, period-appropriate tests should use archived baselines from 2002 onward,
  with the baseline year—not only the article publication cutoff—part of the input identity.
- the archive's documented existence is not evidence that the raw historical records are currently
  retrievable; source acquisition is a blocker until NLM supplies or identifies stable files.

Primary documentation:

- [NLM annual baseline overview](https://www.nlm.nih.gov/bsd/licensee/baseline.html)
- [NLM MEDLINE/PubMed Baseline Repository reference material](https://lhncbc.nlm.nih.gov/ii/information/MBR/MEDLINE_Baseline_Repository_Detail_2017.pdf)
- [NLM MeSH production-year archives](https://www.nlm.nih.gov/databases/download/mesh.html)

## Data path

- Use a pinned archived MEDLINE/PubMed baseline and its matching MeSH production-year files for
  candidate generation and retrospective validation. NLM documentation establishes that this
  design existed from 2002 onward, but the raw historical-record access path must be reacquired.
- Track historical citation records and production-year MeSH as separate source gates. Having the
  vocabulary without the records is not a reconstructable baseline.
- Treat current PubMed E-utilities as a metadata and mapping-audit aid only. A descriptor returned
  today must be labelled `maintained_current_indexing`, never `period_appropriate`.
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
diagnostic, but it cannot be the sole or final acceptance test. At least two held-out cutoffs must
be 2002 or later so their vocabulary state can be reconstructed from an official archived
baseline. Any earlier case without a contemporaneous source is excluded from the shipping gate.
Before any formula is run, freeze at least four held-out cases of each kind so the nominal
eight-case minimum cannot be satisfied almost entirely with development examples.

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
2. Build the benchmark contract and mapping audit, explicitly separating maintained-current,
   period-appropriate, ambiguous, and unavailable mappings.
3. Pre-register candidate formulas and thresholds.
4. Acquire stable raw baseline files from NLM or another source NLM identifies, then implement the
   smallest archived-baseline/MeSH pipeline needed for the benchmark; E-utilities may supply
   citation metadata but not historical vocabulary state.
5. Run development cases, make at most one documented revision, then freeze.
6. Run held-out cases and the manual audit.
7. Only after a pass, design the LLM interpretation schema and pair-detail UI.

No API credits, frontend expansion, or hypothesis generation are required before step 4.
