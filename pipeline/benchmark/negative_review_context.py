"""Build and validate pinned MeSH context for metric-blind negative-control review.

This artifact is a generated review aid. It extracts vocabulary definitions, entry terms, tree
paths, and hard-negative parent labels from checksum-verified production-year MeSH archives. It
does not adjudicate proposals and contributes zero benchmark readiness.

Run:
    python -m pipeline.benchmark.negative_review_context --build
    python -m pipeline.benchmark.negative_review_context
"""

from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path
from xml.etree import ElementTree

from pipeline.benchmark.audit_mesh import pinned_file
from pipeline.benchmark.metric_blind import find_forbidden_fields
from pipeline.benchmark.negative_controls import OUTPUT_PATH as QUEUE_PATH, audit_queue
from pipeline.benchmark.pin_mesh import inspect_descriptor_archive
from pipeline.benchmark.validate_sources import SOURCES_PATH
from pipeline.paths import ARTIFACTS_DIR, MESH_CACHE_DIR, REPO_ROOT
from pipeline.provenance import sha256_payload

OUTPUT_PATH = ARTIFACTS_DIR / "negative-review-context.json"
STATUS = "generated_review_aid"
WARNING = (
    "Pinned vocabulary context is a generated review aid, not human adjudication, evidence that "
    "a relationship is absent, or benchmark readiness."
)


class NegativeReviewContextError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise NegativeReviewContextError(message)


def _unique_text(nodes: list[ElementTree.Element]) -> list[str]:
    return sorted({(node.text or "").strip() for node in nodes if (node.text or "").strip()})


def read_context(
    path: Path,
    *,
    descriptor_uis: set[str],
    parent_trees: set[str],
) -> tuple[dict[str, dict], dict[str, dict]]:
    """Extract only requested descriptor records while streaming the vocabulary archive."""
    by_ui: dict[str, dict] = {}
    by_tree: dict[str, dict] = {}
    with gzip.open(path, "rb") as stream:
        for _, element in ElementTree.iterparse(stream, events=("end",)):
            if element.tag.rsplit("}", 1)[-1] != "DescriptorRecord":
                continue
            ui = element.findtext("./DescriptorUI") or ""
            label = element.findtext("./DescriptorName/String") or ""
            tree_numbers = _unique_text(element.findall("./TreeNumberList/TreeNumber"))
            if ui in descriptor_uis:
                terms = _unique_text(element.findall(".//Term/String"))
                by_ui[ui] = {
                    "descriptor_ui": ui,
                    "descriptor_label": label,
                    "tree_numbers": tree_numbers,
                    "entry_terms": [term for term in terms if term != label],
                    "scope_notes": _unique_text(element.findall(".//ScopeNote")),
                    "annotations": _unique_text(element.findall("./Annotation")),
                }
            for tree in parent_trees.intersection(tree_numbers):
                by_tree[tree] = {
                    "descriptor_ui": ui,
                    "descriptor_label": label,
                    "tree_number": tree,
                }
            element.clear()
    return by_ui, by_tree


def build_review_context(
    *,
    queue_path: Path = QUEUE_PATH,
    cache_dir: Path = MESH_CACHE_DIR,
    sources_path: Path = SOURCES_PATH,
) -> dict:
    audit_queue(queue_path)
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    by_year: dict[int, list[dict]] = {}
    for candidate in queue["candidates"]:
        by_year.setdefault(candidate["baseline_release_year"], []).append(candidate)

    source_entries = []
    contexts: dict[int, tuple[dict[str, dict], dict[str, dict]]] = {}
    for year, candidates in sorted(by_year.items()):
        expected = pinned_file(year, sources_path)
        archive = cache_dir / f"desc{year}.gz"
        _require(archive.is_file(), f"missing pinned vocabulary archive: {archive}")
        sha256, size, descriptor_count = inspect_descriptor_archive(archive)
        _require(sha256 == expected["sha256"], f"{year}: vocabulary checksum mismatch")
        _require(
            size == expected["bytes"] and descriptor_count == expected["descriptor_count"],
            f"{year}: vocabulary measured metadata mismatch",
        )
        wanted_uis = {
            candidate["concepts"][role]["descriptor_ui"]
            for candidate in candidates
            for role in ("a", "c")
        }
        parent_trees = {
            candidate["selection_evidence"]["shared_parent"]
            for candidate in candidates
            if candidate["kind"] == "hard_negative"
        }
        contexts[year] = read_context(
            archive,
            descriptor_uis=wanted_uis,
            parent_trees=parent_trees,
        )
        source_entries.append(
            {
                "year": year,
                "url": expected["url"],
                "sha256": sha256,
                "bytes": size,
                "descriptor_count": descriptor_count,
            }
        )

    entries = []
    for candidate in queue["candidates"]:
        descriptor_context, tree_context = contexts[candidate["baseline_release_year"]]
        concepts = {}
        for role in ("a", "c"):
            proposal = candidate["concepts"][role]
            context = descriptor_context.get(proposal["descriptor_ui"])
            _require(context is not None, f"{candidate['id']}.{role}: descriptor context missing")
            _require(
                context["descriptor_label"] == proposal["descriptor_label"]
                and proposal["tree_number"] in context["tree_numbers"],
                f"{candidate['id']}.{role}: context differs from frozen proposal",
            )
            concepts[role] = context
        entry = {"candidate_id": candidate["id"], "concepts": concepts}
        if candidate["kind"] == "hard_negative":
            parent_tree = candidate["selection_evidence"]["shared_parent"]
            parent = tree_context.get(parent_tree)
            _require(parent is not None, f"{candidate['id']}: shared-parent context missing")
            entry["shared_parent"] = parent
        entries.append(entry)

    return {
        "schema_version": 1,
        "status": STATUS,
        "readiness_contribution": 0,
        "warning": WARNING,
        "queue": {
            "path": queue_path.relative_to(REPO_ROOT).as_posix(),
            "sha256": sha256_payload(queue),
            "canonicalisation": "canonical-json-v1",
        },
        "sources": source_entries,
        "entries": entries,
    }


