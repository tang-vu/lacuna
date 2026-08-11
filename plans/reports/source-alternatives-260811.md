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
baseline coverage or settle whether the JSON field named `meshMajor` contains major headings only
or all assigned descriptor labels. Both questions remain explicit acquisition-audit blockers.

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

Run after registered download:

```bash
python -m pipeline.benchmark.bioasq_snapshot \
  --require-declared-match \
  --output benchmarks/v3/manifests/bioasq-2013-task-a.json \
  path/to/raw_training_set.zip
```

Before adopting the result, compare a deterministic PMID sample and its `meshMajor` labels with a
dated reference that distinguishes major-topic flags from the complete assigned descriptor set.
Then write and freeze a new pre-registration whose population is the measured BioASQ corpus. The
original NLM-baseline gate remains visible and red.

## Primary documentation

- [BioASQ dataset catalog, version table, access rule, and data terms](https://participants-area.bioasq.org/datasets/)
- [BioASQ 2013 challenge operation report](https://bioasq.org/sites/default/files/PublicDocuments/BioASQ_D4.4-Report-On-Challenge-operation-and-technical-support-1_final.pdf)
- [BioASQ first challenge announcement](https://www.bioasq.org/news/bioasq-1st-official-announcement)
- [NLM 2013 baseline inventory](https://www.nlm.nih.gov/bsd/licensee/2013_stats/baseline_med_filecount.html)
- [NLM Persistent PubMed Abstracts documentation](https://bionlp.nlm.nih.gov/persistentAbstracts.html)
- [Europe PMC bulk-download documentation](https://dev.europepmc.org/downloads)
