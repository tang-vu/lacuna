from __future__ import annotations

import json

import pytest

from pipeline.benchmark.validate_candidates import (
    CANDIDATES_PATH,
    CandidateContractError,
    audit_candidates,
)
from pipeline.benchmark.validate_v3 import BENCHMARK_PATH, audit_benchmark


def test_current_candidate_ledger_separates_intake_from_benchmark_readiness():
    intake = audit_candidates()
    benchmark = audit_benchmark()

    assert intake.counts == {
        "accepted": 2,
        "proposed": 5,
        "rejected": 2,
    }
    assert set(intake.accepted_benchmark_ids) == {
        "swanson-fish-oil-raynaud",
        "swanson-magnesium-migraine",
    }
    assert benchmark.counts["positive"] == 2
    assert not benchmark.ready


def test_proposed_candidate_cannot_link_itself_into_benchmark(tmp_path):
    payload = json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))
    proposed = next(item for item in payload["candidates"] if item["status"] == "proposed")
    proposed["benchmark_case_id"] = "swanson-fish-oil-raynaud"
    path = tmp_path / "candidates.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CandidateContractError, match="cannot enter the benchmark"):
        audit_candidates(path, BENCHMARK_PATH)


def test_accepted_candidate_requires_independent_replication(tmp_path):
    payload = json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))
    accepted = next(item for item in payload["candidates"] if item["status"] == "accepted")
    accepted["evidence"] = [
        source
        for source in accepted["evidence"]
        if source["role"] != "independent_replication"
    ]
    path = tmp_path / "candidates.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CandidateContractError, match="independent replication"):
        audit_candidates(path, BENCHMARK_PATH)


def test_candidate_intake_rejects_metric_outputs(tmp_path):
    payload = json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))
    payload["candidates"][0]["rank"] = 1
    path = tmp_path / "candidates.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CandidateContractError, match="metric output fields"):
        audit_candidates(path, BENCHMARK_PATH)
