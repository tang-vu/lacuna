# lacuna

[![CI](https://github.com/tang-vu/lacuna/actions/workflows/ci.yml/badge.svg)](https://github.com/tang-vu/lacuna/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/tang-vu/lacuna?display_name=tag)](https://github.com/tang-vu/lacuna/releases/latest)
[![Live map](https://img.shields.io/badge/live-lacuna.tangvu.dev-1d4e73)](https://lacuna.tangvu.dev)
[![License: MIT](https://img.shields.io/badge/license-MIT-8a3d12.svg)](LICENSE)

A map of what humanity hasn't figured out yet.

Most knowledge maps show what we know. lacuna tries to show where knowledge stops. The knowledge
tree is scaffolding — the holes are the product.

**Status: the computed layer does not work yet, and this README says so before it says anything
else.** The method lacuna was built around failed the test it was pre-registered against. The
curated layers work, the pipeline works, and the negative result is published rather than buried.
Details in [the validation report](plans/reports/validation-260727-1140-swanson-reproduction-negative-result-report.md).

---

## Three kinds of hole

| kind | what it is | how it's found |
|---|---|---|
| `open` | A question a field has explicitly acknowledged it cannot answer — the Riemann hypothesis, P vs NP, the hard problem of consciousness. | Curated. Every entry must cite a source. |
| `blocked` | A well-posed question nobody is short of ideas about, stopped by an instrument, a cost, an ethical limit, or a timescale. | Curated, tagged with the blocker. |
| `gap` | Two areas of research that should probably have met and never did. | **Computed. This is the part that doesn't work yet.** |

The `gap` layer was the reason to build this: it can be computed rather than hand-written, so it
can find things nobody thought to write down. That is also why its failure is the headline.

---

## The evidence lab

The [live map](https://lacuna.tangvu.dev/#computed) includes an interactive lab for auditing the
failed metric rather than hiding its output:

- search all 500 exported measurements by topic name or OpenAlex topic ID;
- separate exact counts from API-derived upper bounds;
- sort by original metric rank, observed/expected ratio, or structural closeness;
- open the pair query and both source-row queries behind any measurement;
- copy a deep link to one pair or export the current filtered view as CSV.

The validation verdict renders before the controls and every card. Searchability does not promote
these rows into candidate discoveries; it makes a negative result easier to inspect and falsify.

---

## The shareable hole atlas

Every curated open question, blocked question, and declared blind spot has a canonical page under
[`/holes/`](https://lacuna.tangvu.dev/holes/). The production build generates those pages directly
from the validated, versioned curated artifact rather than maintaining a second copy of the text.
Each page works without JavaScript, exposes its sources and provenance label, carries distinct
Open Graph/Twitter metadata, and links back to the exact card in the full map.

The sitemap is generated from the same artifact. Computed pairs are deliberately excluded: the
current method failed validation, so social previews and search landing pages must not recast its
measurements as discoveries. A sourced-hole issue form lets readers propose additions while
requiring evidence and preserving the boundary between absent academic coverage and absent human
knowledge.

---

## What the gap metric tries to do, in plain English

In 1986 Don Swanson noticed that papers on fish oil described effects on blood — lower viscosity,
less platelet aggregation — and, separately, papers on Raynaud's syndrome described patients whose
blood had exactly those problems. Neither literature cited the other. Nobody had written the
sentence "fish oil might help Raynaud's". The connection was sitting in public, unassembled.
Clinical trials later supported it.

lacuna looks for that shape at scale. For every pair of research topics it asks two questions:

1. **Do they meet?** Count papers filed under both. Compare that to how many you would expect if
   topics were assigned independently — two topics covering 1% of the literature each should share
   about 0.01% of it. Far fewer than expected means they don't meet.
2. **Do they keep the same company?** Find topics that both associate strongly with. If A and C
   both connect to the same intermediates but never to each other, that is Swanson's shape.

A gap is a pair scoring high on **both**. Distance alone is not interesting — most pairs are
unrelated. Closeness alone is just similarity, which other tools already do well.

### What actually happened

On pre-1986 data the fish oil / Raynaud's pair scored **top 30.8%** of pairs. The bar, fixed in
advance, was top 5%. Two different designs for question 2 both failed.

Question 1 worked perfectly. Before 1986 the two topics appeared together in **zero** papers where
chance predicts about 21 — odds of roughly 1 in 1.5 billion. The bridge then genuinely formed
afterwards, 0 papers becoming 9. The gap was real, it was measurable, and it closed.

Question 2 is what breaks. "Keeps similar company but rarely co-occurs" turns out to describe, for
the most part, **adjacent clinical specialties that split papers between them** — bladder cancer
versus renal cancer, appendicitis versus gastrointestinal tumours. A paper goes to one topic or the
other, rarely both, so they look like a gap without anything being undiscovered. The metric measures
how OpenAlex partitions subject matter, not where knowledge stops.

Swanson worked with individual MeSH terms inside a curated vocabulary where terms are not
alternative labels for one another. OpenAlex topics are not that, and that difference appears to be
the whole problem.

---

## Non-negotiables

- **Measured and written content stay visually and structurally distinct**, everywhere. Numbers
  render in monospace and tinted; human-written entries in body text with citations. Nothing that
  came out of a model inherits the authority of a measurement.
- **Every computed number traces back to runnable queries and pinned inputs.** Each exported pair
  carries the two row queries behind its measured or bounded count plus a targeted query that can
  resolve the exact count. The manifest pins canonical content digests for the taxonomy,
  co-occurrence rows, and exported files. A number a reader cannot check is decoration.
- **The validation tests are load-bearing.** They pin the measured outcome including the failure.
  If a change makes the target pair suddenly rank well, that is a reason to investigate, not to
  celebrate — see `tests/test_swanson_validation.py`.
- **OpenAlex covers academic publishing only.** Humanities reference linkage runs ~70% against ~95%
  for STEM; pre-1970 literature thins out sharply; craft, practitioner and indigenous knowledge are
  absent entirely. Those blind spots are entries in the map, not footnotes under it.

---

## Running it

```bash
pip install -e ".[dev]"

python -m pipeline.ingest.fetch_taxonomy                      # ~31 calls, asserts 4/26/252/4516
python -m pipeline.ingest.fetch_cooccurrence --slice pre1986  # resumable; re-run to continue
python -m pipeline.validate.validate_swanson                  # the pre-registered test
python -m pipeline.export.build_artifacts                     # writes artifacts/{date}/
python -m pipeline.export.build_project_status                # writes contributor gate status
python -m pipeline.export.verify_artifacts                    # checks committed file digests

cd web && npm install && npm run dev
```

`fetch_cooccurrence` needs one request per topic and the free tier allows about 1,000 credits a
day, so a full 1,458-topic sweep spans two days. It resumes where it stopped; just run it again.
Setting `OPENALEX_API_KEY` is reported to raise the ceiling substantially — **unverified**, and the
research that claimed it was wrong by 10× about the anonymous limit.

`OPENALEX_MAILTO` is optional and identifies a local run to OpenAlex. It is used only on requests;
credentials and email addresses are stripped from cached provenance and published artifacts.

Tests:

```bash
python -m pytest -m "not slow"   # unit tests, under a second
python -m pytest                 # adds regression tests over a fetched sweep; minutes
```

Inspect one fetched pair without allocating the full ranking:

```bash
python -m pipeline.inspect_gap "Fatty Acid Research" "Systemic Sclerosis"
```

This command deliberately produces no hypothesis. The current metric failed validation, so its
output is diagnostic evidence only.

Install the repository hook after installing development dependencies:

```bash
pre-commit install
```

It runs the fast Python suite and TypeScript typecheck before each commit. GitHub Actions runs the
tests available in a clean clone, curated-content validation, committed-artifact integrity, and
the production web build on pushes and pull requests. The five slow regression tests require the
gitignored fetched sweep and therefore run locally through `$validate`; CI does not represent them
as having passed.

---

## How it's built

```
pipeline/
  openalex_client.py      cached, resumable, records the URL behind every response
  ingest/                 taxonomy and co-occurrence sweeps
  metric/gap_score.py     both metric versions; the failed one is kept deliberately
  validate/               the pre-registered test
  export/                 versioned static artifacts + curated content validation
curated/                  open.json, blocked.json, blind-spots.json
artifacts/{snapshot}/{metric-version}/  what the site reads; no backend
artifacts/project-status.json           generated v3 source/benchmark gate status
web/                      TypeScript, static build
docs/metric-validation-preregistration.md    criteria, committed before any score existed
```

One request returns a whole row of the co-occurrence matrix, because OpenAlex lets `filter` and
`group_by` compose. That makes a full topic-level matrix 4,516 requests instead of a 400 GB
snapshot download — the single most useful thing discovered while building this.

## Codex workflows

Persistent project rules live in `AGENTS.md`. Repeatable workflows are repository skills:

- `$validate` runs every available validation gate and reports skips or drift.
- `$gap` inspects one topic pair and prints raw evidence and source queries.
- `$honest` audits the latest change for a claim that outruns its evidence.

## Contributing

The highest-impact contributions are historical MEDLINE source leads, metric-blind benchmark-case
review, and provenance or validation engineering. Read [`CONTRIBUTING.md`](CONTRIBUTING.md) before
opening an issue: a vocabulary file is not a historical citation baseline, and a plausible pair is
not automatically a positive case. The live site's **Open work** board is generated from
`artifacts/project-status.json`; its counts and contract fingerprints are rebuilt from the same
validators used by CI rather than maintained as website copy.

The interpretation layer remains gated off. The proposed replacement experiment is documented in
[`plans/metric-v3-validation-plan.md`](plans/metric-v3-validation-plan.md); it moves the biomedical
pilot to period-appropriate MeSH terms and a multi-case held-out benchmark rather than tuning a
third formula on the canonical pair. Its
[`benchmarks/v3/cases.json`](benchmarks/v3/cases.json) contract is deliberately still a draft:
2/8 positives, 0/8 hard negatives, 0/8 distant negatives, and no eligible held-out cutoff. Run
`python -m pipeline.benchmark.validate_v3` to see the blockers; only `--require-ready` is a
shipping gate. `pipeline.pubmed_client` can batch citation/MeSH metadata for mapping audits, but its
output is explicitly maintained-current and cannot satisfy the historical-indexing gate.
Potential positive cases first enter the separate
[`benchmarks/v3/candidates.json`](benchmarks/v3/candidates.json) ledger. Its five proposed cases
from the classic replication catalog, five proposed post-2002 cases from LION's nominal cancer
set, and two rejected noise examples do not count toward readiness; only accepted entries with an
independent LBD replication may be copied into `cases.json`. Run
`python -m pipeline.benchmark.validate_candidates` to audit that boundary.
Negative controls have a separate, frozen selection protocol in
[`benchmarks/v3/negative-selection.json`](benchmarks/v3/negative-selection.json). Its deterministic
sampler uses only pinned 2012 and 2013 MeSH tree structure and a fixed pre-metric seed to propose
8 ontology-adjacent hard negatives and 8 cross-branch distant negatives. Run
`python -m pipeline.benchmark.negative_controls --build` to reproduce
[`artifacts/negative-candidates.json`](artifacts/negative-candidates.json), or omit `--build` to
validate the committed queue. All 16 records are generated review proposals: they contribute zero
to readiness, assert no absence of knowledge, and cannot enter `cases.json` without public,
metric-blind human adjudication. An accepted negative must preserve its generated proposal ID and
direct public issue-comment decision; `validate_v3` audits the commit-pinned frozen queue and
rejects any case whose kind, split, cutoff, or descriptor identity drifts from that proposal.
Negative controls do not duplicate records in the positive-case intake ledger, so they do not
inherit its bridge-publication and independent-replication requirements.
`python -m pipeline.benchmark.negative_review_context --build` derives a separate, checksum-pinned
review aid from the 2012 and 2013 MeSH archives. It adds official scope notes, entry terms, tree
paths, and hard-negative parent labels to the public review desk while contributing zero readiness
and making no adjudication decision.
The live **Metric-blind review desk** publishes all 14 contract-validated intake records directly
from that ledger, including their evidence links, mapping limitations, adjudication rationale, and
unresolved questions. Structural validity is not scientific acceptance: it defaults to the ten
proposed records and labels each one as contributing zero to readiness; accepted and rejected
records remain visible as the audit trail. Deep links let reviewers discuss one stable candidate
identity in issue #7 without duplicating the source data.
The historical-input gate is also red: NLM's legacy MBR download endpoint no longer resolves, and
NLM Support confirmed on 2026-08-10 that previous-year baseline files are not available through its
present distribution service. The repository records a dated public-safe summary without personal
case or tracking identifiers. This establishes NLM's distribution position, not that no third-party
preservation copy exists. The official NLM file inventories are now recovered for all four required
releases—archived snapshots
for 2007 and 2011, plus the live 2012 and 2013 pages—and pinned in
[`benchmarks/v3/inventories.json`](benchmarks/v3/inventories.json). Run
`python -m pipeline.benchmark.source_inventories --probe --require-match` to fetch every page, sum
every file-size row, and fail on drift. This is completeness metadata only: it establishes targets
of 538, 653, 684, and 717 files, but supplies neither the raw XML nor per-file checksums. The
retired MBR homepage itself is now preserved as a digest-addressed Common Crawl WARC range in
[`benchmarks/v3/mbr-capture.json`](benchmarks/v3/mbr-capture.json). It independently confirms the
historical `Download/Baselines/{year}` directory rows and the same release totals. Run
`python -m pipeline.benchmark.mbr_capture --probe --require-match` to check the index record and
independently replay the exact compressed WARC range, verify its payload digest, and parse those
rows. A transient index outage no longer prevents the pinned WARC from being audited, but the
strict command still exits non-zero unless both components match. This is repository metadata
only: no required XML payload was recovered, and an unreachable preservation service is reported
as reachability failure rather than data drift.
The required MeSH descriptor archives are separately pinned by SHA-256, and that vocabulary also does
not replace the missing citation records. `benchmarks/v3/sources.json` records the dated
observation; `python -m pipeline.benchmark.validate_sources --require-ready` must keep failing until
the matching historical records have stable URLs and checksums. The streaming
baseline reader and targeted pair/ABC accumulator are implemented and fixture-tested, but their
production entry point is deliberately closed: it accepts a baseline only when every local file
matches the complete pinned release by filename, byte count, and SHA-256. Release-manifest
generation also requires measured file, byte, and record totals to match independently recorded
official-inventory totals, so a local subset that disagrees with the reviewed inventory values
cannot self-certify.

Source redesign is explicit rather than hidden inside that failed recovery path.
[`benchmarks/v3/source-alternatives.json`](benchmarks/v3/source-alternatives.json) records three
reviewed routes and gives all of them zero readiness contribution. The registered BioASQ Task 1a
version 2013 payload is now acquired locally and pinned by the generated
[`bioasq-2013-task-a.json`](benchmarks/v3/manifests/bioasq-2013-task-a.json) audit. All three catalog
aggregates match: 10,876,004 articles, 26,563 distinct labels, and 136,439,656 assignments or
12.54501709 per article, which rounds to the published 12.55. The declared publication scope does
not match: 280 records date to 1946-1949. All publication years are parseable, although 751,238
values require an explicit non-`YYYY` normalization rule. This secondary
corpus is not the complete 21,508,439-record NLM baseline. A checksum-pinned five-record public
sample gives bounded evidence that `meshMajor`
behaves like all assigned descriptors rather than only major-topic headings: 71/72 assignments
match maintained-current PubMed descriptors, while 9/72 match current `MajorTopicYN=Y` headings.
That is a schema observation, not a corpus-wide or period-appropriate validation. Before seeing the
registered payload, the repository froze a 416-record SHA-256 bottom-k protocol across eight
publication-year strata, including the 2006/2010/2011/2012 candidate cutoffs. It requires every
sampled PMID to return and never inspects a gap score. Run
`python -m pipeline.benchmark.validate_source_alternatives` to audit that boundary. Because the
measured payload contains records outside the protocol's 1950-2013 strata, the strict selector
cannot run it unchanged. That protocol remains immutable. A separately named
`bioasq-semantics-protocol-v2.json` is now frozen after source audit and before semantics selection.
It adds a 32-record 1946-1949 stratum, preserves all 416 allocations and thresholds from v1, and
raises the total to 448 without inspecting a PMID selection or new PubMed response. The subsequently
checksum-pinned bounded audit returned all 448 records: 5,201 of 5,296 assignments match
maintained-current PubMed descriptors, while 455 match current `MajorTopicYN=Y` headings. The
all-descriptor fraction is 0.98206193, the major-topic fraction is 0.0859139, and all-descriptor
matching exceeds major-topic matching in all nine strata, so the sample follows the frozen
`sample_consistent_with_all_assigned_descriptors` classification. This balanced sample is not a
population estimate, historical indexing reconstruction, or completeness result. The full source
audit status remains `measured_unmatched_input`; the
`--require-declared-match` command is expected to fail. Readiness remains zero.

The next experiment is now frozen separately in `benchmarks/v3/bioasq-pilot.json`, before any
BioASQ endpoint-support count, pilot formula, score, or rank was inspected. It includes the complete
five-case LION Cancer Discovery population plus all sixteen metric-blind structural-control
proposals: 11 development and 10 held-out cases. The positive held-out split is deterministic
SHA-256 bottom-2. The first gate is score-free source compatibility for all 21 cases; an
incompatible endpoint makes the pilot inconclusive and cannot be silently replaced. Even a later
passing pilot label contributes zero metric-v3 readiness and is not discovery validation.

## Deployment

The static site is deployed from `main` by the Git-integrated Cloudflare Pages project `lacuna`.
Cloudflare builds from the repository root with:

```bash
npm --prefix web ci && npm --prefix web run build
```

The published directory is `web/dist`; Vite copies the committed, versioned artifacts into that
directory without reshaping their contents. The production site is
[`lacuna.tangvu.dev`](https://lacuna.tangvu.dev); its Cloudflare Pages origin is
[`lacuna-a2y.pages.dev`](https://lacuna-a2y.pages.dev).

The build also publishes a root sitemap, permissive `robots.txt`, a real noindex 404 page, social
preview metadata, JSON-LD, and the favicon/install-icon set from `web/public`. The initial HTML
contains an honest, number-free account of the method status and known coverage limits, so that
crawlers and readers without JavaScript do not receive an empty loading shell.

Search-engine ownership tokens are intentionally not committed. Set either optional Cloudflare
Pages build variable to inject its verification meta tag at build time:

```text
GOOGLE_SITE_VERIFICATION=<Search Console HTML-tag token>
BING_SITE_VERIFICATION=<Bing Webmaster Tools meta-tag token>
```

After ownership is verified, submit `https://lacuna.tangvu.dev/sitemap.xml` in the relevant
webmaster console. The sitemap contains the canonical homepage, the generated hole-atlas index,
and one page per curated entry. Hash sections, failed-metric pair views, and versioned JSON evidence
files are not separate search landing pages.

## Licence

Code is released under the [MIT License](LICENSE). Data from [OpenAlex](https://openalex.org) is
CC0.
