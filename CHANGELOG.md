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
- A fingerprinted four-release NLM inventory contract and live drift probe for the 2007, 2011,
  2012, and 2013 MEDLINE completeness targets.
- A frozen, metric-blind sampler and public review queue for 8 hard-negative and 8 distant-negative
  proposals, split evenly between development and held-out review while contributing zero readiness.
- A digest-addressed Common Crawl WARC contract and replay probe for the retired MBR homepage,
  preserving all four required repository directory rows without treating metadata as raw records.
- Independent live checks for the Common Crawl index and pinned WARC byte range, so an index outage
  no longer suppresses payload-integrity evidence.
- A build-time hole atlas with one canonical, crawlable, social-shareable page per curated open
  question, blocked question, and declared blind spot, generated from the versioned artifact.
- A sourced-hole issue form and share actions that turn a public hole page into a guarded
  contribution path without routing failed computed pairs into the curated layers.

### Changed

- Replaced the static computed-pair table with compact evidence cards that keep exact counts,
  upper bounds, verification queries, source-row queries, and the failed verdict visually linked.
- Expanded the non-JavaScript fallback so crawlers and constrained clients can see what the
  evidence lab does and that its rows are not candidate discoveries.
- Advanced `project-status.json` to schema 2 so the contributor UI reads candidate records from the
  same validated, fingerprinted ledger as CI instead of maintaining a second presentation copy.
- Advanced `project-status.json` to schema 3 so the source-recovery mission distinguishes 4/4
  official inventories from 0/4 pinned raw citation releases.
- Advanced `project-status.json` to schema 4 so generated negative-control proposals and their
  frozen selection contract are independently fingerprinted and visibly separate from accepted cases.
- Advanced `project-status.json` to schema 5 so preserved MBR directory metadata remains visible
  and fingerprinted beside the still-empty raw-record gate.
- Bound every future accepted negative case to an audited, commit-pinned queue proposal and a
  direct public metric-blind adjudication, rejecting drift in kind, split, cutoff, or descriptor
  identity.
- Generate the production sitemap from the curated artifact so it covers the hole atlas and every
  canonical hole page while excluding failed-metric pair URLs.

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
