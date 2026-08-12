from __future__ import annotations

import json

import pytest

from pipeline.benchmark.validate_autonomous_candidate_universe import (
    MANIFEST_PATH,
    AutonomousCandidateUniverseError,
    audit_candidate_universe,
)


def _mutated(tmp_path, mutate):
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    mutate(payload)
    path = tmp_path / "candidate-universe.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_candidate_universe_manifest_is_exact_score_free_and_zero_readiness():
    audit = audit_candidate_universe()

    assert audit.distinct_pmid_count == 39_994_988
    assert audit.descriptor_count == 31_110
    assert audit.positive_pair_count == 51_128_229
    assert audit.candidate_pair_count == 7_310_895
    assert audit.readiness_contribution == 0
    assert audit.local_bytes_verified is False


def test_candidate_universe_rejects_count_or_artifact_shape_drift(tmp_path):
    count_path = _mutated(tmp_path, lambda payload: payload["counts"].update(candidate_pairs=1))
    with pytest.raises(AutonomousCandidateUniverseError, match="artifact identity drifted"):
        audit_candidate_universe(count_path)

    shape_path = _mutated(
        tmp_path,
        lambda payload: payload["artifacts"]["candidate_stream"].update(bytes=1),
    )
    with pytest.raises(AutonomousCandidateUniverseError, match="artifact shape drifted"):
        audit_candidate_universe(shape_path)


def test_candidate_universe_rejects_metric_or_claim_boundary_overreach(tmp_path):
    score_path = _mutated(tmp_path, lambda payload: payload.update(score=0.5))
    with pytest.raises(AutonomousCandidateUniverseError, match="metric or generated fields"):
        audit_candidate_universe(score_path)

    claim_path = _mutated(tmp_path, lambda payload: payload.update(claim_boundary="discoveries"))
    with pytest.raises(AutonomousCandidateUniverseError, match="claim boundary"):
        audit_candidate_universe(claim_path)
