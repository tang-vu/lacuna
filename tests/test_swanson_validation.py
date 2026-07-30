"""Regression tests pinning the measured validation outcome.

These run against fetched data under `data/`, which is gitignored because it is large and
regenerable. They skip when it is absent rather than failing, so a fresh clone is not red — but
locally, after a sweep, they are the tests that stop the metric changing without anyone noticing.

They encode what was *measured*, including the failure. A future change that makes the target pair
rank well is not automatically an improvement: it might be a bug, or it might be the metric being
tuned toward one known answer. Either way it should force a deliberate look, which is what a
failing assertion here does.
"""

from __future__ import annotations

import pytest

from pipeline.metric.gap_score import load_matrix, load_taxonomy_counts, score_pairs
from pipeline.paths import COOCCURRENCE_DIR, TAXONOMY_PATH
from pipeline.validate.validate_swanson import PRE1986_TOTAL_WORKS, TARGET, percentile_rank

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        not (COOCCURRENCE_DIR / "pre1986").exists() or not TAXONOMY_PATH.exists(),
        reason="needs a fetched pre-1986 sweep; run pipeline.ingest.fetch_cooccurrence",
    ),
]


@pytest.fixture(scope="module")
def matrix():
    return load_matrix("pre1986", PRE1986_TOTAL_WORKS)


@pytest.fixture(scope="module")
def scored(matrix):
    """Module-scoped: scoring the full matrix takes minutes, so it runs once per session."""
    return score_pairs(matrix, load_taxonomy_counts(), closeness="bridge")


@pytest.fixture(scope="module")
def scored_cosine(matrix):
    return score_pairs(matrix, load_taxonomy_counts(), closeness="cosine")


def test_target_topics_carry_the_expected_literatures(matrix):
    """The two topics identified as carrying the Raynaud's and fish-oil literatures, with the
    marginals measured on 2026-07-27. A large shift means OpenAlex reclassified something and the
    validation is no longer testing what it claims to."""
    marginals = dict(zip(matrix.topic_ids, matrix.marginals))
    assert marginals["T11330"] == pytest.approx(35_940, rel=0.05)
    assert marginals["T10387"] == pytest.approx(22_574, rel=0.05)


def test_the_deficit_half_of_the_hypothesis_holds(scored):
    """The bibliometric claim, which did reproduce: the two literatures never met before 1986,
    where independence predicts roughly 21 shared works."""
    found = percentile_rank(scored, TARGET)
    assert found is not None, "target pair missing — sweep incomplete or guards dropped it"
    _, _, row = found

    assert row["expected"] == pytest.approx(21.1, rel=0.05)
    # Bounded by the tighter row ceiling rather than the true zero, because group_by never reports
    # zero-valued groups. The exact count, from a targeted two-filter query, is 0.
    assert row["observed"] <= 27
    assert row["p_value"] < 0.05


def test_the_structural_half_does_not_reproduce(scored):
    """The pre-registered result: FAIL. The bar was top 5%; the measured rank was top 30.8%.

    Pinned as a band. If this starts passing, find out why before celebrating."""
    _, percentile, _ = percentile_rank(scored, TARGET)
    assert percentile > 5.0, (
        "target pair now clears the pre-registered bar. Verify this is a real improvement and not "
        "a metric fitted to the one case it is validated against, then update the published result."
    )
    assert 20.0 < percentile < 45.0


def test_negative_control_ranks_poorly(scored):
    """A metric that also ranks unrelated pairs highly has discovered nothing. Aquaculture
    nutrition against systemic sclerosis must stay below the 50th percentile."""
    found = percentile_rank(scored, ("T10450", "T11330"))
    if found is None:
        pytest.skip("control pair not in the fetched analysis set")
    _, percentile, _ = found
    assert percentile > 50.0


def test_bridge_measure_beats_cosine_on_the_target(scored, scored_cosine):
    """v2's justification: the ABC signal sits in ~16 of 4,031 columns, which cosine averages away.
    The bridge measure should recover it without also lifting the negative control."""
    cosine, bridge = scored_cosine, scored

    _, _, cosine_row = percentile_rank(cosine, TARGET)
    _, _, bridge_row = percentile_rank(bridge, TARGET)
    assert bridge_row["similarity"] > cosine_row["similarity"] * 4

    control_cosine = percentile_rank(cosine, ("T10450", "T11330"))
    control_bridge = percentile_rank(bridge, ("T10450", "T11330"))
    if control_cosine and control_bridge:
        assert control_bridge[2]["similarity"] < bridge_row["similarity"] / 4
