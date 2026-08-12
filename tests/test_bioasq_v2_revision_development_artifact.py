from __future__ import annotations

import json

import pytest

from pipeline.benchmark.validate_bioasq_v2_revision_development import (
    REVISION_DEVELOPMENT_PATH,
    BioasqV2RevisionDevelopmentError,
    audit_bioasq_v2_revision_development,
)


def _payload():
    return json.loads(REVISION_DEVELOPMENT_PATH.read_text(encoding="utf-8"))


def _write_output(tmp_path, payload):
    path = tmp_path / "revision-development.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_committed_revision_measurement_fails_and_terminates_before_heldout():
    audit = audit_bioasq_v2_revision_development()

    assert audit.status == "revision_development_gate_failed_terminate_before_heldout"
    assert audit.case_count == 11
    assert audit.heldout_case_count_computed == 0
    assert audit.primary_positive_top5 == 1
    assert audit.primary_hard_top5 == 1
    assert audit.primary_distant_below_median == 1
    assert audit.gate_passed is False
    assert audit.mechanical_action == "terminate_pilot_before_heldout"
    assert audit.readiness_contribution == 0


def test_revision_artifact_cannot_claim_heldout_execution(tmp_path):
    payload = _payload()
    payload["execution_isolation"]["heldout_case_count_computed"] = 1

    with pytest.raises(BioasqV2RevisionDevelopmentError, match="held-out isolation"):
        audit_bioasq_v2_revision_development(_write_output(tmp_path, payload))


def test_revision_population_is_load_bearing(tmp_path):
    payload = _payload()
    payload["cases"][0]["id"] = "substituted-case"

    with pytest.raises(BioasqV2RevisionDevelopmentError, match="population or order"):
        audit_bioasq_v2_revision_development(_write_output(tmp_path, payload))


def test_revision_direct_penalty_is_load_bearing(tmp_path):
    payload = _payload()
    payload["cases"][0]["support_runs"][0]["target_direct_penalty"] += 1

    with pytest.raises(BioasqV2RevisionDevelopmentError, match="direct penalty drifted"):
        audit_bioasq_v2_revision_development(_write_output(tmp_path, payload))


def test_revision_decimal_division_is_load_bearing(tmp_path):
    payload = _payload()
    payload["cases"][0]["support_runs"][0][
        "target_revised_decimal_before_quantization"
    ] = "0.5"

    with pytest.raises(BioasqV2RevisionDevelopmentError, match="Decimal arithmetic"):
        audit_bioasq_v2_revision_development(_write_output(tmp_path, payload))


def test_revision_rank_proof_is_load_bearing(tmp_path):
    payload = _payload()
    payload["cases"][0]["support_runs"][0]["rank_proof"][
        "bound_proven_below_count"
    ] -= 1

    with pytest.raises(BioasqV2RevisionDevelopmentError, match="rank proof"):
        audit_bioasq_v2_revision_development(_write_output(tmp_path, payload))


def test_revision_summary_must_recompute_from_cases(tmp_path):
    payload = _payload()
    payload["revision_development_summary"]["10"]["hard_negative"][
        "top_5_percent_count"
    ] = 0

    with pytest.raises(BioasqV2RevisionDevelopmentError, match="summary drifted"):
        audit_bioasq_v2_revision_development(_write_output(tmp_path, payload))


def test_failed_gate_cannot_be_recast_as_pass(tmp_path):
    payload = _payload()
    payload["pre_registered_revision_development_decision"][
        "pre_registered_gate_passed"
    ] = True
    payload["pre_registered_revision_development_decision"]["mechanical_action"] = (
        "freeze_exact_revision_as_final_before_heldout"
    )

    with pytest.raises(BioasqV2RevisionDevelopmentError, match="gate decision drifted"):
        audit_bioasq_v2_revision_development(_write_output(tmp_path, payload))


def test_revision_failure_cannot_promote_readiness(tmp_path):
    payload = _payload()
    payload["readiness_contribution"] = 1

    with pytest.raises(BioasqV2RevisionDevelopmentError, match="readiness drifted"):
        audit_bioasq_v2_revision_development(_write_output(tmp_path, payload))
