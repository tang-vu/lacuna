from __future__ import annotations

import gzip
import hashlib
import json

import pytest

from pipeline.benchmark.medline_baseline import (
    HistoricalRecordsNotReady,
    iter_medline_records,
    measure_pairs,
    measure_pinned_release,
    require_pinned_historical_records,
)
from pipeline.benchmark.validate_sources import SOURCES_PATH

A = "D000001"
B = "D000002"
C = "D000003"
SECOND_BRIDGE = "D000004"


def _article(pmid: str, date_xml: str, descriptors: list[str]) -> str:
    headings = "".join(
        "<MeshHeading>"
        f'<DescriptorName UI="{ui}" MajorTopicYN="N">{ui}</DescriptorName>'
        "</MeshHeading>"
        for ui in descriptors
    )
    return (
        "<PubmedArticle><MedlineCitation>"
        f"<PMID>{pmid}</PMID>"
        "<Article><Journal><JournalIssue><PubDate>"
        f"{date_xml}"
        "</PubDate></JournalIssue></Journal></Article>"
        f"<MeshHeadingList>{headings}</MeshHeadingList>"
        "</MedlineCitation></PubmedArticle>"
    )


def _write_fixture(tmp_path):
    articles = [
        _article("1", "<Year>2010</Year>", [A, B, B]),
        _article("2", "<MedlineDate>2010 Winter</MedlineDate>", [C, B]),
        _article("3", "<Year>2010</Year>", [A, C]),
        _article("4", "<Year>2010</Year>", [A, SECOND_BRIDGE]),
        _article("5", "<Year>2010</Year>", [C, SECOND_BRIDGE]),
        _article("6", "<Year>2010</Year>", []),
        _article("7", "<Year>2011</Year>", [A, C, B]),
        _article("8", "", [A, C]),
    ]
    xml = f"<PubmedArticleSet>{''.join(articles)}</PubmedArticleSet>"
    path = tmp_path / "baseline.xml.gz"
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.write(xml)
    return path


def test_stream_parser_handles_gzip_medline_dates_and_duplicate_descriptors(tmp_path):
    records = list(iter_medline_records([_write_fixture(tmp_path)]))

    assert len(records) == 8
    assert records[0].publication_year == 2010
    assert records[0].descriptor_uis == frozenset({A, B})
    assert records[1].publication_year == 2010
    assert records[-1].publication_year is None


def test_pair_measurement_counts_denominator_direct_pair_and_abc_bridges(tmp_path):
    evidence = measure_pairs([_write_fixture(tmp_path)], [(C, A)], cutoff_year=2010)

    assert evidence.indexing_basis == "unverified_medline_xml"
    assert evidence.baseline_release_year is None
    assert evidence.source_contract_sha256 is None
    assert evidence.vocabulary_sha256 is None
    source = evidence.source_files[0]
    assert source.filename == "baseline.xml.gz"
    assert source.sha256 == hashlib.sha256(
        (tmp_path / source.filename).read_bytes()
    ).hexdigest()
    assert source.bytes == (tmp_path / source.filename).stat().st_size
    assert evidence.stats.records_seen == 8
    assert evidence.stats.records_in_cutoff == 6
    assert evidence.stats.records_after_cutoff == 1
    assert evidence.stats.records_missing_year == 1
    assert evidence.stats.records_without_mesh == 1
    pair = evidence.pairs[0]
    assert (pair.left_ui, pair.right_ui) == (A, C)
    assert pair.left_records == 3
    assert pair.right_records == 3
    assert pair.direct_cooccurrence == 1
    assert pair.expected_under_independence == 1.5
    assert [
        (bridge.descriptor_ui, bridge.left_cooccurrence, bridge.right_cooccurrence)
        for bridge in pair.bridges
    ] == [
        (B, 1, 1),
        (SECOND_BRIDGE, 1, 1),
    ]


def test_pair_measurement_rejects_invalid_or_self_pairs(tmp_path):
    path = _write_fixture(tmp_path)

    with pytest.raises(ValueError, match="invalid MeSH descriptor pair"):
        measure_pairs([path], [("not-mesh", C)], cutoff_year=2010)
    with pytest.raises(ValueError, match="endpoints must differ"):
        measure_pairs([path], [(A, A)], cutoff_year=2010)


def test_production_source_gate_rejects_current_unavailable_record_source():
    with pytest.raises(HistoricalRecordsNotReady, match="current PubMed data cannot satisfy"):
        require_pinned_historical_records()


def test_production_source_gate_accepts_only_explicit_pinned_status(tmp_path):
    payload = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    source = next(
        item for item in payload["sources"] if item["kind"] == "historical_records"
    )
    vocabulary = next(
        item for item in payload["sources"] if item["kind"] == "historical_vocabulary"
    )
    source["status"] = "available_pinned"
    source["files"] = [
        {
            "year": item["year"],
            "url": item["url"],
            "sha256": item["sha256"],
            "bytes": item["bytes"],
            "record_count": 1,
        }
        for item in vocabulary["files"]
    ]
    path = tmp_path / "sources.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    require_pinned_historical_records(path)


def test_pinned_release_requires_and_labels_an_exact_complete_file_set(tmp_path):
    fixture = _write_fixture(tmp_path)
    payload = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    records = next(
        item for item in payload["sources"] if item["kind"] == "historical_records"
    )
    records["status"] = "available_pinned"
    digest = hashlib.sha256(fixture.read_bytes()).hexdigest()
    records["files"] = [
        {
            "year": year,
            "url": (
                "https://example.test/baseline.xml.gz"
                if year == 2010
                else f"https://example.test/baseline-{year}.xml.gz"
            ),
            "sha256": digest if year == 2010 else str(year)[-1] * 64,
            "bytes": fixture.stat().st_size if year == 2010 else 1,
            "record_count": 8 if year == 2010 else 1,
        }
        for year in payload["required_baseline_years"]
    ]
    source_path = tmp_path / "sources.json"
    source_path.write_text(json.dumps(payload), encoding="utf-8")

    evidence = measure_pinned_release(
        [fixture],
        [(A, C)],
        baseline_release_year=2010,
        cutoff_year=2010,
        source_path=source_path,
    )

    assert evidence.indexing_basis == "pinned_historical_medline"
    assert evidence.baseline_release_year == 2010
    assert evidence.source_contract_sha256 == hashlib.sha256(
        source_path.read_bytes()
    ).hexdigest()
    vocabulary = next(
        item for item in payload["sources"] if item["kind"] == "historical_vocabulary"
    )
    assert evidence.vocabulary_sha256 == next(
        item["sha256"] for item in vocabulary["files"] if item["year"] == 2010
    )

    renamed = tmp_path / "wrong-name.xml.gz"
    renamed.write_bytes(fixture.read_bytes())
    with pytest.raises(HistoricalRecordsNotReady, match="complete pinned release"):
        measure_pinned_release(
            [renamed],
            [(A, C)],
            baseline_release_year=2010,
            cutoff_year=2010,
            source_path=source_path,
        )

    records["files"][1]["record_count"] = 7
    source_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(HistoricalRecordsNotReady, match="record count"):
        measure_pinned_release(
            [fixture],
            [(A, C)],
            baseline_release_year=2010,
            cutoff_year=2010,
            source_path=source_path,
        )

    with pytest.raises(ValueError, match="later than"):
        measure_pinned_release(
            [fixture],
            [(A, C)],
            baseline_release_year=2010,
            cutoff_year=2011,
            source_path=source_path,
        )
