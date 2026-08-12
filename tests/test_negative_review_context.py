from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

import pytest

from pipeline.benchmark.negative_review_context import (
    OUTPUT_PATH,
    NegativeReviewContextError,
    audit_review_context,
)


def test_committed_review_context_is_pinned_and_zero_readiness():
    audit = audit_review_context()

    assert audit == {
        "entries": 16,
        "queries": 32,
        "sources": 2,
        "readiness_contribution": 0,
    }
    payload = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    assert payload["status"] == "generated_review_aid"
    assert payload["schema_version"] == 2
    assert payload["adjudication_protocol"]["path"].endswith(
        "negative-adjudication-protocol.json"
    )
    assert all(entry["concepts"]["a"]["scope_notes"] for entry in payload["entries"])
    assert all(entry["concepts"]["c"]["scope_notes"] for entry in payload["entries"])
    assert all(len(entry["literature_queries"]) == 2 for entry in payload["entries"])
    assert all(
        query["url"].startswith("https://pubmed.ncbi.nlm.nih.gov/?term=")
        for entry in payload["entries"]
        for query in entry["literature_queries"]
    )
    first = payload["entries"][0]["literature_queries"]
    assert first[0]["query"] == (
        '"Pulmonary Artery"[mh:noexp] AND "Textile Industry"[mh:noexp] '
        "AND 1800/01/01:2011/12/31[dp]"
    )
    assert parse_qs(urlparse(first[0]["url"]).query)["term"] == [first[0]["query"]]
    assert first[1]["query"] == (
        '"Pulmonary Artery"[tiab] AND "Textile Industry"[tiab] '
        "AND 1800/01/01:2011/12/31[dp]"
    )


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


def test_review_context_rejects_query_or_adjudication_protocol_drift(tmp_path):
    payload = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    payload["entries"][0]["literature_queries"][0]["query"] = "changed"
    path = tmp_path / "negative-review-context.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(NegativeReviewContextError, match="literature query contract drift"):
        audit_review_context(path)

    payload = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    payload["adjudication_protocol"]["sha256"] = "0" * 64
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(NegativeReviewContextError, match="pin the adjudication protocol"):
        audit_review_context(path)
