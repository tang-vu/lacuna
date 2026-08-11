"""Stream and fingerprint the registered-download BioASQ 2013 Task 1a snapshot.

The raw training set is a multi-gigabyte JSON object whose ``articles`` array cannot be loaded in
memory. This module streams one article at a time, validates its published fields, checks every
``meshMajor`` label against the pinned 2013 MeSH descriptor vocabulary, and emits an aggregate
manifest. The output always contributes zero metric-v3 readiness: BioASQ is a secondary, scoped
snapshot, not one of the missing complete NLM baselines.

After downloading the raw v2013 set through a registered BioASQ account, run:

    python -m pipeline.benchmark.bioasq_snapshot \
      --require-declared-match --output benchmarks/v3/manifests/bioasq-2013-task-a.json \
      path/to/raw_training_set.zip
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import re
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from itertools import chain
from pathlib import Path
from typing import TextIO
from xml.etree import ElementTree

from pipeline.benchmark.audit_mesh import pinned_file
from pipeline.benchmark.pin_mesh import inspect_descriptor_archive
from pipeline.benchmark.validate_source_alternatives import ALTERNATIVES_PATH
from pipeline.paths import MESH_CACHE_DIR, REPO_ROOT

CHUNK_SIZE = 1024 * 1024
HEADER = re.compile(r'^\ufeff?\s*\{\s*"articles"\s*:\s*\[')
TRAILER = re.compile(r"^\s*\}\s*$")
REQUIRED_FIELDS = {"abstractText", "journal", "meshMajor", "pmid", "title", "year"}


class BioasqSnapshotError(ValueError):
    pass


@dataclass(frozen=True)
class BioasqMeasurement:
    article_count: int
    mesh_assignment_count: int
    distinct_mesh_label_count: int
    publication_year_min: int
    publication_year_max: int
    articles_without_mesh_labels: int
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
    match = HEADER.match(prefix)
    _require(match is not None, 'snapshot must start with a top-level "articles" array')
    chunks = chain(
        (prefix[match.end() :],),
        iter(lambda: stream.read(CHUNK_SIZE), ""),
    )
    object_chars: list[str] = []
    depth = 0
    in_string = False
    escaped = False
    need_comma = False

    for chunk in chunks:
        if not chunk:
            break
        index = 0
        while index < len(chunk):
            char = chunk[index]
            if depth:
                object_chars.append(char)
                if in_string:
                    if escaped:
                        escaped = False
                    elif char == "\\":
                        escaped = True
                    elif char == '"':
                        in_string = False
                elif char == '"':
                    in_string = True
                elif char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            article = json.loads("".join(object_chars))
                        except json.JSONDecodeError as exc:
                            raise BioasqSnapshotError("invalid article JSON") from exc
                        _require(isinstance(article, dict), "article entry must be an object")
                        yield article
                        object_chars.clear()
                        need_comma = True
                index += 1
                continue

            if char.isspace():
                index += 1
                continue
            if need_comma:
                if char == ",":
                    need_comma = False
                    index += 1
                    continue
                if char == "]":
                    trailer = chunk[index + 1 :] + stream.read()
                    _require(TRAILER.fullmatch(trailer) is not None, "unexpected data after articles")
                    return
                raise BioasqSnapshotError("articles must be comma-separated")
            if char == "{":
                depth = 1
                object_chars = [char]
                index += 1
                continue
            if char == "]":
                trailer = chunk[index + 1 :] + stream.read()
                _require(TRAILER.fullmatch(trailer) is not None, "unexpected data after articles")
                return
            raise BioasqSnapshotError("articles array contains a non-object entry")

    if depth:
        raise BioasqSnapshotError("snapshot ended inside an article object")
    raise BioasqSnapshotError("snapshot ended before the articles array closed")


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


def measure_snapshot(path: Path, *, mesh_path: Path) -> BioasqMeasurement:
    descriptor_labels = descriptor_label_index(mesh_path)
    article_count = 0
    assignment_count = 0
    empty_mesh_count = 0
    publication_year_min: int | None = None
    publication_year_max: int | None = None
    mesh_labels: set[str] = set()
    unknown_mesh_labels: set[str] = set()

    with open_snapshot_text(path) as (stream, _):
        for article in iter_articles(stream):
            article_count += 1
            _require(REQUIRED_FIELDS.issubset(article), f"article {article_count}: missing fields")
            pmid = article["pmid"]
            _require(
                isinstance(pmid, (str, int)) and str(pmid).isdigit(),
                f"article {article_count}: PMID must be numeric",
            )
            for field in ("abstractText", "journal", "title"):
                _require(
                    isinstance(article[field], str),
                    f"article {article_count}: {field} must be text",
                )
            year = article["year"]
            _require(
                isinstance(year, (str, int)) and str(year).isdigit(),
                f"article {article_count}: publication year must be numeric",
            )
            numeric_year = int(year)
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
            assigned = article["meshMajor"]
            _require(
                isinstance(assigned, list)
                and all(isinstance(label, str) and label.strip() for label in assigned),
                f"article {article_count}: meshMajor must be a list of labels",
            )
            if not assigned:
                empty_mesh_count += 1
            assignment_count += len(assigned)
            for label in assigned:
                mesh_labels.add(label)
                if _normalise(label) not in descriptor_labels:
                    unknown_mesh_labels.add(label)

    _require(article_count > 0, "snapshot contains no articles")
    return BioasqMeasurement(
        article_count=article_count,
        mesh_assignment_count=assignment_count,
        distinct_mesh_label_count=len(mesh_labels),
        publication_year_min=int(publication_year_min),
        publication_year_max=int(publication_year_max),
        articles_without_mesh_labels=empty_mesh_count,
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
        container_metadata = container
    measured = measure_snapshot(path, mesh_path=mesh_path)
    declared = _declared_snapshot()
    declared_match = (
        measured.article_count == declared["article_count"]
        and measured.distinct_mesh_label_count == declared["mesh_label_count"]
        and measured.publication_year_min >= 1950
        and measured.publication_year_max <= declared["version_year"]
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
        "measured": asdict(measured),
        "declared_comparison": {
            "article_count": declared["article_count"],
            "mesh_label_count": declared["mesh_label_count"],
            "publication_scope": declared["publication_scope"],
            "matches_published_aggregate_scope": declared_match,
        },
        "mesh_vocabulary": expected_mesh,
        "limitations": [
            "This secondary BioASQ corpus is not the complete 2013 NLM baseline and cannot satisfy the original four-release source gate.",
            "Matching published aggregate counts does not establish PMID-by-PMID completeness or whether meshMajor contains only major headings versus all assigned descriptors.",
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
