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
from pipeline.benchmark.negative_review_context import (
    OUTPUT_PATH as NEGATIVE_REVIEW_CONTEXT_PATH,
    audit_review_context,
)
from pipeline.benchmark.bioasq_semantics import (
    DEFAULT_AUDIT_PATH as BIOASQ_SEMANTICS_AUDIT_PATH,
    PROTOCOL_PATH as BIOASQ_SEMANTICS_PROTOCOL_PATH,
    SUCCESSOR_PROTOCOL_PATH as BIOASQ_SUCCESSOR_PROTOCOL_PATH,
    audit_semantics_manifest,
)
from pipeline.benchmark.bioasq_snapshot import MANIFEST_PATH as BIOASQ_SNAPSHOT_MANIFEST_PATH
from pipeline.benchmark.bioasq_pilot_compatibility import (
    MANIFEST_PATH as BIOASQ_PILOT_COMPATIBILITY_PATH,
    audit_compatibility_manifest,
)
from pipeline.benchmark.validate_bioasq_formula_v2 import (
    FORMULA_PATH as BIOASQ_FORMULA_V2_PATH,
    audit_bioasq_formula_v2,
)
from pipeline.benchmark.validate_bioasq_formula_v2_revision import (
    REVISION_FORMULA_PATH as BIOASQ_FORMULA_V2_REVISION_PATH,
    audit_bioasq_formula_v2_revision,
)
from pipeline.benchmark.validate_bioasq_v2_development import (
    DEVELOPMENT_PATH as BIOASQ_V2_DEVELOPMENT_PATH,
    audit_bioasq_v2_development,
)
from pipeline.benchmark.validate_bioasq_v2_revision_development import (
    REVISION_DEVELOPMENT_PATH as BIOASQ_V2_REVISION_DEVELOPMENT_PATH,
    audit_bioasq_v2_revision_development,
)
from pipeline.benchmark.validate_bioasq_pilot import (
    PILOT_PATH as BIOASQ_PILOT_PATH,
    audit_bioasq_pilot,
)
from pipeline.benchmark.validate_bioasq_pilot_v2 import (
    SUCCESSOR_PATH as BIOASQ_PILOT_V2_PATH,
    audit_bioasq_pilot_v2,
)
from pipeline.benchmark.mbr_capture import CAPTURE_PATH as MBR_CAPTURE_PATH
from pipeline.benchmark.validate_candidates import CANDIDATES_PATH, audit_candidates
from pipeline.benchmark.validate_source_alternatives import (
    ALTERNATIVES_PATH,
    audit_source_alternatives,
)
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
    alternatives = audit_source_alternatives()
    bioasq_snapshot = json.loads(BIOASQ_SNAPSHOT_MANIFEST_PATH.read_text(encoding="utf-8"))
    bioasq_successor_protocol = json.loads(
        BIOASQ_SUCCESSOR_PROTOCOL_PATH.read_text(encoding="utf-8")
    )
    bioasq_semantics_audit = audit_semantics_manifest()
    audit_bioasq_pilot()
    bioasq_pilot = json.loads(BIOASQ_PILOT_PATH.read_text(encoding="utf-8"))
    audit_compatibility_manifest()
    bioasq_pilot_compatibility = json.loads(
        BIOASQ_PILOT_COMPATIBILITY_PATH.read_text(encoding="utf-8")
    )
    audit_bioasq_pilot_v2()
    bioasq_pilot_v2 = json.loads(BIOASQ_PILOT_V2_PATH.read_text(encoding="utf-8"))
    audit_bioasq_formula_v2()
    bioasq_formula_v2 = json.loads(BIOASQ_FORMULA_V2_PATH.read_text(encoding="utf-8"))
    audit_bioasq_v2_development()
    bioasq_v2_development = json.loads(
        BIOASQ_V2_DEVELOPMENT_PATH.read_text(encoding="utf-8")
    )
    audit_bioasq_formula_v2_revision()
    bioasq_formula_v2_revision = json.loads(
        BIOASQ_FORMULA_V2_REVISION_PATH.read_text(encoding="utf-8")
    )
    audit_bioasq_v2_revision_development()
    bioasq_v2_revision_development = json.loads(
        BIOASQ_V2_REVISION_DEVELOPMENT_PATH.read_text(encoding="utf-8")
    )
    candidates = audit_candidates()
    negative_queue = audit_queue()
    audit_review_context()
    benchmark = audit_benchmark()
    ready = sources.ready and benchmark.ready
    candidate_payload = json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))
    negative_payload = json.loads(NEGATIVE_QUEUE_PATH.read_text(encoding="utf-8"))
    negative_context_payload = json.loads(
        NEGATIVE_REVIEW_CONTEXT_PATH.read_text(encoding="utf-8")
    )
    negative_context = {
        entry["candidate_id"]: entry
        for entry in negative_context_payload["entries"]
    }
    negative_protocol = load_protocol()

    return {
        "schema_version": 18,
        "status": "ready" if ready else "not_ready",
        "inputs": {
            "historical_sources": _input_identity(SOURCES_PATH),
            "source_alternatives": _input_identity(ALTERNATIVES_PATH),
            "bioasq_snapshot_audit": _input_identity(BIOASQ_SNAPSHOT_MANIFEST_PATH),
            "bioasq_semantics_protocol": _input_identity(BIOASQ_SEMANTICS_PROTOCOL_PATH),
            "bioasq_successor_semantics_protocol": _input_identity(
                BIOASQ_SUCCESSOR_PROTOCOL_PATH
            ),
            "bioasq_semantics_audit": _input_identity(BIOASQ_SEMANTICS_AUDIT_PATH),
            "bioasq_pilot_protocol": _input_identity(BIOASQ_PILOT_PATH),
            "bioasq_pilot_compatibility_audit": _input_identity(
                BIOASQ_PILOT_COMPATIBILITY_PATH
            ),
            "bioasq_pilot_successor_protocol": _input_identity(BIOASQ_PILOT_V2_PATH),
            "bioasq_initial_formula_contract": _input_identity(BIOASQ_FORMULA_V2_PATH),
            "bioasq_development_measurement": _input_identity(BIOASQ_V2_DEVELOPMENT_PATH),
            "bioasq_revision_formula_contract": _input_identity(
                BIOASQ_FORMULA_V2_REVISION_PATH
            ),
            "bioasq_revision_development_measurement": _input_identity(
                BIOASQ_V2_REVISION_DEVELOPMENT_PATH
            ),
            "historical_inventories": _input_identity(INVENTORIES_PATH),
            "mbr_preservation_capture": _input_identity(MBR_CAPTURE_PATH),
            "candidate_intake": _input_identity(CANDIDATES_PATH),
            "negative_selection_protocol": _input_identity(NEGATIVE_PROTOCOL_PATH),
            "negative_candidate_queue": _input_identity(NEGATIVE_QUEUE_PATH),
            "negative_review_context": _input_identity(NEGATIVE_REVIEW_CONTEXT_PATH),
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
            "preservation_metadata": {
                "available": len(sources.preservation_capture_years),
                "required": len(sources.required_years),
                "years": list(sources.preservation_capture_years),
                "scope": "preserved repository directory metadata only",
            },
            "statuses": dict(sorted(sources.statuses.items())),
            "provider_confirmation": {
                "provider": "NLM Support",
                "received_on": sources.provider_confirmation_received_on,
                "scope": "previous annual PubMed baseline availability",
            },
            "readiness_blockers": list(sources.readiness_blockers),
        },
        "source_alternatives": {
            "status": alternatives.status,
            "recommended_id": alternatives.recommended_id,
            "counts": alternatives.counts,
            "readiness_contribution": alternatives.readiness_contribution,
            "bioasq_snapshot": bioasq_snapshot,
            "bioasq_successor_protocol": bioasq_successor_protocol,
            "bioasq_semantics_audit": bioasq_semantics_audit,
            "bioasq_pilot_protocol": bioasq_pilot,
            "bioasq_pilot_compatibility_audit": bioasq_pilot_compatibility,
            "bioasq_pilot_successor_protocol": bioasq_pilot_v2,
            "bioasq_initial_formula_contract": bioasq_formula_v2,
            "bioasq_development_measurement": bioasq_v2_development,
            "bioasq_revision_formula_contract": bioasq_formula_v2_revision,
            "bioasq_revision_development_measurement": bioasq_v2_revision_development,
            "entries": list(alternatives.entries),
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
            "context_warning": negative_context_payload["warning"],
            "entries": [
                {
                    **candidate,
                    "review_context": {
                        key: value
                        for key, value in negative_context[candidate["id"]].items()
                        if key != "candidate_id"
                    },
                }
                for candidate in negative_payload["candidates"]
            ],
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
