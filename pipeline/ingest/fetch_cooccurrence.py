"""Fetch topic-level co-occurrence rows from OpenAlex.

`filter` and `group_by` compose, so one request returns an entire row of the co-occurrence matrix:

    /works?filter=topics.id:T10387&group_by=topics.id&per-page=200

That is 4,516 requests for a full matrix rather than the ~10M pairwise requests a naive reading of
the API suggests, and it makes the whole thing feasible without downloading the 400 GB snapshot.

**Truncation.** group_by returns at most 200 groups and cannot paginate (page=2 is an explicit
API error), so a row lists only its 200 largest partners. Gaps live in the tail that gets cut off.
This is survivable because the 200th group's count is a hard ceiling on every partner not listed:
if the smallest reported co-occurrence is 77, no omitted partner exceeds 77. Downstream we
substitute that ceiling, which makes every gap score a conservative lower bound — a pair that
looks like a gap under the ceiling is a gap under its true value.

When a row returns fewer than 200 groups it is exact: every unlisted partner is a true zero.

Run:  python -m pipeline.ingest.fetch_cooccurrence --slice pre1986
      python -m pipeline.ingest.fetch_cooccurrence --slice all --domains 1 4
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from pipeline.openalex_client import OpenAlexClient, RateLimited
from pipeline.paths import COOCCURRENCE_DIR, TAXONOMY_PATH, ensure_dirs

# Named time slices. Validation needs a pre-Swanson view; the shipped map needs everything.
SLICES = {
    "all": {},
    "pre1986": {"to_publication_date": "1985-12-31"},
    "pre2015": {"to_publication_date": "2014-12-31"},
}

MAX_GROUPS = 200  # API hard cap; 201 returns a pagination error.


def load_topics(domains: list[str] | None) -> list[dict]:
    """Topics forming the analysis set, in ascending id order.

    Ordering is deterministic so a sweep can resume, but a partial ID-ordered prefix is not assumed
    to be representative. Every artifact reports exact coverage and remains unvalidated until the
    planned analysis set is complete.
    """
    taxonomy = json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))
    topics = taxonomy["topics"]
    if domains:
        topics = [t for t in topics if t.get("domain") in set(domains)]
    return sorted(topics, key=lambda t: t["id"])


def fetch_row(client: OpenAlexClient, topic_id: str, slice_filters: dict) -> dict:
    """Fetch one topic's co-occurrence row.

    Returns the topic's marginal (works carrying this topic in the slice), its partner counts,
    and the ceiling bounding every partner absent from the response.
    """
    filters = {"topics.id": topic_id, **slice_filters}
    filter_str = ",".join(f"{k}:{v}" for k, v in filters.items())
    params = {"filter": filter_str, "group_by": "topics.id", "per-page": MAX_GROUPS}

    payload = client.get("works", params)
    groups = payload.get("group_by", [])

    partners = {}
    for group in groups:
        partner = group["key"].rstrip("/").split("/")[-1]
        if partner == topic_id:
            continue  # self-count duplicates the marginal
        partners[partner] = group["count"]

    truncated = len(groups) >= MAX_GROUPS
    # Every partner missing from a truncated row is bounded by the smallest reported count.
    # An untruncated row is exact, so missing partners are true zeros.
    ceiling = min(partners.values()) if (truncated and partners) else 0

    return {
        "topic": topic_id,
        "marginal": payload["meta"]["count"],
        "partners": partners,
        "truncated": truncated,
        "ceiling": ceiling,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source_url": payload.get("_lacuna_source_url", ""),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slice", default="pre1986", choices=sorted(SLICES))
    parser.add_argument(
        "--domains",
        nargs="*",
        default=["1", "4"],
        help="OpenAlex domain ids to include (1 Life, 2 Social, 3 Physical, 4 Health). "
        "Empty means all 4,516 topics.",
    )
    args = parser.parse_args()

    ensure_dirs()
    out_dir = COOCCURRENCE_DIR / args.slice
    out_dir.mkdir(parents=True, exist_ok=True)

    topics = load_topics(args.domains)
    client = OpenAlexClient()
    slice_filters = SLICES[args.slice]

    pending = [t for t in topics if not (out_dir / f"{t['id']}.json").exists()]
    print(
        f"slice={args.slice} domains={args.domains or 'all'}  "
        f"{len(topics)} topics, {len(topics) - len(pending)} already fetched, {len(pending)} pending"
    )

    written = 0
    for index, topic in enumerate(pending, start=1):
        try:
            row = fetch_row(client, topic["id"], slice_filters)
        except RateLimited as exhausted:
            print(
                f"\nstopped after {written} rows: {exhausted}"
                f"\n  {len(pending) - written} still pending — re-run this command to resume."
            )
            break

        (out_dir / f"{topic['id']}.json").write_text(json.dumps(row), encoding="utf-8")
        written += 1

        if index % 50 == 0 or index == len(pending):
            print(
                f"  {index}/{len(pending)}  {topic['id']}  "
                f"marginal={row['marginal']:,} partners={len(row['partners'])} "
                f"credits_left={client.credits_remaining}"
            )
    else:
        print(f"\ncomplete: {written} rows written to {out_dir}")

    print(f"api calls {client.calls_made}, cache hits {client.cache_hits}")


if __name__ == "__main__":
    main()
