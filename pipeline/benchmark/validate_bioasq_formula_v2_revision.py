"""Validate the single BioASQ v2 post-development formula revision contract.

This contract consumes the one allowed revision after the initial development failure. It freezes
the direct A-C penalty and a mechanical development gate before any revision score exists. Passing
this validator does not authorize held-out execution by itself and adds no metric-v3 readiness.

Run: ``python -m pipeline.benchmark.validate_bioasq_formula_v2_revision``
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from pipeline.benchmark.validate_bioasq_formula_v2 import (
    FORMULA_PATH as INITIAL_FORMULA_PATH,
    audit_bioasq_formula_v2,
)
from pipeline.benchmark.validate_bioasq_pilot_v2 import (
    SUCCESSOR_PATH,
    audit_bioasq_pilot_v2,
)
from pipeline.benchmark.validate_bioasq_v2_development import (
    DEVELOPMENT_PATH as INITIAL_DEVELOPMENT_PATH,
    PUBLISHED_GRAPH_MANIFEST_PATH,
    audit_bioasq_v2_development,
    audit_bioasq_v2_graph_manifest,
)
from pipeline.paths import REPO_ROOT

REVISION_FORMULA_PATH = (
    REPO_ROOT / "benchmarks" / "v3" / "bioasq-formula-v2-revision-1.json"
)


class BioasqFormulaV2RevisionError(ValueError):
    pass


@dataclass(frozen=True)
class BioasqFormulaV2RevisionAudit:
    status: str
    formula_class: str
    revision_number: int
    budget_remaining: int
    direct_penalty: str
    development_positive_required: int
    development_hard_top5_allowed: int
    development_distant_below_median_required: int
    heldout_output_seen: bool
    readiness_contribution: int


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BioasqFormulaV2RevisionError(message)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(payload, dict), f"{path}: expected a JSON object")
    return payload


def _resolve_reference(value: object, expected: Path, context: str) -> dict:
    _require(isinstance(value, dict), f"{context}: missing reference")
    _require(set(value) == {"path", "sha256"}, f"{context}: malformed reference")
    relative = Path(str(value["path"]))
    _require(not relative.is_absolute() and ".." not in relative.parts, f"{context}: unsafe path")
    path = REPO_ROOT / relative
    _require(path.resolve() == expected.resolve(), f"{context}: unexpected path")
    _require(path.is_file(), f"{context}: referenced file is missing")
    _require(
        isinstance(value.get("sha256"), str)
        and len(value["sha256"]) == 64
        and _sha256_file(path) == value["sha256"],
        f"{context}: checksum mismatch",
    )
    return _load_json(path)


def _development_observation(initial_development: dict) -> dict:
    summary = initial_development["development_summary"]
    return {
        "scope": "descriptive development measurement under the checksum-pinned initial formula",
        "case_count": 11,
        "heldout_case_count_computed": 0,
        "at_support_10": {
            "source_labeled_positive_top_5_percent": (
                f'{summary["10"]["source_labeled_positive"]["top_5_percent_count"]} of 3'
            ),
            "ontology_generated_hard_control_top_5_percent": (
                f'{summary["10"]["hard_negative"]["top_5_percent_count"]} of 4'
            ),
            "ontology_generated_distant_control_below_median": (
                f'{summary["10"]["distant_negative"]["below_median_count"]} of 4'
            ),
        },
        "at_support_5": {
            "source_labeled_positive_top_5_percent": (
                f'{summary["5"]["source_labeled_positive"]["top_5_percent_count"]} of 3'
            ),
            "ontology_generated_hard_control_top_5_percent": (
                f'{summary["5"]["hard_negative"]["top_5_percent_count"]} of 4'
            ),
            "ontology_generated_distant_control_below_median": (
                f'{summary["5"]["distant_negative"]["below_median_count"]} of 4'
            ),
        },
        "support_sensitivity_observation": (
            "All 11 target scores and target bridge counts are identical between support 10 and "
            "support 5; candidate-universe denominators differ."
        ),
        "interpretation": (
            "The initial development pattern is consistent with a generic association score that "
            "rewards structurally close controls; it does not establish the cause of failure and "
            "is not held-out validation."
        ),
    }


def audit_bioasq_formula_v2_revision(
    path: Path = REVISION_FORMULA_PATH,
) -> BioasqFormulaV2RevisionAudit:
    revision = _load_json(path)
    _require(revision.get("schema_version") == 1, "unsupported revision formula schema")
    _require(
        revision.get("id")
        == "bioasq-v2-revision-1-direct-penalized-jaccard-sum-min"
        and revision.get("status")
        == "frozen_single_revision_after_initial_development_before_revision_output",
        "single revision is not frozen before revision output",
    )
    try:
        frozen_on = date.fromisoformat(str(revision.get("frozen_on")))
    except ValueError as exc:
        raise BioasqFormulaV2RevisionError("revision frozen_on must be YYYY-MM-DD") from exc
    _require(frozen_on.isoformat() == "2026-08-12", "revision freeze date drifted")

    boundary = revision.get("claim_boundary")
    _require(isinstance(boundary, dict), "revision claim boundary is missing")
    excluded_claims = boundary.get("not_a_claim_of")
    _require(
        boundary.get("formula_class")
        == "article_level_mesh_direct_penalized_jaccard_sum_of_path_minima"
        and boundary.get("readiness_contribution") == 0
        and isinstance(excluded_claims, list)
        and {
            "a validated gap detector",
            "an exact LION replication",
            "independent formula selection",
            "held-out validation",
            "period-appropriate historical indexing",
            "generalization beyond the BioASQ secondary snapshot",
        }
        == set(excluded_claims),
        "revision claim boundary drifted",
    )

    inputs = revision.get("inputs")
    _require(isinstance(inputs, dict), "revision inputs are missing")
    _require(
        set(inputs)
        == {
            "successor_protocol",
            "initial_formula_contract",
            "initial_development_measurement",
            "case_blind_graph_manifest",
        },
        "revision input set drifted",
    )
    successor = _resolve_reference(
        inputs["successor_protocol"], SUCCESSOR_PATH, "successor protocol"
    )
    initial_formula = _resolve_reference(
        inputs["initial_formula_contract"], INITIAL_FORMULA_PATH, "initial formula"
    )
    initial_development = _resolve_reference(
        inputs["initial_development_measurement"],
        INITIAL_DEVELOPMENT_PATH,
        "initial development measurement",
    )
    _resolve_reference(
        inputs["case_blind_graph_manifest"],
        PUBLISHED_GRAPH_MANIFEST_PATH,
        "case-blind graph manifest",
    )
    successor_audit = audit_bioasq_pilot_v2()
    initial_audit = audit_bioasq_formula_v2()
    development_audit = audit_bioasq_v2_development()
    graph_manifest = audit_bioasq_v2_graph_manifest()
    _require(
        successor_audit.total_cases == 21
        and successor_audit.primary_support == 10
        and successor_audit.sensitivity_supports == (5,)
        and initial_audit.revision_budget == 1
        and development_audit.case_count == 11
        and development_audit.heldout_case_count_computed == 0
        and graph_manifest["case_identities_or_labels_stored"] is False,
        "revision input audit boundary drifted",
    )

    accounting = revision.get("revision_accounting")
    _require(isinstance(accounting, dict), "revision accounting is missing")
    _require(
        accounting.get("initial_budget") == 1
        and accounting.get("revision_number") == 1
        and accounting.get("budget_consumed") == 1
        and accounting.get("budget_remaining") == 0
        and accounting.get("no_further_formula_revision_permitted") is True
        and accounting.get("changed_components")
        == ["candidate score adds the frozen direct A-C denominator 1 + n_AC"]
        and set(accounting.get("unchanged_components", []))
        == {
            "source snapshot and publication cutoffs",
            "MeSH descriptor identities",
            "support runs 10 and 5",
            "eligible node, edge, bridge, and candidate sets",
            "article Jaccard edge weights",
            "minimum A-B-C path aggregation",
            "sum accumulation across B",
            "Decimal precision, ordering, quantization, and tie policy",
            "all 21 case identities, kinds, cutoffs, and splits",
        },
        "revision budget or component accounting drifted",
    )

    timing = revision.get("freeze_timing")
    _require(isinstance(timing, dict), "revision freeze timing is missing")
    for field in (
        "source_compatibility_counts_seen",
        "case_identities_splits_and_labels_seen",
        "initial_formula_development_scores_ranks_and_bridges_seen",
    ):
        _require(timing.get(field) is True, f"revision must disclose {field}")
    for field in (
        "revision_formula_development_scores_ranks_or_bridges_seen",
        "bioasq_heldout_scores_ranks_orderings_or_bridges_seen",
    ):
        _require(timing.get(field) is False, f"revision was not frozen before {field}")
    _require(
        "only revision" in str(timing.get("disclosure"))
        and "No revision-formula development output" in str(timing.get("disclosure"))
        and "no BioASQ held-out metric output" in str(timing.get("disclosure")),
        "revision freeze disclosure is incomplete",
    )

    expected_observation = _development_observation(initial_development)
    _require(
        revision.get("observed_initial_development_failure") == expected_observation,
        "revision initial-development observation drifted",
    )
    _require(
        initial_formula["status"] == "frozen_initial_before_development_metric_output"
        and successor["status"] == "frozen_after_source_compatibility_before_metric_formula",
        "revision predecessor status drifted",
    )

    rationale = revision.get("revision_rationale")
    _require(isinstance(rationale, dict), "revision rationale is missing")
    _require(
        set(rationale)
        == {
            "construct",
            "single_change",
            "denominator_choice",
            "source_timing",
            "anti_tuning_boundary",
            "relation_to_lion",
        }
        and "indirect A-B-C evidence" in rationale["construct"]
        and rationale["single_change"]
        == "Divide the unchanged indirect score by one plus the exact direct A-C article count."
        and "additive-one smoothing" in rationale["denominator_choice"]
        and "no fitted parameter" in rationale["denominator_choice"]
        and "before the initial formula freeze" in rationale["source_timing"]
        and "may not be tuned" in rationale["anti_tuning_boundary"]
        and "does not claim to reproduce" in rationale["relation_to_lion"],
        "revision rationale or anti-tuning boundary drifted",
    )

    graph = revision.get("graph_contract")
    _require(isinstance(graph, dict), "revision graph contract is missing")
    _require(
        graph.get("inherit_exactly_from_initial_formula") is True
        and graph.get("node_identity") == initial_formula["graph_contract"]["node_identity"]
        and graph.get("document_unit") == initial_formula["graph_contract"]["document_unit"]
        and graph.get("threshold_runs") == initial_formula["graph_contract"]["threshold_runs"]
        and graph.get("candidate_set") == initial_formula["graph_contract"]["candidate_set"]
        and graph.get("bridge_set") == initial_formula["graph_contract"]["bridge_set"]
        and graph.get("direct_ac_count")
        == (
            "n_AC is the exact number of included articles containing both A and C at the case "
            "cutoff; zero when the edge is absent."
        )
        and graph.get("direct_article_policy")
        == (
            "Retain every A-C article in all support, edge, and bridge counts; use n_AC only "
            "through the frozen denominator."
        ),
        "revision graph contract drifted",
    )

    score = revision.get("score_contract")
    _require(isinstance(score, dict), "revision score contract is missing")
    _require(
        score
        == {
            "edge_weight": "J(x,y) = n_xy / (n_x + n_y - n_xy)",
            "path_score": "P(A,B,C) = min(J(A,B), J(B,C))",
            "indirect_score": "I(A,C) = sum(P(A,B,C) for B in bridge_set(A,C))",
            "direct_penalty": "D(A,C) = 1 + n_AC",
            "revised_candidate_score": "R(A,C) = I(A,C) / D(A,C)",
            "empty_bridge_score": "0",
            "monotonicity": (
                "At fixed indirect score, R is non-increasing in integer n_AC and equals I when "
                "n_AC is zero."
            ),
            "candidate_direct_count_scope": (
                "Compute n_AC independently for every eligible candidate in the same cutoff "
                "graph; the named target receives no special handling."
            ),
        },
        "revision direct-penalized score drifted",
    )

    numeric = revision.get("numeric_reproducibility")
    _require(isinstance(numeric, dict), "revision numeric contract is missing")
    _require(
        numeric.get("decimal_context_precision") == 40
        and numeric.get("decimal_rounding") == "ROUND_HALF_EVEN"
        and numeric.get("bridge_order") == "descriptor_ui ascending"
        and numeric.get("direct_penalty_evaluation")
        == (
            "After the full indirect sum, construct Decimal(1 + n_AC) from the exact integer and "
            "perform one division under the frozen context."
        )
        and numeric.get("persisted_score_quantum") == "0.000000000000001"
        and numeric.get("persisted_score_rounding")
        == "quantize once after the direct-penalty division using ROUND_HALF_EVEN"
        and numeric.get("comparison_value") == "the persisted quantized revised score"
        and "may not be persisted as scores" in str(numeric.get("arithmetic")),
        "revision numeric contract drifted",
    )

    ranking = revision.get("ranking_contract")
    _require(isinstance(ranking, dict), "revision ranking contract is missing")
    initial_ranking = initial_formula["ranking_contract"]
    _require(
        all(
            ranking.get(field) == initial_ranking[field]
            for field in (
                "primary_orientation",
                "tie_policy",
                "rank_fraction",
                "eligible_candidate_count",
                "top_5_percent",
                "reciprocal_orientation",
            )
        )
        and ranking.get("candidate_order")
        == "persisted revised score descending, descriptor_ui ascending for display only"
        and ranking.get("one_based_rank")
        == (
            "count(candidate_persisted_revised_score >= target_persisted_revised_score)"
        ),
        "revision ranking contract drifted",
    )

    exclusions = revision.get("feature_exclusions")
    _require(
        isinstance(exclusions, list)
        and set(exclusions)
        == {
            "case kind or label",
            "development or heldout split",
            "source discovery year",
            "named target identity as a feature",
            "named positive bridge identity as a feature",
            "MeSH tree distance, parent, child, or sibling relationship",
            "case-specific threshold, penalty, exponent, or candidate override",
            "any OpenAlex topic metric output",
            "any LLM-generated or embedding feature",
        },
        "revision feature exclusions drifted",
    )

    isolation = revision.get("execution_isolation")
    _require(isinstance(isolation, dict), "revision execution isolation is missing")
    _require(
        isolation.get("allowed_revision_run") == "development cases only, at support 10 and 5"
        and str(isolation.get("heldout_prohibition", "")).startswith(
            "Do not compute, cache, log, persist, or preview any held-out"
        )
        and "case-blind graph" in str(isolation.get("shared_graph_rule"))
        and "checksum-addressed" in str(isolation.get("output_path_rule"))
        and "terminates this pilot" in str(isolation.get("no_further_revision")),
        "revision execution isolation drifted",
    )

    gate = revision.get("pre_registered_revision_development_gate")
    _require(isinstance(gate, dict), "revision development gate is missing")
    _require(
        gate.get("evaluability_requirement")
        == (
            "All 11 development cases must be evaluable at support 10 and 5; denominator "
            "shrinkage is forbidden."
        )
        and gate.get("positive_requirement")
        == "At least 2 of 3 development source-labelled positives rank in the top 5 percent."
        and gate.get("hard_control_requirement")
        == "Zero of 4 development ontology-sibling hard controls ranks in the top 5 percent."
        and gate.get("distant_control_requirement")
        == (
            "All 4 development cross-branch distant controls rank below the median, meaning "
            "rank_fraction > 0.5."
        )
        and gate.get("sensitivity_requirement")
        == (
            "All three requirements must hold at both support 10 and support 5; an unevaluable "
            "case or disagreement is not a pass."
        )
        and "Freeze this exact revision as final" in str(gate.get("pass_action"))
        and "Terminate" in str(gate.get("fail_action"))
        and "Do not choose the initial formula" in str(gate.get("no_discretion_rule")),
        "revision development decision gate drifted",
    )

    reporting = revision.get("development_reporting")
    limitations = revision.get("limitations")
    _require(
        isinstance(reporting, list)
        and len(reporting) >= 5
        and isinstance(limitations, list)
        and len(limitations) >= 10
        and any(
            "held-out identities and source counts were known" in limitation.lower()
            for limitation in limitations
        ),
        "revision reporting or limitations are incomplete",
    )
    heldout_ids = {
        case["id"]
        for case in _load_json(
            REPO_ROOT / "benchmarks" / "v3" / "manifests" / "bioasq-pilot-compatibility.json"
        )["measurement"]["cases"]
        if case["split"] == "heldout"
    }
    serialized = json.dumps(revision, ensure_ascii=False)
    _require(
        not any(case_id in serialized for case_id in heldout_ids),
        "revision contract contains a held-out case identity",
    )
    serialized_lower = serialized.lower()
    _require(
        "non-academic" in serialized_lower
        and "period-appropriate historical indexing" in serialized_lower
        and "llm interpretation" in serialized_lower,
        "revision must retain source, knowledge, and LLM limitations",
    )

    return BioasqFormulaV2RevisionAudit(
        status=revision["status"],
        formula_class=boundary["formula_class"],
        revision_number=accounting["revision_number"],
        budget_remaining=accounting["budget_remaining"],
        direct_penalty=score["direct_penalty"],
        development_positive_required=2,
        development_hard_top5_allowed=0,
        development_distant_below_median_required=4,
        heldout_output_seen=timing["bioasq_heldout_scores_ranks_orderings_or_bridges_seen"],
        readiness_contribution=boundary["readiness_contribution"],
    )


def main() -> None:
    audit = audit_bioasq_formula_v2_revision()
    print("BioASQ v2 revision-1 formula contract: structurally valid")
    print(f"status: {audit.status}")
    print(f"formula class: {audit.formula_class}")
    print(f"revision: {audit.revision_number}; budget remaining: {audit.budget_remaining}")
    print(f"direct penalty: {audit.direct_penalty}")
    print(
        "development gate: "
        f"positive >= {audit.development_positive_required}/3; "
        f"hard top-5% <= {audit.development_hard_top5_allowed}/4; "
        f"distant below median = {audit.development_distant_below_median_required}/4"
    )
    print(f"held-out output seen: {str(audit.heldout_output_seen).lower()}")
    print(f"readiness contribution: {audit.readiness_contribution}")


if __name__ == "__main__":
    main()
