from __future__ import annotations

import gzip
import json
import zipfile
from pathlib import Path

import pytest

from pipeline.benchmark.bioasq_snapshot import (
    BioasqSnapshotError,
    iter_articles,
    measure_snapshot,
)


def _write_mesh(path: Path) -> Path:
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<DescriptorRecordSet>
  <DescriptorRecord>
    <DescriptorUI>D000001</DescriptorUI>
    <DescriptorName><String>Calcimycin</String></DescriptorName>
  </DescriptorRecord>
  <DescriptorRecord>
    <DescriptorUI>D000002</DescriptorUI>
    <DescriptorName><String>Temefos</String></DescriptorName>
  </DescriptorRecord>
</DescriptorRecordSet>
"""
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        stream.write(xml)
    return path


def _articles() -> list[dict]:
    return [
        {
            "abstractText": "Text with a brace } and an escaped quote: \\\"yes\\\".",
            "journal": "Journal A",
            "meshMajor": ["Calcimycin", "Temefos"],
            "pmid": "1",
            "title": "First",
            "year": "1950",
        },
        {
            "abstractText": "Second abstract",
            "journal": "Journal B",
            "meshMajor": ["Calcimycin"],
            "pmid": "2",
            "title": "Second",
            "year": "2013",
        },
    ]


def _write_snapshot(path: Path) -> Path:
    path.write_text(json.dumps({"articles": _articles()}), encoding="utf-8")
    return path


def test_streaming_measurement_validates_fields_and_mesh_labels(tmp_path):
    snapshot = _write_snapshot(tmp_path / "training.json")
    mesh = _write_mesh(tmp_path / "desc2013.gz")

    measured = measure_snapshot(snapshot, mesh_path=mesh)

    assert measured.article_count == 2
    assert measured.mesh_assignment_count == 3
    assert measured.distinct_mesh_label_count == 2
    assert measured.publication_year_min == 1950
    assert measured.publication_year_max == 2013
    assert measured.articles_without_mesh_labels == 0
    assert measured.unknown_mesh_labels == ()


def test_streaming_reader_supports_a_single_json_member_zip(tmp_path):
    snapshot = tmp_path / "training.zip"
    with zipfile.ZipFile(snapshot, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("raw_training_set.json", json.dumps({"articles": _articles()}))
    mesh = _write_mesh(tmp_path / "desc2013.gz")

    assert measure_snapshot(snapshot, mesh_path=mesh).article_count == 2


def test_streaming_reader_does_not_treat_braces_inside_strings_as_objects(tmp_path):
    snapshot = _write_snapshot(tmp_path / "training.json")

    with snapshot.open(encoding="utf-8") as stream:
        articles = list(iter_articles(stream))

    assert articles == _articles()


def test_streaming_reader_rejects_missing_array_comma(tmp_path):
    first, second = (json.dumps(item) for item in _articles())
    snapshot = tmp_path / "broken.json"
    snapshot.write_text(f'{{"articles":[{first}{second}]}}', encoding="utf-8")
    mesh = _write_mesh(tmp_path / "desc2013.gz")

    with pytest.raises(BioasqSnapshotError, match="comma-separated"):
        measure_snapshot(snapshot, mesh_path=mesh)


def test_measurement_reports_labels_absent_from_pinned_vocabulary(tmp_path):
    payload = _articles()
    payload[0]["meshMajor"].append("Not a 2013 descriptor")
    snapshot = tmp_path / "training.json"
    snapshot.write_text(json.dumps({"articles": payload}), encoding="utf-8")
    mesh = _write_mesh(tmp_path / "desc2013.gz")

    measured = measure_snapshot(snapshot, mesh_path=mesh)

    assert measured.unknown_mesh_labels == ("Not a 2013 descriptor",)
