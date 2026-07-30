"""Run the pre-registered validation of the gap metric.

Criteria live in docs/metric-validation-preregistration.md and were committed before any gap score
existed. This module only measures against them; it must never be edited to change what counts as
a pass. If the metric fails, the output of this run is the finding.

Run:  python -m pipeline.validate.validate_swanson
"""

from __future__ import annotations

import json

from pipeline.metric.gap_score import load_matrix, load_taxonomy_counts, score_pairs
from pipeline.paths import TAXONOMY_PATH

# The pair Swanson connected in 1986, mapped to the topics carrying each literature.
TARGET = ("T11330", "T10387")

PRE1986_TOTAL_WORKS = 38_458_832

# Percentile thresholds, fixed in advance. Lower percentile rank = better (1.0 means top 1%).
THRESHOLDS = [
    (0.1, "STRONG PASS", "metric ships as-is"),
    (1.0, "PASS", "metric ships, labelled exploratory"),
    (5.0, "WEAK", "ships only alongside published controls and audit"),
]

# Semantically distant pairs that must NOT rank highly. A metric that ranks everything highly has
# discovered nothing. Chosen within the analysis set's domains, since the scored space is
# biomedical; each pair is unrelated by any reading.
NEGATIVE_CONTROLS = [
    ("T10450", "T11330"),  # Aquaculture Nutrition x Systemic Sclerosis
    ("T12924", "T10152"),  # Dermatological/Skeletal Disorders x Animal Nutrition
]


def percentile_rank(results: list[dict], pair: tuple[str, str]) -> tuple[int, float, dict] | None:
    """Position of a pair in the ranking, as a percentile where 0 is best."""
    key = frozenset(pair)
    for index, row in enumerate(results):
        if frozenset((row["topic_a"], row["topic_b"])) == key:
            return index, 100.0 * index / len(results), row
    return None


def verdict_for(percentile: float) -> tuple[str, str]:
    for cutoff, name, consequence in THRESHOLDS:
        if percentile <= cutoff:
            return name, consequence
    return "FAIL", "computed layer does not ship as a discovery tool"


def main() -> None:
    taxonomy = json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))
    names = {t["id"]: t["display_name"] for t in taxonomy["topics"]}

    matrix = load_matrix("pre1986", PRE1986_TOTAL_WORKS)
    results = score_pairs(matrix, load_taxonomy_counts())

    print(f"analysis set   : {len(matrix.topic_ids)} topics fetched")
    print(f"scored pairs   : {len(results):,} (after support and expectation guards)")
    print(f"total works    : {matrix.total_works:,} (pre-1986)\n")

    found = percentile_rank(results, TARGET)
    if found is None:
        print(
            f"TARGET PAIR NOT SCORED: {TARGET[0]} x {TARGET[1]}\n"
            "  Either the sweep has not reached both topics, or the pair was dropped by a guard.\n"
            "  Verdict cannot be computed yet."
        )
        return

    rank, percentile, row = found
    verdict, consequence = verdict_for(percentile)

    print("=== target pair ===")
    print(f"  {row['topic_a']} {names.get(row['topic_a'], '?')}")
    print(f"  {row['topic_b']} {names.get(row['topic_b'], '?')}")
    print(f"  observed {row['observed']:.0f} vs expected {row['expected']} "
          f"(s_a={row['s_a']:,} s_b={row['s_b']:,})")
    print(f"  similarity {row['similarity']}  deficit_bits {row['deficit_bits']}")
    print(f"  gap_score {row['gap_score']}")
    print(f"  rank {rank + 1:,} of {len(results):,}  ->  top {percentile:.3f}%\n")

    print("=== negative controls (must fall below 50th percentile) ===")
    controls_ok = True
    for control in NEGATIVE_CONTROLS:
        hit = percentile_rank(results, control)
        if hit is None:
            print(f"  {control[0]} x {control[1]}: not scored (skipped)")
            continue
        _, control_pct, control_row = hit
        ok = control_pct > 50.0
        controls_ok &= ok
        print(
            f"  {'ok  ' if ok else 'FAIL'} {control[0]} x {control[1]}  "
            f"top {control_pct:.1f}%  similarity {control_row['similarity']}"
        )

    print(f"\n=== verdict: {verdict} ===")
    print(f"  {consequence}")
    if not controls_ok:
        print(
            "  NEGATIVE CONTROLS FAILED — this overrides the verdict above. A metric that also\n"
            "  ranks unrelated pairs highly is ranking on size or vector density, not structure."
        )

    print("\n=== top 15 gaps by score ===")
    for row in results[:15]:
        print(
            f"  {row['gap_score']:.3f}  sim {row['similarity']:.3f}  "
            f"obs {row['observed']:>5.0f}/exp {row['expected']:>8.1f}  "
            f"{names.get(row['topic_a'], '?')[:34]:<34} | {names.get(row['topic_b'], '?')[:34]}"
        )


if __name__ == "__main__":
    main()
