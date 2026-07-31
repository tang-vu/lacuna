# Changelog

All notable public changes to lacuna are recorded here. Scientific failures remain visible rather
than disappearing behind later versions.

## [Unreleased]

### Added

- An interactive evidence lab for searching, filtering, sorting, deep-linking, auditing, and
  exporting the 500 published outputs of the failed metric.
- A data-backed observatory hero that exposes the current method count, validated-gap-pair count,
  scored-pair count, and pinned artifact version without recasting measurements as findings.
- A metric-blind benchmark review desk exposing all 14 contract-validated intake records, evidence
  links, mapping limitations, open questions, status filters, search, and candidate deep links.

### Changed

- Replaced the static computed-pair table with compact evidence cards that keep exact counts,
  upper bounds, verification queries, source-row queries, and the failed verdict visually linked.
- Expanded the non-JavaScript fallback so crawlers and constrained clients can see what the
  evidence lab does and that its rows are not candidate discoveries.
- Advanced `project-status.json` to schema 2 so the contributor UI reads candidate records from the
  same validated, fingerprinted ledger as CI instead of maintaining a second presentation copy.

## [0.1.0] — 2026-07-31

First public release.

### Included

- Static, versioned OpenAlex artifacts with per-pair verification queries and pinned input hashes.
- Curated open, blocked, and coverage-blind-spot layers with source citations.
- Published negative results for metric v1 (cosine) and v2 (bridge-k).
- A pre-metric v3 benchmark contract, metric-blind candidate ledger, historical-source contract,
  streaming MEDLINE reader, and fixture-tested accumulators.
- A production static site at [lacuna.tangvu.dev](https://lacuna.tangvu.dev), including honest
  validation status, crawlable fallback content, crawler controls, structured metadata, social and
  install icons, and a contributor mission board generated from the validated v3 contracts.
- Contribution, citation, issue-form, and pull-request workflows for public collaboration.

### Scientific status

- Metric v2 ranks the canonical fish-oil/Raynaud pair at top 30.840% against a pre-registered top-5%
  minimum; the verdict is `FAIL`.
- Historical MEDLINE citation releases for 2007, 2011, 2012, and 2013 remain unavailable through a
  pinned source. Matching MeSH vocabularies are pinned but do not replace those records.
- The v3 benchmark remains a draft with 2 of 24 minimum cases and 0 of 12 required held-out cases.
- No metric v3 or LLM interpretation layer is included.

[0.1.0]: https://github.com/tang-vu/lacuna/releases/tag/v0.1.0
