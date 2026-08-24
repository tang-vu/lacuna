"""Autonomously pin the three PubMed releases required before prospective T1.

The watcher is a control-plane gate.  It observes only official PubMed/MeSH transport
identities, writes at most one refusal-to-overwrite inventory per annual release, and never
scores or labels a candidate.  A missing, skipped, conflicting, or out-of-order observation is
an explicit machine abstention, not permission to repair the evidence manually.

Run:
    python -m pipeline.benchmark.autonomous_release_watch audit
    python -m pipeline.benchmark.autonomous_release_watch status
    python -m pipeline.benchmark.autonomous_release_watch probe
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin

import requests

from pipeline.benchmark.autonomous_t0 import (
    MESH_BASE_URL,
    PUBMED_BASE_URL,
    AutonomousT0Error,
    _bounded_get,
    _session_get,
    _validate_remote_inventory,
    discover_remote_inventory,
    write_new_json,
)
from pipeline.benchmark.validate_autonomous_predictions_v1 import (
    MANIFEST_PATH as PREDICTIONS_PATH,
    audit_predictions_v1,
)
from pipeline.benchmark.validate_autonomous_prospective import (
    PROTOCOL_PATH,
    audit_autonomous_prospective,
)
from pipeline.paths import REPO_ROOT
from pipeline.provenance import sha256_payload

CONTRACT_PATH = REPO_ROOT / "benchmarks" / "autonomous" / "release-watch-v1.json"
DEFAULT_RELEASE_DIR = REPO_ROOT / "benchmarks" / "autonomous" / "releases"
WATCHER_PATH = Path(__file__).resolve()
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "autonomous-release-watch.yml"
EXPECTED_RELEASES = (2027, 2028, 2029)
PROTOCOL_ID = "autonomous-prospective-pubmed-link-emergence-v1"
README_URL = urljoin(PUBMED_BASE_URL, "README.txt")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class AutonomousReleaseWatchError(ValueError):
    """The release control plane cannot advance without weakening a machine gate."""


@dataclass(frozen=True)
class ReleaseInventoryAudit:
    path: Path
    sha256: str
    release_year: int
    pubmed_file_count: int
    mesh_descriptor_count: int
    readiness_contribution: int


@dataclass(frozen=True)
class ReleaseWindowAudit:
    state: str
    verdict: str
    observed_releases: tuple[int, ...]
    missing_releases: tuple[int, ...]
    blockers: tuple[str, ...]
    human_dependency_count: int
    readiness_contribution: int

    @property
    def identifiers_complete(self) -> bool:
        return not self.missing_releases and self.verdict != "abstained"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AutonomousReleaseWatchError(message)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit_release_watch_contract(path: Path = CONTRACT_PATH) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    protocol_payload = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    protocol = audit_autonomous_prospective()
    predictions = audit_predictions_v1()
    _require(payload.get("schema_version") == 1, "unsupported release-watch schema")
    _require(payload.get("id") == "autonomous-prospective-release-watch-v1", "watch id drifted")
    _require(payload.get("status") == "frozen_before_future_release_observation", "watch status drifted")
    _require(payload.get("frozen_on") == "2026-08-24", "watch freeze date drifted")
    _require(payload.get("human_dependencies") == [], "release watch cannot depend on humans")
    _require(payload.get("readiness_contribution") == 0, "release watch claims readiness")
    _require(
        payload.get("protocol")
        == {
            "path": "../autonomous-prospective-v1.json",
            "id": protocol.protocol_id,
            "canonical_json_sha256": sha256_payload(protocol_payload),
        },
        "watch protocol identity drifted",
    )
    _require(
        payload.get("sealed_predictions")
        == {
            "path": "t0-predictions-v1.json",
            "id": predictions.prediction_id,
            "canonical_json_sha256": predictions.sha256,
        },
        "watch prediction identity drifted",
    )
    schedule = payload.get("schedule")
    _require(
        schedule
        == {
            "workflow": ".github/workflows/autonomous-release-watch.yml",
            "cron_utc": "23 4 2 * *",
            "cadence": "monthly",
            "manual_approval_or_labeling": False,
        },
        "watch schedule drifted",
    )
    source = payload.get("official_source")
    _require(
        source
        == {
            "pubmed_baseline": PUBMED_BASE_URL,
            "pubmed_readme": README_URL,
            "mesh_descriptors": MESH_BASE_URL,
            "api_pages_allowed": False,
        },
        "watch official source drifted",
    )
    _require(payload.get("required_release_years") == list(EXPECTED_RELEASES), "release years drifted")
    _require(payload.get("t1_release_year") == EXPECTED_RELEASES[-1], "T1 year drifted")
    _require(
        payload.get("observation_policy")
        == {
            "only_next_sequential_release_may_be_written": True,
            "inventory_filename": "pubmed-{release_year}-remote-inventory.json",
            "overwrite_allowed": False,
            "missing_or_skipped_release_action": "abstain",
            "source_or_checksum_conflict_action": "abstain",
            "credentials_persisted": False,
        },
        "watch observation policy drifted",
    )
    source_identity = payload.get("watcher_source")
    _require(
        isinstance(source_identity, dict)
        and source_identity.get("path") == "../../pipeline/benchmark/autonomous_release_watch.py"
        and source_identity.get("sha256") == _sha256_file(WATCHER_PATH),
        "watcher source identity drifted",
    )
    workflow_identity = payload.get("workflow_source")
    _require(
        isinstance(workflow_identity, dict)
        and workflow_identity.get("path") == "../../.github/workflows/autonomous-release-watch.yml"
        and workflow_identity.get("sha256") == _sha256_file(WORKFLOW_PATH),
        "watch workflow source identity drifted",
    )
    claim = payload.get("claim_boundary", "")
    for phrase in ("source identities only", "not an outcome", "not a discovery", "zero scientific readiness"):
        _require(phrase in claim, f"watch claim boundary omits {phrase}")
    return payload


def _release_inventory_from_t0(payload: dict) -> dict:
    transformed = copy.deepcopy(payload)
    year = transformed["release_year"]
    transformed.update(
        {
            "kind": "autonomous_prospective_release_inventory",
            "status": "remote_release_identity_only_not_a_verified_t1",
            "protocol_id": PROTOCOL_ID,
            "release_role": "prospective_outcome_window_marker",
            "readiness_contribution": 0,
            "human_dependencies": [],
            "machine_gate": {
                "state": "release_identity_observed",
                "pass_condition": "all three sequential post-T0 release identities are pinned before the complete 2029 T1 source may be acquired",
                "failure_action": "abstain",
            },
            "claim_boundary": (
                f"Official PubMed/MeSH {year} remote source identities only; not a verified "
                "T1 source or outcome, not a metric result, and not a discovery or knowledge claim."
            ),
        }
    )
    return transformed


def _as_t0_inventory(payload: dict) -> dict:
    transformed = copy.deepcopy(payload)
    transformed.pop("protocol_id", None)
    transformed.pop("release_role", None)
    transformed.update(
        {
            "kind": "autonomous_t0_remote_inventory",
            "status": "remote_inventory_only_not_a_verified_t0",
            "machine_gate": {
                "state": "awaiting_local_source_bytes",
                "pass_condition": "every PubMed file matches its official MD5 and receives a local SHA-256 and record count; the complete matching MeSH transport matches this inventory",
                "failure_action": "abstain",
            },
            "claim_boundary": (
                "This captures remote source identities only. It is not a T0 baseline, metric "
                "result, validation result, or knowledge-gap claim."
            ),
        }
    )
    return transformed


def discover_release_inventory(
    *,
    release_year: int,
    observed_on: date | None = None,
    fetch: Callable[..., requests.Response] | None = None,
    workers: int = 16,
) -> dict:
    _require(release_year in EXPECTED_RELEASES, "release is outside the frozen outcome window")
    try:
        payload = discover_remote_inventory(
            release_year=release_year,
            observed_on=observed_on,
            fetch=fetch,
            workers=workers,
        )
    except AutonomousT0Error as exc:
        raise AutonomousReleaseWatchError(str(exc)) from exc
    return _release_inventory_from_t0(payload)


def audit_release_inventory(
    path: Path,
    *,
    as_of: date | None = None,
) -> ReleaseInventoryAudit:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AutonomousReleaseWatchError(f"release inventory is not readable JSON: {path}") from exc
    year = payload.get("release_year")
    _require(year in EXPECTED_RELEASES, "release inventory year is outside the frozen window")
    _require(path.name == f"pubmed-{year}-remote-inventory.json", "release inventory filename drifted")
    _require(
        payload.get("kind") == "autonomous_prospective_release_inventory"
        and payload.get("status") == "remote_release_identity_only_not_a_verified_t1"
        and payload.get("protocol_id") == PROTOCOL_ID
        and payload.get("release_role") == "prospective_outcome_window_marker"
        and payload.get("human_dependencies") == []
        and payload.get("readiness_contribution") == 0,
        "release inventory identity or readiness drifted",
    )
    _require(
        payload.get("machine_gate")
        == {
            "state": "release_identity_observed",
            "pass_condition": "all three sequential post-T0 release identities are pinned before the complete 2029 T1 source may be acquired",
            "failure_action": "abstain",
        },
        "release inventory machine gate drifted",
    )
    _require(
        payload.get("claim_boundary")
        == (
            f"Official PubMed/MeSH {year} remote source identities only; not a verified T1 "
            "source or outcome, not a metric result, and not a discovery or knowledge claim."
        ),
        "release inventory claim boundary drifted",
    )
    try:
        validated_year, files, mesh = _validate_remote_inventory(
            _as_t0_inventory(payload),
            as_of=as_of,
        )
    except AutonomousT0Error as exc:
        raise AutonomousReleaseWatchError(str(exc)) from exc
    _require(validated_year == year, "release inventory year drifted during source audit")
    return ReleaseInventoryAudit(
        path=path,
        sha256=sha256_payload(payload),
        release_year=year,
        pubmed_file_count=len(files),
        mesh_descriptor_count=mesh["descriptor_count"],
        readiness_contribution=0,
    )


def audit_release_window(
    release_dir: Path = DEFAULT_RELEASE_DIR,
    *,
    as_of: date | None = None,
) -> ReleaseWindowAudit:
    audit_release_watch_contract()
    if not release_dir.exists():
        paths: list[Path] = []
    else:
        _require(release_dir.is_dir(), "release inventory location is not a directory")
        paths = sorted(release_dir.glob("pubmed-*-remote-inventory.json"))
    audits = [audit_release_inventory(path, as_of=as_of) for path in paths]
    observed = tuple(item.release_year for item in audits)
    _require(len(set(observed)) == len(observed), "duplicate annual release inventories")
    expected_prefix = EXPECTED_RELEASES[: len(observed)]
    if observed != expected_prefix:
        return ReleaseWindowAudit(
            state="abstained",
            verdict="abstained",
            observed_releases=observed,
            missing_releases=tuple(year for year in EXPECTED_RELEASES if year not in observed),
            blockers=("prospective release evidence is missing, skipped, or out of order",),
            human_dependency_count=0,
            readiness_contribution=0,
        )
    missing = EXPECTED_RELEASES[len(observed) :]
    if missing:
        return ReleaseWindowAudit(
            state="predictions_sealed_waiting_for_outcome",
            verdict="not_ready",
            observed_releases=observed,
            missing_releases=missing,
            blockers=(
                "the three-release prospective outcome window has not matured; missing official release identities: "
                + ", ".join(str(year) for year in missing),
            ),
            human_dependency_count=0,
            readiness_contribution=0,
        )
    return ReleaseWindowAudit(
        state="awaiting_t1_baseline",
        verdict="not_ready",
        observed_releases=observed,
        missing_releases=(),
        blockers=("the complete official 2029 T1 source is not locally checksum-verified",),
        human_dependency_count=0,
        readiness_contribution=0,
    )


def _current_official_release_year(
    fetch: Callable[..., requests.Response] | None = None,
) -> int:
    fetch = fetch or _session_get
    try:
        content = _bounded_get(README_URL, fetch=fetch, maximum_bytes=1_000_000)
        text = content.decode("utf-8")
    except (AutonomousT0Error, UnicodeDecodeError) as exc:
        raise AutonomousReleaseWatchError("official PubMed README cannot establish a release year") from exc
    filename = re.search(r"pubmed(\d{2})n0001\.xml", text, re.IGNORECASE)
    updated = re.search(r"Last Updated[^\n]*(20\d{2})", text, re.IGNORECASE)
    _require(filename is not None and updated is not None, "official PubMed README release identity is missing")
    year = int(updated.group(1))
    _require(year % 100 == int(filename.group(1)), "official PubMed README release identifiers disagree")
    return year


def probe_next_release(
    release_dir: Path = DEFAULT_RELEASE_DIR,
    *,
    observed_on: date | None = None,
    fetch: Callable[..., requests.Response] | None = None,
    workers: int = 16,
) -> tuple[ReleaseWindowAudit, Path | None]:
    window = audit_release_window(release_dir, as_of=observed_on)
    if window.verdict == "abstained" or not window.missing_releases:
        return window, None
    next_year = window.missing_releases[0]
    current_year = _current_official_release_year(fetch)
    if current_year < next_year:
        return window, None
    if current_year > next_year:
        return ReleaseWindowAudit(
            state="abstained",
            verdict="abstained",
            observed_releases=window.observed_releases,
            missing_releases=window.missing_releases,
            blockers=(f"official PubMed advanced to {current_year} before release {next_year} was pinned",),
            human_dependency_count=0,
            readiness_contribution=0,
        ), None
    payload = discover_release_inventory(
        release_year=next_year,
        observed_on=observed_on,
        fetch=fetch,
        workers=workers,
    )
    output = release_dir / f"pubmed-{next_year}-remote-inventory.json"
    try:
        write_new_json(output, payload)
    except AutonomousT0Error as exc:
        raise AutonomousReleaseWatchError(str(exc)) from exc
    audit_release_inventory(output, as_of=observed_on)
    return audit_release_window(release_dir, as_of=observed_on), output


def _print_window(window: ReleaseWindowAudit) -> None:
    print(f"autonomous release watch state: {window.state}")
    print(f"verdict: {window.verdict}")
    print("observed releases: " + (", ".join(map(str, window.observed_releases)) or "none"))
    print("missing releases: " + (", ".join(map(str, window.missing_releases)) or "none"))
    print(f"human dependencies: {window.human_dependency_count}")
    print("readiness contribution: 0")
    for blocker in window.blockers:
        print(f"blocker: {blocker}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("audit")
    status = subparsers.add_parser("status")
    status.add_argument("--release-dir", type=Path, default=DEFAULT_RELEASE_DIR)
    probe = subparsers.add_parser("probe")
    probe.add_argument("--release-dir", type=Path, default=DEFAULT_RELEASE_DIR)
    probe.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()
    try:
        if args.command == "audit":
            payload = audit_release_watch_contract()
            print("autonomous release-watch contract: structurally valid and source-pinned")
            print(f"canonical JSON SHA-256: {sha256_payload(payload)}")
            print("human dependencies: 0")
            print("readiness contribution: 0")
            return
        if args.command == "status":
            _print_window(audit_release_window(args.release_dir))
            return
        window, written = probe_next_release(args.release_dir, workers=args.workers)
        if written is not None:
            print(f"pinned release inventory: {written}")
        _print_window(window)
    except (AutonomousReleaseWatchError, OSError, requests.RequestException) as exc:
        raise SystemExit(str(exc)) from None


if __name__ == "__main__":
    main()
