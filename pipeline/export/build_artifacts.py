"""Build the versioned static artifacts the frontend reads.

There is no backend. Everything the site needs is written here as plain JSON, versioned by the
date of the underlying sweep so an older map stays reproducible after the metric changes.

The computed layer is exported even though it failed validation, because deleting a negative
result is how negative results stop existing. It ships carrying its own verdict: every consumer
reads `computed.validation.verdict` before rendering anything, and the manifest says plainly that
these pairs are not discoveries.

Run:  python -m pipeline.export.build_artifacts
"""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.export.validate_curated import load_all
from pipeline.metric.gap_score import (
    BRIDGE_K,
    generalist_topics,
    load_matrix,
    load_taxonomy_counts,
    score_pairs,
)
from pipeline.openalex_client import OpenAlexClient
from pipeline.paths import ARTIFACTS_DIR, COOCCURRENCE_DIR, TAXONOMY_PATH, ensure_dirs
from pipeline.provenance import input_fingerprints, sha256_payload

PRE1986_TOTAL_WORKS = 38_458_832
TOP_GAPS_EXPORTED = 500
DATA_SNAPSHOT_DATE = "2026-07-27"
METRIC_VERSION = "v2-bridge-k5"
ARTIFACT_SCHEMA_VERSION = 3
ANALYSIS_TOPICS_PLANNED = 1458

# Measured outcome of the pre-registered validation. Travels with the artifact so a consumer
# cannot render the computed layer without also having the verdict in hand.
VALIDATION = {
    "verdict": "FAIL",
    "preregistration": "docs/metric-validation-preregistration.md",
    "report": "plans/reports/validation-260727-1140-swanson-reproduction-negative-result-report.md",
    "target_pair": ["T11330", "T10387"],
    "target_percentile": 30.84,
    "required_percentile": 5.0,
    "negative_controls_pass": None,
    "negative_controls_status": "partial",
    "negative_controls_evaluated": 1,
    "negative_controls_planned": 2,
    "summary": (
        "The metric does not reproduce the canonical Swanson result it was pre-registered against. "
        "These pairs are published as measurements, not as discoveries."
    ),
}


def build_taxonomy() -> dict:
    taxonomy = json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))
    return {
        level: [
            {k: v for k, v in node.items() if k != "keywords"}
            for node in taxonomy[level]
        ]
        for level in ("domains", "fields", "subfields", "topics")
    }


def build_computed_layer(names: dict[str, str], inputs: dict) -> dict:
    """Score the pre-1986 sweep and export the top pairs with per-row provenance."""
    matrix = load_matrix("pre1986", PRE1986_TOTAL_WORKS)
    results = score_pairs(matrix, load_taxonomy_counts(), closeness="bridge")
    source_urls = matrix.source_urls or [""] * len(matrix.topic_ids)
    source_by_topic = dict(zip(matrix.topic_ids, source_urls))

    client = OpenAlexClient()
    rows = []
    for row in results[:TOP_GAPS_EXPORTED]:
        a, b = row["topic_a"], row["topic_b"]
        rows.append(
            {
                **row,
                "name_a": names.get(a, a),
                "name_b": names.get(b, b),
                "row_source_urls": [source_by_topic[a], source_by_topic[b]],
                # The exact query a reader can run to check the count for themselves. Without this
                # the numbers are unfalsifiable, which would make the whole artifact decoration.
                "verify_url": client.build_public_url(
                    "works",
                    {
                        "filter": f"topics.id:{a},topics.id:{b},to_publication_date:1985-12-31",
                        "per-page": 1,
                    },
                ),
            }
        )

    excluded = sorted(generalist_topics(matrix))
    pending = ANALYSIS_TOPICS_PLANNED - len(matrix.topic_ids)
    return {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "status": "unvalidated",
        "validation": VALIDATION,
        "method": {
            "version": METRIC_VERSION,
            "closeness": "bridge",
            "bridge_k": BRIDGE_K,
            "slice": "pre1986",
            "description": (
                "Gap = (summed strength of the k strongest shared intermediate topics) x "
                "(1 - probability of seeing this few co-occurrences by chance)."
            ),
        },
        "coverage": {
            "topics_swept": len(matrix.topic_ids),
            "topics_in_analysis_set": ANALYSIS_TOPICS_PLANNED,
            "pairs_scored": len(results),
            "complete": pending == 0,
            "note": (
                "Sweep complete."
                if pending == 0
                else f"Sweep incomplete: {pending} planned topics have no fetched row."
            ),
        },
        "provenance": {
            "inputs": inputs,
            "total_works_query": client.build_public_url(
                "works",
                {
                    "filter": "to_publication_date:1985-12-31",
                    "per-page": 1,
                },
            ),
        },
        "excluded_topics": [
            {
                "id": topic,
                "display_name": names.get(topic, topic),
                "reason": "slice marginal above Q3 + 10 x IQR",
            }
            for topic in excluded
        ],
        "gaps": rows,
    }


