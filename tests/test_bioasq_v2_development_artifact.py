from __future__ import annotations

import json

import pytest

from pipeline.benchmark.validate_bioasq_v2_development import (
    DEVELOPMENT_PATH,
    PUBLISHED_GRAPH_MANIFEST_PATH,
    BioasqV2DevelopmentError,
    audit_bioasq_v2_development,
    audit_bioasq_v2_graph_manifest,
)


def _write_output(tmp_path, payload):
    path = tmp_path / "bioasq-v2-development.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _payload():
    return json.loads(DEVELOPMENT_PATH.read_text(encoding="utf-8"))


def test_committed_development_output_is_scoped_and_adds_zero_readiness():
    audit = audit_bioasq_v2_development()

    assert audit.status == "development_metric_output_initial_formula"
    assert audit.case_count == 11
    assert audit.heldout_case_count_computed == 0
    assert audit.readiness_contribution == 0


def test_published_case_blind_graph_manifest_is_traceable_without_local_cache():
    manifest = audit_bioasq_v2_graph_manifest()

    assert manifest["case_identities_or_labels_stored"] is False
    assert manifest["metric_outputs_materialized"] is False
    assert manifest["edge_headers"]["2011"]["edge_count"] == 30_875_964
    assert manifest["edge_headers"]["2012"]["edge_count"] == 31_895_136


def test_published_graph_manifest_code_identity_is_load_bearing(tmp_path):
    payload = json.loads(PUBLISHED_GRAPH_MANIFEST_PATH.read_text(encoding="utf-8"))
    payload["native_rank_screener_source"]["sha256"] = "0" * 64
    path = tmp_path / "graph-manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(BioasqV2DevelopmentError, match="code provenance"):
        audit_bioasq_v2_graph_manifest(path)


def test_development_output_cannot_claim_heldout_execution(tmp_path):
    payload = _payload()
    payload["execution_isolation"]["heldout_case_count_computed"] = 1

    with pytest.raises(BioasqV2DevelopmentError, match="execution isolation"):
        audit_bioasq_v2_development(_write_output(tmp_path, payload))


def test_development_population_is_load_bearing(tmp_path):
    payload = _payload()
    payload["cases"][0]["id"] = "substituted-case"

    with pytest.raises(BioasqV2DevelopmentError, match="population or order"):
        audit_bioasq_v2_development(_write_output(tmp_path, payload))


def test_source_counts_are_load_bearing(tmp_path):
    payload = _payload()
    payload["cases"][0]["support_runs"][0]["direct_ac_article_count"] += 1

    with pytest.raises(BioasqV2DevelopmentError, match="source support or direct"):
        audit_bioasq_v2_development(_write_output(tmp_path, payload))


def test_worst_tie_rank_fraction_is_load_bearing(tmp_path):
    payload = _payload()
    payload["cases"][0]["support_runs"][0]["target_rank_fraction"] = "0.5"

    with pytest.raises(BioasqV2DevelopmentError, match="rank fraction drifted"):
        audit_bioasq_v2_development(_write_output(tmp_path, payload))


def test_persisted_score_quantum_is_load_bearing(tmp_path):
    payload = _payload()
    payload["cases"][0]["support_runs"][0]["target_persisted_score"] = "1.0"

    with pytest.raises(BioasqV2DevelopmentError, match="score quantum"):
        audit_bioasq_v2_development(_write_output(tmp_path, payload))


def test_development_summary_must_recompute_from_cases(tmp_path):
    payload = _payload()
    payload["development_summary"]["10"]["source_labeled_positive"][
        "top_5_percent_count"
    ] += 1

    with pytest.raises(BioasqV2DevelopmentError, match="summary drifted"):
        audit_bioasq_v2_development(_write_output(tmp_path, payload))


def test_support_five_score_and_bridge_invariance_is_load_bearing(tmp_path):
    payload = _payload()
    payload["cases"][0]["support_runs"][1]["target_persisted_score"] = (
        "1.151138480117360"
    )

    with pytest.raises(BioasqV2DevelopmentError, match="support-5 score or bridge"):
        audit_bioasq_v2_development(_write_output(tmp_path, payload))


def test_readiness_cannot_be_promoted_by_development_output(tmp_path):
    payload = _payload()
    payload["readiness_contribution"] = 1

    with pytest.raises(BioasqV2DevelopmentError, match="readiness contribution"):
        audit_bioasq_v2_development(_write_output(tmp_path, payload))
