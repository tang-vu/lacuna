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
the required 2007, 2011, 2012, and 2013 descriptor archives were parsed and pinned by SHA-256 on
2026-07-29 in `benchmarks/v3/sources.json`.
On 2026-07-31, official NLM file inventories were also recovered for all four releases and pinned
in `benchmarks/v3/inventories.json`. Those pages establish completeness totals but expose neither
the raw citation XML nor per-file checksums, so the historical-record gate remains unavailable.
A digest-addressed Common Crawl capture of the retired MBR homepage now also preserves the exact
`Download/Baselines/{year}` directory rows for all four required releases. It confirms how the
repository was organized in 2018 but contains no required XML payload, so it contributes no raw
record release to readiness.
On 2026-08-10, NLM Support answered the project's submitted access request: baseline files for
previous years are not available, and the reply points to the current baseline directory. The
committed contract keeps only a public-safe summary; personal correspondence and identifiers stay
outside the repository. This confirms NLM's current distribution position, not the non-existence of
all third-party preservation copies.
This has five consequences:

- no pre-2002 experiment may be called period-appropriate unless a separate contemporaneous
  MEDLINE source is acquired and pinned;
- the fish-oil/Raynaud and magnesium/migraine cases remain useful development diagnostics, but a
  run over today's PubMed indexing is not a historical replication;
- genuinely held-out, period-appropriate tests should use archived baselines from 2002 onward,
  with the baseline year—not only the article publication cutoff—part of the input identity.
- a publication-year cutoff `Y` requires baseline release and MeSH year `Y + 1`, because NLM
  releases that baseline in December after incorporating production-year `Y` updates; using
  baseline `Y` would omit most records published during cutoff year `Y`;
- the archive's documented existence is not evidence that the raw historical records are currently
  retrievable; the original source gate stays blocked unless a verifiable preserved copy is found,
  while any secondary-snapshot experiment requires its own pre-registration and source contract.

## Secondary-snapshot redesign track

The direct NLM request is closed without the four releases, so source recovery and experimental
redesign are now tracked separately in `benchmarks/v3/source-alternatives.json`. None of those
alternatives contributes to the original source gate.

BioASQ Task 1a version 2013 is the leading redesign route. Its acquired registered payload is pinned
by a generated full-corpus manifest. All three catalog aggregates match: 10,876,004 articles,
26,563 distinct labels, and 136,439,656 assignments, whose average rounds to the published 12.55.
The reported post-1949 publication scope does not match the payload: 280 parseable records date to
1946-1949. All year strings are parseable, although 751,238 are not plain `YYYY`. The corpus remains
a plausible dated secondary snapshot, but it is not the
21,508,439-record 2013 NLM baseline and supplies no 2007/2011/2012 release. A checksum-pinned audit
of the five-record public sample found 72 assignments, all present in pinned MeSH 2013. Of those,
71 remain among maintained-current PubMed descriptors and nine carry a current `MajorTopicYN=Y`
flag, so the sample is consistent with `meshMajor` holding all assigned descriptors rather than
only major headings. The sample was not designed or sized to prove corpus-wide semantics, and the
current comparison is not period-appropriate historical indexing.

Before access to the registered payload, a separate checksum-pinned semantics protocol froze 416
SHA-256 bottom-k selections across eight publication-year strata. It gives the four source-defined
post-2002 candidate cutoffs their own coverage, requires every sampled PMID to return from EFetch,
and compares assignment overlap with all maintained-current descriptors versus current
`MajorTopicYN=Y` headings. The protocol was written after the five public records were measured, so
it discloses that evidence; it was written before the full-corpus sample or any v3 metric output.
Even a passing result would remain bounded evidence from maintained-current comparison records and
add zero readiness. The measured payload invalidates this protocol's sampling frame because its
strict selector rejects records outside the frozen 1950-2013 strata. The protocol remains
immutable and no full-corpus semantics sample has been
selected under it.

BioASQ may support a **new, separately pre-registered secondary-snapshot pilot** over its measured
corpus. A separately named successor semantics protocol is now frozen after source audit and before
semantics selection. It adds a 32-record 1946-1949 stratum while retaining the prior 416-record
allocation, hash namespace, comparison, and decision thresholds unchanged. The resulting bounded
audit returned 448/448 maintained-current PubMed records. Of 5,296 BioASQ assignments, 5,201 match
all descriptors and 455 match major-topic headings; all-descriptor matching exceeds major-topic
matching in every stratum, so the frozen sample rule passes. This is not a population-weighted or
period-appropriate result. BioASQ must not be relabelled as a recovered baseline or inserted into
the current benchmark contract. Current PubMed remains an engineering/prospective input, and the
Persistent PubMed Abstracts service remains unsuitable because it lacks historical MeSH
assignments. Full reasoning and acquisition commands are in
`plans/reports/source-alternatives-260811.md`.

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

Negative candidate generation is frozen separately in
`benchmarks/v3/negative-selection.json`. Its fixed seed samples four ontology-sibling hard pairs
and four predefined cross-branch distant pairs from each of the pinned 2012 and 2013 MeSH trees,
alternating development and held-out proposals within each year and kind. Generated records are
not ground truth: they contribute zero until metric-blind human review records a defensible
negative rationale and accepts them into `cases.json`. The generator and validator forbid metric
score, rank, or percentile fields throughout this selection path. An accepted negative retains the
generated proposal ID, a commit-pinned queue link, and a direct public issue-comment adjudication;
the benchmark validator audits the frozen queue and rejects drift in kind, split, cutoff, or
descriptor identity.

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
4. Keep watching for independently preserved complete NLM releases. The archived-baseline reader
   and targeted pair/ABC accumulator remain closed until complete release file sets are pinned. The
   BioASQ full-payload audit matches published aggregate counts but fails the reported publication
   scope, so it emits zero readiness and the first frozen semantics protocol remains unrun. A
   separately named 448-record successor protocol is now frozen to handle the measured 280
   pre-1950 records without changing the prior thresholds. Its deterministic sample has been
   replayed and the bounded maintained-current audit follows the frozen passing rule while adding
   zero readiness. Pre-register the new secondary-snapshot experiment, case population, and success
   criteria before any candidate formula runs.
5. Run development cases, make at most one documented revision, then freeze.
6. Run held-out cases and the manual audit.
7. Only after a pass, design the LLM interpretation schema and pair-detail UI.

No API credits, frontend expansion, or hypothesis generation are required before step 4.
