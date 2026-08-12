"""Execute the frozen BioASQ v2 formula on development cases only.

The module has no held-out mode. It first creates a case-blind compact corpus and sparse edge files
for the two development cutoffs, then applies the checksum-pinned Decimal formula only to the 11
development seeds. Exact integer rational bounds screen candidates far from the target rank
boundary; the target and every boundary-intersecting candidate are evaluated in the frozen Python
Decimal order. Generated cache files stay ignored; the review artifact refuses overwrite.

Prepare the reusable graph cache without computing any case score:

    python -m pipeline.benchmark.bioasq_v2_development \
      data/medline-baseline/bioasq/PubMedWithMeSH.zip --prepare-only

Run development after the graph cache exists:

    python -m pipeline.benchmark.bioasq_v2_development \
      data/medline-baseline/bioasq/PubMedWithMeSH.zip
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from array import array
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from pathlib import Path
from xml.etree import ElementTree

import numpy as np

from pipeline.benchmark.bioasq_snapshot import (
    iter_articles,
    open_snapshot_text,
    validate_article,
)
from pipeline.benchmark.validate_bioasq_formula_v2 import (
    FORMULA_PATH,
    audit_bioasq_formula_v2,
)
from pipeline.benchmark.validate_bioasq_pilot_v2 import (
    SUCCESSOR_PATH,
    audit_bioasq_pilot_v2,
)
from pipeline.paths import MEDLINE_BASELINE_DIR, MESH_CACHE_DIR, REPO_ROOT

SNAPSHOT_PATH = MEDLINE_BASELINE_DIR / "bioasq" / "PubMedWithMeSH.zip"
MESH_PATH = MESH_CACHE_DIR / "desc2013.gz"
V1_PROTOCOL_PATH = REPO_ROOT / "benchmarks" / "v3" / "bioasq-pilot.json"
COMPATIBILITY_PATH = (
    REPO_ROOT / "benchmarks" / "v3" / "manifests" / "bioasq-pilot-compatibility.json"
)
NATIVE_SOURCE_PATH = (
    REPO_ROOT / "pipeline" / "benchmark" / "native" / "bioasq_pair_counts.cpp"
)
SCORE_BOUNDS_SOURCE_PATH = (
    REPO_ROOT / "pipeline" / "benchmark" / "native" / "bioasq_score_bounds.cpp"
)
EXECUTOR_SOURCE_PATH = Path(__file__).resolve()
NEGATIVE_QUEUE_PATH = REPO_ROOT / "artifacts" / "negative-candidates.json"
DEVELOPMENT_CUTOFFS = (2011, 2012)
SUPPORT_THRESHOLDS = (10, 5)
FORMULA_QUANTUM = Decimal("0.000000000000001")
DECIMAL_PRECISION = 40
CORPUS_MAGIC = b"LCNABQ2\0"
EDGE_MAGIC = b"LCEDGE1\0"
CORPUS_HEADER = struct.Struct("<8sIBHH")
DOCUMENT_HEADER = struct.Struct("<BH")
EDGE_HEADER = struct.Struct("<8sIHQ")
EDGE_DTYPE = np.dtype([("left", "<u2"), ("right", "<u2"), ("count", "<u4")])
EDGE_CHUNK_SIZE = 1_000_000
BOUNDS_MAGIC = b"LCBNDS1\0"
BOUNDS_HEADER = struct.Struct("<8sIHHHHBBQ")
BOUNDS_RECORD_SIZE = 40
TARGET_BRIDGE_RECORD = struct.Struct("<HII")
BOUND_SCALE_EXPONENT = 21
BOUND_SCALE = 10**BOUND_SCALE_EXPONENT
BOUND_GUARD_SCALED_UNITS = 10**6


class BioasqDevelopmentError(ValueError):
    pass


@dataclass(frozen=True)
class DevelopmentCase:
    id: str
    kind: str
    cutoff: str
    endpoint_a: dict[str, str]
    target_c: dict[str, str]
    label_scope: str


@dataclass(frozen=True)
class NodeIndex:
    uis: tuple[str, ...]
    labels: tuple[str, ...]
    normalised_label_to_id: dict[str, int]
    ui_to_id: dict[str, int]


@dataclass(frozen=True)
class GraphCache:
    directory: Path
    compact_corpus: Path
    nodes_path: Path
    edge_paths: dict[int, Path]
    score_bounds_executable: Path
    manifest_path: Path
    manifest: dict


@dataclass(frozen=True)
class EdgeGraph:
    path: Path
    cutoff_year: int
    node_count: int
    edge_count: int
    support: np.memmap
    edges: np.memmap


@dataclass(frozen=True)
class ScoreBounds:
    node_count: int
    cutoff_year: int
    threshold: int
    seed_id: int
    target_id: int
    lower: tuple[int, ...]
    upper: tuple[int, ...]
    seed_counts: tuple[int, ...]
    bridge_counts: tuple[int, ...]
    target_paths: tuple[tuple[int, int, int], ...]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BioasqDevelopmentError(message)


def _normalise(value: str) -> str:
    return " ".join(value.casefold().split())


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_identity(path: Path) -> dict[str, object]:
    return {
        "path": path.relative_to(REPO_ROOT).as_posix(),
        "sha256": _sha256_file(path),
        "bytes": path.stat().st_size,
    }


def _load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(payload, dict), f"{path}: expected a JSON object")
    return payload


def _write_new_json(path: Path, payload: dict) -> None:
    if path.exists():
        raise BioasqDevelopmentError(f"refusing to overwrite existing output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")


def load_development_cases() -> list[DevelopmentCase]:
    audit_bioasq_pilot_v2()
    v1 = _load_json(V1_PROTOCOL_PATH)
    queue = _load_json(NEGATIVE_QUEUE_PATH)
    cases = [
        DevelopmentCase(
            id=item["id"],
            kind="source_labeled_positive",
            cutoff=item["cutoff"],
            endpoint_a=item["endpoint_a"],
            target_c=item["target_c"],
            label_scope=v1["case_population"]["positives"]["label_scope"],
        )
        for item in v1["case_population"]["positives"]["cases"]
        if item["split"] == "development"
    ]
    control_scope = v1["case_population"]["controls"]["label_scope"]
    cases.extend(
        DevelopmentCase(
            id=item["id"],
            kind=item["kind"],
            cutoff=item["cutoff"],
            endpoint_a={
                "descriptor_ui": item["concepts"]["a"]["descriptor_ui"],
                "descriptor_label": item["concepts"]["a"]["descriptor_label"],
            },
            target_c={
                "descriptor_ui": item["concepts"]["c"]["descriptor_ui"],
                "descriptor_label": item["concepts"]["c"]["descriptor_label"],
            },
            label_scope=control_scope,
        )
        for item in queue["candidates"]
        if item["proposed_split"] == "development"
    )
    _require(len(cases) == 11, "executor requires exactly 11 development cases")
    _require(
        {int(case.cutoff[:4]) for case in cases} == set(DEVELOPMENT_CUTOFFS),
        "development cutoff population drifted",
    )
    _require(
        sum(case.kind == "source_labeled_positive" for case in cases) == 3
        and sum(case.kind == "hard_negative" for case in cases) == 4
        and sum(case.kind == "distant_negative" for case in cases) == 4,
        "development case-kind counts drifted",
    )
    return cases


def load_node_index(mesh_path: Path = MESH_PATH) -> NodeIndex:
    records: list[tuple[str, str]] = []
    with gzip.open(mesh_path, "rb") as stream:
        for _, element in ElementTree.iterparse(stream, events=("end",)):
            if element.tag.rsplit("}", 1)[-1] != "DescriptorRecord":
                continue
            ui = element.findtext("./DescriptorUI") or ""
            label = element.findtext("./DescriptorName/String") or ""
            _require(bool(ui and label), "MeSH descriptor is missing UI or label")
            records.append((ui, label))
            element.clear()
    records.sort()
    _require(len(records) == len({ui for ui, _ in records}), "duplicate MeSH descriptor UI")
    _require(len(records) <= 65_535, "MeSH descriptor set exceeds compact uint16 identity")
    uis = tuple(ui for ui, _ in records)
    labels = tuple(label for _, label in records)
    ui_to_id = {ui: index for index, ui in enumerate(uis)}
    normalised_label_to_id: dict[str, int] = {}
    for node_id, label in enumerate(labels):
        normalised = _normalise(label)
        _require(
            normalised not in normalised_label_to_id,
            f"ambiguous normalized MeSH descriptor label: {label}",
        )
        normalised_label_to_id[normalised] = node_id
    return NodeIndex(
        uis=uis,
        labels=labels,
        normalised_label_to_id=normalised_label_to_id,
        ui_to_id=ui_to_id,
    )


def _expected_source_identities(snapshot_path: Path, mesh_path: Path) -> tuple[dict, dict]:
    compatibility = _load_json(COMPATIBILITY_PATH)
    snapshot = compatibility["inputs"]["snapshot_transport"]
    mesh = compatibility["inputs"]["descriptor_vocabulary"]
    _require(
        snapshot_path.is_file()
        and snapshot_path.stat().st_size == snapshot["bytes"]
        and _sha256_file(snapshot_path) == snapshot["sha256"],
        "local BioASQ snapshot differs from the pinned compatibility input",
    )
    _require(
        mesh_path.is_file()
        and mesh_path.stat().st_size == mesh["bytes"]
        and _sha256_file(mesh_path) == mesh["sha256"],
        "local MeSH archive differs from the pinned compatibility input",
    )
    return snapshot, mesh


def _cache_directory(cache_root: Path) -> Path:
    formula_hash = _sha256_file(FORMULA_PATH)
    builder_hash = _sha256_file(EXECUTOR_SOURCE_PATH)
    return cache_root / f"bioasq-v2-jaccard-{formula_hash[:12]}-{builder_hash[:12]}"


def _cache_paths(cache_root: Path) -> GraphCache:
    directory = _cache_directory(cache_root)
    return GraphCache(
        directory=directory,
        compact_corpus=directory / "development-cutoffs.corpus.bin",
        nodes_path=directory / "nodes.json",
        edge_paths={
            2011: directory / "edges-2011.bin",
            2012: directory / "edges-2012.bin",
        },
        score_bounds_executable=directory / "bioasq_score_bounds.exe",
        manifest_path=directory / "cache-manifest.json",
        manifest={},
    )


def _compact_metadata_payload(
    *,
    index: NodeIndex,
    snapshot: dict,
    mesh: dict,
    scanned_articles: int,
    scanned_assignments: int,
    included_articles: int,
    included_assignments: int,
) -> dict:
    return {
        "schema_version": 1,
        "purpose": "case_blind_graph_input_for_development_cutoffs_without_metric_output",
        "source_snapshot": {"sha256": snapshot["sha256"], "bytes": snapshot["bytes"]},
        "descriptor_vocabulary": {
            "sha256": mesh["sha256"],
            "bytes": mesh["bytes"],
            "descriptor_count": mesh["descriptor_count"],
        },
        "cutoff_years": list(DEVELOPMENT_CUTOFFS),
        "node_count": len(index.uis),
        "nodes": [
            {"dense_id": node_id, "descriptor_ui": ui, "descriptor_label": index.labels[node_id]}
            for node_id, ui in enumerate(index.uis)
        ],
        "scanned_article_count": scanned_articles,
        "scanned_mesh_assignment_count": scanned_assignments,
        "included_article_count_through_2012": included_articles,
        "included_mesh_assignment_count_through_2012": included_assignments,
        "metric_outputs_materialized": False,
    }


def _write_compact_corpus(
    snapshot_path: Path,
    destination: Path,
    nodes_path: Path,
    *,
    index: NodeIndex,
    snapshot_identity: dict,
    mesh_identity: dict,
) -> dict:
    if destination.exists() or nodes_path.exists():
        raise BioasqDevelopmentError("refusing to overwrite partial graph input cache")
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".partial")
    partial_nodes = nodes_path.with_suffix(nodes_path.suffix + ".partial")
    if partial.exists() or partial_nodes.exists():
        raise BioasqDevelopmentError("partial graph input cache exists; inspect it before retrying")
    scanned_articles = 0
    scanned_assignments = 0
    included_articles = 0
    included_assignments = 0
    bucket_articles = [0, 0]
    bucket_assignments = [0, 0]
    if sys.byteorder != "little":
        raise BioasqDevelopmentError("compact corpus writer requires a little-endian host")
    with partial.open("wb") as output:
        output.write(
            CORPUS_HEADER.pack(
                CORPUS_MAGIC,
                len(index.uis),
                2,
                DEVELOPMENT_CUTOFFS[0],
                DEVELOPMENT_CUTOFFS[1],
            )
        )
        with open_snapshot_text(snapshot_path) as (stream, _container):
            for article in iter_articles(stream):
                scanned_articles += 1
                _pmid, year, assigned, _canonical, _raw_year = validate_article(
                    article, scanned_articles
                )
                _require(year is not None, f"article {scanned_articles}: unparseable year")
                scanned_assignments += len(assigned)
                if year > DEVELOPMENT_CUTOFFS[-1]:
                    continue
                bucket = 0 if year <= DEVELOPMENT_CUTOFFS[0] else 1
                dense_ids = sorted(
                    index.normalised_label_to_id.get(_normalise(label), -1)
                    for label in assigned
                )
                _require(
                    all(node_id >= 0 for node_id in dense_ids),
                    f"article {scanned_articles}: label is absent from MeSH 2013",
                )
                _require(
                    len(dense_ids) == len(set(dense_ids)),
                    f"article {scanned_articles}: duplicate descriptor identity",
                )
                _require(len(dense_ids) <= 65_535, "article descriptor count exceeds uint16")
                output.write(DOCUMENT_HEADER.pack(bucket, len(dense_ids)))
                encoded = array("H", dense_ids)
                encoded.tofile(output)
                included_articles += 1
                included_assignments += len(dense_ids)
                bucket_articles[bucket] += 1
                bucket_assignments[bucket] += len(dense_ids)
    expected = _load_json(COMPATIBILITY_PATH)["measurement"]
    _require(
        scanned_articles == expected["article_count_scanned"]
        and scanned_assignments == expected["mesh_assignment_count_scanned"]
        and included_articles == expected["included_article_count_by_cutoff"]["2012"],
        "compact corpus aggregate counts differ from the pinned compatibility audit",
    )
    metadata = _compact_metadata_payload(
        index=index,
        snapshot=snapshot_identity,
        mesh=mesh_identity,
        scanned_articles=scanned_articles,
        scanned_assignments=scanned_assignments,
        included_articles=included_articles,
        included_assignments=included_assignments,
    )
    metadata["bucket_article_counts"] = {
        "through_2011": bucket_articles[0],
        "2012_only": bucket_articles[1],
    }
    metadata["bucket_assignment_counts"] = {
        "through_2011": bucket_assignments[0],
        "2012_only": bucket_assignments[1],
    }
    partial_nodes.write_text(json.dumps(metadata, indent=1) + "\n", encoding="utf-8")
    partial.replace(destination)
    partial_nodes.replace(nodes_path)
    return metadata


def _compile_native_helper(cache: GraphCache) -> tuple[Path, str]:
    compiler = shutil.which("g++")
    _require(compiler is not None, "g++ is required to build the case-blind pair counter")
    executable = cache.directory / "bioasq_pair_counts.exe"
    compile_manifest = cache.directory / "native-build.json"
    source_sha256 = _sha256_file(NATIVE_SOURCE_PATH)
    version = subprocess.run(
        [compiler, "--version"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()[0]
    if executable.exists() and compile_manifest.exists():
        prior = _load_json(compile_manifest)
        _require(
            prior.get("source_sha256") == source_sha256
            and prior.get("compiler_version") == version
            and prior.get("executable_sha256") == _sha256_file(executable),
            "native helper cache identity drifted",
        )
        return executable, version
    _require(
        not executable.exists() and not compile_manifest.exists(),
        "incomplete native helper cache exists",
    )
    cache.directory.mkdir(parents=True, exist_ok=True)
    partial = executable.with_suffix(".partial.exe")
    _require(not partial.exists(), "partial native helper exists")
    command = [
        compiler,
        "-O3",
        "-std=c++20",
        "-Wall",
        "-Wextra",
        "-Werror",
        str(NATIVE_SOURCE_PATH),
        "-o",
        str(partial),
    ]
    subprocess.run(command, check=True)
    partial.replace(executable)
    _write_new_json(
        compile_manifest,
        {
            "schema_version": 1,
            "source_sha256": source_sha256,
            "compiler_version": version,
            "command": command,
            "executable_sha256": _sha256_file(executable),
        },
    )
    return executable, version


def _compile_score_bounds_helper(cache: GraphCache, compiler_version: str) -> Path:
    compiler = shutil.which("g++")
    _require(compiler is not None, "g++ is required to build the exact rank screener")
    executable = cache.score_bounds_executable
    compile_manifest = cache.directory / "score-bounds-native-build.json"
    source_sha256 = _sha256_file(SCORE_BOUNDS_SOURCE_PATH)
    if executable.exists() and compile_manifest.exists():
        prior = _load_json(compile_manifest)
        _require(
            prior.get("source_sha256") == source_sha256
            and prior.get("compiler_version") == compiler_version
            and prior.get("executable_sha256") == _sha256_file(executable),
            "rank screener native helper cache identity drifted",
        )
        return executable
    _require(
        not executable.exists() and not compile_manifest.exists(),
        "incomplete rank screener helper cache exists",
    )
    partial = executable.with_suffix(".partial.exe")
    _require(not partial.exists(), "partial rank screener helper exists")
    command = [
        compiler,
        "-O3",
        "-std=c++20",
        "-Wall",
        "-Wextra",
        "-Werror",
        str(SCORE_BOUNDS_SOURCE_PATH),
        "-o",
        str(partial),
    ]
    subprocess.run(command, check=True)
    partial.replace(executable)
    _write_new_json(
        compile_manifest,
        {
            "schema_version": 1,
            "source_sha256": source_sha256,
            "compiler_version": compiler_version,
            "command": command,
            "executable_sha256": _sha256_file(executable),
        },
    )
    return executable


def _read_edge_header(path: Path) -> dict:
    with path.open("rb") as stream:
        raw = stream.read(EDGE_HEADER.size)
    _require(len(raw) == EDGE_HEADER.size, f"truncated edge header: {path}")
    magic, node_count, cutoff, edge_count = EDGE_HEADER.unpack(raw)
    _require(magic == EDGE_MAGIC, f"edge magic mismatch: {path}")
    expected_bytes = EDGE_HEADER.size + node_count * 4 + edge_count * EDGE_DTYPE.itemsize
    _require(path.stat().st_size == expected_bytes, f"edge byte length mismatch: {path}")
    return {
        "node_count": node_count,
        "cutoff_year": cutoff,
        "edge_count": edge_count,
        "bytes": expected_bytes,
        "sha256": _sha256_file(path),
    }


def _build_edge_files(cache: GraphCache, executable: Path) -> dict[int, dict]:
    if any(path.exists() for path in cache.edge_paths.values()):
        raise BioasqDevelopmentError("incomplete edge cache exists without a cache manifest")
    partial_paths = {
        year: path.with_suffix(path.suffix + ".partial")
        for year, path in cache.edge_paths.items()
    }
    _require(
        not any(path.exists() for path in partial_paths.values()),
        "partial edge cache exists; inspect it before retrying",
    )
    result = subprocess.run(
        [
            str(executable),
            str(cache.compact_corpus),
            str(partial_paths[2011]),
            str(partial_paths[2012]),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    for year, partial in partial_paths.items():
        partial.replace(cache.edge_paths[year])
    headers = {year: _read_edge_header(path) for year, path in cache.edge_paths.items()}
    _require(
        headers[2011]["cutoff_year"] == 2011
        and headers[2012]["cutoff_year"] == 2012
        and headers[2011]["node_count"] == headers[2012]["node_count"],
        "native edge outputs have incompatible headers",
    )
    headers[2011]["native_stdout"] = result.stdout.strip()
    return headers


def prepare_graph_cache(
    snapshot_path: Path,
    *,
    mesh_path: Path = MESH_PATH,
    cache_root: Path = REPO_ROOT / "data" / "cache",
) -> GraphCache:
    audit_bioasq_formula_v2()
    load_development_cases()
    snapshot_identity, mesh_identity = _expected_source_identities(snapshot_path, mesh_path)
    cache = _cache_paths(cache_root)
    if cache.manifest_path.exists():
        manifest = _load_json(cache.manifest_path)
        _require(
            manifest.get("formula_contract", {}).get("sha256") == _sha256_file(FORMULA_PATH)
            and manifest.get("builder_source", {}).get("sha256")
            == _sha256_file(EXECUTOR_SOURCE_PATH)
            and manifest.get("native_pair_counter_source", {}).get("sha256")
            == _sha256_file(NATIVE_SOURCE_PATH)
            and manifest.get("native_rank_screener_source", {}).get("sha256")
            == _sha256_file(SCORE_BOUNDS_SOURCE_PATH)
            and manifest.get("source_snapshot") == {
                "sha256": snapshot_identity["sha256"],
                "bytes": snapshot_identity["bytes"],
            }
            and manifest.get("descriptor_vocabulary", {}).get("sha256")
            == mesh_identity["sha256"],
            "graph cache manifest input identity drifted",
        )
        for relative_name, identity in manifest["generated_files"].items():
            generated = cache.directory / relative_name
            _require(
                generated.is_file()
                and generated.stat().st_size == identity["bytes"]
                and _sha256_file(generated) == identity["sha256"],
                f"graph cache file drifted: {relative_name}",
            )
        return GraphCache(**{**cache.__dict__, "manifest": manifest})

    _require(
        not cache.directory.exists()
        or not any(cache.directory.iterdir()),
        "unmanifested graph cache directory is not empty",
    )
    cache.directory.mkdir(parents=True, exist_ok=True)
    index = load_node_index(mesh_path)
    metadata = _write_compact_corpus(
        snapshot_path,
        cache.compact_corpus,
        cache.nodes_path,
        index=index,
        snapshot_identity=snapshot_identity,
        mesh_identity=mesh_identity,
    )
    executable, compiler_version = _compile_native_helper(cache)
    score_bounds_executable = _compile_score_bounds_helper(cache, compiler_version)
    edge_headers = _build_edge_files(cache, executable)
    generated_paths = [
        cache.compact_corpus,
        cache.nodes_path,
        cache.directory / "native-build.json",
        executable,
        cache.directory / "score-bounds-native-build.json",
        score_bounds_executable,
        cache.edge_paths[2011],
        cache.edge_paths[2012],
    ]
    manifest = {
        "schema_version": 1,
        "purpose": "case_blind_graph_cache_without_metric_output",
        "formula_contract": _file_identity(FORMULA_PATH),
        "successor_protocol": _file_identity(SUCCESSOR_PATH),
        "builder_source": _file_identity(EXECUTOR_SOURCE_PATH),
        "native_pair_counter_source": _file_identity(NATIVE_SOURCE_PATH),
        "native_rank_screener_source": _file_identity(SCORE_BOUNDS_SOURCE_PATH),
        "source_snapshot": {
            "sha256": snapshot_identity["sha256"],
            "bytes": snapshot_identity["bytes"],
        },
        "descriptor_vocabulary": {
            "sha256": mesh_identity["sha256"],
            "bytes": mesh_identity["bytes"],
        },
        "compiler_version": compiler_version,
        "node_count": metadata["node_count"],
        "cutoff_years": list(DEVELOPMENT_CUTOFFS),
        "edge_headers": {str(year): header for year, header in edge_headers.items()},
        "generated_files": {
            generated.name: {
                "sha256": _sha256_file(generated),
                "bytes": generated.stat().st_size,
            }
            for generated in generated_paths
        },
        "case_identities_or_labels_stored": False,
        "metric_outputs_materialized": False,
    }
    _write_new_json(cache.manifest_path, manifest)
    return GraphCache(**{**cache.__dict__, "manifest": manifest})


def load_edge_graph(path: Path, expected_cutoff: int) -> EdgeGraph:
    header = _read_edge_header(path)
    _require(header["cutoff_year"] == expected_cutoff, "edge cutoff differs from case cutoff")
    support = np.memmap(
        path,
        dtype="<u4",
        mode="r",
        offset=EDGE_HEADER.size,
        shape=(header["node_count"],),
    )
    edges = np.memmap(
        path,
        dtype=EDGE_DTYPE,
        mode="r",
        offset=EDGE_HEADER.size + header["node_count"] * 4,
        shape=(header["edge_count"],),
    )
    return EdgeGraph(
        path=path,
        cutoff_year=expected_cutoff,
        node_count=header["node_count"],
        edge_count=header["edge_count"],
        support=support,
        edges=edges,
    )


def decimal_jaccard(cooccurrence: int, left_support: int, right_support: int) -> Decimal:
    _require(cooccurrence > 0, "Jaccard requires a positive edge count")
    _require(
        cooccurrence <= min(left_support, right_support),
        "edge count exceeds descriptor support",
    )
    denominator = left_support + right_support - cooccurrence
    _require(denominator > 0, "Jaccard denominator must be positive")
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        context.rounding = ROUND_HALF_EVEN
        return Decimal(cooccurrence) / Decimal(denominator)


def _edge_chunks(edges: np.memmap):
    for start in range(0, len(edges), EDGE_CHUNK_SIZE):
        yield edges[start : start + EDGE_CHUNK_SIZE]


def _seed_neighbours(graph: EdgeGraph, seed_id: int, eligible: np.ndarray) -> dict[int, int]:
    neighbours: dict[int, int] = {}
    for chunk in _edge_chunks(graph.edges):
        mask = (chunk["left"] == seed_id) | (chunk["right"] == seed_id)
        selected = chunk[mask]
        for left, right, count in zip(
            selected["left"].tolist(),
            selected["right"].tolist(),
            selected["count"].tolist(),
            strict=True,
        ):
            other = right if left == seed_id else left
            if eligible[other]:
                neighbours[other] = count
    return neighbours


def score_seed(
    graph: EdgeGraph,
    *,
    seed_id: int,
    target_id: int,
    threshold: int,
    node_index: NodeIndex,
    top_bridge_limit: int = 20,
) -> dict:
    _require(threshold in SUPPORT_THRESHOLDS, "unsupported formula support threshold")
    _require(0 <= seed_id < graph.node_count, "seed is outside graph node range")
    _require(0 <= target_id < graph.node_count, "target is outside graph node range")
    eligible = np.asarray(graph.support >= threshold)
    _require(eligible[seed_id] and eligible[target_id], "case endpoint is ineligible")
    neighbours = _seed_neighbours(graph, seed_id, eligible)
    jaccard_from_seed = {
        node_id: decimal_jaccard(
            count,
            int(graph.support[seed_id]),
            int(graph.support[node_id]),
        )
        for node_id, count in neighbours.items()
    }
    is_neighbour = np.zeros(graph.node_count, dtype=np.bool_)
    if neighbours:
        is_neighbour[np.fromiter(neighbours, dtype=np.int64)] = True
    scores = [Decimal(0) for _ in range(graph.node_count)]
    target_bridges: list[dict] = []
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        context.rounding = ROUND_HALF_EVEN
        for chunk in _edge_chunks(graph.edges):
            left_values = chunk["left"]
            right_values = chunk["right"]
            mask = (
                eligible[left_values]
                & eligible[right_values]
                & (is_neighbour[left_values] | is_neighbour[right_values])
            )
            selected = chunk[mask]
            for left, right, count in zip(
                selected["left"].tolist(),
                selected["right"].tolist(),
                selected["count"].tolist(),
                strict=True,
            ):
                edge_weight = decimal_jaccard(
                    count,
                    int(graph.support[left]),
                    int(graph.support[right]),
                )
                if is_neighbour[left] and right != seed_id:
                    contribution = min(jaccard_from_seed[left], edge_weight)
                    scores[right] += contribution
                    if right == target_id:
                        target_bridges.append(
                            {
                                "bridge_id": left,
                                "ab_article_count": neighbours[left],
                                "bc_article_count": count,
                                "jaccard_ab": jaccard_from_seed[left],
                                "jaccard_bc": edge_weight,
                                "path_contribution": contribution,
                            }
                        )
                if is_neighbour[right] and left != seed_id:
                    contribution = min(jaccard_from_seed[right], edge_weight)
                    scores[left] += contribution
                    if left == target_id:
                        target_bridges.append(
                            {
                                "bridge_id": right,
                                "ab_article_count": neighbours[right],
                                "bc_article_count": count,
                                "jaccard_ab": jaccard_from_seed[right],
                                "jaccard_bc": edge_weight,
                                "path_contribution": contribution,
                            }
                        )
        persisted = [
            score.quantize(FORMULA_QUANTUM, rounding=ROUND_HALF_EVEN)
            if eligible[node_id] and node_id != seed_id
            else None
            for node_id, score in enumerate(scores)
        ]
    target_score = persisted[target_id]
    _require(target_score is not None, "target persisted score is missing")
    eligible_scores = [value for value in persisted if value is not None]
    eligible_candidate_count = int(eligible.sum()) - 1
    _require(
        len(eligible_scores) == eligible_candidate_count,
        "eligible candidate denominator drifted",
    )
    worst_tie_rank = sum(value >= target_score for value in eligible_scores)
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        rank_fraction = Decimal(worst_tie_rank) / Decimal(eligible_candidate_count)
    target_bridges.sort(
        key=lambda item: (-item["path_contribution"], node_index.uis[item["bridge_id"]])
    )
    rendered_bridges = [
        {
            "descriptor_ui": node_index.uis[item["bridge_id"]],
            "descriptor_label": node_index.labels[item["bridge_id"]],
            "ab_article_count": item["ab_article_count"],
            "bc_article_count": item["bc_article_count"],
            "jaccard_ab": format(item["jaccard_ab"], "f"),
            "jaccard_bc": format(item["jaccard_bc"], "f"),
            "path_contribution": format(
                item["path_contribution"].quantize(
                    FORMULA_QUANTUM,
                    rounding=ROUND_HALF_EVEN,
                ),
                "f",
            ),
        }
        for item in target_bridges[:top_bridge_limit]
    ]
    return {
        "minimum_support_articles": threshold,
        "endpoint_a_article_support": int(graph.support[seed_id]),
        "target_c_article_support": int(graph.support[target_id]),
        "direct_ac_article_count": neighbours.get(target_id, 0),
        "eligible_candidate_count": eligible_candidate_count,
        "target_persisted_score": format(target_score, "f"),
        "target_worst_tie_rank": worst_tie_rank,
        "target_rank_fraction": format(rank_fraction, "f"),
        "target_top_5_percent": worst_tie_rank * 20 <= eligible_candidate_count,
        "target_below_median": worst_tie_rank * 2 > eligible_candidate_count,
        "target_bridge_count": len(target_bridges),
        "top_target_bridges": rendered_bridges,
    }


def _run_score_bounds(
    graph: EdgeGraph,
    *,
    executable: Path,
    seed_id: int,
    target_id: int,
    threshold: int,
) -> ScoreBounds:
    with tempfile.TemporaryDirectory(prefix="lacuna-bioasq-bounds-") as temporary:
        output_path = Path(temporary) / "bounds.bin"
        subprocess.run(
            [
                str(executable),
                str(graph.path),
                str(seed_id),
                str(target_id),
                str(threshold),
                str(output_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        with output_path.open("rb") as stream:
            raw_header = stream.read(BOUNDS_HEADER.size)
            _require(len(raw_header) == BOUNDS_HEADER.size, "truncated score-bounds header")
            (
                magic,
                node_count,
                cutoff_year,
                measured_threshold,
                measured_seed,
                measured_target,
                scale_exponent,
                reserved,
                target_bridge_count,
            ) = BOUNDS_HEADER.unpack(raw_header)
            _require(
                magic == BOUNDS_MAGIC
                and node_count == graph.node_count
                and cutoff_year == graph.cutoff_year
                and measured_threshold == threshold
                and measured_seed == seed_id
                and measured_target == target_id
                and scale_exponent == BOUND_SCALE_EXPONENT
                and reserved == 0,
                "score-bounds header differs from the requested run",
            )
            lower: list[int] = []
            upper: list[int] = []
            seed_counts: list[int] = []
            bridge_counts: list[int] = []
            for _ in range(node_count):
                record = stream.read(BOUNDS_RECORD_SIZE)
                _require(len(record) == BOUNDS_RECORD_SIZE, "truncated score-bounds record")
                lower.append(int.from_bytes(record[0:16], "little"))
                upper.append(int.from_bytes(record[16:32], "little"))
                seed_counts.append(struct.unpack_from("<I", record, 32)[0])
                bridge_counts.append(struct.unpack_from("<I", record, 36)[0])
            target_paths = []
            for _ in range(target_bridge_count):
                raw_bridge = stream.read(TARGET_BRIDGE_RECORD.size)
                _require(
                    len(raw_bridge) == TARGET_BRIDGE_RECORD.size,
                    "truncated target bridge record",
                )
                target_paths.append(TARGET_BRIDGE_RECORD.unpack(raw_bridge))
            _require(not stream.read(1), "unexpected trailing score-bounds data")
    _require(
        all(left <= right for left, right in zip(lower, upper, strict=True)),
        "score-bounds interval is inverted",
    )
    return ScoreBounds(
        node_count=node_count,
        cutoff_year=cutoff_year,
        threshold=threshold,
        seed_id=seed_id,
        target_id=target_id,
        lower=tuple(lower),
        upper=tuple(upper),
        seed_counts=tuple(seed_counts),
        bridge_counts=tuple(bridge_counts),
        target_paths=tuple(target_paths),
    )


def _exact_candidate_from_paths(
    graph: EdgeGraph,
    *,
    seed_id: int,
    candidate_id: int,
    paths: list[tuple[int, int, int]] | tuple[tuple[int, int, int], ...],
) -> tuple[Decimal, list[dict]]:
    ordered = sorted(paths, key=lambda item: item[0])
    _require(
        len(ordered) == len({bridge_id for bridge_id, _, _ in ordered}),
        "candidate contains a duplicate bridge identity",
    )
    total = Decimal(0)
    rendered: list[dict] = []
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        context.rounding = ROUND_HALF_EVEN
        for bridge_id, ab_count, bc_count in ordered:
            jaccard_ab = decimal_jaccard(
                ab_count,
                int(graph.support[seed_id]),
                int(graph.support[bridge_id]),
            )
            jaccard_bc = decimal_jaccard(
                bc_count,
                int(graph.support[bridge_id]),
                int(graph.support[candidate_id]),
            )
            contribution = min(jaccard_ab, jaccard_bc)
            total += contribution
            rendered.append(
                {
                    "bridge_id": bridge_id,
                    "ab_article_count": ab_count,
                    "bc_article_count": bc_count,
                    "jaccard_ab": jaccard_ab,
                    "jaccard_bc": jaccard_bc,
                    "path_contribution": contribution,
                }
            )
    return total, rendered


def _extract_candidate_paths(
    graph: EdgeGraph,
    *,
    candidate_ids: list[int],
    seed_counts: tuple[int, ...],
    eligible: np.ndarray,
) -> dict[int, list[tuple[int, int, int]]]:
    paths = {candidate_id: [] for candidate_id in candidate_ids}
    if not candidate_ids:
        return paths
    wanted = np.zeros(graph.node_count, dtype=np.bool_)
    wanted[candidate_ids] = True
    seed_neighbour = np.asarray(seed_counts, dtype=np.uint32) > 0
    for chunk in _edge_chunks(graph.edges):
        left_values = chunk["left"]
        right_values = chunk["right"]
        mask = eligible[left_values] & eligible[right_values] & (
            (wanted[right_values] & seed_neighbour[left_values])
            | (wanted[left_values] & seed_neighbour[right_values])
        )
        selected = chunk[mask]
        for left, right, count in zip(
            selected["left"].tolist(),
            selected["right"].tolist(),
            selected["count"].tolist(),
            strict=True,
        ):
            if wanted[right] and seed_counts[left] > 0:
                paths[right].append((left, seed_counts[left], count))
            if wanted[left] and seed_counts[right] > 0:
                paths[left].append((right, seed_counts[right], count))
    return paths


def score_seed_with_bounds(
    graph: EdgeGraph,
    *,
    executable: Path,
    seed_id: int,
    target_id: int,
    threshold: int,
    node_index: NodeIndex,
    top_bridge_limit: int = 20,
) -> dict:
    _require(threshold in SUPPORT_THRESHOLDS, "unsupported formula support threshold")
    eligible = np.asarray(graph.support >= threshold)
    _require(eligible[seed_id] and eligible[target_id], "case endpoint is ineligible")
    bounds = _run_score_bounds(
        graph,
        executable=executable,
        seed_id=seed_id,
        target_id=target_id,
        threshold=threshold,
    )
    target_raw_score, target_bridges = _exact_candidate_from_paths(
        graph,
        seed_id=seed_id,
        candidate_id=target_id,
        paths=bounds.target_paths,
    )
    _require(
        len(target_bridges) == bounds.bridge_counts[target_id],
        "target bridge count differs between bounds and Decimal paths",
    )
    target_score = target_raw_score.quantize(
        FORMULA_QUANTUM, rounding=ROUND_HALF_EVEN
    )
    candidate_ids = [
        int(node_id)
        for node_id in np.flatnonzero(eligible)
        if int(node_id) != seed_id
    ]
    eligible_candidate_count = len(candidate_ids)
    _require(eligible_candidate_count > 0, "eligible candidate universe is empty")
    proven_at_or_above = 0
    proven_below = 0
    ambiguous: list[int] = []
    if target_score == 0:
        proven_at_or_above = eligible_candidate_count - 1
    else:
        boundary = target_score - FORMULA_QUANTUM / 2
        boundary_scaled = int(boundary * BOUND_SCALE)
        _require(
            Decimal(boundary_scaled) / Decimal(BOUND_SCALE) == boundary,
            "rank boundary is not exactly representable at the bounds scale",
        )
        for candidate_id in candidate_ids:
            if candidate_id == target_id:
                continue
            # The native interval encloses the exact rational sum. Expanding it by 1e-15 is
            # deliberately much wider than division and ordered-addition error at Decimal(40).
            # Only intervals wholly on one side of the persisted-score boundary are classified;
            # every intersecting candidate is recomputed with the frozen Python Decimal order.
            guarded_lower = bounds.lower[candidate_id] - BOUND_GUARD_SCALED_UNITS
            guarded_upper = bounds.upper[candidate_id] + BOUND_GUARD_SCALED_UNITS
            if guarded_lower > boundary_scaled:
                proven_at_or_above += 1
            elif guarded_upper < boundary_scaled:
                proven_below += 1
            else:
                ambiguous.append(candidate_id)
    extracted = _extract_candidate_paths(
        graph,
        candidate_ids=ambiguous,
        seed_counts=bounds.seed_counts,
        eligible=eligible,
    )
    refined_at_or_above = 1
    for candidate_id in ambiguous:
        raw_score, _ = _exact_candidate_from_paths(
            graph,
            seed_id=seed_id,
            candidate_id=candidate_id,
            paths=extracted[candidate_id],
        )
        persisted = raw_score.quantize(FORMULA_QUANTUM, rounding=ROUND_HALF_EVEN)
        refined_at_or_above += persisted >= target_score
    worst_tie_rank = proven_at_or_above + refined_at_or_above
    _require(
        proven_at_or_above
        + proven_below
        + len(ambiguous)
        + 1
        == eligible_candidate_count,
        "rank proof does not partition the candidate universe",
    )
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        rank_fraction = Decimal(worst_tie_rank) / Decimal(eligible_candidate_count)
    target_bridges.sort(
        key=lambda item: (-item["path_contribution"], node_index.uis[item["bridge_id"]])
    )
    rendered_bridges = [
        {
            "descriptor_ui": node_index.uis[item["bridge_id"]],
            "descriptor_label": node_index.labels[item["bridge_id"]],
            "ab_article_count": item["ab_article_count"],
            "bc_article_count": item["bc_article_count"],
            "jaccard_ab": format(item["jaccard_ab"], "f"),
            "jaccard_bc": format(item["jaccard_bc"], "f"),
            "path_contribution": format(
                item["path_contribution"].quantize(
                    FORMULA_QUANTUM,
                    rounding=ROUND_HALF_EVEN,
                ),
                "f",
            ),
        }
        for item in target_bridges[:top_bridge_limit]
    ]
    return {
        "minimum_support_articles": threshold,
        "endpoint_a_article_support": int(graph.support[seed_id]),
        "target_c_article_support": int(graph.support[target_id]),
        "direct_ac_article_count": bounds.seed_counts[target_id],
        "eligible_candidate_count": eligible_candidate_count,
        "target_persisted_score": format(target_score, "f"),
        "target_worst_tie_rank": worst_tie_rank,
        "target_rank_fraction": format(rank_fraction, "f"),
        "target_top_5_percent": worst_tie_rank * 20 <= eligible_candidate_count,
        "target_below_median": worst_tie_rank * 2 > eligible_candidate_count,
        "target_bridge_count": len(target_bridges),
        "top_target_bridges": rendered_bridges,
        "rank_proof": {
            "method": "exact_integer_rational_bounds_then_python_decimal_refinement",
            "bound_scale_exponent": BOUND_SCALE_EXPONENT,
            "decimal_guard_scaled_units": BOUND_GUARD_SCALED_UNITS,
            "zero_target_nonnegative_shortcut": target_score == 0,
            "bound_proven_at_or_above_count": proven_at_or_above,
            "bound_proven_below_count": proven_below,
            "exact_decimal_refinement_count": len(ambiguous) + 1,
            "exact_decimal_at_or_above_count": refined_at_or_above,
            "partition_candidate_count": eligible_candidate_count,
        },
    }


def _load_node_index_from_cache(path: Path) -> NodeIndex:
    payload = _load_json(path)
    nodes = payload.get("nodes")
    _require(isinstance(nodes, list), "node cache is missing nodes")
    _require(
        all(item.get("dense_id") == index for index, item in enumerate(nodes)),
        "node cache dense identities drifted",
    )
    uis = tuple(item["descriptor_ui"] for item in nodes)
    labels = tuple(item["descriptor_label"] for item in nodes)
    return NodeIndex(
        uis=uis,
        labels=labels,
        normalised_label_to_id={_normalise(label): index for index, label in enumerate(labels)},
        ui_to_id={ui: index for index, ui in enumerate(uis)},
    )


def _development_summary(case_outputs: list[dict]) -> dict:
    summary: dict[str, dict[str, dict[str, int]]] = {}
    for threshold in SUPPORT_THRESHOLDS:
        threshold_key = str(threshold)
        summary[threshold_key] = {}
        for kind in ("source_labeled_positive", "hard_negative", "distant_negative"):
            rows = [item for item in case_outputs if item["kind"] == kind]
            results = [
                next(
                    result
                    for result in item["support_runs"]
                    if result["minimum_support_articles"] == threshold
                )
                for item in rows
            ]
            summary[threshold_key][kind] = {
                "case_count": len(results),
                "top_5_percent_count": sum(item["target_top_5_percent"] for item in results),
                "below_median_count": sum(item["target_below_median"] for item in results),
            }
    return summary


def run_development(
    cache: GraphCache,
    *,
    output_path: Path,
    command: str,
) -> dict:
    audit_bioasq_formula_v2()
    cases = load_development_cases()
    index = _load_node_index_from_cache(cache.nodes_path)
    graphs = {
        year: load_edge_graph(cache.edge_paths[year], year) for year in DEVELOPMENT_CUTOFFS
    }
    started = time.perf_counter()
    case_outputs = []
    for case in cases:
        cutoff_year = int(case.cutoff[:4])
        graph = graphs[cutoff_year]
        seed_id = index.ui_to_id[case.endpoint_a["descriptor_ui"]]
        target_id = index.ui_to_id[case.target_c["descriptor_ui"]]
        runs = [
            score_seed_with_bounds(
                graph,
                executable=cache.score_bounds_executable,
                seed_id=seed_id,
                target_id=target_id,
                threshold=threshold,
                node_index=index,
            )
            for threshold in SUPPORT_THRESHOLDS
        ]
        case_outputs.append(
            {
                "id": case.id,
                "kind": case.kind,
                "split": "development",
                "label_scope": case.label_scope,
                "cutoff": case.cutoff,
                "endpoint_a": case.endpoint_a,
                "target_c": case.target_c,
                "support_runs": runs,
            }
        )
        print(f"scored development case: {case.id}", flush=True)
    elapsed = time.perf_counter() - started
    cache_bytes = sum(
        identity["bytes"] for identity in cache.manifest["generated_files"].values()
    )
    payload = {
        "schema_version": 1,
        "status": "development_metric_output_initial_formula",
        "readiness_contribution": 0,
        "claim_boundary": (
            "Development-only measurement from the source-informed BioASQ secondary-snapshot "
            "pilot; not held-out validation, discovery truth, metric-v3 readiness, or a general "
            "gap detector."
        ),
        "inputs": {
            "formula_contract": _file_identity(FORMULA_PATH),
            "successor_protocol": _file_identity(SUCCESSOR_PATH),
            "executor_source": _file_identity(EXECUTOR_SOURCE_PATH),
            "native_pair_counter_source": _file_identity(NATIVE_SOURCE_PATH),
            "native_rank_screener_source": _file_identity(SCORE_BOUNDS_SOURCE_PATH),
            "source_snapshot": cache.manifest["source_snapshot"],
            "descriptor_vocabulary": cache.manifest["descriptor_vocabulary"],
            "graph_cache_manifest": _file_identity(cache.manifest_path),
        },
        "execution_isolation": {
            "split": "development",
            "case_count": 11,
            "heldout_case_count_computed": 0,
            "heldout_scores_ranks_orderings_or_bridges_materialized": False,
            "formula_revision_budget_consumed": 0,
        },
        "formula": {
            "edge_weight": "article_jaccard",
            "path_aggregation": "minimum",
            "candidate_accumulation": "sum",
            "support_runs": list(SUPPORT_THRESHOLDS),
            "decimal_precision": DECIMAL_PRECISION,
            "persisted_score_quantum": format(FORMULA_QUANTUM, "f"),
            "tie_policy": "conservative worst tied rank",
        },
        "graph": {
            "node_count": cache.manifest["node_count"],
            "cutoff_years": list(DEVELOPMENT_CUTOFFS),
            "edge_counts": {
                year: cache.manifest["edge_headers"][str(year)]["edge_count"]
                for year in DEVELOPMENT_CUTOFFS
            },
        },
        "cases": case_outputs,
        "development_summary": _development_summary(case_outputs),
        "runtime": {
            "scoring_elapsed_seconds": round(elapsed, 3),
            "generated_cache_bytes": cache_bytes,
            "compiler_version": cache.manifest["compiler_version"],
            "command": command,
        },
        "limitations": [
            "Only development cases were scored; the output is not held-out validation.",
            (
                "Case identities and source counts were known before the source-informed "
                "successor and formula freezes."
            ),
            (
                "The graph uses article-level MeSH co-occurrence rather than LION's "
                "sentence-level heterogeneous entity graph."
            ),
            (
                "Native integer rational bounds only screen rank comparisons; the target and "
                "every boundary-intersecting candidate use the frozen Python Decimal order, and "
                "no native numeric value is persisted as a score."
            ),
            "Source-labelled positives are not independently adjudicated discovery truth.",
            (
                "Ontology-generated controls are not verified absences of relationships or "
                "non-academic knowledge."
            ),
            "No result contributes metric-v3 readiness or authorizes an LLM interpretation layer."
        ],
    }
    _write_new_json(output_path, payload)
    return payload


def default_output_path() -> Path:
    formula_hash = _sha256_file(FORMULA_PATH)
    return (
        REPO_ROOT
        / "benchmarks"
        / "v3"
        / "manifests"
        / f"bioasq-v2-development-{formula_hash[:12]}.json"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path, nargs="?", default=SNAPSHOT_PATH)
    parser.add_argument("--mesh", type=Path, default=MESH_PATH)
    parser.add_argument("--cache-root", type=Path, default=REPO_ROOT / "data" / "cache")
    parser.add_argument("--output", type=Path, default=default_output_path())
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    cache = prepare_graph_cache(
        args.snapshot,
        mesh_path=args.mesh,
        cache_root=args.cache_root,
    )
    print(f"graph cache ready: {cache.directory}")
    if args.prepare_only:
        return
    command = "python -m pipeline.benchmark.bioasq_v2_development"
    payload = run_development(cache, output_path=args.output, command=command)
    print(f"wrote {args.output}")
    print(f"development cases: {len(payload['cases'])}")
    print("held-out cases computed: 0")
    print("readiness contribution: 0")


if __name__ == "__main__":
    main()
