from __future__ import annotations

import json

import pytest

from pipeline.benchmark.negative_review_context import (
    OUTPUT_PATH,
    NegativeReviewContextError,
    audit_review_context,
)


def test_committed_review_context_is_pinned_and_zero_readiness():
    audit = audit_review_context()

    assert audit == {"entries": 16, "sources": 2, "readiness_contribution": 0}
    payload = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    assert payload["status"] == "generated_review_aid"
    assert all(entry["concepts"]["a"]["scope_notes"] for entry in payload["entries"])
    assert all(entry["concepts"]["c"]["scope_notes"] for entry in payload["entries"])


def test_review_context_rejects_queue_and_descriptor_drift(tmp_path):
    payload = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    payload["queue"]["sha256"] = "0" * 64
    path = tmp_path / "negative-review-context.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(NegativeReviewContextError, match="pin the frozen queue"):
        audit_review_context(path)

    payload = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    payload["entries"][0]["concepts"]["a"]["descriptor_label"] = "Changed"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(NegativeReviewContextError, match="descriptor context drift"):
        audit_review_context(path)


def test_review_context_rejects_metric_outputs(tmp_path):
    payload = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    payload["entries"][0]["rank"] = 1
    path = tmp_path / "negative-review-context.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(NegativeReviewContextError, match="metric output fields"):
        audit_review_context(path)

