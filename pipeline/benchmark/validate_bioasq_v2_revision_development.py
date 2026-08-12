"""Validate the terminal BioASQ v2 revision development measurement.

The validator proves provenance, exact direct-penalty arithmetic, rank-proof partitioning, the
frozen 11-case development population, and the mechanical pre-registered gate decision. The
committed result fails that gate and therefore terminates the pilot before held-out execution.

Run: ``python -m pipeline.benchmark.validate_bioasq_v2_revision_development``
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
from pathlib import Path

from pipeline.benchmark.bioasq_v2_development import (
    BOUND_GUARD_SCALED_UNITS,
    BOUND_SCALE_EXPONENT,
    DECIMAL_PRECISION,
    EXECUTOR_SOURCE_PATH as INITIAL_EXECUTOR_SOURCE_PATH,
    FORMULA_QUANTUM,
    NATIVE_SOURCE_PATH,
    SCORE_BOUNDS_SOURCE_PATH,
    SUPPORT_THRESHOLDS,
    load_development_cases,
)
from pipeline.benchmark.bioasq_v2_revision_development import (
    REVISION_EXECUTOR_SOURCE_PATH,
    _gate_decision,
    _revised_decimal,
    _summarize,
)
from pipeline.benchmark.validate_bioasq_formula_v2_revision import (
    REVISION_FORMULA_PATH,
    audit_bioasq_formula_v2_revision,
)
from pipeline.benchmark.validate_bioasq_v2_development import (
    COMPATIBILITY_PATH,
    DEVELOPMENT_PATH as INITIAL_DEVELOPMENT_PATH,
    PUBLISHED_GRAPH_MANIFEST_PATH,
    audit_bioasq_v2_development,
    audit_bioasq_v2_graph_manifest,
)
from pipeline.paths import REPO_ROOT


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


REVISION_FORMULA_SHA256 = _sha256_file(REVISION_FORMULA_PATH)
REVISION_DEVELOPMENT_PATH = (
    REPO_ROOT
    / "benchmarks"
    / "v3"
    / "manifests"
    / f"bioasq-v2-revision-1-development-{REVISION_FORMULA_SHA256[:12]}.json"
)


class BioasqV2RevisionDevelopmentError(ValueError):
    pass


@dataclass(frozen=True)
class BioasqV2RevisionDevelopmentAudit:
    status: str
    case_count: int
    heldout_case_count_computed: int
    primary_positive_top5: int
    primary_hard_top5: int
    primary_distant_below_median: int
    gate_passed: bool
    mechanical_action: str
    readiness_contribution: int


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BioasqV2RevisionDevelopmentError(message)


def _load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(payload, dict), f"{path}: expected a JSON object")
    return payload


def _file_identity(path: Path) -> dict[str, object]:
    return {
        "path": path.relative_to(REPO_ROOT).as_posix(),
        "sha256": _sha256_file(path),
        "bytes": path.stat().st_size,
    }


def _decimal(value: object, context: str) -> Decimal:
    _require(isinstance(value, str), f"{context}: Decimal must be encoded as text")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise BioasqV2RevisionDevelopmentError(f"{context}: invalid Decimal") from exc
    _require(parsed.is_finite(), f"{context}: Decimal must be finite")
    return parsed


def _audit_rank_proof(run: dict, context: str) -> None:
    proof = run.get("rank_proof")
    _require(isinstance(proof, dict), f"{context}: rank proof is missing")
    candidate_count = run["eligible_candidate_count"]
    rank = run["target_worst_tie_rank"]
    _require(
        proof.get("method")
        == "direct_penalized_exact_integer_rational_bounds_then_python_decimal_refinement"
        and proof.get("bound_scale_exponent") == BOUND_SCALE_EXPONENT
        and proof.get("decimal_guard_scaled_units") == BOUND_GUARD_SCALED_UNITS
        and proof.get("partition_candidate_count") == candidate_count,
        f"{context}: rank proof contract drifted",
    )
    bound_above = proof.get("bound_proven_at_or_above_count")
    bound_below = proof.get("bound_proven_below_count")
    exact_count = proof.get("exact_decimal_refinement_count")
    exact_above = proof.get("exact_decimal_at_or_above_count")
    _require(
        all(
            isinstance(value, int) and not isinstance(value, bool) and value >= 0
            for value in (bound_above, bound_below, exact_count, exact_above)
        )
        and exact_count >= 1
        and exact_above <= exact_count
        and bound_above + bound_below + exact_count == candidate_count
        and bound_above + exact_above == rank,
        f"{context}: rank proof does not establish the persisted rank",
    )
    zero_shortcut = proof.get("zero_target_nonnegative_shortcut")
    _require(isinstance(zero_shortcut, bool), f"{context}: zero shortcut flag drifted")
    if zero_shortcut:
        score = _decimal(run["target_persisted_revised_score"], f"{context} score")
        _require(
            score == 0
            and bound_above == candidate_count - 1
            and bound_below == 0
            and exact_count == 1
            and exact_above == 1,
            f"{context}: zero-target proof drifted",
        )


def _audit_run(
    run: object,
    *,
    case_id: str,
    initial_run: dict,
    source_case: dict,
) -> None:
    context = f"{case_id} revision support run"
    _require(isinstance(run, dict), f"{context}: expected an object")
    _require(
        set(run)
        == {
            "minimum_support_articles",
            "endpoint_a_article_support",
            "target_c_article_support",
            "direct_ac_article_count",
            "target_direct_penalty",
            "target_indirect_decimal_score",
            "target_revised_decimal_before_quantization",
            "target_persisted_revised_score",
            "eligible_candidate_count",
            "target_worst_tie_rank",
            "target_rank_fraction",
            "target_top_5_percent",
            "target_below_median",
            "target_bridge_count",
            "top_target_bridges",
            "rank_proof",
        },
        f"{context}: field set drifted",
    )
    threshold = run["minimum_support_articles"]
    _require(threshold in SUPPORT_THRESHOLDS, f"{context}: unsupported threshold")
    _require(
        run["endpoint_a_article_support"] == source_case["endpoint_a"]["article_support"]
        and run["target_c_article_support"] == source_case["target_c"]["article_support"]
        and run["direct_ac_article_count"] == source_case["direct_ac_article_count"]
        and run["target_direct_penalty"] == 1 + run["direct_ac_article_count"],
        f"{context}: source count or direct penalty drifted",
    )
    _require(
        run["eligible_candidate_count"] == initial_run["eligible_candidate_count"]
        and run["target_bridge_count"] == initial_run["target_bridge_count"]
        and run["top_target_bridges"] == initial_run["top_target_bridges"],
        f"{context}: inherited graph measurement drifted",
    )
    indirect = _decimal(run["target_indirect_decimal_score"], f"{context} indirect")
    revised = _decimal(
        run["target_revised_decimal_before_quantization"],
        f"{context} revised before quantization",
    )
    persisted = _decimal(
        run["target_persisted_revised_score"], f"{context} persisted revised"
    )
    _require(
        indirect >= 0
        and indirect.quantize(FORMULA_QUANTUM, rounding=ROUND_HALF_EVEN)
        == Decimal(initial_run["target_persisted_score"]),
        f"{context}: indirect score differs from the frozen initial measurement",
    )
    _require(
        revised == _revised_decimal(indirect, run["target_direct_penalty"])
        and persisted
        == revised.quantize(FORMULA_QUANTUM, rounding=ROUND_HALF_EVEN)
        and persisted.as_tuple().exponent == FORMULA_QUANTUM.as_tuple().exponent,
        f"{context}: revised Decimal arithmetic drifted",
    )
    candidate_count = run["eligible_candidate_count"]
    rank = run["target_worst_tie_rank"]
    _require(
        isinstance(rank, int) and not isinstance(rank, bool) and 1 <= rank <= candidate_count,
        f"{context}: rank is outside the candidate universe",
    )
    with localcontext() as decimal_context:
        decimal_context.prec = DECIMAL_PRECISION
        expected_fraction = Decimal(rank) / Decimal(candidate_count)
    _require(
        _decimal(run["target_rank_fraction"], f"{context} rank fraction")
        == expected_fraction
        and run["target_top_5_percent"] is (rank * 20 <= candidate_count)
        and run["target_below_median"] is (rank * 2 > candidate_count),
        f"{context}: rank fraction or classification drifted",
    )
    _audit_rank_proof(run, context)


def audit_bioasq_v2_revision_development(
    path: Path = REVISION_DEVELOPMENT_PATH,
) -> BioasqV2RevisionDevelopmentAudit:
    audit_bioasq_formula_v2_revision()
    audit_bioasq_v2_development()
    graph_manifest = audit_bioasq_v2_graph_manifest()
    output = _load_json(path)
    _require(output.get("schema_version") == 1, "unsupported revision development schema")
    _require(
        output.get("status") == "revision_development_gate_failed_terminate_before_heldout"
        and output.get("readiness_contribution") == 0,
        "revision development status or readiness drifted",
    )
    claim = output.get("claim_boundary")
    _require(
        isinstance(claim, str)
        and "Development-only measurement" in claim
        and "not held-out validation" in claim
        and "not" in claim
        and "gap detector" in claim,
        "revision development claim boundary is incomplete",
    )

    inputs = output.get("inputs")
    _require(isinstance(inputs, dict), "revision development inputs are missing")
    _require(
        inputs.get("revision_formula_contract") == _file_identity(REVISION_FORMULA_PATH)
        and inputs.get("initial_development_measurement")
        == _file_identity(INITIAL_DEVELOPMENT_PATH)
        and inputs.get("case_blind_graph_manifest")
        == _file_identity(PUBLISHED_GRAPH_MANIFEST_PATH)
        and inputs.get("revision_executor_source")
        == _file_identity(REVISION_EXECUTOR_SOURCE_PATH)
        and inputs.get("initial_graph_executor_source")
        == _file_identity(INITIAL_EXECUTOR_SOURCE_PATH)
        and inputs.get("native_pair_counter_source") == _file_identity(NATIVE_SOURCE_PATH)
        and inputs.get("native_rank_screener_source")
        == _file_identity(SCORE_BOUNDS_SOURCE_PATH),
        "revision development formula, code, or graph provenance drifted",
    )
    compatibility = _load_json(COMPATIBILITY_PATH)
    snapshot = compatibility["inputs"]["snapshot_transport"]
    mesh = compatibility["inputs"]["descriptor_vocabulary"]
    _require(
        inputs.get("source_snapshot")
        == {"sha256": snapshot["sha256"], "bytes": snapshot["bytes"]}
        and inputs.get("descriptor_vocabulary")
        == {"sha256": mesh["sha256"], "bytes": mesh["bytes"]},
        "revision development source identity drifted",
    )
    _require(
        output.get("execution_isolation")
        == {
            "split": "development",
            "case_count": 11,
            "heldout_case_count_computed": 0,
            "heldout_scores_ranks_orderings_or_bridges_materialized": False,
            "revision_number": 1,
            "revision_budget_consumed": 1,
            "revision_budget_remaining": 0,
        },
        "revision development/held-out isolation drifted",
    )
    _require(
        output.get("formula")
        == {
            "indirect_score": "sum(min(article_jaccard_ab, article_jaccard_bc))",
            "direct_penalty": "1 + direct_ac_article_count",
            "revised_score": "indirect_score / direct_penalty",
            "support_runs": [10, 5],
            "decimal_precision": 40,
            "persisted_score_quantum": "0.000000000000001",
            "tie_policy": "conservative worst tied rank",
        },
        "revision development formula declaration drifted",
    )
    expected_edges = {
        year: graph_manifest["edge_headers"][year]["edge_count"]
        for year in ("2011", "2012")
    }
    _require(
        output.get("graph")
        == {
            "node_count": mesh["descriptor_count"],
            "cutoff_years": [2011, 2012],
            "edge_counts": expected_edges,
        },
        "revision development graph declaration drifted",
    )

    cases = output.get("cases")
    expected_cases = load_development_cases()
    initial = _load_json(INITIAL_DEVELOPMENT_PATH)
    initial_cases = {case["id"]: case for case in initial["cases"]}
    source_cases = {case["id"]: case for case in compatibility["measurement"]["cases"]}
    _require(isinstance(cases, list) and len(cases) == 11, "revision case count drifted")
    _require(
        [case.get("id") for case in cases] == [case.id for case in expected_cases],
        "revision development case population or order drifted",
    )
    for case, expected_case in zip(cases, expected_cases, strict=True):
        _require(
            set(case)
            == {
                "id",
                "kind",
                "split",
                "label_scope",
                "cutoff",
                "endpoint_a",
                "target_c",
                "support_runs",
            }
            and case["kind"] == expected_case.kind
            and case["split"] == "development"
            and case["label_scope"] == expected_case.label_scope
            and case["cutoff"] == expected_case.cutoff
            and case["endpoint_a"] == expected_case.endpoint_a
            and case["target_c"] == expected_case.target_c,
            f"{expected_case.id}: frozen case identity, label, or split drifted",
        )
        runs = case["support_runs"]
        initial_runs = initial_cases[expected_case.id]["support_runs"]
        _require(
            isinstance(runs, list)
            and [run.get("minimum_support_articles") for run in runs] == [10, 5],
            f"{expected_case.id}: revision support run order drifted",
        )
        for run, initial_run in zip(runs, initial_runs, strict=True):
            _require(
                run["minimum_support_articles"]
                == initial_run["minimum_support_articles"],
                f"{expected_case.id}: support threshold differs from initial",
            )
            _audit_run(
                run,
                case_id=expected_case.id,
                initial_run=initial_run,
                source_case=source_cases[expected_case.id],
            )
        primary, sensitivity = runs
        _require(
            primary["target_indirect_decimal_score"]
            == sensitivity["target_indirect_decimal_score"]
            and primary["target_persisted_revised_score"]
            == sensitivity["target_persisted_revised_score"]
            and primary["target_bridge_count"] == sensitivity["target_bridge_count"],
            f"{expected_case.id}: support-5 target invariance drifted",
        )

    heldout_ids = {
        case["id"]
        for case in compatibility["measurement"]["cases"]
        if case["split"] == "heldout"
    }
    serialized = json.dumps(output, sort_keys=True)
    _require(
        not any(case_id in serialized for case_id in heldout_ids),
        "revision development artifact contains a held-out case identity",
    )
    expected_summary = _summarize(cases)
    _require(
        output.get("revision_development_summary") == expected_summary,
        "revision development summary drifted",
    )
    expected_decision = _gate_decision(expected_summary)
    decision = output.get("pre_registered_revision_development_decision")
    _require(decision == expected_decision, "revision development gate decision drifted")
    _require(
        decision
        == {
            "pre_registered_gate_passed": False,
            "support_checks": {
                threshold: {
                    "all_11_cases_evaluable": True,
                    "positive_top_5_percent_count": 1,
                    "positive_requirement_at_least": 2,
                    "positive_requirement_passed": False,
                    "hard_control_top_5_percent_count": 1,
                    "hard_control_requirement_allowed": 0,
                    "hard_control_requirement_passed": False,
                    "distant_control_below_median_count": 1,
                    "distant_control_requirement_required": 4,
                    "distant_control_requirement_passed": False,
                    "all_three_separation_requirements_passed": False,
                }
                for threshold in ("10", "5")
            },
            "sensitivity_agreement_required": True,
            "sensitivity_agreement_passed": True,
            "mechanical_action": "terminate_pilot_before_heldout",
            "readiness_contribution": 0,
        },
        "revision terminal gate outcome drifted",
    )
    runtime = output.get("runtime")
    _require(
        isinstance(runtime, dict)
        and isinstance(runtime.get("scoring_elapsed_seconds"), (int, float))
        and runtime["scoring_elapsed_seconds"] >= 0
        and isinstance(runtime.get("reused_case_blind_cache_bytes"), int)
        and runtime["reused_case_blind_cache_bytes"] > 0
        and isinstance(runtime.get("compiler_version"), str)
        and bool(runtime["compiler_version"])
        and runtime.get("command")
        == "python -m pipeline.benchmark.bioasq_v2_revision_development",
        "revision runtime provenance drifted",
    )
    limitations = output.get("limitations")
    limitations_text = " ".join(limitations).lower() if isinstance(limitations, list) else ""
    _require(
        len(limitations or []) >= 8
        and "not held-out validation" in limitations_text
        and "not independent formula selection" in limitations_text
        and "held-out identities and source counts were known" in limitations_text
        and "not causal novelty" in limitations_text
        and "not independently adjudicated" in limitations_text
        and "not verified absences" in limitations_text
        and "period-appropriate historical" in limitations_text
        and "llm interpretation" in limitations_text,
        "revision development limitations are incomplete",
    )
    primary = expected_summary["10"]
    return BioasqV2RevisionDevelopmentAudit(
        status=output["status"],
        case_count=len(cases),
        heldout_case_count_computed=output["execution_isolation"][
            "heldout_case_count_computed"
        ],
        primary_positive_top5=primary["source_labeled_positive"]["top_5_percent_count"],
        primary_hard_top5=primary["hard_negative"]["top_5_percent_count"],
        primary_distant_below_median=primary["distant_negative"]["below_median_count"],
        gate_passed=decision["pre_registered_gate_passed"],
        mechanical_action=decision["mechanical_action"],
        readiness_contribution=output["readiness_contribution"],
    )


def main() -> None:
    audit = audit_bioasq_v2_revision_development()
    print("BioASQ v2 revision development artifact: structurally valid")
    print(f"status: {audit.status}")
    print(f"development cases: {audit.case_count}")
    print(f"held-out cases computed: {audit.heldout_case_count_computed}")
    print(f"primary positives top 5%: {audit.primary_positive_top5}/3")
    print(f"primary hard controls top 5%: {audit.primary_hard_top5}/4")
    print(f"primary distant controls below median: {audit.primary_distant_below_median}/4")
    print(f"pre-registered gate passed: {str(audit.gate_passed).lower()}")
    print(f"mechanical action: {audit.mechanical_action}")
    print(f"readiness contribution: {audit.readiness_contribution}")


if __name__ == "__main__":
    main()
