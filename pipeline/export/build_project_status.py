"""Export the contributor-facing state of metric v3 from its validated contracts.

This artifact is deliberately separate from the dated v2 measurement snapshot. Benchmark and
source readiness can change without changing the failed v2 inputs, so putting both under one
version would make an old scientific snapshot mutable.

Run: ``python -m pipeline.export.build_project_status``
"""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.benchmark.negative_controls import (
    OUTPUT_PATH as NEGATIVE_QUEUE_PATH,
    PROTOCOL_PATH as NEGATIVE_PROTOCOL_PATH,
    audit_queue,
    load_protocol,
)
from pipeline.benchmark.validate_candidates import CANDIDATES_PATH, audit_candidates
from pipeline.benchmark.source_inventories import INVENTORIES_PATH
from pipeline.benchmark.validate_sources import SOURCES_PATH, audit_sources
from pipeline.benchmark.validate_v3 import (
    BENCHMARK_PATH,
    EXPECTED_REQUIREMENTS,
    audit_benchmark,
)
from pipeline.paths import ARTIFACTS_DIR, REPO_ROOT
from pipeline.provenance import sha256_payload

PROJECT_STATUS_PATH = ARTIFACTS_DIR / "project-status.json"


def _input_identity(path: Path) -> dict[str, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        "path": path.relative_to(REPO_ROOT).as_posix(),
        "sha256": sha256_payload(payload),
        "canonicalisation": "canonical-json-v1",
    }


def build_project_status() -> dict:
    sources = audit_sources()
    candidates = audit_candidates()
    negative_queue = audit_queue()
    benchmark = audit_benchmark()
    ready = sources.ready and benchmark.ready
    candidate_payload = json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))
    negative_payload = json.loads(NEGATIVE_QUEUE_PATH.read_text(encoding="utf-8"))
    negative_protocol = load_protocol()

    return {
        "schema_version": 4,
        "status": "ready" if ready else "not_ready",
        "inputs": {
            "historical_sources": _input_identity(SOURCES_PATH),
            "historical_inventories": _input_identity(INVENTORIES_PATH),
            "candidate_intake": _input_identity(CANDIDATES_PATH),
            "negative_selection_protocol": _input_identity(NEGATIVE_PROTOCOL_PATH),
            "negative_candidate_queue": _input_identity(NEGATIVE_QUEUE_PATH),
            "benchmark": _input_identity(BENCHMARK_PATH),
        },
        "historical_sources": {
            "ready": sources.ready,
            "required_years": list(sources.required_years),
            "inventory_metadata": {
                "available": len(sources.inventory_years),
                "required": len(sources.required_years),
                "years": list(sources.inventory_years),
                "scope": "official inventory metadata only",
            },
            "raw_record_releases": {
                "pinned": len(sources.pinned_record_years),
                "required": len(sources.required_years),
                "years": list(sources.pinned_record_years),
            },
            "statuses": dict(sorted(sources.statuses.items())),
            "readiness_blockers": list(sources.readiness_blockers),
        },
        "candidate_intake": {
            "counts": dict(candidates.counts),
            "accepted_benchmark_links": len(candidates.accepted_benchmark_ids),
            "readiness_contribution": "accepted benchmark links only",
            "purpose": candidate_payload["purpose"],
            "policy": candidate_payload["policy"],
            # These entries remain human-curated intake records. Copying them into the generated
            # status artifact makes the public review surface reproducible without changing the
            # dated v2 measurement snapshot or creating a second hand-edited candidate source.
            "entries": candidate_payload["candidates"],
        },
        "negative_candidate_queue": {
            "counts": negative_queue["counts"],
            "heldout_counts": negative_queue["heldout_counts"],
            "readiness_contribution": negative_queue["readiness_contribution"],
            "protocol_status": negative_protocol["status"],
            "warning": negative_payload["warning"],
            "entries": negative_payload["candidates"],
        },
        "benchmark": {
            "ready": benchmark.ready,
            "requirements": dict(EXPECTED_REQUIREMENTS),
            "counts": dict(benchmark.counts),
            "heldout_counts": dict(benchmark.heldout_counts),
            "mapping_counts": dict(benchmark.mapping_counts),
            "period_appropriate_heldout_cutoffs": list(
                benchmark.period_appropriate_heldout_cutoffs
            ),
            "readiness_blockers": list(benchmark.readiness_blockers),
        },
    }


def write_project_status(path: Path = PROJECT_STATUS_PATH) -> dict:
    payload = build_project_status()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    return payload


def main() -> None:
    payload = write_project_status()
    print(f"wrote {PROJECT_STATUS_PATH.relative_to(REPO_ROOT).as_posix()}")
    print(f"v3 readiness: {payload['status'].upper().replace('_', ' ')}")


if __name__ == "__main__":
    main()
