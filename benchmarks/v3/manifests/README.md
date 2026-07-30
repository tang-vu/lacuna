# Historical MEDLINE release manifests

This directory is intentionally empty until NLM identifies an obtainable raw source. One generated
JSON manifest belongs here for each required baseline year. Large XML files stay in ignored local
pipeline state; their identities do not.

Build a manifest only after acquiring the complete release:

```bash
python -m pipeline.benchmark.build_release_manifest \
  --year 2010 \
  --base-url https://official-source.example/baseline/2010/ \
  --inventory-url https://official-source.example/baseline/2010/inventory \
  --inventory-file-count INVENTORY_FILE_COUNT \
  --inventory-total-bytes INVENTORY_TOTAL_BYTES \
  --inventory-total-record-count INVENTORY_TOTAL_RECORD_COUNT \
  --output benchmarks/v3/manifests/medline-2010.json \
  data/medline-baseline/2010/*.xml.gz
```

The command:

- refuses non-HTTPS source identities;
- sorts unique filenames;
- hashes the compressed transport bytes with SHA-256;
- streams every file and records its parsed `PubmedArticle` count;
- compares the measured file, transport-byte, and record totals with the independently transcribed
  official inventory totals before creating any output;
- creates, but never overwrites, the output manifest;
- prints a small reference containing the manifest checksum, measured aggregates, and inventory
  aggregates.

Review that reference, then add it to the historical-record source's `manifests` list in
`../sources.json`. Paths there are relative to `benchmarks/v3`, for example
`manifests/medline-2010.json`. `--inventory-url` must identify the official inventory or
preservation record used to decide that the acquired file set is complete. The three
`--inventory-*` totals must be transcribed from that source, not calculated from the downloaded
directory. This prevents a locally self-consistent subset that disagrees with the reviewed
inventory values from certifying itself as a complete release; the command does not fetch or parse
the remote inventory page.

`validate_sources` reloads every referenced manifest and reconciles its checksum, release year,
file count, compressed-byte total, record total, the independently recorded inventory totals,
unique filenames, URLs, and per-file checksums. The production reader then requires the complete
local file set described by that reviewed manifest. A local subset cannot inherit the
`pinned_historical_medline` label after the full manifest has been pinned.

Generated manifests are committed provenance, not hand-edited source data. If a value is wrong,
fix the acquisition input and rebuild to a new reviewed file rather than editing a count until the
validator passes.
