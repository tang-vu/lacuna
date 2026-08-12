"""Validate the sealed T0 metric-v1 predictions and optionally all local bytes."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from pipeline.benchmark.autonomous_candidate_index import _sha256_file
from pipeline.benchmark.autonomous_metric_v1 import (
    ENGINE_SOURCE,
    PREDICTION_MANIFEST_PATH,
    SCORE_DTYPE,
    WEIGHT_DTYPE,
)
from pipeline.benchmark.autonomous_t0 import audit_sealed_t0
from pipeline.benchmark.validate_autonomous_candidate_universe import audit_candidate_universe
from pipeline.benchmark.validate_autonomous_metric_v1 import audit_autonomous_metric_v1
from pipeline.paths import REPO_ROOT
from pipeline.provenance import sha256_payload

MANIFEST_PATH = PREDICTION_MANIFEST_PATH
EXPECTED_ID = "autonomous-t0-predictions-v1"
EXPECTED_SHA256 = "994e9697e2e7673a077335808d53911ceab674dac18031a3b7f847200caab591"
ARTIFACT_CONTRACT = {
    "degree_weights": ("degree-aa-q48-ra-q48-u64-v1", 31_111, 16),
    "backbone_offsets": ("csr-offset-u64-v1", 31_111, 8),
    "backbone_neighbors": ("csr-neighbor-u32-v1", 63_520_422, 4),
    "candidate_scores": ("candidate-score-record-v1", 7_310_895, 48),
    "primary_order": ("ranked-pair-key-u64-v1", 7_310_895, 8),
}


class AutonomousPredictionsV1Error(ValueError):
    pass


@dataclass(frozen=True)
class AutonomousPredictionsV1Audit:
    prediction_id: str
    sha256: str
    status: str
    primary_formula: str
    backbone_edge_count: int
    candidate_score_count: int
    nonzero_score_count: int
    readiness_contribution: int
    local_bytes_verified: bool


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AutonomousPredictionsV1Error(message)


def _hash_shape(value: object, context: str) -> None:
    _require(
        isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None,
        f"{context} is not a SHA-256",
    )


def _local_path(root: Path, item: dict, context: str) -> Path:
    relative = Path(item["path"])
    _require(not relative.is_absolute() and ".." not in relative.parts, f"{context} path escapes root")
    resolved = (root / relative).resolve()
    _require(resolved.is_relative_to(root.resolve()), f"{context} path escapes root")
    return resolved


def _run_native(engine: Path, command: str, arguments: dict[str, object]) -> None:
    argv = [str(engine), command]
    for name, value in arguments.items():
        argv.extend((f"--{name}", str(value)))
    result = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    _require(
        result.returncode == 0,
        f"native {command} audit failed:\n{result.stdout}\n{result.stderr}",
    )


def audit_predictions_v1(
    path: Path = MANIFEST_PATH,
    *,
    output_dir: Path | None = None,
    scan_dir: Path | None = None,
) -> AutonomousPredictionsV1Audit:
    payload = json.loads(path.read_text(encoding="utf-8"))
    sealed = audit_sealed_t0()
    universe = audit_candidate_universe(scan_dir=scan_dir if output_dir is not None else None)
    metric = audit_autonomous_metric_v1()
    _require(payload.get("schema_version") == 1, "prediction schema drifted")
    _require(payload.get("id") == EXPECTED_ID, "prediction id drifted")
    _require(payload.get("status") == "sealed_before_t1", "prediction status drifted")
    _require(payload.get("sealed_on") == "2026-08-13", "prediction seal date drifted")
    _require(
        payload.get("protocol_id") == "autonomous-prospective-pubmed-link-emergence-v1",
        "prediction protocol identity drifted",
    )
    _require(sha256_payload(payload) == EXPECTED_SHA256, "prediction manifest identity drifted")

    inputs = payload.get("sealed_inputs")
    _require(isinstance(inputs, dict), "prediction sealed inputs missing")
    _require(
        inputs.get("t0_manifest_canonical_json_sha256") == sealed.sha256
        and inputs.get("candidate_universe")
        == {
            "canonical_json_sha256": universe.sha256,
            "candidate_stream_sha256": "ed3c015515ac3e9bb69f7bc98f7663941d7fe57311165d68d72d1979e7b945b4",
            "candidate_pair_count": universe.candidate_pair_count,
        }
        and inputs.get("metric_contract")
        == {
            "canonical_json_sha256": metric.sha256,
            "formula_source_sha256": "2347607abc20600af76d82d741135bfd043a6f4fb4afee5d1517732135583246",
            "dependency_lock_sha256": "443b00eef325cd6e4ac6ab0033ea51c6713f4566401c46a89201ae9f49bc33ea",
        }
        and inputs.get("support_vector_sha256")
        == "e207f5f25633820281992d0a17f0e93266bf62b28d677b8b06d0d09400eb9a22"
        and inputs.get("positive_cooccurrence_index_sha256")
        == "8b656c29bfa3d4fb5df8e7591598a968c5d677a8ad29171908a771efe9e6cced",
        "prediction sealed-input identity drifted",
    )

    runtime = payload.get("runtime")
    _require(isinstance(runtime, dict), "prediction runtime identity missing")
    _require(
        runtime.get("python_implementation") == "cpython"
        and runtime.get("python_version") == "3.14.4"
        and runtime.get("numpy_version") == "2.4.4"
        and runtime.get("native_language_standard") == "C++17"
        and runtime.get("compile_flags")
        == ["-std=c++17", "-O3", "-DNDEBUG", "-Wall", "-Wextra", "-Werror"]
        and "16.1.0" in runtime.get("compiler_version", ""),
        "prediction runtime identity drifted",
    )
    for name, expected_path in (
        ("orchestrator_source", "pipeline/benchmark/autonomous_metric_v1.py"),
        ("engine_source", "pipeline/benchmark/native/autonomous_metric_v1_engine.cpp"),
    ):
        item = runtime.get(name)
        _require(
            isinstance(item, dict) and item.get("path") == expected_path,
            f"{name} identity drifted",
        )
        _hash_shape(item.get("sha256"), f"{name} hash")
        _require(
            _sha256_file(REPO_ROOT / expected_path) == item["sha256"],
            f"{name} source hash drifted",
        )
    binary = runtime.get("engine_binary")
    conformance = runtime.get("native_conformance")
    for item, context, expected_format in (
        (binary, "engine binary", "native-executable"),
        (conformance, "native conformance", "canonical-json-v1"),
    ):
        _require(
            isinstance(item, dict)
            and item.get("format") == expected_format
            and item.get("rows") == 1
            and type(item.get("bytes")) is int
            and item["bytes"] > 0,
            f"{context} artifact identity drifted",
        )
        _hash_shape(item.get("sha256"), f"{context} hash")
    _require(
        conformance.get("passed") is True
        and conformance.get("edge_rows_checked") == 7
        and conformance.get("candidate_score_rows_checked") == 3,
        "native conformance result drifted",
    )

    measurements = payload.get("measurements")
    expected_measurements = {
        "positive_source_rows_audited": 51_128_229,
        "backbone_edges": 31_760_211,
        "backbone_neighbor_rows": 63_520_422,
        "degree_minimum": 0,
        "degree_median_nearest_rank": 1_611,
        "degree_p90_nearest_rank": 4_330,
        "degree_p99_nearest_rank": 8_038,
        "degree_maximum": 17_979,
        "candidate_score_rows": 7_310_895,
        "candidate_primary_score_zero_rows": 69,
        "candidate_primary_score_nonzero_rows": 7_310_826,
        "candidate_primary_score_minimum_q48": "0",
        "candidate_primary_score_maximum_q48": "166267025613987885",
        "maximum_candidate_common_neighbors": 4_607,
        "primary_order_rows": 7_310_895,
    }
    _require(measurements == expected_measurements, "prediction measurement drifted")
    _require(
        measurements["candidate_primary_score_zero_rows"]
        + measurements["candidate_primary_score_nonzero_rows"]
        == universe.candidate_pair_count,
        "prediction score partition drifted",
    )

    artifacts = payload.get("artifacts")
    _require(isinstance(artifacts, dict) and set(artifacts) == set(ARTIFACT_CONTRACT), "artifact set drifted")
    for name, (artifact_format, rows, row_bytes) in ARTIFACT_CONTRACT.items():
        item = artifacts[name]
        _require(
            isinstance(item, dict)
            and set(item) == {"path", "format", "rows", "bytes", "sha256"}
            and item["format"] == artifact_format
            and item["rows"] == rows
            and item["bytes"] == rows * row_bytes,
            f"{name} artifact shape drifted",
        )
        _hash_shape(item.get("sha256"), f"{name} artifact hash")

    _require(
        payload.get("integrity_gates")
        == {
            "all_candidate_universe_local_hashes_and_invariants_match": True,
            "native_engine_matches_python_reference_fixture": True,
            "every_positive_source_row_reapplied_to_backbone": True,
            "backbone_csr_exact_symmetric_sorted_duplicate_free": True,
            "one_exact_score_tuple_for_every_candidate": True,
            "score_pair_keys_equal_candidate_stream_in_order": True,
            "primary_total_order_recomputed_and_equal": True,
            "missing_duplicate_extra_nonfinite_or_overflow_rows": 0,
            "human_or_llm_scoring_ranking_filtering_or_labels": False,
            "t1_source_or_outcomes_inspected": False,
        },
        "prediction integrity gate drifted",
    )
    _require(
        payload.get("seal_policy")
        == {
            "overwrite_allowed": False,
            "formula_revision_allowed": False,
            "prediction_artifact_revision_allowed": False,
            "future_integrity_drift_action": "abstain",
        },
        "prediction seal policy drifted",
    )
    claim = payload.get("claim_boundary", "")
    for phrase in (
        "unvalidated method",
        "not discoveries",
        "validated gaps",
        "scientific truths",
        "non-academic knowledge",
    ):
        _require(phrase in claim, f"prediction claim boundary omits {phrase}")
    _require(payload.get("readiness_contribution") == 0, "predictions claim readiness")

    if output_dir is not None:
        _require(scan_dir is not None, "--scan-dir is required with local prediction verification")
        local_items = {name: _local_path(output_dir, item, name) for name, item in artifacts.items()}
        local_binary = _local_path(output_dir, binary, "engine binary")
        local_conformance = _local_path(output_dir, conformance, "native conformance")
        for name, item, local in (
            *((name, artifacts[name], local_items[name]) for name in artifacts),
            ("engine binary", binary, local_binary),
            ("native conformance", conformance, local_conformance),
        ):
            _require(
                local.is_file()
                and local.stat().st_size == item["bytes"]
                and _sha256_file(local) == item["sha256"],
                f"{name} local bytes drifted",
            )
        conformance_payload = json.loads(local_conformance.read_text(encoding="utf-8"))
        _require(conformance_payload.get("passed") is True, "local native conformance drifted")
        reduced = scan_dir / "reduced"
        common = {
            "supports": reduced / "supports.u64.bin",
            "offsets": local_items["backbone_offsets"],
            "neighbors": local_items["backbone_neighbors"],
            "nodes": universe.descriptor_count,
        }
        _run_native(
            local_binary,
            "audit-backbone",
            {
                **common,
                "positive": reduced / "positive-pairs.u64u64.bin",
                "denominator": universe.distinct_pmid_count,
            },
        )
        _run_native(
            local_binary,
            "audit",
            {
                **common,
                "candidates": reduced / "candidate-keys.u64.bin",
                "weights": local_items["degree_weights"],
                "scores": local_items["candidate_scores"],
                "primary-order": local_items["primary_order"],
                "candidate-rows": universe.candidate_pair_count,
            },
        )
        scores = np.memmap(local_items["candidate_scores"], mode="r", dtype=SCORE_DTYPE)
        _require(
            int(np.count_nonzero(scores["adamic_adar_q48"] == 0)) == 69
            and int(scores["adamic_adar_q48"].max()) == 166267025613987885
            and int(scores["common_neighbors"].max()) == 4607,
            "local score measurement drifted",
        )
        weights = np.memmap(local_items["degree_weights"], mode="r", dtype=WEIGHT_DTYPE)
        _require(weights.size == 31_111 and not weights[:2].view("<u8").any(), "weight table drifted")

    return AutonomousPredictionsV1Audit(
        prediction_id=payload["id"],
        sha256=sha256_payload(payload),
        status=payload["status"],
        primary_formula=metric.primary_formula,
        backbone_edge_count=measurements["backbone_edges"],
        candidate_score_count=measurements["candidate_score_rows"],
        nonzero_score_count=measurements["candidate_primary_score_nonzero_rows"],
        readiness_contribution=0,
        local_bytes_verified=output_dir is not None,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-local", type=Path, metavar="OUTPUT_DIR")
    parser.add_argument("--scan-dir", type=Path)
    args = parser.parse_args()
    if (args.verify_local is None) != (args.scan_dir is None):
        parser.error("--verify-local and --scan-dir must be supplied together")
    audit = audit_predictions_v1(output_dir=args.verify_local, scan_dir=args.scan_dir)
    print("autonomous T0 predictions v1: structurally valid and immutable")
    print(f"canonical JSON SHA-256: {audit.sha256}")
    print(f"primary formula: {audit.primary_formula}")
    print(f"backbone edges: {audit.backbone_edge_count}")
    print(f"candidate scores: {audit.candidate_score_count}")
    print(f"nonzero primary scores: {audit.nonzero_score_count}")
    print(f"local bytes verified: {'yes' if audit.local_bytes_verified else 'not requested'}")
    print("readiness contribution: 0 (prospective outcomes do not exist yet)")


if __name__ == "__main__":
    main()
