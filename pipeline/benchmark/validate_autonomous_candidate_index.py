"""Validate the frozen, score-free T0 candidate-index construction contract."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pipeline.benchmark.autonomous_t0 import SEALED_T0_PATH, audit_sealed_t0
from pipeline.paths import REPO_ROOT
from pipeline.provenance import sha256_payload

CONTRACT_PATH = REPO_ROOT / "benchmarks" / "autonomous" / "t0-candidate-index-v1.json"
EXPECTED_ID = "autonomous-t0-candidate-index-v1"
FORBIDDEN_OUTPUT_FIELDS = {"score", "rank", "percentile", "prediction_label", "interpretation"}


class AutonomousCandidateIndexContractError(ValueError):
    pass


@dataclass(frozen=True)
class AutonomousCandidateIndexAudit:
    contract_id: str
    sha256: str
    t0_manifest_sha256: str
    source_file_count: int
    source_record_count: int
    descriptor_count: int
    status: str
    readiness_contribution: int


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AutonomousCandidateIndexContractError(message)


def _find_forbidden_fields(value: object) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        found.update(FORBIDDEN_OUTPUT_FIELDS.intersection(value))
        for child in value.values():
            found.update(_find_forbidden_fields(child))
    elif isinstance(value, list):
        for child in value:
            found.update(_find_forbidden_fields(child))
    return found


def audit_candidate_index_contract(path: Path = CONTRACT_PATH) -> AutonomousCandidateIndexAudit:
    payload = json.loads(path.read_text(encoding="utf-8"))
    _require(payload.get("schema_version") == 1, "candidate-index schema drifted")
    _require(payload.get("id") == EXPECTED_ID, "candidate-index id drifted")
    _require(
        payload.get("status") == "frozen_before_descriptor_support_or_pair_measurement"
        and payload.get("frozen_on") == "2026-08-13",
        "candidate-index freeze identity drifted",
    )
    _require(
        payload.get("protocol_id") == "autonomous-prospective-pubmed-link-emergence-v1"
        and payload.get("human_dependencies") == [],
        "candidate-index added a human dependency or changed track",
    )

    sealed = audit_sealed_t0(SEALED_T0_PATH)
    known = payload.get("known_before_freeze")
    _require(isinstance(known, dict), "known-before-freeze evidence missing")
    _require(
        known
        == {
            "t0_manifest_path": "autonomous/t0-2026.json",
            "t0_manifest_sha256": sealed.sha256,
            "canonicalisation": "canonical-json-v1",
            "pubmed_file_count": sealed.pubmed_file_count,
            "pubmed_compressed_bytes": sealed.pubmed_bytes,
            "pubmed_record_count": sealed.pubmed_record_count,
            "mesh_descriptor_count": sealed.mesh_descriptor_count,
            "mesh_transport_sha256": "9fe35b3170652376a592daf69e91a80d6c693ecaf9c571ceb701d04204cb357d",
            "candidate_counts_seen": False,
            "descriptor_supports_seen": False,
            "descriptor_pair_counts_seen": False,
            "metric_scores_seen": False,
        },
        "known-before-freeze evidence drifted",
    )

    boundary = payload.get("measurement_boundary", {})
    not_measured = " ".join(boundary.get("not_measured", [])).lower()
    _require(
        boundary.get("indexing_basis") == "maintained_2026_pubmed_mesh_assignments"
        and boundary.get("readiness_contribution") == 0
        and "non-academic" in not_measured
        and "historical" in not_measured
        and "metric score" in not_measured,
        "candidate-index claim boundary drifted",
    )

    records = payload.get("record_contract", {})
    _require(
        records.get("included_xml_record") == "PubmedArticle/MedlineCitation"
        and "exactly once" in records.get("pmid_deduplication", "")
        and records.get("descriptor_multiplicity")
        == "binary within PMID after exact UI deduplication"
        and records.get("unknown_descriptor_action") == "abstain"
        and "included" in records.get("records_without_mesh", "")
        and "must remain zero" in records.get("book_articles", "")
        and "must remain zero" in records.get("delete_citations", ""),
        "record population or deduplication drifted",
    )

    vocabulary = payload.get("vocabulary_contract", {})
    _require(
        vocabulary.get("descriptor_order")
        == "ascending descriptor UI from the complete sealed descriptor transport"
        and vocabulary.get("term_normalisation")
        == "Unicode NFKC, casefold, collapse all whitespace runs to one ASCII space, strip"
        and "strict prefix" in vocabulary.get("ancestor_descendant_rule", "")
        and vocabulary.get("shared_entry_term_rule")
        == "exclude a pair when the normalised term sets intersect",
        "vocabulary exclusion semantics drifted",
    )

    counts = payload.get("count_contract", {})
    _require(
        counts.get("sampling_allowed") is False
        and counts.get("approximation_allowed") is False
        and "distinct PMIDs" in counts.get("descriptor_support", "")
        and "distinct PMIDs" in counts.get("direct_cooccurrence", "")
        and counts.get("integer_width")
        == "unsigned 64-bit accumulation with explicit overflow guards",
        "exact count contract drifted",
    )

    candidate = payload.get("candidate_contract", {})
    _require(
        candidate.get("minimum_endpoint_article_support") == 100
        and candidate.get("minimum_independence_expected_count") == 5
        and candidate.get("maximum_exact_direct_cooccurrence") == 0
        and candidate.get("exclude_identical_descriptors") is True
        and candidate.get("exclude_ancestor_descendant_pairs") is True
        and candidate.get("exclude_shared_entry_term_pairs") is True
        and candidate.get("candidate_set_hash_required") is True
        and candidate.get("exhaustive") is True,
        "candidate eligibility gate drifted",
    )
    _require(
        candidate.get("candidate_identity_fields")
        == [
            "descriptor UI A",
            "descriptor UI C",
            "T0 endpoint supports",
            "T0 exact direct count",
            "T0 expected count numerator and denominator",
            "candidate contract SHA-256",
        ],
        "candidate identity fields drifted",
    )

    storage = payload.get("storage_contract", {})
    shard = storage.get("source_file_shard", {})
    _require(
        storage.get("runtime_volume")
        == "non-system data volume selected explicitly by the operator"
        and storage.get("system_temp_allowed") is False
        and storage.get("overwrite_allowed") is False
        and storage.get("minimum_free_gib_before_scan") == 100
        and "uint64 little-endian" in shard.get("pair_key", "")
        and "uint32 little-endian" in shard.get("count", "")
        and storage.get("partial_suffix") == ".part",
        "bounded storage or shard format drifted",
    )

    gate = payload.get("completion_gate", {})
    required = gate.get("required")
    _require(
        isinstance(required, list)
        and len(required) == 7
        and gate.get("failure_action") == "abstain_without_candidate_or_metric_claim"
        and gate.get("manual_override_allowed") is False,
        "completion or abstention gate drifted",
    )
    output = payload.get("output_contract", {})
    _require(
        output.get("manifest_write") == "exclusive create after every completion gate passes"
        and output.get("forbidden_fields_before_metric_freeze")
        == ["score", "rank", "percentile", "prediction_label", "interpretation"]
        and "not a metric result" in output.get("claim_boundary", ""),
        "score-free output boundary drifted",
    )
    _require(not _find_forbidden_fields(payload), "candidate-index contract contains metric output")

    return AutonomousCandidateIndexAudit(
        contract_id=payload["id"],
        sha256=sha256_payload(payload),
        t0_manifest_sha256=known["t0_manifest_sha256"],
        source_file_count=sealed.pubmed_file_count,
        source_record_count=sealed.pubmed_record_count,
        descriptor_count=sealed.mesh_descriptor_count,
        status=payload["status"],
        readiness_contribution=0,
    )


def main() -> None:
    audit = audit_candidate_index_contract()
    print("autonomous candidate-index contract: structurally valid")
    print(f"contract: {audit.contract_id}")
    print(f"canonical JSON SHA-256: {audit.sha256}")
    print(f"source files: {audit.source_file_count}")
    print(f"source rows: {audit.source_record_count}")
    print(f"MeSH descriptors: {audit.descriptor_count}")
    print("readiness contribution: 0 (no counts, candidates, scores, or predictions yet)")


if __name__ == "__main__":
    main()
