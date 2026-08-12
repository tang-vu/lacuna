from __future__ import annotations

import json

import pytest

from pipeline.benchmark.validate_source_alternatives import (
    ALTERNATIVES_PATH,
    SourceAlternativeContractError,
    audit_source_alternatives,
)


def _write_payload(tmp_path, payload):
    path = tmp_path / "source-alternatives.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_current_alternatives_keep_original_readiness_at_zero():
    audit = audit_source_alternatives()

    assert audit.status == "no_equivalent_replacement_pinned"
    assert audit.recommended_id == "bioasq-2013-task-a"
    assert audit.counts == {
        "audited_scope_mismatch": 1,
        "engineering_only": 1,
        "rejected_for_historical_gate": 1,
    }
    assert audit.readiness_contribution == 0
    bioasq = next(entry for entry in audit.entries if entry["id"] == audit.recommended_id)
    assert bioasq["declared_snapshot"]["article_count"] == 10_876_004
    assert bioasq["declared_snapshot"]["mesh_label_count"] == 26_563
    assert bioasq["declared_snapshot"]["comparison_only_nlm_2013_baseline_record_count"] == (
        21_508_439
    )
    assert bioasq["can_replace_original_gate"] is False
    assert bioasq["public_sample_audit"]["path"].endswith("bioasq-2013-public-sample.json")
    assert bioasq["snapshot_audit"]["path"].endswith("bioasq-2013-task-a.json")
    assert bioasq["semantics_protocol"]["path"].endswith("bioasq-semantics-protocol.json")
    assert bioasq["successor_semantics_protocol"]["path"].endswith(
        "bioasq-semantics-protocol-v2.json"
    )
    assert bioasq["semantics_audit"]["path"].endswith(
        "bioasq-2013-semantics.json"
    )
    assert bioasq["pilot_protocol"]["path"].endswith("bioasq-pilot.json")
    assert bioasq["pilot_development_measurement"]["path"].endswith(
        "bioasq-v2-development-084cc2a9e381.json"
    )
    assert bioasq["pilot_graph_cache_manifest"]["path"].endswith(
        "bioasq-v2-graph-cache-084cc2a9e381-8ebd0c227d93.json"
    )


def test_alternative_cannot_claim_original_gate_readiness(tmp_path):
    payload = json.loads(ALTERNATIVES_PATH.read_text(encoding="utf-8"))
    payload["alternatives"][0]["readiness_contribution"] = 1
    payload["alternatives"][0]["can_replace_original_gate"] = True

    with pytest.raises(SourceAlternativeContractError, match="cannot contribute readiness"):
        audit_source_alternatives(_write_payload(tmp_path, payload))


def test_recommended_alternative_must_be_an_actionable_redesign_route(tmp_path):
    payload = json.loads(ALTERNATIVES_PATH.read_text(encoding="utf-8"))
    payload["recommended_alternative_id"] = "current-pubmed-frozen-surrogate"

    with pytest.raises(SourceAlternativeContractError, match="actionable redesign route"):
        audit_source_alternatives(_write_payload(tmp_path, payload))


def test_alternative_needs_public_evidence_and_explicit_blockers(tmp_path):
    payload = json.loads(ALTERNATIVES_PATH.read_text(encoding="utf-8"))
    payload["alternatives"][0]["blockers"] = []

    with pytest.raises(SourceAlternativeContractError, match="needs a non-empty list"):
        audit_source_alternatives(_write_payload(tmp_path, payload))


def test_alternative_contract_rejects_personal_support_identifiers(tmp_path):
    payload = json.loads(ALTERNATIVES_PATH.read_text(encoding="utf-8"))
    payload["purpose"] += " CAS-private"

    with pytest.raises(SourceAlternativeContractError, match="case identifiers"):
        audit_source_alternatives(_write_payload(tmp_path, payload))


def test_bioasq_public_sample_audit_is_checksum_pinned(tmp_path):
    payload = json.loads(ALTERNATIVES_PATH.read_text(encoding="utf-8"))
    payload["alternatives"][0]["public_sample_audit"]["sha256"] = "0" * 64

    with pytest.raises(SourceAlternativeContractError, match="checksum mismatch"):
        audit_source_alternatives(_write_payload(tmp_path, payload))


