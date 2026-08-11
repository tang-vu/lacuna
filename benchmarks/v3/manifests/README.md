# Benchmark input manifests

This directory is intentionally empty until a reviewed raw source is acquired. One generated JSON
manifest belongs here for each required historical baseline year. A separately named BioASQ audit
manifest may also belong here after the registered v2013 payload matches its published aggregate
scope; that secondary manifest contributes zero readiness and does not enter `sources.json` as a
historical MEDLINE release. Multi-gigabyte payloads stay in ignored local pipeline state; their
identities do not.

Build a manifest only after acquiring the complete release:

```bash
python -m pipeline.benchmark.build_release_manifest \
  --year 2012 \
  --base-url https://official-source.example/baseline/2012/ \
  --output benchmarks/v3/manifests/medline-2012.json \
  data/medline-baseline/2012/*.xml.gz
```

The command:

- refuses non-HTTPS source identities;
- sorts unique filenames;
- hashes the compressed transport bytes with SHA-256;
- streams every file and records its parsed `PubmedArticle` count;
- loads the official inventory metadata through the checksum-pinned reference in `sources.json`;
- compares the complete contiguous filename sequence plus measured file, transport-byte, and record
  totals with that pinned inventory before creating any output;
- creates, but never overwrites, the output manifest;
- prints a small reference containing the manifest checksum, measured aggregates, and inventory
  aggregates.

Review that reference, then add it to the historical-record source's `manifests` list in
`../sources.json`. Paths there are relative to `benchmarks/v3`, for example
`manifests/medline-2012.json`. The inventory URL and totals are not accepted as command-line input:
they come from the fingerprinted `inventories.json` contract, preventing a locally
self-consistent subset—or a mistyped total—from certifying itself as a complete release. Use
`--source-contract` only when testing an independently fingerprinted contract outside the default
repository path.

`validate_sources` reloads every referenced manifest and reconciles its checksum, release year,
file count, compressed-byte total, record total, the independently recorded inventory totals,
unique filenames, URLs, and per-file checksums. The production reader then requires the complete
local file set described by that reviewed manifest. A local subset cannot inherit the
`pinned_historical_medline` label after the full manifest has been pinned.

Generated manifests are committed provenance, not hand-edited source data. If a value is wrong,
fix the acquisition input and rebuild to a new reviewed file rather than editing a count until the
validator passes.

For the distinct zero-readiness BioASQ route, use
`python -m pipeline.benchmark.bioasq_snapshot --require-declared-match`. Its generated manifest
belongs at `bioasq-2013-task-a.json`, remains governed by `../source-alternatives.json`, and cannot
be referenced as one of the four complete NLM release manifests.
