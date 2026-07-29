# Metric v3 benchmark

This directory is a pre-metric selection record, not a validation result. Its current status is
`draft`: it contains two canonical development positives, no hard negatives, no distant
negatives, and no held-out case with reconstructable period-appropriate indexing.

`candidates.json` is the intake ledger in front of that benchmark. It currently records two
accepted development cases, five proposed cases from a published seven-case replication catalog,
five proposed post-2002 cases from LION's nominal cancer set, and two rejected examples of noisy
time-sliced labels. Proposed and rejected entries contribute **zero** cases to readiness. The
separation is deliberate: reuse in an LBD paper is evidence for review, not automatic proof that a
pair was a meaningful discovery.

Run its structural audit separately:

```bash
python -m pipeline.benchmark.validate_candidates
```

Historical inputs have their own dated access record:

```bash
python -m pipeline.benchmark.validate_sources
python -m pipeline.benchmark.validate_sources --require-ready
```

The first command validates the record and reports its blockers. The second is intentionally red:
the legacy MBR download host is unavailable. The public 2006, 2010, 2011, and 2012 production-year
MeSH descriptor archives are now parsed and pinned by SHA-256, but `sources.json` keeps records and
vocabulary as separate gates because vocabulary files alone cannot reconstruct period-appropriate
indexing. A support request is prepared at
`plans/requests/nlm-historical-medline-access.md`; it is explicitly not sent and contains no
maintainer contact details.

The archived-baseline reader is implemented and fixture-tested:

```bash
python -m pipeline.benchmark.medline_baseline \
  --baseline-year 2010 \
  --cutoff-year 2005 \
  --pair D016328:D000236 \
  data/medline-baseline/*.xml.gz
```

It streams XML files without loading the corpus into memory, fingerprints the compressed inputs,
counts direct endpoint co-occurrence, computes the independence expectation, and reports shared
ABC descriptors with counts from both sides. The command currently refuses to run before touching
the supplied files because `historical_records` is not `available_pinned`. Once that source gate is
green, every local filename, byte count, and SHA-256 must match the complete pinned release for the
requested baseline year. A successful report also carries the checksum of the source contract and
the matching production-year MeSH archive. The low-level fixture API labels arbitrary XML as
`unverified_medline_xml`; only this exact-match path may emit `pinned_historical_medline`.
Multi-file releases use generated manifests under `benchmarks/v3/manifests/`; `sources.json`
contains only one checksummed reference and aggregate totals per release rather than hundreds of
hand-maintained file entries.

The reader selects its record shape from the document root. It supports the historical
`MedlineCitationSet/MedlineCitation` distribution and the current
`PubmedArticleSet/PubmedArticle/MedlineCitation` distribution without counting current citations
twice. Delete records are ignored.

The same streaming parser has also read one checksum-verified file from the current 2026 PubMed
baseline: 30,000 records, with no missing publication year or descriptor UI in that file. The
dated [smoke-test report](../../plans/reports/validation-260729-medline-reader-smoke.md) labels this
as schema compatibility only. Current indexing remains unsuitable for the historical experiment.

Search a pinned vocabulary without falling back to today's MeSH service:

```bash
python -m pipeline.benchmark.audit_mesh 2011 "NF-kappa B" "Adenoma"
```

The output includes the archive checksum and calls unmatched terms out explicitly. It is mapping
evidence, not evidence that the descriptor was assigned to any particular historical citation.
All ten LION endpoints and all five nominated bridges have mapping candidates in the relevant
production-year vocabulary. They remain `proposed`: cross-vocabulary identity still needs
adjudication, and the historical-record source gate is unavailable.

An accepted intake record must link to exactly one case in `cases.json` and carry a selection
source, bridge publication, and independent LBD replication. Replication supports using the pair
as a development diagnostic; it does not establish that the proposed biological relationship is
true. A proposed record must list the unresolved work; a rejected record keeps the methodological
rejection visible so the same noisy example is not reintroduced later. Neither file may contain
metric scores or ranks.

The benchmark is ready to freeze only when all of these are true:

- at least 8 positives, 8 hard negatives, and 8 distant negatives are sourced;
- at least 4 cases of each kind are held out;
- at least two held-out cutoffs use a pinned official baseline from 2002 or later with its matching
  MeSH production year;
- ambiguous mappings remain recorded as ambiguous rather than being chosen by whichever ranks
  best;
- selection is completed before any v3 candidate formula sees the held-out cases.

Run the structural audit at any time:

```bash
python -m pipeline.benchmark.validate_v3
```

That command succeeds for a well-formed draft but prints every readiness blocker. The release gate
is intentionally stricter:

```bash
python -m pipeline.benchmark.validate_v3 --require-ready
```

It must fail until the benchmark is frozen and complete. Case files may not contain score, rank,
percentile, or other metric-output fields; the validator rejects them to make score-driven case
selection visible.

The intake policy is motivated by two documented failure modes:

- the seven-case replication catalog reports that direct connections existed for several reused
  targets and that apparently useful bridge terms can collapse into semantic noise;
- time-sliced co-occurrence labels include chance pairs and generic terms, so a newly observed
  co-occurrence cannot serve as discovery ground truth without adjudication.

Sources:

- [Preiss and Stevenson (2017), replication cases and filtering analysis](https://doi.org/10.1186/s12859-017-1641-9)
- [Moreau (2023), critique of LBD evaluation methodology](https://doi.org/10.1093/bioinformatics/btad090)
- [Pyysalo et al. (2019), LION case-selection procedure and source entity IDs](https://doi.org/10.1093/bioinformatics/bty845)
- [Crichton et al. (2020), independent reuse of the LION cases](https://doi.org/10.1371/journal.pone.0232891)

The LION cases are promising candidates for the post-2002 held-out requirement, not ready-made
MeSH cases. Their source triples mix Protein Ontology, ChEBI, Cancer Hallmarks, and MeSH IDs. The
intake preserves those identities and records descriptor mapping as unresolved; silently replacing
them with convenient modern MeSH terms could change the discovery being tested.

For citation and current MeSH metadata audits, a small EFetch client is available:

```bash
NCBI_EMAIL=you@example.org python -m pipeline.pubmed_client 3797213 3075738
```

NCBI asks software clients to send a registered tool/email identity. `NCBI_API_KEY` is optional.
The client batches at most 200 PMIDs, strips both values from cache provenance and errors, and
stores no abstract text. Its output is always labelled `maintained_current_pubmed`; it is not the
archived-baseline pipeline. Users of NCBI data remain subject to the
[NCBI disclaimer and copyright notice](https://www.ncbi.nlm.nih.gov/home/about/policies/).

The two current mappings were verified against NLM's current MeSH service. They are labelled
`maintained_current`, not `period_appropriate`. Current PubMed records and the annual baseline are
maintained to newer vocabulary, while NLM's static baseline repository begins in 2002:

- [NLM annual baseline overview](https://www.nlm.nih.gov/bsd/licensee/baseline.html)
- [NLM baseline repository reference](https://lhncbc.nlm.nih.gov/ii/information/MBR/MEDLINE_Baseline_Repository_Detail_2017.pdf)
- [NLM MeSH production-year downloads](https://www.nlm.nih.gov/databases/download/mesh.html)
