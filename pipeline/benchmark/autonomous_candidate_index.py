"""Build score-free, resumable T0 count shards on an explicitly selected data volume.

The scan stage measures exact descriptor supports, exact positive co-occurrence counts, and PMIDs
per sealed PubMed file. It emits no candidate set, score, rank, prediction, or interpretation.
Global PMID uniqueness, external pair reduction, and candidate generation are later fail-closed
stages governed by ``benchmarks/autonomous/t0-candidate-index-v1.json``.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import unicodedata
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import BinaryIO, Callable
from xml.etree import ElementTree

import numpy as np

from pipeline.benchmark.autonomous_t0 import (
    SEALED_T0_PATH,
    AutonomousT0Error,
    _promote_verified_part,
    audit_sealed_t0,
    write_new_json,
)
from pipeline.benchmark.validate_autonomous_candidate_index import (
    CONTRACT_PATH,
    audit_candidate_index_contract,
)

DESCRIPTOR_UI = re.compile(r"^D\d{6,9}$")
PAIR_DTYPE = np.dtype([("key", "<u8"), ("count", "<u4")])


class CandidateIndexError(ValueError):
    """The score-free T0 count index cannot advance its machine gate."""


@dataclass(frozen=True)
class VocabularyDescriptor:
    ui: str
    label: str
    tree_numbers: tuple[str, ...]
    terms: tuple[str, ...]


@dataclass(frozen=True)
class VocabularyAudit:
    descriptor_count: int
    sha256: str
    bytes: int
    descriptors: tuple[VocabularyDescriptor, ...]


@dataclass(frozen=True)
class SourceShardAudit:
    source_filename: str
    source_sha256: str
    parsed_record_count: int
    records_without_mesh: int
    descriptor_assignments: int
    positive_pair_rows: int
    pair_observations: int
    status: str


class _DigestingReader:
    """Hash raw compressed bytes while GzipFile consumes them."""

    def __init__(self, raw: BinaryIO) -> None:
        self.raw = raw
        self.digest = hashlib.sha256()
        self.bytes_read = 0

    def read(self, size: int = -1) -> bytes:
        data = self.raw.read(size)
        if data:
            self.digest.update(data)
            self.bytes_read += len(data)
        return data

    def tell(self) -> int:
        return self.raw.tell()

    def seekable(self) -> bool:
        return False


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalise_term(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def read_vocabulary(path: Path, *, expected_sha256: str, expected_count: int) -> VocabularyAudit:
    """Parse the complete descriptor transport and establish stable UI order and exclusions."""
    actual_sha256 = _sha256_file(path)
    size = path.stat().st_size
    if actual_sha256 != expected_sha256:
        raise CandidateIndexError("MeSH transport differs from the sealed T0 manifest")
    descriptors: list[VocabularyDescriptor] = []
    seen: set[str] = set()
    try:
        with gzip.open(path, "rb") as stream:
            context = ElementTree.iterparse(stream, events=("start", "end"))
            _event, root = next(context)
            if root.tag.rsplit("}", 1)[-1] != "DescriptorRecordSet":
                raise CandidateIndexError("unexpected MeSH XML root")
            for event, element in context:
                if event != "end" or element.tag.rsplit("}", 1)[-1] != "DescriptorRecord":
                    continue
                ui = element.findtext("./DescriptorUI") or ""
                if not DESCRIPTOR_UI.fullmatch(ui) or ui in seen:
                    raise CandidateIndexError("invalid or duplicate MeSH descriptor UI")
                seen.add(ui)
                label = element.findtext("./DescriptorName/String") or ""
                trees = tuple(
                    sorted(
                        {
                            (node.text or "").strip()
                            for node in element.findall("./TreeNumberList/TreeNumber")
                            if (node.text or "").strip()
                        }
                    )
                )
                terms = tuple(
                    sorted(
                        {
                            normalised
                            for node in element.findall(
                                "./ConceptList/Concept/TermList/Term/String"
                            )
                            if (normalised := _normalise_term(node.text or ""))
                        }
                    )
                )
                descriptors.append(
                    VocabularyDescriptor(
                        ui=ui,
                        label=label,
                        tree_numbers=trees,
                        terms=terms,
                    )
                )
                root.clear()
    except (OSError, ElementTree.ParseError, StopIteration) as exc:
        raise CandidateIndexError("invalid sealed MeSH descriptor transport") from exc
    descriptors.sort(key=lambda item: item.ui)
    if len(descriptors) != expected_count:
        raise CandidateIndexError(
            f"MeSH descriptor count differs from sealed T0 ({len(descriptors)} != {expected_count})"
        )
    return VocabularyAudit(
        descriptor_count=len(descriptors),
        sha256=actual_sha256,
        bytes=size,
        descriptors=tuple(descriptors),
    )


def _write_binary_part(path: Path, array: np.ndarray) -> tuple[str, int]:
    destination = path
    part = destination.with_name(f"{destination.name}.part")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with part.open("wb") as handle:
        array.tofile(handle)
        handle.flush()
        os.fsync(handle.fileno())
    digest = _sha256_file(part)
    size = part.stat().st_size
    if destination.exists():
        if destination.stat().st_size != size or _sha256_file(destination) != digest:
            raise CandidateIndexError(f"refusing to replace conflicting shard: {destination}")
        part.unlink()
    else:
        try:
            _promote_verified_part(part, destination)
        except AutonomousT0Error as exc:
            raise CandidateIndexError(str(exc)) from exc
    return digest, size


def _audit_existing_shard(
    shard_dir: Path,
    *,
    contract_sha256: str,
    vocabulary_sha256: str,
    vocabulary_size: int,
    source: dict,
) -> SourceShardAudit | None:
    checkpoint = shard_dir / "checkpoint.json"
    if not checkpoint.exists():
        return None
    payload = json.loads(checkpoint.read_text(encoding="utf-8"))
    if (
        payload.get("schema_version") != 1
        or payload.get("kind") != "autonomous_t0_source_count_shard"
        or payload.get("candidate_index_contract_sha256") != contract_sha256
        or payload.get("vocabulary_sha256") != vocabulary_sha256
        or payload.get("source")
        != {
            "filename": source["filename"],
            "sha256": source["sha256"],
            "bytes": source["bytes"],
            "total_record_count": source["total_record_count"],
        }
    ):
        raise CandidateIndexError(f"checkpoint identity drifted: {source['filename']}")
    outputs = payload.get("outputs")
    if not isinstance(outputs, dict) or set(outputs) != {"pairs", "supports", "pmids"}:
        raise CandidateIndexError(f"checkpoint outputs drifted: {source['filename']}")
    expected_filenames = {
        "pairs": "pairs.bin",
        "supports": "supports.bin",
        "pmids": "pmids.bin",
    }
    for key, item in outputs.items():
        if (
            not isinstance(item, dict)
            or set(item) != {"filename", "sha256", "bytes"}
            or item.get("filename") != expected_filenames[key]
            or not isinstance(item.get("sha256"), str)
            or re.fullmatch(r"[0-9a-f]{64}", item["sha256"]) is None
            or type(item.get("bytes")) is not int
            or item["bytes"] < 0
        ):
            raise CandidateIndexError(f"checkpoint output identity drifted: {source['filename']}")
        path = shard_dir / expected_filenames[key]
        if (
            not path.is_file()
            or path.stat().st_size != item["bytes"]
            or _sha256_file(path) != item["sha256"]
        ):
            raise CandidateIndexError(f"checkpoint shard bytes drifted: {source['filename']}")
    measured = payload.get("measured", {})
    if (
        not isinstance(measured, dict)
        or set(measured)
        != {
            "parsed_record_count",
            "records_without_mesh",
            "descriptor_assignments",
            "positive_pair_rows",
            "pair_observations",
        }
        or measured.get("parsed_record_count") != source["total_record_count"]
        or type(measured.get("records_without_mesh")) is not int
        or type(measured.get("descriptor_assignments")) is not int
        or type(measured.get("positive_pair_rows")) is not int
        or type(measured.get("pair_observations")) is not int
        or any(value < 0 for value in measured.values())
        or measured["records_without_mesh"] > measured["parsed_record_count"]
        or measured["positive_pair_rows"] > measured["pair_observations"]
    ):
        raise CandidateIndexError(f"checkpoint measurements drifted: {source['filename']}")
    if outputs["supports"]["bytes"] != vocabulary_size * np.dtype("<u4").itemsize:
        raise CandidateIndexError(f"checkpoint support shape drifted: {source['filename']}")
    if outputs["pmids"]["bytes"] != measured["parsed_record_count"] * np.dtype("<u8").itemsize:
        raise CandidateIndexError(f"checkpoint PMID shape drifted: {source['filename']}")
    if outputs["pairs"]["bytes"] != measured["positive_pair_rows"] * PAIR_DTYPE.itemsize:
        raise CandidateIndexError(f"checkpoint pair shape drifted: {source['filename']}")

    supports = np.fromfile(shard_dir / "supports.bin", dtype="<u4")
    pmids = np.fromfile(shard_dir / "pmids.bin", dtype="<u8")
    pairs = np.fromfile(shard_dir / "pairs.bin", dtype=PAIR_DTYPE)
    pair_keys = pairs["key"]
    left = pair_keys // np.uint64(vocabulary_size)
    right = pair_keys % np.uint64(vocabulary_size)
    if (
        int(supports.astype("<u8").sum()) != measured["descriptor_assignments"]
        or (pmids.size > 1 and bool(np.any(pmids[1:] <= pmids[:-1])))
        or (pair_keys.size > 1 and bool(np.any(pair_keys[1:] <= pair_keys[:-1])))
        or bool(np.any(right >= vocabulary_size))
        or bool(np.any(left >= right))
        or bool(np.any(pairs["count"] == 0))
        or int(pairs["count"].astype("<u8").sum()) != measured["pair_observations"]
    ):
        raise CandidateIndexError(f"checkpoint shard invariants drifted: {source['filename']}")
    return SourceShardAudit(
        source_filename=source["filename"],
        source_sha256=source["sha256"],
        parsed_record_count=measured["parsed_record_count"],
        records_without_mesh=measured["records_without_mesh"],
        descriptor_assignments=measured["descriptor_assignments"],
        positive_pair_rows=measured["positive_pair_rows"],
        pair_observations=measured["pair_observations"],
        status="reused",
    )


def scan_source_file(
    source_path: Path,
    source: dict,
    shard_dir: Path,
    *,
    ui_to_index: dict[str, int],
    vocabulary_sha256: str,
    contract_sha256: str,
) -> SourceShardAudit:
    """Measure one sealed PubMed transport and write immutable score-free shards."""
    reused = _audit_existing_shard(
        shard_dir,
        contract_sha256=contract_sha256,
        vocabulary_sha256=vocabulary_sha256,
        vocabulary_size=len(ui_to_index),
        source=source,
    )
    if reused is not None:
        return reused
    shard_dir.mkdir(parents=True, exist_ok=True)
    for name in ("pairs.bin", "supports.bin", "pmids.bin"):
        if (shard_dir / name).exists():
            raise CandidateIndexError(
                f"uncheckpointed complete shard refuses overwrite: {source['filename']}"
            )

    vocabulary_size = len(ui_to_index)
    supports = np.zeros(vocabulary_size, dtype="<u4")
    pmids: list[int] = []
    pair_blocks: list[np.ndarray] = []
    parsed_records = 0
    records_without_mesh = 0
    descriptor_assignments = 0
    pair_observations = 0
    unknown: set[str] = set()

    try:
        with source_path.open("rb") as raw:
            digesting = _DigestingReader(raw)
            with gzip.GzipFile(fileobj=digesting, mode="rb") as stream:
                context = ElementTree.iterparse(stream, events=("start", "end"))
                _event, root = next(context)
                if root.tag != "PubmedArticleSet":
                    raise CandidateIndexError(f"{source_path.name}: unexpected PubMed XML root")
                for event, element in context:
                    if event != "end" or element.tag != "PubmedArticle":
                        continue
                    citation = element.find("./MedlineCitation")
                    if citation is None:
                        raise CandidateIndexError(f"{source_path.name}: article lacks MedlineCitation")
                    pmid_text = citation.findtext("./PMID") or ""
                    if not pmid_text.isdecimal():
                        raise CandidateIndexError(f"{source_path.name}: missing or invalid PMID")
                    pmids.append(int(pmid_text))
                    parsed_records += 1
                    indices: set[int] = set()
                    for descriptor in citation.findall(
                        "./MeshHeadingList/MeshHeading/DescriptorName"
                    ):
                        ui = descriptor.get("UI", "")
                        index = ui_to_index.get(ui)
                        if index is None:
                            unknown.add(ui)
                        else:
                            indices.add(index)
                    if unknown:
                        example = sorted(unknown)[0]
                        raise CandidateIndexError(
                            f"{source_path.name}: descriptor absent from sealed vocabulary: {example}"
                        )
                    if not indices:
                        records_without_mesh += 1
                        root.clear()
                        continue
                    ordered = np.fromiter(sorted(indices), dtype="<u4")
                    if np.any(supports[ordered] == np.iinfo(np.uint32).max):
                        raise CandidateIndexError("descriptor support overflow")
                    supports[ordered] += 1
                    descriptor_assignments += int(ordered.size)
                    if ordered.size > 1:
                        left, right = np.triu_indices(ordered.size, k=1)
                        keys = (
                            ordered[left].astype("<u8") * np.uint64(vocabulary_size)
                            + ordered[right].astype("<u8")
                        )
                        pair_blocks.append(keys)
                        pair_observations += int(keys.size)
                    root.clear()
            # Consume any compressed trailer bytes not requested by the XML parser.
            while digesting.read(1024 * 1024):
                pass
            source_sha256 = digesting.digest.hexdigest()
            source_bytes = digesting.bytes_read
    except (OSError, ElementTree.ParseError, EOFError) as exc:
        raise CandidateIndexError(f"{source_path.name}: invalid PubMed transport") from exc

    if source_sha256 != source["sha256"] or source_bytes != source["bytes"]:
        raise CandidateIndexError(f"{source_path.name}: sealed source hash or byte count drifted")
    if parsed_records != source["total_record_count"]:
        raise CandidateIndexError(
            f"{source_path.name}: record subtotal drifted "
            f"({parsed_records} != {source['total_record_count']})"
        )
    pmid_array = np.asarray(pmids, dtype="<u8")
    pmid_array.sort()
    if pmid_array.size and np.any(pmid_array[1:] == pmid_array[:-1]):
        raise CandidateIndexError(f"{source_path.name}: duplicate PMID within source file")
    if pair_blocks:
        all_keys = np.concatenate(pair_blocks)
        pair_keys, pair_counts64 = np.unique(all_keys, return_counts=True)
        if np.any(pair_counts64 > np.iinfo(np.uint32).max):
            raise CandidateIndexError("within-file pair count overflow")
        pairs = np.empty(pair_keys.size, dtype=PAIR_DTYPE)
        pairs["key"] = pair_keys
        pairs["count"] = pair_counts64.astype("<u4")
    else:
        pairs = np.empty(0, dtype=PAIR_DTYPE)

    pair_sha, pair_bytes = _write_binary_part(shard_dir / "pairs.bin", pairs)
    support_sha, support_bytes = _write_binary_part(shard_dir / "supports.bin", supports)
    pmid_sha, pmid_bytes = _write_binary_part(shard_dir / "pmids.bin", pmid_array)
    checkpoint = {
        "schema_version": 1,
        "kind": "autonomous_t0_source_count_shard",
        "candidate_index_contract_sha256": contract_sha256,
        "vocabulary_sha256": vocabulary_sha256,
        "source": {
            "filename": source["filename"],
            "sha256": source["sha256"],
            "bytes": source["bytes"],
            "total_record_count": source["total_record_count"],
        },
        "measured": {
            "parsed_record_count": parsed_records,
            "records_without_mesh": records_without_mesh,
            "descriptor_assignments": descriptor_assignments,
            "positive_pair_rows": int(pairs.size),
            "pair_observations": pair_observations,
        },
        "outputs": {
            "pairs": {"filename": "pairs.bin", "sha256": pair_sha, "bytes": pair_bytes},
            "supports": {
                "filename": "supports.bin",
                "sha256": support_sha,
                "bytes": support_bytes,
            },
            "pmids": {"filename": "pmids.bin", "sha256": pmid_sha, "bytes": pmid_bytes},
        },
        "readiness_contribution": 0,
        "claim_boundary": "Score-free per-source exact counts only; global uniqueness and candidate gates have not run.",
    }
    try:
        write_new_json(shard_dir / "checkpoint.json", checkpoint)
    except AutonomousT0Error as exc:
        raise CandidateIndexError(str(exc)) from exc
    return SourceShardAudit(
        source_filename=source["filename"],
        source_sha256=source_sha256,
        parsed_record_count=parsed_records,
        records_without_mesh=records_without_mesh,
        descriptor_assignments=descriptor_assignments,
        positive_pair_rows=int(pairs.size),
        pair_observations=pair_observations,
        status="measured",
    )


_WORKER_CONTEXT: dict | None = None


def _init_worker(ui_to_index: dict[str, int], vocabulary_sha256: str, contract_sha256: str) -> None:
    global _WORKER_CONTEXT
    _WORKER_CONTEXT = {
        "ui_to_index": ui_to_index,
        "vocabulary_sha256": vocabulary_sha256,
        "contract_sha256": contract_sha256,
    }


def _scan_task(task: tuple[str, dict, str]) -> SourceShardAudit:
    if _WORKER_CONTEXT is None:
        raise CandidateIndexError("scan worker was not initialized")
    source_path, source, shard_dir = task
    return scan_source_file(
        Path(source_path),
        source,
        Path(shard_dir),
        **_WORKER_CONTEXT,
    )


def _require_non_system_volume(path: Path) -> None:
    if os.name != "nt":
        return
    system_drive = os.environ.get("SystemDrive", "C:").upper()
    resolved_drive = Path(path.resolve()).drive.upper()
    if resolved_drive == system_drive:
        raise CandidateIndexError(f"candidate index must not use the system volume: {path}")


def scan_t0_sources(
    baseline_dir: Path,
    mesh_path: Path,
    output_dir: Path,
    *,
    workers: int = 4,
    minimum_free_bytes: int = 100 * 1024**3,
    enforce_non_system_volume: bool = True,
    progress: Callable[[int, int, SourceShardAudit], None] | None = None,
) -> tuple[SourceShardAudit, ...]:
    """Scan every sealed source into restartable off-system-volume count shards."""
    if not 1 <= workers <= 16:
        raise CandidateIndexError("scan workers must be between 1 and 16")
    contract = audit_candidate_index_contract()
    sealed = audit_sealed_t0()
    if enforce_non_system_volume:
        _require_non_system_volume(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(output_dir).free < minimum_free_bytes:
        raise CandidateIndexError("candidate-index volume has insufficient free space")
    payload = json.loads(SEALED_T0_PATH.read_text(encoding="utf-8"))
    source_files = payload["pubmed_baseline"]["files"]
    if any(
        item["pubmed_book_article_count"] != 0 or item["delete_citation_count"] != 0
        for item in source_files
    ):
        raise CandidateIndexError("sealed source contains unsupported book or delete records")
    vocabulary = read_vocabulary(
        mesh_path,
        expected_sha256=payload["mesh_descriptor"]["sha256"],
        expected_count=sealed.mesh_descriptor_count,
    )
    ui_to_index = {item.ui: index for index, item in enumerate(vocabulary.descriptors)}
    if len(ui_to_index) != vocabulary.descriptor_count:
        raise CandidateIndexError("vocabulary UI index is not one-to-one")
    tasks = []
    for source in source_files:
        path = baseline_dir / source["filename"]
        if not path.is_file():
            raise CandidateIndexError(f"sealed source file is missing: {path}")
        tasks.append((str(path), source, str(output_dir / "shards" / source["filename"])))

    results: list[SourceShardAudit] = []
    if workers == 1:
        _init_worker(ui_to_index, vocabulary.sha256, contract.sha256)
        for task in tasks:
            result = _scan_task(task)
            results.append(result)
            if progress is not None:
                progress(len(results), len(tasks), result)
    else:
        with ProcessPoolExecutor(
            max_workers=workers,
            initializer=_init_worker,
            initargs=(ui_to_index, vocabulary.sha256, contract.sha256),
        ) as executor:
            futures = {executor.submit(_scan_task, task): task[1]["filename"] for task in tasks}
            for future in as_completed(futures):
                try:
                    result = future.result()
                except Exception:
                    for pending in futures:
                        pending.cancel()
                    raise
                results.append(result)
                if progress is not None:
                    progress(len(results), len(tasks), result)
    results.sort(key=lambda item: item.source_filename)
    if sum(item.parsed_record_count for item in results) != sealed.pubmed_record_count:
        raise CandidateIndexError("scan record aggregate differs from sealed T0")
    return tuple(results)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    scan = subparsers.add_parser("scan")
    scan.add_argument("--baseline-dir", type=Path, required=True)
    scan.add_argument("--mesh", type=Path, required=True)
    scan.add_argument("--output-dir", type=Path, required=True)
    scan.add_argument("--workers", type=int, default=4)
    scan.add_argument("--minimum-free-gib", type=float, default=100.0)
    args = parser.parse_args()
    try:
        if args.minimum_free_gib < 0:
            raise CandidateIndexError("minimum free GiB cannot be negative")

        def show_progress(completed: int, total: int, result: SourceShardAudit) -> None:
            if completed % 10 == 0 or completed == total:
                print(
                    f"source shards: {completed}/{total} | {result.source_filename} | "
                    f"{result.status}",
                    flush=True,
                )

        results = scan_t0_sources(
            args.baseline_dir,
            args.mesh,
            args.output_dir,
            workers=args.workers,
            minimum_free_bytes=int(args.minimum_free_gib * 1024**3),
            progress=show_progress,
        )
        print(f"source files scanned: {len(results)}")
        print(f"PubMed rows: {sum(item.parsed_record_count for item in results)}")
        print(f"descriptor assignments: {sum(item.descriptor_assignments for item in results)}")
        print(f"positive pair rows before global merge: {sum(item.positive_pair_rows for item in results)}")
        print("readiness contribution: 0 (global dedup, merge, and candidate gates have not run)")
    except (CandidateIndexError, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(str(exc)) from None


if __name__ == "__main__":
    main()
