"""Validate and optionally replay the preserved MBR repository metadata capture.

The Common Crawl record preserves the retired MBR homepage, not the historical MEDLINE XML.
Matching this probe therefore strengthens source traceability without changing the raw-record
readiness gate.

Run:
    python -m pipeline.benchmark.mbr_capture
    python -m pipeline.benchmark.mbr_capture --probe --require-match
"""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

import requests

from pipeline.benchmark.source_inventories import InventoryContract
from pipeline.paths import REPO_ROOT

CAPTURE_PATH = REPO_ROOT / "benchmarks" / "v3" / "mbr-capture.json"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
TIMESTAMP = re.compile(r"^\d{14}$")
BASE32_SHA1 = re.compile(r"^[A-Z2-7]{32}$")
USER_AGENT = "lacuna-source-audit/0.1 (+https://github.com/tang-vu/lacuna)"


class MbrCaptureError(ValueError):
    pass


@dataclass(frozen=True)
class CapturedRelease:
    release_year: int
    release_date_text: str
    directory_path: str
    file_count: int
    total_record_count: int


@dataclass(frozen=True)
class MbrCaptureContract:
    path: Path
    sha256: str
    observed_on: date
    capture: dict
    releases: tuple[CapturedRelease, ...]
    raw_payload_status: str
    limitation: str


