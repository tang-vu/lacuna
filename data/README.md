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
