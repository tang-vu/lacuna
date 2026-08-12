"""Validate the frozen, pre-score autonomous prospective metric v1 contract."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path

from pipeline.benchmark.autonomous_candidate_index import _sha256_file
from pipeline.benchmark.autonomous_metric_v1_formula import (
    DECIMAL_PRECISION,
    Q48_SCALE,
    TIE_SALT_U64,
    adamic_adar_weight_q48,
    positive_association_edge,
    resource_allocation_weight_q48,
    splitmix64,
    tie_key,
)
from pipeline.benchmark.autonomous_t0 import audit_sealed_t0
from pipeline.benchmark.validate_autonomous_candidate_universe import audit_candidate_universe
from pipeline.paths import REPO_ROOT
from pipeline.provenance import sha256_payload

CONTRACT_PATH = REPO_ROOT / "benchmarks" / "autonomous" / "metric-v1.json"
EXPECTED_ID = "autonomous-prospective-metric-v1"


class AutonomousMetricV1ContractError(ValueError):
    pass


@dataclass(frozen=True)
class AutonomousMetricV1Audit:
    metric_id: str
    sha256: str
    status: str
    primary_formula: str
    candidate_pair_count: int
    readiness_contribution: int


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AutonomousMetricV1ContractError(message)


def _anchored_file(item: object, *, expected_path: str, name: str) -> Path:
    _require(
        isinstance(item, dict)
        and item.get("path") == expected_path
        and isinstance(item.get("file_sha256"), str)
        and re.fullmatch(r"[0-9a-f]{64}", item["file_sha256"]) is not None,
        f"{name} identity drifted",
    )
    resolved = (CONTRACT_PATH.parent / expected_path).resolve()
    _require(resolved.is_file(), f"{name} file is missing")
    _require(_sha256_file(resolved) == item["file_sha256"], f"{name} hash drifted")
    return resolved


def audit_autonomous_metric_v1(path: Path = CONTRACT_PATH) -> AutonomousMetricV1Audit:
    payload = json.loads(path.read_text(encoding="utf-8"))
    sealed = audit_sealed_t0()
    universe = audit_candidate_universe()
    _require(payload.get("schema_version") == 1, "metric-v1 schema drifted")
    _require(payload.get("id") == EXPECTED_ID, "metric-v1 id drifted")
    _require(
        payload.get("status") == "frozen_before_any_t0_candidate_score",
        "metric-v1 freeze status drifted",
    )
    _require(payload.get("frozen_on") == "2026-08-13", "metric-v1 freeze date drifted")
    _require(
        payload.get("protocol")
        == {
            "path": "../autonomous-prospective-v1.json",
            "id": "autonomous-prospective-pubmed-link-emergence-v1",
        },
        "metric-v1 protocol identity drifted",
    )

    inputs = payload.get("sealed_inputs")
    _require(isinstance(inputs, dict), "metric-v1 sealed inputs missing")
    _require(
        inputs.get("t0_manifest")
        == {
            "path": "t0-2026.json",
            "canonical_json_sha256": sealed.sha256,
        },
        "metric-v1 T0 identity drifted",
    )
    _require(
        inputs.get("candidate_universe")
        == {
            "path": "t0-candidate-universe-v1.json",
            "canonical_json_sha256": universe.sha256,
            "candidate_pair_count": universe.candidate_pair_count,
        },
        "metric-v1 candidate-universe identity drifted",
    )
    _anchored_file(
        inputs.get("formula_source"),
        expected_path="../../pipeline/benchmark/autonomous_metric_v1_formula.py",
        name="formula source",
    )
    _anchored_file(
        inputs.get("dependency_lock"),
        expected_path="metric-v1-dependencies.lock.json",
        name="dependency lock",
    )
    _anchored_file(
        inputs.get("design_evidence"),
        expected_path="../../plans/reports/research-260813-autonomous-mesh-link-prediction.md",
        name="design evidence",
    )

    _require(
        payload.get("graph_backbone")
        == {
            "nodes": f"all {universe.descriptor_count} descriptors in the sealed descriptor table",
            "source_rows": "every globally distinct positive T0 descriptor-pair row",
            "undirected": True,
            "weighted": False,
            "edge_rule": "include (u,v) exactly when c_uv * N > support_u * support_v",
            "edge_rule_operands": {
                "c_uv": "exact direct T0 co-index count",
                "N": sealed.pubmed_record_count,
                "support_u": "exact T0 endpoint support",
                "support_v": "exact T0 endpoint support",
            },
            "arithmetic": "non-negative integer products evaluated in at least 128 unsigned bits; equality is excluded",
            "additional_count_threshold": 0,
            "self_edges_allowed": False,
            "parallel_edges_allowed": False,
            "edge_weights_used_by_metric": False,
        },
        "metric-v1 backbone rule drifted",
    )
    _require(
        payload.get("primary_formula")
        == {
            "name": "adamic_adar_q48",
            "common_neighbor_set": "the exact intersection of the sorted unweighted backbone neighbors of candidate endpoints u and v",
            "degree": "unweighted backbone degree",
            "scale": Q48_SCALE,
            "decimal_precision": DECIMAL_PRECISION,
            "decimal_rounding": "ROUND_HALF_EVEN",
            "per_neighbor_weight": "floor(2^48 / Decimal(degree).ln()) after ln and division at precision 80",
            "score": "checked uint64 sum of per-neighbor weights; an empty intersection scores zero",
            "missing_nonfinite_or_overflow_action": "abstain_without_prediction_seal",
        },
        "metric-v1 primary formula drifted",
    )
    baselines = payload.get("frozen_baselines")
    _require(
        isinstance(baselines, dict)
        and set(baselines)
        == {
            "prevalence",
            "common_neighbors",
            "resource_allocation_q48",
            "jaccard",
            "preferential_attachment",
        }
        and baselines["resource_allocation_q48"].get("scale") == Q48_SCALE,
        "metric-v1 baseline set drifted",
    )
    total_order = payload.get("total_order")
    _require(
        isinstance(total_order, dict)
        and total_order.get("primary")
        == [
            "adamic_adar_q48 descending",
            f"splitmix64(pair_key XOR 0x{TIE_SALT_U64:016x}) ascending",
            "pair_key ascending",
        ]
        and total_order.get("future_outcomes_or_descriptor_labels_used") is False,
        "metric-v1 total order drifted",
    )
    execution = payload.get("exhaustive_execution")
    _require(
        isinstance(execution, dict)
        and execution.get("sampling_allowed") is False
        and execution.get("required_candidate_rows") == universe.candidate_pair_count
        and execution.get("one_primary_score_per_candidate") is True
        and execution.get("one_baseline_score_tuple_per_candidate") is True
        and execution.get("maximum_resident_working_set_bytes") == 2 * 1024**3
        and execution.get("minimum_free_bytes_before_execution") == 20 * 1024**3
        and "D:\\lacuna-storage" in execution.get("large_artifact_volume", "")
        and execution.get("missing_duplicate_or_extra_candidate_action")
        == "abstain_without_prediction_seal",
        "metric-v1 exhaustive execution contract drifted",
    )
    artifacts = payload.get("artifact_contract")
    _require(
        isinstance(artifacts, dict)
        and set(artifacts)
        == {
            "degree_weights",
            "backbone_offsets",
            "backbone_neighbors",
            "candidate_scores",
            "primary_order",
            "prediction_manifest",
        }
        and artifacts["candidate_scores"].get("rows") == universe.candidate_pair_count
        and artifacts["candidate_scores"].get("row_bytes") == 48
        and artifacts["primary_order"].get("rows") == universe.candidate_pair_count,
        "metric-v1 artifact contract drifted",
    )
    policy = payload.get("prediction_seal_policy")
    _require(
        isinstance(policy, dict)
        and policy.get("score_artifacts_written_to_repository") is False
        and policy.get("final_manifest_written_once") is True
        and policy.get("overwrite_or_revision_allowed") is False
        and policy.get("llm_or_human_scoring_ranking_filtering_or_labels_allowed") is False,
        "metric-v1 prediction-seal policy drifted",
    )
    claim = payload.get("scientific_claim_boundary", "")
    for phrase in (
        "unvalidated",
        "future direct PubMed/MeSH database-link emergence only",
        "not a score result",
        "not a",
        "validated gap",
        "absent knowledge",
    ):
        _require(phrase in claim, f"metric-v1 claim boundary omits {phrase}")
    _require(payload.get("readiness_contribution") == 0, "metric-v1 claims readiness")

    # Small immutable vectors make Decimal and permutation semantics executable.
    _require(positive_association_edge(2, 100, 10, 19), "edge reference vector drifted")
    _require(not positive_association_edge(2, 100, 10, 20), "edge equality vector drifted")
    _require(adamic_adar_weight_q48(2) == 406082553034799, "AA weight vector drifted")
    _require(adamic_adar_weight_q48(10) == 122243029179284, "AA weight vector drifted")
    _require(resource_allocation_weight_q48(2) == 140737488355328, "RA vector drifted")
    _require(splitmix64(0) == 0xE220A8397B1DCDAF, "SplitMix64 vector drifted")
    _require(tie_key(0) == 0x052E07DBA1DC4264, "tie-key vector drifted")

    return AutonomousMetricV1Audit(
        metric_id=payload["id"],
        sha256=sha256_payload(payload),
        status=payload["status"],
        primary_formula=payload["primary_formula"]["name"],
        candidate_pair_count=universe.candidate_pair_count,
        readiness_contribution=0,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    audit = audit_autonomous_metric_v1()
    print("autonomous metric v1: structurally valid and frozen before scoring")
    print(f"canonical JSON SHA-256: {audit.sha256}")
    print(f"primary formula: {audit.primary_formula}")
    print(f"required candidate scores: {audit.candidate_pair_count}")
    print("readiness contribution: 0 (the formula contract is not a prediction or outcome result)")


if __name__ == "__main__":
    main()
