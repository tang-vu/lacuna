"""Validate committed manifests for multi-file historical MEDLINE releases."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ReleaseManifestError(ValueError):
    pass


@dataclass(frozen=True)
class ReleaseFile:
    filename: str
    url: str
    sha256: str
    bytes: int
    record_count: int


@dataclass(frozen=True)
class ReleaseManifest:
    year: int
    path: Path
    sha256: str
    files: tuple[ReleaseFile, ...]
    total_bytes: int
    total_record_count: int


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ReleaseManifestError(message)


def _resolve_manifest_path(source_path: Path, raw_path: object) -> Path:
    _require(isinstance(raw_path, str) and bool(raw_path), "manifest path is required")
    relative = Path(raw_path)
    _require(not relative.is_absolute(), "manifest path must be relative")
    base = source_path.parent.resolve()
    resolved = (base / relative).resolve()
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise ReleaseManifestError("manifest path must stay under the source contract directory") from exc
    _require(resolved.suffix == ".json", "manifest path must point to JSON")
    return resolved


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_release_manifest(
    source_path: Path,
    reference: dict,
) -> ReleaseManifest:
    """Load one manifest and reconcile it with its small source-contract reference."""
    year = reference.get("year")
    _require(isinstance(year, int) and year >= 2002, "manifest reference needs a release year")
    expected_sha256 = str(reference.get("sha256", ""))
    _require(bool(SHA256.fullmatch(expected_sha256)), f"{year}: invalid manifest SHA-256")
    for field in ("file_count", "total_bytes", "total_record_count"):
        _require(
            isinstance(reference.get(field), int) and reference[field] > 0,
            f"{year}: manifest reference needs a positive {field}",
        )
    for field in (
        "inventory_file_count",
        "inventory_total_bytes",
        "inventory_total_record_count",
    ):
        _require(
            isinstance(reference.get(field), int) and reference[field] > 0,
            f"{year}: manifest reference needs a positive {field}",
        )
    inventory_url = reference.get("inventory_url")
    parsed_inventory_url = urlsplit(str(inventory_url))
    _require(
        isinstance(inventory_url, str)
        and parsed_inventory_url.scheme == "https"
        and bool(parsed_inventory_url.netloc),
        f"{year}: manifest reference needs an HTTPS inventory URL",
    )

    path = _resolve_manifest_path(source_path, reference.get("path"))
    _require(path.is_file(), f"{year}: manifest file is missing: {path}")
    actual_sha256 = _file_sha256(path)
    _require(
        actual_sha256 == expected_sha256,
        f"{year}: manifest checksum mismatch ({actual_sha256} != {expected_sha256})",
    )

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseManifestError(f"{year}: cannot read manifest JSON: {exc}") from exc
    _require(isinstance(payload, dict), f"{year}: manifest root must be an object")
    _require(payload.get("schema_version") == 1, f"{year}: unsupported manifest schema")
    _require(
        payload.get("kind") == "historical_medline_release",
        f"{year}: wrong manifest kind",
    )
    _require(payload.get("release_year") == year, f"{year}: release year mismatch")
    files = payload.get("files")
    _require(isinstance(files, list) and files, f"{year}: manifest needs files")

    parsed_files = []
    seen_names: set[str] = set()
    seen_urls: set[str] = set()
    for index, item in enumerate(files):
        _require(isinstance(item, dict), f"{year}: malformed file {index}")
        filename = item.get("filename")
        url = item.get("url")
        _require(isinstance(filename, str) and bool(filename), f"{year}: file {index} needs filename")
        _require(filename == Path(filename).name, f"{year}: unsafe filename {filename!r}")
        _require(filename not in seen_names, f"{year}: duplicate filename {filename}")
        seen_names.add(filename)
        _require(isinstance(url, str), f"{year}: file {index} URL must be a string")
        parsed_url = urlsplit(url)
        _require(
            parsed_url.scheme == "https" and bool(parsed_url.netloc),
            f"{year}: file {index} URL must be HTTPS",
        )
        _require(url not in seen_urls, f"{year}: duplicate URL {url}")
        seen_urls.add(url)
        _require(
            unquote(Path(parsed_url.path).name) == filename,
            f"{year}: filename does not match URL for file {index}",
        )
        sha256 = str(item.get("sha256", ""))
        _require(bool(SHA256.fullmatch(sha256)), f"{year}: file {index} needs SHA-256")
        byte_count = item.get("bytes")
        record_count = item.get("record_count")
        _require(
            isinstance(byte_count, int) and byte_count > 0,
            f"{year}: file {index} needs positive bytes",
        )
        _require(
            isinstance(record_count, int) and record_count > 0,
            f"{year}: file {index} needs positive record_count",
        )
        parsed_files.append(
            ReleaseFile(
                filename=filename,
                url=str(url),
                sha256=sha256,
                bytes=byte_count,
                record_count=record_count,
            )
        )

    _require(
        len(parsed_files) == reference["file_count"],
        f"{year}: file count does not match manifest reference",
    )
    _require(
        len(parsed_files) == reference["inventory_file_count"],
        f"{year}: manifest file count differs from inventory file count",
    )
    total_bytes = sum(item.bytes for item in parsed_files)
    total_records = sum(item.record_count for item in parsed_files)
    _require(
        total_bytes == reference["total_bytes"],
        f"{year}: byte total does not match manifest reference",
    )
    _require(
        total_records == reference["total_record_count"],
        f"{year}: record total does not match manifest reference",
    )
    _require(
        total_bytes == reference["inventory_total_bytes"],
        f"{year}: manifest byte total differs from inventory byte total",
    )
    _require(
        total_records == reference["inventory_total_record_count"],
        f"{year}: manifest record total differs from inventory record total",
    )
    return ReleaseManifest(
        year=year,
        path=path,
        sha256=actual_sha256,
        files=tuple(parsed_files),
        total_bytes=total_bytes,
        total_record_count=total_records,
    )


def load_release_for_year(
    source_path: Path,
    source: dict,
    year: int,
) -> ReleaseManifest:
    references = source.get("manifests")
    _require(isinstance(references, list), "historical record source needs manifests")
    matching = [
        reference
        for reference in references
        if isinstance(reference, dict) and reference.get("year") == year
    ]
    _require(len(matching) == 1, f"{year}: expected exactly one release manifest")
    return load_release_manifest(source_path, matching[0])
