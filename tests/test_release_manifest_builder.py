from __future__ import annotations

import gzip
import hashlib
import json
import sys

import pytest

from pipeline.benchmark.build_release_manifest import (
    build_manifest,
    main,
    manifest_reference,
)
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


def _write_source_contract(
    root,
    *,
    year=2010,
    file_count=1,
    total_bytes,
    total_record_count=1,
):
    prefix = str(year)[-2:]
    default_records = 1
    last_records = total_record_count - (file_count - 1) * default_records
    inventory = {
        "schema_version": 1,
        "observed_on": "2026-08-07",
        "evidence_scope": "official_inventory_metadata_only",
        "releases": [
            {
                "release_year": year,
                "publication_cutoff_year": year - 1,
                "inventory_url": f"https://www.nlm.nih.gov/example/{year}",
                "file_count": file_count,
                "first_filename": f"medline{prefix}n0001.xml",
                "last_filename": f"medline{prefix}n{file_count:04d}.xml",
                "default_records_per_file": default_records,
                "last_file_record_count": last_records,
                "total_record_count": total_record_count,
                "total_uncompressed_bytes": total_bytes + 1,
                "total_compressed_bytes": total_bytes,
            }
        ],
    }
    inventory_path = root / "inventories.json"
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
    sources = {
        "required_baseline_years": [year],
        "sources": [
            {
                "kind": "historical_records",
                "inventory_contract": {
                    "path": inventory_path.name,
                    "sha256": hashlib.sha256(inventory_path.read_bytes()).hexdigest(),
                },
            }
        ],
    }
    source_path = root / "sources.json"
    source_path.write_text(json.dumps(sources), encoding="utf-8")
    return source_path


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
    source_contract = _write_source_contract(
        tmp_path,
        total_bytes=baseline.stat().st_size,
    )
    argv = [
        "build-release-manifest",
        "--year",
        "2010",
        "--base-url",
        "https://example.test/baseline/2010/",
        "--source-contract",
        str(source_contract),
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
    assert reference["inventory_file_count"] == 1
    assert reference["inventory_total_bytes"] == baseline.stat().st_size
    assert reference["inventory_total_record_count"] == 1

    with pytest.raises(SystemExit, match="refusing to overwrite"):
        main()

    outside_reference = {**reference, "path": "../medline-2010.json"}
    with pytest.raises(ReleaseManifestError, match="must stay under"):
        load_release_manifest(tmp_path / "sources.json", outside_reference)

    wrong_total = {**reference, "total_record_count": 2}
    with pytest.raises(ReleaseManifestError, match="record total"):
        load_release_manifest(tmp_path / "sources.json", wrong_total)

    malformed = json.loads(output.read_text(encoding="utf-8"))
    malformed["files"][0]["filename"] = "medline10n0002.xml.gz"
    malformed["files"][0]["url"] = (
        "https://example.test/baseline/2010/medline10n0002.xml.gz"
    )
    output.write_text(json.dumps(malformed), encoding="utf-8")
    malformed_reference = {
        **reference,
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    }
    with pytest.raises(ReleaseManifestError, match="contiguous official release"):
        load_release_manifest(tmp_path / "sources.json", malformed_reference)


def test_builder_rejects_non_https_source_identity(tmp_path):
    baseline = tmp_path / "medline10n0001.xml.gz"
    _write_baseline(baseline, ["1"])

    with pytest.raises(ValueError, match="must be HTTPS"):
        build_manifest(
            [baseline],
            year=2010,
            base_url="http://example.test/baseline/",
        )


def test_manifest_reference_rejects_a_self_consistent_but_incomplete_release(tmp_path):
    baseline = tmp_path / "medline10n0001.xml.gz"
    output = tmp_path / "medline-2010.json"
    _write_baseline(baseline, ["1"])
    manifest = build_manifest(
        [baseline],
        year=2010,
        base_url="https://example.test/baseline/2010/",
    )
    output.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="file count differs from the official inventory"):
        manifest_reference(
            output,
            manifest,
            relative_path=output.name,
            inventory_url="https://example.test/baseline/2010/inventory",
            inventory_file_count=2,
            inventory_total_bytes=baseline.stat().st_size,
            inventory_total_record_count=1,
        )


def test_cli_checks_inventory_totals_before_creating_manifest(tmp_path, monkeypatch):
    baseline = tmp_path / "medline10n0001.xml.gz"
    output = tmp_path / "medline-2010.json"
    _write_baseline(baseline, ["1"])
    source_contract = _write_source_contract(
        tmp_path,
        file_count=2,
        total_bytes=baseline.stat().st_size,
        total_record_count=2,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build-release-manifest",
            "--year",
            "2010",
            "--base-url",
            "https://example.test/baseline/2010/",
            "--source-contract",
            str(source_contract),
            "--output",
            str(output),
            "--contract-path",
            output.name,
            str(baseline),
        ],
    )

    with pytest.raises(SystemExit, match="file count differs from the official inventory"):
        main()

    assert not output.exists()


def test_cli_rejects_wrong_release_filenames_before_creating_manifest(
    tmp_path,
    monkeypatch,
):
    baseline = tmp_path / "unverified.xml.gz"
    output = tmp_path / "medline-2010.json"
    _write_baseline(baseline, ["1"])
    source_contract = _write_source_contract(
        tmp_path,
        total_bytes=baseline.stat().st_size,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build-release-manifest",
            "--year",
            "2010",
            "--base-url",
            "https://example.test/baseline/2010/",
            "--source-contract",
            str(source_contract),
            "--output",
            str(output),
            "--contract-path",
            output.name,
            str(baseline),
        ],
    )

    with pytest.raises(SystemExit, match="contiguous official release"):
        main()

    assert not output.exists()


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
            "--output",
            str(output),
            str(baseline),
        ],
    )

    with pytest.raises(SystemExit, match="contract-path is required"):
        main()

    assert not output.exists()
