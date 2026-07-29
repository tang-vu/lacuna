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
import hashlib

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

PRE1986_TOTAL_WORKS = 38_458_832
TOP_GAPS_EXPORTED = 500
DATA_SNAPSHOT_DATE = "2026-07-27"
METRIC_VERSION = "v2-bridge-k5"
ARTIFACT_SCHEMA_VERSION = 2
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


def build_computed_layer(names: dict[str, str]) -> dict:
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
    all_row_urls = sorted(url for url in source_urls if url)
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
            "row_sources_count": len(all_row_urls),
            "row_source_digest_sha256": hashlib.sha256(
                "\n".join(all_row_urls).encode()
            ).hexdigest(),
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


def main() -> None:
    ensure_dirs()
    if not (COOCCURRENCE_DIR / "pre1986").exists():
        raise SystemExit("no pre-1986 sweep found; run pipeline.ingest.fetch_cooccurrence first")

    version = f"{DATA_SNAPSHOT_DATE}/{METRIC_VERSION}"
    out_dir = ARTIFACTS_DIR / DATA_SNAPSHOT_DATE / METRIC_VERSION
    out_dir.mkdir(parents=True, exist_ok=True)

    taxonomy = build_taxonomy()
    names = {t["id"]: t["display_name"] for t in taxonomy["topics"]}
    curated = load_all()
    computed = build_computed_layer(names)
    client = OpenAlexClient()

    artifacts = {
        "taxonomy.json": taxonomy,
        "curated.json": curated,
        "computed-gaps.json": computed,
        "manifest.json": {
            "version": version,
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "source": "OpenAlex REST API",
            "snapshot": {
                "date": DATA_SNAPSHOT_DATE,
                "slice": "pre1986",
                "to_publication_date": "1985-12-31",
                "total_works": PRE1986_TOTAL_WORKS,
                "row_source_digest_sha256": computed["provenance"][
                    "row_source_digest_sha256"
                ],
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
        },
    }

    for filename, payload in artifacts.items():
        path = out_dir / filename
        path.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        print(f"  {filename:<20} {path.stat().st_size / 1024:>8.1f} KB")

    (ARTIFACTS_DIR / "latest.json").write_text(
        json.dumps({"version": version}, indent=1), encoding="utf-8"
    )
    print(f"\nwrote artifacts/{version}/ (computed layer: {VALIDATION['verdict']})")


if __name__ == "__main__":
    main()
