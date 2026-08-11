"""Run the frozen, metric-blind BioASQ ``meshMajor`` semantics audit.

The official field name is ambiguous: BioASQ documentation describes all assigned MeSH labels,
while ``meshMajor`` sounds like PubMed's much narrower ``MajorTopicYN=Y`` subset.  The five-record
public sample is suggestive but too small to settle the question.  This module selects a
deterministic, publication-year-stratified sample from the registered v2013 payload and compares it
with maintained-current PubMed records in bounded EFetch batches.

The default sampling protocol was committed before the full payload was available. The measured
payload includes records outside its frozen 1950-2013 strata, so the default protocol intentionally
rejects it and must not be edited in place. This CLI remains available for
fixture validation and for a separately named successor passed through ``--protocol``. Any result
always contributes zero metric-v3 readiness because current PubMed is not period-appropriate
indexing.
"""

from __future__ import annotations

import argparse
import hashlib
import heapq
import json
from collections.abc import Callable
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from pipeline.benchmark.bioasq_snapshot import (
    MANIFEST_PATH as SNAPSHOT_MANIFEST_PATH,
    YEAR_NORMALISATION_RULE,
    _sha256_file,
    open_snapshot_text,
    iter_articles,
    validate_article,
)
from pipeline.benchmark.metric_blind import find_forbidden_fields
from pipeline.paths import REPO_ROOT
from pipeline.provenance import sha256_payload
from pipeline.pubmed_client import MAX_EFETCH_IDS, PubMedClient

PROTOCOL_PATH = REPO_ROOT / "benchmarks" / "v3" / "bioasq-semantics-protocol.json"
SUCCESSOR_PROTOCOL_PATH = (
    REPO_ROOT / "benchmarks" / "v3" / "bioasq-semantics-protocol-v2.json"
)
DEFAULT_SAMPLE_PATH = (
    REPO_ROOT / "data" / "medline-baseline" / "bioasq" / "semantics-sample.json"
)
DEFAULT_AUDIT_PATH = (
    REPO_ROOT / "benchmarks" / "v3" / "manifests" / "bioasq-2013-semantics.json"
)


class BioasqSemanticsError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BioasqSemanticsError(message)


