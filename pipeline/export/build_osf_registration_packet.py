"""Build the byte-level manifest for the prospective-track OSF registration packet.

The packet records an already sealed protocol and T0 prediction state.  It is not a new
preregistration: scoring was completed before this packet was prepared.  Hashes here cover the
small, versioned repository records; the large source and prediction files remain pinned by the
digests inside those records.

Run:  python -m pipeline.export.build_osf_registration_packet
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pipeline.provenance import sha256_payload


ROOT = Path(__file__).parents[2]
OUTPUT = ROOT / "registrations" / "autonomous-prospective-v1" / "manifest.json"

PACKET_FILES = (
    "registrations/autonomous-prospective-v1/README.md",
    "registrations/autonomous-prospective-v1/registration.md",
)

REGISTERED_FILES = (
    "benchmarks/autonomous-prospective-v1.json",
    "benchmarks/autonomous/t0-2026-remote-inventory.json",
    "benchmarks/autonomous/t0-2026.json",
    "benchmarks/autonomous/t0-candidate-index-v1.json",
    "benchmarks/autonomous/t0-candidate-universe-v1.json",
    "benchmarks/autonomous/metric-v1.json",
    "benchmarks/autonomous/metric-v1-dependencies.lock.json",
    "benchmarks/autonomous/t0-predictions-v1.json",
    "benchmarks/autonomous/release-watch-v1.json",
)


def _file_record(root: Path, relative_path: str) -> dict[str, object]:
    path = root / relative_path
    raw = path.read_bytes()
    record: dict[str, object] = {
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    if path.suffix == ".json":
        record["canonical_json_sha256"] = sha256_payload(json.loads(raw))
    return record


def build_manifest(root: Path = ROOT) -> dict[str, object]:
    protocol = json.loads((root / REGISTERED_FILES[0]).read_text(encoding="utf-8"))
    predictions = json.loads(
        (root / "benchmarks/autonomous/t0-predictions-v1.json").read_text(encoding="utf-8")
    )
    return {
        "schema_version": 1,
        "packet_id": "autonomous-prospective-v1-sealed-state-registration",
        "prepared_on": "2026-08-25",
        "submission_status": "prepared_not_submitted",
        "record_type": "registration_of_previously_sealed_protocol_and_predictions",
        "not_a_new_preregistration": True,
        "repository": "https://github.com/tang-vu/lacuna",
        "intended_release": "v0.2.0",
        "release_doi": None,
        "current_scientific_state": {
            "state": protocol["current_state"]["state"],
            "verdict": protocol["current_state"]["verdict"],
            "readiness_contribution": protocol["current_state"]["readiness_contribution"],
            "candidate_pair_count": predictions["measurements"]["candidate_score_rows"],
            "validated_knowledge_gap_pairs": 0,
        },
        "hash_scope": (
            "Raw-byte SHA-256 and byte length cover every listed small repository file. "
            "Canonical JSON SHA-256 is additionally provided for JSON. Large local corpora and "
            "binary outputs are represented by the source and prediction records that pin them."
        ),
        "packet_files": {
            path: _file_record(root, path) for path in PACKET_FILES
        },
        "registered_files": {
            path: _file_record(root, path) for path in REGISTERED_FILES
        },
    }


def main() -> None:
    manifest = build_manifest()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {OUTPUT.relative_to(ROOT)} ({len(manifest['registered_files'])} records)")


if __name__ == "__main__":
    main()
