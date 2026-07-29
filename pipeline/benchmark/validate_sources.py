"""Validate and report the source-access gates for metric v3.

This is a structural audit of the dated access record in ``benchmarks/v3/sources.json``. It does
not make live network calls. ``--require-ready`` fails until both historical records and matching
vocabularies are pinned with checksums for every required year.

Run:
    python -m pipeline.benchmark.validate_sources
    python -m pipeline.benchmark.validate_sources --require-ready
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from pipeline.paths import REPO_ROOT

SOURCES_PATH = REPO_ROOT / "benchmarks" / "v3" / "sources.json"
KINDS = {"historical_records", "historical_vocabulary", "current_records"}
STATUSES = {"unavailable", "available_unpinned", "available_pinned", "available_unsuitable"}
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class SourceContractError(ValueError):
    pass


@dataclass(frozen=True)
class SourceAudit:
    statuses: dict[str, str]
    required_years: tuple[int, ...]
    readiness_blockers: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not self.readiness_blockers


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SourceContractError(message)


def _require_https(url: object, context: str) -> None:
    _require(isinstance(url, str), f"{context}: missing URL")
    parsed = urlsplit(url)
    _require(parsed.scheme == "https" and bool(parsed.netloc), f"{context}: URL must be HTTPS")


def audit_sources(path: Path = SOURCES_PATH) -> SourceAudit:
    payload = json.loads(path.read_text(encoding="utf-8"))
    _require(payload.get("schema_version") == 1, "unsupported source schema")
    try:
        date.fromisoformat(str(payload.get("observed_on")))
    except ValueError as exc:
        raise SourceContractError("observed_on must be YYYY-MM-DD") from exc

    required_years = payload.get("required_baseline_years")
    _require(
        isinstance(required_years, list)
        and required_years
        and all(isinstance(year, int) and year >= 2002 for year in required_years),
        "required baseline years must be a non-empty list of years from 2002 onward",
    )
    _require(
        len(required_years) == len(set(required_years)),
        "required baseline years must be unique",
    )

    sources = payload.get("sources")
    _require(isinstance(sources, list), "sources must be a list")
    seen_ids: set[str] = set()
    seen_kinds: set[str] = set()
    statuses: dict[str, str] = {}
    required_kinds: set[str] = set()

    for source in sources:
        _require(isinstance(source, dict), "every source must be an object")
        source_id = source.get("id")
        _require(isinstance(source_id, str) and bool(source_id), "source missing id")
        _require(source_id not in seen_ids, f"{source_id}: duplicate id")
        seen_ids.add(source_id)

        kind = source.get("kind")
        status = source.get("status")
        _require(kind in KINDS, f"{source_id}: unknown kind {kind!r}")
        _require(status in STATUSES, f"{source_id}: unknown status {status!r}")
        _require(kind not in seen_kinds, f"{source_id}: duplicate source kind {kind}")
        seen_kinds.add(kind)
        _require(bool(source.get("observation")), f"{source_id}: missing observation")
        _require(bool(source.get("next_action")), f"{source_id}: missing next action")
        _require(
            isinstance(source.get("required_for_shipping"), bool),
            f"{source_id}: required_for_shipping must be boolean",
        )

        evidence = source.get("evidence")
        _require(isinstance(evidence, list) and evidence, f"{source_id}: missing evidence")
        for index, item in enumerate(evidence):
            _require(isinstance(item, dict), f"{source_id}: malformed evidence {index}")
            _require(bool(item.get("label")), f"{source_id}: evidence {index} missing label")
            _require_https(item.get("url"), f"{source_id}.evidence[{index}]")

        if source["required_for_shipping"]:
            required_kinds.add(kind)
        if status == "available_pinned":
            files = source.get("files")
            _require(
                isinstance(files, list) and files,
                f"{source_id}: pinned source needs files",
            )
            pinned_years: set[int] = set()
            for index, item in enumerate(files):
                _require(isinstance(item, dict), f"{source_id}: malformed file {index}")
                year = item.get("year")
                _require(year in required_years, f"{source_id}: unexpected pinned year {year}")
                if kind == "historical_vocabulary":
                    _require(
                        year not in pinned_years,
                        f"{source_id}: duplicate pinned year {year}",
                    )
                _require_https(item.get("url"), f"{source_id}.files[{index}]")
                _require(
                    bool(SHA256.fullmatch(str(item.get("sha256", "")))),
                    f"{source_id}: file {index} needs a SHA-256 checksum",
                )
                _require(
                    isinstance(item.get("bytes"), int) and item["bytes"] > 0,
                    f"{source_id}: file {index} needs a positive byte count",
                )
                if kind == "historical_vocabulary":
                    _require(
                        isinstance(item.get("descriptor_count"), int)
                        and item["descriptor_count"] > 0,
                        f"{source_id}: file {index} needs a positive descriptor count",
                    )
                elif kind == "historical_records":
                    _require(
                        isinstance(item.get("record_count"), int)
                        and item["record_count"] > 0,
                        f"{source_id}: file {index} needs a positive record count",
                    )
                pinned_years.add(year)
            _require(
                pinned_years == set(required_years),
                f"{source_id}: pinned files must cover every required year",
            )

        statuses[kind] = str(status)

    _require(
        required_kinds == {"historical_records", "historical_vocabulary"},
        "historical records and vocabulary must both be shipping requirements",
    )

    blockers = []
    for kind in ("historical_records", "historical_vocabulary"):
        if statuses.get(kind) != "available_pinned":
            blockers.append(f"{kind}: {statuses.get(kind, 'missing')} (must be available_pinned)")

    return SourceAudit(
        statuses=statuses,
        required_years=tuple(sorted(required_years)),
        readiness_blockers=tuple(blockers),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-ready", action="store_true")
    args = parser.parse_args()

    audit = audit_sources()
    print("v3 historical source contract: structurally valid")
    print("required years: " + ", ".join(str(year) for year in audit.required_years))
    for kind in sorted(audit.statuses):
        print(f"{kind}: {audit.statuses[kind]}")
    if audit.ready:
        print("readiness: READY")
        return

    print("readiness: NOT READY")
    for blocker in audit.readiness_blockers:
        print(f"  - {blocker}")
    if args.require_ready:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
