from __future__ import annotations

import json

import pytest

from pipeline.benchmark.validate_sources import (
    SOURCES_PATH,
    SourceContractError,
    audit_sources,
)


def test_current_historical_sources_are_explicitly_not_ready():
    audit = audit_sources()

    assert audit.required_years == (2006, 2010, 2011, 2012)
    assert audit.statuses["historical_records"] == "unavailable"
    assert audit.statuses["historical_vocabulary"] == "available_unpinned"
    assert audit.statuses["current_records"] == "available_unsuitable"
    assert not audit.ready


def test_pinned_status_requires_checksummed_files_for_every_year(tmp_path):
    payload = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    vocabulary = next(
        source for source in payload["sources"] if source["kind"] == "historical_vocabulary"
    )
    vocabulary["status"] = "available_pinned"
    path = tmp_path / "sources.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SourceContractError, match="pinned source needs files"):
        audit_sources(path)


def test_current_records_cannot_replace_historical_records(tmp_path):
    payload = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    current = next(source for source in payload["sources"] if source["kind"] == "current_records")
    current["kind"] = "historical_records"
    current["required_for_shipping"] = True
    path = tmp_path / "sources.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SourceContractError, match="duplicate source kind"):
        audit_sources(path)
