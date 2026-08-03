"""Build and validate a metric-blind review queue for v3 negative controls.

The generated entries are proposals, not benchmark cases. The sampler reads only pinned MeSH
vocabulary structure and a frozen hash seed; it never reads a lacuna score, rank, co-occurrence
count, or computed-gap artifact.

Run:
    python -m pipeline.benchmark.negative_controls --build
    python -m pipeline.benchmark.negative_controls
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from itertools import combinations
from pathlib import Path
from xml.etree import ElementTree

from pipeline.benchmark.audit_mesh import pinned_file
from pipeline.benchmark.metric_blind import find_forbidden_fields
from pipeline.benchmark.pin_mesh import inspect_descriptor_archive
from pipeline.benchmark.validate_sources import SOURCES_PATH
from pipeline.paths import ARTIFACTS_DIR, MESH_CACHE_DIR, REPO_ROOT
from pipeline.provenance import sha256_payload

PROTOCOL_PATH = REPO_ROOT / "benchmarks" / "v3" / "negative-selection.json"
OUTPUT_PATH = ARTIFACTS_DIR / "negative-candidates.json"
KINDS = ("hard_negative", "distant_negative")
SPLITS = ("development", "heldout")
DESCRIPTOR_UI = re.compile(r"^D\d{6}$")
TREE_NUMBER = re.compile(r"^[A-Z]\d{2}(?:\.\d{3}){2,}$")
EXPECTED_WARNING = (
    "Generated negative candidates are metric-blind review proposals, not accepted benchmark "
    "cases or evidence that a relationship is absent."
)
MAPPING_BASIS = "pinned_production_year_vocabulary_candidate"
REVIEW_REQUIRED = [
    "Check the negative rationale without inspecting any lacuna metric output.",
    "Reject or replace generic, polysemous, or substantively related concepts.",
    "Keep this proposal at zero readiness until it is accepted into cases.json.",
]


class NegativeControlError(ValueError):
    pass


@dataclass(frozen=True)
class Descriptor:
    ui: str
    label: str
    tree_number: str

    @property
    def branch(self) -> str:
        return self.tree_number[0]

    @property
    def parent(self) -> str:
        return self.tree_number.rsplit(".", 1)[0]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise NegativeControlError(message)


def _hash(seed: str, *parts: str) -> str:
    value = "|".join((seed, *parts)).encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def load_protocol(path: Path = PROTOCOL_PATH) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    _require(payload.get("schema_version") == 1, "unsupported negative protocol schema")
    _require(payload.get("status") == "frozen_before_v3_metric", "protocol is not frozen")
    _require(payload.get("metric_blind") is True, "protocol must remain metric blind")
    _require(
        payload.get("readiness_contribution")
        == "zero_until_human_adjudication_and_case_acceptance",
        "generated queue must contribute zero readiness",
    )
    try:
        frozen_on = date.fromisoformat(str(payload.get("frozen_on")))
    except ValueError as exc:
        raise NegativeControlError("protocol frozen_on must be YYYY-MM-DD") from exc
    _require(frozen_on.isoformat() == "2026-07-31", "protocol freeze date changed")
    years = payload.get("source_vocabulary_years")
    _require(years == [2012, 2013], "source vocabulary years are frozen to 2012 and 2013")
    _require(
        payload.get("seed") == "lacuna-v3-negative-controls-2026-07-31",
        "negative-control seed changed",
    )
    _require(
        payload.get("common_descriptor_rule")
        == {
            "descriptor_class": "1",
            "require_exactly_one_tree_number": True,
            "minimum_tree_depth": 3,
            "excluded_top_level_branches": ["V", "Z"],
        },
        "common descriptor rule changed",
    )
    hard = payload.get("hard_negative", {})
    _require(
        hard.get("allowed_top_level_branches") == list("ABCDEFG"),
        "hard branches changed",
    )
    _require(hard.get("minimum_sibling_group_size") == 2, "hard group minimum changed")
    _require(hard.get("maximum_sibling_group_size") == 12, "hard group maximum changed")
    _require(hard.get("pairs_per_year") == 4, "hard pairs per year changed")
    _require(
        hard.get("selection")
        == "hash_sort_all_eligible_pairs_then_greedily_take_pairs_without_reusing_descriptors",
        "hard selection method changed",
    )
    distant = payload.get("distant_negative", {})
    _require(distant.get("pairs_per_stratum_per_year") == 1, "distant sample size changed")
    _require(
        distant.get("selection")
        == "independently_hash_sort_each_branch_with_stratum_specific_salts_then_take_the_first_unused_descriptor",
        "distant selection method changed",
    )
    split_assignment = payload.get("split_assignment", {})
    _require(
        split_assignment.get("method")
        == "alternate_within_each_year_and_kind_after_deterministic_selection"
        and split_assignment.get("first_split") == "development",
        "split assignment changed",
    )
    totals = split_assignment.get("required_totals_per_kind")
    _require(totals == {"development": 4, "heldout": 4}, "split totals changed")
    strata = payload.get("distant_negative", {}).get("branch_strata")
    _require(
        strata == [["A", "J"], ["B", "F"], ["C", "H"], ["D", "I"]],
        "distant branch strata changed",
    )
    _require(
        payload.get("cutoff_assignment") == "release_year_minus_one_on_december_31",
        "cutoff assignment changed",
    )
    review = payload.get("review_policy", {})
    _require(
        all(review.get(field) is True for field in (
            "generated_entries_are_proposals",
            "acceptance_requires_public_metric_blind_negative_rationale",
            "absence_of_academic_cooccurrence_is_not_evidence_of_absent_human_knowledge",
            "metric_scores_ranks_and_percentiles_are_forbidden",
        )),
        "negative review policy changed",
    )
    _require(not find_forbidden_fields(payload), "protocol contains metric output fields")
    return payload


def read_descriptors(path: Path, protocol: dict) -> tuple[Descriptor, ...]:
    """Read descriptors eligible under the frozen, vocabulary-only sampling rule."""
    common = protocol["common_descriptor_rule"]
    excluded = set(common["excluded_top_level_branches"])
    minimum_depth = common["minimum_tree_depth"]
    descriptors: list[Descriptor] = []
    with gzip.open(path, "rb") as stream:
        for _, element in ElementTree.iterparse(stream, events=("end",)):
            if element.tag.rsplit("}", 1)[-1] != "DescriptorRecord":
                continue
            if element.attrib.get("DescriptorClass") != common["descriptor_class"]:
                element.clear()
                continue
            ui = element.findtext("./DescriptorUI") or ""
            label = element.findtext("./DescriptorName/String") or ""
            trees = [
                node.text or ""
                for node in element.findall("./TreeNumberList/TreeNumber")
                if node.text
            ]
            if (
                DESCRIPTOR_UI.fullmatch(ui)
                and label
                and len(trees) == 1
                and len(trees[0].split(".")) >= minimum_depth
                and trees[0][0] not in excluded
            ):
                descriptors.append(Descriptor(ui=ui, label=label, tree_number=trees[0]))
            element.clear()
    return tuple(sorted(descriptors, key=lambda item: item.ui))


def _hard_pairs(
    descriptors: tuple[Descriptor, ...], protocol: dict, year: int
) -> list[tuple[Descriptor, Descriptor, dict]]:
    rule = protocol["hard_negative"]
    groups: dict[str, list[Descriptor]] = defaultdict(list)
    allowed = set(rule["allowed_top_level_branches"])
    for item in descriptors:
        if item.branch in allowed:
            groups[item.parent].append(item)
    candidates = []
    for parent, siblings in groups.items():
        if not rule["minimum_sibling_group_size"] <= len(siblings) <= rule["maximum_sibling_group_size"]:
            continue
        for left, right in combinations(sorted(siblings, key=lambda item: item.ui), 2):
            candidates.append(
                (
                    _hash(protocol["seed"], "hard", str(year), left.ui, right.ui),
                    left,
                    right,
                    {"shared_parent": parent, "sibling_group_size": len(siblings)},
                )
            )
    selected = []
    used: set[str] = set()
    for _, left, right, evidence in sorted(candidates):
        if left.ui in used or right.ui in used:
            continue
        selected.append((left, right, evidence))
        used.update((left.ui, right.ui))
        if len(selected) == rule["pairs_per_year"]:
            break
    _require(len(selected) == rule["pairs_per_year"], f"{year}: too few hard pairs")
    return selected


def _first_unused(
    descriptors: list[Descriptor], seed: str, salt: str, used: set[str]
) -> Descriptor:
    for item in sorted(descriptors, key=lambda value: _hash(seed, salt, value.ui)):
        if item.ui not in used:
            return item
    raise NegativeControlError(f"no unused descriptor for {salt}")


def _distant_pairs(
    descriptors: tuple[Descriptor, ...], protocol: dict, year: int
) -> list[tuple[Descriptor, Descriptor, dict]]:
    by_branch: dict[str, list[Descriptor]] = defaultdict(list)
    for item in descriptors:
        by_branch[item.branch].append(item)
    selected = []
    used: set[str] = set()
    for index, (left_branch, right_branch) in enumerate(
        protocol["distant_negative"]["branch_strata"]
    ):
        left = _first_unused(
            by_branch[left_branch], protocol["seed"], f"{year}:{index}:left", used
        )
        used.add(left.ui)
        right = _first_unused(
            by_branch[right_branch], protocol["seed"], f"{year}:{index}:right", used
        )
        used.add(right.ui)
        selected.append(
            (
                left,
                right,
                {"branch_stratum": [left_branch, right_branch]},
            )
        )
    return selected


def _candidate(
    kind: str,
    year: int,
    index: int,
    left: Descriptor,
    right: Descriptor,
    selection_evidence: dict,
) -> dict:
    split = SPLITS[index % 2]
    prefix = "hard" if kind == "hard_negative" else "distant"
    return {
        "id": f"generated-{prefix}-{year}-{index + 1:02d}-{left.ui.lower()}-{right.ui.lower()}",
        "kind": kind,
        "status": "proposed",
        "proposed_split": split,
        "selection_stage": "pre_metric",
        "cutoff": f"{year - 1}-12-31",
        "baseline_release_year": year,
        "mapping_basis": MAPPING_BASIS,
        "concepts": {
            "a": {
                "descriptor_ui": left.ui,
                "descriptor_label": left.label,
                "tree_number": left.tree_number,
            },
            "c": {
                "descriptor_ui": right.ui,
                "descriptor_label": right.label,
                "tree_number": right.tree_number,
            },
        },
        "selection_evidence": selection_evidence,
        "negative_rationale": (
            "Ontology-adjacent MeSH siblings are a declared hard confounder, not evidence of a "
            "knowledge gap."
            if kind == "hard_negative"
            else "The fixed cross-branch stratum proposes semantic distance for blinded review; "
            "it does not establish that no relationship or non-academic knowledge exists."
        ),
        "review_required": REVIEW_REQUIRED,
    }


def build_queue(
    descriptor_sets: dict[int, tuple[Descriptor, ...]],
    protocol: dict,
    source_files: dict[int, dict],
) -> dict:
    candidates = []
    for year in protocol["source_vocabulary_years"]:
        descriptors = descriptor_sets[year]
        for kind, selected in (
            ("hard_negative", _hard_pairs(descriptors, protocol, year)),
            ("distant_negative", _distant_pairs(descriptors, protocol, year)),
        ):
            for index, (left, right, evidence) in enumerate(selected):
                candidates.append(_candidate(kind, year, index, left, right, evidence))
    candidates.sort(key=lambda item: (item["kind"], item["baseline_release_year"], item["id"]))
    return {
        "schema_version": 1,
        "status": "generated_review_queue",
        "readiness_contribution": 0,
        "warning": EXPECTED_WARNING,
        "protocol": {
            "path": PROTOCOL_PATH.relative_to(REPO_ROOT).as_posix(),
            "sha256": sha256_payload(protocol),
            "canonicalisation": "canonical-json-v1",
        },
        "sources": [source_files[year] for year in protocol["source_vocabulary_years"]],
        "candidates": candidates,
    }


def build_from_pinned_archives(
    protocol_path: Path = PROTOCOL_PATH,
    cache_dir: Path = MESH_CACHE_DIR,
) -> dict:
    protocol = load_protocol(protocol_path)
    descriptor_sets = {}
    source_files = {}
    for year in protocol["source_vocabulary_years"]:
        expected = pinned_file(year)
        path = cache_dir / f"desc{year}.gz"
        if not path.is_file():
            raise FileNotFoundError(f"missing {path}; run pipeline.benchmark.pin_mesh first")
        sha256, size, descriptor_count = inspect_descriptor_archive(path)
        _require(sha256 == expected["sha256"], f"{year}: vocabulary checksum mismatch")
        _require(
            size == expected["bytes"] and descriptor_count == expected["descriptor_count"],
            f"{year}: vocabulary metadata mismatch",
        )
        descriptor_sets[year] = read_descriptors(path, protocol)
        source_files[year] = {
            "year": year,
            "url": expected["url"],
            "sha256": sha256,
            "bytes": size,
            "descriptor_count": descriptor_count,
        }
    return build_queue(descriptor_sets, protocol, source_files)


def audit_queue(path: Path = OUTPUT_PATH, protocol_path: Path = PROTOCOL_PATH) -> dict:
    protocol = load_protocol(protocol_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    _require(payload.get("schema_version") == 1, "unsupported negative queue schema")
    _require(payload.get("status") == "generated_review_queue", "wrong queue status")
    _require(payload.get("readiness_contribution") == 0, "queue must contribute zero readiness")
    _require(payload.get("warning") == EXPECTED_WARNING, "negative queue warning changed")
    _require(
        payload.get("protocol", {}).get("sha256") == sha256_payload(protocol),
        "negative queue is stale for its protocol",
    )
    _require(
        payload.get("protocol", {}).get("path")
        == protocol_path.relative_to(REPO_ROOT).as_posix()
        and payload.get("protocol", {}).get("canonicalisation") == "canonical-json-v1",
        "negative queue protocol identity is malformed",
    )
    _require(not find_forbidden_fields(payload), "negative queue contains metric output fields")

    expected_sources = {
        year: pinned_file(year) for year in protocol["source_vocabulary_years"]
    }
    sources = payload.get("sources")
    _require(isinstance(sources, list) and len(sources) == 2, "queue needs two sources")
    _require(
        {source.get("year") for source in sources} == set(expected_sources),
        "queue source years differ from the protocol",
    )
    for source in sources:
        expected = expected_sources.get(source.get("year"))
        _require(expected is not None, "queue has an unexpected source year")
        for field in ("url", "sha256", "bytes", "descriptor_count"):
            _require(source.get(field) == expected[field], f"source {field} differs from pin")

    candidates = payload.get("candidates")
    _require(isinstance(candidates, list), "queue candidates must be a list")
    _require(
        candidates
        == sorted(
            candidates,
            key=lambda item: (
                item.get("kind"),
                item.get("baseline_release_year"),
                item.get("id"),
            ),
        ),
        "negative queue ordering changed",
    )
    counts = {kind: 0 for kind in KINDS}
    heldout = {kind: 0 for kind in KINDS}
    bucket_counts = {
        (kind, year, split): 0
        for kind in KINDS
        for year in expected_sources
        for split in SPLITS
    }
    used_by_bucket: dict[tuple[str, int], set[str]] = defaultdict(set)
    seen_ids: set[str] = set()
    seen_pairs: set[tuple[str, str, int]] = set()
    strata = {tuple(item) for item in protocol["distant_negative"]["branch_strata"]}
    for item in candidates:
        _require(isinstance(item, dict), "malformed negative candidate")
        candidate_id = item.get("id")
        _require(isinstance(candidate_id, str) and candidate_id not in seen_ids, "duplicate id")
        seen_ids.add(candidate_id)
        kind = item.get("kind")
        split = item.get("proposed_split")
        _require(kind in KINDS and split in SPLITS, f"{candidate_id}: invalid kind or split")
        _require(item.get("status") == "proposed", f"{candidate_id}: generated item accepted")
        _require(item.get("selection_stage") == "pre_metric", f"{candidate_id}: not pre-metric")
        _require(item.get("mapping_basis") == MAPPING_BASIS, f"{candidate_id}: wrong mapping basis")
        year = item.get("baseline_release_year")
        _require(year in expected_sources, f"{candidate_id}: invalid baseline year")
        _require(item.get("cutoff") == f"{year - 1}-12-31", f"{candidate_id}: wrong cutoff")
        concepts = item.get("concepts")
        _require(
            isinstance(concepts, dict) and set(concepts) == {"a", "c"},
            f"{candidate_id}: bad concepts",
        )
        left, right = concepts["a"], concepts["c"]
        for concept in (left, right):
            _require(
                isinstance(concept, dict)
                and set(concept) == {"descriptor_ui", "descriptor_label", "tree_number"}
                and DESCRIPTOR_UI.fullmatch(str(concept.get("descriptor_ui", ""))) is not None
                and bool(concept.get("descriptor_label"))
                and TREE_NUMBER.fullmatch(str(concept.get("tree_number", ""))) is not None,
                f"{candidate_id}: malformed descriptor",
            )
        pair = tuple(sorted((left["descriptor_ui"], right["descriptor_ui"]))) + (year,)
        _require(pair not in seen_pairs, f"{candidate_id}: duplicate pair")
        seen_pairs.add(pair)
        bucket = (kind, year)
        _require(
            left["descriptor_ui"] not in used_by_bucket[bucket]
            and right["descriptor_ui"] not in used_by_bucket[bucket],
            f"{candidate_id}: descriptor reused within selection bucket",
        )
        used_by_bucket[bucket].update((left["descriptor_ui"], right["descriptor_ui"]))
        selection_evidence = item.get("selection_evidence")
        if kind == "hard_negative":
            parent = left["tree_number"].rsplit(".", 1)[0]
            _require(
                parent == right["tree_number"].rsplit(".", 1)[0],
                f"{candidate_id}: hard pair is not sibling",
            )
            _require(
                isinstance(selection_evidence, dict)
                and set(selection_evidence) == {"shared_parent", "sibling_group_size"}
                and selection_evidence["shared_parent"] == parent
                and 2 <= selection_evidence["sibling_group_size"] <= 12,
                f"{candidate_id}: malformed hard selection evidence",
            )
        else:
            branch_stratum = [left["tree_number"][0], right["tree_number"][0]]
            _require(
                tuple(branch_stratum) in strata,
                f"{candidate_id}: distant pair is outside frozen strata",
            )
            _require(
                selection_evidence == {"branch_stratum": branch_stratum},
                f"{candidate_id}: malformed distant selection evidence",
            )
        _require(bool(item.get("negative_rationale")), f"{candidate_id}: missing rationale")
        _require(item.get("review_required") == REVIEW_REQUIRED, f"{candidate_id}: review gate changed")
        counts[kind] += 1
        bucket_counts[(kind, year, split)] += 1
        if split == "heldout":
            heldout[kind] += 1
    _require(counts == {kind: 8 for kind in KINDS}, f"wrong queue counts: {counts}")
    _require(heldout == {kind: 4 for kind in KINDS}, f"wrong held-out counts: {heldout}")
    _require(
        all(count == 2 for count in bucket_counts.values()),
        f"unbalanced year/kind/split buckets: {bucket_counts}",
    )
    return {"counts": counts, "heldout_counts": heldout, "readiness_contribution": 0}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true")
    args = parser.parse_args()
    if args.build:
        payload = build_from_pinned_archives()
        OUTPUT_PATH.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        print(f"wrote {OUTPUT_PATH.relative_to(REPO_ROOT).as_posix()}")
    audit = audit_queue()
    print(
        "negative review queue: "
        + ", ".join(f"{kind}={count}" for kind, count in audit["counts"].items())
    )
    print("readiness contribution: 0 (human adjudication required)")


if __name__ == "__main__":
    main()
