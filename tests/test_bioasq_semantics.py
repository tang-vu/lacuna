from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from pipeline.benchmark.bioasq_semantics import (
    BioasqSemanticsError,
    DEFAULT_AUDIT_PATH,
    PROTOCOL_PATH,
    SUCCESSOR_PROTOCOL_PATH,
    audit_semantics_manifest,
    audit_semantics_sample,
    audit_semantics_protocol,
    compare_semantics_sample,
    select_semantics_sample,
    selection_hash,
)


def _small_protocol(tmp_path: Path) -> tuple[Path, dict]:
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    protocol["sampling"]["strata"] = [
        {
            "id": "y2000",
            "year_min": 2000,
            "year_max": 2000,
            "sample_size": 2,
            "rationale": "Test fixture stratum.",
        }
    ]
    protocol["sampling"]["total_sample_size"] = 2
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(protocol), encoding="utf-8")
    return path, audit_semantics_protocol(path)


def _article(pmid: str) -> dict:
    return {
        "abstractText": "abstract",
        "journal": "journal",
        "meshMajor": ["Alpha", "Beta"],
        "pmid": pmid,
        "title": "title",
        "year": "2000",
    }


def test_sampler_keeps_predeclared_bottom_hashes_independent_of_input_order(tmp_path: Path):
    protocol_path, protocol = _small_protocol(tmp_path)
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(
        json.dumps({"articles": [_article(pmid) for pmid in ("4", "1", "3", "2")]}),
        encoding="utf-8",
    )
    reversed_snapshot = tmp_path / "snapshot-reversed.json"
    reversed_snapshot.write_text(
        json.dumps({"articles": [_article(pmid) for pmid in ("2", "3", "1", "4")]}),
        encoding="utf-8",
    )

    sample = select_semantics_sample(snapshot, protocol_path=protocol_path)
    reversed_sample = select_semantics_sample(reversed_snapshot, protocol_path=protocol_path)

    expected = sorted(
        ("1", "2", "3", "4"),
        key=lambda pmid: (selection_hash(protocol["sampling"]["hash_namespace"], pmid), int(pmid)),
    )[:2]
    assert [record["pmid"] for record in sample["records"]] == expected
    assert [record["pmid"] for record in reversed_sample["records"]] == expected
    assert sample["selection"] == {
        "algorithm": "sha256_bottom_k_per_publication_year_stratum",
        "hash_namespace": "lacuna-bioasq-2013-semantics-v1",
        "records_scanned": 4,
        "verification_records_scanned": 4,
        "records_outside_strata": 0,
        "eligible_counts": {"y2000": 4},
        "selected_counts": {"y2000": 2},
        "selected_total": 2,
        "duplicate_selected_source_records": 0,
        "selected_pmids_with_duplicate_source_records": [],
    }
    assert sample["readiness_contribution"] == 0


def test_sampler_collapses_identical_source_rows_by_frozen_record_key(tmp_path: Path):
    protocol_path, _protocol = _small_protocol(tmp_path)
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(
        json.dumps({"articles": [_article("1"), _article("1"), _article("2")]}),
        encoding="utf-8",
    )

    sample = select_semantics_sample(snapshot, protocol_path=protocol_path)

    assert {record["pmid"] for record in sample["records"]} == {"1", "2"}
    assert sample["selection"]["eligible_counts"] == {"y2000": 3}
    assert sample["selection"]["duplicate_selected_source_records"] == 1
    assert sample["selection"]["selected_pmids_with_duplicate_source_records"] == ["1"]


def test_sampler_rejects_conflicting_rows_for_a_selected_pmid(tmp_path: Path):
    protocol_path, _protocol = _small_protocol(tmp_path)
    conflicting = _article("1")
    conflicting["meshMajor"] = ["Alpha", "Gamma"]
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(
        json.dumps({"articles": [_article("1"), conflicting, _article("2")]}),
        encoding="utf-8",
    )

    with pytest.raises(BioasqSemanticsError, match="conflicting duplicate source records"):
        select_semantics_sample(snapshot, protocol_path=protocol_path)


def test_successor_protocol_adds_only_the_measured_pre_1950_stratum():
    parent = audit_semantics_protocol(PROTOCOL_PATH)
    successor = audit_semantics_protocol(SUCCESSOR_PROTOCOL_PATH)

    assert successor["sampling"]["total_sample_size"] == 448
    assert successor["sampling"]["strata"][1:] == parent["sampling"]["strata"]
    assert successor["comparison"] == parent["comparison"]
    assert successor["decision_rule"] == parent["decision_rule"]
    assert successor["semantics_sample_seen_before_freeze"] is False


def test_successor_protocol_cannot_tune_a_parent_threshold(tmp_path: Path):
    successor = json.loads(SUCCESSOR_PROTOCOL_PATH.read_text(encoding="utf-8"))
    successor["decision_rule"]["consistent_with_all_assigned_descriptors_if"][
        "minimum_all_descriptor_assignment_match_fraction"
    ] = 0.89
    path = tmp_path / "successor.json"
    path.write_text(json.dumps(successor), encoding="utf-8")

    with pytest.raises(BioasqSemanticsError, match="decision thresholds changed"):
        audit_semantics_protocol(path)


