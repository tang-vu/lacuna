"""Tests for the gap metric's numerical core.

Both bugs that distorted the first validation run — the row ceiling leaking into association
vectors, and column marginals that shifted as the sweep progressed — produced plausible-looking
numbers rather than crashes. Neither would have been caught by anything except a test that pins
down behaviour, hence the regression tests below.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from pipeline.metric import gap_score
from pipeline.metric.gap_score import (
    Matrix,
    association_vectors,
    bridge_similarity,
    column_marginals,
    masked_similarity,
    pair_evidence,
    poisson_cdf,
)


def toy_matrix() -> Matrix:
    """Three analysis topics over four columns, with hand-checkable numbers."""
    return Matrix(
        topic_ids=["T1", "T2", "T3"],
        column_ids=["T1", "T2", "T3", "T4"],
        counts=np.array(
            [
                [0, 10, 0, 40],
                [10, 0, 0, 30],
                [0, 0, 0, 5],
            ],
            dtype=np.float32,
        ),
        marginals=np.array([1000.0, 1000.0, 1000.0]),
        ceilings=np.array([3.0, 2.0, 0.0], dtype=np.float32),
        total_works=100_000,
    )


class TestPoissonCdf:
    def test_matches_manual_summation(self):
        expected = np.array([4.0])
        observed = np.array([2.0])
        manual = sum(math.exp(-4.0) * 4.0**k / math.factorial(k) for k in range(3))
        assert poisson_cdf(observed, expected)[0] == pytest.approx(manual, rel=1e-9)

    def test_zero_observations_against_large_expectation_is_vanishingly_unlikely(self):
        # The canonical pre-1986 case: nothing observed where ~21 works were expected.
        p = poisson_cdf(np.array([0.0]), np.array([21.1]))[0]
        assert p == pytest.approx(math.exp(-21.1), rel=1e-9)
        assert p < 1e-9

    def test_at_or_above_expectation_is_not_a_deficit(self):
        # Pairs at or above chance are not gaps and are assigned p=1 without summation.
        p = poisson_cdf(np.array([50.0, 100.0]), np.array([50.0, 20.0]))
        assert np.all(p == 1.0)

    def test_normal_approximation_agrees_with_exact_at_the_boundary(self):
        # Continuity between the exact branch and the approximate one, checked just either side
        # of the cutoff at a fixed ratio of observed to expected.
        limit = gap_score.EXACT_POISSON_LIMIT
        exact = poisson_cdf(np.array([limit * 0.8]), np.array([limit - 1.0]))[0]
        approx = poisson_cdf(np.array([limit * 0.8]), np.array([limit + 1.0]))[0]
        assert exact == pytest.approx(approx, abs=0.02)


class TestMaskedSimilarity:
    def test_closed_form_matches_explicit_masking(self):
        rng = np.random.default_rng(0)
        vectors = rng.random((6, 9))
        vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
        analysis_cols = np.arange(6)

        fast = masked_similarity(vectors, vectors[:, analysis_cols])

        for i in range(6):
            for j in range(6):
                vi, vj = vectors[i].copy(), vectors[j].copy()
                for masked in (analysis_cols[i], analysis_cols[j]):
                    vi[masked] = 0.0
                    vj[masked] = 0.0
                slow = np.dot(vi, vj) / (np.linalg.norm(vi) * np.linalg.norm(vj))
                assert fast[i, j] == pytest.approx(slow, abs=1e-9)

    def test_masking_removes_the_pairs_own_cooccurrence(self):
        """Without masking, a pair's own co-occurrence inflates the closeness that is supposed to
        be evidence the pair does *not* co-occur. That circularity is the whole reason for it."""
        vectors = np.zeros((2, 4))
        vectors[0] = [0.0, 1.0, 0.0, 0.0]  # T1 associates only with T2
        vectors[1] = [1.0, 0.0, 0.0, 0.0]  # T2 associates only with T1
        similarity = masked_similarity(vectors, vectors[:, np.array([0, 1])])
        # Their only shared structure is each other, which masking removes entirely.
        assert similarity[0, 1] == pytest.approx(0.0, abs=1e-9)


class TestBridgeSimilarity:
    def test_scores_the_strongest_shared_intermediates(self):
        # T1 and T2 share column 3 at strengths 0.5 and 0.25; the bridge is the weaker end.
        vectors = np.array(
            [
                [0.0, 0.0, 0.0, 0.5],
                [0.0, 0.0, 0.0, 0.25],
                [0.9, 0.0, 0.0, 0.0],
            ]
        )
        scores = bridge_similarity(vectors, np.array([0, 1, 2]), k=1)
        assert scores[0, 1] == pytest.approx(0.25)

    def test_a_bridge_needs_both_ends(self):
        """One strong end and one absent end is not a bridge — that is what the minimum enforces."""
        vectors = np.array(
            [
                [0.0, 0.0, 0.0, 0.9],
                [0.0, 0.0, 0.0, 0.0],
                [0.0, 0.0, 0.0, 0.0],
            ]
        )
        scores = bridge_similarity(vectors, np.array([0, 1, 2]), k=1)
        assert scores[0, 1] == pytest.approx(0.0)

    def test_endpoints_cannot_bridge_themselves(self):
        vectors = np.array(
            [
                [0.0, 0.8, 0.0, 0.0],  # T1 -> T2 column
                [0.9, 0.0, 0.0, 0.0],  # T2 -> T1 column
                [0.0, 0.0, 0.0, 0.0],
            ]
        )
        scores = bridge_similarity(vectors, np.array([0, 1, 2]), k=1)
        assert scores[0, 1] == pytest.approx(0.0)

    def test_symmetric(self):
        rng = np.random.default_rng(1)
        vectors = rng.random((5, 8))
        scores = bridge_similarity(vectors, np.arange(5), k=2)
        assert np.allclose(scores, scores.T)


class TestCeilingIsolation:
    """Regression tests for the bug that silently wrecked the first validation run."""

    def test_ceiling_does_not_enter_the_counts_matrix(self):
        matrix = toy_matrix()
        # T1/T3 were never reported together. That cell stays zero here; the ceiling is applied
        # later, and only by the deficit test.
        assert matrix.counts[0, 2] == 0.0

    def test_association_vectors_stay_sparse(self):
        """A dense background makes every topic look alike; that is what collapsed similarity
        into the 0.92-0.97 band and let one hub topic take 9 of the top 15 results."""
        matrix = toy_matrix()
        vectors = association_vectors(matrix, column_marginals(matrix, {}))
        assert (vectors == 0.0).sum() > vectors.size / 2


class TestColumnMarginals:
    def test_estimates_do_not_depend_on_how_much_of_the_sweep_has_run(self):
        """Marginals for unfetched columns once scaled with the number of rows fetched so far, so
        association vectors drifted as a sweep progressed and no run was reproducible."""
        taxonomy_counts = {"T4": 8_000_000}

        small = toy_matrix()
        large = toy_matrix()
        large.topic_ids = ["T1", "T2", "T3"] * 40
        large.marginals = np.tile(large.marginals, 40)
        large.counts = np.tile(large.counts, (40, 1))

        column_of_t4 = small.column_ids.index("T4")
        assert (
            column_marginals(small, taxonomy_counts)[column_of_t4]
            == column_marginals(large, taxonomy_counts)[column_of_t4]
        )

    def test_fetched_marginals_take_precedence_over_estimates(self):
        matrix = toy_matrix()
        result = column_marginals(matrix, {"T1": 999_999_999})
        assert result[matrix.column_ids.index("T1")] == 1000.0


class TestPairEvidence:
    def test_labels_an_unreported_positive_ceiling_as_an_upper_bound(self):
        matrix = toy_matrix()
        evidence = pair_evidence(
            matrix,
            {"T1": 1000, "T2": 1000, "T3": 1000, "T4": 8000},
            "T1",
            "T3",
        )

        assert evidence["observed"] == 0.0
        assert evidence["observed_kind"] == "exact"

        matrix.ceilings[2] = 4.0
        evidence = pair_evidence(
            matrix,
            {"T1": 1000, "T2": 1000, "T3": 1000, "T4": 8000},
            "T1",
            "T3",
        )
        assert evidence["observed"] == 3.0
        assert evidence["observed_kind"] == "upper_bound"

    def test_labels_a_reported_count_as_exact(self):
        evidence = pair_evidence(
            toy_matrix(),
            {"T1": 1000, "T2": 1000, "T3": 1000, "T4": 8000},
            "T1",
            "T2",
        )
        assert evidence["observed"] == 10.0
        assert evidence["observed_kind"] == "exact"
