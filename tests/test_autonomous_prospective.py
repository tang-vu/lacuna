from __future__ import annotations

import json

import pytest

from pipeline.benchmark.validate_autonomous_prospective import (
    PROTOCOL_PATH,
    AutonomousProspectiveContractError,
    audit_autonomous_prospective,
)


def test_active_protocol_has_sealed_t0_no_human_dependency_and_no_metric_claim():
    audit = audit_autonomous_prospective()

    assert audit.protocol_id == "autonomous-prospective-pubmed-link-emergence-v1"
    assert audit.state == "awaiting_frozen_metric"
    assert audit.verdict == "not_ready"
    assert audit.human_dependency_count == 0
    assert audit.readiness_contribution == 0
    assert len(audit.blockers) == 3
    assert audit.ready is False


def test_protocol_rejects_human_gate_and_gap_detector_overclaim(tmp_path):
    payload = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    payload["human_dependencies"] = ["expert review"]
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(AutonomousProspectiveContractError, match="depend on humans"):
        audit_autonomous_prospective(path)

    payload = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    payload["scientific_claim_boundary"]["forbidden_labels"].remove(
        "validated knowledge gap detector"
    )
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(AutonomousProspectiveContractError, match="overclaim guard"):
        audit_autonomous_prospective(path)


def test_protocol_rejects_manual_labels_or_silent_source_failure(tmp_path):
    payload = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    payload["machine_outcomes"]["llm_or_manual_labels_allowed"] = True
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(AutonomousProspectiveContractError, match="no-human outcome"):
        audit_autonomous_prospective(path)

    payload = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    payload["source_contract"]["partial_release_action"] = "continue"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(AutonomousProspectiveContractError, match="source failure"):
        audit_autonomous_prospective(path)


def test_protocol_rejects_remote_inventory_identity_drift(tmp_path):
    payload = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    payload["source_contract"]["t0_remote_inventory"]["sha256"] = "0" * 64
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AutonomousProspectiveContractError, match="remote inventory identity"):
        audit_autonomous_prospective(path)


def test_protocol_rejects_sealed_t0_manifest_identity_drift(tmp_path):
    payload = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    payload["source_contract"]["t0_manifest"]["sha256"] = "0" * 64
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AutonomousProspectiveContractError, match="sealed T0 manifest identity"):
        audit_autonomous_prospective(path)


def test_protocol_rejects_candidate_index_contract_identity_drift(tmp_path):
    payload = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    payload["t0_construction_contract"]["sha256"] = "0" * 64
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AutonomousProspectiveContractError, match="construction contract identity"):
        audit_autonomous_prospective(path)


def test_protocol_rejects_candidate_universe_identity_or_state_drift(tmp_path):
    payload = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    payload["t0_candidate_universe_artifact"]["candidate_pair_count"] = 1
    path = tmp_path / "protocol-universe.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(AutonomousProspectiveContractError, match="candidate-universe artifact"):
        audit_autonomous_prospective(path)

    payload = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    payload["current_state"]["candidate_universe_sealed"] = False
    path = tmp_path / "protocol-state.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(AutonomousProspectiveContractError, match="current autonomous state"):
        audit_autonomous_prospective(path)


def test_protocol_rejects_power_threshold_or_current_readiness_drift(tmp_path):
    payload = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    payload["pre_registered_evaluation"]["minimum_observed_positive_outcomes"] = 1
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(AutonomousProspectiveContractError, match="power gate"):
        audit_autonomous_prospective(path)

    payload = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    payload["current_state"]["verdict"] = "passed"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(AutonomousProspectiveContractError, match="current autonomous state"):
        audit_autonomous_prospective(path)
