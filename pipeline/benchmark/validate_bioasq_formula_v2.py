"""Validate the initial BioASQ v2 formula contract before development output.

This validates a frozen algorithm definition, not a metric result. It must pass before any
development score is computed and never authorizes held-out execution.

Run: ``python -m pipeline.benchmark.validate_bioasq_formula_v2``
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from pipeline.benchmark.metric_blind import find_forbidden_fields
from pipeline.benchmark.validate_bioasq_pilot_v2 import audit_bioasq_pilot_v2
from pipeline.paths import REPO_ROOT

FORMULA_PATH = REPO_ROOT / "benchmarks" / "v3" / "bioasq-formula-v2-initial.json"


class BioasqFormulaV2ContractError(ValueError):
    pass


@dataclass(frozen=True)
class BioasqFormulaV2Audit:
    status: str
    formula_class: str
    edge_weight: str
    path_aggregation: str
    candidate_accumulation: str
    threshold_supports: tuple[int, ...]
    decimal_precision: int
    revision_budget: int
    readiness_contribution: int


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BioasqFormulaV2ContractError(message)


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


def audit_bioasq_formula_v2(path: Path = FORMULA_PATH) -> BioasqFormulaV2Audit:
    formula = _load_json(path)
    _require(formula.get("schema_version") == 1, "unsupported BioASQ formula schema")
    _require(
        formula.get("id") == "bioasq-v2-initial-jaccard-sum-min"
        and formula.get("status") == "frozen_initial_before_development_metric_output",
        "initial BioASQ formula is not frozen before development output",
    )
    try:
        frozen_on = date.fromisoformat(str(formula.get("frozen_on")))
    except ValueError as exc:
        raise BioasqFormulaV2ContractError("formula frozen_on must be YYYY-MM-DD") from exc
    _require(frozen_on.isoformat() == "2026-08-12", "formula freeze date drifted")
    _require(not find_forbidden_fields(formula), "formula contract contains metric output fields")

    successor_path = _resolve_reference(formula.get("successor_protocol"), "successor protocol")
    successor_audit = audit_bioasq_pilot_v2(successor_path)
    successor = _load_json(successor_path)
    _require(
        successor_audit.status == "frozen_after_source_compatibility_before_metric_formula"
        and successor_audit.total_cases == 21
        and successor_audit.primary_support == 10
        and successor_audit.sensitivity_supports == (5,)
        and successor_audit.readiness_contribution == 0,
        "formula references an incompatible successor boundary",
    )

    boundary = formula.get("claim_boundary")
    _require(isinstance(boundary, dict), "formula is missing its claim boundary")
    exclusions = boundary.get("not_a_claim_of")
    _require(
        boundary.get("formula_class") == "article_level_mesh_jaccard_sum_of_path_minima"
        and boundary.get("readiness_contribution") == 0
        and isinstance(exclusions, list)
        and {
            "a validated gap detector",
            "an exact LION replication",
            "period-appropriate historical indexing",
            "independent held-out validation",
            "generalization beyond the BioASQ secondary snapshot",
        }
        <= set(exclusions),
        "formula claim boundary drifted",
    )

    timing = formula.get("freeze_timing")
    _require(isinstance(timing, dict), "formula is missing freeze timing")
    for field in (
        "source_compatibility_counts_seen",
        "case_identities_splits_and_labels_seen",
        "legacy_failed_openalex_metric_outputs_seen",
        "lion_published_aggregate_evaluation_results_seen",
    ):
        _require(timing.get(field) is True, f"formula must disclose {field}")
    for field in (
        "bioasq_development_metric_outputs_seen",
        "bioasq_heldout_metric_outputs_seen",
        "this_formula_executed_on_bioasq_seen",
    ):
        _require(timing.get(field) is False, f"formula was not frozen before {field}")
    _require(
        "No BioASQ candidate score" in str(timing.get("disclosure"))
        and "LION's published aggregate evaluation" in str(timing.get("disclosure")),
        "formula freeze disclosure is incomplete",
    )

    basis = formula.get("research_basis")
    _require(isinstance(basis, dict), "formula is missing its research basis")
    primary = basis.get("primary_source")
    differences = basis.get("material_differences")
    _require(
        isinstance(primary, dict)
        and primary.get("doi") == "https://doi.org/10.1093/bioinformatics/bty845"
        and primary.get("pmc") == "https://pmc.ncbi.nlm.nih.gov/articles/PMC6499247/"
        and basis.get("adopted_design")
        == (
            "LION's default open-discovery configuration uses Jaccard edge weights, minimum "
            "path aggregation, and sum accumulation across linking paths."
        )
        and isinstance(differences, list)
        and len(differences) >= 4
        and any("sentence-level" in item and "article-level" in item for item in differences)
        and any("retains every article" in item for item in differences),
        "formula research basis or material-difference disclosure drifted",
    )

    graph = formula.get("graph_contract")
    _require(isinstance(graph, dict), "formula is missing graph construction")
    _require(
        graph.get("node_identity") == "MeSH 2013 descriptor UI"
        and graph.get("document_unit") == "one BioASQ article"
        and graph.get("publication_cutoff")
        == successor["source_transform"]["publication_cutoff"]
        and graph.get("article_labels")
        == "binary unique descriptor set; duplicate assignments are an error"
        and graph.get("support")
        == "n_x is the number of included articles containing descriptor x"
        and graph.get("cooccurrence")
        == (
            "n_xy is the number of included articles containing both distinct descriptors x "
            "and y"
        )
        and graph.get("threshold_runs")
        == [
            {"name": "primary", "minimum_support_articles": 10},
            {"name": "sensitivity_lower_support", "minimum_support_articles": 5},
        ]
        and graph.get("eligible_node_set")
        == "V_t contains every descriptor x with n_x >= threshold t"
        and graph.get("eligible_edge")
        == (
            "An undirected edge (x,y) exists when x and y are distinct members of V_t and "
            "n_xy > 0"
        )
        and graph.get("candidate_set")
        == "For seed A, rank every C in V_t except A, including candidates with a direct A-C edge."
        and graph.get("bridge_set")
        == (
            "For a candidate C, use every B in V_t except A and C where n_AB > 0 and n_BC > 0."
        )
        and graph.get("direct_ac_policy")
        == (
            "Never delete A-C articles, never exclude C because n_AC > 0, report n_AC, and do "
            "not use n_AC as a separate score feature."
        ),
        "formula graph contract drifted",
    )

    edge = formula.get("edge_weight")
    _require(
        edge
        == {
            "name": "article_jaccard",
            "formula": "J(x,y) = n_xy / (n_x + n_y - n_xy)",
            "domain": "distinct eligible descriptors joined by an eligible edge",
            "range": "0 < J(x,y) <= 1",
            "zero_policy": "A missing edge contributes no path rather than an edge of weight zero.",
        },
        "formula edge weight drifted",
    )
    score = formula.get("path_and_candidate_score")
    _require(isinstance(score, dict), "formula is missing path and candidate scoring")
    _require(
        score.get("path_formula") == "P(A,B,C) = min(J(A,B), J(B,C))"
        and score.get("candidate_formula")
        == "S(A,C) = sum(P(A,B,C) for B in bridge_set(A,C))"
        and score.get("empty_bridge_score") == "0"
        and score.get("bridge_order") == "descriptor_ui ascending"
        and "graph association measurement" in str(score.get("interpretation")),
        "formula path or accumulation rule drifted",
    )

    numeric = formula.get("numeric_reproducibility")
    _require(isinstance(numeric, dict), "formula is missing numeric reproducibility")
    _require(
        numeric.get("arithmetic")
        == (
            "Python decimal.Decimal only; binary floating point is forbidden for persisted scores"
        )
        and numeric.get("decimal_context_precision") == 40
        and numeric.get("decimal_rounding") == "ROUND_HALF_EVEN"
        and numeric.get("edge_weight_evaluation")
        == (
            "construct Decimal from integer counts, then divide under the frozen context"
        )
        and numeric.get("summation")
        == (
            "sum path Decimal values in descriptor_ui ascending order under the frozen context"
        )
        and numeric.get("persisted_score_quantum") == "0.000000000000001"
        and numeric.get("persisted_score_rounding")
        == "quantize once after the full sum using ROUND_HALF_EVEN"
        and numeric.get("comparison_value") == "the persisted quantized Decimal score",
        "formula numeric contract drifted",
    )

    ranking = formula.get("ranking_contract")
    successor_ranking = successor["ranking_contract"]
    _require(isinstance(ranking, dict), "formula is missing ranking contract")
    _require(
        all(
            ranking.get(field) == successor_ranking[field]
            for field in (
                "primary_orientation",
                "tie_policy",
                "rank_fraction",
                "top_5_percent",
            )
        )
        and ranking.get("candidate_order")
        == "persisted score descending, descriptor_ui ascending for display only"
        and ranking.get("one_based_rank")
        == "count(candidate_persisted_score >= target_persisted_score)"
        and ranking.get("eligible_candidate_count") == "cardinality(V_t) - 1"
        and ranking.get("reciprocal_orientation")
        == successor_ranking["reciprocal_c_to_a_orientation"],
        "formula ranking contract drifted",
    )

    exclusions = formula.get("feature_exclusions")
    _require(isinstance(exclusions, list), "formula is missing feature exclusions")
    _require(
        {
            "case kind or label",
            "development or heldout split",
            "source discovery year",
            "named target identity as a feature",
            "named positive bridge identity as a feature",
            "direct A-C count as a separate feature, penalty, filter, or bonus",
            "MeSH tree distance, parent, child, or sibling relationship",
            "case-specific threshold or candidate override",
            "any OpenAlex topic metric output",
            "any LLM-generated or embedding feature",
        }
        == set(exclusions),
        "formula feature exclusions drifted",
    )

    isolation = formula.get("execution_isolation")
    _require(isinstance(isolation, dict), "formula is missing execution isolation")
    _require(
        isolation.get("allowed_first_run") == "development cases only, at support 10 and 5"
        and str(isolation.get("heldout_prohibition", "")).startswith(
            "Do not compute, cache, log, persist, or preview any held-out"
        )
        and "case-label-blind" in str(isolation.get("shared_graph_rule"))
        and "refuse overwrite" in str(isolation.get("output_path_rule"))
        and isolation.get("revision_budget") == 1
        and "at most one separately named revision contract"
        in str(isolation.get("revision_rule"))
        and "consumes the single revision budget" in str(isolation.get("no_silent_tuning")),
        "formula execution isolation or revision rule drifted",
    )

    reporting = formula.get("development_reporting")
    limitations = formula.get("limitations")
    _require(
        isinstance(reporting, list)
        and len(reporting) >= 5
        and isinstance(limitations, list)
        and len(limitations) >= 8,
        "formula reporting or limitations are incomplete",
    )
    serialized = json.dumps(formula, ensure_ascii=False).lower()
    _require("non-academic" in serialized, "formula must retain non-academic blind spots")
    _require("llm interpretation" in serialized, "formula must keep the LLM layer gated")

    return BioasqFormulaV2Audit(
        status=formula["status"],
        formula_class=boundary["formula_class"],
        edge_weight=edge["name"],
        path_aggregation="minimum",
        candidate_accumulation="sum",
        threshold_supports=tuple(
            item["minimum_support_articles"] for item in graph["threshold_runs"]
        ),
        decimal_precision=numeric["decimal_context_precision"],
        revision_budget=isolation["revision_budget"],
        readiness_contribution=boundary["readiness_contribution"],
    )


def main() -> None:
    audit = audit_bioasq_formula_v2()
    print("BioASQ v2 initial formula contract: structurally valid")
    print(f"status: {audit.status}")
    print(f"formula class: {audit.formula_class}")
    print(
        f"formula: {audit.candidate_accumulation}({audit.path_aggregation}({audit.edge_weight}))"
    )
    print(f"support runs: {', '.join(map(str, audit.threshold_supports))}")
    print(f"decimal precision: {audit.decimal_precision}")
    print(f"revision budget: {audit.revision_budget}")
    print(f"readiness contribution: {audit.readiness_contribution}")


if __name__ == "__main__":
    main()
