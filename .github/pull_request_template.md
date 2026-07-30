## What changed

<!-- Describe the smallest coherent change and why it belongs in lacuna. -->

## Evidence

<!-- Link sources, input queries, fixtures, or before/after outputs. Write "not applicable" only when this change makes no scientific or numeric claim. -->

## Scientific status

- [ ] This change keeps measured, curated, and generated content distinct.
- [ ] It does not present v1/v2 output as a discovery, validated gap, or actionable hypothesis.
- [ ] It does not present the v3 draft as ready or current PubMed/MeSH indexing as historical.
- [ ] Every new number is traceable to an input query; bounds are labelled as bounds.
- [ ] No API key or restricted source data is included.

## Verification

<!-- Paste the commands you ran and summarize their results, including every skipped or expected-failing gate. -->

- [ ] `python -m pytest -m "not slow"`
- [ ] `python -m pipeline.export.validate_curated`
- [ ] Relevant benchmark validators
- [ ] `python -m pipeline.export.build_artifacts`
- [ ] `npm --prefix web run build`

## Review focus

<!-- Point reviewers to the highest-risk assumption or line. -->
