# lacuna

A map of what humanity has not figured out yet.

## Product rule

The knowledge tree is scaffolding. The holes are the product. Do not improve the taxonomy UI at
the expense of gap detection, validation, or traceability.

## Current scientific status

- `open` and `blocked` are curated layers. Every entry must cite a source.
- `gap` is the computed layer and the core of the project.
- Metric v1 (cosine) and v2 (bridge-k) both failed the pre-registered Swanson reproduction.
- Never describe current computed pairs as discoveries, validated gaps, or hypotheses worth acting
  on. They are measurements from a failed method.
- Do not add the LLM interpretation layer until a replacement metric passes its pre-registered
  benchmark.
- Current PubMed/MeSH indexing is maintained to newer vocabularies. Never describe it as
  period-appropriate historical indexing; the official static baseline archive begins in 2002.
- The legacy MBR download endpoint is currently unavailable. Public production-year MeSH files do
  not substitute for the matching historical citation records; both source gates must be pinned.
- Historical metric v3 and BioASQ v2 are archived audit tracks; BioASQ v2 terminated on its
  development gate without held-out execution.
- The active replacement is `benchmarks/autonomous-prospective-v1.json`: a no-human prospective
  PubMed link-emergence benchmark. Its sealed 2026 T0 pins 1,334 official PubMed transports,
  39,994,988 parsed records, and the matching 31,110-descriptor MeSH transport. This closes only the
  source gate; the track remains not ready until a frozen metric, sealed predictions, and the
  three-release outcome window pass machine-verifiable gates.
- The score-free T0 construction has sealed 7,310,895 exhaustive exact-zero candidates from
  39,994,988 unique PMIDs. This is an exact maintained-current PubMed/MeSH count/index artifact
  with zero metric or scientific readiness.
- A pass on the active track validates only future PubMed MeSH link-emergence ranking. Never call it
  a validated knowledge-gap detector, autonomous scientific discovery, or evidence of absent
  human knowledge.

## Non-negotiables

- Keep measured, curated, and generated content structurally and visually distinct.
- Trace every exported number to its input query and label bounds as bounds.
- Treat validation tests as load-bearing. Investigate drift; do not update expected values merely
  to make a changed metric pass.
- Keep OpenAlex blind spots prominent: thin humanities and historical coverage, and absent craft,
  practitioner, indigenous, and other non-academic knowledge.
- Never persist API keys in caches, artifacts, logs, or error messages.
- Do not add human review, adjudication, or manual labels as an active-system dependency. Missing
  source, integrity, outcome, or power evidence must produce an explicit machine abstention.

## Commands

```bash
python -m pytest -m "not slow"
python -m pytest
python -m pipeline.export.validate_curated
python -m pipeline.benchmark.validate_sources
python -m pipeline.benchmark.source_inventories
python -m pipeline.benchmark.mbr_capture
python -m pipeline.benchmark.validate_source_alternatives
python -m pipeline.benchmark.autonomous_t0 audit
python -m pipeline.benchmark.autonomous_t0 audit-sealed
python -m pipeline.benchmark.autonomous_t0 download --help
python -m pipeline.benchmark.validate_autonomous_candidate_index
python -m pipeline.benchmark.validate_autonomous_candidate_universe
python -m pipeline.benchmark.autonomous_candidate_index --help
python -m pipeline.benchmark.autonomous_candidate_reduce --help
python -m pipeline.benchmark.validate_autonomous_prospective
python -m pipeline.benchmark.validate_candidates
python -m pipeline.benchmark.negative_controls
python -m pipeline.benchmark.validate_v3
python -m pipeline.export.build_artifacts
npm --prefix web run build
```

Use the repo skills for recurring workflows: `$validate`, `$gap`, and `$honest`.

## Working style

- Prefer static, versioned artifacts and boring technology suitable for one maintainer.
- Add tests before trusting a number.
- Keep generated data out of hand-edited source files.
- Keep large regenerable source corpora and transfer `.part` files off the system volume; use an
  ignored junction or symlink when code needs a stable repository-relative path.
- Update README status and provenance documentation when pipeline behavior changes.
- After each verified update group, commit it and push the current branch. Do not leave completed
  work uncommitted for a later session.
