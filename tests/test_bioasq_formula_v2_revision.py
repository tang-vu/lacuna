from __future__ import annotations

import json

import pytest

from pipeline.benchmark.validate_bioasq_formula_v2_revision import (
    REVISION_FORMULA_PATH,
    BioasqFormulaV2RevisionError,
    audit_bioasq_formula_v2_revision,
)


def _write_revision(tmp_path, payload):
    path = tmp_path / "bioasq-formula-v2-revision-1.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _payload():
    return json.loads(REVISION_FORMULA_PATH.read_text(encoding="utf-8"))


def test_single_revision_is_frozen_before_revision_output_and_adds_zero_readiness():
    audit = audit_bioasq_formula_v2_revision()

    assert audit.status == (
        "frozen_single_revision_after_initial_development_before_revision_output"
    )
    assert audit.formula_class == (
        "article_level_mesh_direct_penalized_jaccard_sum_of_path_minima"
    )
    assert audit.revision_number == 1
    assert audit.budget_remaining == 0
    assert audit.direct_penalty == "D(A,C) = 1 + n_AC"
    assert audit.development_positive_required == 2
    assert audit.development_hard_top5_allowed == 0
    assert audit.development_distant_below_median_required == 4
    assert audit.heldout_output_seen is False
    assert audit.readiness_contribution == 0


def test_revision_must_precede_its_development_output(tmp_path):
    payload = _payload()
    payload["freeze_timing"][
        "revision_formula_development_scores_ranks_or_bridges_seen"
    ] = True

    with pytest.raises(BioasqFormulaV2RevisionError, match="not frozen before"):
        audit_bioasq_formula_v2_revision(_write_revision(tmp_path, payload))


def test_revision_must_precede_heldout_output(tmp_path):
    payload = _payload()
    payload["freeze_timing"][
        "bioasq_heldout_scores_ranks_orderings_or_bridges_seen"
    ] = True

    with pytest.raises(BioasqFormulaV2RevisionError, match="not frozen before"):
        audit_bioasq_formula_v2_revision(_write_revision(tmp_path, payload))


def test_revision_consumes_the_only_budget(tmp_path):
    payload = _payload()
    payload["revision_accounting"]["budget_remaining"] = 1

    with pytest.raises(BioasqFormulaV2RevisionError, match="budget or component"):
        audit_bioasq_formula_v2_revision(_write_revision(tmp_path, payload))


def test_direct_penalty_formula_is_load_bearing(tmp_path):
    payload = _payload()
    payload["score_contract"]["direct_penalty"] = "D(A,C) = exp(n_AC)"

    with pytest.raises(BioasqFormulaV2RevisionError, match="score drifted"):
        audit_bioasq_formula_v2_revision(_write_revision(tmp_path, payload))


def test_revision_keeps_the_initial_graph_and_jaccard_path_score(tmp_path):
    payload = _payload()
    payload["graph_contract"]["inherit_exactly_from_initial_formula"] = False

    with pytest.raises(BioasqFormulaV2RevisionError, match="graph contract drifted"):
        audit_bioasq_formula_v2_revision(_write_revision(tmp_path, payload))


def test_revision_decimal_division_order_is_load_bearing(tmp_path):
    payload = _payload()
    payload["numeric_reproducibility"]["direct_penalty_evaluation"] = (
        "Divide every path before summation."
    )

    with pytest.raises(BioasqFormulaV2RevisionError, match="numeric contract drifted"):
        audit_bioasq_formula_v2_revision(_write_revision(tmp_path, payload))


def test_revision_development_gate_cannot_be_relaxed(tmp_path):
    payload = _payload()
    payload["pre_registered_revision_development_gate"]["positive_requirement"] = (
        "At least 1 of 3 positives ranks in the top 5 percent."
    )

    with pytest.raises(BioasqFormulaV2RevisionError, match="decision gate drifted"):
        audit_bioasq_formula_v2_revision(_write_revision(tmp_path, payload))


def test_revision_cannot_use_case_kind_or_ontology_features(tmp_path):
    payload = _payload()
    payload["feature_exclusions"].remove(
        "MeSH tree distance, parent, child, or sibling relationship"
    )

    with pytest.raises(BioasqFormulaV2RevisionError, match="feature exclusions drifted"):
        audit_bioasq_formula_v2_revision(_write_revision(tmp_path, payload))


def test_revision_does_not_contain_a_heldout_case_identity(tmp_path):
    payload = _payload()
    payload["revision_rationale"]["construct"] += (
        " generated-hard-2012-04-d019956-d019960"
    )

    with pytest.raises(BioasqFormulaV2RevisionError, match="held-out case identity"):
        audit_bioasq_formula_v2_revision(_write_revision(tmp_path, payload))


def test_revision_cannot_promote_readiness(tmp_path):
    payload = _payload()
    payload["claim_boundary"]["readiness_contribution"] = 1

    with pytest.raises(BioasqFormulaV2RevisionError, match="claim boundary drifted"):
        audit_bioasq_formula_v2_revision(_write_revision(tmp_path, payload))
