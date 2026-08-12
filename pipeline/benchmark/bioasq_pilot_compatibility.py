"""Measure the frozen BioASQ pilot's score-free source compatibility.

This module only counts descriptor support and exact article co-occurrence inside the pinned
secondary snapshot. It deliberately has no metric formula, candidate ordering, score, or rank.

Run a first measurement (the output path must not already exist):

    python -m pipeline.benchmark.bioasq_pilot_compatibility \
      data/medline-baseline/bioasq/PubMedWithMeSH.zip \
      --output benchmarks/v3/manifests/bioasq-pilot-compatibility.json

Validate the committed manifest without rescanning the 5.47 GB transport:

    python -m pipeline.benchmark.bioasq_pilot_compatibility --validate

Replay the full source measurement and require byte-equivalent JSON:

    python -m pipeline.benchmark.bioasq_pilot_compatibility \
      data/medline-baseline/bioasq/PubMedWithMeSH.zip --verify
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

from pipeline.benchmark.bioasq_snapshot import (
    descriptor_label_index,
    iter_articles,
    open_snapshot_text,
    validate_article,
)
from pipeline.benchmark.metric_blind import find_forbidden_fields
from pipeline.benchmark.validate_bioasq_pilot import (
    PILOT_PATH,
    audit_bioasq_pilot,
)
from pipeline.paths import MEDLINE_BASELINE_DIR, MESH_CACHE_DIR, REPO_ROOT

MANIFEST_PATH = (
    REPO_ROOT / "benchmarks" / "v3" / "manifests" / "bioasq-pilot-compatibility.json"
)
SNAPSHOT_PATH = MEDLINE_BASELINE_DIR / "bioasq" / "PubMedWithMeSH.zip"
MESH_PATH = MESH_CACHE_DIR / "desc2013.gz"
CUTOFF_YEARS = (2006, 2010, 2011, 2012)
SUPPORT_THRESHOLDS = (5, 10, 20)
PRIMARY_SUPPORT = 10
COMPATIBLE_STATUS = "source_compatible_for_separately_frozen_formula_contract"
SENSITIVITY_BLOCKED_STATUS = "primary_source_compatible_but_sensitivity_20_unevaluable"


class BioasqCompatibilityError(ValueError):
    pass


@dataclass(frozen=True)
class CaseDefinition:
    id: str
    kind: str
    split: str
    cutoff: str
    label_scope: str
    endpoint_a: dict[str, str]
    target_c: dict[str, str]
    bridge_b: dict[str, str] | None = None


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BioasqCompatibilityError(message)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_reference(path: Path) -> dict[str, object]:
    return {
        "path": path.relative_to(REPO_ROOT).as_posix(),
        "sha256": _sha256_file(path),
    }


def _load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(payload, dict), f"{path}: expected a JSON object")
    return payload


def _resolve_reference(reference: object, context: str) -> Path:
    _require(isinstance(reference, dict), f"{context}: missing file reference")
    _require(set(reference) == {"path", "sha256"}, f"{context}: malformed file reference")
    relative = Path(str(reference["path"]))
    _require(not relative.is_absolute() and ".." not in relative.parts, f"{context}: unsafe path")
    path = REPO_ROOT / relative
    _require(path.is_file(), f"{context}: referenced file is missing")
    _require(_sha256_file(path) == reference["sha256"], f"{context}: checksum mismatch")
    return path


def _protocol_dependencies(protocol: dict) -> tuple[dict, dict, Path, Path]:
    inputs = protocol["inputs"]
    snapshot_manifest_path = _resolve_reference(inputs["snapshot_audit"], "snapshot audit")
    negative_queue_path = _resolve_reference(
        inputs["negative_candidate_queue"], "negative candidate queue"
    )
    return (
        _load_json(snapshot_manifest_path),
        _load_json(negative_queue_path),
        snapshot_manifest_path,
        negative_queue_path,
    )


def _case_definitions(protocol: dict, negative_queue: dict) -> list[CaseDefinition]:
    positive_scope = protocol["case_population"]["positives"]["label_scope"]
    cases = [
        CaseDefinition(
            id=item["id"],
            kind="source_labeled_positive",
            split=item["split"],
            cutoff=item["cutoff"],
            label_scope=positive_scope,
            endpoint_a=item["endpoint_a"],
            target_c=item["target_c"],
            bridge_b=item["bridge_b"],
        )
        for item in protocol["case_population"]["positives"]["cases"]
    ]
    control_scope = protocol["case_population"]["controls"]["label_scope"]
    for item in negative_queue["candidates"]:
        cases.append(
            CaseDefinition(
                id=item["id"],
                kind=item["kind"],
                split=item["proposed_split"],
                cutoff=item["cutoff"],
                label_scope=control_scope,
                endpoint_a={
                    "descriptor_ui": item["concepts"]["a"]["descriptor_ui"],
                    "descriptor_label": item["concepts"]["a"]["descriptor_label"],
                },
                target_c={
                    "descriptor_ui": item["concepts"]["c"]["descriptor_ui"],
                    "descriptor_label": item["concepts"]["c"]["descriptor_label"],
                },
            )
        )
    _require(len(cases) == 21, "frozen pilot must contain 21 cases")
    return cases


def _ordered_pair(left: str, right: str) -> tuple[str, str]:
    return (left, right) if left < right else (right, left)


def _required_pairs(cases: list[CaseDefinition]) -> set[tuple[str, str]]:
    pairs = {
        _ordered_pair(case.endpoint_a["descriptor_ui"], case.target_c["descriptor_ui"])
        for case in cases
    }
    for case in cases:
        if case.bridge_b is None:
            continue
        bridge_ui = case.bridge_b["descriptor_ui"]
        pairs.add(_ordered_pair(case.endpoint_a["descriptor_ui"], bridge_ui))
        pairs.add(_ordered_pair(bridge_ui, case.target_c["descriptor_ui"]))
    return pairs


def _bucket_index(publication_year: int) -> int | None:
    index = bisect.bisect_left(CUTOFF_YEARS, publication_year)
    return index if index < len(CUTOFF_YEARS) else None


def _cumulative_counters(
    buckets: list[Counter],
) -> dict[int, Counter]:
    running: Counter = Counter()
    cumulative: dict[int, Counter] = {}
    for cutoff, bucket in zip(CUTOFF_YEARS, buckets, strict=True):
        running.update(bucket)
        cumulative[cutoff] = running.copy()
    return cumulative


def _measure_snapshot(
    snapshot_path: Path,
    *,
    label_index: dict[str, str],
    required_pairs: set[tuple[str, str]],
) -> dict:
    support_buckets = [Counter() for _ in CUTOFF_YEARS]
    pair_buckets = [Counter() for _ in CUTOFF_YEARS]
    article_buckets = [0 for _ in CUTOFF_YEARS]
    monitored_uis = {ui for pair in required_pairs for ui in pair}
    raw_label_cache: dict[str, str] = {}
    observed_uis: set[str] = set()
    article_count = 0
    assignment_count = 0
    ignored_after_last_cutoff = 0
    container: dict | None = None

    with open_snapshot_text(snapshot_path) as (stream, opened_container):
        container = opened_container
        for article in iter_articles(stream):
            article_count += 1
            _pmid, year, assigned, _canonical, _raw_year = validate_article(
                article, article_count
            )
            _require(year is not None, f"article {article_count}: unparseable publication year")
            assignment_count += len(assigned)
            bucket_index = _bucket_index(year)
            if bucket_index is None:
                ignored_after_last_cutoff += 1
                continue

            article_uis: set[str] = set()
            for raw_label in assigned:
                ui = raw_label_cache.get(raw_label)
                if ui is None:
                    normalised = " ".join(raw_label.casefold().split())
                    ui = label_index.get(normalised, "")
                    _require(bool(ui), f"unknown MeSH 2013 label: {raw_label}")
                    raw_label_cache[raw_label] = ui
                article_uis.add(ui)
            _require(
                len(article_uis) == len(assigned),
                f"article {article_count}: duplicate descriptor assignments",
            )
            observed_uis.update(article_uis)
            support_buckets[bucket_index].update(article_uis)
            present_monitored = monitored_uis.intersection(article_uis)
            if len(present_monitored) >= 2:
                for left, right in combinations(sorted(present_monitored), 2):
                    pair = (left, right)
                    if pair in required_pairs:
                        pair_buckets[bucket_index][pair] += 1
            article_buckets[bucket_index] += 1

    _require(container is not None, "snapshot container was not opened")
    support = _cumulative_counters(support_buckets)
    pair_counts = _cumulative_counters(pair_buckets)
    cumulative_articles = []
    running_articles = 0
    for count in article_buckets:
        running_articles += count
        cumulative_articles.append(running_articles)
    return {
        "container": container,
        "article_count": article_count,
        "mesh_assignment_count": assignment_count,
        "distinct_descriptor_count_through_2012": len(observed_uis),
        "articles_after_last_cutoff": ignored_after_last_cutoff,
        "included_articles": dict(zip(CUTOFF_YEARS, cumulative_articles, strict=True)),
        "support": support,
        "pair_counts": pair_counts,
    }


def _support_eligibility(a_count: int, c_count: int) -> dict[str, dict[str, bool]]:
    return {
        str(threshold): {
            "endpoint_a_eligible": a_count >= threshold,
            "target_c_eligible": c_count >= threshold,
        }
        for threshold in SUPPORT_THRESHOLDS
    }


def _case_measurement(
    case: CaseDefinition,
    support: dict[int, Counter],
    pair_counts: dict[int, Counter],
) -> dict:
    cutoff_year = int(case.cutoff[:4])
    _require(cutoff_year in CUTOFF_YEARS, f"{case.id}: unexpected cutoff year")
    cutoff_support = support[cutoff_year]
    cutoff_pairs = pair_counts[cutoff_year]
    a_ui = case.endpoint_a["descriptor_ui"]
    c_ui = case.target_c["descriptor_ui"]
    a_count = cutoff_support[a_ui]
    c_count = cutoff_support[c_ui]
    payload = {
        "id": case.id,
        "kind": case.kind,
        "split": case.split,
        "cutoff": case.cutoff,
        "label_scope": case.label_scope,
        "endpoint_a": {**case.endpoint_a, "article_support": a_count},
        "target_c": {**case.target_c, "article_support": c_count},
        "direct_ac_article_count": cutoff_pairs[_ordered_pair(a_ui, c_ui)],
        "support_eligibility": _support_eligibility(a_count, c_count),
        "primary_source_compatible": a_count >= PRIMARY_SUPPORT and c_count >= PRIMARY_SUPPORT,
    }
    if case.bridge_b is not None:
        b_ui = case.bridge_b["descriptor_ui"]
        payload["named_bridge_b"] = {
            **case.bridge_b,
            "article_support": cutoff_support[b_ui],
            "ab_article_count": cutoff_pairs[_ordered_pair(a_ui, b_ui)],
            "bc_article_count": cutoff_pairs[_ordered_pair(b_ui, c_ui)],
        }
    return payload


def _source_decision(cases: list[dict], failure_outcome: str) -> dict:
    incompatible = [case["id"] for case in cases if not case["primary_source_compatible"]]
    compatible = not incompatible and len(cases) == 21
    heldout_cases = [case for case in cases if case["split"] == "heldout"]
    sensitivity_blockers = {
        str(threshold): [
            case["id"]
            for case in heldout_cases
            if not (
                case["support_eligibility"][str(threshold)]["endpoint_a_eligible"]
                and case["support_eligibility"][str(threshold)]["target_c_eligible"]
            )
        ]
        for threshold in SUPPORT_THRESHOLDS
    }
    sensitivity_evaluable = {
        threshold: not blockers for threshold, blockers in sensitivity_blockers.items()
    }
    frozen_rule_can_still_pass = compatible and all(sensitivity_evaluable.values())
    if not compatible:
        status = failure_outcome
        next_step = (
            "Report the predeclared inconclusive outcome; do not select a metric formula."
        )
    elif not frozen_rule_can_still_pass:
        status = SENSITIVITY_BLOCKED_STATUS
        next_step = (
            "Do not compute a metric under this pilot: its frozen held-out rule cannot earn a "
            "passing label. Preserve this result and freeze a separately named successor before "
            "any metric output if the experiment should continue."
        )
    else:
        status = COMPATIBLE_STATUS
        next_step = (
            "Freeze a separate checksum-pinned formula contract before any development output."
        )
    return {
        "status": status,
        "primary_source_gate_status": COMPATIBLE_STATUS if compatible else failure_outcome,
        "all_21_cases_primary_source_compatible": compatible,
        "primary_minimum_support_articles": PRIMARY_SUPPORT,
        "incompatible_case_ids": incompatible,
        "heldout_sensitivity_evaluable": sensitivity_evaluable,
        "heldout_sensitivity_blockers": sensitivity_blockers,
        "frozen_heldout_rule_can_still_pass": frozen_rule_can_still_pass,
        "metric_work_authorized_by_this_audit": frozen_rule_can_still_pass,
        "replacement_policy": (
            "No case may be dropped, replaced, or relabelled after this measurement."
        ),
        "next_allowed_step": next_step,
        "readiness_contribution": 0,
    }


def build_compatibility_payload(
    snapshot_path: Path,
    *,
    pilot_path: Path = PILOT_PATH,
    mesh_path: Path = MESH_PATH,
) -> dict:
    audit_bioasq_pilot(pilot_path)
    protocol = _load_json(pilot_path)
    snapshot_manifest, negative_queue, snapshot_manifest_path, negative_queue_path = (
        _protocol_dependencies(protocol)
    )
    _require(snapshot_path.is_file(), f"missing local BioASQ snapshot: {snapshot_path}")
    _require(mesh_path.is_file(), f"missing local MeSH 2013 archive: {mesh_path}")
    _require(
        _sha256_file(snapshot_path) == snapshot_manifest["input"]["sha256"]
        and snapshot_path.stat().st_size == snapshot_manifest["input"]["bytes"],
        "local BioASQ snapshot differs from the pinned transport",
    )
    mesh_reference = protocol["inputs"]["descriptor_vocabulary"]
    _require(
        _sha256_file(mesh_path) == mesh_reference["sha256"]
        and mesh_path.stat().st_size == mesh_reference["bytes"],
        "local MeSH 2013 archive differs from the pilot pin",
    )

    cases = _case_definitions(protocol, negative_queue)
    pairs = _required_pairs(cases)
    measured = _measure_snapshot(
        snapshot_path,
        label_index=descriptor_label_index(mesh_path),
        required_pairs=pairs,
    )
    _require(
        measured["article_count"] == snapshot_manifest["measured"]["article_count"]
        and measured["mesh_assignment_count"]
        == snapshot_manifest["measured"]["mesh_assignment_count"],
        "snapshot aggregate counts drifted during compatibility scan",
    )
    expected_container = snapshot_manifest["input"]["container"]
    _require(
        all(
            measured["container"].get(key) == value
            for key, value in expected_container.items()
            if key != "envelope"
        ),
        "snapshot container identity drifted during compatibility scan",
    )
    case_measurements = [
        _case_measurement(case, measured["support"], measured["pair_counts"])
        for case in cases
    ]
    universe_sizes = {
        str(cutoff): {
            str(threshold): sum(
                count >= threshold for count in measured["support"][cutoff].values()
            )
            for threshold in SUPPORT_THRESHOLDS
        }
        for cutoff in CUTOFF_YEARS
    }
    failure_outcome = protocol["source_compatibility_gate"]["failure_outcome"]
    decision = _source_decision(case_measurements, failure_outcome)
    payload = {
        "schema_version": 1,
        "status": decision["status"],
        "readiness_contribution": 0,
        "claim_boundary": (
            "Exact source support measurement inside the pinned BioASQ 2013 secondary snapshot; "
            "not a metric result, historical-baseline reconstruction, discovery validation, or "
            "evidence that generated controls are true negatives."
        ),
        "inputs": {
            "pilot_protocol": _file_reference(pilot_path),
            "snapshot_audit": _file_reference(snapshot_manifest_path),
            "snapshot_transport": {
                "sha256": snapshot_manifest["input"]["sha256"],
                "bytes": snapshot_manifest["input"]["bytes"],
                "container": expected_container,
            },
            "negative_candidate_queue": _file_reference(negative_queue_path),
            "descriptor_vocabulary": mesh_reference,
        },
        "transform": {
            "publication_cutoff": protocol["source_transform"]["publication_cutoff"],
            "descriptor_identity": protocol["source_transform"]["descriptor_identity"],
            "article_contribution": protocol["source_transform"]["article_contribution"],
            "cooccurrence_unit": protocol["source_transform"]["cooccurrence_unit"],
            "direct_endpoint_cooccurrences": protocol["source_transform"][
                "direct_endpoint_cooccurrences"
            ],
            "support_thresholds_articles": list(SUPPORT_THRESHOLDS),
            "cutoff_years": list(CUTOFF_YEARS),
            "source_query": (
                "No API query: stream every article in the checksum-pinned local snapshot and "
                "include it when its normalized publication year is at or before the case cutoff."
            ),
        },
        "measurement": {
            "count_scope": "exact_within_pinned_secondary_snapshot",
            "article_count_scanned": measured["article_count"],
            "mesh_assignment_count_scanned": measured["mesh_assignment_count"],
            "distinct_descriptor_count_through_2012": measured[
                "distinct_descriptor_count_through_2012"
            ],
            "articles_after_last_cutoff": measured["articles_after_last_cutoff"],
            "included_article_count_by_cutoff": {
                str(year): measured["included_articles"][year] for year in CUTOFF_YEARS
            },
            "support_eligible_descriptor_count_by_cutoff_and_threshold": universe_sizes,
            "cases": case_measurements,
        },
        "decision": decision,
        "limitations": [
            "The counts describe one dated secondary snapshot, not any complete NLM baseline.",
            "The snapshot uses MeSH 2013 labels and is not period-appropriate historical indexing.",
            (
                "The five positive cases are source-labelled reproduction targets, not "
                "independently adjudicated discovery truth."
            ),
            (
                "The sixteen controls remain ontology-generated proposals, not verified "
                "absences of a relationship or of non-academic knowledge."
            ),
            "Source compatibility does not evaluate or validate a metric formula.",
            (
                "No result here contributes metric-v3 readiness or permits an LLM "
                "interpretation layer."
            ),
        ],
    }
    _require(not find_forbidden_fields(payload), "compatibility payload contains metric output")
    return payload


def _expected_case_identity(case: CaseDefinition) -> dict[str, object]:
    expected = {
        "id": case.id,
        "kind": case.kind,
        "split": case.split,
        "cutoff": case.cutoff,
        "label_scope": case.label_scope,
        "endpoint_a": case.endpoint_a,
        "target_c": case.target_c,
    }
    if case.bridge_b is not None:
        expected["named_bridge_b"] = case.bridge_b
    return expected


def audit_compatibility_manifest(path: Path = MANIFEST_PATH) -> dict:
    payload = _load_json(path)
    _require(payload.get("schema_version") == 1, "unsupported compatibility schema")
    _require(payload.get("readiness_contribution") == 0, "compatibility cannot add readiness")
    _require(not find_forbidden_fields(payload), "compatibility manifest contains metric output")
    inputs = payload.get("inputs")
    _require(isinstance(inputs, dict), "compatibility manifest is missing inputs")
    pilot_path = _resolve_reference(inputs.get("pilot_protocol"), "pilot protocol")
    audit_bioasq_pilot(pilot_path)
    protocol = _load_json(pilot_path)
    snapshot_manifest, negative_queue, snapshot_manifest_path, negative_queue_path = (
        _protocol_dependencies(protocol)
    )
    _require(
        inputs.get("snapshot_audit") == _file_reference(snapshot_manifest_path),
        "compatibility snapshot-audit identity drifted",
    )
    _require(
        inputs.get("negative_candidate_queue") == _file_reference(negative_queue_path),
        "compatibility control-queue identity drifted",
    )
    _require(
        inputs.get("snapshot_transport", {}).get("sha256")
        == snapshot_manifest["input"]["sha256"]
        and inputs.get("snapshot_transport", {}).get("bytes")
        == snapshot_manifest["input"]["bytes"],
        "compatibility snapshot transport drifted",
    )
    _require(
        inputs.get("descriptor_vocabulary") == protocol["inputs"]["descriptor_vocabulary"],
        "compatibility vocabulary identity drifted",
    )

    transform = payload.get("transform")
    _require(isinstance(transform, dict), "compatibility transform is missing")
    _require(
        transform.get("publication_cutoff")
        == protocol["source_transform"]["publication_cutoff"]
        and transform.get("descriptor_identity")
        == protocol["source_transform"]["descriptor_identity"]
        and transform.get("article_contribution")
        == protocol["source_transform"]["article_contribution"]
        and transform.get("cooccurrence_unit")
        == protocol["source_transform"]["cooccurrence_unit"]
        and transform.get("direct_endpoint_cooccurrences")
        == protocol["source_transform"]["direct_endpoint_cooccurrences"]
        and transform.get("support_thresholds_articles") == list(SUPPORT_THRESHOLDS)
        and transform.get("cutoff_years") == list(CUTOFF_YEARS)
        and str(transform.get("source_query", "")).startswith("No API query:"),
        "compatibility source transform drifted",
    )

    measurement = payload.get("measurement")
    _require(isinstance(measurement, dict), "compatibility measurement is missing")
    _require(
        measurement.get("count_scope") == "exact_within_pinned_secondary_snapshot"
        and measurement.get("article_count_scanned")
        == snapshot_manifest["measured"]["article_count"]
        and measurement.get("mesh_assignment_count_scanned")
        == snapshot_manifest["measured"]["mesh_assignment_count"],
        "compatibility aggregate measurement drifted",
    )
    distinct_count = measurement.get("distinct_descriptor_count_through_2012")
    _require(
        type(distinct_count) is int
        and 0 < distinct_count <= inputs["descriptor_vocabulary"]["descriptor_count"],
        "compatibility distinct descriptor count is invalid",
    )
    included = measurement.get("included_article_count_by_cutoff")
    universes = measurement.get("support_eligible_descriptor_count_by_cutoff_and_threshold")
    _require(
        isinstance(included, dict) and isinstance(universes, dict),
        "cutoff counts are missing",
    )
    previous_articles = 0
    previous_universes = {str(threshold): 0 for threshold in SUPPORT_THRESHOLDS}
    publication_year_counts = {
        int(year): count
        for year, count in snapshot_manifest["measured"]["publication_year_counts"].items()
    }
    for cutoff in CUTOFF_YEARS:
        cutoff_key = str(cutoff)
        count = included.get(cutoff_key)
        universe = universes.get(cutoff_key)
        expected_count = sum(
            year_count for year, year_count in publication_year_counts.items() if year <= cutoff
        )
        _require(
            type(count) is int and count == expected_count and count >= previous_articles,
            "included article counts drifted",
        )
        _require(isinstance(universe, dict), f"{cutoff}: descriptor universe is missing")
        _require(
            all(
                type(universe.get(str(threshold))) is int
                and universe[str(threshold)] >= previous_universes[str(threshold)]
                for threshold in SUPPORT_THRESHOLDS
            ),
            f"{cutoff}: descriptor universe counts drifted",
        )
        _require(
            universe["5"] >= universe["10"] >= universe["20"],
            f"{cutoff}: support threshold universes are not nested",
        )
        previous_articles = count
        previous_universes = universe
    expected_after_last_cutoff = sum(
        count for year, count in publication_year_counts.items() if year > CUTOFF_YEARS[-1]
    )
    _require(
        measurement.get("articles_after_last_cutoff") == expected_after_last_cutoff
        and previous_articles + expected_after_last_cutoff
        == snapshot_manifest["measured"]["article_count"],
        "post-cutoff article count drifted",
    )

    cases = measurement.get("cases")
    definitions = _case_definitions(protocol, negative_queue)
    _require(isinstance(cases, list) and len(cases) == 21, "compatibility needs all 21 cases")
    for case, definition in zip(cases, definitions, strict=True):
        identity = _expected_case_identity(definition)
        for field in ("id", "kind", "split", "cutoff", "label_scope"):
            _require(case.get(field) == identity[field], f"{definition.id}: {field} drifted")
        for field in ("endpoint_a", "target_c"):
            concept = case.get(field)
            _require(isinstance(concept, dict), f"{definition.id}: {field} is missing")
            _require(
                {key: concept.get(key) for key in ("descriptor_ui", "descriptor_label")}
                == identity[field],
                f"{definition.id}: {field} identity drifted",
            )
            _require(
                type(concept.get("article_support")) is int
                and 0 <= concept["article_support"] <= included[definition.cutoff[:4]],
                f"{definition.id}: invalid {field} support",
            )
        a_count = case["endpoint_a"]["article_support"]
        c_count = case["target_c"]["article_support"]
        ac_count = case.get("direct_ac_article_count")
        _require(
            type(ac_count) is int and 0 <= ac_count <= min(a_count, c_count),
            f"{definition.id}: invalid direct A-C count",
        )
        _require(
            case.get("support_eligibility") == _support_eligibility(a_count, c_count)
            and case.get("primary_source_compatible")
            == (a_count >= PRIMARY_SUPPORT and c_count >= PRIMARY_SUPPORT),
            f"{definition.id}: support decision drifted",
        )
        if definition.bridge_b is not None:
            bridge = case.get("named_bridge_b")
            _require(isinstance(bridge, dict), f"{definition.id}: named bridge is missing")
            _require(
                {key: bridge.get(key) for key in ("descriptor_ui", "descriptor_label")}
                == identity["named_bridge_b"],
                f"{definition.id}: named bridge identity drifted",
            )
            b_count = bridge.get("article_support")
            ab_count = bridge.get("ab_article_count")
            bc_count = bridge.get("bc_article_count")
            _require(
                type(b_count) is int
                and type(ab_count) is int
                and type(bc_count) is int
                and 0 <= ab_count <= min(a_count, b_count)
                and 0 <= bc_count <= min(b_count, c_count),
                f"{definition.id}: invalid named-bridge counts",
            )
        else:
            _require("named_bridge_b" not in case, f"{definition.id}: control gained a bridge")

    expected_decision = _source_decision(
        cases, protocol["source_compatibility_gate"]["failure_outcome"]
    )
    _require(payload.get("decision") == expected_decision, "source decision drifted")
    _require(payload.get("status") == expected_decision["status"], "manifest status drifted")
    _require(
        "not a metric result" in str(payload.get("claim_boundary"))
        and isinstance(payload.get("limitations"), list)
        and len(payload["limitations"]) >= 6,
        "compatibility claim boundary or limitations are incomplete",
    )
    return {
        "status": payload["status"],
        "case_count": len(cases),
        "incompatible_case_ids": expected_decision["incompatible_case_ids"],
        "readiness_contribution": 0,
    }


def _write_new(path: Path, payload: dict) -> None:
    if path.exists():
        raise SystemExit(f"refusing to overwrite existing compatibility manifest: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path, nargs="?")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    args = parser.parse_args()
    _require(sum((args.validate, args.verify, args.output is not None)) == 1, "choose one mode")

    if args.validate:
        _require(args.snapshot is None, "--validate does not take a snapshot")
        audit = audit_compatibility_manifest(args.manifest)
        print("BioASQ pilot source compatibility manifest: structurally valid")
        print(f"status: {audit['status']}")
        print(f"cases: {audit['case_count']}")
        print(f"incompatible cases: {len(audit['incompatible_case_ids'])}")
        print(f"readiness contribution: {audit['readiness_contribution']}")
        return

    snapshot_path = args.snapshot or SNAPSHOT_PATH
    payload = build_compatibility_payload(snapshot_path)
    if args.output is not None:
        _write_new(args.output, payload)
        print(f"wrote {args.output}")
        print(f"status: {payload['status']}")
        return
    committed = _load_json(args.manifest)
    _require(payload == committed, "full source replay differs from committed manifest")
    print("BioASQ pilot source compatibility full replay: exact match")
    print(f"status: {payload['status']}")


if __name__ == "__main__":
    main()
