"""Validate the BioASQ v2 initial-formula development review artifact.

This validator checks provenance, the exact 11-case development population, source-count
consistency, Decimal/ranking invariants, and the absence of held-out case output. It validates a
development measurement only; a passing audit does not validate the metric or add v3 readiness.

Run: ``python -m pipeline.benchmark.validate_bioasq_v2_development``
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
from pathlib import Path

from pipeline.benchmark.bioasq_v2_development import (
    BOUND_GUARD_SCALED_UNITS,
    BOUND_SCALE_EXPONENT,
    COMPATIBILITY_PATH,
    DECIMAL_PRECISION,
    EXECUTOR_SOURCE_PATH,
    FORMULA_PATH,
    FORMULA_QUANTUM,
    NATIVE_SOURCE_PATH,
    SCORE_BOUNDS_SOURCE_PATH,
    SUCCESSOR_PATH,
    SUPPORT_THRESHOLDS,
    load_development_cases,
)
from pipeline.benchmark.validate_bioasq_formula_v2 import audit_bioasq_formula_v2
from pipeline.paths import REPO_ROOT


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


FORMULA_SHA256 = _sha256_file(FORMULA_PATH)
DEVELOPMENT_PATH = (
    REPO_ROOT
    / "benchmarks"
    / "v3"
    / "manifests"
    / f"bioasq-v2-development-{FORMULA_SHA256[:12]}.json"
)
EXPECTED_CACHE_MANIFEST_PATH = (
    REPO_ROOT
    / "data"
    / "cache"
    / (
        f"bioasq-v2-jaccard-{FORMULA_SHA256[:12]}-"
        f"{_sha256_file(EXECUTOR_SOURCE_PATH)[:12]}"
    )
    / "cache-manifest.json"
)
PUBLISHED_GRAPH_MANIFEST_PATH = (
    REPO_ROOT
    / "benchmarks"
    / "v3"
    / "manifests"
    / (
        f"bioasq-v2-graph-cache-{FORMULA_SHA256[:12]}-"
        f"{_sha256_file(EXECUTOR_SOURCE_PATH)[:12]}.json"
    )
)


class BioasqV2DevelopmentError(ValueError):
    pass


@dataclass(frozen=True)
class BioasqV2DevelopmentAudit:
    status: str
    case_count: int
    heldout_case_count_computed: int
    primary_top_5_percent_count: int
    sensitivity_top_5_percent_count: int
    readiness_contribution: int
    local_cache_verified: bool


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BioasqV2DevelopmentError(message)


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
    _require(isinstance(value, str), f"{context}: Decimal value must be text")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise BioasqV2DevelopmentError(f"{context}: invalid Decimal") from exc
    _require(parsed.is_finite(), f"{context}: Decimal must be finite")
    return parsed


def _audit_cache_reference(value: object, output: dict, require_local_cache: bool) -> bool:
    _require(isinstance(value, dict), "missing graph cache manifest reference")
    _require(
        set(value) == {"path", "sha256", "bytes"},
        "malformed graph cache manifest reference",
    )
    expected_relative = EXPECTED_CACHE_MANIFEST_PATH.relative_to(REPO_ROOT).as_posix()
    _require(value.get("path") == expected_relative, "graph cache manifest path drifted")
    _require(
        isinstance(value.get("sha256"), str)
        and len(value["sha256"]) == 64
        and isinstance(value.get("bytes"), int)
        and value["bytes"] > 0,
        "graph cache manifest identity is incomplete",
    )
    published = audit_bioasq_v2_graph_manifest()
    published_edges = {
        year: published["edge_headers"][year]["edge_count"] for year in ("2011", "2012")
    }
    _require(
        output.get("graph", {}).get("edge_counts") == published_edges,
        "published graph edge counts drifted",
    )
    if not EXPECTED_CACHE_MANIFEST_PATH.exists():
        _require(not require_local_cache, "required local graph cache manifest is missing")
        return False
    _require(
        _file_identity(EXPECTED_CACHE_MANIFEST_PATH) == value,
        "local graph cache manifest identity drifted",
    )
    cache = _load_json(EXPECTED_CACHE_MANIFEST_PATH)
    _require(cache == published, "local and published graph manifests differ")
    _require(
        cache.get("purpose") == "case_blind_graph_cache_without_metric_output"
        and cache.get("case_identities_or_labels_stored") is False
        and cache.get("metric_outputs_materialized") is False,
        "local graph cache crossed the case or metric isolation boundary",
    )
    _require(
        cache.get("formula_contract") == _file_identity(FORMULA_PATH)
        and cache.get("builder_source") == _file_identity(EXECUTOR_SOURCE_PATH)
        and cache.get("native_pair_counter_source") == _file_identity(NATIVE_SOURCE_PATH),
        "local graph cache code or formula provenance drifted",
    )
    _require(
        cache.get("native_rank_screener_source")
        == _file_identity(SCORE_BOUNDS_SOURCE_PATH),
        "local graph cache rank screener provenance drifted",
    )
    expected_edges = {
        year: cache["edge_headers"][year]["edge_count"] for year in ("2011", "2012")
    }
    _require(output.get("graph", {}).get("edge_counts") == expected_edges, "edge counts drifted")
    if require_local_cache:
        for relative_name, identity in cache.get("generated_files", {}).items():
            generated = EXPECTED_CACHE_MANIFEST_PATH.parent / relative_name
            _require(
                generated.is_file()
                and generated.stat().st_size == identity.get("bytes")
                and _sha256_file(generated) == identity.get("sha256"),
                f"local graph cache file drifted: {relative_name}",
            )
    return True


def audit_bioasq_v2_graph_manifest(
    path: Path = PUBLISHED_GRAPH_MANIFEST_PATH,
) -> dict:
    manifest = _load_json(path)
    _require(
        manifest.get("schema_version") == 1
        and manifest.get("purpose") == "case_blind_graph_cache_without_metric_output"
        and manifest.get("case_identities_or_labels_stored") is False
        and manifest.get("metric_outputs_materialized") is False,
        "published graph manifest crossed its case-blind boundary",
    )
    _require(
        manifest.get("formula_contract") == _file_identity(FORMULA_PATH)
        and manifest.get("successor_protocol") == _file_identity(SUCCESSOR_PATH)
        and manifest.get("builder_source") == _file_identity(EXECUTOR_SOURCE_PATH)
        and manifest.get("native_pair_counter_source") == _file_identity(NATIVE_SOURCE_PATH)
        and manifest.get("native_rank_screener_source")
        == _file_identity(SCORE_BOUNDS_SOURCE_PATH),
        "published graph formula or code provenance drifted",
    )
    compatibility = _load_json(COMPATIBILITY_PATH)
    snapshot = compatibility["inputs"]["snapshot_transport"]
    mesh = compatibility["inputs"]["descriptor_vocabulary"]
    _require(
        manifest.get("source_snapshot")
        == {"sha256": snapshot["sha256"], "bytes": snapshot["bytes"]}
        and manifest.get("descriptor_vocabulary")
        == {"sha256": mesh["sha256"], "bytes": mesh["bytes"]}
        and manifest.get("node_count") == mesh["descriptor_count"]
        and manifest.get("cutoff_years") == [2011, 2012],
        "published graph source or universe provenance drifted",
    )
    edge_headers = manifest.get("edge_headers")
    _require(
        isinstance(edge_headers, dict)
        and set(edge_headers) == {"2011", "2012"},
        "published graph edge headers drifted",
    )
    for year in ("2011", "2012"):
        header = edge_headers[year]
        _require(
            isinstance(header, dict)
            and header.get("node_count") == mesh["descriptor_count"]
            and header.get("cutoff_year") == int(year)
            and isinstance(header.get("edge_count"), int)
            and header["edge_count"] > 0
            and isinstance(header.get("bytes"), int)
            and header["bytes"] > 0
            and isinstance(header.get("sha256"), str)
            and len(header["sha256"]) == 64,
            f"published graph {year} edge identity drifted",
        )
    generated = manifest.get("generated_files")
    _require(
        isinstance(generated, dict)
        and set(generated)
        == {
            "development-cutoffs.corpus.bin",
            "nodes.json",
            "native-build.json",
            "bioasq_pair_counts.exe",
            "score-bounds-native-build.json",
            "bioasq_score_bounds.exe",
            "edges-2011.bin",
            "edges-2012.bin",
        }
        and all(
            isinstance(identity, dict)
            and set(identity) == {"sha256", "bytes"}
            and isinstance(identity["sha256"], str)
            and len(identity["sha256"]) == 64
            and isinstance(identity["bytes"], int)
            and identity["bytes"] > 0
            for identity in generated.values()
        ),
        "published graph generated-file identities drifted",
    )
    _require(
        generated["edges-2011.bin"] == {
            "sha256": edge_headers["2011"]["sha256"],
            "bytes": edge_headers["2011"]["bytes"],
        }
        and generated["edges-2012.bin"] == {
            "sha256": edge_headers["2012"]["sha256"],
            "bytes": edge_headers["2012"]["bytes"],
        },
        "published graph edge identities are internally inconsistent",
    )
    return manifest


def _expected_summary(cases: list[dict]) -> dict:
    result: dict[str, dict[str, dict[str, int]]] = {}
    for threshold in SUPPORT_THRESHOLDS:
        threshold_key = str(threshold)
        result[threshold_key] = {}
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
            result[threshold_key][kind] = {
                "case_count": len(runs),
                "top_5_percent_count": sum(run["target_top_5_percent"] for run in runs),
                "below_median_count": sum(run["target_below_median"] for run in runs),
            }
    return result


def _audit_support_run(
    run: object,
    *,
    case_id: str,
    endpoint_a_ui: str,
    target_c_ui: str,
    source_case: dict,
    eligible_universe: int,
) -> None:
    context = f"{case_id} support run"
    _require(isinstance(run, dict), f"{context}: expected an object")
    _require(
        set(run)
        == {
            "minimum_support_articles",
            "endpoint_a_article_support",
            "target_c_article_support",
            "direct_ac_article_count",
            "eligible_candidate_count",
            "target_persisted_score",
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
        and run["direct_ac_article_count"] == source_case["direct_ac_article_count"],
        f"{context}: source support or direct A-C count drifted",
    )
    candidate_count = run["eligible_candidate_count"]
    _require(
        candidate_count == eligible_universe - 1 and candidate_count > 0,
        f"{context}: eligible candidate denominator drifted",
    )
    score = _decimal(run["target_persisted_score"], f"{context} target score")
    _require(
        score >= 0 and score.as_tuple().exponent == FORMULA_QUANTUM.as_tuple().exponent,
        f"{context}: target score quantum drifted",
    )
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
        == expected_fraction,
        f"{context}: rank fraction drifted",
    )
    _require(
        run["target_top_5_percent"] is (rank * 20 <= candidate_count)
        and run["target_below_median"] is (rank * 2 > candidate_count),
        f"{context}: rank classification drifted",
    )
    proof = run["rank_proof"]
    _require(isinstance(proof, dict), f"{context}: rank proof is missing")
    _require(
        proof.get("method")
        == "exact_integer_rational_bounds_then_python_decimal_refinement"
        and proof.get("bound_scale_exponent") == BOUND_SCALE_EXPONENT
        and proof.get("decimal_guard_scaled_units") == BOUND_GUARD_SCALED_UNITS
        and proof.get("partition_candidate_count") == candidate_count,
        f"{context}: rank proof contract drifted",
    )
    proof_counts = [
        proof.get("bound_proven_at_or_above_count"),
        proof.get("bound_proven_below_count"),
        proof.get("exact_decimal_refinement_count"),
        proof.get("exact_decimal_at_or_above_count"),
    ]
    _require(
        all(
            isinstance(value, int) and not isinstance(value, bool) and value >= 0
            for value in proof_counts
        )
        and proof["exact_decimal_refinement_count"] >= 1
        and proof["exact_decimal_at_or_above_count"]
        <= proof["exact_decimal_refinement_count"]
        and proof["bound_proven_at_or_above_count"]
        + proof["bound_proven_below_count"]
        + proof["exact_decimal_refinement_count"]
        == candidate_count
        and proof["bound_proven_at_or_above_count"]
        + proof["exact_decimal_at_or_above_count"]
        == rank,
        f"{context}: rank proof counts do not establish the persisted rank",
    )
    _require(
        isinstance(proof.get("zero_target_nonnegative_shortcut"), bool),
        f"{context}: zero-target proof flag drifted",
    )
    if proof["zero_target_nonnegative_shortcut"]:
        _require(
            score == 0
            and proof["bound_proven_at_or_above_count"] == candidate_count - 1
            and proof["bound_proven_below_count"] == 0
            and proof["exact_decimal_refinement_count"] == 1
            and proof["exact_decimal_at_or_above_count"] == 1,
            f"{context}: zero-target nonnegative proof drifted",
        )
    bridges = run["top_target_bridges"]
    bridge_count = run["target_bridge_count"]
    _require(
        isinstance(bridges, list)
        and isinstance(bridge_count, int)
        and not isinstance(bridge_count, bool)
        and bridge_count >= len(bridges)
        and len(bridges) <= 20,
        f"{context}: bridge count drifted",
    )
    bridge_uis: list[str] = []
    rendered_contributions: list[Decimal] = []
    for bridge in bridges:
        _require(
            isinstance(bridge, dict)
            and set(bridge)
            == {
                "descriptor_ui",
                "descriptor_label",
                "ab_article_count",
                "bc_article_count",
                "jaccard_ab",
                "jaccard_bc",
                "path_contribution",
            },
            f"{context}: bridge field set drifted",
        )
        bridge_ui = bridge["descriptor_ui"]
        _require(
            isinstance(bridge_ui, str)
            and bridge_ui not in {endpoint_a_ui, target_c_ui}
            and bridge_ui not in bridge_uis,
            f"{context}: invalid or duplicate bridge identity",
        )
        _require(
            isinstance(bridge["descriptor_label"], str)
            and bool(bridge["descriptor_label"])
            and isinstance(bridge["ab_article_count"], int)
            and bridge["ab_article_count"] > 0
            and isinstance(bridge["bc_article_count"], int)
            and bridge["bc_article_count"] > 0,
            f"{context}: bridge counts or label drifted",
        )
        jaccard_ab = _decimal(bridge["jaccard_ab"], f"{context} J(A,B)")
        jaccard_bc = _decimal(bridge["jaccard_bc"], f"{context} J(B,C)")
        contribution = _decimal(
            bridge["path_contribution"], f"{context} bridge contribution"
        )
        expected_contribution = min(jaccard_ab, jaccard_bc).quantize(
            FORMULA_QUANTUM, rounding=ROUND_HALF_EVEN
        )
        _require(
            0 < jaccard_ab <= 1
            and 0 < jaccard_bc <= 1
            and contribution == expected_contribution,
            f"{context}: bridge Jaccard or path minimum drifted",
        )
        bridge_uis.append(bridge_ui)
        rendered_contributions.append(contribution)
    _require(
        rendered_contributions == sorted(rendered_contributions, reverse=True),
        f"{context}: top bridges are not contribution-descending",
    )


def audit_bioasq_v2_development(
    path: Path = DEVELOPMENT_PATH, *, require_local_cache: bool = False
) -> BioasqV2DevelopmentAudit:
    audit_bioasq_formula_v2()
    output = _load_json(path)
    _require(output.get("schema_version") == 1, "unsupported development artifact schema")
    _require(
        output.get("status") == "development_metric_output_initial_formula"
        and output.get("readiness_contribution") == 0,
        "development status or readiness contribution drifted",
    )
    claim = output.get("claim_boundary")
    _require(
        isinstance(claim, str)
        and "Development-only measurement" in claim
        and "not held-out validation" in claim
        and "not" in claim
        and "gap detector" in claim,
        "development claim boundary is incomplete",
    )

    inputs = output.get("inputs")
    _require(isinstance(inputs, dict), "development inputs are missing")
    _require(
        inputs.get("formula_contract") == _file_identity(FORMULA_PATH)
        and inputs.get("successor_protocol") == _file_identity(SUCCESSOR_PATH)
        and inputs.get("executor_source") == _file_identity(EXECUTOR_SOURCE_PATH)
        and inputs.get("native_pair_counter_source") == _file_identity(NATIVE_SOURCE_PATH),
        "development code, formula, or protocol provenance drifted",
    )
    _require(
        inputs.get("native_rank_screener_source")
        == _file_identity(SCORE_BOUNDS_SOURCE_PATH),
        "development rank screener provenance drifted",
    )
    compatibility = _load_json(COMPATIBILITY_PATH)
    expected_snapshot = compatibility["inputs"]["snapshot_transport"]
    expected_mesh = compatibility["inputs"]["descriptor_vocabulary"]
    _require(
        inputs.get("source_snapshot")
        == {"sha256": expected_snapshot["sha256"], "bytes": expected_snapshot["bytes"]}
        and inputs.get("descriptor_vocabulary")
        == {"sha256": expected_mesh["sha256"], "bytes": expected_mesh["bytes"]},
        "development source identity drifted",
    )
    local_cache_verified = _audit_cache_reference(
        inputs.get("graph_cache_manifest"), output, require_local_cache
    )

    isolation = output.get("execution_isolation")
    _require(
        isolation
        == {
            "split": "development",
            "case_count": 11,
            "heldout_case_count_computed": 0,
            "heldout_scores_ranks_orderings_or_bridges_materialized": False,
            "formula_revision_budget_consumed": 0,
        },
        "development/held-out execution isolation drifted",
    )
    _require(
        output.get("formula")
        == {
            "edge_weight": "article_jaccard",
            "path_aggregation": "minimum",
            "candidate_accumulation": "sum",
            "support_runs": [10, 5],
            "decimal_precision": 40,
            "persisted_score_quantum": "0.000000000000001",
            "tie_policy": "conservative worst tied rank",
        },
        "development formula declaration drifted",
    )
    graph = output.get("graph")
    _require(
        isinstance(graph, dict)
        and graph.get("node_count") == expected_mesh["descriptor_count"]
        and graph.get("cutoff_years") == [2011, 2012]
        and isinstance(graph.get("edge_counts"), dict)
        and set(graph["edge_counts"]) == {"2011", "2012"}
        and all(isinstance(value, int) and value > 0 for value in graph["edge_counts"].values()),
        "development graph declaration drifted",
    )

    cases = output.get("cases")
    expected_cases = load_development_cases()
    _require(isinstance(cases, list) and len(cases) == 11, "development case count drifted")
    _require(
        [case.get("id") for case in cases] == [case.id for case in expected_cases],
        "development case population or order drifted",
    )
    source_cases = {case["id"]: case for case in compatibility["measurement"]["cases"]}
    universes = compatibility["measurement"][
        "support_eligible_descriptor_count_by_cutoff_and_threshold"
    ]
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
            },
            f"{expected_case.id}: case field set drifted",
        )
        _require(
            case["kind"] == expected_case.kind
            and case["split"] == "development"
            and case["label_scope"] == expected_case.label_scope
            and case["cutoff"] == expected_case.cutoff
            and case["endpoint_a"] == expected_case.endpoint_a
            and case["target_c"] == expected_case.target_c,
            f"{expected_case.id}: frozen identity, label, or split drifted",
        )
        runs = case["support_runs"]
        _require(
            isinstance(runs, list)
            and [run.get("minimum_support_articles") for run in runs] == [10, 5],
            f"{expected_case.id}: support run order drifted",
        )
        cutoff_year = expected_case.cutoff[:4]
        source_case = source_cases[expected_case.id]
        for run in runs:
            threshold = str(run["minimum_support_articles"])
            _audit_support_run(
                run,
                case_id=expected_case.id,
                endpoint_a_ui=expected_case.endpoint_a["descriptor_ui"],
                target_c_ui=expected_case.target_c["descriptor_ui"],
                source_case=source_case,
                eligible_universe=universes[cutoff_year][threshold],
            )
        primary, sensitivity = runs
        _require(
            Decimal(sensitivity["target_persisted_score"])
            >= Decimal(primary["target_persisted_score"])
            and sensitivity["target_bridge_count"] >= primary["target_bridge_count"],
            f"{expected_case.id}: lower-support graph is not a superset measurement",
        )

    heldout_ids = {
        case["id"]
        for case in compatibility["measurement"]["cases"]
        if case["split"] == "heldout"
    }
    serialized = json.dumps(output, sort_keys=True)
    _require(
        not any(case_id in serialized for case_id in heldout_ids),
        "development artifact contains a held-out case identity",
    )
    _require(
        all(
            case["support_runs"][0]["target_persisted_score"]
            == case["support_runs"][1]["target_persisted_score"]
            and case["support_runs"][0]["target_bridge_count"]
            == case["support_runs"][1]["target_bridge_count"]
            for case in cases
        ),
        "reported support-5 score or bridge invariance drifted",
    )
    expected_summary = _expected_summary(cases)
    _require(
        output.get("development_summary") == expected_summary,
        "development summary drifted from case-level measurements",
    )
    runtime = output.get("runtime")
    _require(
        isinstance(runtime, dict)
        and isinstance(runtime.get("scoring_elapsed_seconds"), (int, float))
        and runtime["scoring_elapsed_seconds"] >= 0
        and isinstance(runtime.get("generated_cache_bytes"), int)
        and runtime["generated_cache_bytes"] > 0
        and isinstance(runtime.get("compiler_version"), str)
        and bool(runtime["compiler_version"])
        and runtime.get("command") == "python -m pipeline.benchmark.bioasq_v2_development",
        "development runtime provenance drifted",
    )
    limitations = output.get("limitations")
    limitations_text = " ".join(limitations).lower() if isinstance(limitations, list) else ""
    _require(
        len(limitations or []) >= 6
        and "not held-out validation" in limitations_text
        and "not independently adjudicated" in limitations_text
        and "not verified absences" in limitations_text
        and "non-academic" in limitations_text
        and "llm interpretation" in limitations_text,
        "development limitations are incomplete",
    )

    primary_top5 = sum(
        case["support_runs"][0]["target_top_5_percent"] for case in cases
    )
    sensitivity_top5 = sum(
        case["support_runs"][1]["target_top_5_percent"] for case in cases
    )
    return BioasqV2DevelopmentAudit(
        status=output["status"],
        case_count=len(cases),
        heldout_case_count_computed=isolation["heldout_case_count_computed"],
        primary_top_5_percent_count=primary_top5,
        sensitivity_top_5_percent_count=sensitivity_top5,
        readiness_contribution=output["readiness_contribution"],
        local_cache_verified=local_cache_verified,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, nargs="?", default=DEVELOPMENT_PATH)
    parser.add_argument("--require-local-cache", action="store_true")
    args = parser.parse_args()
    audit = audit_bioasq_v2_development(
        args.path, require_local_cache=args.require_local_cache
    )
    print("BioASQ v2 development artifact: structurally valid")
    print(f"status: {audit.status}")
    print(f"development cases: {audit.case_count}")
    print(f"held-out cases computed: {audit.heldout_case_count_computed}")
    print(f"primary top-5% targets: {audit.primary_top_5_percent_count}")
    print(f"support-5 top-5% targets: {audit.sensitivity_top_5_percent_count}")
    print(f"local cache verified: {str(audit.local_cache_verified).lower()}")
    print(f"readiness contribution: {audit.readiness_contribution}")


if __name__ == "__main__":
    main()
