"""Validate the frozen BioASQ secondary-snapshot pilot pre-registration.

This command validates an experiment contract, not a metric result. The pilot remains at zero
metric-v3 readiness even when its contract is structurally valid.

Run:
    python -m pipeline.benchmark.validate_bioasq_pilot
    python -m pipeline.benchmark.validate_bioasq_pilot --verify-local-mesh
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from xml.etree import ElementTree

from pipeline.benchmark.audit_mesh import pinned_file
from pipeline.benchmark.bioasq_semantics import audit_semantics_manifest
from pipeline.benchmark.metric_blind import find_forbidden_fields
from pipeline.benchmark.negative_controls import audit_queue, load_protocol
from pipeline.benchmark.pin_mesh import inspect_descriptor_archive
from pipeline.benchmark.validate_candidates import audit_candidates
from pipeline.paths import MESH_CACHE_DIR, REPO_ROOT

PILOT_PATH = REPO_ROOT / "benchmarks" / "v3" / "bioasq-pilot.json"
POSITIVE_IDS = (
    "lion-nfkb-adenoma",
    "lion-notch1-cebpb",
    "lion-il17-mkp1",
    "lion-nrf2-pancreatic-cancer",
    "lion-cxcl12-thyroid-cancer",
)
KINDS = ("hard_negative", "distant_negative")
SPLITS = ("development", "heldout")


class BioasqPilotContractError(ValueError):
    pass


@dataclass(frozen=True)
class BioasqPilotAudit:
    status: str
    positive_counts: dict[str, int]
    control_counts: dict[str, dict[str, int]]
    total_cases: int
    unique_mapping_count: int
    readiness_contribution: int


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BioasqPilotContractError(message)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _referenced_file(value: object, context: str) -> Path:
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


def _selection_hash(namespace: str, case_id: str) -> str:
    return hashlib.sha256(f"{namespace}\0{case_id}".encode("utf-8")).hexdigest()


def _expected_positive_case(candidate: dict, split: str, selection_hash: str) -> dict:
    mappings = candidate["mapping_audit"]["mappings"]
    return {
        "id": candidate["id"],
        "split": split,
        "selection_hash": selection_hash,
        "cutoff": f"{candidate['source_cutoff_year']}-12-31",
        "source_discovery_year": candidate["source_discovery_year"],
        "endpoint_a": {
            "descriptor_ui": mappings["a"]["descriptor_ui"],
            "descriptor_label": mappings["a"]["descriptor_label"],
        },
        "bridge_b": {
            "descriptor_ui": mappings["b"]["descriptor_ui"],
            "descriptor_label": mappings["b"]["descriptor_label"],
        },
        "target_c": {
            "descriptor_ui": mappings["c"]["descriptor_ui"],
            "descriptor_label": mappings["c"]["descriptor_label"],
        },
    }


def _mapping_pairs(protocol: dict, negative_queue: dict) -> dict[str, str]:
    mappings: dict[str, str] = {}
    for case in protocol["case_population"]["positives"]["cases"]:
        for field in ("endpoint_a", "bridge_b", "target_c"):
            concept = case[field]
            ui = concept["descriptor_ui"]
            label = concept["descriptor_label"]
            _require(
                ui not in mappings or mappings[ui] == label,
                f"{ui}: conflicting descriptor labels",
            )
            mappings[ui] = label
    for case in negative_queue["candidates"]:
        for field in ("a", "c"):
            concept = case["concepts"][field]
            ui = concept["descriptor_ui"]
            label = concept["descriptor_label"]
            _require(
                ui not in mappings or mappings[ui] == label,
                f"{ui}: conflicting descriptor labels",
            )
            mappings[ui] = label
    return mappings


def audit_bioasq_pilot(path: Path = PILOT_PATH) -> BioasqPilotAudit:
    protocol = json.loads(path.read_text(encoding="utf-8"))
    _require(protocol.get("schema_version") == 1, "unsupported BioASQ pilot schema")
    _require(
        protocol.get("status") == "frozen_before_bioasq_pilot_metric",
        "BioASQ pilot is not frozen before metric work",
    )
    try:
        frozen_on = date.fromisoformat(str(protocol.get("frozen_on")))
    except ValueError as exc:
        raise BioasqPilotContractError("pilot frozen_on must be YYYY-MM-DD") from exc
    _require(frozen_on.isoformat() == "2026-08-12", "pilot freeze date drifted")
    _require(
        protocol.get("source_alternative_id") == "bioasq-2013-task-a",
        "pilot references the wrong source alternative",
    )

    boundary = protocol.get("claim_boundary")
    _require(isinstance(boundary, dict), "pilot is missing its claim boundary")
    _require(
        boundary.get("experiment_class")
        == "secondary_snapshot_reproduction_and_control_separation_pilot",
        "pilot experiment class drifted",
    )
    _require(boundary.get("readiness_contribution") == 0, "pilot cannot add readiness")
    not_claims = boundary.get("not_a_claim_of")
    _require(
        isinstance(not_claims, list)
        and {
            "period-appropriate historical indexing",
            "validated discovery ground truth",
            "population-wide gap detection",
            "original metric-v3 source readiness",
        }
        <= set(not_claims),
        "pilot claim exclusions are incomplete",
    )

    timing = protocol.get("freeze_timing")
    _require(isinstance(timing, dict), "pilot is missing freeze timing")
    for field in (
        "full_source_audit_seen",
        "bounded_field_semantics_result_seen",
        "positive_source_cases_seen",
        "metric_blind_control_queue_seen",
        "all_unique_case_endpoint_and_bridge_mappings_checked_in_pinned_mesh_2013",
        "legacy_failed_openalex_metric_outputs_seen",
    ):
        _require(timing.get(field) is True, f"freeze timing must disclose {field}")
    for field in (
        "case_endpoint_support_counts_seen",
        "bioasq_pilot_metric_formula_seen",
        "bioasq_pilot_scores_or_ranks_seen",
    ):
        _require(timing.get(field) is False, f"pilot was not frozen before {field}")
    _require(
        timing.get("unique_mapping_count_checked") == 46 and bool(timing.get("disclosure")),
        "pilot mapping disclosure drifted",
    )

    inputs = protocol.get("inputs")
    _require(isinstance(inputs, dict), "pilot is missing inputs")
    _require(
        set(inputs)
        == {
            "snapshot_audit",
            "snapshot_transport",
            "field_semantics_audit",
            "positive_candidate_ledger",
            "negative_selection_protocol",
            "negative_candidate_queue",
            "descriptor_vocabulary",
        },
        "pilot input identities drifted",
    )
    snapshot_path = _referenced_file(inputs["snapshot_audit"], "snapshot_audit")
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    _require(
        snapshot.get("status") == "measured_unmatched_input"
        and snapshot.get("readiness_contribution") == 0,
        "pilot must retain the measured source mismatch",
    )
    _require(
        inputs.get("snapshot_transport")
        == {
            "sha256": snapshot["input"]["sha256"],
            "bytes": snapshot["input"]["bytes"],
        },
        "pilot snapshot transport identity drifted",
    )

    semantics_path = _referenced_file(inputs["field_semantics_audit"], "field_semantics_audit")
    semantics = audit_semantics_manifest(
        semantics_path,
        snapshot_manifest_path=snapshot_path,
    )
    _require(
        semantics["classification"] == "sample_consistent_with_all_assigned_descriptors"
        and semantics["readiness_contribution"] == 0,
        "pilot field-semantics dependency drifted",
    )

    candidate_path = _referenced_file(inputs["positive_candidate_ledger"], "positive ledger")
    candidate_audit = audit_candidates(candidate_path)
    _require(candidate_audit.counts["proposed"] == 10, "positive candidate ledger drifted")
    candidate_payload = json.loads(candidate_path.read_text(encoding="utf-8"))
    candidates_by_id = {item["id"]: item for item in candidate_payload["candidates"]}
    _require(all(case_id in candidates_by_id for case_id in POSITIVE_IDS), "LION case is missing")

    negative_protocol_path = _referenced_file(
        inputs["negative_selection_protocol"], "negative selection protocol"
    )
    load_protocol(negative_protocol_path)
    negative_queue_path = _referenced_file(
        inputs["negative_candidate_queue"], "negative candidate queue"
    )
    queue_audit = audit_queue(negative_queue_path, negative_protocol_path)
    _require(
        queue_audit
        == {
            "counts": {"hard_negative": 8, "distant_negative": 8},
            "heldout_counts": {"hard_negative": 4, "distant_negative": 4},
            "readiness_contribution": 0,
        },
        "negative queue population drifted",
    )
    negative_queue = json.loads(negative_queue_path.read_text(encoding="utf-8"))

    expected_vocabulary = pinned_file(2013)
    _require(
        inputs.get("descriptor_vocabulary") == expected_vocabulary,
        "pilot descriptor vocabulary differs from the pinned MeSH 2013 archive",
    )

    population = protocol.get("case_population")
    _require(isinstance(population, dict), "pilot is missing its case population")
    _require(not find_forbidden_fields(population), "case population contains metric output fields")
    _require(
        population.get("total_cases") == 21
        and population.get("split_counts") == {"development": 11, "heldout": 10}
        and bool(population.get("heldout_disclosure")),
        "pilot population totals drifted",
    )

    positives = population.get("positives")
    _require(isinstance(positives, dict), "pilot is missing positive cases")
    _require(
        positives.get("count") == 5
        and positives.get("label_scope")
        == "source_labeled_lion_reproduction_case_not_independently_validated_discovery_truth",
        "pilot positive scope drifted",
    )
    split_rule = positives.get("split_rule")
    _require(
        split_rule
        == {
            "method": "sha256_bottom_2_case_ids_are_heldout",
            "hash_namespace": "lacuna-bioasq-pilot-v1-positive-split",
            "hash_input": "utf8(hash_namespace + NUL + case_id)",
            "tie_breaker": "case_id_ascending",
            "development_count": 3,
            "heldout_count": 2,
        },
        "pilot positive split rule drifted",
    )
    namespace = split_rule["hash_namespace"]
    hashes = {case_id: _selection_hash(namespace, case_id) for case_id in POSITIVE_IDS}
    heldout_ids = set(sorted(POSITIVE_IDS, key=lambda case_id: (hashes[case_id], case_id))[:2])
    expected_positive_cases = [
        _expected_positive_case(
            candidates_by_id[case_id],
            "heldout" if case_id in heldout_ids else "development",
            hashes[case_id],
        )
        for case_id in POSITIVE_IDS
    ]
    _require(
        positives.get("cases") == expected_positive_cases,
        "pilot positive case identity, mapping, cutoff, or split drifted",
    )
    for case_id in POSITIVE_IDS:
        candidate = candidates_by_id[case_id]
        _require(
            candidate.get("status") == "proposed"
            and candidate.get("selection_stage") == "pre_metric"
            and candidate.get("mapping_audit", {}).get("status")
            == "production_year_candidate",
            f"{case_id}: source-labelled case was overstated as accepted ground truth",
        )

    controls = population.get("controls")
    _require(isinstance(controls, dict), "pilot is missing controls")
    _require(
        controls.get("label_scope")
        == "ontology_generated_structural_control_proposal_not_verified_absence_of_a_relationship"
        and controls.get("status_at_freeze") == "proposed_zero_readiness",
        "pilot control scope drifted",
    )
    expected_control_ids = {
        kind: {
            split: [
                item["id"]
                for item in negative_queue["candidates"]
                if item["kind"] == kind and item["proposed_split"] == split
            ]
            for split in SPLITS
        }
        for kind in KINDS
    }
    _require(
        controls.get("ids_by_kind_and_split") == expected_control_ids,
        "pilot does not include the complete pinned control queue",
    )
    expected_control_counts = {
        kind: {split: len(expected_control_ids[kind][split]) for split in SPLITS}
        for kind in KINDS
    }
    _require(
        controls.get("counts") == expected_control_counts,
        "pilot control counts drifted",
    )

    mappings = _mapping_pairs(protocol, negative_queue)
    _require(
        len(mappings) == timing["unique_mapping_count_checked"] == 46,
        "pilot unique mapping count drifted",
    )

    transform = protocol.get("source_transform")
    _require(isinstance(transform, dict), "pilot is missing its source transform")
    _require(
        transform.get("publication_cutoff")
        == "include_article_if_normalized_publication_year_lte_case_cutoff_year"
        and transform.get("descriptor_identity")
        == "exact_mesh_2013_descriptor_ui_resolved_from_normalized_bioasq_label"
        and transform.get("article_contribution")
        == "binary_unique_descriptor_set_per_article"
        and transform.get("cooccurrence_unit")
        == "number_of_articles_containing_both_descriptors"
        and transform.get("direct_endpoint_cooccurrences")
        == "retain_and_report_exactly; never delete A-C articles for a named case"
        and transform.get("primary_minimum_support_articles") == 10
        and transform.get("support_sensitivity_articles") == [5, 20]
        and transform.get("ontology_relatives_policy")
        == (
            "Do not remove parent, child, or sibling descriptors before ranking; "
            "the hard controls exist to measure that confounder."
        ),
        "pilot source transform drifted",
    )

    compatibility = protocol.get("source_compatibility_gate")
    _require(isinstance(compatibility, dict), "pilot is missing source compatibility gate")
    _require(
        compatibility.get("must_run_before_metric_formula_selection") is True
        and compatibility.get("required_case_count") == 21
        and compatibility.get("failure_outcome") == "pilot_inconclusive_source_coverage"
        and "Do not replace" in str(compatibility.get("replacement_policy")),
        "pilot source compatibility gate drifted",
    )

    isolation = protocol.get("metric_isolation")
    _require(isinstance(isolation, dict), "pilot is missing metric isolation")
    _require(
        isolation.get("formula_contract_required_before_scores") is True
        and isolation.get("formula_contract_must_be_separately_checksum_pinned") is True
        and isolation.get("candidate_formula_revision_limit") == 1
        and "held-out scores" in str(isolation.get("heldout_policy")),
        "pilot metric isolation drifted",
    )

    ranking = protocol.get("ranking_contract")
    _require(
        ranking
        == {
            "primary_orientation": "rank target C conditioned on seed A",
            "candidate_order": "descending metric score",
            "tie_policy": "conservative worst tied rank",
            "one_based_rank": "count(candidate_score >= target_score)",
            "rank_fraction": "one_based_rank / eligible_candidate_count",
            "top_5_percent": "rank_fraction <= 0.05",
            "top_1_percent_and_top_100": "diagnostic_only",
            "reciprocal_c_to_a_orientation": (
                "diagnostic_only_and_cannot_change_the_primary_decision"
            ),
        },
        "pilot ranking contract drifted",
    )

    decision = protocol.get("heldout_decision_rule")
    _require(isinstance(decision, dict), "pilot is missing held-out decision rule")
    _require(
        decision.get("positive_requirement")
        == "At least 1 of 2 held-out source-labelled LION targets ranks in the top 5 percent."
        and decision.get("hard_control_requirement")
        == "Zero of 4 held-out ontology-sibling hard controls ranks in the top 5 percent."
        and decision.get("distant_control_requirement")
        == (
            "All 4 held-out cross-branch distant controls rank below the median, "
            "meaning rank_fraction > 0.5."
        )
        and decision.get("sensitivity_requirement")
        == (
            "The three held-out requirements must also hold at minimum-support settings "
            "5 and 20; an unevaluable sensitivity setting is not a pass."
        )
        and decision.get("passing_label")
        == "pilot_signal_consistent_with_frozen_source_labeled_separation_rule"
        and decision.get("failing_label") == "pilot_signal_not_reproduced"
        and decision.get("inconclusive_label") == "pilot_inconclusive_source_coverage"
        and decision.get("readiness_contribution") == 0,
        "pilot held-out decision rule drifted",
    )

    reporting = protocol.get("reporting_requirements")
    limitations = protocol.get("limitations")
    _require(
        isinstance(reporting, list)
        and len(reporting) >= 5
        and isinstance(limitations, list)
        and len(limitations) >= 7,
        "pilot reporting or limitations are incomplete",
    )
    serialized = json.dumps(protocol, ensure_ascii=False).lower()
    _require("llm interpretation" in serialized, "pilot must keep the LLM layer gated")
    _require("non-academic" in serialized, "pilot must retain non-academic blind spots")

    positive_counts = {
        split: sum(item["split"] == split for item in expected_positive_cases)
        for split in SPLITS
    }
    return BioasqPilotAudit(
        status=protocol["status"],
        positive_counts=positive_counts,
        control_counts=expected_control_counts,
        total_cases=population["total_cases"],
        unique_mapping_count=len(mappings),
        readiness_contribution=boundary["readiness_contribution"],
    )


def verify_local_mesh_mappings(
    protocol_path: Path = PILOT_PATH,
    mesh_path: Path = MESH_CACHE_DIR / "desc2013.gz",
) -> int:
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    inputs = protocol["inputs"]
    negative_queue_path = REPO_ROOT / Path(inputs["negative_candidate_queue"]["path"])
    negative_queue = json.loads(negative_queue_path.read_text(encoding="utf-8"))
    mappings = _mapping_pairs(protocol, negative_queue)
    _require(mesh_path.is_file(), f"local MeSH archive is missing: {mesh_path}")
    sha256, size, descriptor_count = inspect_descriptor_archive(mesh_path)
    expected = inputs["descriptor_vocabulary"]
    _require(
        sha256 == expected["sha256"]
        and size == expected["bytes"]
        and descriptor_count == expected["descriptor_count"],
        "local MeSH 2013 archive differs from the pilot pin",
    )
    found: dict[str, str] = {}
    with gzip.open(mesh_path, "rb") as stream:
        for _, element in ElementTree.iterparse(stream, events=("end",)):
            if element.tag.rsplit("}", 1)[-1] != "DescriptorRecord":
                continue
            ui = element.findtext("./DescriptorUI") or ""
            if ui in mappings:
                found[ui] = element.findtext("./DescriptorName/String") or ""
            element.clear()
    _require(found == mappings, "pilot mappings do not exactly match pinned MeSH 2013")
    return len(found)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verify-local-mesh",
        action="store_true",
        help="also checksum and parse the ignored local MeSH 2013 archive",
    )
    args = parser.parse_args()
    audit = audit_bioasq_pilot()
    print("BioASQ secondary pilot protocol: structurally valid")
    print(f"status: {audit.status}")
    print(
        "positive cases: "
        f"development={audit.positive_counts['development']}, "
        f"heldout={audit.positive_counts['heldout']}"
    )
    for kind in KINDS:
        print(
            f"{kind} controls: "
            f"development={audit.control_counts[kind]['development']}, "
            f"heldout={audit.control_counts[kind]['heldout']}"
        )
    print(f"total cases: {audit.total_cases}")
    print(f"readiness contribution: {audit.readiness_contribution}")
    if args.verify_local_mesh:
        print(f"local MeSH 2013 mappings verified: {verify_local_mesh_mappings()}")


if __name__ == "__main__":
    main()
