"""Execute the frozen BioASQ v2 direct-penalized revision on development only.

The revision keeps the case-blind graph and indirect Jaccard-min-sum calculation frozen by the
initial formula, then divides every candidate score by ``1 + n_AC``. This module exposes no
held-out mode. It writes a new checksum-addressed artifact only after all 11 development cases and
both support settings finish, then applies the pre-registered pass-or-terminate gate mechanically.

Run: ``python -m pipeline.benchmark.bioasq_v2_revision_development``
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from pathlib import Path

import numpy as np

from pipeline.benchmark.bioasq_v2_development import (
    BOUND_GUARD_SCALED_UNITS,
    BOUND_SCALE,
    BOUND_SCALE_EXPONENT,
    DECIMAL_PRECISION,
    DEVELOPMENT_CUTOFFS,
    EXECUTOR_SOURCE_PATH as INITIAL_EXECUTOR_SOURCE_PATH,
    FORMULA_QUANTUM,
    NATIVE_SOURCE_PATH,
    SCORE_BOUNDS_SOURCE_PATH,
    SNAPSHOT_PATH,
    SUPPORT_THRESHOLDS,
    BioasqDevelopmentError,
    EdgeGraph,
    GraphCache,
    NodeIndex,
    _exact_candidate_from_paths,
    _extract_candidate_paths,
    _file_identity,
    _load_json,
    _load_node_index_from_cache,
    _run_score_bounds,
    _write_new_json,
    load_development_cases,
    load_edge_graph,
    prepare_graph_cache,
)
from pipeline.benchmark.validate_bioasq_formula_v2_revision import (
    REVISION_FORMULA_PATH,
    audit_bioasq_formula_v2_revision,
)
from pipeline.benchmark.validate_bioasq_v2_development import (
    DEVELOPMENT_PATH as INITIAL_DEVELOPMENT_PATH,
    PUBLISHED_GRAPH_MANIFEST_PATH,
    audit_bioasq_v2_development,
    audit_bioasq_v2_graph_manifest,
)
from pipeline.paths import MESH_CACHE_DIR, REPO_ROOT

MESH_PATH = MESH_CACHE_DIR / "desc2013.gz"
REVISION_EXECUTOR_SOURCE_PATH = Path(__file__).resolve()


class BioasqRevisionDevelopmentError(BioasqDevelopmentError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BioasqRevisionDevelopmentError(message)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ceil_div(numerator: int, denominator: int) -> int:
    _require(numerator >= 0 and denominator > 0, "ceil division requires non-negative integers")
    return (numerator + denominator - 1) // denominator


def _revised_decimal(indirect: Decimal, direct_penalty: int) -> Decimal:
    _require(indirect >= 0, "indirect score must be non-negative")
    _require(direct_penalty >= 1, "direct penalty must be a positive integer")
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        context.rounding = ROUND_HALF_EVEN
        return indirect / Decimal(direct_penalty)


def score_seed_revision(
    graph: EdgeGraph,
    *,
    executable: Path,
    seed_id: int,
    target_id: int,
    threshold: int,
    node_index: NodeIndex,
    top_bridge_limit: int = 20,
) -> dict:
    _require(threshold in SUPPORT_THRESHOLDS, "unsupported revision support threshold")
    eligible = np.asarray(graph.support >= threshold)
    _require(eligible[seed_id] and eligible[target_id], "revision case endpoint is ineligible")
    bounds = _run_score_bounds(
        graph,
        executable=executable,
        seed_id=seed_id,
        target_id=target_id,
        threshold=threshold,
    )
    target_indirect, target_bridges = _exact_candidate_from_paths(
        graph,
        seed_id=seed_id,
        candidate_id=target_id,
        paths=bounds.target_paths,
    )
    _require(
        len(target_bridges) == bounds.bridge_counts[target_id],
        "revision target bridge count differs between bounds and Decimal paths",
    )
    direct_ac_count = bounds.seed_counts[target_id]
    direct_penalty = 1 + direct_ac_count
    target_revised = _revised_decimal(target_indirect, direct_penalty)
    target_persisted = target_revised.quantize(
        FORMULA_QUANTUM, rounding=ROUND_HALF_EVEN
    )
    candidate_ids = [
        int(node_id)
        for node_id in np.flatnonzero(eligible)
        if int(node_id) != seed_id
    ]
    candidate_count = len(candidate_ids)
    _require(candidate_count > 0, "revision candidate universe is empty")
    proven_at_or_above = 0
    proven_below = 0
    ambiguous: list[int] = []
    if target_persisted == 0:
        proven_at_or_above = candidate_count - 1
    else:
        boundary = target_persisted - FORMULA_QUANTUM / 2
        boundary_scaled = int(boundary * BOUND_SCALE)
        _require(
            Decimal(boundary_scaled) / Decimal(BOUND_SCALE) == boundary,
            "revision rank boundary is not representable at the bounds scale",
        )
        for candidate_id in candidate_ids:
            if candidate_id == target_id:
                continue
            penalty = 1 + bounds.seed_counts[candidate_id]
            lower = bounds.lower[candidate_id] // penalty
            upper = _ceil_div(bounds.upper[candidate_id], penalty)
            guarded_lower = lower - BOUND_GUARD_SCALED_UNITS
            guarded_upper = upper + BOUND_GUARD_SCALED_UNITS
            if guarded_lower > boundary_scaled:
                proven_at_or_above += 1
            elif guarded_upper < boundary_scaled:
                proven_below += 1
            else:
                ambiguous.append(candidate_id)
    extracted = _extract_candidate_paths(
        graph,
        candidate_ids=ambiguous,
        seed_counts=bounds.seed_counts,
        eligible=eligible,
    )
    exact_at_or_above = 1
    for candidate_id in ambiguous:
        indirect, _ = _exact_candidate_from_paths(
            graph,
            seed_id=seed_id,
            candidate_id=candidate_id,
            paths=extracted[candidate_id],
        )
        revised = _revised_decimal(indirect, 1 + bounds.seed_counts[candidate_id])
        persisted = revised.quantize(FORMULA_QUANTUM, rounding=ROUND_HALF_EVEN)
        exact_at_or_above += persisted >= target_persisted
    worst_tie_rank = proven_at_or_above + exact_at_or_above
    _require(
        proven_at_or_above + proven_below + len(ambiguous) + 1 == candidate_count,
        "revision rank proof does not partition the candidate universe",
    )
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        rank_fraction = Decimal(worst_tie_rank) / Decimal(candidate_count)
    target_bridges.sort(
        key=lambda item: (-item["path_contribution"], node_index.uis[item["bridge_id"]])
    )
    rendered_bridges = [
        {
            "descriptor_ui": node_index.uis[item["bridge_id"]],
            "descriptor_label": node_index.labels[item["bridge_id"]],
            "ab_article_count": item["ab_article_count"],
            "bc_article_count": item["bc_article_count"],
            "jaccard_ab": format(item["jaccard_ab"], "f"),
            "jaccard_bc": format(item["jaccard_bc"], "f"),
            "path_contribution": format(
                item["path_contribution"].quantize(
                    FORMULA_QUANTUM,
                    rounding=ROUND_HALF_EVEN,
                ),
                "f",
            ),
        }
        for item in target_bridges[:top_bridge_limit]
    ]
    return {
        "minimum_support_articles": threshold,
        "endpoint_a_article_support": int(graph.support[seed_id]),
        "target_c_article_support": int(graph.support[target_id]),
        "direct_ac_article_count": direct_ac_count,
        "target_direct_penalty": direct_penalty,
        "target_indirect_decimal_score": format(target_indirect, "f"),
        "target_revised_decimal_before_quantization": format(target_revised, "f"),
        "target_persisted_revised_score": format(target_persisted, "f"),
        "eligible_candidate_count": candidate_count,
        "target_worst_tie_rank": worst_tie_rank,
        "target_rank_fraction": format(rank_fraction, "f"),
        "target_top_5_percent": worst_tie_rank * 20 <= candidate_count,
        "target_below_median": worst_tie_rank * 2 > candidate_count,
        "target_bridge_count": len(target_bridges),
        "top_target_bridges": rendered_bridges,
        "rank_proof": {
            "method": (
                "direct_penalized_exact_integer_rational_bounds_then_python_decimal_refinement"
            ),
            "bound_scale_exponent": BOUND_SCALE_EXPONENT,
            "decimal_guard_scaled_units": BOUND_GUARD_SCALED_UNITS,
            "zero_target_nonnegative_shortcut": target_persisted == 0,
            "bound_proven_at_or_above_count": proven_at_or_above,
            "bound_proven_below_count": proven_below,
            "exact_decimal_refinement_count": len(ambiguous) + 1,
            "exact_decimal_at_or_above_count": exact_at_or_above,
            "partition_candidate_count": candidate_count,
        },
    }


def _summarize(cases: list[dict]) -> dict:
    summary: dict[str, dict[str, dict[str, int]]] = {}
    for threshold in SUPPORT_THRESHOLDS:
        threshold_key = str(threshold)
        summary[threshold_key] = {}
        for kind in ("source_labeled_positive", "hard_negative", "distant_negative"):
            runs = [
                next(
                    run
                    for run in case["support_runs"]
                    if run["minimum_support_articles"] == threshold
                )
                for case in cases
                if case["kind"] == kind
            ]
            summary[threshold_key][kind] = {
                "case_count": len(runs),
                "top_5_percent_count": sum(run["target_top_5_percent"] for run in runs),
                "below_median_count": sum(run["target_below_median"] for run in runs),
            }
    return summary


def _gate_decision(summary: dict) -> dict:
    checks: dict[str, dict[str, object]] = {}
    for threshold in SUPPORT_THRESHOLDS:
        key = str(threshold)
        rows = summary[key]
        checks[key] = {
            "all_11_cases_evaluable": sum(item["case_count"] for item in rows.values()) == 11,
            "positive_top_5_percent_count": rows["source_labeled_positive"][
                "top_5_percent_count"
            ],
            "positive_requirement_at_least": 2,
            "positive_requirement_passed": rows["source_labeled_positive"][
                "top_5_percent_count"
            ]
            >= 2,
            "hard_control_top_5_percent_count": rows["hard_negative"][
                "top_5_percent_count"
            ],
            "hard_control_requirement_allowed": 0,
            "hard_control_requirement_passed": rows["hard_negative"][
                "top_5_percent_count"
            ]
            == 0,
            "distant_control_below_median_count": rows["distant_negative"][
                "below_median_count"
            ],
            "distant_control_requirement_required": 4,
            "distant_control_requirement_passed": rows["distant_negative"][
                "below_median_count"
            ]
            == 4,
        }
        checks[key]["all_three_separation_requirements_passed"] = all(
            checks[key][field]
            for field in (
                "positive_requirement_passed",
                "hard_control_requirement_passed",
                "distant_control_requirement_passed",
            )
        )
    overall_pass = all(
        checks[str(threshold)]["all_11_cases_evaluable"]
        and checks[str(threshold)]["all_three_separation_requirements_passed"]
        for threshold in SUPPORT_THRESHOLDS
    )
    return {
        "pre_registered_gate_passed": overall_pass,
        "support_checks": checks,
        "sensitivity_agreement_required": True,
        "sensitivity_agreement_passed": (
            checks["10"]["all_three_separation_requirements_passed"]
            == checks["5"]["all_three_separation_requirements_passed"]
        ),
        "mechanical_action": (
            "freeze_exact_revision_as_final_before_heldout"
            if overall_pass
            else "terminate_pilot_before_heldout"
        ),
        "readiness_contribution": 0,
    }


def run_revision_development(
    cache: GraphCache,
    *,
    output_path: Path,
    command: str,
) -> dict:
    audit_bioasq_formula_v2_revision()
    audit_bioasq_v2_development(require_local_cache=True)
    audit_bioasq_v2_graph_manifest()
    cases = load_development_cases()
    index = _load_node_index_from_cache(cache.nodes_path)
    graphs = {
        year: load_edge_graph(cache.edge_paths[year], year) for year in DEVELOPMENT_CUTOFFS
    }
    started = time.perf_counter()
    outputs = []
    for case in cases:
        cutoff_year = int(case.cutoff[:4])
        graph = graphs[cutoff_year]
        seed_id = index.ui_to_id[case.endpoint_a["descriptor_ui"]]
        target_id = index.ui_to_id[case.target_c["descriptor_ui"]]
        runs = [
            score_seed_revision(
                graph,
                executable=cache.score_bounds_executable,
                seed_id=seed_id,
                target_id=target_id,
                threshold=threshold,
                node_index=index,
            )
            for threshold in SUPPORT_THRESHOLDS
        ]
        outputs.append(
            {
                "id": case.id,
                "kind": case.kind,
                "split": "development",
                "label_scope": case.label_scope,
                "cutoff": case.cutoff,
                "endpoint_a": case.endpoint_a,
                "target_c": case.target_c,
                "support_runs": runs,
            }
        )
        print(f"scored revision development case: {case.id}", flush=True)
    elapsed = time.perf_counter() - started
    summary = _summarize(outputs)
    decision = _gate_decision(summary)
    cache_bytes = sum(
        identity["bytes"] for identity in cache.manifest["generated_files"].values()
    )
    payload = {
        "schema_version": 1,
        "status": (
            "revision_development_gate_passed"
            if decision["pre_registered_gate_passed"]
            else "revision_development_gate_failed_terminate_before_heldout"
        ),
        "readiness_contribution": 0,
        "claim_boundary": (
            "Development-only measurement of the single source-informed BioASQ formula revision; "
            "not held-out validation, discovery truth, metric-v3 readiness, or a general gap "
            "detector."
        ),
        "inputs": {
            "revision_formula_contract": _file_identity(REVISION_FORMULA_PATH),
            "initial_development_measurement": _file_identity(INITIAL_DEVELOPMENT_PATH),
            "case_blind_graph_manifest": _file_identity(PUBLISHED_GRAPH_MANIFEST_PATH),
            "revision_executor_source": _file_identity(REVISION_EXECUTOR_SOURCE_PATH),
            "initial_graph_executor_source": _file_identity(INITIAL_EXECUTOR_SOURCE_PATH),
            "native_pair_counter_source": _file_identity(NATIVE_SOURCE_PATH),
            "native_rank_screener_source": _file_identity(SCORE_BOUNDS_SOURCE_PATH),
            "source_snapshot": cache.manifest["source_snapshot"],
            "descriptor_vocabulary": cache.manifest["descriptor_vocabulary"],
        },
        "execution_isolation": {
            "split": "development",
            "case_count": 11,
            "heldout_case_count_computed": 0,
            "heldout_scores_ranks_orderings_or_bridges_materialized": False,
            "revision_number": 1,
            "revision_budget_consumed": 1,
            "revision_budget_remaining": 0,
        },
        "formula": {
            "indirect_score": "sum(min(article_jaccard_ab, article_jaccard_bc))",
            "direct_penalty": "1 + direct_ac_article_count",
            "revised_score": "indirect_score / direct_penalty",
            "support_runs": list(SUPPORT_THRESHOLDS),
            "decimal_precision": DECIMAL_PRECISION,
            "persisted_score_quantum": format(FORMULA_QUANTUM, "f"),
            "tie_policy": "conservative worst tied rank",
        },
        "graph": {
            "node_count": cache.manifest["node_count"],
            "cutoff_years": list(DEVELOPMENT_CUTOFFS),
            "edge_counts": {
                year: cache.manifest["edge_headers"][str(year)]["edge_count"]
                for year in DEVELOPMENT_CUTOFFS
            },
        },
        "cases": outputs,
        "revision_development_summary": summary,
        "pre_registered_revision_development_decision": decision,
        "runtime": {
            "scoring_elapsed_seconds": round(elapsed, 3),
            "reused_case_blind_cache_bytes": cache_bytes,
            "compiler_version": cache.manifest["compiler_version"],
            "command": command,
        },
        "limitations": [
            "Only development cases were scored; the output is not held-out validation.",
            (
                "The revision was selected after inspecting initial development output and is "
                "not independent formula selection."
            ),
            (
                "Held-out identities and source counts were known before the revision; held-out "
                "metric scores, ranks, orderings, and bridges remain unseen."
            ),
            (
                "The additive-one direct penalty is a transparent heuristic, not causal novelty "
                "or an exact LION implementation."
            ),
            "Source-labelled positives are not independently adjudicated discovery truth.",
            (
                "Ontology-generated controls are not verified absences of relationships or "
                "non-academic knowledge."
            ),
            (
                "The secondary snapshot and maintained 2013 MeSH vocabulary are not the complete "
                "period-appropriate historical NLM baseline."
            ),
            (
                "No result contributes metric-v3 readiness or authorizes an LLM interpretation "
                "layer."
            ),
        ],
    }
    _write_new_json(output_path, payload)
    return payload


def default_output_path() -> Path:
    revision_hash = _sha256_file(REVISION_FORMULA_PATH)
    return (
        REPO_ROOT
        / "benchmarks"
        / "v3"
        / "manifests"
        / f"bioasq-v2-revision-1-development-{revision_hash[:12]}.json"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path, nargs="?", default=SNAPSHOT_PATH)
    parser.add_argument("--mesh", type=Path, default=MESH_PATH)
    parser.add_argument("--cache-root", type=Path, default=REPO_ROOT / "data" / "cache")
    parser.add_argument("--output", type=Path, default=default_output_path())
    args = parser.parse_args()
    cache = prepare_graph_cache(
        args.snapshot,
        mesh_path=args.mesh,
        cache_root=args.cache_root,
    )
    print(f"case-blind graph cache ready: {cache.directory}")
    command = "python -m pipeline.benchmark.bioasq_v2_revision_development"
    payload = run_revision_development(
        cache,
        output_path=args.output,
        command=command,
    )
    decision = payload["pre_registered_revision_development_decision"]
    print(f"wrote {args.output}")
    print(f"development cases: {len(payload['cases'])}")
    print("held-out cases computed: 0")
    print(f"pre-registered development gate passed: {decision['pre_registered_gate_passed']}")
    print(f"mechanical action: {decision['mechanical_action']}")
    print("readiness contribution: 0")


if __name__ == "__main__":
    main()
