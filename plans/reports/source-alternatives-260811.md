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
version 2013**. Its full payload has now been acquired, fingerprinted, and audited. The catalog
aggregate counts match, but the measured publication scope does not. It cannot change
`historical_records` to `available_pinned` and cannot be mixed into the existing four-release
benchmark without changing the experimental population.

## Candidate comparison

| Candidate | Dated citation-to-MeSH state | Fixed declared corpus | Current decision |
|---|---|---|---|
| BioASQ Task 1a v2013 | Yes, described with MeSH 2013 labels | 10,876,004 articles measured; reported post-1949 scope does not match | Preserve the sensitivity-blocked pilot; keep the original gate red |
| Current PubMed baseline frozen locally | No historical state; indexing is maintained-current | A complete current release can be pinned | Engineering and future prospective work only |
| Persistent PubMed Abstracts | Dated titles and abstracts, but no historical MeSH assignments | Dated text snapshots are documented | Rejected for metric-v3 historical indexing |
| Europe PMC current bulk services | Current literature metadata and selected full-text bulk sets | Current collections, not the required old MEDLINE baselines | Not a historical-baseline replacement |

The BioASQ count and NLM's 2013 baseline total of 21,508,439 are both published counts for different
declared populations. Their quotient is deliberately not reported as coverage: PMID overlap has not
been measured, the BioASQ payload contains 280 parseable pre-1950 records despite the reported
post-1949 scope, and the NLM total includes non-equivalent record categories.

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
version label alone. The acquired payload now shows that this description is not an exact record
scope contract.

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

## Full-payload audit completed

The generated `benchmarks/v3/manifests/bioasq-2013-task-a.json` pins the 5,471,741,580-byte ZIP at
SHA-256 `c4f738af8835b9fc300488d484efd633fd4137b149cd852b66a839651e328f68`. Its single
`allMeSH.json` member is 18,383,359,066 bytes and uses the observed legacy envelope
`{'articles'=[`, rather than the public sample's standard JSON envelope.

| Full-corpus measurement | Result |
|---|---:|
| Articles | 10,876,004 |
| MeSH assignments | 136,439,656 |
| Distinct labels | 26,563 |
| Average assignments per article | 12.54501709 |
| Articles with no labels | 0 |
| Labels absent from pinned MeSH 2013 | 0 |
| Duplicate normalized assignments | 0 |
| Parseable publication-year range | 1946-2013 |
| Parseable records before 1950 | 280 |
| Parseable non-`YYYY` year values | 751,238 |
| Unparseable year values | 0 |

The parseable year histogram reconciles exactly with the article count. The 280 pre-1950 records
comprise 7 from 1946, 43 from 1947, 58 from 1948, and 172 from 1949.
Thus the three published aggregates match, while the reported publication scope and the declared
snapshot gate do not. The manifest status is `measured_unmatched_input` and contributes zero
readiness.

## Successor semantics protocol frozen

`benchmarks/v3/bioasq-semantics-protocol-v2.json` was frozen after the aggregate source audit and
before any full-corpus selection or new PubMed request. It changes only what the measured sampling
frame made unsatisfiable:

- adds one SHA-256 bottom-k stratum selecting 32 of the 280 records dated 1946-1949;
- increases the declared total from 416 to 448;
- discloses the full source audit and exact year-normalisation rule.

The hash namespace is deliberately unchanged, preserving the original deterministic choices in all
eight 1950-2013 strata. Their sample sizes and rationales are byte-for-byte unchanged. The PubMed
comparison, 90% all-descriptor minimum, 50% major-topic maximum, every-stratum separation rule,
classification labels, and zero-readiness rule are also unchanged. The validator rejects any
successor that tunes those parent fields. No semantics result was observed at freeze time.