class _CaptureTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_cell = False
        self.cell_parts: list[str] = []
        self.cell_links: list[str] = []
        self.row: list[tuple[str, tuple[str, ...]]] = []
        self.rows: list[list[tuple[str, tuple[str, ...]]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "tr":
            self.row = []
        elif tag in {"td", "th"}:
            self.in_cell = True
            self.cell_parts = []
            self.cell_links = []
        elif tag == "a" and self.in_cell:
            href = dict(attrs).get("href")
            if href:
                self.cell_links.append(href)

    def handle_data(self, data: str) -> None:
        if self.in_cell:
            self.cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"td", "th"}:
            self.in_cell = False
            self.row.append((_normalise(" ".join(self.cell_parts)), tuple(self.cell_links)))
        elif tag == "tr" and self.row:
            self.rows.append(self.row)


def _normalise(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _positive_int(value: object, context: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise MbrCaptureError(f"{context} must be a positive integer")
    return value


def _resolve_contract_path(source_path: Path, raw_path: object) -> Path:
    if not isinstance(raw_path, str) or not raw_path:
        raise MbrCaptureError("MBR capture contract path is required")
    relative = Path(raw_path)
    if relative.is_absolute():
        raise MbrCaptureError("MBR capture contract path must be relative")
    base = source_path.parent.resolve()
    resolved = (base / relative).resolve()
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise MbrCaptureError(
            "MBR capture contract path must stay under the source contract directory"
        ) from exc
    return resolved


def load_capture_contract(
    source_path: Path,
    reference: dict,
    inventories: InventoryContract,
    required_years: set[int],
) -> MbrCaptureContract:
    """Load the fingerprinted preservation record and reconcile it with NLM inventories."""
    path = _resolve_contract_path(source_path, reference.get("path"))
    expected_sha256 = str(reference.get("sha256", ""))
    if not SHA256.fullmatch(expected_sha256):
        raise MbrCaptureError("MBR capture contract needs a SHA-256 checksum")
    if not path.is_file():
        raise MbrCaptureError(f"MBR capture contract is missing: {path}")
    actual_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual_sha256 != expected_sha256:
        raise MbrCaptureError(
            f"MBR capture contract checksum mismatch ({actual_sha256} != {expected_sha256})"
        )

    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise MbrCaptureError("unsupported MBR capture schema")
    if payload.get("evidence_scope") != "preserved_repository_metadata_only":
        raise MbrCaptureError("MBR capture evidence must remain metadata-only")
    if payload.get("raw_payload_status") != "not_established":
        raise MbrCaptureError("MBR capture cannot establish raw baseline payloads")
    try:
        observed_on = date.fromisoformat(str(payload.get("observed_on")))
    except ValueError as exc:
        raise MbrCaptureError("MBR capture observed_on must be YYYY-MM-DD") from exc

    capture = payload.get("capture")
    if not isinstance(capture, dict):
        raise MbrCaptureError("MBR capture metadata is missing")
    index_url = urlsplit(str(capture.get("index_api")))
    if index_url.scheme != "https" or index_url.hostname != "index.commoncrawl.org":
        raise MbrCaptureError("MBR capture index must use Common Crawl HTTPS")
    if capture.get("index_id") != "CC-MAIN-2018-51":
        raise MbrCaptureError("unexpected MBR capture index")
    if not TIMESTAMP.fullmatch(str(capture.get("timestamp", ""))):
        raise MbrCaptureError("MBR capture timestamp is malformed")
    if capture.get("url") != "https://mbr.nlm.nih.gov/":
        raise MbrCaptureError("MBR capture target changed")
    if capture.get("status") != "200" or capture.get("mime") != "text/html":
        raise MbrCaptureError("MBR capture must identify the successful HTML response")
    if not BASE32_SHA1.fullmatch(str(capture.get("digest", ""))):
        raise MbrCaptureError("MBR capture digest is malformed")
    _positive_int(capture.get("length"), "MBR capture range length")
    _positive_int(capture.get("offset"), "MBR capture range offset")
    filename = str(capture.get("filename", ""))
    if not filename.startswith("crawl-data/CC-MAIN-2018-51/") or not filename.endswith(
        ".warc.gz"
    ):
        raise MbrCaptureError("MBR capture WARC path is malformed")

    inventory_by_year = {item.release_year: item for item in inventories.releases}
    raw_releases = payload.get("required_releases")
    if not isinstance(raw_releases, list):
        raise MbrCaptureError("MBR capture releases must be a list")
    releases: list[CapturedRelease] = []
    seen_years: set[int] = set()
    for index, item in enumerate(raw_releases):
        if not isinstance(item, dict):
            raise MbrCaptureError(f"malformed MBR capture release {index}")
        year = _positive_int(item.get("release_year"), f"capture release {index} year")
        if year in seen_years or year not in required_years:
            raise MbrCaptureError(f"unexpected or duplicate MBR capture year {year}")
        seen_years.add(year)
        expected = inventory_by_year[year]
        directory = item.get("directory_path")
        if directory != f"Download/Baselines/{year}":
            raise MbrCaptureError(f"{year}: MBR directory path changed")
        if item.get("file_count") != expected.file_count:
            raise MbrCaptureError(f"{year}: MBR file count differs from inventory")
        if item.get("total_record_count") != expected.total_record_count:
            raise MbrCaptureError(f"{year}: MBR record total differs from inventory")
        release_date = item.get("release_date_text")
        if not isinstance(release_date, str) or not release_date:
            raise MbrCaptureError(f"{year}: MBR release date is missing")
        releases.append(
            CapturedRelease(
                release_year=year,
                release_date_text=release_date,
                directory_path=directory,
                file_count=expected.file_count,
                total_record_count=expected.total_record_count,
            )
        )
    if seen_years != required_years:
        raise MbrCaptureError("MBR capture must cover every required baseline year")
    limitation = payload.get("limitation")
    if not isinstance(limitation, str) or "does not establish" not in limitation:
        raise MbrCaptureError("MBR capture needs an explicit raw-payload limitation")
    return MbrCaptureContract(
        path=path,
        sha256=actual_sha256,
        observed_on=observed_on,
        capture=capture,
        releases=tuple(sorted(releases, key=lambda item: item.release_year)),
        raw_payload_status="not_established",
        limitation=limitation,
    )


def parse_capture_html(html: str, releases: tuple[CapturedRelease, ...]) -> None:
    """Require every pinned MBR directory row and release total in the captured homepage."""
    parser = _CaptureTableParser()
    parser.feed(html)
    for release in releases:
        matching = [row for row in parser.rows if row and row[0][0] == str(release.release_year)]
        if len(matching) != 1 or len(matching[0]) < 4:
            raise MbrCaptureError(f"{release.release_year}: MBR release row not found")
        row = matching[0]
        if release.directory_path not in row[0][1]:
            raise MbrCaptureError(f"{release.release_year}: MBR directory link changed")
        if row[1][0] != release.release_date_text:
            raise MbrCaptureError(f"{release.release_year}: MBR release date changed")
        file_count = int(row[2][0].replace(",", ""))
        record_count = int(row[3][0].replace(",", ""))
        if file_count != release.file_count or record_count != release.total_record_count:
            raise MbrCaptureError(f"{release.release_year}: MBR release totals changed")


def _parse_warc_record(compressed: bytes, contract: MbrCaptureContract) -> str:
    try:
        record = gzip.decompress(compressed)
        warc_headers, http_record = record.split(b"\r\n\r\n", 1)
    except (OSError, ValueError) as exc:
        raise MbrCaptureError("Common Crawl range is not one complete gzip WARC record") from exc
    warc_text = warc_headers.decode("ascii", errors="strict")
    length_match = re.search(r"^Content-Length:\s*(\d+)\s*$", warc_text, re.MULTILINE)
    if length_match is None:
        raise MbrCaptureError("WARC record has no block length")
    block_length = int(length_match.group(1))
    if len(http_record) < block_length:
        raise MbrCaptureError("WARC record is shorter than its declared block length")
    try:
        http_headers, body = http_record[:block_length].split(b"\r\n\r\n", 1)
    except ValueError as exc:
        raise MbrCaptureError("WARC record contains no HTTP payload") from exc
    http_text = http_headers.decode("iso-8859-1")
    if f"WARC-Target-URI: {contract.capture['url']}" not in warc_text:
        raise MbrCaptureError("WARC target differs from the MBR contract")
    if not http_text.startswith("HTTP/1.1 200"):
        raise MbrCaptureError("preserved MBR response is not HTTP 200")
    digest = base64.b32encode(hashlib.sha1(body).digest()).decode("ascii").rstrip("=")
    if digest != contract.capture["digest"]:
        raise MbrCaptureError("preserved MBR payload digest differs from the index")
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise MbrCaptureError("preserved MBR homepage is not UTF-8") from exc


def probe_capture(
    contract: MbrCaptureContract,
    fetch: Callable[..., requests.Response] = requests.get,
    timeout: float = 30.0,
) -> None:
    """Replay the exact Common Crawl range and compare its HTML with the contract."""
    headers = {"User-Agent": USER_AGENT}
    index_response = fetch(contract.capture["index_api"], headers=headers, timeout=timeout)
    index_response.raise_for_status()
    if len(index_response.content) > 1_000_000:
        raise MbrCaptureError("Common Crawl index response is unexpectedly large")
    records = [json.loads(line) for line in index_response.text.splitlines() if line.strip()]
    expected_fields = ("timestamp", "url", "status", "mime", "digest", "length", "offset", "filename")
    if not any(
        all(str(record.get(field)) == str(contract.capture[field]) for field in expected_fields)
        for record in records
    ):
        raise MbrCaptureError("Common Crawl index no longer returns the pinned MBR capture")

    start = contract.capture["offset"]
    end = start + contract.capture["length"] - 1
    data_url = f"https://data.commoncrawl.org/{contract.capture['filename']}"
    range_response = fetch(
        data_url,
        headers={**headers, "Range": f"bytes={start}-{end}"},
        timeout=timeout,
    )
    range_response.raise_for_status()
    if len(range_response.content) != contract.capture["length"]:
        raise MbrCaptureError("Common Crawl returned the wrong WARC range length")
    html = _parse_warc_record(range_response.content, contract)
    parse_capture_html(html, contract.releases)


def main() -> None:
    from pipeline.benchmark.source_inventories import load_inventory_contract
    from pipeline.benchmark.validate_sources import SOURCES_PATH

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", action="store_true", help="replay the Common Crawl WARC range")
    parser.add_argument(
        "--require-match",
        action="store_true",
        help="exit 2 unless the live index, WARC digest, and release rows all match",
    )
    args = parser.parse_args()
    if args.require_match and not args.probe:
        parser.error("--require-match requires --probe")

    sources = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    records = next(item for item in sources["sources"] if item["kind"] == "historical_records")
    years = set(sources["required_baseline_years"])
    inventories = load_inventory_contract(SOURCES_PATH, records["inventory_contract"], years)
    contract = load_capture_contract(
        SOURCES_PATH,
        records["preservation_capture_contract"],
        inventories,
        years,
    )
    if not args.probe:
        print("MBR preservation capture contract: structurally valid")
        print(f"repository directory metadata: {len(contract.releases)} releases")
        print("raw historical records: not established by this command")
        return
    try:
        probe_capture(contract)
    except requests.RequestException as exc:
        print(f"MBR preservation capture: unreachable ({type(exc).__name__})")
        print("raw historical records: not established by this probe")
        if args.require_match:
            raise SystemExit(2) from exc
        return
    except MbrCaptureError as exc:
        print(f"MBR preservation capture: drift ({exc})")
        print("raw historical records: not established by this probe")
        if args.require_match:
            raise SystemExit(2) from exc
        return
    print("MBR preservation capture: match")
    print(f"repository directory metadata: {len(contract.releases)} releases")
    print("raw historical records: not established by this probe")


if __name__ == "__main__":
    main()
