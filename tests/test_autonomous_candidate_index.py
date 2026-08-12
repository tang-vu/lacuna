from __future__ import annotations

import json

import pytest

from pipeline.benchmark.validate_autonomous_candidate_index import (
    CONTRACT_PATH,
    AutonomousCandidateIndexContractError,
    audit_candidate_index_contract,
)


def _write(tmp_path, payload):
    path = tmp_path / "candidate-index.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_committed_candidate_index_is_frozen_score_free_and_exact():
    audit = audit_candidate_index_contract()

    assert audit.contract_id == "autonomous-t0-candidate-index-v1"
    assert len(audit.sha256) == 64
    assert audit.source_file_count == 1334
    assert audit.source_record_count == 39_994_988
    assert audit.descriptor_count == 31_110
    assert audit.status == "frozen_before_descriptor_support_or_pair_measurement"
    assert audit.readiness_contribution == 0


def test_candidate_index_rejects_sampling_threshold_or_human_drift(tmp_path):
    payload = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    payload["count_contract"]["sampling_allowed"] = True
    with pytest.raises(AutonomousCandidateIndexContractError, match="exact count"):
        audit_candidate_index_contract(_write(tmp_path, payload))

    payload = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    payload["candidate_contract"]["minimum_endpoint_article_support"] = 10
    with pytest.raises(AutonomousCandidateIndexContractError, match="eligibility"):
        audit_candidate_index_contract(_write(tmp_path, payload))

    payload = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    payload["human_dependencies"] = ["reviewer"]
    with pytest.raises(AutonomousCandidateIndexContractError, match="human dependency"):
        audit_candidate_index_contract(_write(tmp_path, payload))


def test_candidate_index_rejects_score_fields_or_weak_storage_guards(tmp_path):
    payload = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    payload["candidate_contract"]["score"] = 0.5
    with pytest.raises(AutonomousCandidateIndexContractError, match="metric output"):
        audit_candidate_index_contract(_write(tmp_path, payload))

    payload = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    payload["storage_contract"]["system_temp_allowed"] = True
    with pytest.raises(AutonomousCandidateIndexContractError, match="storage"):
        audit_candidate_index_contract(_write(tmp_path, payload))


def test_candidate_index_rejects_t0_identity_or_claim_boundary_drift(tmp_path):
    payload = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    payload["known_before_freeze"]["t0_manifest_sha256"] = "0" * 64
    with pytest.raises(AutonomousCandidateIndexContractError, match="known-before-freeze"):
        audit_candidate_index_contract(_write(tmp_path, payload))

    payload = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    payload["measurement_boundary"]["not_measured"] = ["historical"]
    with pytest.raises(AutonomousCandidateIndexContractError, match="claim boundary"):
        audit_candidate_index_contract(_write(tmp_path, payload))