The first post-freeze selection attempt stopped before writing a sample or making a PubMed request:
repeated source rows with the same PMID could occupy more than one heap slot even though the frozen
protocol declares `pmid` as its record key. The selector now applies bottom-k to unique retained
PMIDs, replays the full source before emitting the sample, collapses only repeated selected rows
with identical normalized year, stratum, and MeSH assignments, and rejects any conflict. This is an
implementation correction to the frozen record-key rule; the protocol checksum, strata, and
thresholds did not change.

## Bounded semantics result

The deterministic selection and full-source replay completed under the pinned successor. Both
passes scanned 10,876,004 source rows and selected 448 unique PMIDs in the exact nine declared
strata. Within those selected keys, the replay measured 13 extra source occurrences across nine
PMIDs; their normalized year, stratum, and MeSH assignments match, but other source fields were not
compared and this is not a corpus-wide duplicate count. The ignored selection file is pinned in
the result by SHA-256 `536f448266a1f7b8c0453782696188cf13fc7c4e1ab246b537b86fdac2e3a0f3`.

Maintained-current PubMed returned all 448 requested records in the predeclared 200, 200, and 48
record batches. The committed result pins each raw response and parsed-record digest. Across 5,296
BioASQ assignments, 5,201 match maintained-current all-descriptor headings and 455 match
`MajorTopicYN=Y` headings, yielding fractions 0.98206193 and 0.0859139. All-descriptor matching
exceeds major-topic matching in every stratum. The manifest therefore has the predeclared
`sample_consistent_with_all_assigned_descriptors` classification.

This result is deliberately narrower than “the field has been proven corpus-wide.” The strata are
balanced around anomalies and candidate cutoffs rather than weighted to the source population;
PubMed is maintained-current rather than frozen in 2013; 95 assignments do not match a current
descriptor; and the source still fails its reported publication-scope gate. The result contributes
zero readiness and does not replace any missing NLM historical release.

## Secondary-snapshot pilot frozen

`benchmarks/v3/bioasq-pilot.json` was frozen on 2026-08-12 after the source, semantics, case
identities, and descriptor mappings were known but before endpoint-support counts, a BioASQ pilot
formula, scores, or ranks. The positive population is complete rather than convenience-selected:
all five Cancer Discovery cases used in the LION evaluation. SHA-256 bottom-2 assigns IL-17/MKP-1
and Nrf2/pancreatic cancer to held-out; the other three are development cases. All sixteen entries
from the separately frozen negative-control queue are retained with their proposed split, for 21
cases total: 11 development and 10 held-out.

The labels deliberately remain asymmetric in evidential strength. The five positives are
source-labelled LION reproduction targets, not independently validated discovery truth. The eight
hard and eight distant controls are metric-blind ontology-generated proposals, not evidence that no
relationship or non-academic knowledge exists. The protocol tests reproduction and structural-
control separation inside one secondary snapshot; it does not validate a gap detector.

The score-free compatibility gate requires every case endpoint to map uniquely to MeSH 2013 and
have at least ten articles at its source cutoff. All 46 unique endpoint and positive-bridge mappings
were checksum-replayed against the pinned MeSH 2013 archive. The subsequent full scan read
10,876,004 articles and 136,439,656 assignments. Included article counts were 7,689,223 at cutoff
2006, 9,728,136 at 2010, 10,321,817 at 2011, and 10,864,645 at 2012. All 21 cases pass primary
support 10, so no case was dropped or replaced.

The primary gate is not the full decision rule. Held-out hard control
`generated-hard-2012-04-d019956-d019960` has A/C supports 266/10 at cutoff 2011. Its target is
eligible at support 10 but not at sensitivity 20. The frozen rule says an unevaluable sensitivity
setting is not a pass, so the pilot cannot earn a passing label before any metric is run. The audit
therefore sets `metric_work_authorized_by_this_audit` to `false`. The original protocol and cases
remain immutable; a continuation needs a separately named successor frozen before metric output
and must disclose that support counts are now known.

