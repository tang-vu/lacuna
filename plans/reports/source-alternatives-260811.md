# Historical MEDLINE source alternatives

**Date:** 2026-08-11

**Original historical-record gate:** unchanged, `unavailable`

**Alternative-track readiness contribution:** `0`

## Decision

No reviewed source is a drop-in replacement for the complete 2007, 2011, 2012, and 2013 NLM
baseline releases. NLM Support has confirmed that previous-year baseline files are not available
from its present distribution service. That closes the direct NLM request; it does not establish
that no third party preserved a copy.

The strongest actionable alternative is the registered-download **BioASQ Task 1a training set,
version 2013**. It can be considered for a separately pre-registered 2013-snapshot pilot after the
payload is acquired and audited. It cannot change `historical_records` to `available_pinned` and
cannot be mixed into the existing four-release benchmark without changing the experimental
population.

## Candidate comparison

| Candidate | Dated citation-to-MeSH state | Fixed declared corpus | Current decision |
|---|---|---|---|
| BioASQ Task 1a v2013 | Yes, described with MeSH 2013 labels | 10,876,004 post-1949 MEDLINE articles; registered download | Audit for a redesigned 2013-snapshot pilot |
| Current PubMed baseline frozen locally | No historical state; indexing is maintained-current | A complete current release can be pinned | Engineering and future prospective work only |
| Persistent PubMed Abstracts | Dated titles and abstracts, but no historical MeSH assignments | Dated text snapshots are documented | Rejected for metric-v3 historical indexing |
| Europe PMC current bulk services | Current literature metadata and selected full-text bulk sets | Current collections, not the required old MEDLINE baselines | Not a historical-baseline replacement |

The BioASQ count and NLM's 2013 baseline total of 21,508,439 are both published counts for different
declared populations. Their quotient is deliberately not reported as coverage: PMID overlap has not
been measured, BioASQ is scoped to articles published after 1949, and the NLM total includes older
and non-equivalent record categories.

## Why BioASQ is worth auditing

- The official catalog says each annual Task a training set contains PubMed articles with MeSH
  terms assigned by PubMed curators, and that annual versions use the corresponding MeSH version.
- It retains the 2013 version with 10,876,004 articles, 26,563 covered MeSH labels, and a published
  average of 12.55 labels per article.
- A contemporary BioASQ report describes the collection as MEDLINE articles published after 1949
  from 8,915 journals.
- The original announcement dates training-data availability to 18 March 2013.
- The catalog states CC BY 2.5 distribution terms, but the payload download requires a registered
  BioASQ account.

Those points establish a plausible dated secondary snapshot. They do not establish complete NLM
baseline coverage. A peer-reviewed BioASQ overview further states that the initial corpus included
all MEDLINE articles with title, abstract, and MeSH labels indexed before 1 March 2013, and that the
training data was released on 18 March 2013. This pins the intended cutoff more precisely than the
version label alone, but does not substitute for acquiring the payload.

## Public sample audit completed

The official five-record Task 1a sample was downloaded, SHA-256 pinned, checked against the pinned
2013 descriptor vocabulary, and compared with an exact five-PMID maintained-current PubMed EFetch
response. The generated audit is
`benchmarks/v3/manifests/bioasq-2013-public-sample.json`.

| Bounded measurement | Result |
|---|---:|
| Public sample records | 5 |
| `meshMajor` assignments | 72 |
| Distinct labels | 56 |
| Labels absent from pinned MeSH 2013 | 0 |
| Assignments matching current PubMed descriptors | 71/72 |
| Assignments matching current `MajorTopicYN=Y` descriptors | 9/72 |

The single sample assignment absent from the current record is `Intervention Studies` on PMID
23483175. This demonstrates a measured difference from current indexing, not why or when it
changed. The 71-versus-9 comparison is consistent with the misleadingly named `meshMajor` field
containing all assigned descriptors rather than only major-topic headings. Because the public
sample has only five records and the comparison XML is maintained-current, it does not settle the
field semantics across 10,876,004 records or reconstruct 2013 major-topic flags.

## Full-payload semantics protocol frozen

