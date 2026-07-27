"""The gap metric.

A gap is a pair of topics that is **bibliometrically distant** (they co-occur far less than chance
would predict) and **structurally close** (they keep the same company — both associate with a
common set of third topics). Neither half is interesting alone: most pairs are distant and
unrelated, and closeness alone is just similarity, which plenty of tools already compute. Only the
conjunction states Swanson's ABC structure — *A and C keep the same company but never meet*.

    e_ij  = s_i · s_j / N                    expected co-occurrence under independence
    p_ij  = P(X ≤ c_ij),  X ~ Poisson(e_ij)  probability of seeing this few by chance
    a_i   = positive-PMI association vector of topic i over all 4,516 topics
    S_ij  = cosine(a_i, a_j), components i and j masked out
    Gap   = S_ij · (1 − p_ij)

Masking components i and j from the cosine is load-bearing. Without it, part of the "closeness"
signal is the very co-occurrence whose absence is the claim, and the metric argues in a circle.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass

import numpy as np

from pipeline.paths import COOCCURRENCE_DIR, TAXONOMY_PATH

# Guards. A deficit below these is unmeasurable rather than meaningful.
MIN_MARGINAL = 1000  # works carrying the topic within the slice
MIN_EXPECTED = 5.0  # expected co-occurrences; below this "zero" says nothing


@dataclass
class Matrix:
    """Co-occurrence data for one time slice."""

    topic_ids: list[str]  # rows: the analysis set S
    column_ids: list[str]  # columns: every topic appearing as a partner
    counts: np.ndarray  # (rows, cols) observed co-occurrence
    marginals: np.ndarray  # (rows,) works per row topic in this slice
    ceilings: np.ndarray  # (rows,) upper bound on any partner absent from a truncated row
    total_works: int

    def row_index(self, topic_id: str) -> int:
        return self.topic_ids.index(topic_id)


def load_matrix(slice_name: str, total_works: int) -> Matrix:
    """Assemble fetched rows into a dense matrix.

    Absent partners in a truncated row are filled with that row's ceiling, not with zero. The
    ceiling is the smallest co-occurrence the API actually reported, so every unreported partner
    is bounded by it. Substituting the ceiling makes every resulting gap score a conservative
    lower bound: a pair that looks like a gap despite being credited with the maximum possible
    co-occurrence really is one.
    """
    slice_dir = COOCCURRENCE_DIR / slice_name
    rows = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(slice_dir.glob("T*.json"))]
    if not rows:
        raise FileNotFoundError(f"no co-occurrence rows in {slice_dir}; run fetch_cooccurrence first")

    topic_ids = [r["topic"] for r in rows]
    columns = sorted({p for r in rows for p in r["partners"]} | set(topic_ids))
    col_index = {c: i for i, c in enumerate(columns)}

    counts = np.zeros((len(rows), len(columns)), dtype=np.float32)
    marginals = np.zeros(len(rows), dtype=np.float64)
    ceilings = np.zeros(len(rows), dtype=np.float32)

    for i, row in enumerate(rows):
        marginals[i] = row["marginal"]
        ceilings[i] = row["ceiling"]
        if row["truncated"]:
            counts[i, :] = row["ceiling"]
        for partner, count in row["partners"].items():
            counts[i, col_index[partner]] = count
        counts[i, col_index[row["topic"]]] = 0.0  # self-co-occurrence is meaningless

    return Matrix(topic_ids, columns, counts, marginals, ceilings, total_works)


def column_marginals(matrix: Matrix, taxonomy_counts: dict[str, int]) -> np.ndarray:
    """Marginal for every column topic, needed for PMI over the full 4,516-topic space.

    Rows only cover the analysis set, so column marginals for topics outside it come from the
    taxonomy's all-time works_count, rescaled to the slice. The rescaling is crude but affects
    only the association vectors' weighting, not the deficit test that decides significance.
    """
    scale = matrix.total_works / max(sum(taxonomy_counts.values()), 1)
    fetched = dict(zip(matrix.topic_ids, matrix.marginals))
    return np.array(
        [fetched.get(c, taxonomy_counts.get(c, 0) * scale * len(matrix.topic_ids)) or 1.0
         for c in matrix.column_ids],
        dtype=np.float64,
    )


def association_vectors(matrix: Matrix, col_marginals: np.ndarray) -> np.ndarray:
    """Positive pointwise mutual information, row-normalised to unit length.

    Positive PMI is the standard weighting for second-order similarity: it suppresses the
    everything-co-occurs-with-everything background without letting rare pairs dominate the way
    raw counts or plain PMI would.
    """
    expected = np.outer(matrix.marginals, col_marginals) / matrix.total_works
    with np.errstate(divide="ignore", invalid="ignore"):
        pmi = np.log(np.maximum(matrix.counts, 1e-9) / np.maximum(expected, 1e-9))
    pmi = np.nan_to_num(pmi, nan=0.0, posinf=0.0, neginf=0.0)
    np.maximum(pmi, 0.0, out=pmi)

    norms = np.linalg.norm(pmi, axis=1, keepdims=True)
    return pmi / np.maximum(norms, 1e-12)


def _normal_cdf(z: np.ndarray) -> np.ndarray:
    """Standard normal CDF via the Abramowitz & Stegun 7.1.26 erf approximation (|error| < 1.5e-7).

    Avoids a scipy dependency for the one special function this pipeline needs.
    """
    x = z / np.sqrt(2.0)
    sign = np.sign(x)
    x = np.abs(x)
    t = 1.0 / (1.0 + 0.3275911 * x)
    poly = t * (0.254829592 + t * (-0.284496736 + t * (1.421413741 + t * (-1.453152027 + t * 1.061405429))))
    erf = sign * (1.0 - poly * np.exp(-x * x))
    return 0.5 * (1.0 + erf)


# Above this expected count the exact summation is replaced by a normal approximation. The metric
# only consumes (1 - p), which saturates at 1 long before the approximation's error matters.
EXACT_POISSON_LIMIT = 200.0


def poisson_cdf(observed: np.ndarray, expected: np.ndarray) -> np.ndarray:
    """P(X <= observed) for X ~ Poisson(expected).

    Poisson rather than the exact hypergeometric: with N in the tens of millions and expected
    counts in the tens, the two agree far beyond the precision that matters here, and Poisson
    avoids the overflow that exact binomial coefficients invite.

    Only the deficit region (observed < expected) is computed. Everywhere else the pair is at or
    above chance, is not a gap by definition, and is assigned p = 1 so its gap score collapses to
    zero. That restriction also bounds the summation below, which would otherwise run to the
    largest observed co-occurrence in the matrix — tens of thousands of iterations.
    """
    observed = np.floor(observed).astype(np.float64)
    cdf = np.ones_like(expected, dtype=np.float64)

    deficit = observed < expected
    exact = deficit & (expected <= EXACT_POISSON_LIMIT)
    approx = deficit & ~exact

    if exact.any():
        obs_e, exp_e = observed[exact], expected[exact]
        max_k = int(obs_e.max())
        term = np.exp(-exp_e)  # k = 0
        total = term.copy()
        for k in range(1, max_k + 1):
            term = term * exp_e / k
            total += term * (obs_e >= k)
        cdf[exact] = total

    if approx.any():
        # Continuity-corrected normal approximation to Poisson.
        obs_a, exp_a = observed[approx], expected[approx]
        cdf[approx] = _normal_cdf((obs_a + 0.5 - exp_a) / np.sqrt(exp_a))

    return np.clip(cdf, 0.0, 1.0)


def generalist_topics(matrix: Matrix, iqr_multiplier: float = 10.0) -> set[str]:
    """Topics that behave as dumping grounds for poorly-classified works.

    OpenAlex assigns a topic to every work, so works with thin metadata land in whichever topic the
    classifier defaults to. The result is a handful of absurd topics — Military Technology holds
    22.3M works, 7% of the entire corpus; "Diverse Scientific and Economic Studies" holds 5.1M.
    They co-occur with everything and would dominate every association vector.

    Detected by a standard outlier rule on slice marginals rather than a hand-written blocklist,
    so the exclusion is reproducible and nobody gets to quietly exclude a topic they dislike. The
    excluded list ships with the artifact.
    """
    q1, q3 = np.percentile(matrix.marginals, [25, 75])
    threshold = q3 + iqr_multiplier * (q3 - q1)
    return {t for t, m in zip(matrix.topic_ids, matrix.marginals) if m > threshold}


def masked_similarity(vectors: np.ndarray, self_block: np.ndarray) -> np.ndarray:
    """Pairwise cosine similarity with each pair's own two components removed.

    Computed in closed form rather than by masking and re-normalising per pair, which would mean a
    Python loop over ~1M pairs each copying a 4,516-wide vector. Rows of `vectors` are already unit
    length, so for a pair (i, j):

        masked_dot   = v_i . v_j  −  v_i[i]·v_j[i]  −  v_i[j]·v_j[j]
        masked_norm_i = sqrt(1 − v_i[i]² − v_i[j]²)

    `self_block[i, j]` is v_i at the column belonging to topic j, which is all the closed form
    needs. The result is identical to explicit masking, to floating-point precision.
    """
    dot = vectors @ vectors.T
    diagonal = np.diag(self_block)  # v_i[i]

    # Subtract the k=i and k=j terms of the dot product.
    term_i = diagonal[:, None] * self_block.T  # v_i[i] · v_j[i]
    term_j = self_block * diagonal[None, :]  # v_i[j] · v_j[j]
    masked_dot = dot - term_i - term_j

    # Norms after removing the same two components from each vector.
    sq_i = diagonal[:, None] ** 2 + self_block**2  # v_i[i]² + v_i[j]²
    norm_i = np.sqrt(np.maximum(1.0 - sq_i, 1e-12))
    return masked_dot / np.maximum(norm_i * norm_i.T, 1e-12)


def score_pairs(matrix: Matrix, taxonomy_counts: dict[str, int]) -> list[dict]:
    """Score every eligible pair in the analysis set. Returns rows sorted by gap score."""
    col_marginals = column_marginals(matrix, taxonomy_counts)
    vectors = association_vectors(matrix, col_marginals)
    excluded = generalist_topics(matrix)

    col_of_row = {c: i for i, c in enumerate(matrix.column_ids)}
    analysis_cols = np.array([col_of_row[t] for t in matrix.topic_ids])

    similarity = masked_similarity(vectors, vectors[:, analysis_cols])

    # Observed co-occurrence, taking whichever direction is tighter: a value present in a row is
    # exact, while an absent one is only bounded by that row's ceiling.
    counts_block = matrix.counts[:, analysis_cols]
    observed = np.minimum(counts_block, counts_block.T)

    expected = np.outer(matrix.marginals, matrix.marginals) / matrix.total_works

    eligible = np.array(
        [t not in excluded and m >= MIN_MARGINAL for t, m in zip(matrix.topic_ids, matrix.marginals)]
    )
    keep = np.triu(np.outer(eligible, eligible), k=1) & (expected >= MIN_EXPECTED)
    rows, cols = np.nonzero(keep)
    if rows.size == 0:
        return []

    p_values = poisson_cdf(observed[rows, cols], expected[rows, cols])
    gap_scores = similarity[rows, cols] * (1.0 - p_values)

    order = np.argsort(-gap_scores)
    return [
        {
            "topic_a": matrix.topic_ids[rows[k]],
            "topic_b": matrix.topic_ids[cols[k]],
            "observed": float(observed[rows[k], cols[k]]),
            "expected": round(float(expected[rows[k], cols[k]]), 2),
            "s_a": int(matrix.marginals[rows[k]]),
            "s_b": int(matrix.marginals[cols[k]]),
            "similarity": round(float(similarity[rows[k], cols[k]]), 5),
            "p_value": float(p_values[k]),
            "deficit_bits": round(-math.log10(max(float(p_values[k]), 1e-300)), 2),
            "gap_score": round(float(gap_scores[k]), 5),
        }
        for k in order
    ]


def load_taxonomy_counts() -> dict[str, int]:
    taxonomy = json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))
    return {t["id"]: t["works_count"] for t in taxonomy["topics"]}
