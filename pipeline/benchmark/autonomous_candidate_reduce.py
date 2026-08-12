"""Reduce exact T0 source shards and construct the frozen score-free candidate universe.

This module contains no metric. It verifies every source checkpoint, proves global PMID
uniqueness, reduces exact support and positive co-occurrence counts, and applies only the gates
frozen in ``t0-candidate-index-v1.json``. Large and intermediate artifacts stay on the explicitly
selected data volume.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal, Sequence

import numpy as np

from pipeline.benchmark.autonomous_candidate_index import (
    PAIR_DTYPE,
    CandidateIndexError,
    VocabularyAudit,
    VocabularyDescriptor,
    _audit_existing_shard,
    _require_non_system_volume,
    _sha256_file,
    _write_binary_part,
    read_vocabulary,
)
from pipeline.benchmark.autonomous_t0 import (
    SEALED_T0_PATH,
    AutonomousT0Error,
    _promote_verified_part,
    audit_sealed_t0,
    write_new_json,
)
from pipeline.benchmark.validate_autonomous_candidate_index import (
    audit_candidate_index_contract,
)
from pipeline.provenance import canonical_json_bytes

GLOBAL_PAIR_DTYPE = np.dtype([("key", "<u8"), ("count", "<u8")])
PAIR_KEY_BUCKET_SPAN = 2_000_000
AUDIT_ROW_CHUNK = 5_000_000
RunKind = Literal["pmids", "pairs"]
RunFormat = Literal[
    "pmid-u64-v1",
    "support-u64-v1",
    "pair-u64-u32-v1",
    "pair-u64-u64-v1",
    "candidate-key-u64-v1",
    "descriptor-json-v1",
]


@dataclass(frozen=True)
class RunArtifact:
    path: Path
    format: RunFormat
    rows: int
    sha256: str
    bytes: int


@dataclass(frozen=True)
class ScanSetAudit:
    source_count: int
    record_count: int
    records_without_mesh: int
    descriptor_assignments: int
    positive_pair_rows: int
    pair_observations: int
    identity_sha256: str
    support_runs: tuple[Path, ...]
    pmid_runs: tuple[RunArtifact, ...]
    pair_runs: tuple[RunArtifact, ...]
    vocabulary: VocabularyAudit


@dataclass(frozen=True)
class ReductionAudit:
    source_set_sha256: str
    corpus_denominator: int
    descriptor_assignments: int
    pair_observations: int
    source_count: int
    records_without_mesh: int
    vocabulary: VocabularyAudit
    support_vector: RunArtifact
    pmid_vector: RunArtifact
    positive_pairs: RunArtifact


def _checkpoint_sha256(payload: dict) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def audit_scan_set(scan_dir: Path, mesh_path: Path) -> ScanSetAudit:
    """Audit all immutable scan checkpoints and derive their ordered set identity."""
    contract = audit_candidate_index_contract()
    sealed = audit_sealed_t0()
    payload = json.loads(SEALED_T0_PATH.read_text(encoding="utf-8"))
    vocabulary = read_vocabulary(
        mesh_path,
        expected_sha256=payload["mesh_descriptor"]["sha256"],
        expected_count=sealed.mesh_descriptor_count,
    )
    vocabulary_size = vocabulary.descriptor_count
    entries: list[dict] = []
    support_runs: list[Path] = []
    pmid_runs: list[RunArtifact] = []
    pair_runs: list[RunArtifact] = []
    totals = {
        "record_count": 0,
        "records_without_mesh": 0,
        "descriptor_assignments": 0,
        "positive_pair_rows": 0,
        "pair_observations": 0,
    }
    for source in payload["pubmed_baseline"]["files"]:
        shard_dir = scan_dir / "shards" / source["filename"]
        measured = _audit_existing_shard(
            shard_dir,
            contract_sha256=contract.sha256,
            vocabulary_sha256=vocabulary.sha256,
            vocabulary_size=vocabulary_size,
            source=source,
        )
        if measured is None:
            raise CandidateIndexError(f"source shard is incomplete: {source['filename']}")
        checkpoint = json.loads((shard_dir / "checkpoint.json").read_text(encoding="utf-8"))
        entry = {
            "source": checkpoint["source"],
            "measured": checkpoint["measured"],
            "outputs": checkpoint["outputs"],
        }
        entries.append(entry)
        totals["record_count"] += measured.parsed_record_count
        totals["records_without_mesh"] += measured.records_without_mesh
        totals["descriptor_assignments"] += measured.descriptor_assignments
        totals["positive_pair_rows"] += measured.positive_pair_rows
        totals["pair_observations"] += measured.pair_observations
        support_runs.append(shard_dir / "supports.bin")
        pmid_output = checkpoint["outputs"]["pmids"]
        pair_output = checkpoint["outputs"]["pairs"]
        pmid_runs.append(
            RunArtifact(
                path=shard_dir / "pmids.bin",
                format="pmid-u64-v1",
                rows=measured.parsed_record_count,
                sha256=pmid_output["sha256"],
                bytes=pmid_output["bytes"],
            )
        )
        pair_runs.append(
            RunArtifact(
                path=shard_dir / "pairs.bin",
                format="pair-u64-u32-v1",
                rows=measured.positive_pair_rows,
                sha256=pair_output["sha256"],
                bytes=pair_output["bytes"],
            )
        )
    if totals["record_count"] != sealed.pubmed_record_count:
        raise CandidateIndexError("source shard record aggregate differs from sealed T0")
    identity = {
        "schema_version": 1,
        "kind": "autonomous_t0_source_shard_set",
        "candidate_index_contract_sha256": contract.sha256,
        "sealed_t0_sha256": contract.t0_manifest_sha256,
        "vocabulary_sha256": vocabulary.sha256,
        "entries": entries,
    }
    return ScanSetAudit(
        source_count=len(entries),
        identity_sha256=_checkpoint_sha256(identity),
        support_runs=tuple(support_runs),
        pmid_runs=tuple(pmid_runs),
        pair_runs=tuple(pair_runs),
        vocabulary=vocabulary,
        **totals,
    )


def _run_checkpoint_path(path: Path) -> Path:
    return path.with_name(f"{path.name}.checkpoint.json")


def _run_identity(kind: RunKind, inputs: Sequence[RunArtifact], contract_sha256: str) -> dict:
    return {
        "schema_version": 1,
        "kind": f"autonomous_t0_{kind}_merge_run",
        "candidate_index_contract_sha256": contract_sha256,
        "inputs": [
            {
                "format": item.format,
                "rows": item.rows,
                "sha256": item.sha256,
                "bytes": item.bytes,
            }
            for item in inputs
        ],
    }


def _audit_run_content(run: RunArtifact, kind: RunKind, *, vocabulary_size: int, denominator: int) -> None:
    if run.rows < 0 or run.bytes < 0 or not re.fullmatch(r"[0-9a-f]{64}", run.sha256):
        raise CandidateIndexError(f"invalid merge-run metadata: {run.path}")
    expected_itemsize = np.dtype("<u8").itemsize if kind == "pmids" else GLOBAL_PAIR_DTYPE.itemsize
    if run.bytes != run.rows * expected_itemsize:
        raise CandidateIndexError(f"merge-run shape drifted: {run.path}")
    if not run.path.is_file() or run.path.stat().st_size != run.bytes:
        raise CandidateIndexError(f"merge-run bytes are missing: {run.path}")
    if _sha256_file(run.path) != run.sha256:
        raise CandidateIndexError(f"merge-run hash drifted: {run.path}")
    if run.rows == 0:
        return
    if kind == "pmids":
        values = np.memmap(run.path, mode="r", dtype="<u8")
        previous: int | None = None
        for start in range(0, values.size, AUDIT_ROW_CHUNK):
            chunk = values[start : start + AUDIT_ROW_CHUNK]
            if (
                (previous is not None and int(chunk[0]) <= previous)
                or (chunk.size > 1 and bool(np.any(chunk[1:] <= chunk[:-1])))
            ):
                raise CandidateIndexError(f"PMID merge run is not strictly ordered: {run.path}")
            previous = int(chunk[-1])
        return
    pairs = np.memmap(run.path, mode="r", dtype=GLOBAL_PAIR_DTYPE)
    previous = None
    for start in range(0, pairs.size, AUDIT_ROW_CHUNK):
        chunk = pairs[start : start + AUDIT_ROW_CHUNK]
        keys = chunk["key"]
        left = keys // np.uint64(vocabulary_size)
        right = keys % np.uint64(vocabulary_size)
        if (
            (previous is not None and int(keys[0]) <= previous)
            or (keys.size > 1 and bool(np.any(keys[1:] <= keys[:-1])))
            or bool(np.any(left >= right))
            or bool(np.any(right >= vocabulary_size))
            or bool(np.any(chunk["count"] == 0))
            or bool(np.any(chunk["count"] > denominator))
        ):
            raise CandidateIndexError(f"pair merge-run invariants drifted: {run.path}")
        previous = int(keys[-1])


def _reuse_merge_run(
    destination: Path,
    *,
    kind: RunKind,
    identity: dict,
    vocabulary_size: int,
    denominator: int,
) -> RunArtifact | None:
    checkpoint_path = _run_checkpoint_path(destination)
    if not checkpoint_path.exists():
        if destination.exists():
            raise CandidateIndexError(f"uncheckpointed merge run refuses overwrite: {destination}")
        return None
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    if checkpoint.get("identity") != identity:
        raise CandidateIndexError(f"merge-run checkpoint identity drifted: {destination}")
    output = checkpoint.get("output")
    if not isinstance(output, dict) or set(output) != {"format", "rows", "sha256", "bytes"}:
        raise CandidateIndexError(f"merge-run checkpoint output drifted: {destination}")
    expected_format: RunFormat = "pmid-u64-v1" if kind == "pmids" else "pair-u64-u64-v1"
    if output.get("format") != expected_format:
        raise CandidateIndexError(f"merge-run checkpoint format drifted: {destination}")
    run = RunArtifact(path=destination, **output)
    _audit_run_content(run, kind, vocabulary_size=vocabulary_size, denominator=denominator)
    return run


def _write_run_checkpoint(destination: Path, identity: dict, run: RunArtifact) -> None:
    payload = {
        "schema_version": 1,
        "identity": identity,
        "output": {
            "format": run.format,
            "rows": run.rows,
            "sha256": run.sha256,
            "bytes": run.bytes,
        },
        "readiness_contribution": 0,
        "claim_boundary": "Exact score-free merge run; not a metric, prediction, discovery, or validated gap.",
    }
    try:
        write_new_json(_run_checkpoint_path(destination), payload)
    except AutonomousT0Error as exc:
        raise CandidateIndexError(str(exc)) from exc


def _write_bytes_part(destination: Path, raw: bytes) -> tuple[str, int]:
    part = destination.with_name(f"{destination.name}.part")
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(raw).hexdigest()
    if destination.exists():
        if destination.stat().st_size != len(raw) or _sha256_file(destination) != digest:
            raise CandidateIndexError(f"refusing to replace conflicting artifact: {destination}")
        return digest, len(raw)
    with part.open("wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        _promote_verified_part(part, destination)
    except AutonomousT0Error as exc:
        raise CandidateIndexError(str(exc)) from exc
    return digest, len(raw)


def merge_run_group(
    inputs: Sequence[RunArtifact],
    destination: Path,
    *,
    kind: RunKind,
    contract_sha256: str,
    vocabulary_size: int,
    denominator: int,
) -> RunArtifact:
    """Merge one bounded group exactly, with an immutable identity checkpoint."""
    if not inputs:
        raise CandidateIndexError("cannot merge an empty run group")
    identity = _run_identity(kind, inputs, contract_sha256)
    reused = _reuse_merge_run(
        destination,
        kind=kind,
        identity=identity,
        vocabulary_size=vocabulary_size,
        denominator=denominator,
    )
    if reused is not None:
        return reused
    for item in inputs:
        if not item.path.is_file() or item.path.stat().st_size != item.bytes:
            raise CandidateIndexError(f"merge input is missing or changed: {item.path}")
        if _sha256_file(item.path) != item.sha256:
            raise CandidateIndexError(f"merge input hash drifted: {item.path}")

    if kind == "pmids":
        blocks = [np.fromfile(item.path, dtype="<u8") for item in inputs]
        values = np.concatenate(blocks) if len(blocks) > 1 else blocks[0].copy()
        values.sort()
        if values.size > 1 and bool(np.any(values[1:] == values[:-1])):
            raise CandidateIndexError("duplicate PMID across sealed source shards")
        output_array = values
        output_format: RunFormat = "pmid-u64-v1"
    else:
        return _merge_pair_group_bounded(
            inputs,
            destination,
            identity=identity,
            vocabulary_size=vocabulary_size,
            denominator=denominator,
        )

    sha256, byte_count = _write_binary_part(destination, output_array)
    run = RunArtifact(
        path=destination,
        format=output_format,
        rows=int(output_array.size),
        sha256=sha256,
        bytes=byte_count,
    )
    _audit_run_content(run, kind, vocabulary_size=vocabulary_size, denominator=denominator)
    _write_run_checkpoint(destination, identity, run)
    return run


def _merge_pair_group_bounded(
    inputs: Sequence[RunArtifact],
    destination: Path,
    *,
    identity: dict,
    vocabulary_size: int,
    denominator: int,
) -> RunArtifact:
    """Reduce sorted pair runs in fixed key ranges so memory cannot scale with total rows."""
    blocks: list[np.ndarray] = []
    for item in inputs:
        dtype = PAIR_DTYPE if item.format == "pair-u64-u32-v1" else GLOBAL_PAIR_DTYPE
        blocks.append(
            np.memmap(item.path, mode="r", dtype=dtype)
            if item.rows
            else np.empty(0, dtype=dtype)
        )
    part = destination.with_name(f"{destination.name}.part")
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    byte_count = 0
    row_count = 0
    key_limit = vocabulary_size * vocabulary_size
    with part.open("wb") as handle:
        for lower in range(0, key_limit, PAIR_KEY_BUCKET_SPAN):
            upper = min(lower + PAIR_KEY_BUCKET_SPAN, key_limit)
            key_blocks: list[np.ndarray] = []
            count_blocks: list[np.ndarray] = []
            for block in blocks:
                if not block.size:
                    continue
                keys = block["key"]
                start = int(np.searchsorted(keys, np.uint64(lower), side="left"))
                stop = int(np.searchsorted(keys, np.uint64(upper), side="left"))
                if stop > start:
                    key_blocks.append(np.asarray(keys[start:stop]))
                    count_blocks.append(np.asarray(block["count"][start:stop], dtype="<u8"))
            if not key_blocks:
                continue
            keys = np.concatenate(key_blocks) if len(key_blocks) > 1 else key_blocks[0].copy()
            counts = (
                np.concatenate(count_blocks) if len(count_blocks) > 1 else count_blocks[0].copy()
            )
            order = np.argsort(keys, kind="stable")
            keys = keys[order]
            counts = counts[order]
            starts = np.concatenate(
                (np.array([0], dtype=np.int64), np.flatnonzero(keys[1:] != keys[:-1]) + 1)
            )
            unique_keys = keys[starts]
            sums = np.add.reduceat(counts, starts, dtype=np.uint64)
            if bool(np.any(sums == 0)) or bool(np.any(sums > denominator)):
                raise CandidateIndexError("pair count overflow or corpus-denominator violation")
            pairs = np.empty(unique_keys.size, dtype=GLOBAL_PAIR_DTYPE)
            pairs["key"] = unique_keys
            pairs["count"] = sums
            raw = pairs.tobytes(order="C")
            handle.write(raw)
            digest.update(raw)
            byte_count += len(raw)
            row_count += int(pairs.size)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        _promote_verified_part(part, destination)
    except AutonomousT0Error as exc:
        raise CandidateIndexError(str(exc)) from exc
    run = RunArtifact(
        path=destination,
        format="pair-u64-u64-v1",
        rows=row_count,
        sha256=digest.hexdigest(),
        bytes=byte_count,
    )
    _audit_run_content(
        run,
        "pairs",
        vocabulary_size=vocabulary_size,
        denominator=denominator,
    )
    _write_run_checkpoint(destination, identity, run)
    return run


def external_merge(
    inputs: Sequence[RunArtifact],
    work_dir: Path,
    final_path: Path,
    *,
    kind: RunKind,
    contract_sha256: str,
    vocabulary_size: int,
    denominator: int,
    fan_in: int = 8,
    progress: Callable[[str], None] | None = None,
) -> RunArtifact:
    """Perform a deterministic bounded-fan-in external reduction."""
    if fan_in < 2 or fan_in > 32:
        raise CandidateIndexError("external merge fan-in must be between 2 and 32")
    runs = list(inputs)
    if not runs:
        raise CandidateIndexError("external merge requires at least one input")
    pass_number = 0
    while len(runs) > fan_in:
        next_runs: list[RunArtifact] = []
        pass_dir = work_dir / f"pass-{pass_number:02d}"
        for group_index, start in enumerate(range(0, len(runs), fan_in)):
            group = runs[start : start + fan_in]
            destination = pass_dir / f"run-{group_index:05d}.bin"
            result = merge_run_group(
                group,
                destination,
                kind=kind,
                contract_sha256=contract_sha256,
                vocabulary_size=vocabulary_size,
                denominator=denominator,
            )
            next_runs.append(result)
            if progress is not None:
                progress(
                    f"{kind} pass {pass_number}: {group_index + 1}/"
                    f"{(len(runs) + fan_in - 1) // fan_in}"
                )
        runs = next_runs
        pass_number += 1
    return merge_run_group(
        runs,
        final_path,
        kind=kind,
        contract_sha256=contract_sha256,
        vocabulary_size=vocabulary_size,
        denominator=denominator,
    )


def reduce_supports(
    inputs: Sequence[Path],
    destination: Path,
    *,
    vocabulary_size: int,
    denominator: int,
) -> RunArtifact:
    """Sum all per-source uint32 support vectors into one exact uint64 vector."""
    supports = np.zeros(vocabulary_size, dtype="<u8")
    for path in inputs:
        block = np.fromfile(path, dtype="<u4")
        if block.size != vocabulary_size:
            raise CandidateIndexError(f"source support vector shape drifted: {path}")
        supports += block.astype("<u8")
        if bool(np.any(supports > denominator)):
            raise CandidateIndexError("descriptor support exceeds corpus denominator")
    sha256, byte_count = _write_binary_part(destination, supports)
    return RunArtifact(
        path=destination,
        format="support-u64-v1",
        rows=vocabulary_size,
        sha256=sha256,
        bytes=byte_count,
    )


def _tree_tokens(value: str) -> tuple[str, ...]:
    return tuple(value.split("."))


def build_exclusions(vocabulary: Sequence[VocabularyDescriptor]) -> tuple[np.ndarray, ...]:
    """Build exact frozen ancestor/descendant and shared-entry-term exclusions."""
    excluded: list[set[int]] = [set() for _ in vocabulary]
    tree_owners: dict[tuple[str, ...], set[int]] = {}
    term_owners: dict[str, list[int]] = {}
    for index, descriptor in enumerate(vocabulary):
        for tree in descriptor.tree_numbers:
            tree_owners.setdefault(_tree_tokens(tree), set()).add(index)
        for term in descriptor.terms:
            term_owners.setdefault(term, []).append(index)
    for descendant, descriptor in enumerate(vocabulary):
        for tree in descriptor.tree_numbers:
            tokens = _tree_tokens(tree)
            for length in range(1, len(tokens)):
                for ancestor in tree_owners.get(tokens[:length], ()):
                    if ancestor != descendant:
                        excluded[ancestor].add(descendant)
                        excluded[descendant].add(ancestor)
    for owners in term_owners.values():
        if len(owners) < 2:
            continue
        unique = sorted(set(owners))
        for offset, left in enumerate(unique):
            excluded[left].update(unique[:offset])
            excluded[left].update(unique[offset + 1 :])
    return tuple(np.fromiter(sorted(values), dtype="<u4") for values in excluded)


def write_candidate_stream(
    supports_path: Path,
    positive_pairs_path: Path,
    destination: Path,
    *,
    vocabulary: Sequence[VocabularyDescriptor],
    denominator: int,
    minimum_support: int = 100,
    minimum_expected_count: int = 5,
) -> RunArtifact:
    """Emit every zero-direct-count pair passing the frozen score-free gates."""
    vocabulary_size = len(vocabulary)
    supports = np.memmap(supports_path, mode="r", dtype="<u8")
    if supports.size != vocabulary_size:
        raise CandidateIndexError("global support vector shape differs from vocabulary")
    positives = (
        np.memmap(positive_pairs_path, mode="r", dtype=GLOBAL_PAIR_DTYPE)
        if positive_pairs_path.stat().st_size
        else np.empty(0, dtype=GLOBAL_PAIR_DTYPE)
    )
    positive_keys = positives["key"]
    exclusions = build_exclusions(vocabulary)
    if destination.exists():
        return audit_candidate_stream(
            supports_path,
            positive_pairs_path,
            destination,
            vocabulary=vocabulary,
            denominator=denominator,
            minimum_support=minimum_support,
            minimum_expected_count=minimum_expected_count,
            exclusions=exclusions,
        )
    part = destination.with_name(f"{destination.name}.part")
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    byte_count = 0
    row_count = 0
    previous_key: int | None = None
    with part.open("wb") as handle:
        for left_index in range(vocabulary_size - 1):
            keys = _candidate_keys_for_left(
                left_index,
                supports,
                positive_keys,
                exclusions,
                vocabulary_size=vocabulary_size,
                denominator=denominator,
                minimum_support=minimum_support,
                minimum_expected_count=minimum_expected_count,
            )
            if not keys.size:
                continue
            if previous_key is not None and int(keys[0]) <= previous_key:
                raise CandidateIndexError("candidate stream lost strict pair-key order")
            previous_key = int(keys[-1])
            raw = keys.tobytes(order="C")
            handle.write(raw)
            digest.update(raw)
            byte_count += len(raw)
            row_count += int(keys.size)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        _promote_verified_part(part, destination)
    except AutonomousT0Error as exc:
        raise CandidateIndexError(str(exc)) from exc
    return RunArtifact(
        path=destination,
        format="candidate-key-u64-v1",
        rows=row_count,
        sha256=digest.hexdigest(),
        bytes=byte_count,
    )


def _candidate_keys_for_left(
    left_index: int,
    supports: np.ndarray,
    positive_keys: np.ndarray,
    exclusions: Sequence[np.ndarray],
    *,
    vocabulary_size: int,
    denominator: int,
    minimum_support: int,
    minimum_expected_count: int,
) -> np.ndarray:
    right_indices = np.arange(left_index + 1, vocabulary_size, dtype="<u8")
    mask = supports[right_indices] >= minimum_support
    mask &= supports[left_index] >= minimum_support
    mask &= (
        supports[right_indices] * supports[left_index]
        >= np.uint64(minimum_expected_count * denominator)
    )
    lower = np.uint64(left_index * vocabulary_size)
    upper = np.uint64((left_index + 1) * vocabulary_size)
    start = int(np.searchsorted(positive_keys, lower, side="left"))
    stop = int(np.searchsorted(positive_keys, upper, side="left"))
    if stop > start:
        positive_right = positive_keys[start:stop] % np.uint64(vocabulary_size)
        valid = positive_right > left_index
        mask[positive_right[valid] - (left_index + 1)] = False
    if exclusions[left_index].size:
        excluded_right = exclusions[left_index]
        excluded_right = excluded_right[excluded_right > left_index].astype("<u8")
        mask[excluded_right - (left_index + 1)] = False
    return np.asarray(np.uint64(left_index * vocabulary_size) + right_indices[mask], dtype="<u8")


def audit_candidate_stream(
    supports_path: Path,
    positive_pairs_path: Path,
    candidate_path: Path,
    *,
    vocabulary: Sequence[VocabularyDescriptor],
    denominator: int,
    minimum_support: int = 100,
    minimum_expected_count: int = 5,
    exclusions: Sequence[np.ndarray] | None = None,
) -> RunArtifact:
    """Prove a candidate stream is exhaustive for the frozen score-free gates."""
    vocabulary_size = len(vocabulary)
    supports = np.memmap(supports_path, mode="r", dtype="<u8")
    positives = (
        np.memmap(positive_pairs_path, mode="r", dtype=GLOBAL_PAIR_DTYPE)
        if positive_pairs_path.stat().st_size
        else np.empty(0, dtype=GLOBAL_PAIR_DTYPE)
    )
    candidates = (
        np.memmap(candidate_path, mode="r", dtype="<u8")
        if candidate_path.stat().st_size
        else np.empty(0, dtype="<u8")
    )
    if candidate_path.stat().st_size % np.dtype("<u8").itemsize:
        raise CandidateIndexError("candidate stream byte count is not uint64-aligned")
    if supports.size != vocabulary_size:
        raise CandidateIndexError("global support vector shape differs from vocabulary")
    if candidates.size > 1 and bool(np.any(candidates[1:] <= candidates[:-1])):
        raise CandidateIndexError("candidate stream is not strictly ordered and duplicate-free")
    resolved_exclusions = exclusions if exclusions is not None else build_exclusions(vocabulary)
    expected_total = 0
    for left_index in range(vocabulary_size - 1):
        expected = _candidate_keys_for_left(
            left_index,
            supports,
            positives["key"],
            resolved_exclusions,
            vocabulary_size=vocabulary_size,
            denominator=denominator,
            minimum_support=minimum_support,
            minimum_expected_count=minimum_expected_count,
        )
        lower = np.uint64(left_index * vocabulary_size)
        upper = np.uint64((left_index + 1) * vocabulary_size)
        start = int(np.searchsorted(candidates, lower, side="left"))
        stop = int(np.searchsorted(candidates, upper, side="left"))
        if not np.array_equal(candidates[start:stop], expected):
            raise CandidateIndexError(f"candidate stream is not exhaustive at left index {left_index}")
        expected_total += int(expected.size)
    if expected_total != int(candidates.size):
        raise CandidateIndexError("candidate stream contains keys outside the descriptor-pair universe")
    return RunArtifact(
        path=candidate_path,
        format="candidate-key-u64-v1",
        rows=int(candidates.size),
        sha256=_sha256_file(candidate_path),
        bytes=candidate_path.stat().st_size,
    )


def write_descriptor_table(
    vocabulary: VocabularyAudit,
    destination: Path,
    *,
    contract_sha256: str,
) -> RunArtifact:
    """Write the vocabulary order and exact exclusion inputs as canonical JSON."""
    completed_on = dt.date.today().isoformat()
    if manifest_path.exists():
        existing_completed_on = json.loads(manifest_path.read_text(encoding="utf-8")).get(
            "completed_on"
        )
        if isinstance(existing_completed_on, str):
            completed_on = existing_completed_on
    payload = {
        "schema_version": 1,
        "kind": "autonomous_t0_descriptor_table",
        "candidate_index_contract_sha256": contract_sha256,
        "mesh_transport_sha256": vocabulary.sha256,
        "descriptor_count": vocabulary.descriptor_count,
        "descriptors": [
            {
                "index": index,
                "ui": descriptor.ui,
                "label": descriptor.label,
                "tree_numbers": list(descriptor.tree_numbers),
                "normalised_terms": list(descriptor.terms),
            }
            for index, descriptor in enumerate(vocabulary.descriptors)
        ],
    }
    raw = canonical_json_bytes(payload)
    sha256, byte_count = _write_bytes_part(destination, raw)
    return RunArtifact(
        path=destination,
        format="descriptor-json-v1",
        rows=vocabulary.descriptor_count,
        sha256=sha256,
        bytes=byte_count,
    )


def reduce_scan_set(
    scan_dir: Path,
    mesh_path: Path,
    *,
    fan_in: int = 8,
    minimum_free_bytes: int = 50 * 1024**3,
    progress: Callable[[str], None] | None = None,
) -> ReductionAudit:
    """Run the exact global uniqueness, support, and positive-pair reductions."""
    _require_non_system_volume(scan_dir)
    if shutil.disk_usage(scan_dir).free < minimum_free_bytes:
        raise CandidateIndexError("candidate-index volume has insufficient free space for reduction")
    contract = audit_candidate_index_contract()
    sealed = audit_sealed_t0()
    scan = audit_scan_set(scan_dir, mesh_path)
    reduced_dir = scan_dir / "reduced"
    supports = reduce_supports(
        scan.support_runs,
        reduced_dir / "supports.u64.bin",
        vocabulary_size=scan.vocabulary.descriptor_count,
        denominator=sealed.pubmed_record_count,
    )
    support_values = np.memmap(supports.path, mode="r", dtype="<u8")
    if int(support_values.sum(dtype=np.uint64)) != scan.descriptor_assignments:
        raise CandidateIndexError("global support sum differs from source-shard assignments")
    pmids = external_merge(
        scan.pmid_runs,
        scan_dir / "merge-pmids",
        reduced_dir / "pmids.u64.bin",
        kind="pmids",
        contract_sha256=contract.sha256,
        vocabulary_size=scan.vocabulary.descriptor_count,
        denominator=sealed.pubmed_record_count,
        fan_in=fan_in,
        progress=progress,
    )
    if pmids.rows != sealed.pubmed_record_count:
        raise CandidateIndexError("global distinct PMID count differs from sealed T0")
    pairs = external_merge(
        scan.pair_runs,
        scan_dir / "merge-pairs",
        reduced_dir / "positive-pairs.u64u64.bin",
        kind="pairs",
        contract_sha256=contract.sha256,
        vocabulary_size=scan.vocabulary.descriptor_count,
        denominator=sealed.pubmed_record_count,
        fan_in=fan_in,
        progress=progress,
    )
    pair_values = np.memmap(pairs.path, mode="r", dtype=GLOBAL_PAIR_DTYPE)
    if int(pair_values["count"].sum(dtype=np.uint64)) != scan.pair_observations:
        raise CandidateIndexError("global pair-count sum differs from source-shard observations")
    return ReductionAudit(
        source_set_sha256=scan.identity_sha256,
        corpus_denominator=sealed.pubmed_record_count,
        descriptor_assignments=scan.descriptor_assignments,
        pair_observations=scan.pair_observations,
        source_count=scan.source_count,
        records_without_mesh=scan.records_without_mesh,
        vocabulary=scan.vocabulary,
        support_vector=supports,
        pmid_vector=pmids,
        positive_pairs=pairs,
    )


def _artifact_entry(scan_dir: Path, artifact: RunArtifact) -> dict:
    return {
        "path": artifact.path.relative_to(scan_dir).as_posix(),
        "format": artifact.format,
        "rows": artifact.rows,
        "sha256": artifact.sha256,
        "bytes": artifact.bytes,
    }


def build_candidate_universe(
    scan_dir: Path,
    mesh_path: Path,
    manifest_path: Path,
    *,
    fan_in: int = 8,
    minimum_free_bytes: int = 50 * 1024**3,
    progress: Callable[[str], None] | None = None,
) -> dict:
    """Complete and seal the score-free candidate universe after every exact gate passes."""
    contract = audit_candidate_index_contract()
    reduction = reduce_scan_set(
        scan_dir,
        mesh_path,
        fan_in=fan_in,
        minimum_free_bytes=minimum_free_bytes,
        progress=progress,
    )
    reduced_dir = scan_dir / "reduced"
    descriptors = write_descriptor_table(
        reduction.vocabulary,
        reduced_dir / "descriptors.json",
        contract_sha256=contract.sha256,
    )
    candidates = write_candidate_stream(
        reduction.support_vector.path,
        reduction.positive_pairs.path,
        reduced_dir / "candidate-keys.u64.bin",
        vocabulary=reduction.vocabulary.descriptors,
        denominator=reduction.corpus_denominator,
    )
    candidates = audit_candidate_stream(
        reduction.support_vector.path,
        reduction.positive_pairs.path,
        candidates.path,
        vocabulary=reduction.vocabulary.descriptors,
        denominator=reduction.corpus_denominator,
    )
    builder_sha256 = _sha256_file(Path(__file__))
    payload = {
        "schema_version": 1,
        "id": "autonomous-t0-candidate-universe-v1",
        "status": "score_free_candidate_universe_complete",
        "completed_on": completed_on,
        "protocol_id": "autonomous-prospective-pubmed-link-emergence-v1",
        "inputs": {
            "candidate_index_contract": {
                "path": "autonomous/t0-candidate-index-v1.json",
                "canonical_json_sha256": contract.sha256,
            },
            "sealed_t0": {
                "path": "autonomous/t0-2026.json",
                "canonical_json_sha256": contract.t0_manifest_sha256,
            },
            "source_shard_set_canonical_json_sha256": reduction.source_set_sha256,
            "mesh_transport_sha256": reduction.vocabulary.sha256,
            "builder_source_sha256": builder_sha256,
        },
        "measurement_boundary": {
            "indexing_basis": "maintained_2026_pubmed_mesh_assignments",
            "method": "exact full-baseline integer reduction; no sampling or approximation",
            "readiness_contribution": 0,
        },
        "counts": {
            "source_files": reduction.source_count,
            "distinct_valid_pmids": reduction.corpus_denominator,
            "records_without_mesh": reduction.records_without_mesh,
            "mesh_descriptors": reduction.vocabulary.descriptor_count,
            "descriptor_assignments": reduction.descriptor_assignments,
            "positive_pair_rows": reduction.positive_pairs.rows,
            "pair_observations": reduction.pair_observations,
            "candidate_pairs": candidates.rows,
        },
        "artifacts": {
            "descriptor_table": _artifact_entry(scan_dir, descriptors),
            "support_vector": _artifact_entry(scan_dir, reduction.support_vector),
            "pmid_vector": _artifact_entry(scan_dir, reduction.pmid_vector),
            "positive_cooccurrence_index": _artifact_entry(scan_dir, reduction.positive_pairs),
            "candidate_stream": _artifact_entry(scan_dir, candidates),
        },
        "completion_gates": {
            "all_source_hashes_and_record_subtotals_match": True,
            "global_pmids_strictly_unique_and_equal_sealed_denominator": True,
            "unknown_descriptors": 0,
            "support_and_positive_pair_reductions_exact": True,
            "candidate_stream_exhaustive_strictly_ordered_duplicate_free": True,
            "metric_scores_or_predictions_emitted": False,
        },
        "claim_boundary": (
            "Exact maintained-current PubMed/MeSH count index and score-free candidate set only; "
            "not a metric result, prediction, discovery, validated gap, or evidence of absent knowledge."
        ),
    }
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing != payload:
            raise CandidateIndexError(f"existing candidate-universe manifest drifted: {manifest_path}")
    else:
        try:
            write_new_json(manifest_path, payload)
        except AutonomousT0Error as exc:
            raise CandidateIndexError(str(exc)) from exc
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    reduce_parser = subparsers.add_parser("reduce")
    reduce_parser.add_argument("--scan-dir", type=Path, required=True)
    reduce_parser.add_argument("--mesh", type=Path, required=True)
    reduce_parser.add_argument("--fan-in", type=int, default=8)
    reduce_parser.add_argument("--minimum-free-gib", type=float, default=50.0)
    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("--scan-dir", type=Path, required=True)
    build_parser.add_argument("--mesh", type=Path, required=True)
    build_parser.add_argument("--manifest", type=Path, required=True)
    build_parser.add_argument("--fan-in", type=int, default=8)
    build_parser.add_argument("--minimum-free-gib", type=float, default=50.0)
    args = parser.parse_args()
    try:
        if args.minimum_free_gib < 0:
            raise CandidateIndexError("minimum free GiB cannot be negative")
        if args.command == "reduce":
            result = reduce_scan_set(
                args.scan_dir,
                args.mesh,
                fan_in=args.fan_in,
                minimum_free_bytes=int(args.minimum_free_gib * 1024**3),
                progress=lambda message: print(message, flush=True),
            )
            print(f"distinct PubMed rows: {result.pmid_vector.rows}")
            print(f"descriptor assignments: {result.descriptor_assignments}")
            print(f"positive pair rows: {result.positive_pairs.rows}")
            print(f"pair observations: {result.pair_observations}")
            print("readiness contribution: 0 (candidate stream and metric are absent)")
        else:
            result = build_candidate_universe(
                args.scan_dir,
                args.mesh,
                args.manifest,
                fan_in=args.fan_in,
                minimum_free_bytes=int(args.minimum_free_gib * 1024**3),
                progress=lambda message: print(message, flush=True),
            )
            print(f"candidate pairs: {result['counts']['candidate_pairs']}")
            print("readiness contribution: 0 (no metric, prediction, or outcome result)")
    except (CandidateIndexError, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(str(exc)) from None


if __name__ == "__main__":
    main()
