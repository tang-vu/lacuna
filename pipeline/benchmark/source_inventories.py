"""Validate pinned NLM release inventories and optionally probe their live pages.

The inventories are completeness metadata, not historical citation records. A successful probe
must never turn the historical-record gate green; it only establishes the exact release that a
future raw-file manifest has to match.

Run:
    python -m pipeline.benchmark.source_inventories
    python -m pipeline.benchmark.source_inventories --probe
    python -m pipeline.benchmark.source_inventories --probe --require-match
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

import requests

from pipeline.paths import REPO_ROOT

INVENTORIES_PATH = REPO_ROOT / "benchmarks" / "v3" / "inventories.json"

SHA256 = re.compile(r"^[0-9a-f]{64}$")
SUMMARY = re.compile(
    r"baseline database contains\s+([\d,]+)\s+records\s+and\s+contains\s+([\d,]+)\s+bytes",
    re.IGNORECASE,
)


class InventoryContractError(ValueError):
    pass


@dataclass(frozen=True)
class ReleaseInventory:
    release_year: int
    publication_cutoff_year: int
    inventory_url: str
    file_count: int
    first_filename: str
    last_filename: str
    default_records_per_file: int
    last_file_record_count: int
    total_record_count: int
    total_uncompressed_bytes: int
    total_compressed_bytes: int


@dataclass(frozen=True)
class InventoryContract:
    path: Path
    sha256: str
    observed_on: date
    releases: tuple[ReleaseInventory, ...]


@dataclass(frozen=True)
class InventoryObservation:
    release_year: int
    url: str
    status: str
    file_count: int | None = None
    last_file_record_count: int | None = None
    total_record_count: int | None = None
    total_uncompressed_bytes: int | None = None
    total_compressed_bytes: int | None = None
    detail: str | None = None


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_cell = False
        self.cell_parts: list[str] = []
        self.row: list[str] = []
        self.rows: list[list[str]] = []
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "tr":
            self.row = []
        elif tag.lower() in {"td", "th"}:
            self.in_cell = True
            self.cell_parts = []

    def handle_data(self, data: str) -> None:
        self.text_parts.append(data)
        if self.in_cell:
            self.cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"td", "th"}:
            self.in_cell = False
            self.row.append(_normalise_text(" ".join(self.cell_parts)))
        elif tag.lower() == "tr" and self.row:
            self.rows.append(self.row)


def _normalise_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _positive_int(value: object, context: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise InventoryContractError(f"{context} must be a positive integer")
    return value


def _number(value: str, context: str) -> int:
    digits = re.sub(r"[^0-9]", "", value)
    if not digits:
        raise InventoryContractError(f"{context} does not contain a number")
    return int(digits)


def _resolve_contract_path(source_path: Path, raw_path: object) -> Path:
    if not isinstance(raw_path, str) or not raw_path:
        raise InventoryContractError("inventory contract path is required")
    relative = Path(raw_path)
    if relative.is_absolute():
        raise InventoryContractError("inventory contract path must be relative")
    base = source_path.parent.resolve()
    resolved = (base / relative).resolve()
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise InventoryContractError(
            "inventory contract path must stay under the source contract directory"
        ) from exc
    return resolved


def load_inventory_contract(
    source_path: Path,
    reference: dict,
    required_years: set[int] | None = None,
) -> InventoryContract:
    """Load a fingerprinted inventory contract and enforce its internal arithmetic."""
    path = _resolve_contract_path(source_path, reference.get("path"))
    expected_sha256 = str(reference.get("sha256", ""))
    if not SHA256.fullmatch(expected_sha256):
        raise InventoryContractError("inventory contract needs a SHA-256 checksum")
    if not path.is_file():
        raise InventoryContractError(f"inventory contract is missing: {path}")
    actual_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual_sha256 != expected_sha256:
        raise InventoryContractError(
            f"inventory contract checksum mismatch ({actual_sha256} != {expected_sha256})"
        )

    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise InventoryContractError("unsupported inventory contract schema")
    if payload.get("evidence_scope") != "official_inventory_metadata_only":
        raise InventoryContractError("inventory evidence must remain metadata-only")
    try:
        observed_on = date.fromisoformat(str(payload.get("observed_on")))
    except ValueError as exc:
        raise InventoryContractError("inventory observed_on must be YYYY-MM-DD") from exc

    raw_releases = payload.get("releases")
    if not isinstance(raw_releases, list) or not raw_releases:
        raise InventoryContractError("inventory contract needs releases")
    releases: list[ReleaseInventory] = []
    seen_years: set[int] = set()
    for index, item in enumerate(raw_releases):
        if not isinstance(item, dict):
            raise InventoryContractError(f"malformed inventory release {index}")
        year = _positive_int(item.get("release_year"), f"release {index} year")
        if year in seen_years:
            raise InventoryContractError(f"duplicate inventory release year {year}")
        seen_years.add(year)
        cutoff = _positive_int(item.get("publication_cutoff_year"), f"{year} cutoff")
        if cutoff != year - 1:
            raise InventoryContractError(f"{year}: publication cutoff must be release year - 1")
        url = item.get("inventory_url")
        parsed_url = urlsplit(str(url))
        if not (
            isinstance(url, str)
            and parsed_url.scheme == "https"
            and parsed_url.hostname == "www.nlm.nih.gov"
        ):
            raise InventoryContractError(f"{year}: inventory URL must use official NLM HTTPS")

        file_count = _positive_int(item.get("file_count"), f"{year} file_count")
        default_records = _positive_int(
            item.get("default_records_per_file"), f"{year} default_records_per_file"
        )
        last_records = _positive_int(
            item.get("last_file_record_count"), f"{year} last_file_record_count"
        )
        total_records = _positive_int(
            item.get("total_record_count"), f"{year} total_record_count"
        )
        uncompressed = _positive_int(
            item.get("total_uncompressed_bytes"), f"{year} total_uncompressed_bytes"
        )
        compressed = _positive_int(
            item.get("total_compressed_bytes"), f"{year} total_compressed_bytes"
        )
        if compressed >= uncompressed:
            raise InventoryContractError(f"{year}: compressed bytes must be below uncompressed")
        if (file_count - 1) * default_records + last_records != total_records:
            raise InventoryContractError(f"{year}: record total does not reconcile with files")

        prefix = str(year)[-2:]
        expected_first = f"medline{prefix}n0001.xml"
        expected_last = f"medline{prefix}n{file_count:04d}.xml"
        first_filename = item.get("first_filename")
        last_filename = item.get("last_filename")
        if first_filename != expected_first or last_filename != expected_last:
            raise InventoryContractError(f"{year}: filename range does not match file count")

        releases.append(
            ReleaseInventory(
                release_year=year,
                publication_cutoff_year=cutoff,
                inventory_url=url,
                file_count=file_count,
                first_filename=first_filename,
                last_filename=last_filename,
                default_records_per_file=default_records,
                last_file_record_count=last_records,
                total_record_count=total_records,
                total_uncompressed_bytes=uncompressed,
                total_compressed_bytes=compressed,
            )
        )

    if required_years is not None and seen_years != required_years:
        raise InventoryContractError("inventory releases must cover every required baseline year")
    return InventoryContract(
        path=path,
        sha256=actual_sha256,
        observed_on=observed_on,
        releases=tuple(sorted(releases, key=lambda item: item.release_year)),
    )


def parse_inventory_html(html: str, release_year: int, url: str) -> InventoryObservation:
    """Extract the exact inventory summary and sum every per-file size row."""
    parser = _TableParser()
    parser.feed(html)
    page_text = _normalise_text(" ".join(parser.text_parts))
    summary = SUMMARY.search(page_text)
    if summary is None:
        raise InventoryContractError(f"{release_year}: inventory summary not found")

    filename_pattern = re.compile(rf"^medline{str(release_year)[-2:]}n\d{{4}}\.xml$")
    file_rows = [
        row for row in parser.rows if len(row) >= 4 and filename_pattern.fullmatch(row[0])
    ]
    if not file_rows:
        raise InventoryContractError(f"{release_year}: inventory file rows not found")
    filenames = [row[0] for row in file_rows]
    if len(filenames) != len(set(filenames)):
        raise InventoryContractError(f"{release_year}: duplicate inventory filenames")
    expected_names = [
        f"medline{str(release_year)[-2:]}n{index:04d}.xml"
        for index in range(1, len(file_rows) + 1)
    ]
    if filenames != expected_names:
        raise InventoryContractError(f"{release_year}: inventory filenames are not contiguous")

    record_exceptions = [
        (row[0], _number(row[1], f"{release_year} record exception"))
        for row in parser.rows
        if len(row) == 2 and filename_pattern.fullmatch(row[0])
    ]
    if len(record_exceptions) != 1 or record_exceptions[0][0] != filenames[-1]:
        raise InventoryContractError(
            f"{release_year}: expected one last-file record-count exception"
        )

    return InventoryObservation(
        release_year=release_year,
        url=url,
        status="match_pending",
        file_count=len(file_rows),
        last_file_record_count=record_exceptions[0][1],
        total_record_count=_number(summary.group(1), f"{release_year} record total"),
        total_uncompressed_bytes=sum(
            _number(row[-2], f"{release_year} uncompressed bytes") for row in file_rows
        ),
        total_compressed_bytes=sum(
            _number(row[-1], f"{release_year} compressed bytes") for row in file_rows
        ),
    )


def _matches(expected: ReleaseInventory, observed: InventoryObservation) -> bool:
    return all(
        (
            observed.file_count == expected.file_count,
            observed.last_file_record_count == expected.last_file_record_count,
            observed.total_record_count == expected.total_record_count,
            observed.total_uncompressed_bytes == expected.total_uncompressed_bytes,
            observed.total_compressed_bytes == expected.total_compressed_bytes,
        )
    )


def probe_inventories(
    contract: InventoryContract,
    fetch: Callable[..., requests.Response] = requests.get,
    timeout: float = 20.0,
) -> tuple[InventoryObservation, ...]:
    """Fetch official inventory pages and compare their content with the pinned contract."""
    observations: list[InventoryObservation] = []
    headers = {"User-Agent": "lacuna-source-audit/0.1 (+https://github.com/tang-vu/lacuna)"}
    for release in contract.releases:
        try:
            response = fetch(release.inventory_url, headers=headers, timeout=timeout)
            response.raise_for_status()
            if len(response.content) > 5_000_000:
                raise InventoryContractError(f"{release.release_year}: inventory page is too large")
            observed = parse_inventory_html(
                response.text,
                release.release_year,
                release.inventory_url,
            )
            observations.append(
                InventoryObservation(
                    **{
                        **asdict(observed),
                        "status": "match" if _matches(release, observed) else "drift",
                    }
                )
            )
        except (requests.RequestException, InventoryContractError) as exc:
            observations.append(
                InventoryObservation(
                    release_year=release.release_year,
                    url=release.inventory_url,
                    status="unreachable_or_unparseable",
                    detail=type(exc).__name__,
                )
            )
    return tuple(observations)


def main() -> None:
    from pipeline.benchmark.validate_sources import SOURCES_PATH

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", action="store_true", help="make live requests to NLM")
    parser.add_argument(
        "--require-match",
        action="store_true",
        help="exit 2 unless every live inventory exactly matches the pinned metadata",
    )
    parser.add_argument("--json", action="store_true", help="emit the live report as JSON")
    args = parser.parse_args()
    if args.require_match and not args.probe:
        parser.error("--require-match requires --probe")

    sources = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    records = next(
        item for item in sources["sources"] if item.get("kind") == "historical_records"
    )
    contract = load_inventory_contract(
        SOURCES_PATH,
        records.get("inventory_contract", {}),
        set(sources["required_baseline_years"]),
    )
    if not args.probe:
        print("historical inventory contract: structurally valid")
        print(f"evidence scope: metadata only ({len(contract.releases)} releases)")
        print("raw historical records: not established by this command")
        return

    observations = probe_inventories(contract)
    if args.json:
        print(json.dumps([asdict(item) for item in observations], indent=2))
    else:
        print("historical inventory live probe (metadata only)")
        for item in observations:
            print(f"{item.release_year}: {item.status} · {item.url}")
        print("raw historical records: not established by this probe")
    if args.require_match and any(item.status != "match" for item in observations):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
