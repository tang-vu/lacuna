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
        "proposed": 10,
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


def test_proposed_candidate_requires_a_selection_source(tmp_path):
    payload = json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))
    proposed = next(item for item in payload["candidates"] if item["status"] == "proposed")
    proposed["evidence"] = [
        source for source in proposed["evidence"] if source["role"] != "selection_source"
    ]
    path = tmp_path / "candidates.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CandidateContractError, match="needs a selection source"):
        audit_candidates(path, BENCHMARK_PATH)


def test_production_year_mapping_must_use_the_pinned_vocabulary(tmp_path):
    payload = json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))
    mapped = next(item for item in payload["candidates"] if "mapping_audit" in item)
    mapped["mapping_audit"]["source_sha256"] = "0" * 64
    path = tmp_path / "candidates.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CandidateContractError, match="differs from the pinned vocabulary"):
        audit_candidates(path, BENCHMARK_PATH)


def test_source_cutoff_must_match_the_documented_evaluation_lag(tmp_path):
    payload = json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))
    mapped = next(item for item in payload["candidates"] if "source_cutoff_year" in item)
    mapped["source_cutoff_year"] += 1
    path = tmp_path / "candidates.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CandidateContractError, match="source cutoff year differs"):
        audit_candidates(path, BENCHMARK_PATH)


def test_source_cutoff_basis_must_be_publication_year_bounded(tmp_path):
    payload = json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))
    mapped = next(item for item in payload["candidates"] if "source_cutoff_basis" in item)
    mapped["source_cutoff_basis"] = "exact_publication_date"
    path = tmp_path / "candidates.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CandidateContractError, match="unsupported source cutoff basis"):
        audit_candidates(path, BENCHMARK_PATH)
