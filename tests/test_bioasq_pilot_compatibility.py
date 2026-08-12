from __future__ import annotations

import json

import pytest

from pipeline.benchmark.bioasq_pilot_compatibility import (
    MANIFEST_PATH,
    BioasqCompatibilityError,
    _measure_snapshot,
    _source_decision,
    audit_compatibility_manifest,
)


def _article(pmid: int, year: int, labels: list[str]) -> dict:
    return {
        "abstractText": "Abstract",
        "journal": "Journal",
        "meshMajor": labels,
        "pmid": str(pmid),
        "title": "Title",
        "year": str(year),
    }


def _write_snapshot(tmp_path, articles: list[dict]):
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps({"articles": articles}), encoding="utf-8")
    return path


def _write_manifest(tmp_path, payload: dict):
    path = tmp_path / "bioasq-pilot-compatibility.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_committed_source_compatibility_manifest_records_the_frozen_sensitivity_blocker():
    audit = audit_compatibility_manifest()

    assert audit == {
        "status": "primary_source_compatible_but_sensitivity_20_unevaluable",
        "case_count": 21,
        "incompatible_case_ids": [],
        "readiness_contribution": 0,
    }


def test_compatibility_manifest_rejects_metric_output_fields(tmp_path):
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    payload["measurement"]["cases"][0]["score"] = 0.5

    with pytest.raises(BioasqCompatibilityError, match="metric output"):
        audit_compatibility_manifest(_write_manifest(tmp_path, payload))


def test_compatibility_manifest_cannot_hide_the_sensitivity_blocker(tmp_path):
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    payload["decision"]["heldout_sensitivity_evaluable"]["20"] = True
    payload["decision"]["heldout_sensitivity_blockers"]["20"] = []
    payload["decision"]["frozen_heldout_rule_can_still_pass"] = True
    payload["decision"]["metric_work_authorized_by_this_audit"] = True

    with pytest.raises(BioasqCompatibilityError, match="decision drifted"):
        audit_compatibility_manifest(_write_manifest(tmp_path, payload))


def test_score_free_measurement_counts_cutoffs_support_and_required_pairs(tmp_path):
    snapshot = _write_snapshot(
        tmp_path,
        [
            _article(1, 2005, ["Alpha", "Beta"]),
            _article(2, 2008, ["Alpha", "Gamma"]),
            _article(3, 2011, ["Beta", "Gamma"]),
            _article(4, 2012, ["Alpha", "Beta", "Gamma"]),
            _article(5, 2013, ["Alpha"]),
        ],
    )

    measured = _measure_snapshot(
        snapshot,
        label_index={"alpha": "D1", "beta": "D2", "gamma": "D3"},
        required_pairs={("D1", "D2"), ("D1", "D3"), ("D2", "D3")},
    )

    assert measured["article_count"] == 5
    assert measured["mesh_assignment_count"] == 10
    assert measured["articles_after_last_cutoff"] == 1
    assert measured["included_articles"] == {2006: 1, 2010: 2, 2011: 3, 2012: 4}
    assert [measured["support"][year]["D1"] for year in (2006, 2010, 2011, 2012)] == [
        1,
        2,
        2,
        3,
    ]
    assert [
        measured["pair_counts"][year][("D1", "D2")]
        for year in (2006, 2010, 2011, 2012)
    ] == [1, 1, 1, 2]
    assert [
        measured["pair_counts"][year][("D1", "D3")]
        for year in (2006, 2010, 2011, 2012)
    ] == [0, 1, 1, 2]
    assert [
        measured["pair_counts"][year][("D2", "D3")]
        for year in (2006, 2010, 2011, 2012)
    ] == [0, 0, 1, 2]


def test_score_free_measurement_enforces_binary_descriptor_articles(tmp_path):
    snapshot = _write_snapshot(tmp_path, [_article(1, 2005, ["Alpha", " alpha "])])

    with pytest.raises(BioasqCompatibilityError, match="duplicate descriptor"):
        _measure_snapshot(
            snapshot,
            label_index={"alpha": "D1"},
            required_pairs=set(),
        )


def test_source_decision_uses_all_cases_and_never_adds_readiness():
    cases = [
        {
            "id": f"case-{index}",
            "split": "heldout" if index < 10 else "development",
            "primary_source_compatible": True,
            "support_eligibility": {
                str(threshold): {
                    "endpoint_a_eligible": True,
                    "target_c_eligible": True,
                }
                for threshold in (5, 10, 20)
            },
        }
        for index in range(21)
    ]

    decision = _source_decision(cases, "pilot_inconclusive_source_coverage")

    assert decision["status"] == "source_compatible_for_separately_frozen_formula_contract"
    assert decision["all_21_cases_primary_source_compatible"] is True
    assert decision["incompatible_case_ids"] == []
    assert decision["frozen_heldout_rule_can_still_pass"] is True
    assert decision["metric_work_authorized_by_this_audit"] is True
    assert decision["readiness_contribution"] == 0


def test_source_decision_is_inconclusive_without_replacing_a_low_support_case():
    cases = [
        {
            "id": f"case-{index}",
            "split": "heldout" if index < 10 else "development",
            "primary_source_compatible": index != 7,
            "support_eligibility": {
                str(threshold): {
                    "endpoint_a_eligible": index != 7,
                    "target_c_eligible": True,
                }
                for threshold in (5, 10, 20)
            },
        }
        for index in range(21)
    ]

    decision = _source_decision(cases, "pilot_inconclusive_source_coverage")

    assert decision["status"] == "pilot_inconclusive_source_coverage"
    assert decision["incompatible_case_ids"] == ["case-7"]
    assert decision["metric_work_authorized_by_this_audit"] is False
    assert decision["readiness_contribution"] == 0


def test_source_decision_stops_before_metric_when_frozen_sensitivity_is_unevaluable():
    cases = [
        {
            "id": f"case-{index}",
            "split": "heldout" if index < 10 else "development",
            "primary_source_compatible": True,
            "support_eligibility": {
                "5": {"endpoint_a_eligible": True, "target_c_eligible": True},
                "10": {"endpoint_a_eligible": True, "target_c_eligible": True},
                "20": {
                    "endpoint_a_eligible": True,
                    "target_c_eligible": index != 4,
                },
            },
        }
        for index in range(21)
    ]

    decision = _source_decision(cases, "pilot_inconclusive_source_coverage")

    assert decision["primary_source_gate_status"] == (
        "source_compatible_for_separately_frozen_formula_contract"
    )
    assert decision["status"] == (
        "primary_source_compatible_but_sensitivity_20_unevaluable"
    )
    assert decision["heldout_sensitivity_blockers"]["20"] == ["case-4"]
    assert decision["frozen_heldout_rule_can_still_pass"] is False
    assert decision["metric_work_authorized_by_this_audit"] is False
