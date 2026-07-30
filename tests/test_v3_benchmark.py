from __future__ import annotations

import json

import pytest

from pipeline.benchmark.validate_v3 import (
    BENCHMARK_PATH,
    BenchmarkContractError,
    audit_benchmark,
)


def test_current_v3_benchmark_is_an_explicitly_incomplete_draft():
    audit = audit_benchmark()

    assert audit.counts == {
        "positive": 2,
        "hard_negative": 0,
        "distant_negative": 0,
    }
    assert sum(audit.heldout_counts.values()) == 0
    assert audit.mapping_counts["maintained_current"] == 4
    assert not audit.ready
    assert "benchmark status is draft" in audit.readiness_blockers
    assert not audit.period_appropriate_heldout_cutoffs


def test_case_selection_rejects_metric_outputs(tmp_path):
    payload = json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))
    payload["cases"][0]["score"] = 0.99
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(BenchmarkContractError, match="metric output fields"):
        audit_benchmark(path)


def test_period_appropriate_mapping_requires_pinned_archived_baseline(tmp_path):
    payload = json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))
    mapping = payload["cases"][0]["concepts"]["a"]["mapping"]
    mapping["status"] = "period_appropriate"
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(BenchmarkContractError, match="archived baseline identity"):
        audit_benchmark(path)


def test_readiness_thresholds_cannot_be_lowered_in_the_case_file(tmp_path):
    payload = json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))
    payload["requirements"]["minimum_per_kind"] = 1
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(BenchmarkContractError, match="readiness requirements must remain"):
        audit_benchmark(path)
