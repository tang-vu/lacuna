# Swanson reproduction: negative result

**Date:** 2026-07-27
**Criteria:** `docs/metric-validation-preregistration.md`, committed at `739c330` before any gap
score existed.
**Verdict: FAIL.** The pre-registered metric does not reproduce the canonical result.

---

## Result

| | |
|---|---|
| Analysis set | 909 of 1,458 topics (domains 1 + 4); sweep halted on the daily credit ceiling |
| Scored pairs | 220,396 after support and expectation guards |
| Target pair | T10387 Fatty Acid Research and Health × T11330 Systemic Sclerosis and Related Diseases |
| Observed / expected | ≤12 / 21.1 (pre-1986) |
| Similarity | 0.0355 |
| **Rank** | **83,654 of 220,396 → top 37.96%** |
| Pre-registered bar | top 5% for the weakest passing grade |

Stable across sweep sizes — 39.8% at 575 topics, 39.8% at 833, 38.0% at 909. Not an artifact of
incomplete data.

**Negative-control evaluation is partial.** Aquaculture Nutrition × Systemic Sclerosis ranks at
top 72.2%, well below the 50th-percentile bar. The second registered control was outside the
incomplete 909-topic sweep and was not evaluated. The available result shows the metric is not
indiscriminate, but it does not satisfy the full two-control gate.

## What the deficit half got right

The bibliometric half of the claim holds exactly as Swanson described:

| | pre-1986 | present day |
|---|---|---|
| expected under independence | 21.1 | 91.6 |
| observed | **0** | 9 |

Zero co-occurrence where ~21 works were expected — `P(X=0 | λ=21.1) ≈ 7×10⁻¹⁰`. The bridge then
genuinely formed after 1986 (0 → 9) while remaining 10× under-represented. The gap existed, and it
closed. The deficit test detects this cleanly.

The failure is entirely in the **structural-closeness** half.

## Diagnosis: cosine similarity is not the ABC structure

The pre-registered metric scores closeness as cosine over each topic's full 4,031-dimension
association vector — "A and C keep the same company". Swanson's actual claim is different: *there
exists a B such that A–B and B–C are both strong*. One path, not an overall profile.

Testing the two topics for bridges directly, ranked by `min(pPMI(A,B), pPMI(B,C))`:

| bridge strength | c(fish-oil, B) | c(sclerosis, B) | topic B |
|---|---|---|---|
| 0.0765 | 153 | 115 | Cardiovascular Disease and Adiposity |
| 0.0701 | 36 | 142 | Atherosclerosis and Cardiovascular Diseases |
| 0.0689 | 79 | 44 | Lipid metabolism and disorders |
| 0.0289 | 43 | 36 | **Antiplatelet Therapy and Cardiovascular Diseases** |
| 0.0262 | 60 | 36 | Proteoglycans and glycosaminoglycans research |

The fourth row is Swanson's own mechanism. His 1986 chain ran fish oil → reduced blood viscosity
and platelet aggregation → Raynaud's, and antiplatelet therapy surfaces as a bridge with both ends
observed in the pre-1986 literature.

**So the ABC structure is present at topic granularity — the aggregation destroyed it.** Only 16 of
4,031 columns have both ends observed. Cosine divides that concentrated signal across 4,015 zeros
and returns 0.0355. The control pair has 3 such columns, so a bridge-count measure would separate
them where cosine does not.

## What this settles

- **Assumption 1 from the architecture plan survives, narrowly.** Topic granularity does carry
  Swanson-type signal. Subfield granularity does not (the two literatures share two of their top
  five subfields). Topics were the right call.
- **The metric was wrong, not the data.** The pre-registered formula measured global profile
  overlap when the hypothesis was about path existence.

## Bugs found and fixed during the run

Both were found by inspecting behaviour, not by the metric failing:

1. **Ceiling leaked into the association vectors.** Filling every unreported cell with the row
   ceiling made all 3,857 columns non-zero in every row, giving each topic an identical dense
   background. Pairwise similarity collapsed into 0.92–0.97 and the ranking became noise, with one
   topic ("Metabolism and Genetic Disorders") appearing in 9 of the top 15. The ceiling now applies
   only to the deficit test, where a conservative upper bound is what is wanted.
