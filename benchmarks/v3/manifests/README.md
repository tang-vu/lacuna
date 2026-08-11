# Benchmark input manifests

This directory contains generated source audits, not hand-edited measurements. One generated JSON
manifest belongs here for each acquired input. The bounded `bioasq-2013-public-sample.json` audit
pins the five-record public sample and a maintained-current PubMed comparison; it contributes zero
readiness and does not certify the registered corpus. The full `bioasq-2013-task-a.json` audit pins
the acquired payload and records `measured_unmatched_input`: catalog aggregate counts match, while
280 records precede the declared post-1949 scope; all years are parseable. Neither
BioASQ manifest enters `sources.json` as a historical NLM release. Multi-gigabyte payloads stay in
ignored local pipeline state; their identities do not.

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

For the distinct zero-readiness BioASQ route, use `python -m pipeline.benchmark.bioasq_snapshot`
without the strict flag and write to a review path. Its generated manifest remains governed by
`../source-alternatives.json` and cannot be referenced as one of the four complete NLM release
manifests. Running with `--require-declared-match` is now a negative gate check and must fail for the
pinned payload.

The separate `../bioasq-semantics-protocol.json` was frozen before the registered payload was
available. The measured payload violates its declared 1950-2013 sampling frame, so its strict
selector rejects the source and the protocol remains an immutable failed pre-registration. Do not
write `bioasq-2013-semantics.json` from a modified copy. The separately named
`../bioasq-semantics-protocol-v2.json` now handles the 280 pre-1950 records with a predeclared
32-record stratum. It was frozen before selection and keeps the prior comparison and decision
thresholds unchanged. The committed `bioasq-2013-semantics.json` records the completed 448-record
comparison: 448/448 PubMed records returned, with 5,201/5,296 assignments matching all descriptors
and 455/5,296 matching major-topic headings. The classification follows the frozen rule and
contributes zero readiness. Generate any reproduction only under that checksum-pinned protocol,
then replay it from the full snapshot before EFetch and write the result to a review path.

Reproduce the committed public-sample audit with:

```bash
python -m pipeline.benchmark.bioasq_download sample
python -m pipeline.benchmark.bioasq_sample_audit
```

The second command refuses to overwrite the committed manifest. Generate into a clean temporary
checkout or provide a different `--output`, compare the byte-identical JSON, then review any live
PubMed response drift rather than silently replacing the pinned observation.