def _is_sha256(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def _normalise(label: str) -> str:
    return " ".join(label.casefold().split())


def _file_reference(path: Path) -> dict[str, object]:
    sha256, size = _sha256_file(path)
    try:
        relative = path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        relative = str(path)
    return {"path": relative, "sha256": sha256, "bytes": size}


def audit_semantics_protocol(path: Path = PROTOCOL_PATH) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    _require(payload.get("schema_version") == 1, "unsupported BioASQ semantics protocol")
    status = payload.get("status")
    _require(
        status
        in {
            "frozen_before_full_payload",
            "frozen_after_source_audit_before_semantics_selection",
        },
        "unsupported semantics protocol freeze stage",
    )
    _require(payload.get("source_alternative_id") == "bioasq-2013-task-a", "wrong source")
    _require(payload.get("metric_blind") is True, "semantics sampling must be metric-blind")
    _require(
        payload.get("candidate_metric_seen") is False,
        "semantics protocol cannot be informed by a candidate metric",
    )
    if status == "frozen_before_full_payload":
        _require(
            payload.get("full_payload_seen_before_freeze") is False,
            "original semantics protocol must remain frozen before the full payload",
        )
    else:
        _require(
            payload.get("full_payload_seen_before_freeze") is True,
            "successor protocol must disclose full-payload access",
        )
        _require(
            payload.get("semantics_sample_seen_before_freeze") is False,
            "successor protocol must be frozen before semantics selection",
        )
    _require(not find_forbidden_fields(payload), "metric output fields are forbidden")

    evidence = payload.get("evidence_seen_before_freeze")
    _require(isinstance(evidence, dict), "protocol must disclose evidence seen before freeze")
    sample_reference = REPO_ROOT / str(evidence.get("public_sample_audit_path", ""))
    _require(sample_reference.is_file(), "referenced public sample audit is missing")
    measured_sha256, _ = _sha256_file(sample_reference)
    _require(
        measured_sha256 == evidence.get("public_sample_audit_sha256"),
        "public sample audit checksum drifted",
    )

    parent_protocol: dict | None = None
    snapshot_audit: dict | None = None
    if status == "frozen_after_source_audit_before_semantics_selection":
        parent_relative = Path(str(evidence.get("prior_protocol_path", "")))
        _require(
            not parent_relative.is_absolute() and ".." not in parent_relative.parts,
            "unsafe prior protocol path",
        )
        parent_path = REPO_ROOT / parent_relative
        _require(parent_path.is_file() and parent_path != path, "prior protocol is missing")
        parent_sha256, _ = _sha256_file(parent_path)
        _require(
            parent_sha256 == evidence.get("prior_protocol_sha256"),
            "prior semantics protocol checksum drifted",
        )
        parent_protocol = audit_semantics_protocol(parent_path)
        _require(
            parent_protocol["status"] == "frozen_before_full_payload",
            "successor parent must be the pre-payload protocol",
        )

        snapshot_relative = Path(str(evidence.get("full_snapshot_audit_path", "")))
        _require(
            not snapshot_relative.is_absolute() and ".." not in snapshot_relative.parts,
            "unsafe full snapshot audit path",
        )
        snapshot_path = REPO_ROOT / snapshot_relative
        _require(snapshot_path.is_file(), "full snapshot audit is missing")
        snapshot_sha256, _ = _sha256_file(snapshot_path)
        _require(
            snapshot_sha256 == evidence.get("full_snapshot_audit_sha256"),
            "full snapshot audit checksum drifted",
        )
        snapshot_audit = json.loads(snapshot_path.read_text(encoding="utf-8"))
        _require(
            snapshot_audit.get("status") == "measured_unmatched_input"
            and snapshot_audit.get("readiness_contribution") == 0,
            "successor must retain the source audit's bounded mismatch",
        )

    sampling = payload.get("sampling")
    _require(isinstance(sampling, dict), "protocol is missing sampling rules")
    _require(
        sampling.get("algorithm") == "sha256_bottom_k_per_publication_year_stratum",
        "unsupported semantics sampling algorithm",
    )
    _require(isinstance(sampling.get("hash_namespace"), str), "missing hash namespace")
    strata = sampling.get("strata")
    _require(isinstance(strata, list) and strata, "sampling strata are required")
    seen_ids: set[str] = set()
    ranges: list[tuple[int, int]] = []
    total_sample_size = 0
    for index, stratum in enumerate(strata):
        _require(isinstance(stratum, dict), f"stratum {index}: expected an object")
        stratum_id = stratum.get("id")
        _require(
            isinstance(stratum_id, str) and stratum_id and stratum_id not in seen_ids,
            f"stratum {index}: invalid or duplicate id",
        )
        seen_ids.add(stratum_id)
        year_min = stratum.get("year_min")
        year_max = stratum.get("year_max")
        sample_size = stratum.get("sample_size")
        _require(
            isinstance(year_min, int)
            and isinstance(year_max, int)
            and 1800 <= year_min <= year_max <= 2100,
            f"{stratum_id}: invalid year range",
        )
        _require(
            isinstance(sample_size, int) and sample_size > 0,
            f"{stratum_id}: invalid sample size",
        )
        _require(bool(stratum.get("rationale")), f"{stratum_id}: missing rationale")
        ranges.append((year_min, year_max))
        total_sample_size += sample_size
    for left_index, (left_min, left_max) in enumerate(ranges):
        for right_min, right_max in ranges[left_index + 1 :]:
            _require(
                left_max < right_min or right_max < left_min,
                "semantics sampling year strata overlap",
            )
    _require(
        sampling.get("total_sample_size") == total_sample_size,
        "declared semantics sample size does not equal stratum sizes",
    )

    comparison = payload.get("comparison")
    _require(isinstance(comparison, dict), "protocol is missing comparison rules")
    _require(
        comparison.get("basis") == "maintained_current_pubmed",
        "comparison must remain explicitly maintained-current",
    )
    batch_size = comparison.get("batch_size")
    _require(
        isinstance(batch_size, int) and 0 < batch_size <= MAX_EFETCH_IDS,
        "comparison batch size exceeds the PubMed EFetch limit",
    )
    _require(
        comparison.get("required_record_return_fraction") == 1.0,
        "the predeclared sample requires every PubMed record",
    )

    decision = payload.get("decision_rule")
    _require(isinstance(decision, dict), "protocol is missing a decision rule")
    thresholds = decision.get("consistent_with_all_assigned_descriptors_if")
    _require(isinstance(thresholds, dict), "protocol is missing semantics thresholds")
    minimum_all = thresholds.get("minimum_all_descriptor_assignment_match_fraction")
    maximum_major = thresholds.get("maximum_major_topic_assignment_match_fraction")
    _require(
        isinstance(minimum_all, (int, float))
        and isinstance(maximum_major, (int, float))
        and 0 <= maximum_major < minimum_all <= 1,
        "semantics thresholds must separate all-descriptor and major-topic matches",
    )
    _require(decision.get("readiness_contribution") == 0, "semantics cannot add readiness")

    if status == "frozen_after_source_audit_before_semantics_selection":
        _require(
            parent_protocol is not None and snapshot_audit is not None,
            "missing parent audit",
        )
        parent_sampling = parent_protocol["sampling"]
        inherited_sampling_fields = (
            "algorithm",
            "hash_namespace",
            "hash_input",
            "record_key",
            "tie_breaker",
        )
        _require(
            all(
                sampling.get(field) == parent_sampling.get(field)
                for field in inherited_sampling_fields
            ),
            "successor changed an inherited sampling identity",
        )
        _require(
            sampling.get("publication_year_normalisation") == YEAR_NORMALISATION_RULE,
            "successor publication-year normalisation drifted",
        )
        _require(
            sampling.get("outside_strata_policy") == "reject_entire_selection",
            "successor must reject any still-uncovered record",
        )
        parent_strata = {item["id"]: item for item in parent_sampling["strata"]}
        successor_strata = {item["id"]: item for item in strata}
        _require(
            set(successor_strata) == set(parent_strata) | {"y1946_1949"},
            "successor must add only the measured pre-1950 stratum",
        )
        _require(
            all(successor_strata[key] == value for key, value in parent_strata.items()),
            "successor changed a prior sampling stratum",
        )
        _require(
            successor_strata["y1946_1949"]
            == {
                "id": "y1946_1949",
                "year_min": 1946,
                "year_max": 1949,
                "sample_size": 32,
                "rationale": (
                    "Covers the 280 measured records that contradict the reported post-1949 "
                    "scope; 32 matches the allocation for each other broad historical stratum "
                    "without treating this small anomalous group as population-representative."
                ),
            },
            "successor pre-1950 stratum drifted",
        )
        _require(
            sampling["total_sample_size"] == parent_sampling["total_sample_size"] + 32,
            "successor total must add exactly 32 records",
        )
        _require(comparison == parent_protocol["comparison"], "comparison rules changed")
        _require(decision == parent_protocol["decision_rule"], "decision thresholds changed")

        measured = snapshot_audit["measured"]
        snapshot_comparison = snapshot_audit["declared_comparison"]
        source_population = payload.get("source_population")
        _require(isinstance(source_population, dict), "missing measured source population")
        expected_pre_1950 = {
            year: measured["publication_year_counts"][year]
            for year in ("1946", "1947", "1948", "1949")
        }
        _require(
            source_population
            == {
                "snapshot_input_sha256": snapshot_audit["input"]["sha256"],
                "article_count": measured["article_count"],
                "parseable_publication_year_min": measured["publication_year_min"],
                "parseable_publication_year_max": measured["publication_year_max"],
                "noncanonical_year_count": measured["noncanonical_year_count"],
                "unparseable_year_count": measured["unparseable_year_count"],
                "records_before_1950": snapshot_comparison[
                    "articles_before_declared_publication_scope"
                ],
                "records_before_1950_by_year": expected_pre_1950,
            },
            "successor source population does not match the pinned audit",
        )
        revision = payload.get("revision_from_prior_protocol")
        _require(
            isinstance(revision, dict)
            and bool(revision.get("reason"))
            and isinstance(revision.get("changed"), list)
            and revision["changed"]
            and isinstance(revision.get("unchanged"), list)
            and revision["unchanged"],
            "successor must disclose its revision scope",
        )

    limitations = payload.get("limitations")
    _require(
        isinstance(limitations, list)
        and limitations
        and all(isinstance(item, str) and item for item in limitations),
        "protocol needs explicit limitations",
    )
    return payload


def _stratum_for_year(protocol: dict, year: int) -> dict | None:
    matches = [
        item
        for item in protocol["sampling"]["strata"]
        if item["year_min"] <= year <= item["year_max"]
    ]
    _require(len(matches) <= 1, f"publication year {year} matches overlapping strata")
    return matches[0] if matches else None


def selection_hash(namespace: str, pmid: str) -> str:
    value = f"{namespace}\0{pmid}".encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def _selected_record(
    pmid: str,
    year: int,
    stratum_id: str,
    digest: str,
    mesh_labels: tuple[str, ...],
) -> dict:
    return {
        "pmid": pmid,
        "publication_year": year,
        "stratum": stratum_id,
        "selection_hash": digest,
        "mesh_labels": sorted(mesh_labels, key=lambda label: (_normalise(label), label)),
    }


def _same_selected_observation(
    selected: dict,
    *,
    year: int | None,
    stratum_id: str | None,
    mesh_labels: tuple[str, ...],
) -> bool:
    return (
        selected["publication_year"] == year
        and selected["stratum"] == stratum_id
        and selected["mesh_labels"]
        == sorted(mesh_labels, key=lambda label: (_normalise(label), label))
    )


def select_semantics_sample(
    snapshot_path: Path,
    *,
    protocol_path: Path = PROTOCOL_PATH,
) -> dict:
    protocol = audit_semantics_protocol(protocol_path)
    namespace = protocol["sampling"]["hash_namespace"]
    strata = protocol["sampling"]["strata"]
    heaps: dict[str, list[tuple[int, int, int, dict]]] = {item["id"]: [] for item in strata}
    retained_by_stratum: dict[str, dict[str, dict]] = {
        item["id"]: {} for item in strata
    }
    eligible_counts = {item["id"]: 0 for item in strata}
    total_records = 0
    outside_strata = 0

    with open_snapshot_text(snapshot_path) as (stream, container):
        for article in iter_articles(stream):
            total_records += 1
            pmid, year, mesh_labels, _canonical_year, _raw_year = validate_article(
                article, total_records
            )
            if year is None:
                outside_strata += 1
                continue
            stratum = _stratum_for_year(protocol, year)
            if stratum is None:
                outside_strata += 1
                continue
            stratum_id = stratum["id"]
            eligible_counts[stratum_id] += 1
            digest = selection_hash(namespace, pmid)
            rank = int(digest, 16)
            record = _selected_record(pmid, year, stratum_id, digest, mesh_labels)
            retained = retained_by_stratum[stratum_id]
            if pmid in retained:
                _require(
                    _same_selected_observation(
                        retained[pmid],
                        year=year,
                        stratum_id=stratum_id,
                        mesh_labels=mesh_labels,
                    ),
                    f"PMID {pmid}: conflicting duplicate source records",
                )
                continue
            # A min-heap over negative ranks keeps the largest retained rank at index zero.  A
            # smaller hash (then smaller numeric PMID) deterministically replaces that boundary.
            # The retained PMID map makes the protocol's record_key explicit: repeated source
            # rows cannot consume multiple bottom-k slots.
            heap_entry = (-rank, -int(pmid), total_records, record)
            heap = heaps[stratum_id]
            if len(heap) < stratum["sample_size"]:
                heapq.heappush(heap, heap_entry)
                retained[pmid] = record
            elif heap_entry > heap[0]:
                removed = heapq.heapreplace(heap, heap_entry)
                del retained[removed[3]["pmid"]]
                retained[pmid] = record

    _require(outside_strata == 0, "snapshot contains publication years outside frozen strata")
    records: list[dict] = []
    selected_counts: dict[str, int] = {}
    for stratum in strata:
        stratum_id = stratum["id"]
        selected = [entry[3] for entry in heaps[stratum_id]]
        selected.sort(key=lambda item: (item["selection_hash"], int(item["pmid"])))
        _require(
            len(selected) == stratum["sample_size"],
            f"{stratum_id}: too few eligible records for the frozen sample",
        )
        records.extend(selected)
        selected_counts[stratum_id] = len(selected)
    pmids = [record["pmid"] for record in records]
    _require(len(pmids) == len(set(pmids)), "selected sample contains duplicate PMIDs")

    # Re-read the source before emitting a sample. This bounds duplicate-state memory to the
    # selected PMIDs while proving that every occurrence of a retained key has the same year,
    # stratum, and MeSH assignments. A conflicting source row is never silently collapsed.
    selected_by_pmid = {record["pmid"]: record for record in records}
    selected_occurrences = {pmid: 0 for pmid in pmids}
    verification_records_scanned = 0
    with open_snapshot_text(snapshot_path) as (stream, verification_container):
        for article in iter_articles(stream):
            verification_records_scanned += 1
            pmid, year, mesh_labels, _canonical_year, _raw_year = validate_article(
                article, verification_records_scanned
            )
            selected = selected_by_pmid.get(pmid)
            if selected is None:
                continue
            stratum = _stratum_for_year(protocol, year) if year is not None else None
            stratum_id = stratum["id"] if stratum is not None else None
            _require(
                _same_selected_observation(
                    selected,
                    year=year,
                    stratum_id=stratum_id,
                    mesh_labels=mesh_labels,
                ),
                f"PMID {pmid}: conflicting duplicate source records",
            )
            selected_occurrences[pmid] += 1
    _require(verification_container == container, "snapshot container changed during replay")
    _require(
        verification_records_scanned == total_records,
        "snapshot record count changed during replay",
    )
    _require(
        all(count > 0 for count in selected_occurrences.values()),
        "selected PMID disappeared during source replay",
    )
    duplicate_selected_pmids = sorted(
        (pmid for pmid, count in selected_occurrences.items() if count > 1),
        key=int,
    )
    duplicate_selected_source_records = sum(
        count - 1 for count in selected_occurrences.values()
    )

    protocol_reference = _file_reference(protocol_path)
    input_reference = _file_reference(snapshot_path)
    return {
        "schema_version": 1,
        "status": "predeclared_bioasq_semantics_sample",
        "readiness_contribution": 0,
        "source_alternative_id": "bioasq-2013-task-a",
        "protocol": protocol_reference,
        "input": {**input_reference, "local_name": snapshot_path.name, "container": container},
        "selection": {
            "algorithm": protocol["sampling"]["algorithm"],
            "hash_namespace": namespace,
            "records_scanned": total_records,
            "verification_records_scanned": verification_records_scanned,
            "records_outside_strata": outside_strata,
            "eligible_counts": eligible_counts,
            "selected_counts": selected_counts,
            "selected_total": len(records),
            "duplicate_selected_source_records": duplicate_selected_source_records,
            "selected_pmids_with_duplicate_source_records": duplicate_selected_pmids,
        },
        "records": records,
        "limitations": list(protocol["limitations"]),
    }


def _fraction(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 8) if denominator else 0.0


def _comparison_counts(sample_record: dict, pubmed_record: dict) -> dict:
    all_labels = {
        _normalise(item["descriptor_label"])
        for item in pubmed_record.get("mesh_headings", [])
        if item.get("descriptor_label")
    }
    major_labels = {
        _normalise(item["descriptor_label"])
        for item in pubmed_record.get("mesh_headings", [])
        if item.get("descriptor_label") and item.get("major_topic") is True
    }
    sample_labels = sample_record["mesh_labels"]
    matched_all = [label for label in sample_labels if _normalise(label) in all_labels]
    matched_major = [label for label in sample_labels if _normalise(label) in major_labels]
    sample_only = [label for label in sample_labels if _normalise(label) not in all_labels]
    return {
        "pmid": sample_record["pmid"],
        "publication_year": sample_record["publication_year"],
        "stratum": sample_record["stratum"],
        "bioasq_assignments": len(sample_labels),
        "matched_current_all_descriptor_assignments": len(matched_all),
        "matched_current_major_topic_assignments": len(matched_major),
        "sample_only_labels": sample_only,
    }


def _summarise_records(records: list[dict]) -> dict:
    assignments = sum(item["bioasq_assignments"] for item in records)
    matched_all = sum(item["matched_current_all_descriptor_assignments"] for item in records)
    matched_major = sum(item["matched_current_major_topic_assignments"] for item in records)
    return {
        "records": len(records),
        "bioasq_assignments": assignments,
        "matched_current_all_descriptor_assignments": matched_all,
        "matched_current_major_topic_assignments": matched_major,
        "all_descriptor_assignment_match_fraction": _fraction(matched_all, assignments),
        "major_topic_assignment_match_fraction": _fraction(matched_major, assignments),
    }


def compare_semantics_sample(
    sample: dict,
    protocol: dict,
    fetch_batch: Callable[[list[str]], dict],
) -> dict:
    _require(sample.get("schema_version") == 1, "unsupported semantics sample schema")
    _require(
        sample.get("status") == "predeclared_bioasq_semantics_sample",
        "input is not a predeclared semantics sample",
    )
    _require(sample.get("readiness_contribution") == 0, "sample cannot add readiness")
    records = sample.get("records")
    _require(isinstance(records, list) and records, "semantics sample contains no records")
    pmids = [str(item.get("pmid", "")) for item in records]
    _require(all(pmid.isdigit() for pmid in pmids), "semantics sample contains invalid PMIDs")
    _require(len(pmids) == len(set(pmids)), "semantics sample contains duplicate PMIDs")
    _require(
        len(records) == protocol["sampling"]["total_sample_size"],
        "semantics sample size differs from the frozen protocol",
    )
    protocol_counts = {
        item["id"]: item["sample_size"] for item in protocol["sampling"]["strata"]
    }
    actual_counts = {stratum_id: 0 for stratum_id in protocol_counts}
    namespace = protocol["sampling"]["hash_namespace"]
    for record in records:
        stratum = _stratum_for_year(protocol, int(record["publication_year"]))
        _require(stratum is not None, f"PMID {record['pmid']}: year is outside frozen strata")
        _require(record.get("stratum") == stratum["id"], f"PMID {record['pmid']}: wrong stratum")
        _require(
            record.get("selection_hash") == selection_hash(namespace, record["pmid"]),
            f"PMID {record['pmid']}: selection hash drifted",
        )
        _require(
            isinstance(record.get("mesh_labels"), list)
            and all(isinstance(label, str) and label for label in record["mesh_labels"]),
            f"PMID {record['pmid']}: invalid BioASQ labels",
        )
        actual_counts[stratum["id"]] += 1
    _require(actual_counts == protocol_counts, "semantics sample stratum counts drifted")

    batch_size = protocol["comparison"]["batch_size"]
    batches: list[dict] = []
    pubmed_by_pmid: dict[str, dict] = {}
    for start in range(0, len(pmids), batch_size):
        batch_pmids = sorted(pmids[start : start + batch_size], key=int)
        payload = fetch_batch(batch_pmids)
        _require(
            payload.get("mesh_basis") == "maintained_current_pubmed",
            "PubMed comparison is not labelled maintained-current",
        )
        fetched = payload.get("records")
        _require(isinstance(fetched, list), "PubMed comparison has no records")
        for record in fetched:
            pmid = str(record.get("pmid", ""))
            _require(pmid in batch_pmids, f"PubMed returned unexpected PMID {pmid}")
            _require(pmid not in pubmed_by_pmid, f"PubMed returned duplicate PMID {pmid}")
            pubmed_by_pmid[pmid] = record
        response_sha256 = payload.get("response_sha256")
        response_bytes = payload.get("response_bytes")
        _require(
            isinstance(response_sha256, str) and len(response_sha256) == 64,
            "PubMed batch lacks an exact response checksum",
        )
        _require(
            isinstance(response_bytes, int) and response_bytes > 0,
            "PubMed batch lacks an exact response byte count",
        )
        source_url = payload.get("source_url")
        _require(
            isinstance(source_url, str)
            and source_url.startswith("https://eutils.ncbi.nlm.nih.gov/"),
            "PubMed batch lacks a public EFetch query URL",
        )
        batches.append(
            {
                "source_url": source_url,
                "requested_pmids": len(batch_pmids),
                "records_returned": len(fetched),
                "response_sha256": response_sha256,
                "response_bytes": response_bytes,
                "parsed_records_sha256": sha256_payload(fetched),
            }
        )

    missing_pmids = sorted(set(pmids) - set(pubmed_by_pmid), key=int)
    returned_fraction = _fraction(len(pubmed_by_pmid), len(pmids))
    comparisons = [
        _comparison_counts(record, pubmed_by_pmid[record["pmid"]])
        for record in records
        if record["pmid"] in pubmed_by_pmid
    ]
    overall = _summarise_records(comparisons)
    by_stratum = {
        stratum["id"]: _summarise_records(
            [item for item in comparisons if item["stratum"] == stratum["id"]]
        )
        for stratum in protocol["sampling"]["strata"]
    }
    thresholds = protocol["decision_rule"]["consistent_with_all_assigned_descriptors_if"]
    every_stratum_separates = all(
        item["all_descriptor_assignment_match_fraction"]
        > item["major_topic_assignment_match_fraction"]
        for item in by_stratum.values()
    )
    passes = (
        returned_fraction >= protocol["comparison"]["required_record_return_fraction"]
        and overall["all_descriptor_assignment_match_fraction"]
        >= thresholds["minimum_all_descriptor_assignment_match_fraction"]
        and overall["major_topic_assignment_match_fraction"]
        <= thresholds["maximum_major_topic_assignment_match_fraction"]
        and (
            every_stratum_separates
            or not thresholds["all_descriptor_match_must_exceed_major_topic_match_in_every_stratum"]
        )
    )
    classification = protocol["decision_rule"][
        "passing_label" if passes else "nonpassing_label"
    ]
    interpretation = (
        "The predeclared balanced sample is consistent with meshMajor containing all assigned "
        "descriptors rather than only MajorTopicYN=Y headings."
        if passes
        else "The predeclared balanced sample does not resolve whether meshMajor contains all "
        "assigned descriptors rather than only MajorTopicYN=Y headings."
    )
    return {
        "schema_version": 1,
        "status": "bounded_corpus_semantics_audit",
        "readiness_contribution": 0,
        "source_alternative_id": "bioasq-2013-task-a",
        "classification": classification,
        "sample": {
            "selected_records": len(records),
            "source_snapshot_sha256": sample["input"]["sha256"],
            "source_snapshot_bytes": sample["input"]["bytes"],
            "sampling_protocol_sha256": sample["protocol"]["sha256"],
        },
        "maintained_current_pubmed_comparison": {
            "basis": "maintained_current_pubmed",
            "records_requested": len(pmids),
            "records_returned": len(pubmed_by_pmid),
            "record_return_fraction": returned_fraction,
            "missing_pmids": missing_pmids,
            "batches": batches,
            "overall": overall,
            "by_stratum": by_stratum,
            "records": comparisons,
        },
        "decision_checks": {
            "required_record_return_fraction": protocol["comparison"][
                "required_record_return_fraction"
            ],
            "minimum_all_descriptor_assignment_match_fraction": thresholds[
                "minimum_all_descriptor_assignment_match_fraction"
            ],
            "maximum_major_topic_assignment_match_fraction": thresholds[
                "maximum_major_topic_assignment_match_fraction"
            ],
            "all_descriptor_match_exceeds_major_topic_match_in_every_stratum": (
                every_stratum_separates
            ),
            "passed": passes,
        },
        "interpretation": interpretation,
        "limitations": list(protocol["limitations"]),
    }


def audit_semantics_manifest(
    path: Path = DEFAULT_AUDIT_PATH,
    *,
    protocol_path: Path = SUCCESSOR_PROTOCOL_PATH,
    snapshot_manifest_path: Path = SNAPSHOT_MANIFEST_PATH,
) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    protocol = audit_semantics_protocol(protocol_path)
    snapshot = json.loads(snapshot_manifest_path.read_text(encoding="utf-8"))
    _require(
        set(payload)
        == {
            "schema_version",
            "status",
            "readiness_contribution",
            "source_alternative_id",
            "classification",
            "sample",
            "maintained_current_pubmed_comparison",
            "decision_checks",
            "interpretation",
            "limitations",
        },
        "semantics manifest fields drifted",
    )
    _require(payload.get("schema_version") == 1, "unsupported semantics manifest schema")
    _require(
        payload.get("status") == "bounded_corpus_semantics_audit",
        "semantics result must remain explicitly bounded",
    )
    _require(payload.get("readiness_contribution") == 0, "semantics result cannot add readiness")
    _require(payload.get("source_alternative_id") == "bioasq-2013-task-a", "wrong source")
    _require(
        snapshot.get("status") == "measured_unmatched_input"
        and snapshot.get("readiness_contribution") == 0,
        "semantics result must retain the snapshot scope mismatch",
    )

    sample = payload.get("sample")
    _require(isinstance(sample, dict), "semantics manifest is missing its sample identity")
    _require(
        set(sample)
        == {
            "selected_records",
            "source_snapshot_sha256",
            "source_snapshot_bytes",
            "sampling_protocol_sha256",
            "selection_file",
        },
        "semantics sample identity fields drifted",
    )
    protocol_sha256, _protocol_bytes = _sha256_file(protocol_path)
    snapshot_input = snapshot.get("input")
    _require(isinstance(snapshot_input, dict), "snapshot audit is missing its input identity")
    _require(
        sample["selected_records"] == protocol["sampling"]["total_sample_size"],
        "semantics sample size differs from the frozen protocol",
    )
    _require(
        sample["sampling_protocol_sha256"] == protocol_sha256,
        "semantics manifest references a different sampling protocol",
    )
    _require(
        sample["source_snapshot_sha256"] == snapshot_input.get("sha256")
        and sample["source_snapshot_bytes"] == snapshot_input.get("bytes"),
        "semantics manifest references a different source snapshot",
    )
    selection_file = sample.get("selection_file")
    _require(
        isinstance(selection_file, dict)
        and set(selection_file) == {"path", "sha256", "bytes"},
        "semantics selection identity is malformed",
    )
    selection_path = str(selection_file.get("path", "")).replace("\\", "/")
    _require(
        selection_path == "data/medline-baseline/bioasq/semantics-sample.json",
        "semantics selection path drifted",
    )
    _require(_is_sha256(selection_file.get("sha256")), "invalid semantics selection checksum")
    _require(
        type(selection_file.get("bytes")) is int and selection_file["bytes"] > 0,
        "invalid semantics selection byte count",
    )

    comparison = payload.get("maintained_current_pubmed_comparison")
    _require(isinstance(comparison, dict), "semantics manifest is missing its comparison")
    _require(
        set(comparison)
        == {
            "basis",
            "records_requested",
            "records_returned",
            "record_return_fraction",
            "missing_pmids",
            "batches",
            "overall",
            "by_stratum",
            "records",
        },
        "semantics comparison fields drifted",
    )
    _require(
        comparison.get("basis") == "maintained_current_pubmed",
        "semantics comparison is not labelled maintained-current",
    )
    requested = comparison.get("records_requested")
    returned = comparison.get("records_returned")
    _require(
        type(requested) is int
        and requested == protocol["sampling"]["total_sample_size"],
        "semantics requested-record count drifted",
    )
    _require(
        type(returned) is int and 0 <= returned <= requested,
        "invalid semantics returned-record count",
    )
    _require(
        comparison.get("record_return_fraction") == _fraction(returned, requested),
        "semantics record-return fraction does not reconcile",
    )

    batches = comparison.get("batches")
    _require(isinstance(batches, list) and batches, "semantics manifest has no PubMed batches")
    requested_pmids: list[str] = []
    returned_from_batches = 0
    remaining = requested
    for index, batch in enumerate(batches):
        context = f"PubMed batch {index + 1}"
        _require(
            isinstance(batch, dict)
            and set(batch)
            == {
                "source_url",
                "requested_pmids",
                "records_returned",
                "response_sha256",
                "response_bytes",
                "parsed_records_sha256",
            },
            f"{context} fields drifted",
        )
        source_url = batch.get("source_url")
        _require(isinstance(source_url, str), f"{context} is missing its source URL")
        parsed = urlsplit(source_url)
        query = parse_qs(parsed.query, keep_blank_values=True)
        _require(
            parsed.scheme == "https"
            and parsed.hostname == "eutils.ncbi.nlm.nih.gov"
            and parsed.path == "/entrez/eutils/efetch.fcgi"
            and parsed.username is None
            and parsed.password is None
            and parsed.port is None
            and not parsed.fragment,
            f"{context} source is not NCBI EFetch",
        )
        _require(
            set(query) == {"db", "id", "retmode", "tool"}
            and query.get("db") == ["pubmed"]
            and len(query.get("id", [])) == 1
            and query.get("retmode") == ["xml"]
            and query.get("tool") == ["lacuna"],
            f"{context} query contains unpinned or identifying parameters",
        )
        batch_pmids = query["id"][0].split(",")
        _require(
            batch_pmids
            and all(pmid.isdigit() for pmid in batch_pmids)
            and batch_pmids == sorted(batch_pmids, key=int)
            and len(batch_pmids) == len(set(batch_pmids)),
            f"{context} has invalid PMID keys",
        )
        expected_batch_size = min(protocol["comparison"]["batch_size"], remaining)
        _require(
            batch.get("requested_pmids") == len(batch_pmids) == expected_batch_size,
            f"{context} requested-record count drifted",
        )
        batch_returned = batch.get("records_returned")
        _require(
            type(batch_returned) is int and 0 <= batch_returned <= len(batch_pmids),
            f"{context} returned-record count is invalid",
        )
        _require(
            _is_sha256(batch.get("response_sha256")),
            f"{context} response checksum is invalid",
        )
        _require(
            type(batch.get("response_bytes")) is int and batch["response_bytes"] > 0,
            f"{context} response byte count is invalid",
        )
        _require(
            _is_sha256(batch.get("parsed_records_sha256")),
            f"{context} parsed-record checksum is invalid",
        )
        requested_pmids.extend(batch_pmids)
        returned_from_batches += batch_returned
        remaining -= len(batch_pmids)
    _require(remaining == 0, "PubMed batches do not cover the requested sample")
    _require(
        len(requested_pmids) == len(set(requested_pmids)),
        "PubMed batches contain duplicate PMID requests",
    )
    _require(
        returned_from_batches == returned,
        "PubMed batch return counts do not reconcile",
    )

    records = comparison.get("records")
    _require(isinstance(records, list), "semantics comparison records are missing")
    _require(len(records) == returned, "semantics comparison record count does not reconcile")
    compared_pmids: list[str] = []
    for record in records:
        _require(
            isinstance(record, dict)
            and set(record)
            == {
                "pmid",
                "publication_year",
                "stratum",
                "bioasq_assignments",
                "matched_current_all_descriptor_assignments",
                "matched_current_major_topic_assignments",
                "sample_only_labels",
            },
            "semantics comparison record fields drifted",
        )
        pmid = str(record.get("pmid", ""))
        year = record.get("publication_year")
        _require(pmid.isdigit(), "semantics comparison contains an invalid PMID")
        _require(type(year) is int, f"PMID {pmid}: invalid publication year")
        stratum = _stratum_for_year(protocol, year)
        _require(
            stratum is not None and record.get("stratum") == stratum["id"],
            f"PMID {pmid}: wrong comparison stratum",
        )
        assignments = record.get("bioasq_assignments")
        matched_all = record.get("matched_current_all_descriptor_assignments")
        matched_major = record.get("matched_current_major_topic_assignments")
        _require(
            type(assignments) is int
            and type(matched_all) is int
            and type(matched_major) is int
            and 0 <= matched_major <= matched_all <= assignments
            and assignments > 0,
            f"PMID {pmid}: assignment counts do not reconcile",
        )
        sample_only = record.get("sample_only_labels")
        _require(
            isinstance(sample_only, list)
            and all(isinstance(label, str) and label for label in sample_only)
            and len(sample_only) == assignments - matched_all,
            f"PMID {pmid}: unmatched labels do not reconcile",
        )
        compared_pmids.append(pmid)
    _require(
        len(compared_pmids) == len(set(compared_pmids)),
        "semantics comparison contains duplicate PMIDs",
    )
    requested_set = set(requested_pmids)
    compared_set = set(compared_pmids)
    _require(compared_set <= requested_set, "PubMed returned an unrequested PMID")
    missing_pmids = comparison.get("missing_pmids")
    _require(
        isinstance(missing_pmids, list)
        and all(isinstance(pmid, str) and pmid.isdigit() for pmid in missing_pmids)
        and missing_pmids == sorted(missing_pmids, key=int)
        and len(missing_pmids) == len(set(missing_pmids)),
        "semantics missing-PMID list is invalid",
    )
    _require(
        set(missing_pmids) == requested_set - compared_set,
        "semantics missing-PMID list does not reconcile",
    )

    overall = comparison.get("overall")
    by_stratum = comparison.get("by_stratum")
    _require(overall == _summarise_records(records), "semantics overall counts drifted")
    expected_by_stratum = {
        stratum["id"]: _summarise_records(
            [record for record in records if record["stratum"] == stratum["id"]]
        )
        for stratum in protocol["sampling"]["strata"]
    }
    _require(by_stratum == expected_by_stratum, "semantics stratum counts drifted")

    thresholds = protocol["decision_rule"]["consistent_with_all_assigned_descriptors_if"]
    every_stratum_separates = all(
        result["all_descriptor_assignment_match_fraction"]
        > result["major_topic_assignment_match_fraction"]
        for result in expected_by_stratum.values()
    )
    passes = (
        comparison["record_return_fraction"]
        >= protocol["comparison"]["required_record_return_fraction"]
        and overall["all_descriptor_assignment_match_fraction"]
        >= thresholds["minimum_all_descriptor_assignment_match_fraction"]
        and overall["major_topic_assignment_match_fraction"]
        <= thresholds["maximum_major_topic_assignment_match_fraction"]
        and (
            every_stratum_separates
            or not thresholds[
                "all_descriptor_match_must_exceed_major_topic_match_in_every_stratum"
            ]
        )
    )
    expected_checks = {
        "required_record_return_fraction": protocol["comparison"][
            "required_record_return_fraction"
        ],
        "minimum_all_descriptor_assignment_match_fraction": thresholds[
            "minimum_all_descriptor_assignment_match_fraction"
        ],
        "maximum_major_topic_assignment_match_fraction": thresholds[
            "maximum_major_topic_assignment_match_fraction"
        ],
        "all_descriptor_match_exceeds_major_topic_match_in_every_stratum": (
            every_stratum_separates
        ),
        "passed": passes,
    }
    _require(payload.get("decision_checks") == expected_checks, "semantics decision checks drifted")
    expected_classification = protocol["decision_rule"][
        "passing_label" if passes else "nonpassing_label"
    ]
    _require(
        payload.get("classification") == expected_classification,
        "semantics classification does not follow the frozen rule",
    )
    expected_interpretation = (
        "The predeclared balanced sample is consistent with meshMajor containing all assigned "
        "descriptors rather than only MajorTopicYN=Y headings."
        if passes
        else "The predeclared balanced sample does not resolve whether meshMajor contains all "
        "assigned descriptors rather than only MajorTopicYN=Y headings."
    )
    _require(payload.get("interpretation") == expected_interpretation, "interpretation drifted")
    _require(payload.get("limitations") == protocol["limitations"], "semantics limitations drifted")
    return payload


def audit_semantics_sample(
    sample_path: Path,
    snapshot_path: Path,
    *,
    protocol_path: Path = PROTOCOL_PATH,
    client: PubMedClient | None = None,
) -> dict:
    protocol = audit_semantics_protocol(protocol_path)
    sample = json.loads(sample_path.read_text(encoding="utf-8"))
    regenerated_sample = select_semantics_sample(snapshot_path, protocol_path=protocol_path)
    _require(
        sample == regenerated_sample,
        "semantics sample does not match a fresh selection from the pinned snapshot",
    )
    expected_protocol = _file_reference(protocol_path)
    _require(
        sample.get("protocol", {}).get("sha256") == expected_protocol["sha256"],
        "semantics sample was selected under a different protocol",
    )
    client = client or PubMedClient()
    result = compare_semantics_sample(sample, protocol, client.fetch_records)
    result["sample"]["selection_file"] = _file_reference(sample_path)
    return result


def _write_new(path: Path, payload: dict) -> None:
    if path.exists():
        raise SystemExit(f"refusing to overwrite existing output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    try:
        relative = path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        relative = str(path)
    print(f"wrote {relative}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=PROTOCOL_PATH)
    subparsers = parser.add_subparsers(dest="command", required=True)
    sample = subparsers.add_parser("sample", help="select the frozen sample from the full snapshot")
    sample.add_argument("snapshot", type=Path)
    sample.add_argument("--output", type=Path, default=DEFAULT_SAMPLE_PATH)
    audit = subparsers.add_parser("audit", help="compare the selected sample with current PubMed")
    audit.add_argument("sample", type=Path)
    audit.add_argument(
        "--snapshot",
        type=Path,
        required=True,
        help="recompute and verify the sample from this full snapshot before EFetch",
    )
    audit.add_argument("--output", type=Path, default=DEFAULT_AUDIT_PATH)
    audit.add_argument(
        "--refresh-pubmed",
        action="store_true",
        help="ignore matching PubMed caches (required if a legacy cache lacks response digests)",
    )
    args = parser.parse_args()
    if args.command == "sample":
        payload = select_semantics_sample(args.snapshot, protocol_path=args.protocol)
    else:
        payload = audit_semantics_sample(
            args.sample,
            args.snapshot,
            protocol_path=args.protocol,
            client=PubMedClient(use_cache=not args.refresh_pubmed),
        )
    _write_new(args.output, payload)


if __name__ == "__main__":
    main()
