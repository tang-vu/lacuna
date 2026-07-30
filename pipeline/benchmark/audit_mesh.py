"""Search pinned production-year MeSH descriptors for candidate mappings.

The command verifies the local archive against ``benchmarks/v3/sources.json`` before returning
matches. A vocabulary match is mapping evidence only; it does not substitute for historical
citation records and does not make a benchmark case period-appropriate.

Run:
    python -m pipeline.benchmark.audit_mesh 2012 "NF-kappa B" "Adenoma"
"""

from __future__ import annotations

import argparse
import gzip
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from xml.etree import ElementTree

from pipeline.benchmark.pin_mesh import inspect_descriptor_archive
from pipeline.benchmark.validate_sources import SOURCES_PATH
from pipeline.paths import MESH_CACHE_DIR


@dataclass(frozen=True)
class DescriptorHit:
    query: str
    descriptor_ui: str
    descriptor_label: str
    matched_term: str
    match_basis: str


def _normalise(value: str) -> str:
    return " ".join(value.casefold().split())


def find_descriptors(path: Path, queries: list[str]) -> list[DescriptorHit]:
    wanted = {_normalise(query): query for query in queries}
    hits: list[DescriptorHit] = []
    with gzip.open(path, "rb") as stream:
        for _, element in ElementTree.iterparse(stream, events=("end",)):
            if element.tag.rsplit("}", 1)[-1] != "DescriptorRecord":
                continue
            descriptor_ui = element.findtext("./DescriptorUI") or ""
            descriptor_label = element.findtext("./DescriptorName/String") or ""
            values = [("descriptor_label", descriptor_label)]
            values.extend(
                ("entry_term", term.text or "") for term in element.findall(".//Term/String")
            )
            matched: set[str] = set()
            for basis, value in values:
                normalised = _normalise(value)
                if normalised in wanted and normalised not in matched:
                    hits.append(
                        DescriptorHit(
                            query=wanted[normalised],
                            descriptor_ui=descriptor_ui,
                            descriptor_label=descriptor_label,
                            matched_term=value,
                            match_basis=basis,
                        )
                    )
                    matched.add(normalised)
            element.clear()
    return hits


def pinned_file(year: int, sources_path: Path = SOURCES_PATH) -> dict:
    payload = json.loads(sources_path.read_text(encoding="utf-8"))
    vocabulary = next(
        source
        for source in payload["sources"]
        if source["kind"] == "historical_vocabulary"
    )
    for item in vocabulary.get("files", []):
        if item.get("year") == year:
            return item
    raise ValueError(f"production-year MeSH {year} is not pinned")


def audit_mappings(
    year: int,
    queries: list[str],
    *,
    cache_dir: Path = MESH_CACHE_DIR,
    sources_path: Path = SOURCES_PATH,
) -> dict:
    expected = pinned_file(year, sources_path)
    path = cache_dir / f"desc{year}.gz"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} is missing; run `python -m pipeline.benchmark.pin_mesh {year}` first"
        )
    sha256, size, descriptor_count = inspect_descriptor_archive(path)
    if sha256 != expected["sha256"]:
        raise ValueError(f"desc{year}.gz checksum differs from the reviewed source contract")
    if size != expected["bytes"] or descriptor_count != expected["descriptor_count"]:
        raise ValueError(f"desc{year}.gz measured metadata differs from the source contract")

    hits = find_descriptors(path, queries)
    matched_queries = {hit.query for hit in hits}
    return {
        "schema_version": 1,
        "mapping_basis": "pinned_production_year_mesh",
        "vocabulary_year": year,
        "source": {
            "url": expected["url"],
            "sha256": expected["sha256"],
            "bytes": size,
            "descriptor_count": descriptor_count,
        },
        "hits": [asdict(hit) for hit in hits],
        "unmatched_queries": [query for query in queries if query not in matched_queries],
        "limitation": (
            "Vocabulary matches do not establish historical record assignments and cannot by "
            "themselves satisfy the period-appropriate benchmark gate."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("year", type=int)
    parser.add_argument("queries", nargs="+")
    args = parser.parse_args()
    print(json.dumps(audit_mappings(args.year, args.queries), indent=1))


if __name__ == "__main__":
    main()
