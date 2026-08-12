from __future__ import annotations

import json

import pytest

from pipeline.benchmark.validate_autonomous_predictions_v1 import (
    MANIFEST_PATH,
    AutonomousPredictionsV1Error,
    audit_predictions_v1,
)


def _mutated(tmp_path, mutate):
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    mutate(payload)
    path = tmp_path / "predictions.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_prediction_seal_is_exhaustive_immutable_and_zero_readiness():
    audit = audit_predictions_v1()

    assert audit.status == "sealed_before_t1"
    assert audit.primary_formula == "adamic_adar_q48"
    assert audit.backbone_edge_count == 31_760_211
    assert audit.candidate_score_count == 7_310_895
    assert audit.nonzero_score_count == 7_310_826
    assert audit.readiness_contribution == 0
    assert audit.local_bytes_verified is False


def test_prediction_seal_rejects_measurement_or_artifact_drift(tmp_path):
    measurement_path = _mutated(
        tmp_path,
        lambda payload: payload["measurements"].update(backbone_edges=1),
    )
    with pytest.raises(AutonomousPredictionsV1Error, match="manifest identity"):
        audit_predictions_v1(measurement_path)

    artifact_path = _mutated(
        tmp_path,
        lambda payload: payload["artifacts"]["candidate_scores"].update(bytes=1),
    )
    with pytest.raises(AutonomousPredictionsV1Error, match="manifest identity"):
        audit_predictions_v1(artifact_path)


def test_prediction_seal_rejects_readiness_or_claim_overreach(tmp_path):
    readiness_path = _mutated(tmp_path, lambda payload: payload.update(readiness_contribution=1))
    with pytest.raises(AutonomousPredictionsV1Error, match="manifest identity"):
        audit_predictions_v1(readiness_path)

    claim_path = _mutated(tmp_path, lambda payload: payload.update(claim_boundary="discoveries"))
    with pytest.raises(AutonomousPredictionsV1Error, match="manifest identity"):
        audit_predictions_v1(claim_path)
