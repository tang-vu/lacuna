"""Pure reference formula for the frozen autonomous prospective metric v1.

This module performs no repository or data I/O.  It defines the integer edge
rule, fixed-point common-neighbour scores, and outcome-independent total-order
tie key that must be reproduced by any full-corpus scoring engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_EVEN, localcontext
from typing import Iterable

Q48_SCALE = 1 << 48
DECIMAL_PRECISION = 80
MAX_U64 = (1 << 64) - 1
TIE_SALT_U64 = 0x7A6B4D2F19C3E805


class AutonomousMetricV1FormulaError(ValueError):
    pass


@dataclass(frozen=True)
class LocalScores:
    adamic_adar_q48: int
    resource_allocation_q48: int
    common_neighbors: int


def _require_u64(value: int, name: str) -> None:
    if type(value) is not int or not 0 <= value <= MAX_U64:
        raise AutonomousMetricV1FormulaError(f"{name} is outside uint64")


def positive_association_edge(
    direct_count: int,
    denominator: int,
    left_support: int,
    right_support: int,
) -> bool:
    """Return the exact unweighted-backbone edge predicate.

    The operational implementation must evaluate both products without
    overflow.  Equality is not an edge.
    """
    for value, name in (
        (direct_count, "direct_count"),
        (denominator, "denominator"),
        (left_support, "left_support"),
        (right_support, "right_support"),
    ):
        _require_u64(value, name)
    if direct_count == 0 or denominator == 0:
        return False
    return direct_count * denominator > left_support * right_support


def adamic_adar_weight_q48(degree: int) -> int:
    """Return floor(2**48 / ln(degree)) under the frozen Decimal context."""
    if type(degree) is not int or degree < 2:
        raise AutonomousMetricV1FormulaError("Adamic-Adar degree must be at least two")
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        context.rounding = ROUND_HALF_EVEN
        logarithm = Decimal(degree).ln(context=context)
        quotient = Decimal(Q48_SCALE) / logarithm
        weight = int(quotient.to_integral_value(rounding=ROUND_FLOOR))
    _require_u64(weight, "Adamic-Adar weight")
    return weight


def resource_allocation_weight_q48(degree: int) -> int:
    if type(degree) is not int or degree < 2:
        raise AutonomousMetricV1FormulaError(
            "resource-allocation degree must be at least two"
        )
    return Q48_SCALE // degree


def local_scores(common_neighbor_degrees: Iterable[int]) -> LocalScores:
    adamic_adar = 0
    resource_allocation = 0
    common_neighbors = 0
    for degree in common_neighbor_degrees:
        adamic_adar += adamic_adar_weight_q48(degree)
        resource_allocation += resource_allocation_weight_q48(degree)
        common_neighbors += 1
        if adamic_adar > MAX_U64 or resource_allocation > MAX_U64:
            raise AutonomousMetricV1FormulaError("fixed-point score overflowed uint64")
        if common_neighbors > 0xFFFFFFFF:
            raise AutonomousMetricV1FormulaError("common-neighbor count overflowed uint32")
    return LocalScores(adamic_adar, resource_allocation, common_neighbors)


def jaccard_denominator(left_degree: int, right_degree: int, common_neighbors: int) -> int:
    for value, name in (
        (left_degree, "left_degree"),
        (right_degree, "right_degree"),
        (common_neighbors, "common_neighbors"),
    ):
        if type(value) is not int or value < 0:
            raise AutonomousMetricV1FormulaError(f"{name} must be a non-negative integer")
    if common_neighbors > min(left_degree, right_degree):
        raise AutonomousMetricV1FormulaError("common-neighbor count exceeds endpoint degree")
    return max(1, left_degree + right_degree - common_neighbors)


def prevalence_score(left_support: int, right_support: int) -> int:
    _require_u64(left_support, "left_support")
    _require_u64(right_support, "right_support")
    score = left_support * right_support
    _require_u64(score, "prevalence score")
    return score


def preferential_attachment_score(left_degree: int, right_degree: int) -> int:
    _require_u64(left_degree, "left_degree")
    _require_u64(right_degree, "right_degree")
    score = left_degree * right_degree
    _require_u64(score, "preferential-attachment score")
    return score


def splitmix64(value: int) -> int:
    """Return the frozen unsigned SplitMix64 permutation."""
    _require_u64(value, "splitmix64 input")
    value = (value + 0x9E3779B97F4A7C15) & MAX_U64
    value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & MAX_U64
    value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & MAX_U64
    return (value ^ (value >> 31)) & MAX_U64


def tie_key(pair_key: int) -> int:
    _require_u64(pair_key, "pair_key")
    return splitmix64(pair_key ^ TIE_SALT_U64)


def descending_integer_rank_key(score: int, pair_key: int) -> tuple[int, int, int]:
    """Sort key for integer-valued rankings: score desc, tie key asc, pair key asc."""
    _require_u64(score, "score")
    _require_u64(pair_key, "pair_key")
    return (-score, tie_key(pair_key), pair_key)

