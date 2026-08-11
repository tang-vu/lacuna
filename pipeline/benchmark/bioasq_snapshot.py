"""Stream and fingerprint the registered-download BioASQ 2013 Task 1a snapshot.

The raw training set is a multi-gigabyte JSON object whose ``articles`` array cannot be loaded in
memory. This module streams one article at a time, validates its published fields, checks every
``meshMajor`` label against the pinned 2013 MeSH descriptor vocabulary, and emits an aggregate
manifest. The output always contributes zero metric-v3 readiness: BioASQ is a secondary, scoped
snapshot, not one of the missing complete NLM baselines.

Rebuild the measured audit to a review path after downloading the raw v2013 set:

    python -m pipeline.benchmark.bioasq_snapshot \
      --output path/to/rebuilt-bioasq-2013-task-a.json \
      path/to/raw_training_set.zip

The pinned payload fails ``--require-declared-match`` because its publication-year scope differs
from the published description. That strict failure is an audit result, not an error to bypass.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import re
import zipfile
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TextIO
from xml.etree import ElementTree

from pipeline.benchmark.audit_mesh import pinned_file
from pipeline.benchmark.pin_mesh import inspect_descriptor_archive
from pipeline.paths import MESH_CACHE_DIR, REPO_ROOT

CHUNK_SIZE = 1024 * 1024
MAX_ARTICLE_CHARS = 64 * 1024 * 1024
JSON_HEADER = re.compile(r'^\ufeff?\s*\{\s*"articles"\s*:\s*\[')
LEGACY_ASSIGNMENT_HEADER = re.compile(r"^\ufeff?\s*\{\s*'articles'\s*=\s*\[")
YEAR_TOKEN = re.compile(r"(?<!\d)(?:18|19|20)\d{2}(?!\d)")
YEAR_NORMALISATION_RULE = (
    "strip_text_then_parse_full_digits_else_first_four_digit_token_not_adjacent_to_a_digit"
)
TRAILER = re.compile(r"^\s*\}\s*$")
REQUIRED_FIELDS = {"abstractText", "journal", "meshMajor", "pmid", "title", "year"}
ALTERNATIVES_PATH = REPO_ROOT / "benchmarks" / "v3" / "source-alternatives.json"
MANIFEST_PATH = REPO_ROOT / "benchmarks" / "v3" / "manifests" / "bioasq-2013-task-a.json"


class BioasqSnapshotError(ValueError):
    pass


@dataclass(frozen=True)
class BioasqMeasurement:
    article_count: int
    mesh_assignment_count: int
    distinct_mesh_label_count: int
    publication_year_min: int
    publication_year_max: int
    publication_year_counts: dict[int, int]
    articles_without_mesh_labels: int
    noncanonical_year_count: int
    noncanonical_year_examples: tuple[str, ...]
    unparseable_year_count: int
    unparseable_year_examples: tuple[str, ...]
    articles_with_duplicate_mesh_labels: int
    duplicate_mesh_assignment_count: int
    unknown_mesh_labels: tuple[str, ...]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BioasqSnapshotError(message)


def _normalise(value: str) -> str:
    return " ".join(value.casefold().split())


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK_SIZE), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _zip_json_member(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            members = [
                item.filename
                for item in archive.infolist()
                if not item.is_dir() and item.filename.casefold().endswith(".json")
            ]
    except (OSError, zipfile.BadZipFile) as exc:
        raise BioasqSnapshotError(f"{path.name}: not a readable ZIP archive") from exc
    _require(len(members) == 1, f"{path.name}: expected exactly one JSON member")
    return members[0]


def _match_header(prefix: str) -> tuple[re.Match[str] | None, str | None]:
    match = JSON_HEADER.match(prefix)
    if match is not None:
        return match, "json_articles_colon"
    match = LEGACY_ASSIGNMENT_HEADER.match(prefix)
    if match is not None:
        return match, "bioasq_single_quote_assignment"
    return None, None


@contextmanager
def open_snapshot_text(path: Path) -> Iterator[tuple[TextIO, dict]]:
    """Open plain, gzip, or single-JSON-member ZIP input without extracting it."""
    suffix = path.suffix.casefold()
    if suffix == ".zip":
        member = _zip_json_member(path)
        with zipfile.ZipFile(path) as archive:
            info = archive.getinfo(member)
            with archive.open(info, "r") as binary:
                with io.TextIOWrapper(binary, encoding="utf-8") as text:
                    yield text, {
                        "format": "zip",
                        "member": member,
                        "member_bytes": info.file_size,
                        "member_compressed_bytes": info.compress_size,
                        "member_crc32": f"{info.CRC:08x}",
                    }
        return
    if suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as text:
            yield text, {"format": "gzip"}
        return
    with path.open("rt", encoding="utf-8") as text:
        yield text, {"format": "json"}


def iter_articles(stream: TextIO) -> Iterator[dict]:
    """Yield objects from the top-level ``articles`` array with bounded memory."""
    prefix = stream.read(CHUNK_SIZE)
    match, _envelope = _match_header(prefix)
    _require(
        match is not None,
        'snapshot must start with a supported top-level "articles" envelope',
    )
    decoder = json.JSONDecoder()
    buffer = prefix[match.end() :]
    index = 0
    need_comma = False
    after_comma = False

    while True:
        while index < len(buffer) and buffer[index].isspace():
            index += 1
        if index == len(buffer):
            buffer = stream.read(CHUNK_SIZE)
            index = 0
            if not buffer:
                raise BioasqSnapshotError("snapshot ended before the articles array closed")
            continue

        char = buffer[index]
        if need_comma:
            if char == ",":
                need_comma = False
                after_comma = True
                index += 1
                continue
            if char == "]":
                trailer = buffer[index + 1 :] + stream.read()
                _require(
                    TRAILER.fullmatch(trailer) is not None,
                    "unexpected data after articles",
                )
                return
            raise BioasqSnapshotError("articles must be comma-separated")

        if char == "]":
            _require(not after_comma, "articles array must not end after a comma")
            trailer = buffer[index + 1 :] + stream.read()
            _require(
                TRAILER.fullmatch(trailer) is not None,
                "unexpected data after articles",
            )
            return
        if char != "{":
            raise BioasqSnapshotError("articles array contains a non-object entry")

        while True:
            try:
                article, end = decoder.raw_decode(buffer, index)
                _require(
                    end - index <= MAX_ARTICLE_CHARS,
                    "article JSON exceeds streaming safety limit",
                )
                break
            except json.JSONDecodeError as exc:
                _require(
                    len(buffer) - index <= MAX_ARTICLE_CHARS,
                    "article JSON exceeds streaming safety limit",
                )
                chunk = stream.read(CHUNK_SIZE)
                if not chunk:
                    raise BioasqSnapshotError("invalid or truncated article JSON") from exc
                buffer = buffer[index:] + chunk
                index = 0

        _require(isinstance(article, dict), "article entry must be an object")
        yield article
        index = end
        need_comma = True
        after_comma = False


def snapshot_envelope(path: Path) -> str:
    """Identify the exact bounded envelope dialect without parsing the corpus."""
    with open_snapshot_text(path) as (stream, _):
        prefix = stream.read(CHUNK_SIZE)
    match, envelope = _match_header(prefix)
    _require(match is not None and envelope is not None, "unsupported snapshot envelope")
    return envelope


def descriptor_label_index(mesh_path: Path) -> dict[str, str]:
    labels: dict[str, str] = {}
    with gzip.open(mesh_path, "rb") as stream:
        for _, element in ElementTree.iterparse(stream, events=("end",)):
            if element.tag.rsplit("}", 1)[-1] != "DescriptorRecord":
                continue
            descriptor_ui = element.findtext("./DescriptorUI") or ""
            descriptor_label = element.findtext("./DescriptorName/String") or ""
            normalised = _normalise(descriptor_label)
            _require(bool(descriptor_ui and normalised), "MeSH descriptor is missing UI or label")
            existing = labels.get(normalised)
            _require(
                existing in (None, descriptor_ui),
                f"ambiguous normalised descriptor label: {descriptor_label}",
            )
            labels[normalised] = descriptor_ui
            element.clear()
    _require(bool(labels), "MeSH archive contains no descriptor labels")
    return labels


def validate_article(
    article: dict, article_number: int
) -> tuple[str, int | None, tuple[str, ...], bool, str]:
    """Validate one documented BioASQ record and return its sampling fields.

    Keeping this check shared prevents the aggregate snapshot audit and the separately frozen
    semantics sampler from accepting different record shapes.
    """
    _require(REQUIRED_FIELDS.issubset(article), f"article {article_number}: missing fields")
    pmid = article["pmid"]
    _require(
        isinstance(pmid, (str, int)) and str(pmid).isdigit(),
        f"article {article_number}: PMID must be numeric",
    )
    for field in ("abstractText", "journal", "title"):
        _require(
            isinstance(article[field], str),
            f"article {article_number}: {field} must be text",
        )
    year = article["year"]
    _require(
        isinstance(year, (str, int)),
        f"article {article_number}: publication year must be text or integer",
    )
    raw_year = str(year).strip()
    canonical_year = raw_year.isdigit()
    year_match = YEAR_TOKEN.search(raw_year)
    numeric_year = (
        int(raw_year)
        if canonical_year
        else (int(year_match.group()) if year_match else None)
    )
    assigned = article["meshMajor"]
    _require(
        isinstance(assigned, list)
        and all(isinstance(label, str) and label.strip() for label in assigned),
        f"article {article_number}: meshMajor must be a list of labels",
    )
    return str(pmid), numeric_year, tuple(assigned), canonical_year, raw_year


def measure_snapshot(path: Path, *, mesh_path: Path) -> BioasqMeasurement:
    descriptor_labels = descriptor_label_index(mesh_path)
    article_count = 0
    assignment_count = 0
    empty_mesh_count = 0
    publication_year_min: int | None = None
    publication_year_max: int | None = None
    publication_year_counts: Counter[int] = Counter()
    mesh_labels: set[str] = set()
    unknown_mesh_labels: set[str] = set()
    noncanonical_year_count = 0
    noncanonical_year_examples: list[str] = []
    unparseable_year_count = 0
    unparseable_year_examples: list[str] = []
    duplicate_mesh_article_count = 0
    duplicate_mesh_assignment_count = 0

    with open_snapshot_text(path) as (stream, _):
        for article in iter_articles(stream):
            article_count += 1
            _pmid, numeric_year, assigned, canonical_year, raw_year = validate_article(
                article, article_count
            )
            if numeric_year is None:
                unparseable_year_count += 1
                if (
                    raw_year not in unparseable_year_examples
                    and len(unparseable_year_examples) < 20
                ):
                    unparseable_year_examples.append(raw_year)
            else:
                publication_year_counts[numeric_year] += 1
                publication_year_min = (
                    numeric_year
                    if publication_year_min is None
                    else min(publication_year_min, numeric_year)
                )
                publication_year_max = (
                    numeric_year
                    if publication_year_max is None
                    else max(publication_year_max, numeric_year)
                )
                if not canonical_year:
                    noncanonical_year_count += 1
                    if (
                        raw_year not in noncanonical_year_examples
                        and len(noncanonical_year_examples) < 20
                    ):
                        noncanonical_year_examples.append(raw_year)
            if not assigned:
                empty_mesh_count += 1
            assignment_count += len(assigned)
            normalised_labels = [_normalise(label) for label in assigned]
            duplicate_count = len(normalised_labels) - len(set(normalised_labels))
            if duplicate_count:
                duplicate_mesh_article_count += 1
                duplicate_mesh_assignment_count += duplicate_count
            for label in assigned:
                mesh_labels.add(label)
                if _normalise(label) not in descriptor_labels:
                    unknown_mesh_labels.add(label)

    _require(article_count > 0, "snapshot contains no articles")
    _require(publication_year_min is not None, "snapshot contains no parseable publication year")
    return BioasqMeasurement(
        article_count=article_count,
        mesh_assignment_count=assignment_count,
        distinct_mesh_label_count=len(mesh_labels),
        publication_year_min=int(publication_year_min),
        publication_year_max=int(publication_year_max),
        publication_year_counts=dict(sorted(publication_year_counts.items())),
        articles_without_mesh_labels=empty_mesh_count,
        noncanonical_year_count=noncanonical_year_count,
        noncanonical_year_examples=tuple(noncanonical_year_examples),
        unparseable_year_count=unparseable_year_count,
        unparseable_year_examples=tuple(unparseable_year_examples),
        articles_with_duplicate_mesh_labels=duplicate_mesh_article_count,
        duplicate_mesh_assignment_count=duplicate_mesh_assignment_count,
        unknown_mesh_labels=tuple(sorted(unknown_mesh_labels)),
    )


def _declared_snapshot(path: Path = ALTERNATIVES_PATH) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return next(
        item["declared_snapshot"]
        for item in payload["alternatives"]
        if item["id"] == "bioasq-2013-task-a"
    )


def audit_snapshot(
    path: Path,
    *,
    mesh_path: Path | None = None,
    require_declared_match: bool = False,
) -> dict:
    expected_mesh = pinned_file(2013)
    mesh_path = mesh_path or MESH_CACHE_DIR / "desc2013.gz"
    _require(mesh_path.is_file(), f"missing pinned vocabulary archive: {mesh_path}")
    mesh_sha256, mesh_bytes, descriptor_count = inspect_descriptor_archive(mesh_path)
    _require(mesh_sha256 == expected_mesh["sha256"], "2013 MeSH checksum mismatch")
    _require(
        mesh_bytes == expected_mesh["bytes"]
        and descriptor_count == expected_mesh["descriptor_count"],
        "2013 MeSH measured metadata mismatch",
    )
    payload_sha256, payload_bytes = _sha256_file(path)
    with open_snapshot_text(path) as (_, container):
        container_metadata = {**container, "envelope": snapshot_envelope(path)}
    measured = measure_snapshot(path, mesh_path=mesh_path)
    declared = _declared_snapshot()
    measured_average = measured.mesh_assignment_count / measured.article_count
    aggregate_counts_match = (
        measured.article_count == declared["article_count"]
        and measured.distinct_mesh_label_count == declared["mesh_label_count"]
        and round(measured_average, 2) == declared["average_mesh_labels_per_article"]
    )
    articles_before_declared_scope = sum(
        count
        for year, count in measured.publication_year_counts.items()
        if year < 1950
    )
    articles_after_snapshot_version = sum(
        count
        for year, count in measured.publication_year_counts.items()
        if year > declared["version_year"]
    )
    publication_scope_match = (
        articles_before_declared_scope == 0
        and articles_after_snapshot_version == 0
        and measured.unparseable_year_count == 0
    )
    declared_match = (
        aggregate_counts_match
        and publication_scope_match
        and measured.articles_without_mesh_labels == 0
        and measured.noncanonical_year_count == 0
        and measured.articles_with_duplicate_mesh_labels == 0
        and not measured.unknown_mesh_labels
    )
    if require_declared_match:
        _require(declared_match, "measured snapshot does not match BioASQ's published v2013 scope")

    return {
        "schema_version": 1,
        "status": "audited_secondary_snapshot" if declared_match else "measured_unmatched_input",
        "readiness_contribution": 0,
        "source_alternative_id": "bioasq-2013-task-a",
        "input": {
            "local_name": path.name,
            "sha256": payload_sha256,
            "bytes": payload_bytes,
            "container": container_metadata,
        },
        "measured": {
            **asdict(measured),
            "average_mesh_labels_per_article": round(measured_average, 8),
        },
        "declared_comparison": {
            "article_count": declared["article_count"],
            "mesh_label_count": declared["mesh_label_count"],
            "average_mesh_labels_per_article": declared["average_mesh_labels_per_article"],
            "publication_scope": declared["publication_scope"],
            "articles_before_declared_publication_scope": articles_before_declared_scope,
            "articles_after_snapshot_version": articles_after_snapshot_version,
            "matches_published_aggregate_counts": aggregate_counts_match,
            "matches_published_publication_scope": publication_scope_match,
            "passes_declared_snapshot_gate": declared_match,
        },
        "mesh_vocabulary": expected_mesh,
        "limitations": [
            "This secondary BioASQ corpus is not the complete 2013 NLM baseline and cannot satisfy the original four-release source gate.",
            "Matching published aggregate counts does not establish PMID-by-PMID completeness or whether meshMajor contains only major headings versus all assigned descriptors.",
            "Non-YYYY publication-year values are parsed only for aggregate year bounds and are reported separately rather than silently treated as schema-conforming years.",
            "Any metric experiment using this input needs a separately frozen pre-registration scoped to the measured BioASQ corpus.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--require-declared-match", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = audit_snapshot(args.path, require_declared_match=args.require_declared_match)
    rendered = json.dumps(payload, indent=1)
    if args.output:
        if args.output.exists():
            raise SystemExit(f"refusing to overwrite existing audit manifest: {args.output}")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        try:
            relative = args.output.relative_to(REPO_ROOT).as_posix()
        except ValueError:
            relative = str(args.output)
        print(f"wrote {relative}")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
