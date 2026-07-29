"""Inspect the raw evidence for one fetched topic pair.

This command does not generate a hypothesis. The current metric failed its pre-registered
validation, so its output is diagnostic evidence rather than a discovery claim.

Run:
    python -m pipeline.inspect_gap "Fatty Acid Research" "Systemic Sclerosis"
"""

from __future__ import annotations

import argparse
import json

from pipeline.metric.gap_score import load_matrix, load_taxonomy_counts, pair_evidence
from pipeline.openalex_client import OpenAlexClient
from pipeline.paths import TAXONOMY_PATH

SLICE_TOTALS = {"pre1986": 38_458_832}


def load_topics() -> list[dict]:
    taxonomy = json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))
    return taxonomy["topics"]


def resolve_topic(value: str, topics: list[dict]) -> dict:
    """Resolve an exact ID/name or an unambiguous case-insensitive name fragment."""
    folded = value.casefold()
    exact = [
        topic
        for topic in topics
        if topic["id"].casefold() == folded or topic["display_name"].casefold() == folded
    ]
    if len(exact) == 1:
        return exact[0]

    matches = [topic for topic in topics if folded in topic["display_name"].casefold()]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ValueError(f"no OpenAlex topic matches {value!r}")

    choices = ", ".join(f"{topic['id']} {topic['display_name']}" for topic in matches[:10])
    suffix = "" if len(matches) <= 10 else f", ... ({len(matches)} matches)"
    raise ValueError(f"ambiguous topic {value!r}: {choices}{suffix}")


def inspect(topic_a: str, topic_b: str, slice_name: str = "pre1986") -> dict:
    topics = load_topics()
    names = {topic["id"]: topic["display_name"] for topic in topics}
    a = resolve_topic(topic_a, topics)
    b = resolve_topic(topic_b, topics)

    matrix = load_matrix(slice_name, SLICE_TOTALS[slice_name])
    evidence = pair_evidence(matrix, load_taxonomy_counts(), a["id"], b["id"])
    client = OpenAlexClient()

    return {
        "status": "diagnostic_only",
        "validation_warning": (
            "Metric v2 failed the pre-registered Swanson reproduction; this pair is not a "
            "validated gap or discovery."
        ),
        **evidence,
        "name_a": a["display_name"],
        "name_b": b["display_name"],
        "bridges": [
            {**bridge, "display_name": names.get(bridge["topic"], bridge["topic"])}
            for bridge in evidence["bridges"]
        ],
        "slice": slice_name,
        "total_works": matrix.total_works,
        "verify_url": client.build_public_url(
            "works",
            {
                "filter": (
                    f"topics.id:{a['id']},topics.id:{b['id']},"
                    "to_publication_date:1985-12-31"
                ),
                "per-page": 1,
            },
        ),
    }


def render_text(result: dict) -> str:
    observed_prefix = "<=" if result["observed_kind"] == "upper_bound" else ""
    lines = [
        "DIAGNOSTIC ONLY — current metric failed validation",
        f"{result['topic_a']} {result['name_a']}",
        f"{result['topic_b']} {result['name_b']}",
        "",
        (
            f"observed {observed_prefix}{result['observed']:g} "
            f"({result['observed_kind'].replace('_', ' ')})"
        ),
        f"expected {result['expected']:g}",
        f"marginals {result['s_a']:,} × {result['s_b']:,} / {result['total_works']:,}",
        f"deficit p={result['p_value']:.6g}  deficit_bits={result['deficit_bits']:g}",
        f"bridge={result['similarity']:g}  combined score={result['gap_score']:g}",
        f"eligible={str(result['eligible']).lower()}",
        "",
        "strongest intermediate topics:",
    ]
    if result["bridges"]:
        lines.extend(
            f"  {bridge['strength']:.5f}  {bridge['topic']} {bridge['display_name']}"
            for bridge in result["bridges"]
        )
    else:
        lines.append("  none observed")

    lines.extend(["", "row sources:"])
    lines.extend(f"  {url}" for url in result["row_source_urls"])
    lines.extend(["exact-count verification:", f"  {result['verify_url']}"])
    if result["excluded_as_generalist"]:
        lines.append(
            "excluded generalist endpoint(s): "
            + ", ".join(result["excluded_as_generalist"])
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("topic_a")
    parser.add_argument("topic_b")
    parser.add_argument("--slice", choices=sorted(SLICE_TOTALS), default="pre1986")
    parser.add_argument("--json", action="store_true", help="emit structured JSON")
    args = parser.parse_args()

    try:
        result = inspect(args.topic_a, args.topic_b, args.slice)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    print(json.dumps(result, indent=2) if args.json else render_text(result))


if __name__ == "__main__":
    main()
