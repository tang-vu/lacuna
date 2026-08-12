from __future__ import annotations

import json

import pytest

from pipeline.benchmark.validate_bioasq_pilot_v2 import (
    SUCCESSOR_PATH,
    BioasqPilotV2ContractError,
    audit_bioasq_pilot_v2,
)


def _write_successor(tmp_path, payload):
    path = tmp_path / "bioasq-pilot-v2.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_source_informed_successor_preserves_population_and_zero_readiness():
    audit = audit_bioasq_pilot_v2()

    assert audit.status == "frozen_after_source_compatibility_before_metric_formula"
    assert audit.total_cases == 21
    assert audit.development_cases == 11
    assert audit.heldout_cases == 10
    assert audit.primary_support == 10
    assert audit.sensitivity_supports == (5,)
    assert audit.predecessor_blocker_ids == (
        "generated-hard-2012-04-d019956-d019960",
    )
    assert audit.readiness_contribution == 0


def test_successor_must_disclose_that_source_counts_were_seen(tmp_path):
    payload = json.loads(SUCCESSOR_PATH.read_text(encoding="utf-8"))
    payload["freeze_timing"]["case_endpoint_support_counts_seen"] = False

    with pytest.raises(BioasqPilotV2ContractError, match="must disclose"):
        audit_bioasq_pilot_v2(_write_successor(tmp_path, payload))


def test_successor_must_still_precede_every_bioasq_metric_output(tmp_path):
    payload = json.loads(SUCCESSOR_PATH.read_text(encoding="utf-8"))
    payload["freeze_timing"]["bioasq_pilot_heldout_scores_or_ranks_seen"] = True

    with pytest.raises(BioasqPilotV2ContractError, match="not frozen before"):
        audit_bioasq_pilot_v2(_write_successor(tmp_path, payload))


def test_successor_cannot_drop_or_move_a_frozen_case(tmp_path):
    payload = json.loads(SUCCESSOR_PATH.read_text(encoding="utf-8"))
    payload["case_population"]["split_counts"] = {"development": 12, "heldout": 9}

    with pytest.raises(BioasqPilotV2ContractError, match="case population"):
        audit_bioasq_pilot_v2(_write_successor(tmp_path, payload))


def test_successor_support_change_is_load_bearing(tmp_path):
    payload = json.loads(SUCCESSOR_PATH.read_text(encoding="utf-8"))
    payload["source_compatibility"]["support_sensitivity_articles"] = [5, 20]

    with pytest.raises(BioasqPilotV2ContractError, match="support boundary"):
        audit_bioasq_pilot_v2(_write_successor(tmp_path, payload))


def test_successor_cannot_overstate_heldout_independence(tmp_path):
    payload = json.loads(SUCCESSOR_PATH.read_text(encoding="utf-8"))
    payload["case_population"]["heldout_disclosure"] = (
        "Held-out identities and source counts are fully blinded and independent."
    )

    with pytest.raises(BioasqPilotV2ContractError, match="held-out disclosure"):
        audit_bioasq_pilot_v2(_write_successor(tmp_path, payload))


def test_successor_cannot_erase_the_terminal_predecessor(tmp_path):
    payload = json.loads(SUCCESSOR_PATH.read_text(encoding="utf-8"))
    payload["predecessor"]["terminal_status"] = (
        "source_compatible_for_separately_frozen_formula_contract"
    )

    with pytest.raises(BioasqPilotV2ContractError, match="terminal predecessor"):
        audit_bioasq_pilot_v2(_write_successor(tmp_path, payload))


def test_successor_rejects_embedded_metric_output(tmp_path):
    payload = json.loads(SUCCESSOR_PATH.read_text(encoding="utf-8"))
    payload["metric_result"] = {"rank": 1}

    with pytest.raises(BioasqPilotV2ContractError, match="metric output"):
        audit_bioasq_pilot_v2(_write_successor(tmp_path, payload))
