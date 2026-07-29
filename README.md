# lacuna

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

The interpretation layer remains gated off. The proposed replacement experiment is documented in
[`plans/metric-v3-validation-plan.md`](plans/metric-v3-validation-plan.md); it moves the biomedical
pilot to period-appropriate MeSH terms and a multi-case held-out benchmark rather than tuning a
third formula on the canonical pair. Its
[`benchmarks/v3/cases.json`](benchmarks/v3/cases.json) contract is deliberately still a draft:
2/8 positives, 0/8 hard negatives, 0/8 distant negatives, and no eligible held-out cutoff. Run
`python -m pipeline.benchmark.validate_v3` to see the blockers; only `--require-ready` is a
shipping gate. `pipeline.pubmed_client` can batch citation/MeSH metadata for mapping audits, but its
output is explicitly maintained-current and cannot satisfy the historical-indexing gate.

## Licence

Code is released under the [MIT License](LICENSE). Data from [OpenAlex](https://openalex.org) is
CC0.
