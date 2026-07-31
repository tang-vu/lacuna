from __future__ import annotations

import base64
import gzip
import hashlib
import json

import pytest
import requests

from pipeline.benchmark.mbr_capture import (
    CAPTURE_PATH,
    MbrCaptureError,
    _parse_warc_record,
    load_capture_contract,
    parse_capture_html,
    probe_capture,
)
from pipeline.benchmark.source_inventories import load_inventory_contract
from pipeline.benchmark.validate_sources import SOURCES_PATH


def _contracts():
    sources = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    records = next(item for item in sources["sources"] if item["kind"] == "historical_records")
    years = set(sources["required_baseline_years"])
    inventories = load_inventory_contract(SOURCES_PATH, records["inventory_contract"], years)
    capture = load_capture_contract(
        SOURCES_PATH,
        records["preservation_capture_contract"],
        inventories,
        years,
    )
    return capture, inventories


def test_committed_capture_is_metadata_only_and_reconciles_with_inventories():
    capture, inventories = _contracts()

    assert capture.raw_payload_status == "not_established"
    assert [item.release_year for item in capture.releases] == [2007, 2011, 2012, 2013]
    assert [item.file_count for item in capture.releases] == [
        item.file_count for item in inventories.releases
    ]
    assert capture.capture["url"] == "https://mbr.nlm.nih.gov/"


def test_capture_parser_requires_directory_link_and_release_totals():
    capture, _ = _contracts()
    rows = "".join(
        "<tr><td><a href='{directory}'>{year}</a></td><td>{release_date}</td>"
        "<td>{files}</td><td>{records:,}</td></tr>".format(
            directory=item.directory_path,
            year=item.release_year,
            release_date=item.release_date_text,
            files=item.file_count,
            records=item.total_record_count,
        )
        for item in capture.releases
    )
    html = f"<html><table>{rows}</table></html>"

    parse_capture_html(html, capture.releases)
    with pytest.raises(MbrCaptureError, match="directory link changed"):
        parse_capture_html(html.replace("Download/Baselines/2007", "missing"), capture.releases)


def test_warc_parser_checks_target_status_and_payload_digest():
    capture, _ = _contracts()
    body = b"<html><body>preserved MBR</body></html>"
    digest = base64.b32encode(hashlib.sha1(body).digest()).decode("ascii").rstrip("=")
    mutable = _capture_with_digest(capture, digest)
    http_record = b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n" + body
    record = (
        f"WARC/1.0\r\nWARC-Target-URI: {capture.capture['url']}\r\n"
        f"Content-Length: {len(http_record)}\r\n\r\n"
    ).encode("ascii") + http_record

    assert _parse_warc_record(gzip.compress(record), mutable) == body.decode()
    with pytest.raises(MbrCaptureError, match="payload digest"):
        _parse_warc_record(gzip.compress(record.replace(b"preserved", b"corrupted")), mutable)


def _capture_with_digest(contract, digest):
    return type(contract)(
        path=contract.path,
        sha256=contract.sha256,
        observed_on=contract.observed_on,
        capture={**contract.capture, "digest": digest},
        releases=contract.releases,
        raw_payload_status=contract.raw_payload_status,
        limitation=contract.limitation,
    )


class _Response:
    def __init__(self, content=b"", error=None):
        self.content = content
        self.text = content.decode("utf-8", errors="replace")
        self.error = error

    def raise_for_status(self):
        if self.error is not None:
            raise self.error


def _replay_fixture(capture):
    rows = "".join(
        "<tr><td><a href='{directory}'>{year}</a></td><td>{release_date}</td>"
        "<td>{files}</td><td>{records:,}</td></tr>".format(
            directory=item.directory_path,
            year=item.release_year,
            release_date=item.release_date_text,
            files=item.file_count,
            records=item.total_record_count,
        )
        for item in capture.releases
    )
    body = f"<html><table>{rows}</table></html>".encode()
    digest = base64.b32encode(hashlib.sha1(body).digest()).decode("ascii").rstrip("=")
    http_record = b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n" + body
    record = (
        f"WARC/1.0\r\nWARC-Target-URI: {capture.capture['url']}\r\n"
        f"Content-Length: {len(http_record)}\r\n\r\n"
    ).encode("ascii") + http_record
    compressed = gzip.compress(record)
    mutable = type(capture)(
        path=capture.path,
        sha256=capture.sha256,
        observed_on=capture.observed_on,
        capture={**capture.capture, "digest": digest, "length": len(compressed)},
        releases=capture.releases,
        raw_payload_status=capture.raw_payload_status,
        limitation=capture.limitation,
    )
    return mutable, compressed


def test_probe_replays_warc_when_index_api_is_unreachable():
    capture, _ = _contracts()
    mutable, compressed = _replay_fixture(capture)
    calls = []

    def fetch(url, **_kwargs):
        calls.append(url)
        if url == mutable.capture["index_api"]:
            raise requests.ConnectionError("index unavailable")
        return _Response(compressed)

    result = probe_capture(mutable, fetch=fetch)

    assert result.index_status == "unreachable"
    assert result.index_detail == "ConnectionError"
    assert result.warc_status == "match"
    assert not result.fully_matched
    assert len(calls) == 2


def test_probe_reports_warc_content_drift_separately_from_matching_index():
    capture, _ = _contracts()
    mutable, compressed = _replay_fixture(capture)
    fields = ("timestamp", "url", "status", "mime", "digest", "length", "offset", "filename")
    index_record = {field: mutable.capture[field] for field in fields}

    def fetch(url, **_kwargs):
        if url == mutable.capture["index_api"]:
            return _Response((json.dumps(index_record) + "\n").encode())
        return _Response(b"not-gzip" + compressed[8:])

    result = probe_capture(mutable, fetch=fetch)

    assert result.index_status == "match"
    assert result.warc_status == "drift"
    assert not result.fully_matched


def test_capture_checksum_and_metadata_scope_are_load_bearing(tmp_path):
    sources = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    records = next(item for item in sources["sources"] if item["kind"] == "historical_records")
    years = set(sources["required_baseline_years"])
    inventories = load_inventory_contract(SOURCES_PATH, records["inventory_contract"], years)
    payload = json.loads(CAPTURE_PATH.read_text(encoding="utf-8"))
    payload["raw_payload_status"] = "available"
    path = tmp_path / CAPTURE_PATH.name
    path.write_text(json.dumps(payload), encoding="utf-8")
    reference = {"path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    with pytest.raises(MbrCaptureError, match="cannot establish raw baseline"):
        load_capture_contract(tmp_path / "sources.json", reference, inventories, years)

    reference["sha256"] = "0" * 64
    with pytest.raises(MbrCaptureError, match="checksum mismatch"):
        load_capture_contract(tmp_path / "sources.json", reference, inventories, years)
