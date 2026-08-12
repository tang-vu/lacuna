from __future__ import annotations

import numpy as np

from pipeline.benchmark.autonomous_metric_v1 import (
    SCORE_DTYPE,
    WEIGHT_DTYPE,
    _degree_statistics,
    build_weight_bytes,
)
from pipeline.benchmark.autonomous_metric_v1_formula import (
    adamic_adar_weight_q48,
    resource_allocation_weight_q48,
)


def test_frozen_score_record_is_exactly_48_little_endian_bytes():
    assert SCORE_DTYPE.itemsize == 48
    assert SCORE_DTYPE.fields["pair_key"][1] == 0
    assert SCORE_DTYPE.fields["common_neighbors"][1] == 32
    assert SCORE_DTYPE.fields["preferential_attachment"][1] == 40


def test_degree_weight_bytes_match_reference_for_every_fixture_degree():
    rows = np.frombuffer(build_weight_bytes(17), dtype=WEIGHT_DTYPE)

    assert rows.size == 18
    assert not rows[:2].view("<u8").any()
    for degree in range(2, rows.size):
        assert int(rows["adamic_adar_q48"][degree]) == adamic_adar_weight_q48(degree)
        assert int(rows["resource_allocation_q48"][degree]) == (
            resource_allocation_weight_q48(degree)
        )


def test_degree_statistics_use_frozen_integer_nearest_rank():
    degrees = np.arange(101, dtype="<u8")

    assert _degree_statistics(degrees) == (0, 50, 90, 99, 100)
