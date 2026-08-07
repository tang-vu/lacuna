from __future__ import annotations

import json

import pytest

from pipeline.benchmark.validate_v3 import (
    BENCHMARK_PATH,
    BenchmarkContractError,
    audit_benchmark,
)
from pipeline.benchmark.validate_candidates import CANDIDATES_PATH, audit_candidates
from pipeline.benchmark.negative_controls import OUTPUT_PATH as NEGATIVE_QUEUE_PATH


def _benchmark_with_negative() -> tuple[dict, dict]:
    payload = json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))
    queue = json.loads(NEGATIVE_QUEUE_PATH.read_text(encoding="utf-8"))
    proposal = next(
        item for item in queue["candidates"] if item["kind"] == "hard_negative"
    )
    payload["cases"].append(
        {
            "id": "reviewed-hard-negative",
            "kind": proposal["kind"],
            "split": proposal["proposed_split"],
            "cutoff": proposal["cutoff"],
            "selection_stage": "pre_metric",
            "selection_candidate_id": proposal["id"],
            "selection_rationale": (
                "Accepted after metric-blind review of the frozen generated proposal."
            ),
            "negative_rationale": (
                "The pair is an ontology-sibling confounder selected before metric v3."
            ),
            "evidence": [
                {
                    "role": "negative_selection_source",
                    "label": "Frozen metric-blind negative-control queue",
                    "url": (
                        "https://github.com/tang-vu/lacuna/blob/"
                        "e33d6c297ed09c5ff4edf7eacdaa51effcdca319/"
                        "artifacts/negative-candidates.json"
                    ),
                },
                {
                    "role": "metric_blind_adjudication",
                    "label": "Public review decision",
                    "url": "https://github.com/tang-vu/lacuna/issues/4#issuecomment-1",
                },
            ],
            "concepts": {
                role: {
                    "label": proposal["concepts"][role]["descriptor_label"],
                    "mapping": {
                        "status": "unavailable",
                        "note": "Historical citation records are not pinned yet.",
                    },
                }
                for role in ("a", "c")
            },
        }
    )
    return payload, proposal


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


def test_reviewed_negative_satisfies_both_separate_intake_contracts(tmp_path):
    payload, _proposal = _benchmark_with_negative()
    benchmark_path = tmp_path / "cases.json"
    benchmark_path.write_text(json.dumps(payload), encoding="utf-8")

    benchmark = audit_benchmark(benchmark_path)
    positives = audit_candidates(CANDIDATES_PATH, benchmark_path)

    assert benchmark.counts["hard_negative"] == 1
    assert set(positives.accepted_benchmark_ids) == {
        "swanson-fish-oil-raynaud",
        "swanson-magnesium-migraine",
    }


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


def test_negative_case_reconciles_with_frozen_metric_blind_proposal(tmp_path):
    payload, proposal = _benchmark_with_negative()
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    audit = audit_benchmark(path)

    assert audit.counts[proposal["kind"]] == 1


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("selection_candidate_id", "not-in-the-queue", "unknown negative proposal"),
        ("split", "heldout", "split differs from frozen proposal"),
        ("cutoff", "2010-12-31", "cutoff differs from frozen proposal"),
        ("kind", "distant_negative", "kind differs from frozen proposal"),
    ],
)
def test_negative_case_rejects_lineage_drift(tmp_path, field, value, message):
    payload, _ = _benchmark_with_negative()
    payload["cases"][-1][field] = value
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(BenchmarkContractError, match=message):
        audit_benchmark(path)


def test_negative_case_rejects_descriptor_or_adjudication_drift(tmp_path):
    payload, _ = _benchmark_with_negative()
    payload["cases"][-1]["concepts"]["a"]["label"] = "Hand-picked replacement"
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(BenchmarkContractError, match="concept a differs from frozen proposal"):
        audit_benchmark(path)

    payload, _ = _benchmark_with_negative()
    payload["cases"][-1]["evidence"] = payload["cases"][-1]["evidence"][:1]
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(BenchmarkContractError, match="metric-blind adjudication"):
        audit_benchmark(path)

    payload, _ = _benchmark_with_negative()
    payload["cases"][-1]["evidence"][-1]["url"] = (
        "https://github.com/tang-vu/lacuna/issues/3#issuecomment-1"
    )
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(BenchmarkContractError, match="metric-blind adjudication"):
        audit_benchmark(path)


def test_negative_case_rejects_an_unauditable_queue(tmp_path):
    payload, _ = _benchmark_with_negative()
    benchmark_path = tmp_path / "cases.json"
    benchmark_path.write_text(json.dumps(payload), encoding="utf-8")
    queue = json.loads(NEGATIVE_QUEUE_PATH.read_text(encoding="utf-8"))
    queue["candidates"][0]["rank"] = 1
    queue_path = tmp_path / "negative-candidates.json"
    queue_path.write_text(json.dumps(queue), encoding="utf-8")

    with pytest.raises(BenchmarkContractError, match="negative queue"):
        audit_benchmark(benchmark_path, negative_queue_path=queue_path)
