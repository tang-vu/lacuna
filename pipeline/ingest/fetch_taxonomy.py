"""Ingest the OpenAlex classification tree: domains -> fields -> subfields -> topics.

The tree is scaffolding, not the product — but every gap is a pair of nodes in it, so if the tree
is wrong everything downstream is wrong silently. Hence the count assertions: this module refuses
to write an artifact when OpenAlex returns a shape we did not expect.

Run:  python -m pipeline.ingest.fetch_taxonomy
"""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.openalex_client import OpenAlexClient

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Measured live on 2026-07-27. These are assertions, not documentation: OpenAlex reshapes its
# taxonomy occasionally, and a silent change would move every gap score without explanation.
# A mismatch is a stop-and-report event, not a warning to scroll past.
EXPECTED_COUNTS = {"domains": 4, "fields": 26, "subfields": 252, "topics": 4516}

# Trimmed to what the pipeline actually uses; full responses stay in the request cache.
LEVEL_FIELDS = {
    "domains": "id,display_name,works_count",
    "fields": "id,display_name,works_count,domain",
    "subfields": "id,display_name,works_count,field,domain",
    "topics": "id,display_name,description,keywords,works_count,subfield,field,domain",
}


class TaxonomyCountMismatch(Exception):
    """OpenAlex returned a different number of nodes than this pipeline was built against."""


def short_id(openalex_id: str) -> str:
    """'https://openalex.org/T10387' -> 'T10387'. Used as the key everywhere downstream."""
    return openalex_id.rstrip("/").split("/")[-1]


def fetch_level(client: OpenAlexClient, level: str) -> list[dict]:
    """Fetch every node at one taxonomy level, verifying the count OpenAlex reports."""
    reported = client.get(level, {"per-page": 1})["meta"]["count"]
    expected = EXPECTED_COUNTS[level]
    if reported != expected:
        raise TaxonomyCountMismatch(
            f"/{level}: OpenAlex reports {reported} nodes, pipeline expects {expected}. "
            f"The taxonomy changed. Review the gap metric's assumptions, update EXPECTED_COUNTS, "
            f"and re-run validation before trusting any artifact built on this tree."
        )

    nodes = list(client.paginate(level, {"select": LEVEL_FIELDS[level]}))
    if len(nodes) != expected:
        raise TaxonomyCountMismatch(
            f"/{level}: paginated {len(nodes)} nodes but meta.count said {expected}. "
            f"Pagination is dropping records; do not build on this."
        )
    return nodes


def normalise(level: str, node: dict) -> dict:
    """Flatten OpenAlex's nested parent objects into plain short ids."""
    out = {
        "id": short_id(node["id"]),
        "display_name": node["display_name"],
        "works_count": node["works_count"],
    }
    for parent in ("subfield", "field", "domain"):
        if node.get(parent):
            out[parent] = short_id(node[parent]["id"])
    if level == "topics":
        out["description"] = node.get("description") or ""
        out["keywords"] = node.get("keywords") or []
    return out


def main() -> None:
    client = OpenAlexClient()
    taxonomy: dict[str, list[dict]] = {}

    for level in ("domains", "fields", "subfields", "topics"):
        nodes = fetch_level(client, level)
        taxonomy[level] = [normalise(level, n) for n in nodes]
        print(f"  {level:<10} {len(nodes):>5} nodes  (expected {EXPECTED_COUNTS[level]}) OK")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DATA_DIR / "taxonomy.json"
    out_path.write_text(json.dumps(taxonomy, indent=1), encoding="utf-8")

    topics = taxonomy["topics"]
    largest = max(topics, key=lambda t: t["works_count"])
    print(
        f"\nwrote {out_path}"
        f"\n  api calls {client.calls_made}, cache hits {client.cache_hits}"
        f"\n  credits remaining {client.credits_remaining}"
        f"\n  largest topic: {largest['id']} {largest['display_name']} "
        f"({largest['works_count']:,} works)"
    )


if __name__ == "__main__":
    main()
