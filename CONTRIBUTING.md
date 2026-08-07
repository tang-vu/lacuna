# Contributing to lacuna

lacuna is trying to compute holes in knowledge. Its first two metrics failed their pre-registered
test. Contributions are welcome, but a plausible-looking ranking is not evidence that the method
works.

Read `AGENTS.md` and the current status in `README.md` before changing code or data.

## Current campaign

The [Metric v3 readiness milestone](https://github.com/tang-vu/lacuna/milestone/1) keeps the
pre-metric work public:

- [recover complete historical MEDLINE baselines](https://github.com/tang-vu/lacuna/issues/6);
- [adjudicate the proposed positive-case queue](https://github.com/tang-vu/lacuna/issues/7);
- [build the hard-negative cohort](https://github.com/tang-vu/lacuna/issues/4);
- [build the distant-negative cohort](https://github.com/tang-vu/lacuna/issues/3).

Each issue has evidence and acceptance criteria. Comment before starting a large investigation so
parallel contributors do not repeat the same source search or adjudication.

## Where help matters most

### 1. Recover a historical MEDLINE baseline

Metric v3 needs complete 2007, 2011, 2012, and 2013 MEDLINE/PubMed baseline releases. The matching
MeSH vocabularies are pinned; the citation records are not obtainable from the retired endpoint
currently documented by the project.

Useful contributions identify a stable source or preservation record with:

- an official custodian or a documented provenance chain;
- the complete release inventory, not a convenient subset;
- stable file URLs plus compressed byte counts;
- checksums, or enough independent metadata to verify newly computed SHA-256 hashes;
- distribution terms that permit the project to process the files.

Do not upload licensed or unverified data to an issue. Use the
[historical-source issue form](https://github.com/tang-vu/lacuna/issues/new?template=historical-source.yml)
to submit a lead.

### 2. Review a benchmark case

The v3 benchmark needs positives, nearby hard negatives, and distant negatives selected before a
candidate formula sees the held-out set. A positive needs more than a later co-occurrence:

- a metric-blind selection source;
- a documented cutoff;
- a bridge or discovery publication;
- independent literature-based-discovery replication;
- period-appropriate MeSH mapping evidence, with ambiguity kept visible.

Proposed cases enter `benchmarks/v3/candidates.json`. They do not count toward readiness until
reviewed and accepted into `cases.json`. Start with the
[benchmark-case issue form](https://github.com/tang-vu/lacuna/issues/new?template=benchmark-case.yml).

For negative controls, begin with the generated queue in `artifacts/negative-candidates.json`
rather than choosing a pair after seeing a metric. The frozen protocol in
`benchmarks/v3/negative-selection.json` proposes ontology siblings and fixed cross-branch pairs
from pinned MeSH vocabularies. A proposal is not an accepted negative and contributes zero to
readiness. Reviewers should reject or replace generic, polysemous, or substantively related pairs
without inspecting any lacuna score, then document the rationale publicly in issue #4 or #3.

When accepting a negative into `benchmarks/v3/cases.json`, keep its generated
`selection_candidate_id`, cite the commit-pinned `artifacts/negative-candidates.json` permalink
with evidence role `negative_selection_source`, and cite the direct public issue-comment decision
with role `metric_blind_adjudication`. The validator reconciles the kind, proposed split, cutoff,
and both descriptor labels with the audited queue, so a hand-picked replacement cannot silently
inherit a pre-metric proposal's provenance.

After publishing the decision, generate the case fragment without retyping proposal identity,
split, cutoff, or descriptor fields:

```bash
python -m pipeline.benchmark.build_negative_case \
  --candidate-id generated-hard-2012-01-d001174-d014143 \
  --adjudication-url https://github.com/tang-vu/lacuna/issues/4#issuecomment-COMMENT_ID \
  --negative-rationale "Reviewer-authored rationale"
```

The command prints JSON and never edits `cases.json`. It verifies the frozen queue and direct issue
comment shape, but it does not verify the scientific judgment or turn an AI-generated rationale
into human adjudication. Review the fragment, append it to `cases.json`, and run both candidate and
v3 validators.

### 3. Propose a sourced hole

The public [hole atlas](https://lacuna.tangvu.dev/holes/) is generated from `curated/open.json`,
`curated/blocked.json`, and `curated/blind-spots.json`. Use the
[sourced-hole issue form](https://github.com/tang-vu/lacuna/issues/new?template=curated-hole.yml)
instead of editing generated pages.

An open question needs evidence that a field explicitly treats it as unanswered. A blocked
question needs a well-posed target and a documented instrumentation, cost, ethics, or timescale
constraint. A coverage blind spot must describe what lacuna's source or method cannot see; missing
OpenAlex literature is not evidence that human knowledge is absent. Keep measured numbers separate
from the written summary and cite every public claim.

### 4. Improve the pipeline

Good engineering contributions strengthen provenance, source validation, bounded-count handling,
streaming performance, accessibility, or reproducibility. Do not implement or tune a v3 scoring
formula before the benchmark and historical-source gates are ready.

For a bug, include the smallest reproducible input and explain whether it could change a published
number or scientific status.

## Development workflow

```bash
pip install -e ".[dev]"
npm --prefix web ci

python -m pytest -m "not slow"
python -m pipeline.export.validate_curated
python -m pipeline.benchmark.validate_sources
python -m pipeline.benchmark.validate_candidates
python -m pipeline.benchmark.negative_controls
python -m pipeline.benchmark.validate_v3
python -m pipeline.export.verify_artifacts
npm --prefix web run build
```

If `data/cooccurrence/pre1986/` exists, run the full slow suite and Swanson report:

```bash
python -m pytest
python -m pipeline.validate.validate_swanson
```

The `--require-ready` source and v3 commands are intentionally red while their documented blockers
remain. Never weaken a gate or update an expected value merely to make a check green.

## Data and claim rules

- Never commit API keys, account emails, access tokens, or credential-bearing URLs.
- Generated data stays out of hand-edited source files.
- Curated entries cite a source; generated prose never inherits the authority of measured data.
- Bounds remain labelled as bounds.
- Current PubMed indexing is not a period-appropriate historical snapshot.
- OpenAlex cannot establish the absence of craft, practitioner, indigenous, or other non-academic
  knowledge.
- The current computed pairs are outputs of a failed method, not discoveries or actionable
  hypotheses.

## Pull requests

Keep one verified change group per pull request. Include:

- the problem and why it matters scientifically;
- the provenance of every new number or curated claim;
- tests added or changed;
- every validation command run and every gate skipped;
- screenshots for visible UI changes;
- an explicit note if the scientific status did not change.

By contributing, you agree that your contribution is licensed under the repository's MIT License.
