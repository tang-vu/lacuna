# Metric design evidence: prospective MeSH link prediction

**Date:** 2026-08-13

**Status:** pre-formula research note; no lacuna score, rank, prediction, or metric selection exists

**Active target:** future direct PubMed/MeSH database-link emergence under
`benchmarks/autonomous-prospective-v1.json`

## Claim boundary first

This literature supports treating the active task as graph link prediction. It does not show that
a predicted link is scientifically true, important, causally novel, absent from non-academic
knowledge, or a knowledge gap. It also does not validate a lacuna formula: the active protocol can
only do that prospectively after three later complete PubMed releases.

## Direct domain precedent

Kastrin, Rindflesch, and Hristovski studied future links in networks of co-occurring MeSH
descriptors, which is unusually close to lacuna's measured target.

- Their 2014 preliminary experiment built training and testing networks from UMLS MRCOC MeSH
  co-occurrences, retained positively associated edges using a Pearson chi-square independence
  test, and evaluated Jaccard and Adamic-Adar on node pairs with no earlier link.
- The unfiltered earlier network had 24,225 nodes and 4,897,380 edges; chi-square filtering retained
  3,328,288. The later network went from 5,615,965 to 3,810,535 edges. The reported mean degrees
  after filtering were about 275 and 298.
- Evaluation was not exhaustive: each of 100 bootstrap replicates sampled 1,000 nodes. Reported
  mean AUC was 0.78 for Jaccard and 0.82 for Adamic-Adar.
- Their 2016 follow-up compared common neighbors, Jaccard, Adamic-Adar, and preferential
  attachment. Adamic-Adar was the best unsupervised method at AUC 0.76; a supervised random forest
  over the predictors reached AUC 0.87.

Sources:

- [Kastrin et al. (2014), preliminary MeSH co-occurrence link prediction](https://pubmed.ncbi.nlm.nih.gov/25160252/)
- [Kastrin et al. (2016), MeSH link prediction follow-up](https://pubmed.ncbi.nlm.nih.gov/27435341/)

These results make degree-discounted common-neighbor structure a defensible primary family to
consider. They do not determine lacuna's formula or expected performance. Their sampled AUC target,
MRCOC time split, edge filtering, and outcome definition differ from lacuna's exhaustive
precision-at-100 and three-release database-emergence protocol.

## General link-prediction evidence

Lü and Zhou compared weighted and unweighted local indices. In their tested networks, resource
allocation performed best, while adding edge weights could reduce performance; weak edges carried
useful predictive information. This is a warning against assuming that raw PubMed co-occurrence
frequency should automatically improve an unweighted topological score.

- [Lü and Zhou (2009), Role of Weak Ties in Link Prediction of Complex Networks](https://doi.org/10.1145/1651274.1651285)

Dunlavy, Kolda, and Acar showed that temporal weighting and tensor structure can improve temporal
link prediction in other domains. Their result supports time-resolved inputs as a separate design
family, not silently adding publication-year features after inspecting lacuna ranks. Any temporal
variant would need its own frozen extraction contract before those counts are measured.

- [Dunlavy, Kolda, and Acar (2011), Temporal Link Prediction using Matrix and Tensor Factorizations](https://arxiv.org/abs/1005.4006)

## Candidate formula families before seeing lacuna scores

| Family | Evidence role | Current decision |
|---|---|---|
| Adamic-Adar on an explicitly frozen positive-association MeSH backbone | Best direct unsupervised MeSH precedent | Leading family; not selected or frozen |
| Resource allocation on the same backbone | Strong low-complexity general-network comparator | Required structural baseline candidate |
| Common neighbors, Jaccard, preferential attachment | Direct comparators in the MeSH follow-up | Required baseline candidates, not primary by default |
| Weighted edge variants | Plausible but weighted indices have performed worse in some networks | Do not assume benefit; requires a pre-score rule |
| Temporally weighted or tensor methods | Preserve graph evolution but require new time-resolved inputs and parameters | Defer unless extraction and parameters are frozen before measurement |
| Supervised model | Higher AUC in the MeSH follow-up | Not usable without a separate leakage-safe, fully machine-labelled development contract |

## What may be inspected before formula freeze

After the score-free candidate universe is sealed, the following feasibility measurements may be
reported without ranking any candidate:

- exact positive-edge count and density;
- descriptor degree minimum, median, upper quantiles, and maximum under each predeclared backbone
  rule;
- exact candidate count;
- bounded storage and operation counts for scoring every candidate.

No candidate score, rank, top pair, prediction label, parameter sweep, or outcome proxy may be
materialized during this feasibility audit. Parameters cannot be chosen because a known pair looks
good.

## Requirements for the frozen metric contract

Before the first score is computed, one committed contract must pin:

1. the exact edge-backbone inequality and every integer threshold;
2. the primary formula and all baseline formulas;
3. deterministic fixed-point arithmetic, rounding, overflow guards, and non-finite refusal;
4. a computational plan that assigns one score to every eligible pair without sampling;
5. the total-order tie policy independent of descriptor labels and future outcomes;
6. formula-source, dependency-lock, T0, candidate-set, and output hashes;
7. the score and prediction artifact formats, off-system-volume path, checkpoints, and
   refusal-to-overwrite behavior;
8. automatic abstention on any missing candidate, score, integrity check, or structural diagnostic;
9. zero LLM or human interpretation in metric construction, scoring, ranking, or outcome labels.

Until that contract exists and its predictions are sealed, Adamic-Adar is a literature-supported
design candidate only. It is not lacuna's metric and has no readiness contribution.
