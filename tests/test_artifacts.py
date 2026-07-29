from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

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


def test_every_exported_gap_labels_bounds_and_has_public_provenance():
    _, computed = load_latest()

    assert computed["excluded_topics"], "the documented generalist exclusions must ship"
    for gap in computed["gaps"]:
        assert gap["observed_kind"] in {"exact", "upper_bound"}
        assert len(gap["row_source_urls"]) == 2
        for url in [*gap["row_source_urls"], gap["verify_url"]]:
            assert_public_openalex_url(url)