2. **Column marginal estimates depended on sweep progress.** Marginals for unfetched columns were
   scaled by the number of rows fetched so far, so association vectors shifted as the sweep ran and
   nothing was reproducible. Now scaled by the slice's share of the all-time corpus.

Neither fix altered the pre-registered thresholds.

## Metric v2 result — also FAIL

Pre-registered separately before running, with k=5 fixed in advance and v1's thresholds reused
unchanged. Post-hoc, and reported as such.

| | v1 cosine | v2 bridge |
|---|---|---|
| target similarity | 0.0355 | **0.2888** |
| target rank | top 38.0% | **top 30.8%** |
| negative control | top 72.2% (sim 0.0003) | top 71.3% (sim 0.0156) |
| verdict | FAIL | **FAIL** |

The fix works in the direction predicted — target closeness rose 8×, the control stayed flat, so
the bridge measure does discriminate where cosine did not. It is nowhere near enough. The bar was
top 5%.

### Why v2 still fails: adjacent-specialty artifacts

v2's top-ranked pairs are pairs of clinically adjacent topics:

| rank | pair |
|---|---|
| 1 | Urinary Bladder and Prostate Research × Renal cell carcinoma treatment |
| 2 | Uterine Myomas × Pediatric Urology and Nephrology |
| 6 | Gastrointestinal Tumor Research × Anorectal Disease Treatments |
| 8 | Dental Health and Care Utilization × Oral and Maxillofacial Pathology |
| 14 | Appendicitis Diagnosis × Gastrointestinal Tumor Research |

These share abundant bridges and co-occur less than chance — but not because a discovery is
waiting. A paper about a bladder tumour is classified into one of these topics, not both, so
co-occurrence is structurally suppressed while the shared literature keeps bridge strength high.
The metric is detecting how OpenAlex partitions clinical subject matter.

Same-subfield sibling pairs are 12% of the top 100 against a 2.9% base rate — 4× enriched, so the
effect is real but not the whole story: 88% of top pairs cross subfield boundaries while staying
inside one clinical neighbourhood. Excluding siblings would not fix it.

The target pair sits across Nutrition and Dietetics × Pathology and Forensic Medicine — genuinely
distant in the taxonomy, which is exactly why it does not compete with same-neighbourhood pairs on
bridge strength.

### Where this leaves the approach

Both metrics fail the same way: **"structurally close but rarely co-occurring" is dominated by
classification artifacts, not by knowledge gaps.** Anything that keeps a lot of company with a
topic while sharing few papers with it is, most often, a topic the classifier treats as an
alternative label for similar work.

A third post-hoc iteration is not worth running. Two revisions already exhausted the evidential
value of this test case; a metric tuned until one known pair ranks well would demonstrate nothing
except that it was tuned.

## Proposed metric v2 — superseded by the result above

Replace cosine with a bridge measure that keeps the signal concentrated:

```
bridge_k(A,C) = sum of the top-k values of min(pPMI(A,B), pPMI(B,C)) over all B
Gap(A,C)      = bridge_k(A,C) · (1 − p_AC)
```

This must be pre-registered separately before it is run, and any result it produces is post-hoc
and weaker evidence than the failed test — the failure is what suggested the fix. Honest reporting
requires publishing both.

## Limitations

- 909 of 1,458 topics. Completing the sweep needs ~549 more calls, one further day at the free
  tier's ~1,000/day, or minutes with a registered API key.
- OpenAlex assigns topics with a model trained on the modern corpus and applies it retroactively,
  so the pre-1986 slice is today's ontology projected backwards, not the 1986 literature. Swanson
  used 1986's MeSH indexing. Even a pass would have been weaker evidence than a true replication.
- Only one target pair. A single canonical case cannot establish that a metric generalises,
  whichever way it comes out.

## Unresolved questions

1. The second pre-registered negative control remains unevaluated because its row is outside the
   incomplete sweep.
2. The free API key's real credit ceiling is still unverified — the 100,000/day figure came from a
   research report whose rate-limit claims were wrong by 10× elsewhere.
3. Which historical LBD cases and period-appropriate MeSH mappings can form a benchmark without
   selecting cases based on how a candidate v3 formula ranks them?
