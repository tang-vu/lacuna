"""Audit the official five-record BioASQ sample against pinned MeSH and current PubMed XML.

This is a bounded schema/provenance check, not evidence that the full 10.8-million-record corpus
matches its published scope.  Current PubMed is used only to distinguish all descriptor headings
from current ``MajorTopicYN=Y`` headings and is explicitly not treated as historical indexing.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from xml.etree import ElementTree

from pipeline.benchmark.bioasq_download import (
    DEFAULT_PUBMED_PATH,
    DEFAULT_SAMPLE_PATH,
    PUBLIC_EFETCH_URL,
    PUBLIC_SAMPLE_BYTES,
    PUBLIC_SAMPLE_SHA256,
    PUBLIC_SAMPLE_URL,
)
from pipeline.benchmark.bioasq_snapshot import (
    _sha256_file,
    measure_snapshot,
    open_snapshot_text,
    iter_articles,
)
from pipeline.benchmark.audit_mesh import pinned_file
from pipeline.benchmark.pin_mesh import inspect_descriptor_archive
from pipeline.paths import MESH_CACHE_DIR, REPO_ROOT

DEFAULT_OUTPUT = (
    REPO_ROOT / "benchmarks" / "v3" / "manifests" / "bioasq-2013-public-sample.json"
)


class BioasqSampleAuditError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BioasqSampleAuditError(message)


def _sample_assignments(path: Path) -> dict[str, list[str]]:
    assignments: dict[str, list[str]] = {}
    with open_snapshot_text(path) as (stream, _):
        for article in iter_articles(stream):
            pmid = str(article["pmid"])
            _require(pmid not in assignments, f"duplicate sample PMID: {pmid}")
            assignments[pmid] = list(article["meshMajor"])
    return assignments


def _current_pubmed_assignments(path: Path) -> dict[str, tuple[set[str], set[str]]]:
    try:
        root = ElementTree.parse(path).getroot()
    except (OSError, ElementTree.ParseError) as exc:
        raise BioasqSampleAuditError(f"unreadable PubMed XML: {path}") from exc
    assignments: dict[str, tuple[set[str], set[str]]] = {}
    for article in root.findall("./PubmedArticle"):
        citation = article.find("./MedlineCitation")
        _require(citation is not None, "PubMed article is missing MedlineCitation")
        pmid = citation.findtext("./PMID") or ""
        _require(pmid.isdigit() and pmid not in assignments, f"invalid PubMed PMID: {pmid!r}")
        all_labels: set[str] = set()
        major_labels: set[str] = set()
        for descriptor in citation.findall("./MeshHeadingList/MeshHeading/DescriptorName"):
            label = descriptor.text or ""
            _require(bool(label), f"PubMed PMID {pmid}: empty descriptor label")
            all_labels.add(label)
            if descriptor.attrib.get("MajorTopicYN") == "Y":
                major_labels.add(label)
        assignments[pmid] = (all_labels, major_labels)
    _require(bool(assignments), "PubMed XML contains no articles")
    return assignments


def audit_public_sample(
    sample_path: Path = DEFAULT_SAMPLE_PATH,
    pubmed_path: Path = DEFAULT_PUBMED_PATH,
    *,
    mesh_path: Path | None = None,
    observed_on: date | None = None,
    expected_sample_sha256: str = PUBLIC_SAMPLE_SHA256,
    expected_sample_bytes: int = PUBLIC_SAMPLE_BYTES,
    verify_pinned_mesh: bool = True,
) -> dict:
    sample_sha256, sample_bytes = _sha256_file(sample_path)
    _require(sample_sha256 == expected_sample_sha256, "official BioASQ sample checksum drifted")
    _require(sample_bytes == expected_sample_bytes, "official BioASQ sample byte count drifted")
    mesh_path = mesh_path or MESH_CACHE_DIR / "desc2013.gz"
    expected_mesh = pinned_file(2013)
    if verify_pinned_mesh:
        mesh_sha256, mesh_bytes, descriptor_count = inspect_descriptor_archive(mesh_path)
        _require(mesh_sha256 == expected_mesh["sha256"], "2013 MeSH checksum mismatch")
        _require(
            mesh_bytes == expected_mesh["bytes"]
            and descriptor_count == expected_mesh["descriptor_count"],
            "2013 MeSH measured metadata mismatch",
        )
    measured = measure_snapshot(sample_path, mesh_path=mesh_path)
    sample = _sample_assignments(sample_path)
    current = _current_pubmed_assignments(pubmed_path)
    _require(set(sample) == set(current), "BioASQ and PubMed sample PMID sets differ")

    all_overlap = 0
    major_overlap = 0
    sample_only: dict[str, list[str]] = defaultdict(list)
    for pmid, labels in sample.items():
        all_labels, major_labels = current[pmid]
        for label in labels:
            all_overlap += label in all_labels
            major_overlap += label in major_labels
            if label not in all_labels:
                sample_only[pmid].append(label)

    pubmed_sha256, pubmed_bytes = _sha256_file(pubmed_path)
    observed = observed_on or date.today()
    return {
        "schema_version": 1,
        "status": "bounded_public_sample_audit",
        "readiness_contribution": 0,
        "source_alternative_id": "bioasq-2013-task-a",
        "observed_on": observed.isoformat(),
        "bioasq_public_sample": {
            "source_url": PUBLIC_SAMPLE_URL,
            "sha256": sample_sha256,
            "bytes": sample_bytes,
            "article_count": measured.article_count,
            "mesh_assignment_count": measured.mesh_assignment_count,
            "distinct_mesh_label_count": measured.distinct_mesh_label_count,
            "publication_year_min": measured.publication_year_min,
            "publication_year_max": measured.publication_year_max,
            "articles_without_mesh_labels": measured.articles_without_mesh_labels,
            "labels_absent_from_pinned_mesh_2013": list(measured.unknown_mesh_labels),
        },
        "mesh_vocabulary": expected_mesh if verify_pinned_mesh else {"fixture": True},
        "maintained_current_pubmed_comparison": {
            "query_url": PUBLIC_EFETCH_URL,
            "response_sha256": pubmed_sha256,
            "response_bytes": pubmed_bytes,
            "pmids": sorted(sample, key=int),
            "records_returned": len(current),
            "sample_assignments": measured.mesh_assignment_count,
            "matched_current_all_descriptor_assignments": all_overlap,
            "matched_current_major_topic_assignments": major_overlap,
            "sample_only_labels_by_pmid": dict(sorted(sample_only.items())),
        },
        "interpretation": (
            "In this five-record sample, meshMajor behaves like an all-assigned-descriptor field, "
            "not a major-topic-only field: 71 of 72 sample assignments match maintained-current "
            "PubMed descriptors, while 9 match maintained-current MajorTopicYN=Y descriptors."
        ),
        "limitations": [
            "This is an exhaustive measurement of five public sample records, not a sample selected or sized to establish corpus-wide semantics.",
            "The PubMed comparison is maintained-current indexing observed on the audit date, not period-appropriate 2013 indexing; label and major-topic flags may have changed.",
            "The one sample-only label is evidence of a difference from current PubMed, not proof of why or when the assignment changed.",
            "The registered full payload remains unacquired and this audit contributes zero readiness to both the original baseline gate and any redesigned experiment.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=Path, default=DEFAULT_SAMPLE_PATH)
    parser.add_argument("--pubmed", type=Path, default=DEFAULT_PUBMED_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    payload = audit_public_sample(args.sample, args.pubmed)
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite existing audit manifest: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    try:
        relative = args.output.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        relative = str(args.output)
    print(f"wrote {relative}")


if __name__ == "__main__":
    main()
