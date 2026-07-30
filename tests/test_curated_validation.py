from __future__ import annotations

import pytest

from pipeline.export.validate_curated import CuratedContentError, validate_entry


def entry_with_source(url: str) -> dict:
    return {
        "id": "test-entry",
        "title": "Test",
        "summary": "A sourced test entry.",
        "sources": [{"label": "Evidence", "url": url}],
    }


def test_external_sources_must_be_https(tmp_path):
    with pytest.raises(CuratedContentError, match="must use HTTPS"):
        validate_entry(
            entry_with_source("http://example.test/source"),
            "open",
            set(),
            tmp_path,
        )


def test_local_sources_must_exist_inside_repo(tmp_path):
    evidence = tmp_path / "evidence.md"
    evidence.write_text("evidence", encoding="utf-8")
    validate_entry(entry_with_source("evidence.md"), "open", set(), tmp_path)

    with pytest.raises(CuratedContentError, match="does not exist"):
        validate_entry(entry_with_source("missing.md"), "open", set(), tmp_path)
    with pytest.raises(CuratedContentError, match="outside the repository"):
        validate_entry(entry_with_source("../outside.md"), "open", set(), tmp_path)


def test_duplicate_source_urls_are_rejected(tmp_path):
    entry = entry_with_source("https://example.test/evidence")
    entry["sources"].append(dict(entry["sources"][0]))

    with pytest.raises(CuratedContentError, match="duplicate source URL"):
        validate_entry(entry, "open", set(), tmp_path)


def test_measured_values_must_be_finite_non_negative_numbers(tmp_path):
    entry = entry_with_source("https://example.test/evidence")
    entry.update({"kind": "coverage", "severity": "partial", "measured": {"count": -1}})

    with pytest.raises(CuratedContentError, match="finite non-negative"):
        validate_entry(entry, "blind-spots", set(), tmp_path)


def test_ids_and_topic_ids_are_structured(tmp_path):
    entry = entry_with_source("https://example.test/evidence")
    entry["id"] = "Not a slug"
    with pytest.raises(CuratedContentError, match="lowercase slug"):
        validate_entry(entry, "open", set(), tmp_path)

    entry = entry_with_source("https://example.test/evidence")
    entry["topics"] = ["not-a-topic"]
    with pytest.raises(CuratedContentError, match="invalid topic id"):
        validate_entry(entry, "open", set(), tmp_path)
