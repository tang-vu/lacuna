# Pre-registration: gap metric validation

**Written 2026-07-27, before any gap score was computed.** Committed before the co-occurrence
sweep finished, so the thresholds below cannot have been fitted to the results.

The point of this file is to remove the author's freedom to decide what counts as success after
seeing the numbers. Literature-based discovery has a long history of retrospective narration —
finding a link, then explaining why finding it was the goal. If the criteria here are not met,
the honest output is a negative result, not a redefinition of "met".

---

## Hypothesis under test

At **topic** granularity (4,516 OpenAlex topics), a Swanson-style ABC metric computed on
pre-1986 literature ranks the pair

- `T11330` — Systemic Sclerosis and Related Diseases *(carries the Raynaud's literature)*
- `T10387` — Fatty Acid Research and Health *(carries the fish-oil / EPA literature)*

highly among biomedical topic pairs.

These two topics were identified by grouping pre-1986 free-text searches for `raynaud` and
`eicosapentaenoic OR "fish oil"` by topic, and taking the dominant topic of each. Both are the
clear mode of their literature (336/2,437 and 448/2,931 works respectively) and they do not
overlap in either literature's top eight.

**This assumption already failed one level up.** At *subfield* granularity the two literatures
share two of their top five subfields, so the canonical gap is not detectable there at all. Topics
are 18× finer, but Swanson worked at the level of individual MeSH terms, finer still. There may be
no level in OpenAlex's taxonomy at which this reproduces.

---

## Analysis set

- **S** = all topics in domain 1 (Life Sciences) and domain 4 (Health Sciences) — 1,458 topics.
  Chosen as a whole-domain rule, not fitted around the target pair. Rationale: the canonical LBD
  results are biomedical, and Swanson's bridging concepts (blood viscosity, platelet aggregation)
  are physiological, so Life Sciences must be included alongside Health Sciences.
- **Columns are not restricted.** Association vectors span all 4,516 topics, so bridge topics
  outside S still contribute. Only the *scored pairs* are limited to S × S.
- If the sweep is incomplete at analysis time, S is whichever subset was fetched, and the report
  must state N explicitly. The pass criterion is a percentile, so it is robust to N.

## Time slice

`to_publication_date:1985-12-31` — 38,458,832 works.

**Known defect, stated up front:** OpenAlex topics are assigned by a model trained on the modern
corpus and applied retroactively. This filter does not reconstruct the 1986 literature; it projects
today's ontology backwards onto it. Swanson used 1986's MeSH indexing. A pass here is therefore
weaker evidence than a true replication would be, and must never be described as one.

## Metric

```
e_ij  = s_i · s_j / N                         expected co-occurrence under independence
D_ij  = P(X ≤ c_ij), X ~ Hypergeometric(N, s_i, s_j)      deficit significance
a_i   = association vector of topic i over all 4,516 topics
S_ij  = cosine(a_i, a_j), with components i and j masked out
GapScore_ij = S_ij · (1 − D_ij_normalised)
```

Masking components i and j from the cosine is required, not cosmetic: without it the "closeness"
signal partly consists of the co-occurrence whose absence is the claim.

Guards, applied before ranking:
- `s_i, s_j ≥ 1000` works in the slice
- `e_ij ≥ 5` — below this a deficit is unmeasurable; the pair is dropped, not scored as a gap
- generalist topics excluded by a data-driven rule (see below), not a hand-picked list

**Generalist exclusion.** OpenAlex's classifier dumps poorly-described works into a handful of
topics — `T14423` Military Technology holds 22.3M works (7% of the corpus), `T10346` Magnetic
confinement fusion 9.3M, `T13370` "Diverse Scientific and Economic Studies" 5.1M. These co-occur
near-uniformly with everything and would dominate every association vector. The exclusion rule is
stated in code as a threshold on the *entropy of the normalised association vector* — a behavioural
test, so it catches dumping grounds without anyone choosing which topics to dislike. The excluded
list is published with the artifact.

---

## Pass criteria — fixed in advance

Percentile of the target pair's GapScore among all eligible scored pairs in S × S:

| Result | Criterion | Consequence |
|---|---|---|
| **STRONG PASS** | top 0.1% | Metric ships as-is |
| **PASS** | top 1% | Metric ships, labelled exploratory |
| **WEAK** | top 5% | Ships only with the negative-control and audit results published beside it |
| **FAIL** | below top 5% | Computed layer does **not** ship as a discovery tool. Publish the negative result. |

## Negative control — must also hold

Pairs that are semantically unrelated must **not** score highly. Sampled pairs crossing
domain 2 (Social Sciences) × domain 3 (Physical Sciences) with no plausible bridge — e.g. medieval
literature × semiconductor fabrication — must fall **below the 50th percentile**. A metric that
ranks everything highly has discovered nothing.

If the target pair passes *and* the negative controls also score highly, the result is a FAIL:
it means the metric is ranking on topic size or vector density, not on structure.

## Third test — bridges built after the slice

Pairs where a bridge genuinely formed later (machine learning × protein structure, bridged around
2020) must score highly on a pre-2015 slice. Deferred: each additional time slice costs a full
sweep (1,458 calls at ~930/day). Runs after the primary test resolves.

## Manual audit threshold

For a random — explicitly not cherry-picked — sample of 30 top-ranked gaps from the current-era
artifact, checked against Google Scholar for existing bridging literature:

- **≥50%** with no substantive bridging literature → metric validated as a gap detector
- **30–50%** → ships labelled low-precision and exploratory
- **<30%** → the metric is measuring OpenAlex's indexing artifacts rather than holes in knowledge,
  and the computed layer does not ship as a discovery tool

Published LBD work reports 40–70% false positives at term level with human filtering, so ≥50% at
coarser granularity with no filtering would be a good outcome, not a modest one.

---

## Amendment log

Amendments are appended, never edited into the text above, so the original commitments stay
readable in the file rather than only in git history.

**A1 — negative controls moved inside the analysis set (2026-07-27, before any gap score was
computed).** As written, the negative control specified pairs crossing domain 2 × domain 3, but the
analysis set is domains 1 and 4, so no such pair can ever be scored — the criterion was
unsatisfiable as stated. Replaced with semantically distant pairs *within* the biomedical domains
(aquaculture nutrition × systemic sclerosis; dermatological disorders × animal nutrition). The
50th-percentile bar is unchanged. Timing matters: this was corrected while the co-occurrence sweep
was still running, so no ranking existed to fit it to.

**A2 — ranking is driven by similarity, with the deficit acting as a gate (2026-07-27, before any
gap score was computed).** `Gap = S · (1 − p)` saturates: any pair with a significant deficit gets
`(1 − p) ≈ 1`, so the ranking is effectively similarity among significantly-deficient pairs. This
was noticed while implementing, not after seeing results. It is left unchanged because the obvious
alternative — weighting by `−log10(p)` — reintroduces exactly the size bias the metric exists to
avoid: topics with huge marginals produce astronomically significant deficits regardless of
whether anything interesting is going on.

**A3 — ranking uses conservative bounds, not exact counts (2026-07-27, before any gap score was
computed).** `group_by` never reports zero-valued groups, so a pair that truly never co-occurs is
absent from both rows and is scored using the tighter of the two ceilings rather than its true
value of zero. For the target pair this attenuates the deficit from `p ≈ 7e-10` to `p ≈ 0.026`.
Ranking therefore runs on conservative bounds throughout, which understates every gap equally.
Exact counts are resolved by targeted two-filter queries for reported gaps only, and each published
row states whether its count is exact or bounded.

## What a FAIL means

It means the computed layer has no demonstrated validity and lacuna ships the curated layers only,
with the negative result published as its first finding. That is a real outcome and an acceptable
one. A gap map that cannot distinguish a hole in human knowledge from a hole in OpenAlex's index is
worse than no gap map, because it launders the second as the first.