def test_bioasq_semantics_protocol_is_frozen_and_checksum_pinned(tmp_path):
    payload = json.loads(ALTERNATIVES_PATH.read_text(encoding="utf-8"))
    payload["alternatives"][0]["semantics_protocol"]["sha256"] = "0" * 64

    with pytest.raises(SourceAlternativeContractError, match="protocol checksum mismatch"):
        audit_source_alternatives(_write_payload(tmp_path, payload))


def test_bioasq_successor_semantics_protocol_is_checksum_pinned(tmp_path):
    payload = json.loads(ALTERNATIVES_PATH.read_text(encoding="utf-8"))
    payload["alternatives"][0]["successor_semantics_protocol"]["sha256"] = "0" * 64

    with pytest.raises(
        SourceAlternativeContractError,
        match="successor protocol checksum mismatch",
    ):
        audit_source_alternatives(_write_payload(tmp_path, payload))


def test_bioasq_semantics_audit_is_checksum_pinned(tmp_path):
    payload = json.loads(ALTERNATIVES_PATH.read_text(encoding="utf-8"))
    payload["alternatives"][0]["semantics_audit"]["sha256"] = "0" * 64

    with pytest.raises(
        SourceAlternativeContractError,
        match="semantics audit checksum mismatch",
    ):
        audit_source_alternatives(_write_payload(tmp_path, payload))


def test_bioasq_pilot_protocol_is_checksum_pinned(tmp_path):
    payload = json.loads(ALTERNATIVES_PATH.read_text(encoding="utf-8"))
    payload["alternatives"][0]["pilot_protocol"]["sha256"] = "0" * 64

    with pytest.raises(
        SourceAlternativeContractError,
        match="BioASQ pilot checksum mismatch",
    ):
        audit_source_alternatives(_write_payload(tmp_path, payload))


def test_bioasq_pilot_compatibility_audit_is_checksum_pinned(tmp_path):
    payload = json.loads(ALTERNATIVES_PATH.read_text(encoding="utf-8"))
    payload["alternatives"][0]["pilot_compatibility_audit"]["sha256"] = "0" * 64

    with pytest.raises(
        SourceAlternativeContractError,
        match="compatibility audit checksum mismatch",
    ):
        audit_source_alternatives(_write_payload(tmp_path, payload))


def test_bioasq_pilot_successor_is_checksum_pinned(tmp_path):
    payload = json.loads(ALTERNATIVES_PATH.read_text(encoding="utf-8"))
    payload["alternatives"][0]["pilot_successor_protocol"]["sha256"] = "0" * 64

    with pytest.raises(SourceAlternativeContractError, match="pilot v2 checksum mismatch"):
        audit_source_alternatives(_write_payload(tmp_path, payload))


def test_bioasq_initial_formula_is_checksum_pinned(tmp_path):
    payload = json.loads(ALTERNATIVES_PATH.read_text(encoding="utf-8"))
    payload["alternatives"][0]["pilot_initial_formula_contract"]["sha256"] = "0" * 64

    with pytest.raises(
        SourceAlternativeContractError,
        match="formula contract checksum mismatch",
    ):
        audit_source_alternatives(_write_payload(tmp_path, payload))


def test_bioasq_development_measurement_is_checksum_pinned(tmp_path):
    payload = json.loads(ALTERNATIVES_PATH.read_text(encoding="utf-8"))
    payload["alternatives"][0]["pilot_development_measurement"]["sha256"] = "0" * 64

    with pytest.raises(
        SourceAlternativeContractError,
        match="development measurement checksum mismatch",
    ):
        audit_source_alternatives(_write_payload(tmp_path, payload))


def test_bioasq_graph_manifest_is_checksum_pinned(tmp_path):
    payload = json.loads(ALTERNATIVES_PATH.read_text(encoding="utf-8"))
    payload["alternatives"][0]["pilot_graph_cache_manifest"]["sha256"] = "0" * 64

    with pytest.raises(
        SourceAlternativeContractError,
        match="graph manifest checksum mismatch",
    ):
        audit_source_alternatives(_write_payload(tmp_path, payload))


def test_bioasq_full_snapshot_audit_is_checksum_pinned(tmp_path):
    payload = json.loads(ALTERNATIVES_PATH.read_text(encoding="utf-8"))
    payload["alternatives"][0]["snapshot_audit"]["sha256"] = "0" * 64

    with pytest.raises(SourceAlternativeContractError, match="snapshot audit checksum mismatch"):
        audit_source_alternatives(_write_payload(tmp_path, payload))