def _validate_text_list(value: object, context: str) -> None:
    _require(isinstance(value, list), f"{context}: expected a list")
    _require(
        all(isinstance(item, str) and item.strip() for item in value),
        f"{context}: entries must be non-empty strings",
    )
    _require(value == sorted(set(value)), f"{context}: entries must be sorted and unique")


def audit_review_context(
    path: Path = OUTPUT_PATH,
    *,
    queue_path: Path = QUEUE_PATH,
    sources_path: Path = SOURCES_PATH,
) -> dict:
    audit_queue(queue_path)
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    payload = json.loads(path.read_text(encoding="utf-8"))
    _require(payload.get("schema_version") == 1, "unsupported review-context schema")
    _require(payload.get("status") == STATUS, "review context has the wrong status")
    _require(payload.get("readiness_contribution") == 0, "review context cannot add readiness")
    _require(payload.get("warning") == WARNING, "review-context warning changed")
    _require(not find_forbidden_fields(payload), "review context contains metric output fields")
    _require(
        payload.get("queue")
        == {
            "path": queue_path.relative_to(REPO_ROOT).as_posix(),
            "sha256": sha256_payload(queue),
            "canonicalisation": "canonical-json-v1",
        },
        "review context does not pin the frozen queue",
    )

    expected_sources = {
        item["year"]: item
        for item in (
            pinned_file(year, sources_path)
            for year in sorted({item["baseline_release_year"] for item in queue["candidates"]})
        )
    }
    sources = payload.get("sources")
    _require(isinstance(sources, list), "review context needs sources")
    _require(
        {
            item.get("year"): item
            for item in sources
            if isinstance(item, dict)
        }
        == expected_sources,
        "review-context sources differ from pinned vocabularies",
    )

    candidates = {item["id"]: item for item in queue["candidates"]}
    entries = payload.get("entries")
    _require(isinstance(entries, list), "review context needs entries")
    _require(
        [entry.get("candidate_id") for entry in entries if isinstance(entry, dict)]
        == list(candidates),
        "review-context entries differ from the frozen queue order",
    )
    for entry in entries:
        candidate = candidates[entry["candidate_id"]]
        concepts = entry.get("concepts")
        _require(
            isinstance(concepts, dict) and set(concepts) == {"a", "c"},
            f"{candidate['id']}: context concepts must contain a and c",
        )
        for role in ("a", "c"):
            context = concepts[role]
            proposal = candidate["concepts"][role]
            _require(
                context.get("descriptor_ui") == proposal["descriptor_ui"]
                and context.get("descriptor_label") == proposal["descriptor_label"],
                f"{candidate['id']}.{role}: descriptor context drift",
            )
            _validate_text_list(context.get("tree_numbers"), f"{candidate['id']}.{role}.trees")
            _require(
                proposal["tree_number"] in context["tree_numbers"],
                f"{candidate['id']}.{role}: selected tree missing from context",
            )
            for field in ("entry_terms", "scope_notes", "annotations"):
                _validate_text_list(context.get(field), f"{candidate['id']}.{role}.{field}")
        if candidate["kind"] == "hard_negative":
            parent = entry.get("shared_parent")
            _require(isinstance(parent, dict), f"{candidate['id']}: parent context missing")
            _require(
                parent.get("tree_number") == candidate["selection_evidence"]["shared_parent"]
                and bool(parent.get("descriptor_ui"))
                and bool(parent.get("descriptor_label")),
                f"{candidate['id']}: parent context drift",
            )
        else:
            _require("shared_parent" not in entry, f"{candidate['id']}: unexpected parent context")
    return {
        "entries": len(entries),
        "sources": len(sources),
        "readiness_contribution": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true")
    args = parser.parse_args()
    if args.build:
        payload = build_review_context()
        OUTPUT_PATH.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        print(f"wrote {OUTPUT_PATH.relative_to(REPO_ROOT).as_posix()}")
    audit = audit_review_context()
    print("negative review context: 16 generated aids · 0 readiness")


if __name__ == "__main__":
    main()

