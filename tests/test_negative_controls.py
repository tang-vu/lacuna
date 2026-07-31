from __future__ import annotations

import json

import pytest

from pipeline.benchmark.negative_controls import (
    OUTPUT_PATH,
    PROTOCOL_PATH,
    Descriptor,
    NegativeControlError,
    audit_queue,
    build_queue,
    load_protocol,
)


def _descriptors(year: int) -> tuple[Descriptor, ...]:
    siblings = [
        Descriptor(
            ui=f"D{year % 100:02d}{index:04d}",
            label=f"Sibling {year}-{index}",
            tree_number=f"C01.100.{index:03d}",
        )
        for index in range(1, 9)
    ]
    branches = ["A", "J", "B", "F", "C", "H", "D", "I"]
    distant = [
        Descriptor(
            ui=f"D{(year + 1) % 100:02d}{index:04d}",
            label=f"Branch {branch} {year}",
            tree_number=f"{branch}01.200.{index:03d}",
        )
        for index, branch in enumerate(branches, start=20)
    ]
    return tuple(siblings + distant)


def _sources() -> dict[int, dict]:
    return {
        year: {
            "year": year,
            "url": f"https://example.test/desc{year}.gz",
            "sha256": str(year)[-1] * 64,
            "bytes": year,
            "descriptor_count": 16,
        }
        for year in (2012, 2013)
    }


def test_committed_negative_queue_is_metric_blind_and_zero_readiness():
    audit = audit_queue()

    assert audit == {
        "counts": {"hard_negative": 8, "distant_negative": 8},
        "heldout_counts": {"hard_negative": 4, "distant_negative": 4},
        "readiness_contribution": 0,
    }


def test_frozen_sampler_is_deterministic_and_assigns_balanced_splits():
    protocol = load_protocol()
    descriptor_sets = {year: _descriptors(year) for year in (2012, 2013)}

    first = build_queue(descriptor_sets, protocol, _sources())
    second = build_queue(descriptor_sets, protocol, _sources())

    assert first == second
    assert len(first["candidates"]) == 16
    assert sum(
        candidate["proposed_split"] == "heldout"
        for candidate in first["candidates"]
        if candidate["kind"] == "hard_negative"
    ) == 4
    assert all(candidate["status"] == "proposed" for candidate in first["candidates"])


def test_queue_rejects_metric_output_fields_and_non_sibling_hard_pairs(tmp_path):
    payload = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    payload["candidates"][0]["rank"] = 1
    path = tmp_path / "negative-candidates.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(NegativeControlError, match="metric output fields"):
        audit_queue(path)

    payload = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    hard = next(item for item in payload["candidates"] if item["kind"] == "hard_negative")
    hard["concepts"]["c"]["tree_number"] = "C99.999.001"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(NegativeControlError, match="not sibling"):
        audit_queue(path)


def test_protocol_thresholds_are_load_bearing(tmp_path):
    payload = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    payload["split_assignment"]["required_totals_per_kind"]["heldout"] = 1
    path = tmp_path / "negative-selection.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(NegativeControlError, match="split totals changed"):
        load_protocol(path)


def test_queue_rejects_source_or_split_balance_drift(tmp_path):
    payload = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    payload["sources"][1] = payload["sources"][0]
    path = tmp_path / "negative-candidates.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(NegativeControlError, match="source years"):
        audit_queue(path)

    payload = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    hard = [item for item in payload["candidates"] if item["kind"] == "hard_negative"]
    first_development = next(
        item
        for item in hard
        if item["baseline_release_year"] == 2012 and item["proposed_split"] == "development"
    )
    second_heldout = next(
        item
        for item in hard
        if item["baseline_release_year"] == 2013 and item["proposed_split"] == "heldout"
    )
    first_development["proposed_split"] = "heldout"
    second_heldout["proposed_split"] = "development"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(NegativeControlError, match="unbalanced year/kind/split"):
        audit_queue(path)