The exact retained direct A-C counts for the five source-labelled positives, in protocol order, are
16, 0, 0, 0, and 5. Eight of sixteen generated controls have zero direct A-C articles; the other
eight have positive counts from 1 to 121. These are source measurements, not evidence that the
positive cases are validated discoveries or that zero-count controls are true negatives.

The held-out signal rule remains fixed: at least one of two positive targets in the top 5%,
no hard control in the top 5%, and all four distant controls below the median, repeated at minimum
supports 5, 10, and 20. A consistent signal remains a BioASQ pilot result with zero readiness; it is
not metric-v3 validation, period-appropriate reconstruction, or permission to add LLM output. The
current pilot stops before this metric stage because sensitivity 20 is not evaluable.

## Implemented streaming audit

`python -m pipeline.benchmark.bioasq_snapshot` now reads plain JSON, gzip, or a ZIP containing one
JSON member without loading the multi-gigabyte array into memory. It:

- fingerprints the downloaded container with SHA-256 and byte count;
- records ZIP member identity, sizes, CRC32 when applicable;
- validates the documented article fields and numeric PMID shape;
- reports canonical, parseable noncanonical, and unparseable year values separately;
- counts articles, assignments, distinct labels, empty-label articles, and the full parseable-year
  histogram;
- checks every observed label against the checksum-pinned 2013 MeSH descriptor archive;
- compares measured aggregates with BioASQ's published 2013 counts; and
- emits zero readiness plus limitations even though every declared aggregate count matches.

`python -m pipeline.benchmark.bioasq_download` now covers both acquisition paths. `sample` verifies
the public sample checksum and fetches the exact current-PubMed comparison. `full` logs in with
credentials read only from `BIOASQ_USERNAME` and `BIOASQ_PASSWORD`, rejects login HTML in place of a
file, checks free disk space, and writes atomically through a `.part` file. No credential or session
cookie enters an artifact, cache identity, command-line argument, or error message.

Rebuild the completed audit to a review path; the strict gate is expected to fail:

```bash
python -m pipeline.benchmark.bioasq_snapshot \
  --output path/to/rebuilt-bioasq-2013-task-a.json \
  path/to/raw_training_set.zip
python -m pipeline.benchmark.bioasq_snapshot \
  --require-declared-match \
  path/to/raw_training_set.zip
```

The first semantics protocol remains unchanged: its strict sampler correctly rejects the 280
records outside its 1950-2013 strata. Reproduce the completed bounded audit only with the pinned
successor, replay the selection before network access, and write outputs to review paths. The
completed pilot audit is primary-compatible but sensitivity-blocked. The next scientific action is
to preserve that result and, only if continuing, freeze a separately named pre-metric successor—not
to flip the original NLM-baseline gate, which remains visible and red.

## Primary documentation

- [BioASQ dataset catalog, version table, access rule, and data terms](https://participants-area.bioasq.org/datasets/)
- [BioASQ peer-reviewed overview and initial-corpus cutoff](https://pmc.ncbi.nlm.nih.gov/articles/PMC4450488/)
- [BioASQ public Task 1a sample](https://participants-area.bioasq.org/download/sampleData/task1a/)
- [BioASQ 2013 challenge operation report](https://bioasq.org/sites/default/files/PublicDocuments/BioASQ_D4.4-Report-On-Challenge-operation-and-technical-support-1_final.pdf)
- [BioASQ first challenge announcement](https://www.bioasq.org/news/bioasq-1st-official-announcement)
- [Pyysalo et al. (2019), LION LBD and its five Cancer Discovery evaluation cases](https://doi.org/10.1093/bioinformatics/bty845)
- [NLM 2013 baseline inventory](https://www.nlm.nih.gov/bsd/licensee/2013_stats/baseline_med_filecount.html)
- [NLM Persistent PubMed Abstracts documentation](https://bionlp.nlm.nih.gov/persistentAbstracts.html)
- [Europe PMC bulk-download documentation](https://dev.europepmc.org/downloads)
