from __future__ import annotations

import json

import pytest

from pipeline.benchmark.build_negative_case import (
    NegativeCaseBuildError,
    build_negative_case,
)
from pipeline.benchmark.negative_controls import OUTPUT_PATH as NEGATIVE_QUEUE_PATH
from pipeline.benchmark.validate_v3 import BENCHMARK_PATH, audit_benchmark


def _proposal(kind: str) -> dict:
    queue = json.loads(NEGATIVE_QUEUE_PATH.read_text(encoding="utf-8"))
    return next(item for item in queue["candidates"] if item["kind"] == kind)


@pytest.mark.parametrize(
    ("kind", "issue"),
    [("hard_negative", 4), ("distant_negative", 3)],
)
def test_builder_preserves_frozen_identity_and_passes_v3_contract(
    tmp_path,
    kind,
    issue,
):
    proposal = _proposal(kind)
    case = build_negative_case(
        proposal["id"],
        adjudication_url=(
            f"https://github.com/tang-vu/lacuna/issues/{issue}#issuecomment-123"
        ),
        negative_rationale="Reviewer confirmed this pre-metric control rationale.",
    )
    benchmark = json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))
    benchmark["cases"].append(case)
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(benchmark), encoding="utf-8")

    audit = audit_benchmark(path)

    assert audit.counts[kind] == 1
    assert case["selection_candidate_id"] == proposal["id"]
    assert case["split"] == proposal["proposed_split"]
    assert case["cutoff"] == proposal["cutoff"]
    assert all(
        concept["mapping"]["status"] == "unavailable"
        for concept in case["concepts"].values()
    )


def test_builder_rejects_unknown_candidates_and_wrong_issue_links():
    with pytest.raises(NegativeCaseBuildError, match="unknown frozen"):
        build_negative_case(
            "not-in-the-queue",
            adjudication_url=(
                "https://github.com/tang-vu/lacuna/issues/4#issuecomment-123"
            ),
            negative_rationale="Reviewed.",
        )

    proposal = _proposal("hard_negative")
    with pytest.raises(NegativeCaseBuildError, match="issue #4"):
        build_negative_case(
            proposal["id"],
            adjudication_url=(
                "https://github.com/tang-vu/lacuna/issues/3#issuecomment-123"
            ),
            negative_rationale="Reviewed.",
        )


def test_builder_requires_a_reviewer_rationale():
    proposal = _proposal("distant_negative")
    with pytest.raises(NegativeCaseBuildError, match="reviewer-authored"):
        build_negative_case(
            proposal["id"],
            adjudication_url=(
                "https://github.com/tang-vu/lacuna/issues/3#issuecomment-123"
            ),
            negative_rationale="Reviewed but too short.",
        )
