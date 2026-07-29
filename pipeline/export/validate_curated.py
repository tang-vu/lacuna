"""Validate the hand-curated layers before they are published.

Curated entries are the part of lacuna a reader is most likely to trust, because a person wrote
them. That makes an unsourced claim here more damaging than a bad number in the computed layer,
which carries its own caveats. So sourcing is enforced rather than encouraged.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from urllib.parse import urlsplit

from pipeline.paths import REPO_ROOT

CURATED_DIR = REPO_ROOT / "curated"

BLOCKER_TYPES = {"instrumentation", "cost", "ethics", "timescale"}
SEVERITIES = {"partial", "total", "structural"}
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
TOPIC_ID = re.compile(r"^T\d+$")


class CuratedContentError(Exception):
    """A curated entry is malformed or unsourced."""


def _require(condition: bool, entry_id: str, message: str) -> None:
    if not condition:
        raise CuratedContentError(f"{entry_id}: {message}")


def _validate_source(source: dict, entry_id: str, repo_root: Path) -> str:
    _require(isinstance(source, dict), entry_id, "source must be an object")
    _require(bool(source.get("label")), entry_id, "source missing label")
    url = source.get("url")
    _require(isinstance(url, str) and bool(url), entry_id, "source missing url")

    parts = urlsplit(url)
    if parts.scheme:
        _require(parts.scheme == "https", entry_id, "external source URL must use HTTPS")
        _require(bool(parts.netloc), entry_id, "external source URL has no host")
    else:
        _require(not Path(url).is_absolute(), entry_id, "local source path must be repo-relative")
        target = (repo_root / url).resolve()
        root = repo_root.resolve()
        _require(
            target != root and root in target.parents,
            entry_id,
            "local source path resolves outside the repository",
        )
        _require(target.is_file(), entry_id, f"local source does not exist: {url}")
    return url


def validate_entry(
    entry: dict,
    layer: str,
    seen: set[str],
    repo_root: Path = REPO_ROOT,
) -> None:
    entry_id = entry.get("id", "<missing id>")
    _require(bool(entry.get("id")), entry_id, "missing id")
    _require(bool(SLUG.fullmatch(str(entry_id))), entry_id, "id must be a lowercase slug")
    _require(entry_id not in seen, entry_id, "duplicate id")
    seen.add(entry_id)

    for field in ("title", "summary"):
        _require(bool(entry.get(field)), entry_id, f"missing {field}")

    sources = entry.get("sources") or []
    if layer in ("open", "blocked"):
        # An acknowledged open problem without a citation is just an assertion.
        _require(len(sources) > 0, entry_id, "no sources; every open/blocked entry must cite one")
    _require(isinstance(sources, list), entry_id, "sources must be a list")
    source_urls = [_validate_source(source, entry_id, repo_root) for source in sources]
    _require(len(source_urls) == len(set(source_urls)), entry_id, "duplicate source URL")

    topics = entry.get("topics") or []
    _require(isinstance(topics, list), entry_id, "topics must be a list")
    for topic in topics:
        _require(bool(TOPIC_ID.fullmatch(str(topic))), entry_id, f"invalid topic id: {topic!r}")

    if "posed" in entry:
        _require(
            isinstance(entry["posed"], int) and not isinstance(entry["posed"], bool),
            entry_id,
            "posed must be an integer year",
        )
        _require(0 < entry["posed"] <= 9999, entry_id, "posed year is outside 1..9999")

    if "measured" in entry:
        measured = entry["measured"]
        _require(isinstance(measured, dict) and measured, entry_id, "measured must be an object")
        for name, value in measured.items():
            _require(bool(name), entry_id, "measured field has an empty name")
            _require(
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(value)
                and value >= 0,
                entry_id,
                f"measured field {name!r} must be a finite non-negative number",
            )

    if layer == "blocked":
        blocker = entry.get("blocker")
        _require(
            blocker in BLOCKER_TYPES,
            entry_id,
            f"blocker must be one of {sorted(BLOCKER_TYPES)}, got {blocker!r}",
        )

    if layer == "blind-spots":
        _require(bool(entry.get("kind")), entry_id, "blind spot missing kind")
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
        validate_entry(entry, layer, seen, REPO_ROOT)
    return entries


def load_all(curated_dir: Path = CURATED_DIR) -> dict[str, list[dict]]:
    return {layer: load_layer(layer, curated_dir) for layer in ("open", "blocked", "blind-spots")}


def main() -> None:
    layers = load_all()
    for layer, entries in layers.items():
        print(f"  {layer:<12} {len(entries):>3} entries OK")


if __name__ == "__main__":
    main()
