# Metric v3 benchmark

This directory is a pre-metric selection record, not a validation result. Its current status is
`draft`: it contains two canonical development positives, no hard negatives, no distant
negatives, and no held-out case with reconstructable period-appropriate indexing.

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
