"""Validate the hand-curated layers before they are published.

Curated entries are the part of lacuna a reader is most likely to trust, because a person wrote
them. That makes an unsourced claim here more damaging than a bad number in the computed layer,
which carries its own caveats. So sourcing is enforced rather than encouraged.
"""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.paths import REPO_ROOT

CURATED_DIR = REPO_ROOT / "curated"

BLOCKER_TYPES = {"instrumentation", "cost", "ethics", "timescale"}
SEVERITIES = {"partial", "total", "structural"}


class CuratedContentError(Exception):
    """A curated entry is malformed or unsourced."""


def _require(condition: bool, entry_id: str, message: str) -> None:
    if not condition:
        raise CuratedContentError(f"{entry_id}: {message}")


def validate_entry(entry: dict, layer: str, seen: set[str]) -> None:
    entry_id = entry.get("id", "<missing id>")
    _require(bool(entry.get("id")), entry_id, "missing id")
    _require(entry_id not in seen, entry_id, "duplicate id")
    seen.add(entry_id)

    for field in ("title", "summary"):
        _require(bool(entry.get(field)), entry_id, f"missing {field}")

    if layer in ("open", "blocked"):
        # An acknowledged open problem without a citation is just an assertion.
        sources = entry.get("sources") or []
        _require(len(sources) > 0, entry_id, "no sources; every open/blocked entry must cite one")
        for source in sources:
            _require(bool(source.get("label")), entry_id, "source missing label")
            _require(bool(source.get("url")), entry_id, "source missing url")

    if layer == "blocked":
        blocker = entry.get("blocker")
        _require(
            blocker in BLOCKER_TYPES,
            entry_id,
            f"blocker must be one of {sorted(BLOCKER_TYPES)}, got {blocker!r}",
        )

    if layer == "blind-spots":
        _require(
            entry.get("severity") in SEVERITIES,
            entry_id,
            f"severity must be one of {sorted(SEVERITIES)}",
        )


def load_layer(layer: str, curated_dir: Path = CURATED_DIR) -> list[dict]:
    """Read and validate one curated layer."""
    path = curated_dir / f"{layer}.json"
    if not path.exists():
        raise CuratedContentError(f"missing curated layer: {path}")

    entries = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(entries, list):
        raise CuratedContentError(f"{path}: expected a list of entries")

    seen: set[str] = set()
    for entry in entries:
        validate_entry(entry, layer, seen)
    return entries


def load_all(curated_dir: Path = CURATED_DIR) -> dict[str, list[dict]]:
    return {layer: load_layer(layer, curated_dir) for layer in ("open", "blocked", "blind-spots")}


def main() -> None:
    layers = load_all()
    for layer, entries in layers.items():
        print(f"  {layer:<12} {len(entries):>3} entries OK")


if __name__ == "__main__":
    main()