def _assert_snapshot_inputs_unchanged(out_dir: Path, inputs: dict) -> None:
    """Refuse to silently reuse a snapshot label for different measured inputs."""
    manifest_path = out_dir / "manifest.json"
    if not manifest_path.exists():
        return
    previous = json.loads(manifest_path.read_text(encoding="utf-8"))
    previous_inputs = previous.get("snapshot", {}).get("inputs")
    # Schema v2 did not fingerprint content. Permit the one-way schema upgrade; every subsequent
    # build of this snapshot label is immutable with respect to measured inputs.
    if previous_inputs is not None and previous_inputs != inputs:
        raise SystemExit(
            f"{out_dir} already identifies different input content; choose a new "
            "DATA_SNAPSHOT_DATE instead of overwriting a published snapshot"
        )


def main() -> None:
    ensure_dirs()
    if not (COOCCURRENCE_DIR / "pre1986").exists():
        raise SystemExit("no pre-1986 sweep found; run pipeline.ingest.fetch_cooccurrence first")

    version = f"{DATA_SNAPSHOT_DATE}/{METRIC_VERSION}"
    out_dir = ARTIFACTS_DIR / DATA_SNAPSHOT_DATE / METRIC_VERSION
    out_dir.mkdir(parents=True, exist_ok=True)
    inputs = input_fingerprints("pre1986")
    _assert_snapshot_inputs_unchanged(out_dir, inputs)

    taxonomy = build_taxonomy()
    names = {t["id"]: t["display_name"] for t in taxonomy["topics"]}
    curated = load_all()
    computed = build_computed_layer(names, inputs)
    client = OpenAlexClient()

    payloads = {
        "taxonomy.json": taxonomy,
        "curated.json": curated,
        "computed-gaps.json": computed,
    }
    manifest = {
        "version": version,
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "source": "OpenAlex REST API",
        "snapshot": {
            "date": DATA_SNAPSHOT_DATE,
            "slice": "pre1986",
            "to_publication_date": "1985-12-31",
            "total_works": PRE1986_TOTAL_WORKS,
            "inputs": inputs,
        },
        "files": {
            filename: {
                "sha256": sha256_payload(payload),
                "canonicalisation": "canonical-json-v1",
            }
            for filename, payload in payloads.items()
        },
        "source_queries": {
            "total_works": computed["provenance"]["total_works_query"],
            "taxonomy_counts": {
                level: client.build_public_url(level, {"per-page": 1})
                for level in ("domains", "fields", "subfields", "topics")
            },
        },
        "metric": {
            "version": METRIC_VERSION,
            "closeness": "bridge",
            "bridge_k": BRIDGE_K,
        },
        "counts": {
            "domains": len(taxonomy["domains"]),
            "fields": len(taxonomy["fields"]),
            "subfields": len(taxonomy["subfields"]),
            "topics": len(taxonomy["topics"]),
            **{layer: len(entries) for layer, entries in curated.items()},
            "computed_gaps": len(computed["gaps"]),
            "excluded_topics": len(computed["excluded_topics"]),
        },
        "computed_layer_status": computed["status"],
        "computed_layer_verdict": VALIDATION["verdict"],
    }
    payloads["manifest.json"] = manifest

    for filename, payload in payloads.items():
        path = out_dir / filename
        path.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        print(f"  {filename:<20} {path.stat().st_size / 1024:>8.1f} KB")

    (ARTIFACTS_DIR / "latest.json").write_text(
        json.dumps({"version": version}, indent=1), encoding="utf-8"
    )
    print(f"\nwrote artifacts/{version}/ (computed layer: {VALIDATION['verdict']})")


if __name__ == "__main__":
    main()
