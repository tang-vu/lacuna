"""Validate the sealed score-free T0 candidate universe and optionally its local bytes.

The committed manifest is an exact count/index result with zero metric or scientific readiness.
Use ``--verify-local`` only where the off-repository binary artifacts are available.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from pipeline.benchmark.autonomous_candidate_index import _sha256_file
from pipeline.benchmark.autonomous_candidate_reduce import (
    GLOBAL_PAIR_DTYPE,
    audit_candidate_stream,
)
from pipeline.benchmark.autonomous_t0 import audit_sealed_t0
from pipeline.benchmark.validate_autonomous_candidate_index import audit_candidate_index_contract
from pipeline.paths import REPO_ROOT
from pipeline.provenance import sha256_payload

MANIFEST_PATH = REPO_ROOT / "benchmarks" / "autonomous" / "t0-candidate-universe-v1.json"
EXPECTED_ID = "autonomous-t0-candidate-universe-v1"
FORBIDDEN_FIELDS = {"score", "rank", "percentile", "prediction_label", "interpretation"}
ARTIFACT_FORMATS = {
    "descriptor_table": ("descriptor-json-v1", None),
    "support_vector": ("support-u64-v1", 8),
    "pmid_vector": ("pmid-u64-v1", 8),
    "positive_cooccurrence_index": ("pair-u64-u64-v1", 16),
    "candidate_stream": ("candidate-key-u64-v1", 8),
}


class AutonomousCandidateUniverseError(ValueError):
    pass


@dataclass(frozen=True)
class AutonomousCandidateUniverseAudit:
    manifest_id: str
    sha256: str
    status: str
    source_file_count: int
    distinct_pmid_count: int
    descriptor_count: int
    descriptor_assignment_count: int
    positive_pair_count: int
    pair_observation_count: int
    candidate_pair_count: int
    readiness_contribution: int
    local_bytes_verified: bool


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AutonomousCandidateUniverseError(message)


def _find_forbidden(value: object) -> set[str]:
    if isinstance(value, dict):
        found = FORBIDDEN_FIELDS.intersection(value)
        for child in value.values():
            found.update(_find_forbidden(child))
        return found
    if isinstance(value, list):
        found: set[str] = set()
        for child in value:
            found.update(_find_forbidden(child))
        return found
    return set()


def _artifact_path(scan_dir: Path, item: dict) -> Path:
    relative = Path(item["path"])
    _require(not relative.is_absolute() and ".." not in relative.parts, "artifact path escapes scan dir")
    path = (scan_dir / relative).resolve()
    _require(path.is_relative_to(scan_dir.resolve()), "artifact path escapes scan dir")
    return path


def audit_candidate_universe(
    path: Path = MANIFEST_PATH,
    *,
    scan_dir: Path | None = None,
) -> AutonomousCandidateUniverseAudit:
    payload = json.loads(path.read_text(encoding="utf-8"))
    contract = audit_candidate_index_contract()
    sealed = audit_sealed_t0()
    _require(payload.get("schema_version") == 1, "candidate-universe schema drifted")
    _require(payload.get("id") == EXPECTED_ID, "candidate-universe id drifted")
    _require(
        payload.get("status") == "score_free_candidate_universe_complete",
        "candidate-universe status drifted",
    )
    _require(payload.get("completed_on") == "2026-08-13", "candidate-universe date drifted")
    _require(
        payload.get("protocol_id") == "autonomous-prospective-pubmed-link-emergence-v1",
        "candidate-universe protocol identity drifted",
    )
    _require(not _find_forbidden(payload), "candidate-universe contains metric or generated fields")

    inputs = payload.get("inputs")
    _require(isinstance(inputs, dict), "candidate-universe inputs missing")
    _require(
        inputs.get("candidate_index_contract")
        == {
            "path": "autonomous/t0-candidate-index-v1.json",
            "canonical_json_sha256": contract.sha256,
        },
        "candidate-index contract input drifted",
    )
    _require(
        inputs.get("sealed_t0")
        == {
            "path": "autonomous/t0-2026.json",
            "canonical_json_sha256": sealed.sha256,
        },
        "sealed T0 input drifted",
    )
    for name in ("source_shard_set_canonical_json_sha256", "mesh_transport_sha256", "builder_source_sha256"):
        _require(
            isinstance(inputs.get(name), str) and re.fullmatch(r"[0-9a-f]{64}", inputs[name]) is not None,
            f"{name} is not a SHA-256",
        )
    _require(
        inputs["mesh_transport_sha256"]
        == json.loads((REPO_ROOT / "benchmarks" / "autonomous" / "t0-2026.json").read_text(encoding="utf-8"))["mesh_descriptor"]["sha256"],
        "MeSH transport input drifted",
    )

    boundary = payload.get("measurement_boundary")
    _require(
        boundary
        == {
            "indexing_basis": "maintained_2026_pubmed_mesh_assignments",
            "method": "exact full-baseline integer reduction; no sampling or approximation",
            "readiness_contribution": 0,
        },
        "candidate-universe measurement boundary drifted",
    )
    counts = payload.get("counts")
    _require(isinstance(counts, dict), "candidate-universe counts missing")
    _require(
        set(counts)
        == {
            "source_files",
            "distinct_valid_pmids",
            "records_without_mesh",
            "mesh_descriptors",
            "descriptor_assignments",
            "positive_pair_rows",
            "pair_observations",
            "candidate_pairs",
        }
        and all(type(value) is int and value >= 0 for value in counts.values()),
        "candidate-universe count shape drifted",
    )
    _require(
        counts["source_files"] == sealed.pubmed_file_count
        and counts["distinct_valid_pmids"] == sealed.pubmed_record_count
        and counts["mesh_descriptors"] == sealed.mesh_descriptor_count
        and counts["records_without_mesh"] <= counts["distinct_valid_pmids"]
        and counts["positive_pair_rows"] <= counts["pair_observations"]
        and counts["candidate_pairs"] > 0,
        "candidate-universe count invariants drifted",
    )

    artifacts = payload.get("artifacts")
    _require(isinstance(artifacts, dict) and set(artifacts) == set(ARTIFACT_FORMATS), "artifact set drifted")
    expected_rows = {
        "descriptor_table": counts["mesh_descriptors"],
        "support_vector": counts["mesh_descriptors"],
        "pmid_vector": counts["distinct_valid_pmids"],
        "positive_cooccurrence_index": counts["positive_pair_rows"],
        "candidate_stream": counts["candidate_pairs"],
    }
    for name, (expected_format, itemsize) in ARTIFACT_FORMATS.items():
        item = artifacts[name]
        _require(
            isinstance(item, dict)
            and set(item) == {"path", "format", "rows", "sha256", "bytes"}
            and item["format"] == expected_format
            and item["rows"] == expected_rows[name]
            and type(item["bytes"]) is int
            and item["bytes"] >= 0
            and isinstance(item["sha256"], str)
            and re.fullmatch(r"[0-9a-f]{64}", item["sha256"]) is not None,
            f"{name} artifact identity drifted",
        )
        if itemsize is not None:
            _require(item["bytes"] == item["rows"] * itemsize, f"{name} artifact shape drifted")

    _require(
        payload.get("completion_gates")
        == {
            "all_source_hashes_and_record_subtotals_match": True,
            "global_pmids_strictly_unique_and_equal_sealed_denominator": True,
            "unknown_descriptors": 0,
            "support_and_positive_pair_reductions_exact": True,
            "candidate_stream_exhaustive_strictly_ordered_duplicate_free": True,
            "metric_scores_or_predictions_emitted": False,
        },
        "candidate-universe completion gates drifted",
    )
    claim = payload.get("claim_boundary", "")
    for phrase in ("maintained-current", "not a metric", "not a", "validated gap", "absent knowledge"):
        _require(phrase in claim, f"candidate-universe claim boundary omits {phrase}")

    if scan_dir is not None:
        paths = {name: _artifact_path(scan_dir, item) for name, item in artifacts.items()}
        for name, item in artifacts.items():
            local = paths[name]
            _require(local.is_file() and local.stat().st_size == item["bytes"], f"{name} local bytes missing")
            _require(_sha256_file(local) == item["sha256"], f"{name} local hash drifted")
        supports = np.memmap(paths["support_vector"], mode="r", dtype="<u8")
        pmids = np.memmap(paths["pmid_vector"], mode="r", dtype="<u8")
        pairs = np.memmap(paths["positive_cooccurrence_index"], mode="r", dtype=GLOBAL_PAIR_DTYPE)
        _require(int(supports.sum(dtype=np.uint64)) == counts["descriptor_assignments"], "support sum drifted")
        previous_pmid: int | None = None
        for start in range(0, pmids.size, 5_000_000):
            chunk = pmids[start : start + 5_000_000]
            _require(
                (previous_pmid is None or int(chunk[0]) > previous_pmid)
                and (chunk.size < 2 or not bool(np.any(chunk[1:] <= chunk[:-1]))),
                "global PMID order drifted",
            )
            previous_pmid = int(chunk[-1])
        previous_pair: int | None = None
        pair_sum = 0
        for start in range(0, pairs.size, 5_000_000):
            chunk = pairs[start : start + 5_000_000]
            keys = chunk["key"]
            left = keys // np.uint64(counts["mesh_descriptors"])
            right = keys % np.uint64(counts["mesh_descriptors"])
            _require(
                (previous_pair is None or int(keys[0]) > previous_pair)
                and (keys.size < 2 or not bool(np.any(keys[1:] <= keys[:-1])))
                and not bool(np.any(left >= right))
                and not bool(np.any(right >= counts["mesh_descriptors"]))
                and not bool(np.any(chunk["count"] == 0))
                and not bool(np.any(chunk["count"] > counts["distinct_valid_pmids"])),
                "positive-pair index invariants drifted",
            )
            pair_sum += int(chunk["count"].sum(dtype=np.uint64))
            previous_pair = int(keys[-1])
        _require(pair_sum == counts["pair_observations"], "pair sum drifted")
        descriptors_payload = json.loads(paths["descriptor_table"].read_text(encoding="utf-8"))
        descriptor_rows = descriptors_payload.get("descriptors")
        _require(
            descriptors_payload.get("candidate_index_contract_sha256") == contract.sha256
            and descriptors_payload.get("mesh_transport_sha256") == inputs["mesh_transport_sha256"]
            and descriptors_payload.get("descriptor_count") == counts["mesh_descriptors"]
            and isinstance(descriptor_rows, list)
            and len(descriptor_rows) == counts["mesh_descriptors"]
            and [item.get("index") for item in descriptor_rows]
            == list(range(counts["mesh_descriptors"]))
            and [item.get("ui") for item in descriptor_rows]
            == sorted(item.get("ui") for item in descriptor_rows),
            "descriptor table drifted",
        )
        from pipeline.benchmark.autonomous_candidate_index import VocabularyDescriptor

        vocabulary = tuple(
            VocabularyDescriptor(
                item["ui"], item["label"], tuple(item["tree_numbers"]), tuple(item["normalised_terms"])
            )
            for item in descriptor_rows
        )
        audited_candidates = audit_candidate_stream(
            paths["support_vector"],
            paths["positive_cooccurrence_index"],
            paths["candidate_stream"],
            vocabulary=vocabulary,
            denominator=counts["distinct_valid_pmids"],
        )
        _require(audited_candidates.rows == counts["candidate_pairs"], "candidate exhaustiveness drifted")

    return AutonomousCandidateUniverseAudit(
        manifest_id=payload["id"],
        sha256=sha256_payload(payload),
        status=payload["status"],
        source_file_count=counts["source_files"],
        distinct_pmid_count=counts["distinct_valid_pmids"],
        descriptor_count=counts["mesh_descriptors"],
        descriptor_assignment_count=counts["descriptor_assignments"],
        positive_pair_count=counts["positive_pair_rows"],
        pair_observation_count=counts["pair_observations"],
        candidate_pair_count=counts["candidate_pairs"],
        readiness_contribution=0,
        local_bytes_verified=scan_dir is not None,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-local", type=Path, metavar="SCAN_DIR")
    args = parser.parse_args()
    audit = audit_candidate_universe(scan_dir=args.verify_local)
    print("autonomous candidate universe: structurally valid")
    print(f"canonical JSON SHA-256: {audit.sha256}")
    print(f"distinct PubMed rows: {audit.distinct_pmid_count}")
    print(f"positive pair rows: {audit.positive_pair_count}")
    print(f"candidate pairs: {audit.candidate_pair_count}")
    print(f"local bytes verified: {'yes' if audit.local_bytes_verified else 'not requested'}")
    print("readiness contribution: 0 (no metric, prediction, or outcome result)")


if __name__ == "__main__":
    main()
