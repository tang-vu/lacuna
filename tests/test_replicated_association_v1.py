from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np
import pytest

from pipeline.evidence.replicated_association_v1 import (
    PROTOCOL_PATH,
    P_VALUE_FLOOR,
    EvidenceV1Error,
    _gate_pairs,
    _rho_p_values,
    _write_new_json,
    audit_protocol,
    benjamini_hochberg,
    parse_expression_values,
    standardised_rank_rows,
)


def _mutated(tmp_path: Path, mutate) -> Path:
    payload = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    mutate(payload)
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_frozen_protocol_is_valid_and_has_no_human_or_llm_gate():
    payload = audit_protocol()

    assert payload["human_dependencies"] == []
    assert payload["manual_override_allowed"] is False
    assert payload["llm_interpretation_authorized"] is False
    assert payload["candidate_universe"]["uses_expression_values"] is False
    assert payload["readiness_contribution"] == 0


def test_protocol_rejects_human_dependency_and_overclaim(tmp_path):
    human = _mutated(tmp_path, lambda payload: payload["human_dependencies"].append("reviewer"))
    with pytest.raises(EvidenceV1Error, match="human dependency"):
        audit_protocol(human)

    def remove_boundary(payload):
        payload["claim_boundary"]["not_a_claim_of"].remove("novelty to humanity")

    overclaim = _mutated(tmp_path, remove_boundary)
    with pytest.raises(EvidenceV1Error, match="overclaiming"):
        audit_protocol(overclaim)


def test_protocol_rejects_threshold_or_source_identity_drift(tmp_path):
    threshold = _mutated(
        tmp_path,
        lambda payload: payload["machine_gates"].update(minimum_absolute_rho_per_cohort=0.1),
    )
    with pytest.raises(EvidenceV1Error, match="gates drifted"):
        audit_protocol(threshold)

    source = _mutated(tmp_path, lambda payload: payload["sources"][0].update(sha256="0" * 64))
    with pytest.raises(EvidenceV1Error, match="implementation identity|source"):
        audit_protocol(source)


def test_average_tie_spearman_rows_are_standardised_and_constant_is_censored():
    matrix = np.asarray(
        [
            [1.0, 2.0, 2.0, 4.0],
            [4.0, 2.0, 2.0, 1.0],
            [3.0, 3.0, 3.0, 3.0],
        ]
    )

    ranked, usable = standardised_rank_rows(matrix)

    assert usable.tolist() == [True, True, False]
    assert np.dot(ranked[0], ranked[0]) == pytest.approx(1.0)
    assert np.dot(ranked[0], ranked[1]) == pytest.approx(-1.0)
    assert ranked[2].tolist() == [0.0, 0.0, 0.0, 0.0]


def test_declared_missing_expression_values_are_parsed_then_censored():
    parsed = parse_expression_values(["1.5", "NA", "NaN", ""], context="fixture")
    assert parsed[0] == 1.5
    assert np.isnan(parsed[1:]).all()

    ranked, usable = standardised_rank_rows(parsed.reshape(1, -1))
    assert usable.tolist() == [False]
    assert ranked.tolist() == [[0.0, 0.0, 0.0, 0.0]]

    with pytest.raises(EvidenceV1Error, match="unrecognised expression value"):
        parse_expression_values(["not-a-number"], context="fixture")


def test_benjamini_hochberg_and_replication_gate_are_mechanical():
    q_values = benjamini_hochberg(np.asarray([0.01, 0.04, 0.03, 0.002]))
    assert q_values.tolist() == pytest.approx([0.02, 0.04, 0.04, 0.008])

    gates = audit_protocol()["machine_gates"]
    passed = _gate_pairs(
        np.asarray([0.50, 0.50, 0.50, -0.60]),
        np.asarray([0.45, -0.45, 0.20, -0.50]),
        np.asarray([0.001, 0.001, 0.001, 0.001]),
        np.asarray([0.001, 0.001, 0.001, 0.001]),
        gates,
    )
    assert passed.tolist() == [True, False, False, True]


def test_extreme_p_values_are_conservative_positive_bounds_not_zero():
    p_values, floor_count = _rho_p_values(np.asarray([0.99999999, 0.0]), sample_count=1980)

    assert floor_count == 1
    assert p_values[0] == P_VALUE_FLOOR
    assert p_values[1] == pytest.approx(1.0)


def test_sealed_json_writer_refuses_overwrite(tmp_path):
    path = tmp_path / "sealed.json"
    _write_new_json(path, {"first": True})

    with pytest.raises(EvidenceV1Error, match="refusing to overwrite"):
        _write_new_json(path, {"first": False})

    assert json.loads(path.read_text(encoding="utf-8")) == {"first": True}
