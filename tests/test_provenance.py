from __future__ import annotations

import json

from pipeline.provenance import (
    cooccurrence_rows_fingerprint,
    sanitise_local_provenance,
)


def test_row_fingerprint_ignores_timestamp_and_request_credentials(tmp_path):
    row = {
        "topic": "T1",
        "marginal": 10,
        "partners": {"T2": 3},
        "truncated": False,
        "ceiling": 0,
        "fetched_at": "2026-01-01T00:00:00Z",
        "source_url": "https://api.openalex.org/works?filter=topics.id:T1&mailto=one@example.test",
    }
    row_path = tmp_path / "T1.json"
    row_path.write_text(json.dumps(row), encoding="utf-8")
    digest_a = cooccurrence_rows_fingerprint([row_path])

    row["fetched_at"] = "2027-01-01T00:00:00Z"
    row["source_url"] = (
        "https://api.openalex.org/works?filter=topics.id:T1"
        "&mailto=two@example.test&api_key=secret"
    )
    row_path.write_text(json.dumps(row), encoding="utf-8")
    digest_b = cooccurrence_rows_fingerprint([row_path])

    assert digest_a == digest_b


def test_local_provenance_cleaner_changes_urls_not_measurements(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    row_dir = tmp_path / "cooccurrence" / "pre1986"
    cache_dir.mkdir()
    row_dir.mkdir(parents=True)
    cache = cache_dir / "response.json"
    row_path = row_dir / "T1.json"
    cache.write_text(
        json.dumps(
            {
                "meta": {"count": 7},
                "_lacuna_source_url": "https://api.openalex.org/works?api_key=secret",
            }
        ),
        encoding="utf-8",
    )
    row_path.write_text(
        json.dumps(
            {
                "topic": "T1",
                "marginal": 7,
                "partners": {},
                "truncated": False,
                "ceiling": 0,
                "source_url": "https://api.openalex.org/works?mailto=person@example.test",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("pipeline.provenance.CACHE_DIR", cache_dir)
    monkeypatch.setattr("pipeline.provenance.COOCCURRENCE_DIR", tmp_path / "cooccurrence")

    scanned, changed = sanitise_local_provenance()

    assert (scanned, changed) == (2, 2)
    assert json.loads(cache.read_text(encoding="utf-8"))["meta"]["count"] == 7
    cleaned_row = json.loads(row_path.read_text(encoding="utf-8"))
    assert cleaned_row["marginal"] == 7
    assert "mailto" not in cleaned_row["source_url"]