def test_committed_semantics_manifest_reconciles_with_the_frozen_rule():
    result = audit_semantics_manifest()

    comparison = result["maintained_current_pubmed_comparison"]
    assert result["classification"] == "sample_consistent_with_all_assigned_descriptors"
    assert result["decision_checks"]["passed"] is True
    assert result["readiness_contribution"] == 0
    assert comparison["records_requested"] == 448
    assert comparison["records_returned"] == 448
    assert comparison["overall"]["bioasq_assignments"] == 5_296
    assert comparison["overall"]["matched_current_all_descriptor_assignments"] == 5_201
    assert comparison["overall"]["matched_current_major_topic_assignments"] == 455


def test_semantics_manifest_cannot_overstate_its_reconciled_counts(tmp_path: Path):
    result = json.loads(DEFAULT_AUDIT_PATH.read_text(encoding="utf-8"))
    result["maintained_current_pubmed_comparison"]["overall"][
        "matched_current_all_descriptor_assignments"
    ] += 1
    path = tmp_path / "semantics-audit.json"
    path.write_text(json.dumps(result), encoding="utf-8")

    with pytest.raises(BioasqSemanticsError, match="overall counts drifted"):
        audit_semantics_manifest(path)


def test_semantics_manifest_rejects_identifying_query_parameters(tmp_path: Path):
    result = json.loads(DEFAULT_AUDIT_PATH.read_text(encoding="utf-8"))
    result["maintained_current_pubmed_comparison"]["batches"][0][
        "source_url"
    ] += "&email="
    path = tmp_path / "semantics-audit.json"
    path.write_text(json.dumps(result), encoding="utf-8")

    with pytest.raises(BioasqSemanticsError, match="identifying parameters"):
        audit_semantics_manifest(path)


@pytest.mark.parametrize("outside_year", ["1999", "undated"])
def test_sampler_rejects_records_outside_frozen_year_strata(
    tmp_path: Path, outside_year: str
):
    protocol_path, _protocol = _small_protocol(tmp_path)
    outside = _article("3")
    outside["year"] = outside_year
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(
        json.dumps({"articles": [_article("1"), _article("2"), outside]}),
        encoding="utf-8",
    )

    with pytest.raises(BioasqSemanticsError, match="outside frozen strata"):
        select_semantics_sample(snapshot, protocol_path=protocol_path)


def _pubmed_payload(pmids: list[str], *, omit_last: bool = False) -> dict:
    returned = pmids[:-1] if omit_last else pmids
    records = [
        {
            "pmid": pmid,
            "mesh_headings": [
                {"descriptor_label": "Alpha", "major_topic": True},
                {"descriptor_label": "Beta", "major_topic": False},
            ],
        }
        for pmid in returned
    ]
    response = json.dumps(records, sort_keys=True).encode("utf-8")
    return {
        "mesh_basis": "maintained_current_pubmed",
        "source_url": f"https://eutils.ncbi.nlm.nih.gov/efetch?ids={','.join(pmids)}",
        "response_sha256": hashlib.sha256(response).hexdigest(),
        "response_bytes": len(response),
        "records": records,
    }


def test_semantics_decision_uses_assignment_counts_and_stays_bounded(tmp_path: Path):
    protocol_path, protocol = _small_protocol(tmp_path)
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(
        json.dumps({"articles": [_article("1"), _article("2")]}), encoding="utf-8"
    )
    sample = select_semantics_sample(snapshot, protocol_path=protocol_path)

    audit = compare_semantics_sample(sample, protocol, _pubmed_payload)

    overall = audit["maintained_current_pubmed_comparison"]["overall"]
    assert audit["classification"] == "sample_consistent_with_all_assigned_descriptors"
    assert audit["readiness_contribution"] == 0
    assert overall["bioasq_assignments"] == 4
    assert overall["matched_current_all_descriptor_assignments"] == 4
    assert overall["matched_current_major_topic_assignments"] == 2
    assert audit["decision_checks"]["passed"] is True
    assert "maintained-current" in " ".join(audit["limitations"])


def test_missing_pubmed_record_keeps_semantics_unresolved(tmp_path: Path):
    protocol_path, protocol = _small_protocol(tmp_path)
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(
        json.dumps({"articles": [_article("1"), _article("2")]}), encoding="utf-8"
    )
    sample = select_semantics_sample(snapshot, protocol_path=protocol_path)

    audit = compare_semantics_sample(
        sample,
        protocol,
        lambda pmids: _pubmed_payload(pmids, omit_last=True),
    )

    assert audit["classification"] == "semantics_unresolved"
    assert audit["decision_checks"]["passed"] is False
    assert len(audit["maintained_current_pubmed_comparison"]["missing_pmids"]) == 1


def test_production_audit_replays_selection_before_any_network_call(tmp_path: Path):
    protocol_path, _protocol = _small_protocol(tmp_path)
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(
        json.dumps({"articles": [_article("1"), _article("2")]}), encoding="utf-8"
    )
    sample = select_semantics_sample(snapshot, protocol_path=protocol_path)
    sample["records"][0]["mesh_labels"] = ["Cherry-picked label"]
    sample_path = tmp_path / "sample.json"
    sample_path.write_text(json.dumps(sample), encoding="utf-8")

    with pytest.raises(BioasqSemanticsError, match="fresh selection"):
        audit_semantics_sample(sample_path, snapshot, protocol_path=protocol_path)
