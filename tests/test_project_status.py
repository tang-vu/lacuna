from __future__ import annotations

import json

from pipeline.export.build_project_status import (
    PROJECT_STATUS_PATH,
    build_project_status,
)
from pipeline.export.verify_artifacts import verify_project_status


def test_project_status_exposes_validator_results_without_claiming_readiness():
    status = build_project_status()

    assert status["schema_version"] == 14
    assert status["status"] == "not_ready"
    assert status["historical_sources"] == {
        "ready": False,
        "required_years": [2007, 2011, 2012, 2013],
        "inventory_metadata": {
            "available": 4,
            "required": 4,
            "years": [2007, 2011, 2012, 2013],
            "scope": "official inventory metadata only",
        },
        "raw_record_releases": {
            "pinned": 0,
            "required": 4,
            "years": [],
        },
        "preservation_metadata": {
            "available": 4,
            "required": 4,
            "years": [2007, 2011, 2012, 2013],
            "scope": "preserved repository directory metadata only",
        },
        "statuses": {
            "current_records": "available_unsuitable",
            "historical_records": "unavailable",
            "historical_vocabulary": "available_pinned",
        },
        "provider_confirmation": {
            "provider": "NLM Support",
            "received_on": "2026-08-10",
            "scope": "previous annual PubMed baseline availability",
        },
        "readiness_blockers": [
            "historical_records: unavailable (must be available_pinned)"
        ],
    }
    assert status["source_alternatives"]["status"] == "no_equivalent_replacement_pinned"
    assert status["source_alternatives"]["recommended_id"] == "bioasq-2013-task-a"
    assert status["source_alternatives"]["counts"] == {
        "audited_scope_mismatch": 1,
        "engineering_only": 1,
        "rejected_for_historical_gate": 1,
    }
    assert status["source_alternatives"]["readiness_contribution"] == 0
    snapshot = status["source_alternatives"]["bioasq_snapshot"]
    assert snapshot["status"] == "measured_unmatched_input"
    assert snapshot["readiness_contribution"] == 0
    assert snapshot["measured"]["article_count"] == 10_876_004
    assert snapshot["measured"]["noncanonical_year_count"] == 751_238
    assert snapshot["measured"]["unparseable_year_count"] == 0
    assert snapshot["declared_comparison"] == {
        "article_count": 10_876_004,
        "mesh_label_count": 26_563,
        "average_mesh_labels_per_article": 12.55,
        "publication_scope": "MEDLINE articles published after 1949",
        "articles_before_declared_publication_scope": 280,
        "articles_after_snapshot_version": 0,
        "matches_published_aggregate_counts": True,
        "matches_published_publication_scope": False,
        "passes_declared_snapshot_gate": False,
    }
    successor = status["source_alternatives"]["bioasq_successor_protocol"]
    assert successor["status"] == "frozen_after_source_audit_before_semantics_selection"
    assert successor["sampling"]["total_sample_size"] == 448
    assert successor["decision_rule"]["readiness_contribution"] == 0
    semantics = status["source_alternatives"]["bioasq_semantics_audit"]
    assert semantics["status"] == "bounded_corpus_semantics_audit"
    assert semantics["classification"] == "sample_consistent_with_all_assigned_descriptors"
    assert semantics["readiness_contribution"] == 0
    assert semantics["maintained_current_pubmed_comparison"]["records_returned"] == 448
    assert semantics["maintained_current_pubmed_comparison"]["overall"] == {
        "records": 448,
        "bioasq_assignments": 5_296,
        "matched_current_all_descriptor_assignments": 5_201,
        "matched_current_major_topic_assignments": 455,
        "all_descriptor_assignment_match_fraction": 0.98206193,
        "major_topic_assignment_match_fraction": 0.0859139,
    }
    assert semantics["decision_checks"]["passed"] is True
    pilot = status["source_alternatives"]["bioasq_pilot_protocol"]
    assert pilot["status"] == "frozen_before_bioasq_pilot_metric"
    assert pilot["case_population"]["total_cases"] == 21
    assert pilot["case_population"]["split_counts"] == {
        "development": 11,
        "heldout": 10,
    }
    assert pilot["freeze_timing"]["case_endpoint_support_counts_seen"] is False
    assert pilot["freeze_timing"]["bioasq_pilot_scores_or_ranks_seen"] is False
    assert pilot["claim_boundary"]["readiness_contribution"] == 0
    compatibility = status["source_alternatives"]["bioasq_pilot_compatibility_audit"]
    assert compatibility["status"] == (
        "primary_source_compatible_but_sensitivity_20_unevaluable"
    )
    assert compatibility["decision"]["all_21_cases_primary_source_compatible"] is True
    assert compatibility["decision"]["heldout_sensitivity_evaluable"] == {
        "5": True,
        "10": True,
        "20": False,
    }
    assert compatibility["decision"]["heldout_sensitivity_blockers"] == {
        "5": [],
        "10": [],
        "20": ["generated-hard-2012-04-d019956-d019960"],
    }
    assert compatibility["decision"]["frozen_heldout_rule_can_still_pass"] is False
    assert compatibility["decision"]["metric_work_authorized_by_this_audit"] is False
    assert compatibility["readiness_contribution"] == 0
    pilot_v2 = status["source_alternatives"]["bioasq_pilot_successor_protocol"]
    assert pilot_v2["status"] == "frozen_after_source_compatibility_before_metric_formula"
    assert pilot_v2["case_population"]["total_cases"] == 21
    assert pilot_v2["case_population"]["split_counts"] == {
        "development": 11,
        "heldout": 10,
    }
    assert pilot_v2["freeze_timing"]["case_endpoint_support_counts_seen"] is True
    assert pilot_v2["freeze_timing"]["bioasq_pilot_metric_formula_seen"] is False
    assert pilot_v2["source_compatibility"]["primary_minimum_support_articles"] == 10
    assert pilot_v2["source_compatibility"]["support_sensitivity_articles"] == [5]
    assert pilot_v2["claim_boundary"]["readiness_contribution"] == 0
    assert len(status["source_alternatives"]["entries"]) == 3
    assert status["candidate_intake"]["counts"] == {
        "accepted": 2,
        "proposed": 10,
        "rejected": 2,
    }
    assert status["candidate_intake"]["accepted_benchmark_links"] == 2
    assert status["candidate_intake"]["readiness_contribution"] == (
        "accepted benchmark links only"
    )
    assert status["candidate_intake"]["policy"] == {
        "metric_blind": True,
        "accepted_only_enters_benchmark": True,
        "acceptance_requires_independent_replication": True,
    }
    entries = status["candidate_intake"]["entries"]
    assert len(entries) == 14
    assert {
        entry["id"] for entry in entries if entry["status"] == "proposed"
    } == {
        "swanson-somatomedin-c-arginine",
        "smalheiser-magnesium-neurologic-disease",
        "smalheiser-alzheimer-indomethacin",
        "smalheiser-alzheimer-estrogen",
        "smalheiser-schizophrenia-ipla2",
        "lion-nfkb-adenoma",
        "lion-notch1-cebpb",
        "lion-il17-mkp1",
        "lion-nrf2-pancreatic-cancer",
        "lion-cxcl12-thyroid-cancer",
    }
    assert all(
        entry["open_questions"]
        for entry in entries
        if entry["status"] == "proposed"
    )
    negative_queue = status["negative_candidate_queue"]
    assert negative_queue["counts"] == {
        "hard_negative": 8,
        "distant_negative": 8,
    }
    assert negative_queue["heldout_counts"] == {
        "hard_negative": 4,
        "distant_negative": 4,
    }
    assert negative_queue["readiness_contribution"] == 0
    assert negative_queue["protocol_status"] == "frozen_before_v3_metric"
    assert len(negative_queue["entries"]) == 16
    assert all(entry["status"] == "proposed" for entry in negative_queue["entries"])
    assert "generated review aid" in negative_queue["context_warning"]
    assert all(entry["review_context"]["concepts"] for entry in negative_queue["entries"])
    assert all(
        entry["review_context"].get("shared_parent")
        for entry in negative_queue["entries"]
        if entry["kind"] == "hard_negative"
    )
    assert status["benchmark"]["ready"] is False
    assert status["benchmark"]["requirements"] == {
        "minimum_per_kind": 8,
        "minimum_heldout_per_kind": 4,
        "minimum_period_appropriate_heldout_cutoffs": 2,
    }
    assert status["benchmark"]["counts"] == {
        "positive": 2,
        "hard_negative": 0,
        "distant_negative": 0,
    }
    assert status["benchmark"]["heldout_counts"] == {
        "positive": 0,
        "hard_negative": 0,
        "distant_negative": 0,
    }
    assert status["benchmark"]["mapping_counts"]["maintained_current"] == 4
    assert status["benchmark"]["mapping_counts"]["period_appropriate"] == 0
    assert status["benchmark"]["readiness_blockers"]


def test_committed_project_status_matches_its_pinned_contract_inputs():
    committed = json.loads(PROJECT_STATUS_PATH.read_text(encoding="utf-8"))

    assert committed == build_project_status()
    assert verify_project_status() == committed
    assert set(committed["inputs"]) == {
        "historical_sources",
        "source_alternatives",
        "bioasq_snapshot_audit",
        "bioasq_semantics_protocol",
        "bioasq_successor_semantics_protocol",
        "bioasq_semantics_audit",
        "bioasq_pilot_protocol",
        "bioasq_pilot_compatibility_audit",
        "bioasq_pilot_successor_protocol",
        "historical_inventories",
        "mbr_preservation_capture",
        "candidate_intake",
        "negative_selection_protocol",
        "negative_candidate_queue",
        "negative_review_context",
        "benchmark",
    }
    for source in committed["inputs"].values():
        assert source["canonicalisation"] == "canonical-json-v1"
        assert len(source["sha256"]) == 64
