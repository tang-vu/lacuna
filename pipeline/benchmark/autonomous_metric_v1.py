"""Build and exhaustively audit metric-v1 artifacts on an explicit data volume.

The frozen formula lives in ``autonomous_metric_v1_formula.py``.  This module
only orchestrates the native bounded-memory engine, generates the exact Decimal
degree table, proves conformance on a synthetic graph, and audits full-corpus
artifacts.  It does not interpret or publish ranked pairs.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np

from pipeline.benchmark.autonomous_candidate_index import (
    _require_non_system_volume,
    _sha256_file,
)
from pipeline.benchmark.autonomous_metric_v1_formula import (
    Q48_SCALE,
    adamic_adar_weight_q48,
    descending_integer_rank_key,
    jaccard_denominator,
    local_scores,
    preferential_attachment_score,
    prevalence_score,
    resource_allocation_weight_q48,
)
from pipeline.benchmark.validate_autonomous_candidate_universe import (
    audit_candidate_universe,
)
from pipeline.benchmark.validate_autonomous_metric_v1 import (
    audit_autonomous_metric_v1,
)
from pipeline.paths import REPO_ROOT
from pipeline.provenance import canonical_json_bytes

ENGINE_SOURCE = (
    REPO_ROOT
    / "pipeline"
    / "benchmark"
    / "native"
    / "autonomous_metric_v1_engine.cpp"
)
SCORE_DTYPE = np.dtype(
    [
        ("pair_key", "<u8"),
        ("adamic_adar_q48", "<u8"),
        ("resource_allocation_q48", "<u8"),
        ("prevalence", "<u8"),
        ("common_neighbors", "<u4"),
        ("jaccard_denominator", "<u4"),
        ("preferential_attachment", "<u8"),
    ]
)
WEIGHT_DTYPE = np.dtype(
    [("adamic_adar_q48", "<u8"), ("resource_allocation_q48", "<u8")]
)
POSITIVE_DTYPE = np.dtype([("key", "<u8"), ("count", "<u8")])
MINIMUM_FREE_BYTES = 20 * 1024**3


class AutonomousMetricV1BuildError(ValueError):
    pass


@dataclass(frozen=True)
class EngineIdentity:
    path: Path
    source_sha256: str
    binary_sha256: str
    compiler_path: str
    compiler_version: str
    command: tuple[str, ...]


@dataclass(frozen=True)
class MetricRunAudit:
    engine: EngineIdentity
    output_dir: Path
    backbone_edge_count: int
    degree_minimum: int
    degree_median: int
    degree_p90: int
    degree_p99: int
    degree_maximum: int
    score_rows: int
    primary_order_rows: int
    conformance_sha256: str


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AutonomousMetricV1BuildError(message)


def _write_or_audit_bytes(path: Path, raw: bytes) -> None:
    if path.exists():
        _require(path.is_file() and path.read_bytes() == raw, f"existing artifact drifted: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(f"{path.name}.part")
    _require(not part.exists(), f"partial artifact requires inspection: {part}")
    with part.open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(part, path)


def _write_or_audit_json(path: Path, payload: dict) -> None:
    _write_or_audit_bytes(path, canonical_json_bytes(payload))


def _compiler_version(compiler: str) -> str:
    result = subprocess.run(
        [compiler, "--version"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    first_line = result.stdout.splitlines()[0].strip() if result.stdout else ""
    _require(bool(first_line), "compiler version output is empty")
    return first_line


def compile_engine(output_dir: Path, *, compiler: str = "g++") -> EngineIdentity:
    _require_non_system_volume(output_dir)
    resolved_compiler = shutil.which(compiler)
    _require(resolved_compiler is not None, f"native compiler is unavailable: {compiler}")
    source_sha256 = _sha256_file(ENGINE_SOURCE)
    suffix = ".exe" if os.name == "nt" else ""
    binary = output_dir / "engine" / f"metric-v1-{source_sha256[:16]}{suffix}"
    command = (
        resolved_compiler,
        "-std=c++17",
        "-O3",
        "-DNDEBUG",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-o",
        str(binary),
        str(ENGINE_SOURCE),
    )
    if not binary.exists():
        binary.parent.mkdir(parents=True, exist_ok=True)
        part = binary.with_name(f"{binary.name}.part{suffix}")
        _require(not part.exists(), f"partial compiler output requires inspection: {part}")
        part_command = list(command)
        part_command[part_command.index(str(binary))] = str(part)
        result = subprocess.run(part_command, capture_output=True, text=True, encoding="utf-8")
        if result.returncode:
            raise AutonomousMetricV1BuildError(
                f"native engine compilation failed:\n{result.stdout}\n{result.stderr}"
            )
        os.replace(part, binary)
    _require(binary.is_file() and binary.stat().st_size > 0, "native engine binary is missing")
    return EngineIdentity(
        path=binary,
        source_sha256=source_sha256,
        binary_sha256=_sha256_file(binary),
        compiler_path=resolved_compiler,
        compiler_version=_compiler_version(resolved_compiler),
        command=command,
    )


def build_weight_bytes(maximum_degree: int) -> bytes:
    _require(maximum_degree >= 2, "maximum degree must be at least two")
    rows = np.zeros(maximum_degree + 1, dtype=WEIGHT_DTYPE)
    for degree in range(2, maximum_degree + 1):
        rows["adamic_adar_q48"][degree] = adamic_adar_weight_q48(degree)
        rows["resource_allocation_q48"][degree] = resource_allocation_weight_q48(degree)
    return rows.tobytes(order="C")


def write_degree_weights(path: Path, descriptor_count: int) -> str:
    raw = build_weight_bytes(descriptor_count)
    _write_or_audit_bytes(path, raw)
    return hashlib.sha256(raw).hexdigest()


def _run_engine(engine: Path, command: str, arguments: dict[str, object]) -> str:
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
    if result.returncode:
        raise AutonomousMetricV1BuildError(
            f"native engine {command} failed:\n{result.stdout}\n{result.stderr}"
        )
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="", flush=True)
    return result.stdout


def _binary_rows(rows: Iterable[tuple[int, int]], dtype: np.dtype) -> bytes:
    values = np.array(list(rows), dtype=dtype)
    return values.tobytes(order="C")


def run_conformance(engine: EngineIdentity, output_dir: Path) -> dict:
    """Prove native behavior against the Python reference on every synthetic row."""
    fixture_identity = hashlib.sha256(
        f"{engine.source_sha256}:metric-v1-conformance-v1".encode("ascii")
    ).hexdigest()
    fixture_dir = output_dir / "conformance" / fixture_identity[:16]
    fixture_dir.mkdir(parents=True, exist_ok=True)
    nodes = 5
    denominator = 100
    supports = np.array([10, 19, 20, 30, 40], dtype="<u8")
    positive_rows = (
        (0 * nodes + 2, 2),  # exact equality: excluded from backbone
        (0 * nodes + 3, 4),
        (0 * nodes + 4, 5),
        (1 * nodes + 3, 6),
        (1 * nodes + 4, 8),
        (2 * nodes + 3, 6),  # exact equality: excluded from backbone
        (2 * nodes + 4, 9),
    )
    candidate_keys = np.array(
        [0 * nodes + 1, 1 * nodes + 2, 3 * nodes + 4], dtype="<u8"
    )
    paths = {
        "supports": fixture_dir / "supports.u64.bin",
        "positive": fixture_dir / "positive.u64u64.bin",
        "candidates": fixture_dir / "candidates.u64.bin",
        "weights": fixture_dir / "weights.u64u64.bin",
        "offsets": fixture_dir / "offsets.u64.bin",
        "neighbors": fixture_dir / "neighbors.u32.bin",
        "scores": fixture_dir / "scores.v1.bin",
        "primary-order": fixture_dir / "primary-order.u64.bin",
    }
    _write_or_audit_bytes(paths["supports"], supports.tobytes())
    _write_or_audit_bytes(paths["positive"], _binary_rows(positive_rows, POSITIVE_DTYPE))
    _write_or_audit_bytes(paths["candidates"], candidate_keys.tobytes())
    _write_or_audit_bytes(paths["weights"], build_weight_bytes(nodes))
    if not paths["offsets"].exists() and not paths["neighbors"].exists():
        _run_engine(
            engine.path,
            "build-backbone",
            {
                "supports": paths["supports"],
                "positive": paths["positive"],
                "offsets": paths["offsets"],
                "neighbors": paths["neighbors"],
                "nodes": nodes,
                "denominator": denominator,
            },
        )
    _require(paths["offsets"].exists() and paths["neighbors"].exists(), "conformance backbone partial")
    _run_engine(
        engine.path,
        "audit-backbone",
        {
            "supports": paths["supports"],
            "positive": paths["positive"],
            "offsets": paths["offsets"],
            "neighbors": paths["neighbors"],
            "nodes": nodes,
            "denominator": denominator,
        },
    )
    expected_offsets = np.array([0, 2, 4, 5, 7, 10], dtype="<u8")
    expected_neighbors = np.array([3, 4, 3, 4, 4, 0, 1, 0, 1, 2], dtype="<u4")
    _require(
        paths["offsets"].read_bytes() == expected_offsets.tobytes()
        and paths["neighbors"].read_bytes() == expected_neighbors.tobytes(),
        "native backbone differs from Python conformance fixture",
    )
    if not paths["scores"].exists() and not paths["primary-order"].exists():
        _run_engine(
            engine.path,
            "score",
            {
                "supports": paths["supports"],
                "candidates": paths["candidates"],
                "offsets": paths["offsets"],
                "neighbors": paths["neighbors"],
                "weights": paths["weights"],
                "scores": paths["scores"],
                "primary-order": paths["primary-order"],
                "nodes": nodes,
                "candidate-rows": candidate_keys.size,
            },
        )
    _require(paths["scores"].exists() and paths["primary-order"].exists(), "conformance score partial")
    native_scores = np.fromfile(paths["scores"], dtype=SCORE_DTYPE)
    expected_scores = np.zeros(candidate_keys.size, dtype=SCORE_DTYPE)
    neighbor_sets = ({3, 4}, {3, 4}, {4}, {0, 1}, {0, 1, 2})
    degrees = tuple(len(row) for row in neighbor_sets)
    for index, pair_key_raw in enumerate(candidate_keys):
        pair_key = int(pair_key_raw)
        left, right = divmod(pair_key, nodes)
        common = sorted(neighbor_sets[left].intersection(neighbor_sets[right]))
        local = local_scores(degrees[node] for node in common)
        expected_scores[index] = (
            pair_key,
            local.adamic_adar_q48,
            local.resource_allocation_q48,
            prevalence_score(int(supports[left]), int(supports[right])),
            local.common_neighbors,
            jaccard_denominator(degrees[left], degrees[right], local.common_neighbors),
            preferential_attachment_score(degrees[left], degrees[right]),
        )
    _require(np.array_equal(native_scores, expected_scores), "native scores differ from Python fixture")
    expected_order = np.array(
        sorted(
            (int(key) for key in candidate_keys),
            key=lambda key: descending_integer_rank_key(
                int(expected_scores["adamic_adar_q48"][np.searchsorted(candidate_keys, key)]),
                key,
            ),
        ),
        dtype="<u8",
    )
    _require(
        paths["primary-order"].read_bytes() == expected_order.tobytes(),
        "native total order differs from Python fixture",
    )
    _run_engine(
        engine.path,
        "audit",
        {
            "supports": paths["supports"],
            "candidates": paths["candidates"],
            "offsets": paths["offsets"],
            "neighbors": paths["neighbors"],
            "weights": paths["weights"],
            "scores": paths["scores"],
            "primary-order": paths["primary-order"],
            "nodes": nodes,
            "candidate-rows": candidate_keys.size,
        },
    )
    payload = {
        "schema_version": 1,
        "kind": "autonomous_metric_v1_native_conformance",
        "fixture": "metric-v1-conformance-v1",
        "engine_source_sha256": engine.source_sha256,
        "engine_binary_sha256": engine.binary_sha256,
        "edge_rows_checked": len(positive_rows),
        "candidate_score_rows_checked": int(candidate_keys.size),
        "primary_order_rows_checked": int(candidate_keys.size),
        "python_reference_scale": Q48_SCALE,
        "passed": True,
    }
    report = fixture_dir / "conformance.json"
    _write_or_audit_json(report, payload)
    return {**payload, "path": report, "sha256": _sha256_file(report)}


def _full_engine_args(scan_dir: Path, output_dir: Path, descriptor_count: int) -> dict[str, object]:
    reduced = scan_dir / "reduced"
    return {
        "supports": reduced / "supports.u64.bin",
        "candidates": reduced / "candidate-keys.u64.bin",
        "offsets": output_dir / "backbone-offsets.u64.bin",
        "neighbors": output_dir / "backbone-neighbors.u32.bin",
        "weights": output_dir / "degree-weights.u64u64.bin",
        "scores": output_dir / "candidate-scores.v1.bin",
        "primary-order": output_dir / "primary-order.u64.bin",
        "nodes": descriptor_count,
    }


def _audit_graph_artifacts(arguments: dict[str, object], descriptor_count: int) -> tuple[int, np.ndarray]:
    offsets_path = Path(arguments["offsets"])
    neighbors_path = Path(arguments["neighbors"])
    _require(offsets_path.stat().st_size == (descriptor_count + 1) * 8, "offset byte count drifted")
    offsets = np.memmap(offsets_path, mode="r", dtype="<u8")
    _require(offsets[0] == 0 and not bool(np.any(offsets[1:] < offsets[:-1])), "offset order drifted")
    neighbor_rows = int(offsets[-1])
    _require(neighbor_rows % 2 == 0, "backbone degree sum is odd")
    _require(neighbors_path.stat().st_size == neighbor_rows * 4, "neighbor byte count drifted")
    neighbors = np.memmap(neighbors_path, mode="r", dtype="<u4")
    for node in range(descriptor_count):
        row = neighbors[int(offsets[node]) : int(offsets[node + 1])]
        _require(
            not bool(np.any(row >= descriptor_count))
            and not bool(np.any(row == node))
            and (row.size < 2 or not bool(np.any(row[1:] <= row[:-1]))),
            f"backbone neighbor invariant drifted at node {node}",
        )
    return neighbor_rows // 2, np.diff(offsets).astype("<u8", copy=False)


def _degree_statistics(degrees: np.ndarray) -> tuple[int, int, int, int, int]:
    ordered = np.sort(np.asarray(degrees, dtype="<u8"))
    size = int(ordered.size)
    _require(size > 0, "degree vector is empty")

    def nearest_rank(percentile: int) -> int:
        return int(ordered[((size - 1) * percentile + 50) // 100])

    return (
        int(ordered[0]),
        nearest_rank(50),
        nearest_rank(90),
        nearest_rank(99),
        int(ordered[-1]),
    )


def build_full_run(
    scan_dir: Path,
    output_dir: Path,
    *,
    compiler: str = "g++",
    minimum_free_bytes: int = MINIMUM_FREE_BYTES,
) -> MetricRunAudit:
    _require_non_system_volume(scan_dir)
    _require_non_system_volume(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    _require(
        shutil.disk_usage(output_dir).free >= minimum_free_bytes,
        "metric-v1 data volume has insufficient free space",
    )
    metric = audit_autonomous_metric_v1()
    universe = audit_candidate_universe(scan_dir=scan_dir)
    _require(metric.candidate_pair_count == universe.candidate_pair_count, "metric/universe row drift")
    engine = compile_engine(output_dir, compiler=compiler)
    conformance = run_conformance(engine, output_dir)
    arguments = _full_engine_args(scan_dir, output_dir, universe.descriptor_count)
    write_degree_weights(Path(arguments["weights"]), universe.descriptor_count)
    offsets_path = Path(arguments["offsets"])
    neighbors_path = Path(arguments["neighbors"])
    if not offsets_path.exists() and not neighbors_path.exists():
        output = _run_engine(
            engine.path,
            "build-backbone",
            {
                "supports": arguments["supports"],
                "positive": scan_dir / "reduced" / "positive-pairs.u64u64.bin",
                "offsets": offsets_path,
                "neighbors": neighbors_path,
                "nodes": universe.descriptor_count,
                "denominator": universe.distinct_pmid_count,
            },
        )
        print(output, end="", flush=True)
    _require(offsets_path.exists() and neighbors_path.exists(), "full backbone is partial")
    output = _run_engine(
        engine.path,
        "audit-backbone",
        {
            "supports": arguments["supports"],
            "positive": scan_dir / "reduced" / "positive-pairs.u64u64.bin",
            "offsets": offsets_path,
            "neighbors": neighbors_path,
            "nodes": universe.descriptor_count,
            "denominator": universe.distinct_pmid_count,
        },
    )
    print(output, end="", flush=True)
    edge_count, degrees = _audit_graph_artifacts(arguments, universe.descriptor_count)
    score_path = Path(arguments["scores"])
    order_path = Path(arguments["primary-order"])
    if not score_path.exists() and not order_path.exists():
        output = _run_engine(
            engine.path,
            "score",
            {
                **arguments,
                "candidate-rows": universe.candidate_pair_count,
            },
        )
        print(output, end="", flush=True)
    _require(score_path.exists() and order_path.exists(), "full scoring output is partial")
    _require(
        score_path.stat().st_size == universe.candidate_pair_count * SCORE_DTYPE.itemsize,
        "candidate score byte count drifted",
    )
    _require(
        order_path.stat().st_size == universe.candidate_pair_count * 8,
        "primary order byte count drifted",
    )
    output = _run_engine(
        engine.path,
        "audit",
        {
            **arguments,
            "candidate-rows": universe.candidate_pair_count,
        },
    )
    print(output, end="", flush=True)
    score_rows = np.memmap(score_path, mode="r", dtype=SCORE_DTYPE)
    candidate_rows = np.memmap(Path(arguments["candidates"]), mode="r", dtype="<u8")
    _require(
        np.array_equal(score_rows["pair_key"], candidate_rows),
        "score pair keys differ from candidate stream",
    )
    stats = _degree_statistics(degrees)
    return MetricRunAudit(
        engine=engine,
        output_dir=output_dir,
        backbone_edge_count=edge_count,
        degree_minimum=stats[0],
        degree_median=stats[1],
        degree_p90=stats[2],
        degree_p99=stats[3],
        degree_maximum=stats[4],
        score_rows=universe.candidate_pair_count,
        primary_order_rows=universe.candidate_pair_count,
        conformance_sha256=conformance["sha256"],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("--scan-dir", type=Path, required=True)
    build_parser.add_argument("--output-dir", type=Path, required=True)
    build_parser.add_argument("--compiler", default="g++")
    build_parser.add_argument("--minimum-free-gib", type=float, default=20.0)
    conformance_parser = subparsers.add_parser("conformance")
    conformance_parser.add_argument("--output-dir", type=Path, required=True)
    conformance_parser.add_argument("--compiler", default="g++")
    args = parser.parse_args()
    try:
        if args.command == "conformance":
            engine = compile_engine(args.output_dir, compiler=args.compiler)
            result = run_conformance(engine, args.output_dir)
            print(f"native conformance: passed ({result['candidate_score_rows_checked']} score rows)")
            print(f"conformance SHA-256: {result['sha256']}")
            return
        _require(args.minimum_free_gib >= 0, "minimum free GiB cannot be negative")
        result = build_full_run(
            args.scan_dir,
            args.output_dir,
            compiler=args.compiler,
            minimum_free_bytes=int(args.minimum_free_gib * 1024**3),
        )
        print(f"backbone edges: {result.backbone_edge_count}")
        print(
            "degree min/median/p90/p99/max: "
            f"{result.degree_minimum}/{result.degree_median}/{result.degree_p90}/"
            f"{result.degree_p99}/{result.degree_maximum}"
        )
        print(f"candidate scores audited: {result.score_rows}")
        print(f"primary order audited: {result.primary_order_rows}")
        print("readiness contribution: 0 (unsealed predictions and no prospective outcomes)")
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        raise SystemExit(str(exc)) from None


if __name__ == "__main__":
    main()
