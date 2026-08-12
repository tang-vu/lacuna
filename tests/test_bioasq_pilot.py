from __future__ import annotations

import json

import pytest

from pipeline.benchmark.validate_bioasq_pilot import (
    PILOT_PATH,
    BioasqPilotContractError,
    audit_bioasq_pilot,
)


def _write_protocol(tmp_path, payload):
    path = tmp_path / "bioasq-pilot.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_frozen_bioasq_pilot_has_a_complete_zero_readiness_population():
    audit = audit_bioasq_pilot()

    assert audit.status == "frozen_before_bioasq_pilot_metric"
    assert audit.positive_counts == {"development": 3, "heldout": 2}
    assert audit.control_counts == {
        "hard_negative": {"development": 4, "heldout": 4},
        "distant_negative": {"development": 4, "heldout": 4},
    }
    assert audit.total_cases == 21
    assert audit.unique_mapping_count == 46
    assert audit.readiness_contribution == 0


def test_pilot_cannot_claim_support_was_unseen_after_inspecting_it(tmp_path):
    payload = json.loads(PILOT_PATH.read_text(encoding="utf-8"))
    payload["freeze_timing"]["case_endpoint_support_counts_seen"] = True

    with pytest.raises(BioasqPilotContractError, match="not frozen before"):
        audit_bioasq_pilot(_write_protocol(tmp_path, payload))


def test_pilot_positive_heldout_split_is_hash_frozen(tmp_path):
    payload = json.loads(PILOT_PATH.read_text(encoding="utf-8"))
    payload["case_population"]["positives"]["cases"][0]["split"] = "heldout"

    with pytest.raises(BioasqPilotContractError, match="positive case identity"):
        audit_bioasq_pilot(_write_protocol(tmp_path, payload))


def test_pilot_cannot_drop_a_control_after_source_freeze(tmp_path):
    payload = json.loads(PILOT_PATH.read_text(encoding="utf-8"))
    payload["case_population"]["controls"]["ids_by_kind_and_split"]["hard_negative"][
        "heldout"
    ].pop()

    with pytest.raises(BioasqPilotContractError, match="complete pinned control queue"):
        audit_bioasq_pilot(_write_protocol(tmp_path, payload))


def test_pilot_heldout_thresholds_are_load_bearing(tmp_path):
    payload = json.loads(PILOT_PATH.read_text(encoding="utf-8"))
    payload["heldout_decision_rule"]["positive_requirement"] = (
        "At least 0 of 2 held-out positives ranks anywhere."
    )

    with pytest.raises(BioasqPilotContractError, match="decision rule drifted"):
        audit_bioasq_pilot(_write_protocol(tmp_path, payload))
