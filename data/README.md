# Local pipeline state

This directory holds regenerable API caches, the fetched OpenAlex taxonomy, and co-occurrence
rows. It also holds trimmed PubMed metadata fetched for benchmark mapping audits. Those files are
intentionally ignored: the current pre-1986 pilot is tens of megabytes and the replacement MEDLINE
experiment will be larger.

Production-year MeSH descriptor archives are cached under `data/mesh/`. Download, validate, and
fingerprint the years required by the v3 source contract with:

```bash
python -m pipeline.benchmark.pin_mesh
```

The command prints checksums for review but does not edit the committed source contract.

Historical MEDLINE baseline XML belongs under `data/medline-baseline/` and is ignored by Git. The
streaming reader will not trust files merely because they are in that directory: a production run
requires every file in the selected release to match the filename, byte count, and SHA-256 pinned
in `benchmarks/v3/sources.json`. The record source is currently unavailable, so the command remains
closed even though its parser and exact pair/ABC accumulator are fixture-tested.

After acquiring a complete release, use `pipeline.benchmark.build_release_manifest` to fingerprint
and count its files. XML stays here; the generated manifest is reviewed and committed under
`benchmarks/v3/manifests/`.

A registered BioASQ Task 1a v2013 download may also be stored under
`data/medline-baseline/bioasq/`. The public sample and maintained-current PubMed comparison can be
downloaded and audited reproducibly without an account:

```bash
python -m pipeline.benchmark.bioasq_download sample
python -m pipeline.benchmark.bioasq_sample_audit
```

The full corpus downloader reads credentials only from the process environment and writes through
a `.part` file so failed login, checksum drift, or an interrupted transfer cannot masquerade as a
complete ZIP:

```bash
$env:BIOASQ_USERNAME = Read-Host "BioASQ username"
$env:BIOASQ_PASSWORD = Read-Host -MaskInput "BioASQ password"
python -m pipeline.benchmark.bioasq_download full
python -m pipeline.benchmark.bioasq_snapshot \
  --output path/to/rebuilt-bioasq-2013-task-a.json \
  data/medline-baseline/bioasq/PubMedWithMeSH.zip
python -m pipeline.benchmark.bioasq_snapshot \
  --require-declared-match \
  data/medline-baseline/bioasq/PubMedWithMeSH.zip
```

The strict command is expected to fail: the pinned audit measures 280 records before the reported
post-1949 scope. All years are parseable, with 751,238 explicitly normalized non-`YYYY` values. Do
not run the original semantics protocol against this mismatched sampling frame. The separately
named successor is now frozen and checksum-pinned; use it explicitly:

```bash
python -m pipeline.benchmark.bioasq_semantics \
  --protocol benchmarks/v3/bioasq-semantics-protocol-v2.json sample \
  data/medline-baseline/bioasq/PubMedWithMeSH.zip \
  --output data/medline-baseline/bioasq/semantics-sample.json
$env:NCBI_EMAIL = Read-Host "NCBI registered email"
python -m pipeline.benchmark.bioasq_semantics \
  --protocol benchmarks/v3/bioasq-semantics-protocol-v2.json audit \
  data/medline-baseline/bioasq/semantics-sample.json \
  --snapshot data/medline-baseline/bioasq/PubMedWithMeSH.zip \
  --output benchmarks/v3/manifests/bioasq-2013-semantics.json
```

The sampler makes a second streaming pass before it writes output. That replay verifies every
occurrence of the 448 retained PMID keys: repeated occurrences with the same normalized year,
stratum, and MeSH assignments are collapsed, while a difference in any of those compared fields for
the same retained PMID is a hard error. Other source fields are outside this duplicate check.

Do not put the variables in a repository `.env` file or pass secrets on the command line. Only the
generated aggregate and bounded semantics manifests belong in Git. Any future selection stays in
ignored local state and must be reproducible from the source snapshot and its separately pinned
successor protocol. This secondary corpus contributes zero readiness and must not be named or
referenced as one of the four complete historical NLM releases.

Before any BioASQ pilot formula is written, validate the frozen case and mapping boundary:

```bash
python -m pipeline.benchmark.validate_bioasq_pilot --verify-local-mesh
```

The protocol contains 21 fixed cases and requires a score-free source-compatibility audit next.
Do not compute endpoint ranks while building that audit; incompatible cases cannot be replaced
without a separately named successor protocol frozen before any metric output.

The committed manifest pins canonical SHA-256 digests of the exact taxonomy and row content used
to build each artifact. Canonicalisation excludes fetch timestamps and strips `mailto` and
`api_key` query parameters; neither personal identifiers nor credentials are part of a published
fingerprint.

Rebuild the current local inputs with:

```bash
python -m pipeline.ingest.fetch_taxonomy
python -m pipeline.ingest.fetch_cooccurrence --slice pre1986
```

Then verify and export with:

```bash
python -m pytest
python -m pipeline.export.build_artifacts
python -m pipeline.export.verify_artifacts
```

To clean credential-bearing provenance left by versions before the public/private URL split:

```bash
python -m pipeline.provenance
```

The PubMed cache retains citation and MeSH metadata only, never abstracts, request email addresses,
or API keys. It is maintained-current metadata and is not evidence of historical vocabulary state.
