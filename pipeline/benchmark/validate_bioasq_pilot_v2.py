"""Validate the source-informed BioASQ pilot successor before any metric output.

The successor preserves the terminal predecessor and all 21 cases. It records the source coverage
already seen, removes the infeasible support-20 sensitivity only in a new experiment, and remains
at zero metric-v3 readiness.

Run: ``python -m pipeline.benchmark.validate_bioasq_pilot_v2``
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from pipeline.benchmark.bioasq_pilot_compatibility import (
    SENSITIVITY_BLOCKED_STATUS,
    audit_compatibility_manifest,
)
from pipeline.benchmark.metric_blind import find_forbidden_fields
from pipeline.benchmark.validate_bioasq_pilot import audit_bioasq_pilot
from pipeline.paths import REPO_ROOT

SUCCESSOR_PATH = REPO_ROOT / "benchmarks" / "v3" / "bioasq-pilot-v2.json"
EXPECTED_BLOCKER_ID = "generated-hard-2012-04-d019956-d019960"


class BioasqPilotV2ContractError(ValueError):
    pass


@dataclass(frozen=True)
class BioasqPilotV2Audit:
    status: str
    total_cases: int
    development_cases: int
    heldout_cases: int
    primary_support: int
    sensitivity_supports: tuple[int, ...]
    predecessor_blocker_ids: tuple[str, ...]
    readiness_contribution: int


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BioasqPilotV2ContractError(message)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_reference(value: object, context: str) -> Path:
    _require(isinstance(value, dict), f"{context}: missing file reference")
    _require(set(value) == {"path", "sha256"}, f"{context}: malformed file reference")
    relative = Path(str(value["path"]))
    _require(not relative.is_absolute() and ".." not in relative.parts, f"{context}: unsafe path")
    path = REPO_ROOT / relative
    _require(path.is_file(), f"{context}: referenced file is missing")
    _require(
        isinstance(value.get("sha256"), str)
        and len(value["sha256"]) == 64
        and _sha256_file(path) == value["sha256"],
        f"{context}: checksum mismatch",
    )
    return path


def _load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(payload, dict), f"{path}: expected a JSON object")
    return payload


def _assert_source_measurement_boundary(compatibility: dict) -> None:
    decision = compatibility.get("decision")
    measurement = compatibility.get("measurement")
    _require(
        isinstance(decision, dict) and isinstance(measurement, dict),
        "source audit is incomplete",
    )
    _require(
        compatibility.get("status") == SENSITIVITY_BLOCKED_STATUS
        and decision.get("all_21_cases_primary_source_compatible") is True
        and decision.get("metric_work_authorized_by_this_audit") is False
        and decision.get("frozen_heldout_rule_can_still_pass") is False
        and decision.get("heldout_sensitivity_evaluable")
        == {"5": True, "10": True, "20": False}
        and decision.get("heldout_sensitivity_blockers")
        == {"5": [], "10": [], "20": [EXPECTED_BLOCKER_ID]},
        "successor is not based on the pinned predecessor blocker",
    )
    cases = measurement.get("cases")
    _require(isinstance(cases, list) and len(cases) == 21, "source audit must contain 21 cases")
    heldout = [case for case in cases if case.get("split") == "heldout"]
    _require(len(heldout) == 10, "source audit must retain 10 held-out cases")
    for case in heldout:
        eligibility = case.get("support_eligibility")
        _require(isinstance(eligibility, dict), f"{case.get('id')}: eligibility is missing")
        for threshold in ("5", "10"):
            _require(
                eligibility.get(threshold)
                == {"endpoint_a_eligible": True, "target_c_eligible": True},
                f"{case.get('id')}: held-out case is not evaluable at support {threshold}",
            )


def audit_bioasq_pilot_v2(path: Path = SUCCESSOR_PATH) -> BioasqPilotV2Audit:
    successor = _load_json(path)
    _require(successor.get("schema_version") == 1, "unsupported BioASQ pilot v2 schema")
    _require(
        successor.get("id") == "bioasq-secondary-pilot-v2-source-informed"
        and successor.get("status") == "frozen_after_source_compatibility_before_metric_formula",
        "BioASQ pilot v2 is not frozen at the source-informed pre-metric boundary",
    )
    try:
        frozen_on = date.fromisoformat(str(successor.get("frozen_on")))
    except ValueError as exc:
        raise BioasqPilotV2ContractError("pilot v2 frozen_on must be YYYY-MM-DD") from exc
    _require(frozen_on.isoformat() == "2026-08-12", "pilot v2 freeze date drifted")
    _require(
        successor.get("source_alternative_id") == "bioasq-2013-task-a",
        "pilot v2 references the wrong source alternative",
    )
    _require(not find_forbidden_fields(successor), "pilot v2 contains metric output fields")

    boundary = successor.get("claim_boundary")
    _require(isinstance(boundary, dict), "pilot v2 is missing its claim boundary")
    exclusions = boundary.get("not_a_claim_of")
    _require(
        boundary.get("experiment_class")
        == "source_informed_secondary_snapshot_reproduction_and_control_separation_pilot"
        and boundary.get("readiness_contribution") == 0
        and isinstance(exclusions, list)
        and {
            "period-appropriate historical indexing",
            "validated discovery ground truth",
            "independent identity-blinded holdout",
            "population-wide gap detection",
            "original metric-v3 source readiness",
            "generalization beyond biomedicine",
        }
        <= set(exclusions),
        "pilot v2 claim boundary drifted",
    )

    predecessor = successor.get("predecessor")
    _require(isinstance(predecessor, dict), "pilot v2 is missing predecessor identities")
    predecessor_path = _resolve_reference(predecessor.get("protocol"), "predecessor protocol")
    compatibility_path = _resolve_reference(
        predecessor.get("source_compatibility_audit"), "predecessor compatibility audit"
    )
    predecessor_audit = audit_bioasq_pilot(predecessor_path)
    compatibility_audit = audit_compatibility_manifest(compatibility_path)
    _require(
        predecessor_audit.total_cases == 21
        and predecessor_audit.readiness_contribution == 0
        and compatibility_audit["status"] == SENSITIVITY_BLOCKED_STATUS
        and predecessor.get("terminal_status") == SENSITIVITY_BLOCKED_STATUS
        and "immutable" in str(predecessor.get("preservation_rule")),
        "pilot v2 does not preserve the terminal predecessor",
    )
    predecessor_payload = _load_json(predecessor_path)
    compatibility_payload = _load_json(compatibility_path)
    _assert_source_measurement_boundary(compatibility_payload)

    timing = successor.get("freeze_timing")
    _require(isinstance(timing, dict), "pilot v2 is missing freeze timing")
    for field in (
        "case_identities_and_splits_seen",
        "case_endpoint_support_counts_seen",
        "case_direct_ac_cooccurrence_counts_seen",
        "positive_named_bridge_support_and_cooccurrence_counts_seen",
        "candidate_universe_sizes_at_support_5_10_20_seen",
        "predecessor_sensitivity_blocker_seen",
        "legacy_failed_openalex_metric_outputs_seen",
    ):
        _require(timing.get(field) is True, f"pilot v2 must disclose {field}")
    for field in (
        "bioasq_pilot_metric_formula_seen",
        "bioasq_pilot_development_scores_or_ranks_seen",
        "bioasq_pilot_heldout_scores_or_ranks_seen",
    ):
        _require(timing.get(field) is False, f"pilot v2 was not frozen before {field}")
    _require(
        "source-informed successor" in str(timing.get("disclosure"))
        and "no BioASQ metric formula" in str(timing.get("disclosure")),
        "pilot v2 freeze disclosure is incomplete",
    )

    change = successor.get("successor_change")
    _require(isinstance(change, dict), "pilot v2 is missing its changed-rule disclosure")
    _require(
        "support exactly 10" in str(change.get("reason"))
        and change.get("changed_rule")
        == (
            "Remove support 20 from the successor decision and retain primary support 10 plus "
            "lower-support sensitivity 5."
        )
        and "weakens independence" in str(change.get("source_informed_status"))
        and isinstance(change.get("unchanged_rules"), list)
        and len(change["unchanged_rules"]) == 8,
        "pilot v2 source-informed change drifted",
    )

    population = successor.get("case_population")
    predecessor_population = predecessor_payload["case_population"]
    _require(isinstance(population, dict), "pilot v2 is missing case population policy")
    _require(
        population.get("inherit_exactly_from_predecessor") is True
        and population.get("total_cases") == predecessor_population["total_cases"] == 21
        and population.get("split_counts") == predecessor_population["split_counts"]
        == {"development": 11, "heldout": 10}
        and "Do not drop" in str(population.get("replacement_policy"))
        and "score-unseen" in str(population.get("heldout_disclosure"))
        and "not identity-" in str(population.get("heldout_disclosure")),
        "pilot v2 case population or held-out disclosure drifted",
    )

    compatibility = successor.get("source_compatibility")
    _require(isinstance(compatibility, dict), "pilot v2 is missing source compatibility")
    _require(
        compatibility.get("primary_minimum_support_articles") == 10
        and compatibility.get("support_sensitivity_articles") == [5]
        and compatibility.get("all_21_cases_primary_eligible") is True
        and compatibility.get("all_10_heldout_cases_eligible_at_5_and_10") is True
        and compatibility.get("predecessor_support_20_blocker_ids") == [EXPECTED_BLOCKER_ID]
        and "only for this successor" in str(compatibility.get("metric_work_boundary")),
        "pilot v2 support boundary drifted",
    )

    transform = successor.get("source_transform")
    predecessor_transform = predecessor_payload["source_transform"]
    _require(isinstance(transform, dict), "pilot v2 is missing source transform")
    _require(
        transform.get("inherit_non_threshold_fields_from_predecessor") is True
        and all(
            transform.get(field) == predecessor_transform[field]
            for field in (
                "publication_cutoff",
                "descriptor_identity",
                "article_contribution",
                "cooccurrence_unit",
                "direct_endpoint_cooccurrences",
                "ontology_relatives_policy",
            )
        ),
        "pilot v2 source transform drifted",
    )

    isolation = successor.get("metric_isolation")
    _require(isinstance(isolation, dict), "pilot v2 is missing metric isolation")
    _require(
        isolation.get("formula_contract_required_before_scores") is True
        and isolation.get("formula_contract_must_be_separately_checksum_pinned") is True
        and isolation.get("candidate_formula_revision_limit") == 1
        and "held-out metric scores" in str(isolation.get("heldout_policy"))
        and "case-specific support eligibility overrides"
        in isolation.get("metric_inputs_may_not_include", [])
        and "any LLM-generated feature" in isolation.get("metric_inputs_may_not_include", []),
        "pilot v2 metric isolation drifted",
    )

    _require(
        successor.get("ranking_contract") == predecessor_payload["ranking_contract"],
        "pilot v2 ranking contract differs from its predecessor",
    )
    decision = successor.get("heldout_decision_rule")
    predecessor_decision = predecessor_payload["heldout_decision_rule"]
    _require(isinstance(decision, dict), "pilot v2 is missing held-out decision rule")
    _require(
        all(
            decision.get(field) == predecessor_decision[field]
            for field in (
                "positive_requirement",
                "hard_control_requirement",
                "distant_control_requirement",
            )
        )
        and decision.get("evaluability_requirement")
        == (
            "All 10 frozen held-out cases must be evaluable at support 10 and sensitivity 5; "
            "denominator shrinkage is forbidden."
        )
        and decision.get("sensitivity_requirement")
        == (
            "The three held-out requirements must hold at both primary support 10 and "
            "lower-support sensitivity 5; an unevaluable case or disagreement is not a pass."
        )
        and decision.get("passing_label")
        == "source_informed_pilot_signal_consistent_with_frozen_separation_rule"
        and decision.get("failing_label") == "source_informed_pilot_signal_not_reproduced"
        and decision.get("inconclusive_label") == "source_informed_pilot_inconclusive"
        and decision.get("readiness_contribution") == 0,
        "pilot v2 held-out decision rule drifted",
    )

    reporting = successor.get("reporting_requirements")
    limitations = successor.get("limitations")
    _require(
        isinstance(reporting, list)
        and len(reporting) >= 5
        and "never erase" in reporting[0]
        and isinstance(limitations, list)
        and len(limitations) >= 8,
        "pilot v2 reporting or limitations are incomplete",
    )
    serialized = json.dumps(successor, ensure_ascii=False).lower()
    _require("source-informed" in serialized, "pilot v2 must label its source-informed design")
    _require("non-academic" in serialized, "pilot v2 must retain non-academic blind spots")
    _require("llm interpretation" in serialized, "pilot v2 must keep the LLM layer gated")

    return BioasqPilotV2Audit(
        status=successor["status"],
        total_cases=population["total_cases"],
        development_cases=population["split_counts"]["development"],
        heldout_cases=population["split_counts"]["heldout"],
        primary_support=compatibility["primary_minimum_support_articles"],
        sensitivity_supports=tuple(compatibility["support_sensitivity_articles"]),
        predecessor_blocker_ids=tuple(compatibility["predecessor_support_20_blocker_ids"]),
        readiness_contribution=boundary["readiness_contribution"],
    )


def main() -> None:
    audit = audit_bioasq_pilot_v2()
    print("BioASQ source-informed pilot v2: structurally valid")
    print(f"status: {audit.status}")
    print(
        f"cases: total={audit.total_cases}, development={audit.development_cases}, "
        f"heldout={audit.heldout_cases}"
    )
    print(f"primary support: {audit.primary_support}")
    print(f"sensitivity supports: {', '.join(map(str, audit.sensitivity_supports))}")
    print(f"preserved predecessor blockers: {len(audit.predecessor_blocker_ids)}")
    print(f"readiness contribution: {audit.readiness_contribution}")


if __name__ == "__main__":
    main()
