from __future__ import annotations

import json

import pytest

from pipeline.benchmark.validate_negative_adjudication_protocol import (
    ADJUDICATION_PROTOCOL_PATH,
    NegativeAdjudicationProtocolError,
    audit_negative_adjudication_protocol,
)


def test_committed_negative_adjudication_protocol_is_bounded_and_zero_readiness():
    audit = audit_negative_adjudication_protocol()

    assert audit.status == "frozen_before_human_adjudication_after_bioasq_terminal_result"
    assert audit.common_check_count == 5
    assert audit.hard_check_count == 3
    assert audit.distant_check_count == 3
    assert audit.metric_v3_blind is True
    assert audit.bioasq_output_disclosed is True
    assert audit.readiness_contribution == 0


def test_protocol_rejects_hidden_bioasq_timing_or_input_drift(tmp_path):
    payload = json.loads(ADJUDICATION_PROTOCOL_PATH.read_text(encoding="utf-8"))
    payload["authoring_timing"]["bioasq_v2_pilot_outputs_seen"] = False
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(NegativeAdjudicationProtocolError, match="BioASQ disclosure"):
        audit_negative_adjudication_protocol(path)

    payload = json.loads(ADJUDICATION_PROTOCOL_PATH.read_text(encoding="utf-8"))
    payload["inputs"]["candidate_queue"]["sha256"] = "0" * 64
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(NegativeAdjudicationProtocolError, match="input identities"):
        audit_negative_adjudication_protocol(path)


def test_protocol_keeps_hard_and_distant_review_constructs_distinct(tmp_path):
    payload = json.loads(ADJUDICATION_PROTOCOL_PATH.read_text(encoding="utf-8"))
    payload["kind_specific_review_checks"]["hard_negative"][0] = (
        "Reject substantively related concepts because controls must be unrelated in every sense."
    )
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(NegativeAdjudicationProtocolError, match="relatedness rule"):
        audit_negative_adjudication_protocol(path)


def test_protocol_cannot_smuggle_a_candidate_metric_output(tmp_path):
    payload = json.loads(ADJUDICATION_PROTOCOL_PATH.read_text(encoding="utf-8"))
    payload["candidate_score"] = 0.5
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(NegativeAdjudicationProtocolError, match="metric output fields"):
        audit_negative_adjudication_protocol(path)
