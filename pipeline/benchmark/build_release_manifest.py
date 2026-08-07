"""Build a checksummed manifest from an already-acquired MEDLINE baseline release.

This command does not download data and does not change ``sources.json``. It reads every supplied
XML/XML.gz file, fingerprints the transport bytes, counts parsed PubMed citations, reconciles the
result with the checksum-pinned NLM inventory contract, creates a new manifest without overwriting
an existing one, and prints the small reference object that can be reviewed for the source
contract.

Run:
    python -m pipeline.benchmark.build_release_manifest \
      --year 2010 \
      --base-url https://official.example/baseline/2010/ \
      --output benchmarks/v3/manifests/medline-2010.json \
      data/medline-baseline/2010/*.xml.gz
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from pipeline.benchmark.medline_baseline import (
    fingerprint_file,
    iter_medline_records,
)
from pipeline.benchmark.source_inventories import (
    ReleaseInventory,
    load_inventory_contract,
)
from pipeline.paths import BENCHMARKS_DIR

SOURCES_PATH = BENCHMARKS_DIR / "v3" / "sources.json"


def _validate_https_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise argparse.ArgumentTypeError("URL must be HTTPS")
    return value


def _validate_base_url(value: str) -> str:
    return _validate_https_url(value).rstrip("/") + "/"


def load_pinned_inventory(year: int, source_path: Path = SOURCES_PATH) -> ReleaseInventory:
    """Return one release only after verifying the repository's inventory fingerprint."""
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    required_years = set(payload.get("required_baseline_years", []))
    records = next(
        (
            source
            for source in payload.get("sources", [])
            if source.get("kind") == "historical_records"
        ),
        None,
    )
    if records is None:
        raise ValueError("source contract has no historical-record source")
    contract = load_inventory_contract(
        source_path,
        records.get("inventory_contract", {}),
        required_years,
    )
    matches = [release for release in contract.releases if release.release_year == year]
    if len(matches) != 1:
        raise ValueError(f"{year}: release is not present in the pinned inventory contract")
    return matches[0]


def build_manifest(
    paths: list[Path],
    *,
    year: int,
    base_url: str,
) -> dict:
    if year < 2002:
        raise ValueError("release year must be 2002 or later")
    if not paths:
        raise ValueError("at least one baseline file is required")
    parsed_base = urlsplit(base_url)
    if parsed_base.scheme != "https" or not parsed_base.netloc:
        raise ValueError("base URL must be HTTPS")
    base_url = base_url.rstrip("/") + "/"
    names = [path.name for path in paths]
    if len(names) != len(set(names)):
        raise ValueError("baseline filenames must be unique")

    files = []
    for path in sorted(paths, key=lambda item: item.name):
        if not path.is_file():
            raise FileNotFoundError(path)
        identity = fingerprint_file(path)
        record_count = sum(1 for _record in iter_medline_records([path]))
        if record_count <= 0:
            raise ValueError(f"{path}: no PubmedArticle records parsed")
        files.append(
            {
                "filename": identity.filename,
                "url": urljoin(base_url, identity.filename),
                "sha256": identity.sha256,
                "bytes": identity.bytes,
                "record_count": record_count,
            }
        )
    return {
        "schema_version": 1,
        "kind": "historical_medline_release",
        "release_year": year,
        "files": files,
    }


def validate_inventory_totals(
    manifest: dict,
    *,
    inventory_file_count: int,
    inventory_total_bytes: int,
    inventory_total_record_count: int,
) -> None:
    """Refuse a local subset that disagrees with the supplied independent inventory totals."""
    files = manifest["files"]
    measured = {
        "file count": len(files),
        "total bytes": sum(item["bytes"] for item in files),
        "total record count": sum(item["record_count"] for item in files),
    }
    expected = {
        "file count": inventory_file_count,
        "total bytes": inventory_total_bytes,
        "total record count": inventory_total_record_count,
    }
    for label, actual in measured.items():
        if actual != expected[label]:
            raise ValueError(
                f"manifest {label} differs from the official inventory "
                f"({actual} != {expected[label]})"
            )


def validate_pinned_inventory(manifest: dict, inventory: ReleaseInventory) -> None:
    """Reconcile a generated manifest with independently pinned NLM metadata."""
    if manifest.get("release_year") != inventory.release_year:
        raise ValueError("manifest release year differs from the pinned inventory")
    validate_inventory_totals(
        manifest,
        inventory_file_count=inventory.file_count,
        inventory_total_bytes=inventory.total_compressed_bytes,
        inventory_total_record_count=inventory.total_record_count,
    )
    expected_names = [
        f"medline{str(inventory.release_year)[-2:]}n{index:04d}.xml"
        for index in range(1, inventory.file_count + 1)
    ]
    actual_names = [
        item["filename"][:-3]
        if item["filename"].endswith(".xml.gz")
        else item["filename"]
        for item in manifest["files"]
    ]
    if actual_names != expected_names:
        raise ValueError("manifest filenames do not cover the contiguous official release")


def manifest_reference(
    output: Path,
    manifest: dict,
    *,
    relative_path: str,
    inventory_url: str,
    inventory_file_count: int,
    inventory_total_bytes: int,
    inventory_total_record_count: int,
) -> dict:
    validate_inventory_totals(
        manifest,
        inventory_file_count=inventory_file_count,
        inventory_total_bytes=inventory_total_bytes,
        inventory_total_record_count=inventory_total_record_count,
    )
    raw = output.read_bytes()
    return {
        "year": manifest["release_year"],
        "path": relative_path,
        "inventory_url": inventory_url,
        "inventory_file_count": inventory_file_count,
        "inventory_total_bytes": inventory_total_bytes,
        "inventory_total_record_count": inventory_total_record_count,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "file_count": len(manifest["files"]),
        "total_bytes": sum(item["bytes"] for item in manifest["files"]),
        "total_record_count": sum(item["record_count"] for item in manifest["files"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--year", required=True, type=int)
    parser.add_argument("--base-url", required=True, type=_validate_base_url)
    parser.add_argument(
        "--source-contract",
        type=Path,
        default=SOURCES_PATH,
        help="source contract containing the checksum-pinned official inventory reference",
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--contract-path",
        help="path relative to benchmarks/v3; inferred when output is under that directory",
    )
    args = parser.parse_args()

    contract_path = args.contract_path
    if contract_path is None:
        try:
            contract_path = args.output.resolve().relative_to(
                (BENCHMARKS_DIR / "v3").resolve()
            ).as_posix()
        except ValueError:
            raise SystemExit(
                "--contract-path is required when output is outside benchmarks/v3"
            ) from None
    try:
        inventory = load_pinned_inventory(args.year, args.source_contract)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"cannot load pinned inventory: {exc}") from None
    manifest = build_manifest(args.files, year=args.year, base_url=args.base_url)
    try:
        validate_pinned_inventory(manifest, inventory)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with args.output.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(manifest, handle, indent=2)
            handle.write("\n")
    except FileExistsError:
        raise SystemExit(f"refusing to overwrite existing manifest: {args.output}") from None

    reference = manifest_reference(
        args.output,
        manifest,
        relative_path=contract_path,
        inventory_url=inventory.inventory_url,
        inventory_file_count=inventory.file_count,
        inventory_total_bytes=inventory.total_compressed_bytes,
        inventory_total_record_count=inventory.total_record_count,
    )
    print(json.dumps(reference, indent=2))


if __name__ == "__main__":
    main()
