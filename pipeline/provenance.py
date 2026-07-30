"""Content fingerprints and provenance hygiene for regenerable pipeline state.

Source URLs prove which query was requested, but they do not prove which response was used.
Published artifacts therefore pin canonical content digests for the taxonomy and every
co-occurrence row. Volatile fetch timestamps and request credentials are deliberately excluded:
rerunning an identical query should produce the same fingerprint, and a digest must not become a
stable fingerprint of a maintainer's email address or API key.

Run ``python -m pipeline.provenance`` to remove credentials from provenance fields in older local
caches. The command does not alter measured counts.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable

from pipeline.openalex_client import sanitise_url
from pipeline.paths import CACHE_DIR, COOCCURRENCE_DIR, TAXONOMY_PATH

ROW_FIELDS = ("topic", "marginal", "partners", "truncated", "ceiling")


def canonical_json_bytes(payload: object) -> bytes:
    """Encode JSON deterministically for content-addressing."""
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_payload(payload: object) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def canonical_cooccurrence_row(row: dict) -> dict:
    """Keep measured row content and public query provenance, excluding fetch-time noise."""
    canonical = {field: row[field] for field in ROW_FIELDS}
    canonical["source_url"] = sanitise_url(row.get("source_url", ""))
    return canonical


def cooccurrence_rows_fingerprint(paths: Iterable[Path]) -> dict[str, str | int]:
    """Fingerprint a deterministically ordered collection of row artifacts."""
    rows = []
    for path in sorted(paths):
        row = json.loads(path.read_text(encoding="utf-8"))
        rows.append(canonical_cooccurrence_row(row))
    return {
        "sha256": sha256_payload(rows),
        "rows": len(rows),
        "canonicalisation": "counts+public-query-v1",
    }


def input_fingerprints(slice_name: str) -> dict[str, dict[str, str | int]]:
    taxonomy = json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))
    rows = (COOCCURRENCE_DIR / slice_name).glob("T*.json")
    return {
        "taxonomy": {
            "sha256": sha256_payload(taxonomy),
            "canonicalisation": "canonical-json-v1",
        },
        "cooccurrence_rows": cooccurrence_rows_fingerprint(rows),
    }


def _sanitise_file(path: Path, field: str) -> bool:
    payload = json.loads(path.read_text(encoding="utf-8"))
    current = payload.get(field)
    if not isinstance(current, str):
        return False
    cleaned = sanitise_url(current)
    if cleaned == current:
        return False
    payload[field] = cleaned
    path.write_text(json.dumps(payload), encoding="utf-8")
    return True


def sanitise_local_provenance() -> tuple[int, int]:
    """Rewrite only provenance URL fields in ignored, regenerable local data."""
    scanned = changed = 0
    for path in CACHE_DIR.glob("*.json"):
        scanned += 1
        changed += int(_sanitise_file(path, "_lacuna_source_url"))
    for path in COOCCURRENCE_DIR.glob("*/*.json"):
        scanned += 1
        changed += int(_sanitise_file(path, "source_url"))
    return scanned, changed


def main() -> None:
    scanned, changed = sanitise_local_provenance()
    print(f"provenance files scanned: {scanned}")
    print(f"credential-bearing provenance fields cleaned: {changed}")


if __name__ == "__main__":
    main()
