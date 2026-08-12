"""Validate the pre-metric v3 benchmark contract and report readiness honestly.

The default command validates a draft without pretending it is ready. ``--require-ready`` is the
shipping gate and fails until case counts, held-out splits, historical mappings, and the freeze
flags all satisfy the contract.

Run:
    python -m pipeline.benchmark.validate_v3
    python -m pipeline.benchmark.validate_v3 --require-ready
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from pipeline.benchmark.metric_blind import find_forbidden_fields
from pipeline.paths import REPO_ROOT

BENCHMARK_PATH = REPO_ROOT / "benchmarks" / "v3" / "cases.json"
NEGATIVE_QUEUE_PATH = REPO_ROOT / "artifacts" / "negative-candidates.json"
NEGATIVE_QUEUE_PUBLIC_URL = (
    "https://github.com/tang-vu/lacuna/blob/"
    "e33d6c297ed09c5ff4edf7eacdaa51effcdca319/artifacts/negative-candidates.json"
)
KINDS = ("positive", "hard_negative", "distant_negative")
SPLITS = {"development", "heldout"}
MAPPING_STATUSES = {
    "period_appropriate",
    "maintained_current",
    "ambiguous",
    "unavailable",
}
EXPECTED_REQUIREMENTS = {
    "minimum_per_kind": 8,
    "minimum_heldout_per_kind": 4,
    "minimum_period_appropriate_heldout_cutoffs": 2,
}
DESCRIPTOR_UI = re.compile(r"^D\d{6}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class BenchmarkContractError(ValueError):
    pass


@dataclass(frozen=True)
class BenchmarkAudit:
    counts: dict[str, int]
    heldout_counts: dict[str, int]
    mapping_counts: dict[str, int]
    period_appropriate_heldout_cutoffs: tuple[str, ...]
    readiness_blockers: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not self.readiness_blockers


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BenchmarkContractError(message)


def _require_https(url: object, context: str) -> None:
    _require(isinstance(url, str), f"{context}: missing URL")
    parts = urlsplit(url)
    _require(parts.scheme == "https" and bool(parts.netloc), f"{context}: URL must be HTTPS")


def _validate_mapping(mapping: dict, context: str) -> str:
    status = mapping.get("status")
    _require(status in MAPPING_STATUSES, f"{context}: unknown mapping status {status!r}")

    if status in {"period_appropriate", "maintained_current"}:
        _require(
            bool(DESCRIPTOR_UI.fullmatch(str(mapping.get("descriptor_ui", "")))),
            f"{context}: invalid MeSH descriptor UI",
        )
        _require(bool(mapping.get("descriptor_label")), f"{context}: missing descriptor label")
        _require(
            isinstance(mapping.get("vocabulary_year"), int),
            f"{context}: missing vocabulary year",
        )
        _require_https(mapping.get("evidence_url"), f"{context}.evidence_url")

    if status == "maintained_current":
        _require(bool(mapping.get("note")), f"{context}: current mapping must state its limitation")
        try:
            date.fromisoformat(str(mapping.get("verified_on")))
        except ValueError as exc:
            raise BenchmarkContractError(
                f"{context}: current mapping needs a YYYY-MM-DD verification date"
            ) from exc

    if status == "period_appropriate":
        baseline = mapping.get("baseline")
        _require(isinstance(baseline, dict), f"{context}: missing archived baseline identity")
        _require(
            isinstance(baseline.get("year"), int) and baseline["year"] >= 2002,
            f"{context}: official archived baselines begin in 2002",
        )
        _require(
            mapping["vocabulary_year"] == baseline["year"],
            f"{context}: vocabulary year must match baseline year",
        )
        _require_https(baseline.get("source_url"), f"{context}.baseline.source_url")
        _require(
            bool(SHA256.fullmatch(str(baseline.get("sha256", "")))),
            f"{context}: baseline must carry a SHA-256 checksum",
        )

    if status == "ambiguous":
        options = mapping.get("options")
        _require(
            isinstance(options, list) and len(options) >= 2,
            f"{context}: ambiguous mapping needs at least two options",
        )
        for option in options:
            _require(
                isinstance(option, dict)
                and bool(DESCRIPTOR_UI.fullmatch(str(option.get("descriptor_ui", ""))))
                and bool(option.get("descriptor_label")),
                f"{context}: malformed ambiguous option",
            )
        _require(bool(mapping.get("note")), f"{context}: ambiguous mapping needs an explanation")

    if status == "unavailable":
        _require(bool(mapping.get("note")), f"{context}: unavailable mapping needs an explanation")

    return str(status)


def _load_negative_proposals(path: Path) -> dict[str, dict]:
    """Load only a queue that still satisfies its frozen, metric-blind contract."""
    from pipeline.benchmark.negative_controls import audit_queue

    try:
        audit_queue(path)
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BenchmarkContractError(f"negative queue failed validation: {exc}") from exc
    return {item["id"]: item for item in payload["candidates"]}


def _has_public_adjudication(evidence: list[dict], issue: int) -> bool:
    expected_path = f"/tang-vu/lacuna/issues/{issue}"
    for source in evidence:
        if source.get("role") != "metric_blind_adjudication":
            continue
        parts = urlsplit(str(source.get("url", "")))
        if (
            parts.scheme == "https"
            and parts.hostname == "github.com"
            and parts.path == expected_path
            and re.fullmatch(r"issuecomment-\d+", parts.fragment)
            and source.get("metric_output_blind_attestation") is True
        ):
            return True
    return False


def audit_benchmark(
    path: Path = BENCHMARK_PATH,
    *,
    negative_queue_path: Path = NEGATIVE_QUEUE_PATH,
) -> BenchmarkAudit:
    payload = json.loads(path.read_text(encoding="utf-8"))
    _require(payload.get("schema_version") == 1, "unsupported benchmark schema")
    _require(payload.get("status") in {"draft", "frozen"}, "status must be draft or frozen")
    _require(
        payload.get("preregistration") == "plans/metric-v3-validation-plan.md",
        "benchmark must point to the v3 validation plan",
    )

    forbidden = find_forbidden_fields(payload.get("cases", []))
    _require(
        not forbidden,
        "case selection contains metric output fields: " + ", ".join(forbidden),
    )

    requirements = payload.get("requirements")
    _require(isinstance(requirements, dict), "missing readiness requirements")
    _require(
        requirements == EXPECTED_REQUIREMENTS,
        f"readiness requirements must remain {EXPECTED_REQUIREMENTS}",
    )

    selection = payload.get("selection")
    _require(isinstance(selection, dict), "missing selection state")
    _require(isinstance(selection.get("frozen"), bool), "selection.frozen must be boolean")
    _require(
        isinstance(selection.get("completed_before_metric"), bool),
        "selection.completed_before_metric must be boolean",
    )

    negative_proposals = _load_negative_proposals(negative_queue_path)

    cases = payload.get("cases")
    _require(isinstance(cases, list), "cases must be a list")
    counts = {kind: 0 for kind in KINDS}
    heldout_counts = {kind: 0 for kind in KINDS}
    mapping_counts = {status: 0 for status in sorted(MAPPING_STATUSES)}
    eligible_cutoffs: set[str] = set()
    seen: set[str] = set()
    linked_negative_proposals: set[str] = set()

    for case in cases:
        _require(isinstance(case, dict), "every case must be an object")
        case_id = case.get("id")
        _require(isinstance(case_id, str) and bool(case_id), "case missing id")
        _require(case_id not in seen, f"{case_id}: duplicate id")
        seen.add(case_id)

        kind = case.get("kind")
        split = case.get("split")
        _require(kind in KINDS, f"{case_id}: unknown kind {kind!r}")
        _require(split in SPLITS, f"{case_id}: unknown split {split!r}")
        _require(case.get("selection_stage") == "pre_metric", f"{case_id}: not pre-metric")
        _require(bool(case.get("selection_rationale")), f"{case_id}: missing selection rationale")
        try:
            cutoff = date.fromisoformat(str(case.get("cutoff")))
        except ValueError as exc:
            raise BenchmarkContractError(f"{case_id}: cutoff must be YYYY-MM-DD") from exc

        evidence = case.get("evidence")
        _require(isinstance(evidence, list) and evidence, f"{case_id}: missing evidence")
        evidence_roles: set[str] = set()
        for index, source in enumerate(evidence):
            _require(isinstance(source, dict), f"{case_id}: evidence {index} is malformed")
            _require(bool(source.get("label")), f"{case_id}: evidence {index} missing label")
            _require_https(source.get("url"), f"{case_id}.evidence[{index}]")
            if isinstance(source.get("role"), str):
                evidence_roles.add(source["role"])
        if kind == "positive":
            _require(
                "bridge_publication" in evidence_roles,
                f"{case_id}: positive case needs a bridge publication",
            )
            _require(
                "selection_candidate_id" not in case,
                f"{case_id}: positive case cannot link to a negative proposal",
            )
        else:
            _require(bool(case.get("negative_rationale")), f"{case_id}: missing negative rationale")
            _require(
                "negative_selection_source" in evidence_roles,
                f"{case_id}: negative case needs a selection source",
            )
            _require(
                any(
                    source.get("role") == "negative_selection_source"
                    and source.get("url") == NEGATIVE_QUEUE_PUBLIC_URL
                    for source in evidence
                ),
                f"{case_id}: negative selection source must be the frozen review queue",
            )
            proposal_id = case.get("selection_candidate_id")
            _require(
                isinstance(proposal_id, str) and proposal_id in negative_proposals,
                f"{case_id}: unknown negative proposal {proposal_id!r}",
            )
            _require(
                proposal_id not in linked_negative_proposals,
                f"{case_id}: negative proposal {proposal_id} is already linked",
            )
            linked_negative_proposals.add(proposal_id)
            proposal = negative_proposals[proposal_id]
            _require(
                kind == proposal["kind"],
                f"{case_id}: kind differs from frozen proposal",
            )
            _require(
                _has_public_adjudication(
                    evidence,
                    4 if kind == "hard_negative" else 3,
                ),
                f"{case_id}: negative case needs a direct public metric-blind adjudication",
            )
            _require(
                any(source.get("role") == "review_evidence" for source in evidence),
                f"{case_id}: negative case needs public review evidence beyond generated queries",
            )
            _require(
                split == proposal["proposed_split"],
                f"{case_id}: split differs from frozen proposal",
            )
            _require(
                case.get("cutoff") == proposal["cutoff"],
                f"{case_id}: cutoff differs from frozen proposal",
            )

        concepts = case.get("concepts")
        _require(
            isinstance(concepts, dict) and set(concepts) == {"a", "c"},
            f"{case_id}: concepts must contain exactly a and c",
        )
        statuses = []
        for role in ("a", "c"):
            concept = concepts[role]
            _require(isinstance(concept, dict), f"{case_id}.{role}: malformed concept")
            _require(bool(concept.get("label")), f"{case_id}.{role}: missing label")
            _require(
                isinstance(concept.get("mapping"), dict),
                f"{case_id}.{role}: missing mapping",
            )
            status = _validate_mapping(concept["mapping"], f"{case_id}.{role}.mapping")
            mapping_counts[status] += 1
            statuses.append(status)
            if kind != "positive":
                proposal_concept = proposal["concepts"][role]
                _require(
                    concept["label"] == proposal_concept["descriptor_label"],
                    f"{case_id}: concept {role} differs from frozen proposal",
                )
                if status in {"period_appropriate", "maintained_current"}:
                    _require(
                        concept["mapping"]["descriptor_ui"]
                        == proposal_concept["descriptor_ui"]
                        and concept["mapping"]["descriptor_label"]
                        == proposal_concept["descriptor_label"],
                        f"{case_id}: mapped concept {role} differs from frozen proposal",
                    )

        counts[kind] += 1
        if split == "heldout":
            heldout_counts[kind] += 1
            if (
                cutoff.year >= 2002
                and statuses == ["period_appropriate", "period_appropriate"]
            ):
                eligible_cutoffs.add(case["cutoff"])

    blockers = []
    for kind in KINDS:
        missing = requirements["minimum_per_kind"] - counts[kind]
        if missing > 0:
            blockers.append(f"{kind}: {missing} more case(s) required")
        missing_heldout = requirements["minimum_heldout_per_kind"] - heldout_counts[kind]
        if missing_heldout > 0:
            blockers.append(f"{kind}: {missing_heldout} more held-out case(s) required")

    missing_cutoffs = (
        requirements["minimum_period_appropriate_heldout_cutoffs"] - len(eligible_cutoffs)
    )
    if missing_cutoffs > 0:
        blockers.append(
            f"period-appropriate held-out cutoffs: {missing_cutoffs} more required"
        )
    if payload["status"] != "frozen":
        blockers.append("benchmark status is draft")
    if not selection["frozen"]:
        blockers.append("case selection is not frozen")
    if not selection["completed_before_metric"]:
        blockers.append("pre-metric selection is not marked complete")

    return BenchmarkAudit(
        counts=counts,
        heldout_counts=heldout_counts,
        mapping_counts=mapping_counts,
        period_appropriate_heldout_cutoffs=tuple(sorted(eligible_cutoffs)),
        readiness_blockers=tuple(blockers),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-ready", action="store_true")
    args = parser.parse_args()

    audit = audit_benchmark()
    print("v3 benchmark contract: structurally valid")
    print("cases: " + ", ".join(f"{kind}={audit.counts[kind]}" for kind in KINDS))
    print(
        "held out: "
        + ", ".join(f"{kind}={audit.heldout_counts[kind]}" for kind in KINDS)
    )
    print(
        "mapping statuses: "
        + ", ".join(
            f"{status}={count}" for status, count in audit.mapping_counts.items()
        )
    )
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
