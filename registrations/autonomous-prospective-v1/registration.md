# Registration of a sealed 2026 protocol and T0 prediction state for prospective PubMed/MeSH link-emergence ranking

## Registration status and timing

This document records a protocol, candidate universe, metric, and prediction ordering that were
already public and sealed before this registration packet was prepared. It is therefore a
registration of prior sealed state, not a claim of prospective preregistration made today.

The protocol first appeared in repository commit `c22f05c9` on 2026-08-12. The complete official
2026 T0 source was sealed in `dea380e`; the score-free candidate-index contract in `47f26d7`; the
candidate universe in `ac88302`; the metric contract in `82bdeda`; and the complete prediction
ordering in `0f3f844`, all before any T1 outcome source existed. The source-pinned monthly release
watcher was added in `31eed12` on 2026-08-24. The protocol edits through `0f3f844` linked the sealed
artifacts and updated state; they did not replace the registered evaluation rules.

## Purpose

The experiment asks one narrow question: does a frozen, score-based ordering predict future direct
PubMed MeSH link emergence better than registered prevalence and structural baselines? It does not
test whether a pair is scientifically true, important, causal, novel to humanity, or absent from
academic or non-academic knowledge.

## T0 source and candidate construction

The sealed T0 input consists of 1,334 official 2026 PubMed baseline transports containing
39,994,988 distinct parsed PMIDs and the matching official MeSH transport containing 31,110
descriptors. Source URLs, filenames, byte lengths, SHA-256 values, record counts, and vocabulary
identity are pinned in the registered records.

Candidate construction was exhaustive and score-free. Eligible unordered descriptor pairs had at
least 100 T0 articles at each endpoint, an independence expected count of at least 5, and an exact
direct T0 count of zero. Identical, ancestor-descendant, and shared-entry-term pairs were excluded.
This produced 7,310,895 candidates. Zero sampling and zero human or LLM labels were used.

An exact-zero count is a maintained-current PubMed/MeSH database measurement. It is not evidence
that knowledge or a relationship is absent, including from craft, practitioner, indigenous,
historical, humanities, or other non-indexed sources.

## Frozen metric and predictions

`autonomous-prospective-metric-v1` is an unvalidated Adamic-Adar Q48 link-ranking formula. It was
frozen before any candidate score. Its source, parameters, dependency lock, candidate stream, and
total-order tie policy are hash-pinned. The sealed run produced one score and one deterministic
position for each of 7,310,895 candidates; 7,310,826 scores were nonzero. Overwrite and post-seal
formula revision are forbidden.

The seal proves computation and ordering integrity only. It contributes zero scientific readiness
and does not make any ranked pair a discovery, a validated gap, or a hypothesis worth acting on.

## Outcomes and evaluation

The watcher accepts only the next sequential official annual PubMed/MeSH release identities. The
outcome window requires three releases after T0. Missing, partial, out-of-order, or conflicting
source evidence causes machine abstention.

A positive outcome requires at least three distinct newly observed co-indexed PMIDs across at least
two journals and two publication years. A pair with no newly observed co-indexed PMID is labelled
only as having no observed link emergence in this window. One or two PMIDs, ambiguous descriptor
mapping, source reconciliation failures, and qualifying retractions are censored under the frozen
rules. Exact source rows and PMIDs must be retained.

The primary gates require at least 200 positive and 20,000 negative outcomes, precision at 100 of
at least 0.25, precision-at-100 lift over prevalence of at least 5, average-precision lift over
prevalence of at least 3, and a bootstrap 95% lower bound on precision lift of at least 2 using
10,000 registered replicates. Registered structural diagnostics must also pass. Every gate passes
for a pass; any evaluable metric or diagnostic gate failure is terminal for this formula; missing
source, integrity, outcome, or power evidence produces abstention without manual override.

Even a future pass would validate only prospective PubMed/MeSH link-emergence ranking. It would not
validate a general knowledge-gap detector or autonomous scientific discovery.

## Current state on 2026-08-25

The state is `predictions_sealed_waiting_for_outcome`; the verdict is `not_ready`; readiness
contribution is zero. The only current blocker is that the three-release prospective outcome window
has not matured. Validated knowledge-gap pairs: zero. No T1 outcomes have been inspected.

The earlier OpenAlex cosine and bridge-k metrics failed their pre-registered Swanson reproduction.
They remain negative results, separate from this prospective track. The evidence-v1 association
track is also separate and does not validate this metric or its candidates.

## Materials, integrity, and availability

The public repository contains the machine-readable protocol, all small source and seal manifests,
validation commands, tests, and automatic abstention logic. `manifest.json` in this packet provides
raw-byte SHA-256 values and byte lengths for the uploaded records. The large, regenerable source
corpus and prediction binaries remain off-repository; their exact identities and content hashes are
pinned in the uploaded records. Full byte-level replay requires those pinned files.

Repository: https://github.com/tang-vu/lacuna

Version archive: **pending publication of the Zenodo-backed v0.2.0 release; do not submit this OSF
registration until the DOI and archive URL are inserted here.**

## Ethics, automation, and AI disclosure

This benchmark analyzes public bibliographic metadata; it does not recruit participants or make
clinical decisions. The active benchmark has no human review, adjudication, or manual-label
dependency. Its ranking and outcome rules prohibit human or LLM scoring, filtering, or labelling.

OpenAI Codex assisted with preparing this registration narrative and its manifest generator on
2026-08-25. That assistance did not alter the already sealed T0 scores or ordering. The author is
responsible for checking the submitted text and for disclosing any additional tool use required by
the selected venue.
