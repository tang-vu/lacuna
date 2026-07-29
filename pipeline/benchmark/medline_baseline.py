"""Stream historical MEDLINE baseline XML and measure selected MeSH pairs.

This module is deliberately narrower than a general bibliometric graph builder. It keeps counters
only for requested endpoint descriptors, so memory grows with the benchmark rather than with every
pair in MEDLINE. It reports direct co-occurrence and shared ABC neighbours; it does not turn either
quantity into a gap score.

The parser can be tested against synthetic fixtures, but a production run must remain gated on
``historical_records == available_pinned`` in ``benchmarks/v3/sources.json``. Current PubMed records
are not a substitute for an older indexing state.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, replace
from itertools import combinations
from pathlib import Path
from typing import BinaryIO, Iterable, Iterator
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree

from pipeline.benchmark.source_manifests import load_release_for_year
from pipeline.benchmark.validate_sources import SOURCES_PATH, audit_sources

MESH_DESCRIPTOR_UI = re.compile(r"^D\d{6}$")


class HistoricalRecordsNotReady(RuntimeError):
    """Raised when code attempts a production run without pinned historical records."""


@dataclass(frozen=True)
class MedlineRecord:
    pmid: str
    publication_year: int | None
    descriptor_uis: frozenset[str]


@dataclass(frozen=True)
class BaselineStats:
    records_seen: int
    records_in_cutoff: int
    records_after_cutoff: int
    records_missing_year: int
    records_without_mesh: int


@dataclass(frozen=True)
class SourceFileEvidence:
    filename: str
    sha256: str
    bytes: int


@dataclass(frozen=True)
class BridgeEvidence:
    descriptor_ui: str
    left_cooccurrence: int
    right_cooccurrence: int


@dataclass(frozen=True)
class PairEvidence:
    left_ui: str
    right_ui: str
    left_records: int
    right_records: int
    direct_cooccurrence: int
    expected_under_independence: float
    bridges: tuple[BridgeEvidence, ...]


@dataclass(frozen=True)
class BaselineEvidence:
    schema_version: int
    indexing_basis: str
    baseline_release_year: int | None
    source_contract_sha256: str | None
    vocabulary_sha256: str | None
    cutoff_basis: str
    cutoff_year: int
    source_files: tuple[SourceFileEvidence, ...]
    stats: BaselineStats
    pairs: tuple[PairEvidence, ...]

    def as_dict(self) -> dict:
        return asdict(self)


def require_pinned_historical_records(source_path: Path = SOURCES_PATH) -> None:
    """Refuse a production measurement until the historical-record source gate is green."""
    audit = audit_sources(source_path)
    status = audit.statuses.get("historical_records", "missing")
    if status != "available_pinned":
        raise HistoricalRecordsNotReady(
            "historical MEDLINE records are not pinned "
            f"(status: {status}); current PubMed data cannot satisfy this gate"
        )


def _source_by_kind(source_path: Path, kind: str) -> dict:
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    return next(source for source in payload["sources"] if source["kind"] == kind)


def _open_xml(path: Path) -> BinaryIO:
    if path.suffix.lower() == ".gz":
        return gzip.open(path, "rb")
    return path.open("rb")


def fingerprint_file(path: Path) -> SourceFileEvidence:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return SourceFileEvidence(filename=path.name, sha256=digest.hexdigest(), bytes=size)


def _publication_year(citation: ElementTree.Element) -> int | None:
    article = citation.find("./Article")
    if article is None:
        return None
    year = article.findtext("./Journal/JournalIssue/PubDate/Year")
    if year and year.isdigit():
        return int(year)
    medline_date = article.findtext("./Journal/JournalIssue/PubDate/MedlineDate") or ""
    match = re.search(r"\b(?:18|19|20)\d{2}\b", medline_date)
    return int(match.group()) if match else None


def _record_from_citation(citation: ElementTree.Element) -> MedlineRecord:
    descriptor_uis = frozenset(
        descriptor.get("UI", "")
        for descriptor in citation.findall("./MeshHeadingList/MeshHeading/DescriptorName")
        if MESH_DESCRIPTOR_UI.fullmatch(descriptor.get("UI", ""))
    )
    return MedlineRecord(
        pmid=citation.findtext("./PMID") or "",
        publication_year=_publication_year(citation),
        descriptor_uis=descriptor_uis,
    )


def iter_medline_records(paths: Iterable[Path]) -> Iterator[MedlineRecord]:
    """Yield trimmed citation records from baseline XML or XML.gz files.

    ``Element.clear`` releases each completed article before the next one is parsed. Delete records
    and unsupported book records are ignored because they do not contain the citation/MeSH shape
    measured here. Historical licensee distributions use ``MedlineCitationSet`` with direct
    ``MedlineCitation`` children; current PubMed files wrap each citation in ``PubmedArticle``.
    """
    for raw_path in paths:
        path = Path(raw_path)
        with _open_xml(path) as handle:
            context = ElementTree.iterparse(handle, events=("start", "end"))
            _event, root = next(context)
            if root.tag == "MedlineCitationSet":
                record_tag = "MedlineCitation"
                direct_citation = True
            elif root.tag == "PubmedArticleSet":
                record_tag = "PubmedArticle"
                direct_citation = False
            else:
                raise ValueError(f"{path}: unsupported MEDLINE XML root {root.tag!r}")
            for event, element in context:
                if event == "end" and element.tag == record_tag:
                    citation = element if direct_citation else element.find("./MedlineCitation")
                    if citation is not None:
                        yield _record_from_citation(citation)
                    # Clearing only the article leaves an empty child attached to the document
                    # root for every citation. Clear the root to release those references too.
                    root.clear()


def _normalise_pairs(pairs: Iterable[tuple[str, str]]) -> tuple[tuple[str, str], ...]:
    normalised: set[tuple[str, str]] = set()
    for left, right in pairs:
        if not MESH_DESCRIPTOR_UI.fullmatch(left) or not MESH_DESCRIPTOR_UI.fullmatch(right):
            raise ValueError(f"invalid MeSH descriptor pair: {left!r}, {right!r}")
        if left == right:
            raise ValueError(f"pair endpoints must differ: {left}")
        normalised.add(tuple(sorted((left, right))))
    if not normalised:
        raise ValueError("at least one MeSH descriptor pair is required")
    return tuple(sorted(normalised))


def measure_pairs(
    paths: Iterable[Path],
    pairs: Iterable[tuple[str, str]],
    *,
    cutoff_year: int,
) -> BaselineEvidence:
    """Count exact endpoint and ABC evidence through a publication-year cutoff.

    Every citation with a known year at or before the cutoff contributes to the corpus denominator,
    including citations with no MeSH headings. Records without a parseable publication year are
    reported separately and excluded rather than silently assigned to a period.
    """
    if cutoff_year < 1800:
        raise ValueError("cutoff_year must be 1800 or later")
    source_paths = tuple(Path(path) for path in paths)
    if not source_paths:
        raise ValueError("at least one MEDLINE baseline file is required")
    source_files = tuple(fingerprint_file(path) for path in source_paths)
    selected_pairs = _normalise_pairs(pairs)
    endpoints = {endpoint for pair in selected_pairs for endpoint in pair}

    endpoint_records: Counter[str] = Counter()
    endpoint_neighbours: dict[str, Counter[str]] = defaultdict(Counter)
    direct_records: Counter[tuple[str, str]] = Counter()
    records_seen = 0
    records_in_cutoff = 0
    records_after_cutoff = 0
    records_missing_year = 0
    records_without_mesh = 0

    for record in iter_medline_records(source_paths):
        records_seen += 1
        if record.publication_year is None:
            records_missing_year += 1
            continue
        if record.publication_year > cutoff_year:
            records_after_cutoff += 1
            continue

        records_in_cutoff += 1
        descriptors = record.descriptor_uis
        if not descriptors:
            records_without_mesh += 1
            continue

        present_endpoints = endpoints.intersection(descriptors)
        for endpoint in present_endpoints:
            endpoint_records[endpoint] += 1
            endpoint_neighbours[endpoint].update(descriptors - {endpoint})
        for left, right in combinations(sorted(present_endpoints), 2):
            pair = (left, right)
            if pair in selected_pairs:
                direct_records[pair] += 1

    measured_pairs = []
    for left, right in selected_pairs:
        left_count = endpoint_records[left]
        right_count = endpoint_records[right]
        denominator = records_in_cutoff
        expected = (left_count * right_count / denominator) if denominator else 0.0
        shared = set(endpoint_neighbours[left]).intersection(endpoint_neighbours[right])
        shared.difference_update({left, right})
        bridges = tuple(
            sorted(
                (
                    BridgeEvidence(
                        descriptor_ui=descriptor,
                        left_cooccurrence=endpoint_neighbours[left][descriptor],
                        right_cooccurrence=endpoint_neighbours[right][descriptor],
                    )
                    for descriptor in shared
                ),
                key=lambda item: (
                    -min(item.left_cooccurrence, item.right_cooccurrence),
                    -(item.left_cooccurrence + item.right_cooccurrence),
                    item.descriptor_ui,
                ),
            )
        )
        measured_pairs.append(
            PairEvidence(
                left_ui=left,
                right_ui=right,
                left_records=left_count,
                right_records=right_count,
                direct_cooccurrence=direct_records[(left, right)],
                expected_under_independence=expected,
                bridges=bridges,
            )
        )

    return BaselineEvidence(
        schema_version=1,
        indexing_basis="unverified_medline_xml",
        baseline_release_year=None,
        source_contract_sha256=None,
        vocabulary_sha256=None,
        cutoff_basis="publication_year_lte",
        cutoff_year=cutoff_year,
        source_files=source_files,
        stats=BaselineStats(
            records_seen=records_seen,
            records_in_cutoff=records_in_cutoff,
            records_after_cutoff=records_after_cutoff,
            records_missing_year=records_missing_year,
            records_without_mesh=records_without_mesh,
        ),
        pairs=tuple(measured_pairs),
    )


def measure_pinned_release(
    paths: Iterable[Path],
    pairs: Iterable[tuple[str, str]],
    *,
    baseline_release_year: int,
    cutoff_year: int,
    source_path: Path = SOURCES_PATH,
) -> BaselineEvidence:
    """Verify a complete pinned release before labelling its measurements historical."""
    require_pinned_historical_records(source_path)
    if cutoff_year > baseline_release_year:
        raise ValueError("cutoff_year cannot be later than the baseline release year")
    source = _source_by_kind(source_path, "historical_records")
    vocabulary = _source_by_kind(source_path, "historical_vocabulary")
    release = load_release_for_year(source_path, source, baseline_release_year)
    vocabulary_file = next(
        item for item in vocabulary["files"] if item["year"] == baseline_release_year
    )

    source_paths = tuple(Path(path) for path in paths)
    actual = tuple(fingerprint_file(path) for path in source_paths)
    expected_identities = sorted(
        (
            unquote(Path(urlsplit(item.url).path).name),
            item.sha256,
            item.bytes,
        )
        for item in release.files
    )
    actual_identities = sorted(
        (item.filename, item.sha256, item.bytes) for item in actual
    )
    if actual_identities != expected_identities:
        raise HistoricalRecordsNotReady(
            "local MEDLINE files do not exactly match the complete pinned release "
            f"for {baseline_release_year}"
        )

    evidence = measure_pairs(source_paths, pairs, cutoff_year=cutoff_year)
    expected_record_count = release.total_record_count
    if evidence.stats.records_seen != expected_record_count:
        raise HistoricalRecordsNotReady(
            "parsed MEDLINE record count does not match the pinned release "
            f"({evidence.stats.records_seen} != {expected_record_count})"
        )
    return replace(
        evidence,
        indexing_basis="pinned_historical_medline",
        baseline_release_year=baseline_release_year,
        source_contract_sha256=hashlib.sha256(source_path.read_bytes()).hexdigest(),
        vocabulary_sha256=vocabulary_file["sha256"],
    )


def _parse_pair(value: str) -> tuple[str, str]:
    try:
        left, right = value.split(":", 1)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("pairs must use LEFT_UI:RIGHT_UI") from exc
    return left, right


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--pair", action="append", required=True, type=_parse_pair)
    parser.add_argument("--baseline-year", required=True, type=int)
    parser.add_argument("--cutoff-year", required=True, type=int)
    args = parser.parse_args()
    try:
        evidence = measure_pinned_release(
            args.files,
            args.pair,
            baseline_release_year=args.baseline_year,
            cutoff_year=args.cutoff_year,
        )
    except HistoricalRecordsNotReady as exc:
        raise SystemExit(str(exc)) from None
    print(json.dumps(evidence.as_dict(), indent=2))


if __name__ == "__main__":
    main()
