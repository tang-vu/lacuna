from __future__ import annotations

import json

import pytest

from pipeline.benchmark.autonomous_metric_v1_formula import (
    AutonomousMetricV1FormulaError,
    adamic_adar_weight_q48,
    descending_integer_rank_key,
    jaccard_denominator,
    local_scores,
    positive_association_edge,
    prevalence_score,
    resource_allocation_weight_q48,
    splitmix64,
    tie_key,
)
from pipeline.benchmark.validate_autonomous_metric_v1 import (
    CONTRACT_PATH,
    AutonomousMetricV1ContractError,
    audit_autonomous_metric_v1,
)


def _mutated(tmp_path, mutate):
    payload = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    mutate(payload)
    path = tmp_path / "metric-v1.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_metric_contract_is_frozen_exhaustive_and_zero_readiness():
    audit = audit_autonomous_metric_v1()

    assert audit.status == "frozen_before_any_t0_candidate_score"
    assert audit.primary_formula == "adamic_adar_q48"
    assert audit.candidate_pair_count == 7_310_895
    assert audit.readiness_contribution == 0


def test_formula_reference_vectors_and_exact_edge_boundary():
    assert positive_association_edge(2, 100, 10, 19)
    assert not positive_association_edge(2, 100, 10, 20)
    assert not positive_association_edge(0, 100, 10, 19)
    assert adamic_adar_weight_q48(2) == 406_082_553_034_799
    assert adamic_adar_weight_q48(10) == 122_243_029_179_284
    assert resource_allocation_weight_q48(2) == 140_737_488_355_328
    assert splitmix64(0) == 0xE220A8397B1DCDAF
    assert tie_key(0) == 0x052E07DBA1DC4264


def test_formula_aggregates_and_orders_without_floats_or_labels():
    scores = local_scores([2, 10])
    assert scores.adamic_adar_q48 == 528_325_582_214_083
    assert scores.resource_allocation_q48 == 168_884_986_026_393
    assert scores.common_neighbors == 2
    assert jaccard_denominator(3, 4, 2) == 5
    assert jaccard_denominator(0, 0, 0) == 1
    assert prevalence_score(10, 20) == 200
    assert descending_integer_rank_key(9, 3)[0] < descending_integer_rank_key(8, 2)[0]


def test_formula_rejects_invalid_degree_or_integer_domain():
    with pytest.raises(AutonomousMetricV1FormulaError):
        adamic_adar_weight_q48(1)
    with pytest.raises(AutonomousMetricV1FormulaError):
        positive_association_edge(-1, 100, 10, 20)
    with pytest.raises(AutonomousMetricV1FormulaError):
        jaccard_denominator(1, 1, 2)


def test_metric_contract_rejects_formula_backbone_or_readiness_drift(tmp_path):
    formula_path = _mutated(
        tmp_path,
        lambda payload: payload["primary_formula"].update(scale=1),
    )
    with pytest.raises(AutonomousMetricV1ContractError, match="primary formula"):
        audit_autonomous_metric_v1(formula_path)

    edge_path = _mutated(
        tmp_path,
        lambda payload: payload["graph_backbone"].update(additional_count_threshold=1),
    )
    with pytest.raises(AutonomousMetricV1ContractError, match="backbone rule"):
        audit_autonomous_metric_v1(edge_path)

    readiness_path = _mutated(tmp_path, lambda payload: payload.update(readiness_contribution=1))
    with pytest.raises(AutonomousMetricV1ContractError, match="readiness"):
        audit_autonomous_metric_v1(readiness_path)
