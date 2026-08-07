# Metric v3 benchmark

This directory is a pre-metric selection record, not a validation result. Its current status is
`draft`: it contains two canonical development positives, no hard negatives, no distant
negatives, and no held-out case with reconstructable period-appropriate indexing.

`candidates.json` is the positive-case intake ledger in front of that benchmark. It currently records two
accepted development cases, five proposed cases from a published seven-case replication catalog,
five proposed post-2002 cases from LION's nominal cancer set, and two rejected examples of noisy
time-sliced labels. Proposed and rejected entries contribute **zero** cases to readiness. The
separation is deliberate: reuse in an LBD paper is evidence for review, not automatic proof that a
pair was a meaningful discovery.

Negative controls do not duplicate records in `candidates.json`. Their frozen intake is
`../../artifacts/negative-candidates.json`, and `validate_v3` reconciles every accepted negative
directly against that queue and its public metric-blind adjudication. This keeps positive discovery
evidence requirements—bridge publication and independent replication—from being incorrectly
applied to controls.

Run its structural audit separately:

```bash
python -m pipeline.benchmark.validate_candidates
```

`negative-selection.json` is the frozen, metric-blind sampling contract for the two negative
cohorts. It deterministically proposes eight ontology-sibling hard negatives and eight fixed
cross-branch distant negatives from the pinned 2012 and 2013 MeSH descriptor trees. The generated
`../../artifacts/negative-candidates.json` queue is review material only: its development and
held-out labels are proposed, all entries contribute zero readiness, and none are benchmark cases.
Rebuild it only from the checksum-verified vocabulary archives, then validate the committed result:

```bash
python -m pipeline.benchmark.negative_controls --build
python -m pipeline.benchmark.negative_controls
```

The separate generated `../../artifacts/negative-review-context.json` makes review less dependent
on labels alone. It is built only from checksum-verified production-year MeSH archives and the
frozen queue:

```bash
python -m pipeline.benchmark.negative_review_context --build
python -m pipeline.benchmark.negative_review_context
```

It exposes scope notes, entry terms, all descriptor tree paths, annotations, and hard-negative
parent labels. It is a generated vocabulary aid with zero readiness—not a judgment that a pair is
unrelated and not a substitute for public human adjudication.

Human adjudication must happen without metric output. A reviewer may reject or replace a generic,
polysemous, or substantively related pair; acceptance requires a public negative rationale and an
explicit move into `cases.json`. Every accepted negative must retain its generated
`selection_candidate_id`, cite the frozen queue as `negative_selection_source`, and cite the public
issue-comment decision as `metric_blind_adjudication`. The queue evidence URL is pinned to the
commit that generated it rather than mutable `main`. `validate_v3` audits the queue before trusting
that link, then requires the case kind, split, cutoff, and descriptor labels to match the frozen proposal.
Changing any of those fields requires changing and regenerating the pre-metric selection record;
it cannot be hidden in the accepted case.

After a reviewer publishes the decision, generate a validator-ready case fragment without
retyping frozen proposal fields:

```bash
python -m pipeline.benchmark.build_negative_case \
  --candidate-id generated-hard-2012-01-d001174-d014143 \
  --adjudication-url https://github.com/tang-vu/lacuna/issues/4#issuecomment-COMMENT_ID \
  --negative-rationale "Reviewer-authored rationale"
```

This command prints JSON and never edits `cases.json`. It validates the queue, direct-comment URL
shape, and a non-trivial rationale, but the cited human decision must still be inspected before the
fragment is appended.

Historical inputs have their own dated access record:

```bash
python -m pipeline.benchmark.validate_sources
python -m pipeline.benchmark.validate_sources --require-ready
```

The first command validates the record and reports its blockers. The second is intentionally red:
the legacy MBR download host is unavailable. The public 2007, 2011, 2012, and 2013 production-year
MeSH descriptor archives are now parsed and pinned by SHA-256, but `sources.json` keeps records and
vocabulary as separate gates because vocabulary files alone cannot reconstruct period-appropriate
indexing. A support request is prepared at
`plans/requests/nlm-historical-medline-access.md`; it is explicitly not sent and contains no
maintainer contact details.

The retired repository homepage also has a checksum-pinned Common Crawl capture:

```bash
python -m pipeline.benchmark.mbr_capture
python -m pipeline.benchmark.mbr_capture --probe --require-match
```

The live probe checks the index record and independently fetches the exact WARC byte range, checks
its SHA-1 payload digest, and parses the 2007, 2011, 2012, and 2013
`Download/Baselines/{year}` rows against `inventories.json`. An index outage therefore does not hide
a valid payload replay, although `--require-match` still requires both checks. That capture contains
directory metadata, not baseline XML; success leaves historical records at 0/4, while unreachable
dependencies are reported separately from content drift.

The archived-baseline reader is implemented and fixture-tested:

```bash
python -m pipeline.benchmark.medline_baseline \
  --baseline-year 2012 \
  --cutoff-year 2011 \
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
The production entry point requires baseline release year `R = cutoff year + 1`: NLM releases
baseline `R` in December after incorporating production-year `R-1` updates and maintaining records
to MeSH `R`. A same-numbered baseline and cutoff would omit most of the claimed cutoff year.
Multi-file releases use generated manifests under `benchmarks/v3/manifests/`; `sources.json`
contains only one checksummed reference per release rather than hundreds of hand-maintained file
entries. Each reference keeps measured aggregates separate from totals transcribed from the
official inventory, and validation requires them to agree. This catches a local subset that
disagrees with the reviewed values; it does not verify the remote inventory page automatically.

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
python -m pipeline.benchmark.audit_mesh 2012 "NF-kappa B" "Adenoma"
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

LION defines its evaluation corpus at publication-year granularity: literature through the year
five years before the relevant discovery publication. The intake therefore records both the
source rule and the derived cutoff year. It separately records the following year's MEDLINE
baseline release and MeSH vocabulary, reflecting NLM's year-end production cycle. This resolves
the temporal rule without pretending that an exact calendar date was published; acquiring and
pinning the complete matching MEDLINE releases remains a separate source-readiness requirement.

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
