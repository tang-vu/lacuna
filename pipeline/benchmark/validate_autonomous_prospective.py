"""Validate the no-human prospective link-emergence protocol and current state.

This is a protocol validator, not a metric result. T0 sources, metric, and predictions are sealed;
the track remains not ready while its future outcome window is absent.

Run:
    python -m pipeline.benchmark.validate_autonomous_prospective
    python -m pipeline.benchmark.validate_autonomous_prospective --require-ready
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from pipeline.benchmark.autonomous_t0 import (
    REMOTE_INVENTORY_PATH,
    SEALED_T0_PATH,
    audit_remote_inventory,
    audit_sealed_t0,
)
from pipeline.benchmark.validate_autonomous_candidate_index import (
    CONTRACT_PATH as CANDIDATE_INDEX_CONTRACT_PATH,
    audit_candidate_index_contract,
)
from pipeline.benchmark.validate_autonomous_candidate_universe import (
    MANIFEST_PATH as CANDIDATE_UNIVERSE_PATH,
    audit_candidate_universe,
)
from pipeline.benchmark.validate_autonomous_metric_v1 import (
    CONTRACT_PATH as METRIC_V1_PATH,
    audit_autonomous_metric_v1,
)
from pipeline.benchmark.validate_autonomous_predictions_v1 import (
    MANIFEST_PATH as PREDICTIONS_V1_PATH,
    audit_predictions_v1,
)
from pipeline.paths import REPO_ROOT

PROTOCOL_PATH = REPO_ROOT / "benchmarks" / "autonomous-prospective-v1.json"
EXPECTED_ID = "autonomous-prospective-pubmed-link-emergence-v1"
EXPECTED_STATUS = "frozen_before_t0_source_acquisition_and_metric"
EXPECTED_BLOCKERS = (
    "the three-release prospective outcome window has not matured",
)


class AutonomousProspectiveContractError(ValueError):
    pass


@dataclass(frozen=True)
class AutonomousProspectiveAudit:
    protocol_id: str
    state: str
    verdict: str
    human_dependency_count: int
    blockers: tuple[str, ...]
    readiness_contribution: int

    @property
    def ready(self) -> bool:
        return self.verdict == "passed" and not self.blockers


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AutonomousProspectiveContractError(message)


def _substantive_list(value: object, context: str, minimum: int) -> list:
    _require(isinstance(value, list) and len(value) >= minimum, f"{context}: list too short")
    _require(all(isinstance(item, str) and item.strip() for item in value), f"{context}: invalid text")
    return value


def audit_autonomous_prospective(path: Path = PROTOCOL_PATH) -> AutonomousProspectiveAudit:
    payload = json.loads(path.read_text(encoding="utf-8"))
    _require(payload.get("schema_version") == 1, "unsupported autonomous protocol schema")
    _require(payload.get("id") == EXPECTED_ID, "autonomous protocol id drifted")
    _require(payload.get("status") == EXPECTED_STATUS, "autonomous protocol status drifted")
    _require(payload.get("frozen_on") == "2026-08-12", "freeze date drifted")
    _require(payload.get("active_track") is True, "autonomous track must remain active")
    _require(payload.get("human_dependencies") == [], "active track cannot depend on humans")

    legacy = payload.get("legacy_tracks")
    _require(isinstance(legacy, dict), "legacy track boundaries are missing")
    _require(
        set(legacy) == {"historical_metric_v3", "bioasq_v2", "human_negative_review"}
        and "not_a_blocker" in legacy["historical_metric_v3"]
        and "terminal_development_failure" in legacy["bioasq_v2"]
        and "superseded_as_an_active_dependency" in legacy["human_negative_review"],
        "legacy track boundaries drifted",
    )

    boundary = payload.get("scientific_claim_boundary")
    _require(isinstance(boundary, dict), "scientific claim boundary missing")
    _require(
        boundary.get("measured_target")
        == "future_direct_mesh_link_emergence_in_complete_pubmed_baselines",
        "measured target drifted",
    )
    not_measured = _substantive_list(boundary.get("not_measured"), "not-measured claims", 5)
    not_measured_text = " ".join(not_measured).lower()
    for phrase in ("importance", "causal", "non-academic", "historical", "outside biomedicine"):
        _require(phrase in not_measured_text, f"claim boundary omits {phrase}")
    _require(
        boundary.get("passing_label")
        == "validated_for_prospective_pubmed_link_emergence_ranking_only"
        and boundary.get("llm_interpretation_authorized") is False,
        "passing label or LLM boundary drifted",
    )
    forbidden_labels = _substantive_list(boundary.get("forbidden_labels"), "forbidden labels", 2)
    _require("validated knowledge gap detector" in forbidden_labels, "gap-detector overclaim guard missing")

    machine = payload.get("state_machine")
    _require(isinstance(machine, dict), "state machine missing")
    states = machine.get("states")
    _require(
        states
        == [
            "awaiting_t0_baseline",
            "awaiting_frozen_metric",
            "predictions_sealed_waiting_for_outcome",
            "awaiting_t1_baseline",
            "evaluating",
            "passed",
            "failed",
            "abstained",
        ],
        "state vocabulary drifted",
    )
    _require(
        machine.get("initial_state") == states[0]
        and machine.get("manual_override_allowed") is False
        and machine.get("failure_is_terminal_for_the_sealed_formula") is True,
        "state machine safety changed",
    )
    transitions = machine.get("transitions")
    _require(isinstance(transitions, list) and len(transitions) == 5, "state transitions drifted")
    _require(
        all(isinstance(item, dict) and bool(item.get("machine_gate")) for item in transitions),
        "every transition needs a machine gate",
    )

    sources = payload.get("source_contract")
    _require(isinstance(sources, dict), "source contract missing")
    remote_reference = sources.get("t0_remote_inventory")
    _require(isinstance(remote_reference, dict), "T0 remote inventory reference missing")
    remote_audit = audit_remote_inventory(REMOTE_INVENTORY_PATH)
    _require(
        remote_reference
        == {
            "path": "autonomous/t0-2026-remote-inventory.json",
            "sha256": remote_audit.sha256,
            "canonicalisation": "canonical-json-v1",
            "release_year": remote_audit.release_year,
            "pubmed_file_count": remote_audit.pubmed_file_count,
            "mesh_descriptor_count": remote_audit.mesh_descriptor_count,
            "evidence_scope": "remote source identities only; zero readiness until every local byte and record count is sealed",
        }
        and remote_audit.readiness_contribution == 0,
        "T0 remote inventory identity or zero-readiness boundary drifted",
    )
    sealed_reference = sources.get("t0_manifest")
    _require(isinstance(sealed_reference, dict), "sealed T0 manifest reference missing")
    sealed_audit = audit_sealed_t0(SEALED_T0_PATH, REMOTE_INVENTORY_PATH)
    _require(
        sealed_reference
        == {
            "path": "autonomous/t0-2026.json",
            "sha256": sealed_audit.sha256,
            "canonicalisation": "canonical-json-v1",
            "release_year": sealed_audit.release_year,
            "pubmed_file_count": sealed_audit.pubmed_file_count,
            "pubmed_bytes": sealed_audit.pubmed_bytes,
            "pubmed_record_count": sealed_audit.pubmed_record_count,
            "mesh_descriptor_count": sealed_audit.mesh_descriptor_count,
            "evidence_scope": "locally sealed source identity and record counts; zero metric or scientific readiness",
        }
        and sealed_audit.state == "awaiting_frozen_metric"
        and sealed_audit.readiness_contribution == 0,
        "sealed T0 manifest identity or claim boundary drifted",
    )
    _require(
        sources.get("source_failure_action") == "abstain"
        and sources.get("partial_release_action") == "abstain"
        and sources.get("api_result_pages_allowed_as_baseline") is False
        and sources.get("credentials_persisted") is False,
        "source failure or credential policy drifted",
    )
    for point, minimum_identity_fields in (("t0", 6), ("t1", 3)):
        identity = sources.get(point)
        _require(isinstance(identity, dict), f"{point} source identity missing")
        _substantive_list(
            identity.get("required_identity"),
            f"{point} source identity",
            minimum_identity_fields,
        )

    universe = payload.get("t0_candidate_universe")
    _require(isinstance(universe, dict), "candidate universe missing")
    _require(
        universe.get("minimum_endpoint_article_support") == 100
        and universe.get("minimum_independence_expected_count") == 5
        and universe.get("maximum_exact_direct_ac_count") == 0
        and universe.get("exclude_ancestor_descendant_pairs") is True
        and universe.get("exclude_shared_entry_term_pairs") is True
        and universe.get("candidate_set_hash_required") is True
        and universe.get("sampling_allowed") is False,
        "candidate universe drifted",
    )
    _substantive_list(universe.get("candidate_identity_fields"), "candidate identity", 6)
    candidate_index = audit_candidate_index_contract(CANDIDATE_INDEX_CONTRACT_PATH)
    _require(
        payload.get("t0_construction_contract")
        == {
            "path": "autonomous/t0-candidate-index-v1.json",
            "sha256": candidate_index.sha256,
            "canonicalisation": "canonical-json-v1",
            "status": candidate_index.status,
            "score_free": True,
            "readiness_contribution": 0,
        },
        "candidate-index construction contract identity drifted",
    )
    candidate_universe = audit_candidate_universe(CANDIDATE_UNIVERSE_PATH)
    _require(
        payload.get("t0_candidate_universe_artifact")
        == {
            "path": "autonomous/t0-candidate-universe-v1.json",
            "sha256": candidate_universe.sha256,
            "canonicalisation": "canonical-json-v1",
            "status": candidate_universe.status,
            "source_file_count": candidate_universe.source_file_count,
            "distinct_pmid_count": candidate_universe.distinct_pmid_count,
            "descriptor_count": candidate_universe.descriptor_count,
            "positive_pair_count": candidate_universe.positive_pair_count,
            "candidate_pair_count": candidate_universe.candidate_pair_count,
            "score_free": True,
            "readiness_contribution": 0,
        },
        "candidate-universe artifact identity drifted",
    )
    metric = audit_autonomous_metric_v1(METRIC_V1_PATH)
    metric_inputs = json.loads(METRIC_V1_PATH.read_text(encoding="utf-8"))["sealed_inputs"]
    _require(
        payload.get("metric_contract_artifact")
        == {
            "path": "autonomous/metric-v1.json",
            "sha256": metric.sha256,
            "canonicalisation": "canonical-json-v1",
            "status": metric.status,
            "primary_formula": metric.primary_formula,
            "candidate_pair_count": metric.candidate_pair_count,
            "formula_source_sha256": metric_inputs["formula_source"]["file_sha256"],
            "dependency_lock_sha256": metric_inputs["dependency_lock"]["file_sha256"],
            "readiness_contribution": 0,
        },
        "metric-v1 contract identity drifted",
    )
    predictions = audit_predictions_v1(PREDICTIONS_V1_PATH)
    _require(
        payload.get("t0_prediction_artifact")
        == {
            "path": "autonomous/t0-predictions-v1.json",
            "sha256": predictions.sha256,
            "canonicalisation": "canonical-json-v1",
            "status": predictions.status,
            "primary_formula": predictions.primary_formula,
            "backbone_edge_count": predictions.backbone_edge_count,
            "candidate_score_count": predictions.candidate_score_count,
            "nonzero_primary_score_count": predictions.nonzero_score_count,
            "overwrite_allowed": False,
            "readiness_contribution": 0,
        },
        "prediction-v1 artifact identity drifted",
    )

    seal = payload.get("prediction_seal")
    _require(isinstance(seal, dict), "prediction seal missing")
    _substantive_list(seal.get("required_before_t1"), "prediction seal", 8)
    _require(
        seal.get("missing_or_nonfinite_score_action") == "abstain"
        and seal.get("overwrite_allowed") is False
        and seal.get("formula_revision_after_seal_allowed") is False,
        "prediction seal safety drifted",
    )

    outcomes = payload.get("machine_outcomes")
    _require(isinstance(outcomes, dict), "machine outcomes missing")
    positive = outcomes.get("positive_label", {}).get("requirements", {})
    negative = outcomes.get("negative_label", {})
    censored = outcomes.get("censored_label", {})
    _require(
        "present in the complete T1 baseline but absent" in outcomes.get("observation_window", "")
        and outcomes.get("new_row_definition")
        == "a PMID plus the unordered T0 descriptor-UI pair is absent at T0 and present at T1"
        and "not evidence" in outcomes.get("pre_existing_pmid_handling", ""),
        "database-emergence observation boundary drifted",
    )
    _require(
        positive
        == {
            "minimum_distinct_new_pmids_with_both_t0_descriptor_uis": 3,
            "minimum_distinct_journals": 2,
            "minimum_distinct_publication_years": 2,
        },
        "positive outcome rule drifted",
    )
    _require(
        negative.get("name") == "no_observed_link_emergence_in_window"
        and negative.get("requirements")
        == {"distinct_new_pmids_with_both_t0_descriptor_uis": 0}
        and "not evidence" in negative.get("claim_limit", ""),
        "negative outcome claim boundary drifted",
    )
    _substantive_list(censored.get("conditions"), "censoring conditions", 4)
    _require(
        "exclude from primary" in censored.get("evaluation_action", "")
        and outcomes.get("outcome_artifact_requires_exact_pmids_and_source_rows") is True
        and outcomes.get("llm_or_manual_labels_allowed") is False,
        "censoring or no-human outcome contract drifted",
    )

    diagnostics = payload.get("automatic_structural_diagnostics")
    _require(isinstance(diagnostics, dict), "structural diagnostics missing")
    _require(
        diagnostics.get("role") == "artifact probes, not negative ground truth"
        and set(diagnostics.get("cohorts", {})) == {"ontology_adjacent", "degree_matched_distant"}
        and diagnostics.get("gate")
        == {
            "ontology_adjacent_top_1_percent_maximum": 0.01,
            "degree_matched_distant_top_5_percent_maximum": 0.05,
        }
        and diagnostics.get("failure_action") == "fail",
        "structural diagnostic boundary drifted",
    )

    evaluation = payload.get("pre_registered_evaluation")
    _require(isinstance(evaluation, dict), "evaluation gate missing")
    _require(
        evaluation.get("minimum_observed_positive_outcomes") == 200
        and evaluation.get("minimum_observed_negative_outcomes") == 20000
        and evaluation.get("underpowered_action") == "abstain",
        "power gate drifted",
    )
    _require(
        evaluation.get("primary_metrics")
        == {
            "precision_at_100_minimum": 0.25,
            "precision_at_100_lift_over_prevalence_minimum": 5,
            "average_precision_lift_over_prevalence_minimum": 3,
            "bootstrap_replicates": 10000,
            "bootstrap_seed": "lacuna-autonomous-prospective-v1",
            "precision_at_100_lift_95_percent_lower_bound_minimum": 2,
        },
        "primary metric thresholds drifted",
    )
    for field, word in (("pass_rule", "Every"), ("fail_rule", "fails"), ("abstain_rule", "insufficient")):
        _require(word in evaluation.get(field, ""), f"{field} drifted")

    outputs = payload.get("autonomous_outputs")
    _require(isinstance(outputs, dict), "autonomous output contract missing")
    _substantive_list(outputs.get("required_per_pair_trace"), "per-pair trace", 6)
    blind_spots = _substantive_list(outputs.get("blind_spots_required_in_every_release"), "blind spots", 5)
    _require(
        "non-academic knowledge" in blind_spots
        and "indigenous knowledge" in blind_spots
        and outputs.get("automatic_abstention_visible") is True,
        "coverage or abstention visibility drifted",
    )

    current = payload.get("current_state")
    _require(isinstance(current, dict), "current state missing")
    _require(
        current.get("state") == "predictions_sealed_waiting_for_outcome"
        and current.get("t0_remote_inventory_pinned") is True
        and current.get("t0_source_pinned") is True
        and current.get("candidate_index_contract_frozen") is True
        and current.get("candidate_universe_sealed") is True
        and current.get("metric_frozen") is True
        and current.get("predictions_sealed") is True
        and current.get("t1_source_pinned") is False
        and current.get("outcome_window_mature") is False
        and current.get("verdict") == "not_ready"
        and current.get("readiness_contribution") == 0,
        "current autonomous state drifted",
    )
    blockers = current.get("blockers")
    _require(blockers == list(EXPECTED_BLOCKERS), "current blocker list drifted")
    _require(
        "Wait for three subsequent complete annual PubMed baseline" in current.get(
            "next_machine_action", ""
        )
        and "official T1 source" in current.get("next_machine_action", "")
        and "do not revise" in current.get("next_machine_action", ""),
        "next machine action drifted",
    )

    return AutonomousProspectiveAudit(
        protocol_id=payload["id"],
        state=current["state"],
        verdict=current["verdict"],
        human_dependency_count=0,
        blockers=tuple(blockers),
        readiness_contribution=0,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-ready", action="store_true")
    args = parser.parse_args()
    audit = audit_autonomous_prospective()
    print("autonomous prospective protocol: structurally valid")
    print(f"track: {audit.protocol_id}")
    print(f"state: {audit.state}")
    print(f"human dependencies: {audit.human_dependency_count}")
    print(f"verdict: {audit.verdict}")
    print("readiness: NOT READY")
    for blocker in audit.blockers:
        print(f"  - {blocker}")
    if args.require_ready:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