`benchmarks/v3/bioasq-semantics-protocol.json` was frozen after the bounded public-sample result but
before access to the registered corpus. It selects the 416 lowest SHA-256 record keys within eight
fixed publication-year strata. Separate strata cover 2006, 2010, 2011, and 2012 because those are
the source-defined cutoffs in the post-2002 positive-candidate queue; selection never reads a gap
score, rank, bridge, or candidate metric output.

The decision rule requires all 416 PMIDs to return from maintained-current PubMed, at least 90% of
BioASQ assignments to match current descriptor headings, at most 50% to match current
`MajorTopicYN=Y` headings, and all-descriptor overlap to exceed major-topic overlap in every
stratum. These deliberately separated thresholds were informed by the disclosed five-record
sample, not by the unavailable full-payload sample. Passing would be bounded evidence that the
field behaves like all assigned descriptors in the selected records. It would not recover 2013
major-topic flags, estimate population coverage, or add metric-v3 readiness.

## Implemented acquisition audit

`python -m pipeline.benchmark.bioasq_snapshot` now reads plain JSON, gzip, or a ZIP containing one
JSON member without loading the multi-gigabyte array into memory. It:

- fingerprints the downloaded container with SHA-256 and byte count;
- records ZIP member identity, sizes, CRC32 when applicable;
- validates the documented article fields and numeric PMID/year shapes;
- counts articles, assignments, distinct labels, empty-label articles, and publication-year bounds;
- checks every observed label against the checksum-pinned 2013 MeSH descriptor archive;
- compares measured aggregates with BioASQ's published 2013 counts; and
- emits zero readiness plus limitations even when every declared aggregate matches.

`python -m pipeline.benchmark.bioasq_download` now covers both acquisition paths. `sample` verifies
the public sample checksum and fetches the exact current-PubMed comparison. `full` logs in with
credentials read only from `BIOASQ_USERNAME` and `BIOASQ_PASSWORD`, rejects login HTML in place of a
file, checks free disk space, and writes atomically through a `.part` file. No credential or session
cookie enters an artifact, cache identity, command-line argument, or error message.

Run after the BioASQ account has been activated:

```bash
python -m pipeline.benchmark.bioasq_download full
python -m pipeline.benchmark.bioasq_snapshot \
  --require-declared-match \
  --output benchmarks/v3/manifests/bioasq-2013-task-a.json \
  path/to/raw_training_set.zip
python -m pipeline.benchmark.bioasq_semantics sample \
  path/to/raw_training_set.zip \
  --output data/medline-baseline/bioasq/semantics-sample.json
python -m pipeline.benchmark.bioasq_semantics audit \
  data/medline-baseline/bioasq/semantics-sample.json \
  --snapshot path/to/raw_training_set.zip \
  --output benchmarks/v3/manifests/bioasq-2013-semantics.json
```

The audit command replays the selection from the full snapshot before any network call, so a
hand-edited sample cannot inherit the source digest. It requires `NCBI_EMAIL`; stored queries omit
the email and optional API key, while each exact response is pinned by byte count and SHA-256.
After reviewing the aggregate and bounded semantics results, write and freeze a new
pre-registration whose population is the measured BioASQ corpus. The original NLM-baseline gate
remains visible and red.

## Primary documentation

- [BioASQ dataset catalog, version table, access rule, and data terms](https://participants-area.bioasq.org/datasets/)
- [BioASQ peer-reviewed overview and initial-corpus cutoff](https://pmc.ncbi.nlm.nih.gov/articles/PMC4450488/)
- [BioASQ public Task 1a sample](https://participants-area.bioasq.org/download/sampleData/task1a/)
- [BioASQ 2013 challenge operation report](https://bioasq.org/sites/default/files/PublicDocuments/BioASQ_D4.4-Report-On-Challenge-operation-and-technical-support-1_final.pdf)
- [BioASQ first challenge announcement](https://www.bioasq.org/news/bioasq-1st-official-announcement)
- [NLM 2013 baseline inventory](https://www.nlm.nih.gov/bsd/licensee/2013_stats/baseline_med_filecount.html)
- [NLM Persistent PubMed Abstracts documentation](https://bionlp.nlm.nih.gov/persistentAbstracts.html)
- [Europe PMC bulk-download documentation](https://dev.europepmc.org/downloads)
