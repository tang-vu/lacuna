from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from pipeline.export.build_artifacts import _assert_snapshot_inputs_unchanged
from pipeline.export.verify_artifacts import verify_latest
from pipeline.paths import ARTIFACTS_DIR


def load_latest() -> tuple[dict, dict]:
    latest = json.loads((ARTIFACTS_DIR / "latest.json").read_text(encoding="utf-8"))
    version_dir = ARTIFACTS_DIR / Path(latest["version"])
    manifest = json.loads((version_dir / "manifest.json").read_text(encoding="utf-8"))
    computed = json.loads((version_dir / "computed-gaps.json").read_text(encoding="utf-8"))
    return manifest, computed


def assert_public_openalex_url(url: str) -> None:
    assert url.startswith("https://api.openalex.org/")
    params = parse_qs(urlsplit(url).query)
    assert "api_key" not in params
    assert "mailto" not in params


def test_manifest_pins_snapshot_and_metric_version():
    manifest, computed = load_latest()

    assert manifest["version"] == "2026-07-27/v2-bridge-k5"
    assert manifest["snapshot"]["date"] == "2026-07-27"
    assert manifest["metric"]["version"] == "v2-bridge-k5"
    assert computed["method"]["version"] == manifest["metric"]["version"]
    assert computed["validation"]["verdict"] == "FAIL"
    assert computed["validation"]["negative_controls_status"] == "partial"
    assert computed["validation"]["negative_controls_evaluated"] == 1
    assert computed["validation"]["negative_controls_planned"] == 2
    assert computed["coverage"]["complete"] is False
    assert manifest["schema_version"] == 3
    inputs = manifest["snapshot"]["inputs"]
    assert inputs == computed["provenance"]["inputs"]
    assert inputs["cooccurrence_rows"]["rows"] == computed["coverage"]["topics_swept"]
    for source in inputs.values():
        assert len(source["sha256"]) == 64


def test_every_exported_gap_labels_bounds_and_has_public_provenance():
    _, computed = load_latest()

    assert computed["excluded_topics"], "the documented generalist exclusions must ship"
    for gap in computed["gaps"]:
        assert gap["observed_kind"] in {"exact", "upper_bound"}
        assert len(gap["row_source_urls"]) == 2
        for url in [*gap["row_source_urls"], gap["verify_url"]]:
            assert_public_openalex_url(url)


def test_latest_artifact_files_match_manifest_digests():
    manifest = verify_latest()
    assert set(manifest["files"]) == {
        "taxonomy.json",
        "curated.json",
        "computed-gaps.json",
    }
    assert all(
        metadata["canonicalisation"] == "canonical-json-v1"
        for metadata in manifest["files"].values()
    )


def test_published_snapshot_label_cannot_be_reused_for_different_inputs(tmp_path):
    existing = {"taxonomy": {"sha256": "a" * 64}}
    (tmp_path / "manifest.json").write_text(
        json.dumps({"snapshot": {"inputs": existing}}),
        encoding="utf-8",
    )

    _assert_snapshot_inputs_unchanged(tmp_path, existing)
    with pytest.raises(SystemExit, match="different input content"):
        _assert_snapshot_inputs_unchanged(
            tmp_path,
            {"taxonomy": {"sha256": "b" * 64}},
        )
