from __future__ import annotations

import gzip
import json
import sys

import pytest

from pipeline.benchmark.build_release_manifest import build_manifest, main
from pipeline.benchmark.source_manifests import (
    ReleaseManifestError,
    load_release_manifest,
)


def _write_baseline(path, pmids):
    articles = "".join(
        "<PubmedArticle><MedlineCitation>"
        f"<PMID>{pmid}</PMID>"
        "<Article><Journal><JournalIssue><PubDate><Year>2010</Year>"
        "</PubDate></JournalIssue></Journal></Article>"
        "<MeshHeadingList><MeshHeading>"
        '<DescriptorName UI="D000001">A</DescriptorName>'
        "</MeshHeading></MeshHeadingList>"
        "</MedlineCitation></PubmedArticle>"
        for pmid in pmids
    )
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.write(f"<PubmedArticleSet>{articles}</PubmedArticleSet>")


def test_builder_hashes_sorts_and_counts_real_gzip_inputs(tmp_path):
    second = tmp_path / "medline10n0002.xml.gz"
    first = tmp_path / "medline10n0001.xml.gz"
    _write_baseline(second, ["2", "3"])
    _write_baseline(first, ["1"])

    manifest = build_manifest(
        [second, first],
        year=2010,
        base_url="https://example.test/baseline/2010",
    )

    assert [item["filename"] for item in manifest["files"]] == [
        first.name,
        second.name,
    ]
    assert [item["record_count"] for item in manifest["files"]] == [1, 2]
    assert all(len(item["sha256"]) == 64 for item in manifest["files"])
    assert manifest["files"][0]["url"] == (
        "https://example.test/baseline/2010/medline10n0001.xml.gz"
    )


def test_builder_cli_creates_a_loadable_manifest_and_refuses_overwrite(
    tmp_path,
    monkeypatch,
    capsys,
):
    baseline = tmp_path / "medline10n0001.xml.gz"
    output = tmp_path / "medline-2010.json"
    _write_baseline(baseline, ["1"])
    argv = [
        "build-release-manifest",
        "--year",
        "2010",
        "--base-url",
        "https://example.test/baseline/2010/",
        "--inventory-url",
        "https://example.test/baseline/2010/inventory",
        "--output",
        str(output),
        "--contract-path",
        output.name,
        str(baseline),
    ]
    monkeypatch.setattr(sys, "argv", argv)

    main()

    reference = json.loads(capsys.readouterr().out)
    loaded = load_release_manifest(tmp_path / "sources.json", reference)
    assert loaded.total_record_count == 1
    assert loaded.files[0].filename == baseline.name

    with pytest.raises(SystemExit, match="refusing to overwrite"):
        main()

    outside_reference = {**reference, "path": "../medline-2010.json"}
    with pytest.raises(ReleaseManifestError, match="must stay under"):
        load_release_manifest(tmp_path / "sources.json", outside_reference)

    wrong_total = {**reference, "total_record_count": 2}
    with pytest.raises(ReleaseManifestError, match="record total"):
        load_release_manifest(tmp_path / "sources.json", wrong_total)


def test_builder_rejects_non_https_source_identity(tmp_path):
    baseline = tmp_path / "medline10n0001.xml.gz"
    _write_baseline(baseline, ["1"])

    with pytest.raises(ValueError, match="must be HTTPS"):
        build_manifest(
            [baseline],
            year=2010,
            base_url="http://example.test/baseline/",
        )


def test_cli_requires_contract_path_before_creating_external_output(
    tmp_path,
    monkeypatch,
):
    baseline = tmp_path / "medline10n0001.xml.gz"
    output = tmp_path / "would-be-created.json"
    _write_baseline(baseline, ["1"])
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build-release-manifest",
            "--year",
            "2010",
            "--base-url",
            "https://example.test/baseline/2010/",
            "--inventory-url",
            "https://example.test/baseline/2010/inventory",
            "--output",
            str(output),
            str(baseline),
        ],
    )

    with pytest.raises(SystemExit, match="contract-path is required"):
        main()

    assert not output.exists()
