"""Validate the evidence-bounded alternatives to unavailable historical baselines.

This contract is a research-routing aid, not a second path around the metric-v3 source gate. Every
current entry contributes zero readiness. A dated secondary snapshot can support a redesigned,
separately pre-registered experiment only after acquisition and payload-level audit.

Run: ``python -m pipeline.benchmark.validate_source_alternatives``
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from pipeline.benchmark.bioasq_semantics import audit_semantics_protocol
from pipeline.paths import REPO_ROOT

ALTERNATIVES_PATH = REPO_ROOT / "benchmarks" / "v3" / "source-alternatives.json"
STATUSES = {
    "candidate_requires_acquisition_audit",
    "engineering_only",
    "rejected_for_historical_gate",
}
ACCESS_MODES = {"public", "registration_required", "public_documentation_only"}


class SourceAlternativeContractError(ValueError):
    pass


@dataclass(frozen=True)
class SourceAlternativeAudit:
    status: str
    recommended_id: str
    counts: dict[str, int]
    readiness_contribution: int
    entries: tuple[dict, ...]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SourceAlternativeContractError(message)


def _require_https(value: object, context: str) -> None:
    _require(isinstance(value, str), f"{context}: missing URL")
    parsed = urlsplit(value)
    _require(parsed.scheme == "https" and bool(parsed.netloc), f"{context}: URL must be HTTPS")


def _require_text_list(value: object, context: str) -> None:
    _require(isinstance(value, list) and value, f"{context}: needs a non-empty list")
    _require(
        all(isinstance(item, str) and item.strip() for item in value),
        f"{context}: entries must be non-empty strings",
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _audit_public_sample_reference(value: object, context: str) -> None:
    _require(isinstance(value, dict), f"{context}: missing public sample audit")
    _require(set(value) == {"path", "sha256"}, f"{context}: malformed public sample reference")
    relative = Path(str(value["path"]))
    _require(not relative.is_absolute() and ".." not in relative.parts, f"{context}: unsafe path")
    path = REPO_ROOT / relative
    _require(path.is_file(), f"{context}: referenced public sample audit is missing")
    expected_sha256 = value.get("sha256")
    _require(
        isinstance(expected_sha256, str)
        and len(expected_sha256) == 64
        and _sha256_file(path) == expected_sha256,
        f"{context}: public sample audit checksum mismatch",
    )
    audit = json.loads(path.read_text(encoding="utf-8"))
    _require(audit.get("schema_version") == 1, f"{context}: unsupported sample audit schema")
    _require(
        audit.get("status") == "bounded_public_sample_audit",
        f"{context}: sample result must remain explicitly bounded",
    )
    _require(audit.get("readiness_contribution") == 0, f"{context}: sample cannot add readiness")
    _require(
        audit.get("source_alternative_id") == "bioasq-2013-task-a",
        f"{context}: wrong source alternative",
    )
    sample = audit.get("bioasq_public_sample")
    mesh = audit.get("mesh_vocabulary")
    comparison = audit.get("maintained_current_pubmed_comparison")
    _require(isinstance(sample, dict) and sample.get("article_count") == 5, f"{context}: wrong sample")
    _require(
        isinstance(mesh, dict)
        and mesh.get("year") == 2013
        and isinstance(mesh.get("sha256"), str)
        and len(mesh["sha256"]) == 64,
        f"{context}: sample audit does not identify pinned MeSH 2013",
    )
    _require(
        isinstance(comparison, dict)
        and comparison.get("records_returned") == sample["article_count"]
        and comparison.get("sample_assignments") == sample.get("mesh_assignment_count"),
        f"{context}: PubMed comparison does not reconcile with sample",
    )
    _require_text_list(audit.get("limitations"), f"{context}.limitations")


def _audit_semantics_protocol_reference(value: object, context: str) -> None:
    _require(isinstance(value, dict), f"{context}: missing semantics protocol")
    _require(set(value) == {"path", "sha256"}, f"{context}: malformed protocol reference")
    relative = Path(str(value["path"]))
    _require(not relative.is_absolute() and ".." not in relative.parts, f"{context}: unsafe path")
    path = REPO_ROOT / relative
    _require(path.is_file(), f"{context}: referenced semantics protocol is missing")
    _require(
        isinstance(value.get("sha256"), str)
        and len(value["sha256"]) == 64
        and _sha256_file(path) == value["sha256"],
        f"{context}: semantics protocol checksum mismatch",
    )
    protocol = audit_semantics_protocol(path)
    sampling = protocol["sampling"]
    _require(sampling["total_sample_size"] == 416, f"{context}: frozen sample size drifted")
    _require(
        [item["id"] for item in sampling["strata"]]
        == [
            "y1950_1969",
            "y1970_1989",
            "y1990_1999",
            "y2000_2006",
            "y2007_2010",
            "y2011",
            "y2012",
            "y2013",
        ],
        f"{context}: frozen year strata drifted",
    )


def audit_source_alternatives(
    path: Path = ALTERNATIVES_PATH,
) -> SourceAlternativeAudit:
    payload = json.loads(path.read_text(encoding="utf-8"))
    _require(payload.get("schema_version") == 1, "unsupported source-alternatives schema")
    try:
        date.fromisoformat(str(payload.get("observed_on")))
    except ValueError as exc:
        raise SourceAlternativeContractError("observed_on must be YYYY-MM-DD") from exc
    _require(
        payload.get("status") == "no_equivalent_replacement_pinned",
        "alternatives status must not imply that an equivalent replacement is pinned",
    )
    _require(bool(payload.get("purpose")), "source alternatives need a purpose")
    decision_rule = payload.get("decision_rule")
    _require(
        isinstance(decision_rule, dict)
        and set(decision_rule)
        == {"original_gate", "redesign_gate", "current_or_title_abstract_only_data"}
        and all(isinstance(value, str) and value.strip() for value in decision_rule.values()),
        "source alternatives need all three decision rules",
    )

    alternatives = payload.get("alternatives")
    _require(isinstance(alternatives, list) and alternatives, "alternatives must be a list")
    seen: set[str] = set()
    counts: Counter[str] = Counter()
    for index, entry in enumerate(alternatives):
        _require(isinstance(entry, dict), f"alternative {index}: expected an object")
        entry_id = entry.get("id")
        _require(isinstance(entry_id, str) and entry_id, f"alternative {index}: missing id")
        _require(entry_id not in seen, f"{entry_id}: duplicate alternative id")
        seen.add(entry_id)
        _require(bool(entry.get("label")), f"{entry_id}: missing label")
        status = entry.get("status")
        _require(status in STATUSES, f"{entry_id}: unsupported status {status!r}")
        counts[str(status)] += 1
        _require(bool(entry.get("source_class")), f"{entry_id}: missing source class")
        _require(entry.get("access") in ACCESS_MODES, f"{entry_id}: unsupported access mode")
        _require(
            entry.get("readiness_contribution") == 0,
            f"{entry_id}: an unaudited alternative cannot contribute readiness",
        )
        _require(
            entry.get("can_replace_original_gate") is False,
            f"{entry_id}: alternative cannot claim to replace the original gate",
        )
        _require(bool(entry.get("potential_role")), f"{entry_id}: missing potential role")
        _require_text_list(entry.get("blockers"), f"{entry_id}.blockers")
        _require(bool(entry.get("next_action")), f"{entry_id}: missing next action")
        evidence = entry.get("evidence")
        _require(isinstance(evidence, list) and evidence, f"{entry_id}: missing evidence")
        for evidence_index, item in enumerate(evidence):
            _require(isinstance(item, dict), f"{entry_id}: malformed evidence")
            _require(bool(item.get("label")), f"{entry_id}: evidence missing label")
            _require_https(item.get("url"), f"{entry_id}.evidence[{evidence_index}]")

        if status == "candidate_requires_acquisition_audit":
            declared = entry.get("declared_snapshot")
            _require(isinstance(declared, dict), f"{entry_id}: missing declared snapshot")
            for field in ("version_year", "article_count", "mesh_label_count"):
                _require(
                    isinstance(declared.get(field), int) and declared[field] > 0,
                    f"{entry_id}: {field} must be a positive integer",
                )
            _require(
                isinstance(declared.get("average_mesh_labels_per_article"), (int, float))
                and declared["average_mesh_labels_per_article"] > 0,
                f"{entry_id}: average MeSH labels must be positive",
            )
            _require_text_list(declared.get("record_fields"), f"{entry_id}.record_fields")
            if entry_id == "bioasq-2013-task-a":
                _audit_public_sample_reference(
                    entry.get("public_sample_audit"), f"{entry_id}.public_sample_audit"
                )
                _audit_semantics_protocol_reference(
                    entry.get("semantics_protocol"), f"{entry_id}.semantics_protocol"
                )

    recommended_id = payload.get("recommended_alternative_id")
    _require(recommended_id in seen, "recommended alternative does not exist")
    recommended = next(entry for entry in alternatives if entry["id"] == recommended_id)
    _require(
        recommended["status"] == "candidate_requires_acquisition_audit",
        "recommended alternative must still require acquisition audit",
    )

    serialized = json.dumps(payload, ensure_ascii=False)
    _require("CAS-" not in serialized, "support case identifiers must not be committed")
    _require("@gmail.com" not in serialized, "personal email addresses must not be committed")
    return SourceAlternativeAudit(
        status=payload["status"],
        recommended_id=str(recommended_id),
        counts=dict(sorted(counts.items())),
        readiness_contribution=sum(entry["readiness_contribution"] for entry in alternatives),
        entries=tuple(alternatives),
    )


def main() -> None:
    audit = audit_source_alternatives()
    print("source alternatives contract: structurally valid")
    print(f"status: {audit.status}")
    print(f"recommended audit: {audit.recommended_id}")
    for status, count in audit.counts.items():
        print(f"{status}: {count}")
    print(f"readiness contribution: {audit.readiness_contribution}")


if __name__ == "__main__":
    main()
