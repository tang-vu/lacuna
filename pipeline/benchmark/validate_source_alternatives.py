"""Validate the evidence-bounded alternatives to unavailable historical baselines.

This contract is a research-routing aid, not a second path around the metric-v3 source gate. Every
current entry contributes zero readiness. A dated secondary snapshot can support a redesigned,
separately pre-registered experiment only after payload-level audit and a protocol scoped to the
measured input.

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

from pipeline.benchmark.bioasq_semantics import (
    audit_semantics_manifest,
    audit_semantics_protocol,
)
from pipeline.benchmark.bioasq_pilot_compatibility import audit_compatibility_manifest
from pipeline.benchmark.validate_bioasq_pilot import audit_bioasq_pilot
from pipeline.benchmark.validate_bioasq_pilot_v2 import audit_bioasq_pilot_v2
from pipeline.paths import REPO_ROOT

ALTERNATIVES_PATH = REPO_ROOT / "benchmarks" / "v3" / "source-alternatives.json"
STATUSES = {
    "audited_scope_mismatch",
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


def _audit_successor_semantics_protocol_reference(value: object, context: str) -> None:
    _require(isinstance(value, dict), f"{context}: missing successor semantics protocol")
    _require(set(value) == {"path", "sha256"}, f"{context}: malformed protocol reference")
    relative = Path(str(value["path"]))
    _require(not relative.is_absolute() and ".." not in relative.parts, f"{context}: unsafe path")
    path = REPO_ROOT / relative
    _require(path.is_file(), f"{context}: referenced successor protocol is missing")
    _require(
        isinstance(value.get("sha256"), str)
        and len(value["sha256"]) == 64
        and _sha256_file(path) == value["sha256"],
        f"{context}: successor protocol checksum mismatch",
    )
    protocol = audit_semantics_protocol(path)
    sampling = protocol["sampling"]
    _require(
        protocol["status"] == "frozen_after_source_audit_before_semantics_selection",
        f"{context}: wrong successor freeze stage",
    )
    _require(
        sampling["total_sample_size"] == 448,
        f"{context}: successor sample size drifted",
    )
    _require(
        [item["id"] for item in sampling["strata"]]
        == [
            "y1946_1949",
            "y1950_1969",
            "y1970_1989",
            "y1990_1999",
            "y2000_2006",
            "y2007_2010",
            "y2011",
            "y2012",
            "y2013",
        ],
        f"{context}: successor year strata drifted",
    )


def _audit_semantics_manifest_reference(
    value: object,
    context: str,
    *,
    protocol_reference: object,
    snapshot_reference: object,
) -> None:
    _require(isinstance(value, dict), f"{context}: missing semantics audit")
    _require(set(value) == {"path", "sha256"}, f"{context}: malformed audit reference")
    relative = Path(str(value["path"]))
    _require(not relative.is_absolute() and ".." not in relative.parts, f"{context}: unsafe path")
    path = REPO_ROOT / relative
    _require(path.is_file(), f"{context}: referenced semantics audit is missing")
    _require(
        isinstance(value.get("sha256"), str)
        and len(value["sha256"]) == 64
        and _sha256_file(path) == value["sha256"],
        f"{context}: semantics audit checksum mismatch",
    )
    _require(
        isinstance(protocol_reference, dict) and isinstance(snapshot_reference, dict),
        f"{context}: missing protocol or snapshot dependency",
    )
    protocol_path = REPO_ROOT / Path(str(protocol_reference.get("path", "")))
    snapshot_path = REPO_ROOT / Path(str(snapshot_reference.get("path", "")))
    result = audit_semantics_manifest(
        path,
        protocol_path=protocol_path,
        snapshot_manifest_path=snapshot_path,
    )
    _require(
        result["classification"] == "sample_consistent_with_all_assigned_descriptors"
        and result["decision_checks"]["passed"] is True
        and result["readiness_contribution"] == 0,
        f"{context}: bounded semantics result drifted",
    )


def _audit_bioasq_pilot_reference(value: object, context: str) -> None:
    _require(isinstance(value, dict), f"{context}: missing BioASQ pilot protocol")
    _require(set(value) == {"path", "sha256"}, f"{context}: malformed pilot reference")
    relative = Path(str(value["path"]))
    _require(not relative.is_absolute() and ".." not in relative.parts, f"{context}: unsafe path")
    path = REPO_ROOT / relative
    _require(path.is_file(), f"{context}: referenced pilot protocol is missing")
    _require(
        isinstance(value.get("sha256"), str)
        and len(value["sha256"]) == 64
        and _sha256_file(path) == value["sha256"],
        f"{context}: BioASQ pilot checksum mismatch",
    )
    pilot = audit_bioasq_pilot(path)
    _require(
        pilot.status == "frozen_before_bioasq_pilot_metric"
        and pilot.total_cases == 21
        and pilot.readiness_contribution == 0,
        f"{context}: BioASQ pilot scope drifted",
    )


def _audit_bioasq_compatibility_reference(value: object, context: str) -> None:
    _require(isinstance(value, dict), f"{context}: missing compatibility audit")
    _require(set(value) == {"path", "sha256"}, f"{context}: malformed audit reference")
    relative = Path(str(value["path"]))
    _require(not relative.is_absolute() and ".." not in relative.parts, f"{context}: unsafe path")
    path = REPO_ROOT / relative
    _require(path.is_file(), f"{context}: referenced compatibility audit is missing")
    _require(
        isinstance(value.get("sha256"), str)
        and len(value["sha256"]) == 64
        and _sha256_file(path) == value["sha256"],
        f"{context}: compatibility audit checksum mismatch",
    )
    audit = audit_compatibility_manifest(path)
    _require(
        audit
        == {
            "status": "primary_source_compatible_but_sensitivity_20_unevaluable",
            "case_count": 21,
            "incompatible_case_ids": [],
            "readiness_contribution": 0,
        },
        f"{context}: compatibility decision drifted",
    )


def _audit_bioasq_pilot_v2_reference(value: object, context: str) -> None:
    _require(isinstance(value, dict), f"{context}: missing pilot v2 protocol")
    _require(set(value) == {"path", "sha256"}, f"{context}: malformed protocol reference")
    relative = Path(str(value["path"]))
    _require(not relative.is_absolute() and ".." not in relative.parts, f"{context}: unsafe path")
    path = REPO_ROOT / relative
    _require(path.is_file(), f"{context}: referenced pilot v2 protocol is missing")
    _require(
        isinstance(value.get("sha256"), str)
        and len(value["sha256"]) == 64
        and _sha256_file(path) == value["sha256"],
        f"{context}: pilot v2 checksum mismatch",
    )
    audit = audit_bioasq_pilot_v2(path)
    _require(
        audit.status == "frozen_after_source_compatibility_before_metric_formula"
        and audit.total_cases == 21
        and audit.sensitivity_supports == (5,)
        and audit.readiness_contribution == 0,
        f"{context}: pilot v2 scope drifted",
    )


def _audit_snapshot_reference(value: object, context: str) -> dict:
    _require(isinstance(value, dict), f"{context}: missing full snapshot audit")
    _require(set(value) == {"path", "sha256"}, f"{context}: malformed snapshot reference")
    relative = Path(str(value["path"]))
    _require(not relative.is_absolute() and ".." not in relative.parts, f"{context}: unsafe path")
    path = REPO_ROOT / relative
    _require(path.is_file(), f"{context}: referenced full snapshot audit is missing")
    _require(
        isinstance(value.get("sha256"), str)
        and len(value["sha256"]) == 64
        and _sha256_file(path) == value["sha256"],
        f"{context}: full snapshot audit checksum mismatch",
    )
    audit = json.loads(path.read_text(encoding="utf-8"))
    _require(audit.get("schema_version") == 1, f"{context}: unsupported snapshot schema")
    _require(
        audit.get("status") == "measured_unmatched_input",
        f"{context}: snapshot must retain its measured scope mismatch",
    )
    _require(audit.get("readiness_contribution") == 0, f"{context}: snapshot cannot add readiness")
    _require(
        audit.get("source_alternative_id") == "bioasq-2013-task-a",
        f"{context}: wrong source alternative",
    )
    source = audit.get("input")
    container = source.get("container") if isinstance(source, dict) else None
    _require(
        isinstance(source, dict)
        and isinstance(source.get("sha256"), str)
        and len(source["sha256"]) == 64
        and isinstance(source.get("bytes"), int)
        and source["bytes"] > 0
        and isinstance(container, dict)
        and container.get("envelope") == "bioasq_single_quote_assignment",
        f"{context}: snapshot input identity is incomplete",
    )
    measured = audit.get("measured")
    _require(isinstance(measured, dict), f"{context}: missing measured snapshot")
    year_counts = measured.get("publication_year_counts")
    _require(isinstance(year_counts, dict) and year_counts, f"{context}: missing year histogram")
    try:
        parsed_year_counts = {int(year): int(count) for year, count in year_counts.items()}
    except (TypeError, ValueError) as exc:
        raise SourceAlternativeContractError(f"{context}: malformed year histogram") from exc
    _require(
        all(count > 0 for count in parsed_year_counts.values()),
        f"{context}: year histogram counts must be positive",
    )
    _require(
        sum(parsed_year_counts.values()) + measured.get("unparseable_year_count", -1)
        == measured.get("article_count"),
        f"{context}: year histogram does not reconcile with article count",
    )
    _require(
        min(parsed_year_counts) == measured.get("publication_year_min")
        and max(parsed_year_counts) == measured.get("publication_year_max"),
        f"{context}: year histogram bounds do not reconcile",
    )
    _require(
        measured.get("noncanonical_year_count") == 751_238
        and measured.get("unparseable_year_count") == 0,
        f"{context}: measured year-shape counts drifted",
    )
    comparison = audit.get("declared_comparison")
    _require(
        isinstance(comparison, dict)
        and comparison.get("matches_published_aggregate_counts") is True
        and comparison.get("matches_published_publication_scope") is False
        and comparison.get("passes_declared_snapshot_gate") is False
        and comparison.get("articles_before_declared_publication_scope", 0) > 0
        and comparison.get("articles_after_snapshot_version") == 0,
        f"{context}: declared comparison no longer records the bounded scope mismatch",
    )
    _require(
        sum(count for year, count in parsed_year_counts.items() if year < 1950)
        == comparison["articles_before_declared_publication_scope"],
        f"{context}: pre-1950 count does not reconcile with year histogram",
    )
    _require(
        measured.get("unknown_mesh_labels") == []
        and measured.get("duplicate_mesh_assignment_count") == 0,
        f"{context}: unexpected label-integrity anomaly",
    )
    _require(
        measured.get("articles_without_mesh_labels") == 0,
        f"{context}: unexpected label-integrity anomaly",
    )
    _require_text_list(audit.get("limitations"), f"{context}.limitations")
    return audit


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
            f"{entry_id}: a source alternative cannot contribute readiness",
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

        if status in {"candidate_requires_acquisition_audit", "audited_scope_mismatch"}:
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
                if status == "audited_scope_mismatch":
                    _audit_successor_semantics_protocol_reference(
                        entry.get("successor_semantics_protocol"),
                        f"{entry_id}.successor_semantics_protocol",
                    )
                    snapshot = _audit_snapshot_reference(
                        entry.get("snapshot_audit"), f"{entry_id}.snapshot_audit"
                    )
                    _audit_semantics_manifest_reference(
                        entry.get("semantics_audit"),
                        f"{entry_id}.semantics_audit",
                        protocol_reference=entry.get("successor_semantics_protocol"),
                        snapshot_reference=entry.get("snapshot_audit"),
                    )
                    _audit_bioasq_pilot_reference(
                        entry.get("pilot_protocol"),
                        f"{entry_id}.pilot_protocol",
                    )
                    _audit_bioasq_compatibility_reference(
                        entry.get("pilot_compatibility_audit"),
                        f"{entry_id}.pilot_compatibility_audit",
                    )
                    _audit_bioasq_pilot_v2_reference(
                        entry.get("pilot_successor_protocol"),
                        f"{entry_id}.pilot_successor_protocol",
                    )
                    _require(
                        snapshot["measured"]["article_count"] == declared["article_count"]
                        and snapshot["measured"]["distinct_mesh_label_count"]
                        == declared["mesh_label_count"]
                        and round(snapshot["measured"]["average_mesh_labels_per_article"], 2)
                        == declared["average_mesh_labels_per_article"],
                        f"{entry_id}: measured aggregates do not reconcile with declaration",
                    )

    recommended_id = payload.get("recommended_alternative_id")
    _require(recommended_id in seen, "recommended alternative does not exist")
    recommended = next(entry for entry in alternatives if entry["id"] == recommended_id)
    _require(
        recommended["status"]
        in {"candidate_requires_acquisition_audit", "audited_scope_mismatch"},
        "recommended alternative must remain an actionable redesign route",
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
    print(f"recommended redesign route: {audit.recommended_id}")
    for status, count in audit.counts.items():
        print(f"{status}: {count}")
    print(f"readiness contribution: {audit.readiness_contribution}")


if __name__ == "__main__":
    main()
