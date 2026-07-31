from __future__ import annotations

import hashlib
import json
import shutil

import pytest

from pipeline.benchmark.validate_sources import (
    SOURCES_PATH,
    SourceContractError,
    audit_sources,
)

INVENTORIES_PATH = SOURCES_PATH.parent / "inventories.json"


def _write_sources(tmp_path, payload):
    records = next(
        source for source in payload["sources"] if source["kind"] == "historical_records"
    )
    inventory_path = tmp_path / "inventories.json"
    if records["status"] == "available_pinned":
        inventory_payload = json.loads(INVENTORIES_PATH.read_text(encoding="utf-8"))
        references = {item["year"]: item for item in records["manifests"]}
        for release in inventory_payload["releases"]:
            reference = references[release["release_year"]]
            file_count = reference["file_count"]
            total_records = reference["total_record_count"]
            default_records = total_records // file_count
            last_records = total_records - default_records * (file_count - 1)
            release.update(
                file_count=file_count,
                first_filename=f"medline{str(release['release_year'])[-2:]}n0001.xml",
                last_filename=(
                    f"medline{str(release['release_year'])[-2:]}n{file_count:04d}.xml"
                ),
                default_records_per_file=default_records,
                last_file_record_count=last_records,
                total_record_count=total_records,
                total_uncompressed_bytes=reference["total_bytes"] + 1,
                total_compressed_bytes=reference["total_bytes"],
            )
            reference["inventory_url"] = release["inventory_url"]
        inventory_path.write_text(json.dumps(inventory_payload), encoding="utf-8")
        records["inventory_contract"]["sha256"] = hashlib.sha256(
            inventory_path.read_bytes()
        ).hexdigest()
    else:
        shutil.copy2(INVENTORIES_PATH, inventory_path)
    path = tmp_path / "sources.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_manifest(tmp_path, year, files):
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir(exist_ok=True)
    path = manifest_dir / f"medline-{year}.json"
    payload = {
        "schema_version": 1,
        "kind": "historical_medline_release",
        "release_year": year,
        "files": files,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return {
        "year": year,
        "path": f"manifests/{path.name}",
        "inventory_url": f"https://example.test/inventory/{year}",
        "inventory_file_count": len(files),
        "inventory_total_bytes": sum(item["bytes"] for item in files),
        "inventory_total_record_count": sum(item["record_count"] for item in files),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "file_count": len(files),
        "total_bytes": sum(item["bytes"] for item in files),
        "total_record_count": sum(item["record_count"] for item in files),
    }


def _record_file(year, index=1):
    filename = f"medline{str(year)[-2:]}n{index:04d}.xml.gz"
    return {
        "filename": filename,
        "url": f"https://example.test/{filename}",
        "sha256": str(year)[-1] * 64,
        "bytes": index,
        "record_count": 1,
    }


def test_current_historical_sources_are_explicitly_not_ready():
    audit = audit_sources()

    assert audit.required_years == (2007, 2011, 2012, 2013)
    assert audit.inventory_years == (2007, 2011, 2012, 2013)
    assert audit.pinned_record_years == ()
    assert audit.statuses["historical_records"] == "unavailable"
    assert audit.statuses["historical_vocabulary"] == "available_pinned"
    assert audit.statuses["current_records"] == "available_unsuitable"
    assert not audit.ready
    assert audit.readiness_blockers == (
        "historical_records: unavailable (must be available_pinned)",
    )


def test_pinned_status_requires_checksummed_files_for_every_year(tmp_path):
    payload = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    vocabulary = next(
        source for source in payload["sources"] if source["kind"] == "historical_vocabulary"
    )
    vocabulary["status"] = "available_pinned"
    del vocabulary["files"]
    path = _write_sources(tmp_path, payload)

    with pytest.raises(SourceContractError, match="pinned source needs files"):
        audit_sources(path)


def test_current_records_cannot_replace_historical_records(tmp_path):
    payload = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    current = next(source for source in payload["sources"] if source["kind"] == "current_records")
    current["kind"] = "historical_records"
    current["required_for_shipping"] = True
    path = _write_sources(tmp_path, payload)

    with pytest.raises(SourceContractError, match="duplicate source kind"):
        audit_sources(path)


def test_pinned_vocabulary_needs_a_measured_descriptor_count(tmp_path):
    payload = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    vocabulary = next(
        source for source in payload["sources"] if source["kind"] == "historical_vocabulary"
    )
    vocabulary["files"][0]["descriptor_count"] = 0
    path = _write_sources(tmp_path, payload)

    with pytest.raises(SourceContractError, match="positive descriptor count"):
        audit_sources(path)


def test_pinned_historical_records_need_record_counts_but_allow_many_files_per_year(
    tmp_path,
):
    payload = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    records = next(
        source for source in payload["sources"] if source["kind"] == "historical_records"
    )
    records["status"] = "available_pinned"
    records["manifests"] = []
    for year in payload["required_baseline_years"]:
        files = [_record_file(year)]
        if year == 2011:
            files.append(_record_file(year, 2))
        records["manifests"].append(_write_manifest(tmp_path, year, files))
    path = _write_sources(tmp_path, payload)

    audit = audit_sources(path)

    assert audit.statuses["historical_records"] == "available_pinned"
    assert audit.pinned_record_years == (2007, 2011, 2012, 2013)

    first_reference = records["manifests"][0]
    manifest_path = tmp_path / first_reference["path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    del manifest["files"][0]["record_count"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    first_reference["sha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(SourceContractError, match="positive record_count"):
        audit_sources(path)


def test_pinned_historical_record_manifest_checksum_is_load_bearing(tmp_path):
    payload = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    records = next(
        source for source in payload["sources"] if source["kind"] == "historical_records"
    )
    records["status"] = "available_pinned"
    records["manifests"] = [
        _write_manifest(tmp_path, year, [_record_file(year)])
        for year in payload["required_baseline_years"]
    ]
    records["manifests"][0]["sha256"] = "0" * 64
    path = _write_sources(tmp_path, payload)

    with pytest.raises(SourceContractError, match="manifest checksum mismatch"):
        audit_sources(path)


def test_pinned_manifest_must_match_independent_inventory_totals(tmp_path):
    payload = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    records = next(
        source for source in payload["sources"] if source["kind"] == "historical_records"
    )
    records["status"] = "available_pinned"
    records["manifests"] = [
        _write_manifest(tmp_path, year, [_record_file(year)])
        for year in payload["required_baseline_years"]
    ]
    path = _write_sources(tmp_path, payload)
    records["manifests"][0]["inventory_file_count"] = 2
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SourceContractError, match="differs from inventory file count"):
        audit_sources(path)


def test_pinned_manifest_must_use_the_fingerprinted_nlm_inventory(tmp_path):
    payload = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    records = next(
        source for source in payload["sources"] if source["kind"] == "historical_records"
    )
    records["status"] = "available_pinned"
    records["manifests"] = [
        _write_manifest(tmp_path, year, [_record_file(year)])
        for year in payload["required_baseline_years"]
    ]
    path = _write_sources(tmp_path, payload)
    records["manifests"][0]["inventory_url"] = "https://example.test/substitute"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SourceContractError, match="differs from the pinned NLM contract"):
        audit_sources(path)
