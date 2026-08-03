"""Shared guards that keep metric output out of pre-metric selection records."""

from __future__ import annotations

FORBIDDEN_OUTPUT_FIELDS = frozenset(
    {
        "score",
        "rank",
        "percentile",
        "metric_output",
        "candidate_score",
    }
)


def find_forbidden_fields(value: object, path: str = "$") -> list[str]:
    found = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key in FORBIDDEN_OUTPUT_FIELDS:
                found.append(child_path)
            found.extend(find_forbidden_fields(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(find_forbidden_fields(child, f"{path}[{index}]"))
    return found
