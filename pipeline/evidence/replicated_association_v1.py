"""Build and audit the frozen evidence-v1 replicated-association experiment.

The experiment measures rank-expression associations in two independent breast-tumour cohorts.
Its outputs are bounded computational observations, not causal, mechanistic, clinical, or
novel-to-humanity claims.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import os
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Mapping, Sequence

import numpy as np

from pipeline.paths import ARTIFACTS_DIR, BENCHMARKS_DIR, REPO_ROOT
from pipeline.provenance import canonical_json_bytes, sha256_payload

PROTOCOL_PATH = BENCHMARKS_DIR / "evidence-v1.json"
SOURCE_MANIFEST_PATH = BENCHMARKS_DIR / "evidence" / "source-v1.json"
UNIVERSE_MANIFEST_PATH = BENCHMARKS_DIR / "evidence" / "candidate-universe-v1.json"
RESULT_MANIFEST_PATH = ARTIFACTS_DIR / "evidence-v1.json"
MODULE_PATH = Path(__file__).resolve()
BASE_PROTOCOL_SHA256 = "f0fe2090a08011616d205b129057044b9b3da1efd4280e6e55753f98d9fa21e2"
BASE_PROTOCOL_COMMIT = "e0b36b7"

EXPECTED_SOURCE_IDENTITIES = {
    "tcga_brca_pancan_2018_expression": {
        "study_id": "brca_tcga_pan_can_atlas_2018",
        "filename": "data_mrna_seq_v2_rsem.txt",
        "bytes": 154654165,
        "sha256": "aba030e1f04a196ee6c2118ed37e777b533f7fd24ffd1bcbde908dcee33b2eb5",
        "platform": "batch_normalized_illumina_hiseq_rnaseqv2_rsem",
    },
    "metabric_brca_expression": {
        "study_id": "brca_metabric",
        "filename": "data_mrna_illumina_microarray.txt",
        "bytes": 689254846,
        "sha256": "4470069455a4ed38ffed5d12513e468bbf5b9a57d66fa1162e7bd9a64889ab7a",
        "platform": "illumina_ht12_v3_microarray_log2_intensity",
    },
}


class EvidenceV1Error(ValueError):
    """Raised when evidence-v1 must refuse or abstain."""


@dataclass(frozen=True)
class SourceSpec:
    source_id: str
    study_id: str
    filename: str
    url: str
    bytes: int
    sha256: str
    platform: str


@dataclass(frozen=True)
class SourceScan:
    source_id: str
    path: Path
    bytes: int
    sha256: str
    sample_count: int
    row_count: int
    positive_entrez_row_count: int
    unique_positive_entrez_count: int
    duplicate_positive_entrez_count: int
    blank_symbol_count: int
    nonfinite_value_count: int


@dataclass(frozen=True)
class ResultAudit:
    state: str
    claim_count: int
    tested_pair_count: int
    null_pass_count: int
    readiness_contribution: int


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceV1Error(message)


def _sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path, label: str) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceV1Error(f"{label} is not readable JSON: {path}") from exc
    _require(isinstance(payload, dict), f"{label} must be a JSON object")
    return payload


def _write_new_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, indent=1, ensure_ascii=False).encode("utf-8")
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    except FileExistsError as exc:
        raise EvidenceV1Error(f"refusing to overwrite sealed evidence: {path}") from exc
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(encoded)


def _module_sha256() -> str:
    return _sha256_file(MODULE_PATH)


def _score_free_protocol_sha256(protocol: Mapping) -> str:
    base = protocol.get("base_freeze")
    if isinstance(base, dict):
        return str(base.get("canonical_json_sha256", ""))
    return sha256_payload(protocol)


def _source_specs(protocol: Mapping) -> tuple[SourceSpec, ...]:
    specs: list[SourceSpec] = []
    sources = protocol.get("sources")
    _require(isinstance(sources, list) and len(sources) == 2, "exactly two sources are required")
    for item in sources:
        _require(isinstance(item, dict), "source entry is malformed")
        specs.append(
            SourceSpec(
                source_id=str(item.get("id", "")),
                study_id=str(item.get("study_id", "")),
                filename=str(item.get("filename", "")),
                url=str(item.get("url", "")),
                bytes=int(item.get("bytes", -1)),
                sha256=str(item.get("sha256", "")),
                platform=str(item.get("platform", "")),
            )
        )
    return tuple(specs)


def audit_protocol(path: Path = PROTOCOL_PATH) -> dict:
    payload = _load_json(path, "evidence-v1 protocol")
    _require(payload.get("schema_version") == 1, "protocol schema drifted")
    _require(payload.get("id") == "replicated-expression-association-v1", "protocol id drifted")
    _require(
        payload.get("status") == "frozen_before_any_pairwise_association",
        "protocol is not frozen before pairwise measurement",
    )
    _require(payload.get("human_dependencies") == [], "human dependency entered evidence-v1")
    _require(payload.get("manual_override_allowed") is False, "manual override entered evidence-v1")
    _require(payload.get("llm_interpretation_authorized") is False, "LLM interpretation entered evidence-v1")

    freeze = payload.get("freeze_boundary")
    _require(isinstance(freeze, dict), "freeze boundary is missing")
    _require(
        freeze.get("seen_before_freeze")
        == [
            "two complete source transports and their Git LFS byte identities",
            "source metadata, both headers, and one data row per source for parser conformance",
        ],
        "pre-freeze disclosure drifted",
    )
    unseen = freeze.get("not_seen_before_freeze")
    _require(
        unseen
        == [
            "any pairwise association",
            "any candidate ranking",
            "any passing or null-control pair count",
        ],
        "outcome-blind freeze boundary drifted",
    )

    specs = _source_specs(payload)
    _require(len({spec.source_id for spec in specs}) == 2, "source ids are not distinct")
    _require(len({spec.study_id for spec in specs}) == 2, "cohort study ids are not distinct")
    _require(len({spec.platform for spec in specs}) == 2, "measurement platforms are not distinct")
    _require({spec.source_id for spec in specs} == set(EXPECTED_SOURCE_IDENTITIES), "source ids drifted")
    for spec in specs:
        expected = EXPECTED_SOURCE_IDENTITIES[spec.source_id]
        _require(
            {
                "study_id": spec.study_id,
                "filename": spec.filename,
                "bytes": spec.bytes,
                "sha256": spec.sha256,
                "platform": spec.platform,
            }
            == expected,
            f"{spec.source_id}: source identity drifted",
        )
        _require(spec.bytes > 100_000_000, f"{spec.source_id}: source byte identity is implausible")
        _require(len(spec.sha256) == 64, f"{spec.source_id}: source SHA-256 is malformed")
        _require(
            spec.url.startswith("https://media.githubusercontent.com/media/cBioPortal/datahub/")
            and "/0cc9138746c08b304f8dac92c31983e0ef44af1d/" in spec.url,
            f"{spec.source_id}: source URL is not commit-pinned",
        )

    universe = payload.get("candidate_universe")
    _require(isinstance(universe, dict), "candidate-universe rule is missing")
    _require(
        universe.get("selection") == "sha256_bottom_k_over_common_unique_positive_entrez_gene_ids"
        and universe.get("k") == 1000
        and isinstance(universe.get("seed"), str)
        and universe.get("pair_order") == "all_unordered_pairs_entrez_id_ascending"
        and universe.get("expected_pair_count") == 499500
        and universe.get("uses_expression_values") is False,
        "score-free candidate-universe rule drifted",
    )

    measurement = payload.get("measurement")
    _require(isinstance(measurement, dict), "measurement contract is missing")
    _require(
        measurement.get("association") == "spearman_average_ties"
        and measurement.get("p_value") == "two_sided_fisher_z_normal_approximation"
        and measurement.get("multiple_testing") == "benjamini_hochberg_per_cohort"
        and measurement.get("quantize_rho_decimals_before_gates") == 8,
        "measurement formula drifted",
    )

    gates = payload.get("machine_gates")
    _require(isinstance(gates, dict), "machine gates are missing")
    _require(
        gates.get("minimum_samples_per_cohort") == 800
        and gates.get("minimum_analyzable_genes_per_cohort") == 950
        and gates.get("maximum_q_per_cohort") == 0.01
        and gates.get("minimum_absolute_rho_per_cohort") == 0.4
        and gates.get("maximum_absolute_rho_difference") == 0.15
        and gates.get("same_direction_required") is True
        and gates.get("maximum_null_pass_count") == 5,
        "evidence gates drifted",
    )
    null = payload.get("negative_control")
    _require(
        isinstance(null, dict)
        and null.get("method") == "independent_sample_permutation_per_gene_per_cohort"
        and null.get("replicates") == 1
        and isinstance(null.get("seed"), str)
        and null.get("failure_action") == "abstain_without_claims",
        "negative-control contract drifted",
    )

    publication = payload.get("publication")
    _require(
        isinstance(publication, dict)
        and publication.get("status_label") == "replicated_computational_observation"
        and publication.get("maximum_published_claims") == 100
        and publication.get("full_pair_table_required") is True
        and publication.get("overwrite_allowed") is False,
        "publication contract drifted",
    )
    boundary = payload.get("claim_boundary")
    _require(isinstance(boundary, dict), "claim boundary is missing")
    excluded = boundary.get("not_a_claim_of")
    _require(
        isinstance(excluded, list)
        and {
            "causality",
            "mechanism",
            "clinical utility or safety",
            "cell-intrinsic regulation",
            "novelty to humanity",
            "absence of academic or non-academic knowledge",
            "a validated knowledge-gap detector",
        }
        <= set(excluded),
        "claim boundary permits overclaiming",
    )
    _require(
        boundary.get("allowed_claim")
        == "a bounded rank-expression association observed in both pinned cohorts under this frozen protocol",
        "allowed claim drifted",
    )
    source = payload.get("implementation")
    _require(
        isinstance(source, dict)
        and source.get("path") == "../pipeline/evidence/replicated_association_v1.py"
        and source.get("sha256") == _module_sha256(),
        "evidence-v1 implementation identity drifted",
    )
    _require(
        payload.get("base_freeze")
        == {
            "commit": BASE_PROTOCOL_COMMIT,
            "canonical_json_sha256": BASE_PROTOCOL_SHA256,
            "implementation_sha256": "6a2f3ef73560ae13ee5f635ea5b2ee87d29311be17e75579ba6e8edc9573a4ed",
        },
        "base freeze identity drifted",
    )
    amendments = payload.get("amendments")
    _require(isinstance(amendments, list) and len(amendments) == 1, "amendment trail drifted")
    amendment = amendments[0]
    _require(
        amendment.get("id") == "A1"
        and amendment.get("outcome_seen") is False
        and "before any pairwise association" in amendment.get("timing", "")
        and "Entrez 404217" in amendment.get("trigger", "")
        and "already-frozen" in amendment.get("trigger", "")
        and "censors the gene" in amendment.get("change", "")
        and set(amendment.get("unchanged", []))
        == {
            "both source byte identities",
            "the sealed 1,000-gene universe and all 499,500 pair identities",
            "all effect, q-value, agreement, power, and null-control thresholds",
            "all claim boundaries",
        },
        "A1 disclosure drifted",
    )
    _require(payload.get("readiness_contribution") == 0, "protocol claims evidential readiness")
    return payload


def source_paths(source_dir: Path, protocol: Mapping) -> dict[str, Path]:
    return {
        spec.source_id: source_dir / f"{spec.study_id}-{spec.filename}"
        for spec in _source_specs(protocol)
    }


def _verify_source_file(path: Path, spec: SourceSpec) -> None:
    _require(path.is_file(), f"{spec.source_id}: source file missing: {path}")
    _require(path.stat().st_size == spec.bytes, f"{spec.source_id}: source byte count drifted")
    _require(_sha256_file(path) == spec.sha256, f"{spec.source_id}: source SHA-256 drifted")


def _row_identity(row: Sequence[str], context: str) -> tuple[str, int | None]:
    _require(len(row) >= 3, f"{context}: row is too short")
    symbol = row[0].strip()
    raw_entrez = row[1].strip()
    if not raw_entrez:
        return symbol, None
    try:
        entrez = int(raw_entrez)
    except ValueError:
        return symbol, None
    return symbol, entrez if entrez > 0 else None


def iter_source_rows(path: Path) -> tuple[list[str], Iterator[list[str]]]:
    handle = path.open("r", encoding="utf-8", newline="")
    reader = csv.reader(handle, delimiter="\t")
    try:
        header = next(reader)
    except StopIteration as exc:
        handle.close()
        raise EvidenceV1Error(f"empty expression source: {path}") from exc
    _require(header[:2] == ["Hugo_Symbol", "Entrez_Gene_Id"], f"source header drifted: {path}")
    _require(len(header) == len(set(header)), f"duplicate source columns: {path}")

    def rows() -> Iterator[list[str]]:
        try:
            yield from reader
        finally:
            handle.close()

    return header, rows()


def scan_source(path: Path, spec: SourceSpec) -> SourceScan:
    _verify_source_file(path, spec)
    header, rows = iter_source_rows(path)
    expected_fields = len(header)
    ids: Counter[int] = Counter()
    row_count = blank_symbols = nonfinite = 0
    for row_number, row in enumerate(rows, start=2):
        _require(len(row) == expected_fields, f"{spec.source_id}: row {row_number} width drifted")
        symbol, entrez = _row_identity(row, f"{spec.source_id}: row {row_number}")
        row_count += 1
        blank_symbols += int(not symbol)
        if entrez is not None:
            ids[entrez] += 1
        for column_number, raw in enumerate(row[2:], start=3):
            try:
                value = float(raw)
            except ValueError:
                nonfinite += 1
                continue
            if not math.isfinite(value):
                nonfinite += 1
    return SourceScan(
        source_id=spec.source_id,
        path=path,
        bytes=path.stat().st_size,
        sha256=spec.sha256,
        sample_count=expected_fields - 2,
        row_count=row_count,
        positive_entrez_row_count=sum(ids.values()),
        unique_positive_entrez_count=len(ids),
        duplicate_positive_entrez_count=sum(1 for count in ids.values() if count > 1),
        blank_symbol_count=blank_symbols,
        nonfinite_value_count=nonfinite,
    )


def build_source_manifest(source_dir: Path, output: Path = SOURCE_MANIFEST_PATH) -> dict:
    protocol = audit_protocol()
    scans = [
        scan_source(source_paths(source_dir, protocol)[spec.source_id], spec)
        for spec in _source_specs(protocol)
    ]
    payload = {
        "schema_version": 1,
        "id": "replicated-expression-source-v1",
        "status": "score_free_source_audit_complete",
        "protocol": {
            "id": protocol["id"],
            "canonical_json_sha256": _score_free_protocol_sha256(protocol),
        },
        "sources": [
            {
                "id": scan.source_id,
                "local_filename": scan.path.name,
                "bytes": scan.bytes,
                "sha256": scan.sha256,
                "sample_count": scan.sample_count,
                "row_count": scan.row_count,
                "positive_entrez_row_count": scan.positive_entrez_row_count,
                "unique_positive_entrez_count": scan.unique_positive_entrez_count,
                "duplicate_positive_entrez_count": scan.duplicate_positive_entrez_count,
                "blank_symbol_count": scan.blank_symbol_count,
                "nonfinite_value_count": scan.nonfinite_value_count,
            }
            for scan in scans
        ],
        "pairwise_associations_computed": False,
        "candidate_ranking_computed": False,
        "readiness_contribution": 0,
        "claim_boundary": "Complete byte and parse audit only; not an association, finding, discovery, or knowledge claim.",
    }
    _write_new_json(output, payload)
    audit_source_manifest(output)
    return payload


def audit_source_manifest(path: Path = SOURCE_MANIFEST_PATH) -> dict:
    protocol = audit_protocol()
    payload = _load_json(path, "evidence-v1 source manifest")
    _require(payload.get("schema_version") == 1, "source-manifest schema drifted")
    _require(
        payload.get("id") == "replicated-expression-source-v1"
        and payload.get("status") == "score_free_source_audit_complete",
        "source-manifest identity drifted",
    )
    _require(
        payload.get("protocol")
        == {"id": protocol["id"], "canonical_json_sha256": _score_free_protocol_sha256(protocol)},
        "source manifest does not pin the protocol",
    )
    entries = payload.get("sources")
    specs = {spec.source_id: spec for spec in _source_specs(protocol)}
    _require(isinstance(entries, list) and len(entries) == 2, "source audit entries drifted")
    _require({entry.get("id") for entry in entries} == set(specs), "source audit ids drifted")
    for entry in entries:
        spec = specs[entry["id"]]
        _require(
            entry.get("local_filename") == f"{spec.study_id}-{spec.filename}"
            and entry.get("bytes") == spec.bytes
            and entry.get("sha256") == spec.sha256,
            f"{spec.source_id}: source identity drifted in audit",
        )
        for field in (
            "sample_count",
            "row_count",
            "positive_entrez_row_count",
            "unique_positive_entrez_count",
            "duplicate_positive_entrez_count",
            "blank_symbol_count",
            "nonfinite_value_count",
        ):
            _require(isinstance(entry.get(field), int) and entry[field] >= 0, f"{spec.source_id}: {field} invalid")
        _require(
            entry["sample_count"] >= protocol["machine_gates"]["minimum_samples_per_cohort"],
            f"{spec.source_id}: source is underpowered",
        )
    _require(
        payload.get("pairwise_associations_computed") is False
        and payload.get("candidate_ranking_computed") is False
        and payload.get("readiness_contribution") == 0
        and "not an association" in payload.get("claim_boundary", "")
        and "knowledge claim" in payload.get("claim_boundary", ""),
        "source audit overclaims evidence",
    )
    return payload


def _identity_map(path: Path) -> dict[int, str]:
    header, rows = iter_source_rows(path)
    del header
    found: dict[int, list[str]] = {}
    for row_number, row in enumerate(rows, start=2):
        symbol, entrez = _row_identity(row, f"{path.name}: row {row_number}")
        if entrez is not None:
            found.setdefault(entrez, []).append(symbol)
    return {
        entrez: symbols[0]
        for entrez, symbols in found.items()
        if len(symbols) == 1 and symbols[0]
    }


def _selection_digest(seed: str, entrez: int) -> str:
    return hashlib.sha256(f"{seed}\n{entrez}".encode("ascii")).hexdigest()


def build_candidate_universe(
    source_dir: Path,
    output: Path = UNIVERSE_MANIFEST_PATH,
) -> dict:
    protocol = audit_protocol()
    source_manifest = audit_source_manifest()
    del source_manifest
    paths = source_paths(source_dir, protocol)
    for spec in _source_specs(protocol):
        _verify_source_file(paths[spec.source_id], spec)
    identities = [_identity_map(paths[spec.source_id]) for spec in _source_specs(protocol)]
    common = sorted(
        entrez
        for entrez in identities[0].keys() & identities[1].keys()
        if identities[0][entrez] == identities[1][entrez]
    )
    rule = protocol["candidate_universe"]
    _require(len(common) >= rule["k"], "fewer common unique genes than frozen k")
    selected = sorted(
        common,
        key=lambda entrez: (_selection_digest(rule["seed"], entrez), entrez),
    )[: rule["k"]]
    selected.sort()
    genes = [{"entrez_gene_id": entrez, "symbol": identities[0][entrez]} for entrez in selected]
    payload = {
        "schema_version": 1,
        "id": "replicated-expression-candidate-universe-v1",
        "status": "score_free_candidate_universe_complete",
        "protocol": {
            "id": protocol["id"],
            "canonical_json_sha256": _score_free_protocol_sha256(protocol),
        },
        "source_manifest": {
            "path": "source-v1.json",
            "canonical_json_sha256": sha256_payload(audit_source_manifest()),
        },
        "selection": {
            "method": rule["selection"],
            "seed": rule["seed"],
            "common_identically_labelled_unique_gene_count": len(common),
            "selected_gene_count": len(genes),
            "candidate_pair_count": len(genes) * (len(genes) - 1) // 2,
            "selection_sha256": sha256_payload(genes),
        },
        "genes": genes,
        "expression_values_read": False,
        "pairwise_associations_computed": False,
        "readiness_contribution": 0,
        "claim_boundary": "Source-structure-only deterministic candidates; not measured associations, ranked gaps, findings, discoveries, or evidence of absent knowledge.",
    }
    _write_new_json(output, payload)
    audit_candidate_universe(output, source_dir=source_dir)
    return payload


def audit_candidate_universe(
    path: Path = UNIVERSE_MANIFEST_PATH,
    *,
    source_dir: Path | None = None,
) -> dict:
    protocol = audit_protocol()
    source_manifest = audit_source_manifest()
    payload = _load_json(path, "evidence-v1 candidate universe")
    _require(payload.get("schema_version") == 1, "candidate-universe schema drifted")
    _require(
        payload.get("id") == "replicated-expression-candidate-universe-v1"
        and payload.get("status") == "score_free_candidate_universe_complete",
        "candidate-universe identity drifted",
    )
    _require(
        payload.get("protocol")
        == {"id": protocol["id"], "canonical_json_sha256": _score_free_protocol_sha256(protocol)},
        "candidate universe does not pin the protocol",
    )
    _require(
        payload.get("source_manifest")
        == {"path": "source-v1.json", "canonical_json_sha256": sha256_payload(source_manifest)},
        "candidate universe does not pin the source audit",
    )
    genes = payload.get("genes")
    rule = protocol["candidate_universe"]
    _require(isinstance(genes, list) and len(genes) == rule["k"], "candidate gene count drifted")
    ids = [item.get("entrez_gene_id") for item in genes]
    labels = [item.get("symbol") for item in genes]
    _require(
        all(isinstance(value, int) and value > 0 for value in ids)
        and ids == sorted(ids)
        and len(set(ids)) == len(ids)
        and all(isinstance(value, str) and value for value in labels),
        "candidate gene identities drifted",
    )
    selection = payload.get("selection")
    _require(
        isinstance(selection, dict)
        and selection.get("method") == rule["selection"]
        and selection.get("seed") == rule["seed"]
        and selection.get("selected_gene_count") == rule["k"]
        and selection.get("candidate_pair_count") == rule["expected_pair_count"]
        and selection.get("selection_sha256") == sha256_payload(genes),
        "candidate selection evidence drifted",
    )
    _require(
        payload.get("expression_values_read") is False
        and payload.get("pairwise_associations_computed") is False
        and payload.get("readiness_contribution") == 0
        and "not measured associations" in payload.get("claim_boundary", "")
        and "absent knowledge" in payload.get("claim_boundary", ""),
        "candidate-universe claim boundary drifted",
    )
    if source_dir is not None:
        paths = source_paths(source_dir, protocol)
        identities = [_identity_map(paths[spec.source_id]) for spec in _source_specs(protocol)]
        common = sorted(
            entrez
            for entrez in identities[0].keys() & identities[1].keys()
            if identities[0][entrez] == identities[1][entrez]
        )
        selected = sorted(
            common,
            key=lambda entrez: (_selection_digest(rule["seed"], entrez), entrez),
        )[: rule["k"]]
        _require(sorted(selected) == ids, "candidate universe does not reproduce from sources")
        _require(
            selection.get("common_identically_labelled_unique_gene_count") == len(common),
            "common gene count drifted",
        )
    return payload


def _load_selected_matrix(path: Path, genes: Sequence[dict]) -> tuple[list[str], np.ndarray]:
    wanted = {item["entrez_gene_id"]: index for index, item in enumerate(genes)}
    header, rows = iter_source_rows(path)
    matrix = np.full((len(genes), len(header) - 2), np.nan, dtype=np.float64)
    seen: set[int] = set()
    for row_number, row in enumerate(rows, start=2):
        symbol, entrez = _row_identity(row, f"{path.name}: row {row_number}")
        if entrez not in wanted:
            continue
        index = wanted[entrez]
        _require(entrez not in seen, f"selected Entrez id {entrez} is duplicated in {path}")
        _require(symbol == genes[index]["symbol"], f"selected gene label drifted for {entrez}")
        _require(len(row) == len(header), f"selected row width drifted for {entrez}")
        values = parse_expression_values(row[2:], context=f"Entrez {entrez} in {path}")
        matrix[index] = values
        seen.add(entrez)
    _require(len(seen) == len(genes), f"selected genes missing from {path}")
    return header[2:], matrix


def parse_expression_values(values: Sequence[str], *, context: str) -> np.ndarray:
    """Parse one expression row, retaining declared missing cells for machine censoring."""
    parsed = np.empty(len(values), dtype=np.float64)
    for index, raw in enumerate(values):
        stripped = raw.strip()
        if stripped.upper() in {"", "NA", "NAN"}:
            parsed[index] = np.nan
            continue
        try:
            parsed[index] = float(stripped)
        except ValueError as exc:
            raise EvidenceV1Error(f"unrecognised expression value {raw!r} in {context}") from exc
    return parsed


def _average_ranks(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="mergesort")
    sorted_values = values[order]
    ranked = np.empty(values.size, dtype=np.float64)
    start = 0
    while start < values.size:
        end = start + 1
        while end < values.size and sorted_values[end] == sorted_values[start]:
            end += 1
        ranked[order[start:end]] = (start + end - 1) / 2.0
        start = end
    return ranked


def standardised_rank_rows(matrix: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    _require(matrix.ndim == 2 and matrix.shape[1] >= 4, "expression matrix is malformed")
    output = np.zeros_like(matrix, dtype=np.float64)
    usable = np.zeros(matrix.shape[0], dtype=bool)
    for index, row in enumerate(matrix):
        if not np.all(np.isfinite(row)):
            continue
        ranks = _average_ranks(row)
        ranks -= ranks.mean()
        norm = float(np.sqrt(np.dot(ranks, ranks)))
        if norm == 0.0:
            continue
        output[index] = ranks / norm
        usable[index] = True
    return output, usable


def _rho_p_values(rho: np.ndarray, sample_count: int) -> np.ndarray:
    clipped = np.clip(rho, -0.999999999999, 0.999999999999)
    z = np.arctanh(clipped) * math.sqrt(sample_count - 3)
    return np.fromiter(
        (math.erfc(abs(float(value)) / math.sqrt(2.0)) for value in z),
        dtype=np.float64,
        count=z.size,
    )


def benjamini_hochberg(p_values: np.ndarray) -> np.ndarray:
    _require(p_values.ndim == 1, "p-values must be one-dimensional")
    count = p_values.size
    order = np.argsort(p_values, kind="mergesort")
    ordered = p_values[order]
    adjusted = ordered * count / np.arange(1, count + 1, dtype=np.float64)
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
    adjusted = np.minimum(adjusted, 1.0)
    result = np.empty_like(adjusted)
    result[order] = adjusted
    return result


def _permuted_rows(rows: np.ndarray, seed: str) -> np.ndarray:
    numeric_seed = int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16], 16)
    rng = np.random.Generator(np.random.PCG64(numeric_seed))
    result = np.empty_like(rows)
    for index, row in enumerate(rows):
        result[index] = row[rng.permutation(row.size)]
    return result


def _pair_arrays(
    ranks: np.ndarray,
    usable: np.ndarray,
    left: np.ndarray,
    right: np.ndarray,
    decimals: int,
) -> tuple[np.ndarray, np.ndarray]:
    correlation = ranks @ ranks.T
    rho = np.round(correlation[left, right], decimals=decimals)
    pair_usable = usable[left] & usable[right]
    rho[~pair_usable] = np.nan
    return rho, pair_usable


def _gate_pairs(
    rho_a: np.ndarray,
    rho_b: np.ndarray,
    q_a: np.ndarray,
    q_b: np.ndarray,
    gates: Mapping,
) -> np.ndarray:
    finite = np.isfinite(rho_a) & np.isfinite(rho_b) & np.isfinite(q_a) & np.isfinite(q_b)
    return (
        finite
        & (np.signbit(rho_a) == np.signbit(rho_b))
        & (rho_a != 0)
        & (np.abs(rho_a) >= gates["minimum_absolute_rho_per_cohort"])
        & (np.abs(rho_b) >= gates["minimum_absolute_rho_per_cohort"])
        & (np.abs(rho_a - rho_b) <= gates["maximum_absolute_rho_difference"])
        & (q_a <= gates["maximum_q_per_cohort"])
        & (q_b <= gates["maximum_q_per_cohort"])
    )


def _q_values_for_pairs(rho: np.ndarray, usable: np.ndarray, sample_count: int) -> np.ndarray:
    q_values = np.full(rho.size, np.nan, dtype=np.float64)
    p_values = _rho_p_values(rho[usable], sample_count)
    q_values[usable] = benjamini_hochberg(p_values)
    return q_values


def _write_full_table(
    output: Path,
    genes: Sequence[dict],
    left: np.ndarray,
    right: np.ndarray,
    rho_a: np.ndarray,
    rho_b: np.ndarray,
    q_a: np.ndarray,
    q_b: np.ndarray,
    passed: np.ndarray,
) -> str:
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    except FileExistsError as exc:
        raise EvidenceV1Error(f"refusing to overwrite sealed evidence: {output}") from exc
    with os.fdopen(descriptor, "wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as compressed:
            header = "entrez_a\tsymbol_a\tentrez_b\tsymbol_b\trho_tcga\tq_tcga\trho_metabric\tq_metabric\tstatus\n"
            compressed.write(header.encode("utf-8"))
            for index in range(left.size):
                gene_a = genes[int(left[index])]
                gene_b = genes[int(right[index])]
                status = "replicated" if passed[index] else "not_replicated_or_censored"
                values = (
                    gene_a["entrez_gene_id"],
                    gene_a["symbol"],
                    gene_b["entrez_gene_id"],
                    gene_b["symbol"],
                    _format_float(rho_a[index]),
                    _format_float(q_a[index]),
                    _format_float(rho_b[index]),
                    _format_float(q_b[index]),
                    status,
                )
                compressed.write(("\t".join(map(str, values)) + "\n").encode("utf-8"))
    return _sha256_file(output)


def _format_float(value: float) -> str:
    if not math.isfinite(float(value)):
        return "NA"
    return format(float(value), ".10g")


def _published_observations(
    genes: Sequence[dict],
    left: np.ndarray,
    right: np.ndarray,
    rho_a: np.ndarray,
    rho_b: np.ndarray,
    q_a: np.ndarray,
    q_b: np.ndarray,
    passed: np.ndarray,
    maximum: int,
    sample_counts: tuple[int, int],
) -> list[dict]:
    indices = np.flatnonzero(passed)
    order = sorted(
        (int(index) for index in indices),
        key=lambda index: (
            -min(abs(float(rho_a[index])), abs(float(rho_b[index]))),
            genes[int(left[index])]["entrez_gene_id"],
            genes[int(right[index])]["entrez_gene_id"],
        ),
    )[:maximum]
    observations: list[dict] = []
    for rank, index in enumerate(order, start=1):
        gene_a = genes[int(left[index])]
        gene_b = genes[int(right[index])]
        direction = "positive" if rho_a[index] > 0 else "negative"
        observations.append(
            {
                "rank": rank,
                "status": "replicated_computational_observation",
                "entities": {"a": gene_a, "b": gene_b},
                "direction": direction,
                "tcga": {
                    "samples": sample_counts[0],
                    "spearman_rho": float(rho_a[index]),
                    "benjamini_hochberg_q": float(q_a[index]),
                },
                "metabric": {
                    "samples": sample_counts[1],
                    "spearman_rho": float(rho_b[index]),
                    "benjamini_hochberg_q": float(q_b[index]),
                },
                "generated_claim": (
                    f"In the pinned TCGA and METABRIC breast-tumour cohorts, expression ranks "
                    f"for {gene_a['symbol']} (Entrez {gene_a['entrez_gene_id']}) and "
                    f"{gene_b['symbol']} (Entrez {gene_b['entrez_gene_id']}) had a {direction} "
                    "association that passed the frozen evidence-v1 replication gates."
                ),
                "claim_scope": "cohort-level rank-expression association only",
            }
        )
    return observations


def evaluate(
    source_dir: Path,
    full_table: Path,
    manifest: Path = RESULT_MANIFEST_PATH,
) -> dict:
    protocol = audit_protocol()
    source_manifest = audit_source_manifest()
    universe = audit_candidate_universe(source_dir=source_dir)
    genes = universe["genes"]
    paths = source_paths(source_dir, protocol)
    specs = _source_specs(protocol)
    for spec in specs:
        _verify_source_file(paths[spec.source_id], spec)
    loaded = [_load_selected_matrix(paths[spec.source_id], genes) for spec in specs]
    _require(set(loaded[0][0]).isdisjoint(loaded[1][0]), "cohort sample ids overlap")
    sample_counts = (len(loaded[0][0]), len(loaded[1][0]))
    gates = protocol["machine_gates"]
    _require(
        min(sample_counts) >= gates["minimum_samples_per_cohort"],
        "sample-count power gate failed",
    )
    ranked = [standardised_rank_rows(item[1]) for item in loaded]
    _require(
        min(int(np.count_nonzero(item[1])) for item in ranked)
        >= gates["minimum_analyzable_genes_per_cohort"],
        "analyzable-gene power gate failed",
    )
    left, right = np.triu_indices(len(genes), k=1)
    decimals = protocol["measurement"]["quantize_rho_decimals_before_gates"]
    rho_a, usable_a = _pair_arrays(ranked[0][0], ranked[0][1], left, right, decimals)
    rho_b, usable_b = _pair_arrays(ranked[1][0], ranked[1][1], left, right, decimals)
    q_a = _q_values_for_pairs(rho_a, usable_a, sample_counts[0])
    q_b = _q_values_for_pairs(rho_b, usable_b, sample_counts[1])
    passed = _gate_pairs(rho_a, rho_b, q_a, q_b, gates)

    null_seed = protocol["negative_control"]["seed"]
    null_a = _permuted_rows(ranked[0][0], f"{null_seed}\n{specs[0].source_id}")
    null_b = _permuted_rows(ranked[1][0], f"{null_seed}\n{specs[1].source_id}")
    null_rho_a, null_usable_a = _pair_arrays(null_a, ranked[0][1], left, right, decimals)
    null_rho_b, null_usable_b = _pair_arrays(null_b, ranked[1][1], left, right, decimals)
    null_q_a = _q_values_for_pairs(null_rho_a, null_usable_a, sample_counts[0])
    null_q_b = _q_values_for_pairs(null_rho_b, null_usable_b, sample_counts[1])
    null_passed = _gate_pairs(null_rho_a, null_rho_b, null_q_a, null_q_b, gates)
    null_pass_count = int(np.count_nonzero(null_passed))
    calibration_passed = null_pass_count <= gates["maximum_null_pass_count"]
    if not calibration_passed:
        passed[:] = False

    full_hash = _write_full_table(
        full_table,
        genes,
        left,
        right,
        rho_a,
        rho_b,
        q_a,
        q_b,
        passed,
    )
    observations = _published_observations(
        genes,
        left,
        right,
        rho_a,
        rho_b,
        q_a,
        q_b,
        passed,
        protocol["publication"]["maximum_published_claims"],
        sample_counts,
    )
    state = "replicated_observations_published" if observations else "no_claims_or_abstained"
    payload = {
        "schema_version": 1,
        "id": "replicated-expression-evidence-v1-result",
        "state": state,
        "verdict": "measured" if calibration_passed else "abstained",
        "protocol": {
            "id": protocol["id"],
            "canonical_json_sha256": sha256_payload(protocol),
        },
        "source_manifest": {
            "path": "../benchmarks/evidence/source-v1.json",
            "canonical_json_sha256": sha256_payload(source_manifest),
        },
        "candidate_universe": {
            "path": "../benchmarks/evidence/candidate-universe-v1.json",
            "canonical_json_sha256": sha256_payload(universe),
        },
        "full_pair_table": {
            "filename": full_table.name,
            "sha256": full_hash,
            "row_count": int(left.size),
            "committed": False,
            "local_verification_required_for_byte_level_replay": True,
        },
        "cohorts": [
            {
                "id": spec.source_id,
                "study_id": spec.study_id,
                "platform": spec.platform,
                "sample_count": sample_counts[index],
                "analyzable_gene_count": int(np.count_nonzero(ranked[index][1])),
            }
            for index, spec in enumerate(specs)
        ],
        "gates": {
            "source_integrity": "passed",
            "sample_independence": "passed",
            "power": "passed",
            "null_calibration": "passed" if calibration_passed else "failed",
            "null_pass_count": null_pass_count,
            "maximum_null_pass_count": gates["maximum_null_pass_count"],
        },
        "counts": {
            "tested_pairs": int(left.size),
            "replicated_pairs": int(np.count_nonzero(passed)),
            "published_observations": len(observations),
        },
        "observations": observations,
        "human_dependencies": [],
        "manual_override_used": False,
        "llm_interpretation_used": False,
        "claim_boundary": protocol["claim_boundary"],
        "limitations": protocol["limitations"],
        "readiness_contribution": 1 if calibration_passed and observations else 0,
    }
    _write_new_json(manifest, payload)
    audit_result(manifest, full_table=full_table)
    return payload


def audit_result(
    path: Path = RESULT_MANIFEST_PATH,
    *,
    full_table: Path | None = None,
) -> ResultAudit:
    protocol = audit_protocol()
    source_manifest = audit_source_manifest()
    universe = audit_candidate_universe()
    payload = _load_json(path, "evidence-v1 result")
    _require(payload.get("schema_version") == 1, "result schema drifted")
    _require(payload.get("id") == "replicated-expression-evidence-v1-result", "result id drifted")
    _require(payload.get("verdict") in {"measured", "abstained"}, "result verdict drifted")
    _require(
        payload.get("protocol")
        == {"id": protocol["id"], "canonical_json_sha256": sha256_payload(protocol)},
        "result does not pin the protocol",
    )
    _require(
        payload.get("source_manifest")
        == {
            "path": "../benchmarks/evidence/source-v1.json",
            "canonical_json_sha256": sha256_payload(source_manifest),
        },
        "result does not pin the source audit",
    )
    _require(
        payload.get("candidate_universe")
        == {
            "path": "../benchmarks/evidence/candidate-universe-v1.json",
            "canonical_json_sha256": sha256_payload(universe),
        },
        "result does not pin the candidate universe",
    )
    table = payload.get("full_pair_table")
    _require(isinstance(table, dict), "full pair-table identity is missing")
    _require(
        table.get("row_count") == protocol["candidate_universe"]["expected_pair_count"]
        and isinstance(table.get("sha256"), str)
        and len(table["sha256"]) == 64
        and table.get("committed") is False
        and table.get("local_verification_required_for_byte_level_replay") is True,
        "full pair-table identity drifted",
    )
    if full_table is not None:
        _require(full_table.name == table["filename"], "full pair-table filename drifted")
        _require(_sha256_file(full_table) == table["sha256"], "full pair-table SHA-256 drifted")
        with gzip.open(full_table, "rt", encoding="utf-8", newline="") as handle:
            rows = sum(1 for _ in handle) - 1
        _require(rows == table["row_count"], "full pair-table row count drifted")

    cohorts = payload.get("cohorts")
    _require(isinstance(cohorts, list) and len(cohorts) == 2, "result cohorts drifted")
    _require(
        all(item.get("sample_count", 0) >= protocol["machine_gates"]["minimum_samples_per_cohort"] for item in cohorts)
        and all(item.get("analyzable_gene_count", 0) >= protocol["machine_gates"]["minimum_analyzable_genes_per_cohort"] for item in cohorts),
        "result power gate drifted",
    )
    gates = payload.get("gates")
    _require(isinstance(gates, dict), "result gates are missing")
    null_count = gates.get("null_pass_count")
    calibration = gates.get("null_calibration")
    _require(
        isinstance(null_count, int)
        and gates.get("maximum_null_pass_count") == protocol["machine_gates"]["maximum_null_pass_count"]
        and calibration == ("passed" if null_count <= gates["maximum_null_pass_count"] else "failed"),
        "null calibration evidence drifted",
    )
    counts = payload.get("counts")
    observations = payload.get("observations")
    _require(isinstance(counts, dict) and isinstance(observations, list), "result counts are malformed")
    _require(
        counts.get("tested_pairs") == table["row_count"]
        and counts.get("published_observations") == len(observations)
        and len(observations) <= protocol["publication"]["maximum_published_claims"],
        "published observation counts drifted",
    )
    for expected_rank, observation in enumerate(observations, start=1):
        _require(
            observation.get("rank") == expected_rank
            and observation.get("status") == protocol["publication"]["status_label"]
            and observation.get("claim_scope") == "cohort-level rank-expression association only"
            and "passed the frozen evidence-v1 replication gates" in observation.get("generated_claim", ""),
            f"observation {expected_rank}: identity or claim scope drifted",
        )
        for cohort in ("tcga", "metabric"):
            measured = observation.get(cohort)
            _require(isinstance(measured, dict), f"observation {expected_rank}: {cohort} missing")
            _require(
                abs(measured.get("spearman_rho", 0)) >= protocol["machine_gates"]["minimum_absolute_rho_per_cohort"]
                and measured.get("benjamini_hochberg_q", 1) <= protocol["machine_gates"]["maximum_q_per_cohort"],
                f"observation {expected_rank}: {cohort} gate failed",
            )
        _require(
            observation["direction"] == ("positive" if observation["tcga"]["spearman_rho"] > 0 else "negative")
            and np.signbit(observation["tcga"]["spearman_rho"])
            == np.signbit(observation["metabric"]["spearman_rho"])
            and abs(observation["tcga"]["spearman_rho"] - observation["metabric"]["spearman_rho"])
            <= protocol["machine_gates"]["maximum_absolute_rho_difference"],
            f"observation {expected_rank}: replication gate drifted",
        )
    expected_contribution = int(calibration == "passed" and bool(observations))
    _require(
        payload.get("human_dependencies") == []
        and payload.get("manual_override_used") is False
        and payload.get("llm_interpretation_used") is False
        and payload.get("claim_boundary") == protocol["claim_boundary"]
        and payload.get("limitations") == protocol["limitations"]
        and payload.get("readiness_contribution") == expected_contribution,
        "result autonomy or claim boundary drifted",
    )
    if calibration != "passed":
        _require(not observations and counts.get("replicated_pairs") == 0, "failed calibration published claims")
    return ResultAudit(
        state=str(payload.get("state")),
        claim_count=len(observations),
        tested_pair_count=int(counts["tested_pairs"]),
        null_pass_count=int(null_count),
        readiness_contribution=expected_contribution,
    )


def _print_result(audit: ResultAudit) -> None:
    print(f"evidence-v1 state: {audit.state}")
    print(f"tested pairs: {audit.tested_pair_count:,}")
    print(f"published bounded observations: {audit.claim_count:,}")
    print(f"permuted-null passing pairs: {audit.null_pass_count:,}")
    print("human dependencies: 0")
    print(f"readiness contribution: {audit.readiness_contribution}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("audit-protocol")
    build_source = subparsers.add_parser("build-source")
    build_source.add_argument("--source-dir", type=Path, required=True)
    build_source.add_argument("--output", type=Path, default=SOURCE_MANIFEST_PATH)
    build_universe = subparsers.add_parser("build-universe")
    build_universe.add_argument("--source-dir", type=Path, required=True)
    build_universe.add_argument("--output", type=Path, default=UNIVERSE_MANIFEST_PATH)
    run = subparsers.add_parser("evaluate")
    run.add_argument("--source-dir", type=Path, required=True)
    run.add_argument("--full-table", type=Path, required=True)
    run.add_argument("--manifest", type=Path, default=RESULT_MANIFEST_PATH)
    audit = subparsers.add_parser("audit-result")
    audit.add_argument("--full-table", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "audit-protocol":
            payload = audit_protocol()
            print("evidence-v1 protocol: frozen, source-pinned, and structurally valid")
            print(f"canonical JSON SHA-256: {sha256_payload(payload)}")
            print("human dependencies: 0")
            print("readiness contribution: 0")
        elif args.command == "build-source":
            payload = build_source_manifest(args.source_dir, args.output)
            for source in payload["sources"]:
                print(f"{source['id']}: {source['sample_count']:,} samples; {source['row_count']:,} rows")
            print("pairwise associations computed: no")
        elif args.command == "build-universe":
            payload = build_candidate_universe(args.source_dir, args.output)
            print(f"selected genes: {payload['selection']['selected_gene_count']:,}")
            print(f"candidate pairs: {payload['selection']['candidate_pair_count']:,}")
            print("expression values read: no")
        elif args.command == "evaluate":
            _print_result(evaluate(args.source_dir, args.full_table, args.manifest) and audit_result(args.manifest, full_table=args.full_table))
        else:
            _print_result(audit_result(full_table=args.full_table))
    except (EvidenceV1Error, OSError) as exc:
        raise SystemExit(str(exc)) from None


if __name__ == "__main__":
    main()
