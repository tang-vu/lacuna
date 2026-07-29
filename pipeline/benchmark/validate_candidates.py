"""Validate the metric-blind v3 candidate intake ledger.

The candidate ledger is deliberately separate from ``cases.json``. Proposed and rejected entries
never count toward benchmark readiness, and accepted entries must link to an actual benchmark case.

Run:
    python -m pipeline.benchmark.validate_candidates
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from pipeline.benchmark.validate_v3 import BENCHMARK_PATH, FORBIDDEN_OUTPUT_FIELDS, KINDS
from pipeline.paths import REPO_ROOT

CANDIDATES_PATH = REPO_ROOT / "benchmarks" / "v3" / "candidates.json"
STATUSES = ("accepted", "proposed", "rejected")


class CandidateContractError(ValueError):
    pass


@dataclass(frozen=True)
class CandidateAudit:
    counts: dict[str, int]
    accepted_benchmark_ids: tuple[str, ...]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CandidateContractError(message)


def _require_https(url: object, context: str) -> None:
    _require(isinstance(url, str), f"{context}: missing URL")
    parts = urlsplit(url)
    _require(parts.scheme == "https" and bool(parts.netloc), f"{context}: URL must be HTTPS")


def _find_forbidden_fields(value: object, path: str = "$") -> list[str]:
    found = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key in FORBIDDEN_OUTPUT_FIELDS:
                found.append(child_path)
            found.extend(_find_forbidden_fields(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_find_forbidden_fields(child, f"{path}[{index}]"))
    return found


def _load_benchmark_cases(path: Path) -> dict[str, dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases")
    _require(isinstance(cases, list), "benchmark cases must be a list")
    return {case["id"]: case for case in cases}


def audit_candidates(
    path: Path = CANDIDATES_PATH,
    benchmark_path: Path = BENCHMARK_PATH,
) -> CandidateAudit:
    payload = json.loads(path.read_text(encoding="utf-8"))
    _require(payload.get("schema_version") == 1, "unsupported candidate schema")
    _require(bool(payload.get("purpose")), "candidate ledger needs an explicit purpose")

    policy = payload.get("policy")
    _require(isinstance(policy, dict), "missing candidate policy")
    for flag in (
        "metric_blind",
        "accepted_only_enters_benchmark",
        "acceptance_requires_independent_replication",
    ):
        _require(policy.get(flag) is True, f"policy.{flag} must remain true")

    candidates = payload.get("candidates")
    _require(isinstance(candidates, list), "candidates must be a list")
    forbidden = _find_forbidden_fields(candidates)
    _require(
        not forbidden,
        "candidate intake contains metric output fields: " + ", ".join(forbidden),
    )

    benchmark_cases = _load_benchmark_cases(benchmark_path)
    counts = {status: 0 for status in STATUSES}
    accepted_benchmark_ids: list[str] = []
    seen: set[str] = set()

    for candidate in candidates:
        _require(isinstance(candidate, dict), "every candidate must be an object")
        candidate_id = candidate.get("id")
        _require(isinstance(candidate_id, str) and bool(candidate_id), "candidate missing id")
        _require(candidate_id not in seen, f"{candidate_id}: duplicate id")
        seen.add(candidate_id)

        status = candidate.get("status")
        _require(status in STATUSES, f"{candidate_id}: unknown status {status!r}")
        _require(
            candidate.get("proposed_kind") in KINDS,
            f"{candidate_id}: unknown proposed kind",
        )
        _require(
            candidate.get("selection_stage") == "pre_metric",
            f"{candidate_id}: candidate was not selected pre-metric",
        )

        concepts = candidate.get("concepts")
        _require(
            isinstance(concepts, dict) and set(concepts) == {"a", "c"},
            f"{candidate_id}: concepts must contain exactly a and c",
        )
        for role in ("a", "c"):
            concept = concepts[role]
            _require(
                isinstance(concept, dict) and bool(concept.get("label")),
                f"{candidate_id}.{role}: missing concept label",
            )
            if "source_entity_id" in concept:
                _require(
                    isinstance(concept["source_entity_id"], str)
                    and ":" in concept["source_entity_id"],
                    f"{candidate_id}.{role}: malformed source entity id",
                )

        bridge = candidate.get("bridge")
        if bridge is not None:
            _require(
                isinstance(bridge, dict)
                and bool(bridge.get("label"))
                and isinstance(bridge.get("source_entity_id"), str)
                and ":" in bridge["source_entity_id"],
                f"{candidate_id}: malformed bridge identity",
            )

        if "source_discovery_year" in candidate:
            _require(
                isinstance(candidate["source_discovery_year"], int)
                and candidate["source_discovery_year"] >= 1900,
                f"{candidate_id}: malformed source discovery year",
            )
            _require(
                isinstance(candidate.get("source_evaluation_lag_years"), int)
                and candidate["source_evaluation_lag_years"] > 0,
                f"{candidate_id}: discovery year needs a positive evaluation lag",
            )

        if "candidate_cutoff" in candidate:
            try:
                date.fromisoformat(str(candidate["candidate_cutoff"]))
            except ValueError as exc:
                raise CandidateContractError(
                    f"{candidate_id}: candidate_cutoff must be YYYY-MM-DD"
                ) from exc

        evidence = candidate.get("evidence")
        _require(isinstance(evidence, list) and evidence, f"{candidate_id}: missing evidence")
        evidence_roles: set[str] = set()
        for index, source in enumerate(evidence):
            _require(
                isinstance(source, dict),
                f"{candidate_id}: evidence {index} is malformed",
            )
            _require(bool(source.get("role")), f"{candidate_id}: evidence {index} missing role")
            _require(bool(source.get("label")), f"{candidate_id}: evidence {index} missing label")
            _require_https(source.get("url"), f"{candidate_id}.evidence[{index}]")
            evidence_roles.add(source["role"])

        adjudication = candidate.get("adjudication")
        _require(isinstance(adjudication, dict), f"{candidate_id}: missing adjudication")
        _require(bool(adjudication.get("rationale")), f"{candidate_id}: missing rationale")
        _require(
            adjudication.get("decision") == status,
            f"{candidate_id}: adjudication decision must match status",
        )

        if status == "accepted":
            benchmark_case_id = candidate.get("benchmark_case_id")
            _require(
                isinstance(benchmark_case_id, str) and benchmark_case_id in benchmark_cases,
                f"{candidate_id}: accepted candidate must link to a benchmark case",
            )
            _require(
                {"selection_source", "bridge_publication", "independent_replication"}
                <= evidence_roles,
                f"{candidate_id}: acceptance needs selection, bridge, and independent replication",
            )
            _require(
                candidate.get("candidate_cutoff") == benchmark_cases[benchmark_case_id]["cutoff"],
                f"{candidate_id}: candidate cutoff differs from benchmark case",
            )
            benchmark_concepts = benchmark_cases[benchmark_case_id]["concepts"]
            for role in ("a", "c"):
                _require(
                    concepts[role]["label"] == benchmark_concepts[role]["label"],
                    f"{candidate_id}.{role}: label differs from benchmark case",
                )
            _require(
                candidate["proposed_kind"] == benchmark_cases[benchmark_case_id]["kind"],
                f"{candidate_id}: kind differs from benchmark case",
            )
            try:
                date.fromisoformat(str(adjudication.get("decided_on")))
            except ValueError as exc:
                raise CandidateContractError(
                    f"{candidate_id}: accepted decision needs a YYYY-MM-DD date"
                ) from exc
            accepted_benchmark_ids.append(benchmark_case_id)
        elif status == "proposed":
            _require(
                "benchmark_case_id" not in candidate,
                f"{candidate_id}: proposed candidate cannot enter the benchmark",
            )
            _require(
                isinstance(candidate.get("open_questions"), list)
                and bool(candidate["open_questions"]),
                f"{candidate_id}: proposed candidate needs open questions",
            )
            _require(
                "selection_source" in evidence_roles,
                f"{candidate_id}: proposed candidate needs a selection source",
            )
        else:
            _require(
                "benchmark_case_id" not in candidate,
                f"{candidate_id}: rejected candidate cannot enter the benchmark",
            )
            _require(
                "methodological_rejection" in evidence_roles,
                f"{candidate_id}: rejected candidate needs rejection evidence",
            )
            try:
                date.fromisoformat(str(adjudication.get("decided_on")))
            except ValueError as exc:
                raise CandidateContractError(
                    f"{candidate_id}: rejected decision needs a YYYY-MM-DD date"
                ) from exc

        counts[status] += 1

    _require(
        len(accepted_benchmark_ids) == len(set(accepted_benchmark_ids)),
        "multiple candidates link to the same benchmark case",
    )
    _require(
        set(accepted_benchmark_ids) == set(benchmark_cases),
        "every benchmark case must have exactly one accepted intake record",
    )

    return CandidateAudit(
        counts=counts,
        accepted_benchmark_ids=tuple(sorted(accepted_benchmark_ids)),
    )


def main() -> None:
    audit = audit_candidates()
    print("v3 candidate intake: structurally valid")
    print("status: " + ", ".join(f"{status}={audit.counts[status]}" for status in STATUSES))
    print(f"accepted benchmark links: {len(audit.accepted_benchmark_ids)}")
    print("readiness contribution: none (cases.json remains the only readiness input)")


if __name__ == "__main__":
    main()
