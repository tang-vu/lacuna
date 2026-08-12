from __future__ import annotations

import json

import pytest

from pipeline.benchmark.validate_bioasq_formula_v2 import (
    FORMULA_PATH,
    BioasqFormulaV2ContractError,
    audit_bioasq_formula_v2,
)


def _write_formula(tmp_path, payload):
    path = tmp_path / "bioasq-formula-v2-initial.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_initial_formula_is_frozen_before_output_and_adds_zero_readiness():
    audit = audit_bioasq_formula_v2()

    assert audit.status == "frozen_initial_before_development_metric_output"
    assert audit.formula_class == "article_level_mesh_jaccard_sum_of_path_minima"
    assert audit.edge_weight == "article_jaccard"
    assert audit.path_aggregation == "minimum"
    assert audit.candidate_accumulation == "sum"
    assert audit.threshold_supports == (10, 5)
    assert audit.decimal_precision == 40
    assert audit.revision_budget == 1
    assert audit.readiness_contribution == 0


def test_formula_must_precede_development_output(tmp_path):
    payload = json.loads(FORMULA_PATH.read_text(encoding="utf-8"))
    payload["freeze_timing"]["bioasq_development_metric_outputs_seen"] = True

    with pytest.raises(BioasqFormulaV2ContractError, match="not frozen before"):
        audit_bioasq_formula_v2(_write_formula(tmp_path, payload))


def test_formula_must_precede_heldout_output(tmp_path):
    payload = json.loads(FORMULA_PATH.read_text(encoding="utf-8"))
    payload["freeze_timing"]["bioasq_heldout_metric_outputs_seen"] = True

    with pytest.raises(BioasqFormulaV2ContractError, match="not frozen before"):
        audit_bioasq_formula_v2(_write_formula(tmp_path, payload))


def test_formula_retains_direct_ac_articles_and_candidates(tmp_path):
    payload = json.loads(FORMULA_PATH.read_text(encoding="utf-8"))
    payload["graph_contract"]["candidate_set"] = "Exclude every direct neighbour of A."

    with pytest.raises(BioasqFormulaV2ContractError, match="graph contract drifted"):
        audit_bioasq_formula_v2(_write_formula(tmp_path, payload))


def test_jaccard_edge_formula_is_load_bearing(tmp_path):
    payload = json.loads(FORMULA_PATH.read_text(encoding="utf-8"))
    payload["edge_weight"]["formula"] = "J(x,y) = n_xy"

    with pytest.raises(BioasqFormulaV2ContractError, match="edge weight drifted"):
        audit_bioasq_formula_v2(_write_formula(tmp_path, payload))


def test_sum_of_path_minima_is_load_bearing(tmp_path):
    payload = json.loads(FORMULA_PATH.read_text(encoding="utf-8"))
    payload["path_and_candidate_score"]["candidate_formula"] = (
        "S(A,C) = max(P(A,B,C) for B in bridge_set(A,C))"
    )

    with pytest.raises(BioasqFormulaV2ContractError, match="accumulation rule drifted"):
        audit_bioasq_formula_v2(_write_formula(tmp_path, payload))


def test_decimal_precision_and_quantum_are_load_bearing(tmp_path):
    payload = json.loads(FORMULA_PATH.read_text(encoding="utf-8"))
    payload["numeric_reproducibility"]["decimal_context_precision"] = 16

    with pytest.raises(BioasqFormulaV2ContractError, match="numeric contract drifted"):
        audit_bioasq_formula_v2(_write_formula(tmp_path, payload))


def test_formula_cannot_use_known_case_or_ontology_features(tmp_path):
    payload = json.loads(FORMULA_PATH.read_text(encoding="utf-8"))
    payload["feature_exclusions"].remove(
        "MeSH tree distance, parent, child, or sibling relationship"
    )

    with pytest.raises(BioasqFormulaV2ContractError, match="feature exclusions drifted"):
        audit_bioasq_formula_v2(_write_formula(tmp_path, payload))


def test_initial_contract_cannot_preview_heldout_outputs(tmp_path):
    payload = json.loads(FORMULA_PATH.read_text(encoding="utf-8"))
    payload["execution_isolation"]["heldout_prohibition"] = "Held-out preview is allowed."

    with pytest.raises(BioasqFormulaV2ContractError, match="execution isolation"):
        audit_bioasq_formula_v2(_write_formula(tmp_path, payload))
